#!/usr/bin/env python3
"""Build the play-area polygon from the eligible stations.

General rule (city-agnostic; works for any metro once stations.json exists):
a Census place (city / town / CDP) is IN the play area if EITHER
  1. it contains an eligible station, OR
  2. it is *reachable / hideable* — any part of it lies within the largest
     hiding-zone radius (0.5 mi) of an eligible station, OR
  3. it is *transit-enclosed* — an enclave whose land border is essentially all
     in-play places and that touches no out-of-play place (e.g. Alameda, Foster
     City, Newark, Piedmont, Emeryville). This keeps islands separated only by
     water/in-play cities while excluding cities that open onto out-of-play
     open space (Los Altos, Moraga's hills, Livermore).
Plus a manual keep/drop list in play_area_overrides.json (e.g. Cupertino).

POIs are then clipped to this polygon (see dedup_poi.py): strictly inside for
natural categories (park, mountain); a small 150 m shoreline buffer is allowed
for the other categories so pier/waterfront pins (Exploratorium, USS Hornet…)
that sit just over the water inside an in-play city are kept.

Emits (committed):
  play_area.geojson           raw union of kept places
  play_area_buffered.geojson  union buffered by SHORELINE_BUF_M (pier rescue)
  play_area_cities.json       sorted keep list with the reason each qualified
and copies the raw union into the app at
  ../../<app>/src/data/play-area.geojson.json
"""
import json, math, os, sys, io, zipfile, urllib.request
from shapely.geometry import shape, Point, mapping
from shapely.ops import transform, unary_union

HERE = os.path.dirname(os.path.abspath(__file__))
STATIONS = os.environ.get("STATIONS_JSON",
    os.path.join(HERE, "..", "..", "repos", "bayarea-hideandseek", "src", "data", "stations.json"))
APP_PLAY_AREA = os.environ.get("APP_PLAY_AREA",
    os.path.join(HERE, "..", "..", "repos", "bayarea-hideandseek", "src", "data", "play-area.geojson.json"))
OVERRIDES = os.path.join(HERE, "play_area_overrides.json")
CACHE = os.path.join(HERE, "_census_place")

HIDE_RADIUS_MI = 0.5            # largest game-size hiding radius
SHORELINE_BUF_M = 150.0        # pier/waterfront rescue for non-natural POIs
ENCLAVE_IN_MIN = 0.30          # >= this share of border adjacent to in-play
ENCLAVE_OUT_MAX = 0.12         # <= this share of border adjacent to out-of-play places
ADJ_TOL_M = 150.0
# Census place shapefile (cartographic boundary, 1:500k, NAD83 ~ WGS84 for our use)
CBF_URL = "https://www2.census.gov/geo/tiger/GENZ2023/shp/cb_2023_06_place_500k.zip"
CBF_STEM = "cb_2023_06_place_500k"

LAT0 = 37.6
M = 111320.0


def _proj(lat0):
    cos0 = math.cos(math.radians(lat0))
    def to_m(x, y, z=None): return (x * M * cos0, y * M)
    def to_ll(x, y, z=None): return (x / (M * cos0), y / M)
    return to_m, to_ll


def ensure_shapefile():
    shp = os.path.join(CACHE, CBF_STEM + ".shp")
    if os.path.exists(shp):
        return shp
    os.makedirs(CACHE, exist_ok=True)
    print(f"downloading {CBF_URL} ...", file=sys.stderr)
    data = urllib.request.urlopen(CBF_URL, timeout=180).read()
    zipfile.ZipFile(io.BytesIO(data)).extractall(CACHE)
    return shp


def load_places(bbox):
    import shapefile
    r = shapefile.Reader(ensure_shapefile())
    flds = [f[0] for f in r.fields[1:]]
    out = {}
    for sh, rec in zip(r.shapes(), r.records()):
        d = dict(zip(flds, rec))
        bb = sh.bbox
        if bb[2] < bbox[0] or bb[0] > bbox[1] or bb[3] < bbox[2] or bb[1] > bbox[3]:
            continue
        g = shape(sh.__geo_interface__)
        if not g.is_valid:
            g = g.buffer(0)
        out[d["NAMELSAD"]] = g
    return out


def main():
    stations = json.load(open(STATIONS))
    lats = [s["lat"] for s in stations]
    lons = [s["lon"] for s in stations]
    lat0 = sum(lats) / len(lats)
    to_m, to_ll = _proj(lat0)
    pad = 0.5
    bbox = (min(lons) - pad, max(lons) + pad, min(lats) - pad, max(lats) + pad)

    places_ll = load_places(bbox)
    places_m = {n: transform(to_m, g) for n, g in places_ll.items()}
    station_cities = {s["city"] for s in stations}
    missing = sorted(c for c in station_cities if c not in places_ll)
    if missing:
        print("WARN station cities with no place polygon:", missing, file=sys.stderr)

    stpts = [Point(*to_m(s["lon"], s["lat"])) for s in stations]
    zone = unary_union([p.buffer(HIDE_RADIUS_MI * 1609.344) for p in stpts])
    reachable = {n for n, g in places_m.items() if g.intersects(zone)}
    base = (station_cities & set(places_m)) | reachable
    baseU = unary_union([places_m[n] for n in base])

    reason = {}
    for n in station_cities & set(places_m):
        reason[n] = "station"
    for n in reachable - (station_cities & set(places_m)):
        reason[n] = "reachable"

    # transit-enclosed enclaves
    nonbase = [n for n in places_m if n not in base]

    def frac(b, other):
        return b.intersection(other.buffer(ADJ_TOL_M)).length / b.length if b.length else 0.0

    for n in nonbase:
        b = places_m[n].boundary
        others = [places_m[x] for x in nonbase if x != n]
        ou = unary_union(others) if others else None
        fi = frac(b, baseU)
        fo = frac(b, ou) if ou is not None else 0.0
        if fi >= ENCLAVE_IN_MIN and fo <= ENCLAVE_OUT_MAX:
            reason[n] = "enclave"

    ov = json.load(open(OVERRIDES)) if os.path.exists(OVERRIDES) else {}
    for n in ov.get("keep", []):
        if n not in places_ll:
            print(f"WARN override keep not found: {n!r}", file=sys.stderr)
        else:
            reason[n] = reason.get(n, "manual-keep")
    drop = set(ov.get("drop", []))
    for n in drop:
        reason.pop(n, None)

    keep = sorted(reason)
    union_ll = unary_union([places_ll[n] for n in keep])
    union_m = transform(to_m, union_ll)
    buf_ll = transform(to_ll, union_m.buffer(SHORELINE_BUF_M))

    feat = {"type": "Feature", "properties": {"name": "play-area"},
            "geometry": mapping(union_ll)}
    json.dump(feat, open(os.path.join(HERE, "play_area.geojson"), "w"))
    json.dump({"type": "Feature", "properties": {"name": "play-area-buffered"},
               "geometry": mapping(buf_ll)}, open(os.path.join(HERE, "play_area_buffered.geojson"), "w"))
    json.dump({"hide_radius_mi": HIDE_RADIUS_MI, "shoreline_buffer_m": SHORELINE_BUF_M,
               "count": len(keep),
               "cities": [{"name": n, "reason": reason[n]} for n in keep]},
              open(os.path.join(HERE, "play_area_cities.json"), "w"), indent=1)

    if os.path.exists(os.path.dirname(APP_PLAY_AREA)):
        # The app only uses this polygon for display (out-of-play dimming mask,
        # satellite clip-path / tile culling), not for any correctness check, so
        # ship a simplified version (~40 m tolerance) to keep the clip-path light.
        simp_ll = transform(to_ll, union_m.simplify(40.0, preserve_topology=True))
        app_feat = {"type": "Feature", "properties": {"name": "play-area"},
                    "geometry": mapping(simp_ll)}
        json.dump({"type": "FeatureCollection", "features": [app_feat]},
                  open(APP_PLAY_AREA, "w"))
        print("updated app play-area:", APP_PLAY_AREA)

    by = {}
    for n in keep:
        by.setdefault(reason[n], []).append(n)
    print(f"play area = {len(keep)} places")
    for r in ("station", "reachable", "enclave", "manual-keep"):
        if by.get(r):
            print(f"  {r:12} {len(by[r]):3}  {', '.join(by[r])}")


if __name__ == "__main__":
    main()
