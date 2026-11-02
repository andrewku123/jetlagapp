#!/usr/bin/env python3
"""Endgame play area: the decided map plus every station's endgame disk.

Rule (Andrew): the playable area of every map is the decided map unioned with a
disk around each station sized for two Curses of the Prosperous Home (x1.5 each,
drawn once + duplicated). A third is possible but too unlikely to plan for. So
the disk is the game size's zone radius x 1.5^2 (Medium: 0.25 x 2.25 =
0.5625 mi). Land outside the decided map but inside a
disk is in play like any other (POIs, city/ZIP lookups); open water past the
shore stays out.

Every play-area build calls `with_endgame_zones` before it writes the polygon
(build_play_area.py, build_la_play_area.py, build_sfmuni_region.py). Run this
script directly to patch an already-built region's committed data without a full
rebuild: it unions the zones into the app play area (and the POI pipeline's raw
and buffered play areas, where they exist), then adds the Census places and
ZCTAs of the new land to the city / ZIP layers. Idempotent.

    python3 scripts/endgame_zones.py --region dc
"""
import json
import math
import os
import sys

from shapely.geometry import shape, mapping, Polygon, MultiPolygon, GeometryCollection
from shapely.ops import transform, unary_union

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
REGION_SIZES = os.path.join(ROOT, "src", "data", "region-sizes.json")

# Must match SIZE_PARAMS.hidingZoneRadiusMi (src/data/questionSets.ts) and
# PROSPEROUS_FACTOR (src/lib/hidingZone.ts).
BASE_RADIUS_MI = {"small": 0.25, "medium": 0.25, "large": 0.5}
PROSPEROUS_FACTOR = 1.5
# Draw + duplicate. A third Prosperous Home can happen but is too rare to cover.
PLANNED_PROSPEROUS_HOMES = 2
# so the app's rendered 128-gon circle sits fully inside the unioned polygon
PAD_MI = 0.01
# drop clip slivers (~100 m^2) where the disk only grazes the existing border
MIN_PIECE_DEG2 = 1e-8
# New land thinner than ~2x this is shoreline noise (the play area and the water
# mask trace the coast from different sources), not land the disks really add.
SLIVER_OPEN_DEG = 0.0002  # ~20 m
# notches narrower than ~2x this between kept new land and the old border get filled
NOTCH_FILL_DEG = 0.0003  # ~30 m
SHORELINE_BUF_M = 150.0  # build_play_area.py's buffered (pier-rescue) play area

# poi_geo region id -> app region id (src/data/regions.ts, region-sizes.json)
APP_ID = {"bay": "bayarea"}


def max_hiding_radius_mi(app_region_id):
    size = json.load(open(REGION_SIZES))[app_region_id]
    return BASE_RADIUS_MI[size] * PROSPEROUS_FACTOR ** PLANNED_PROSPEROUS_HOMES


def geodesic_circle(lat, lon, radius_mi, n=128):
    """Same spherical metric (R = 6371 km, destination-point formula) as the
    app's circlePolygon in src/lib/geo.ts, so the polygon edge lines up with the
    drawn hiding-zone circle."""
    R = 6371000.0
    d = radius_mi * 1609.344 / R
    lat1, lon1 = math.radians(lat), math.radians(lon)
    pts = []
    for i in range(n):
        b = 2 * math.pi * i / n
        lat2 = math.asin(math.sin(lat1) * math.cos(d) + math.cos(lat1) * math.sin(d) * math.cos(b))
        lon2 = lon1 + math.atan2(math.sin(b) * math.sin(d) * math.cos(lat1),
                                 math.cos(d) - math.sin(lat1) * math.sin(lat2))
        pts.append((math.degrees(lon2), math.degrees(lat2)))
    return Polygon(pts)


def endgame_zones(stations, radius_mi, water=None):
    """Union of every station's endgame disk, minus open water."""
    zones = unary_union([geodesic_circle(s["lat"], s["lon"], radius_mi + PAD_MI) for s in stations])
    if water is not None and not water.is_empty:
        zones = zones.difference(water)
    return zones.buffer(0)


def polygonal(g):
    if g.is_empty or isinstance(g, (Polygon, MultiPolygon)):
        return g
    if isinstance(g, GeometryCollection):
        parts = [p for p in g.geoms if isinstance(p, (Polygon, MultiPolygon))]
        return unary_union(parts) if parts else Polygon()
    return Polygon()


def drop_slivers(g):
    parts = list(g.geoms) if hasattr(g, "geoms") else [g]
    return unary_union([p for p in parts if p.area >= MIN_PIECE_DEG2]) if parts else Polygon()


def new_land(play, stations, radius_mi, water=None):
    """The land the station disks add beyond `play`, without shoreline slivers."""
    ext = polygonal(endgame_zones(stations, radius_mi, water).difference(play))
    if ext.is_empty:
        return ext
    opened = ext.buffer(-SLIVER_OPEN_DEG).buffer(SLIVER_OPEN_DEG)
    kept = drop_slivers(polygonal(opened.intersection(ext).buffer(0)))
    if kept.is_empty:
        return kept
    # The opening rounds off the tapers where a disk arc meets the old border,
    # leaving notches in the outline. Close them back up, but only with disk land
    # next to a kept piece, so shoreline noise elsewhere stays out.
    both = unary_union([play, kept])
    closed = both.buffer(NOTCH_FILL_DEG).buffer(-NOTCH_FILL_DEG)
    fill = closed.intersection(ext).intersection(kept.buffer(2 * NOTCH_FILL_DEG))
    return drop_slivers(polygonal(unary_union([kept, polygonal(fill)]).buffer(0)))


def with_endgame_zones(play, stations, radius_mi, water=None):
    """`play` plus the station disks, as one valid polygon. Only the new land the
    disks add is unioned in, so an existing play area that already covers them
    comes back unchanged."""
    ext = new_land(play, stations, radius_mi, water)
    return play if ext.is_empty else unary_union([play, ext]).buffer(0)


def load_water(paths):
    gs = []
    for p in paths:
        d = json.load(open(os.path.join(ROOT, p)))
        for f in d.get("features", [d]):
            gs.append(shape(f["geometry"]).buffer(0))
    return unary_union(gs) if gs else None


def rounded(g, nd=6):
    return transform(lambda x, y, z=None: (round(x, nd), round(y, nd)), g)


def merge_into_layer(path, pieces):
    """Union each named piece into the feature of that name, or append it."""
    fc = json.load(open(path))
    byname = {f["properties"]["name"]: f for f in fc["features"]}
    for name, g in sorted(pieces.items()):
        g = rounded(polygonal(g))
        if g.is_empty:
            continue
        if name in byname:
            f = byname[name]
            f["geometry"] = mapping(polygonal(unary_union([shape(f["geometry"]).buffer(0), g]).buffer(0)))
        else:
            f = {"type": "Feature", "properties": {"name": name}, "geometry": mapping(g)}
            fc["features"].append(f)
            byname[name] = f
    json.dump(fc, open(path, "w"))
    return sorted(pieces)


def census_pieces(ext, readers, name_field):
    import shapefile
    minx, miny, maxx, maxy = ext.bounds
    out = {}
    for shp in readers:
        r = shapefile.Reader(shp)
        flds = [f[0] for f in r.fields[1:]]
        nf = next(f for f in name_field if f in flds)
        for sh, rec in zip(r.iterShapes(), r.iterRecords()):
            bx0, by0, bx1, by1 = sh.bbox
            if bx1 < minx or bx0 > maxx or by1 < miny or by0 > maxy:
                continue
            g = shape(sh.__geo_interface__).buffer(0)
            piece = drop_slivers(polygonal(g.intersection(ext)))
            if piece.is_empty:
                continue
            name = str(dict(zip(flds, rec))[nf])
            out[name] = unary_union([out[name], piece]) if name in out else piece
    return out


def main():
    import build_region_geo as brg
    import poi_geo

    region = poi_geo.region_from_argv()
    cfg = poi_geo.REGIONS[region]
    radius = max_hiding_radius_mi(APP_ID.get(region, region))
    stations = json.load(open(poi_geo.repo_path(region, "stations")))
    water = load_water(cfg.get("endgameWater", []))

    play_path = poi_geo.repo_path(region, "play")
    play_fc = json.load(open(play_path))
    play = unary_union([shape(f["geometry"]).buffer(0) for f in play_fc["features"]])
    ext = new_land(play, stations, radius, water)
    print(f"{region}: endgame disk {radius} mi, new land {ext.area:.7f} deg^2")
    if ext.is_empty:
        return
    new_play = unary_union([play, ext]).buffer(0)

    play_fc["features"] = [{"type": "Feature", "properties": play_fc["features"][0]["properties"],
                            "geometry": mapping(rounded(new_play))}]
    json.dump(play_fc, open(play_path, "w"))
    print("  updated", os.path.relpath(play_path, ROOT))

    lat0 = (ext.bounds[1] + ext.bounds[3]) / 2
    buf_deg = SHORELINE_BUF_M / (111320.0 * math.cos(math.radians(lat0)))
    for name, grow in (("play_area.geojson", ext), ("play_area_buffered.geojson", ext.buffer(buf_deg))):
        p = poi_geo.work(region, name)
        if not os.path.exists(p):
            continue
        feat = json.load(open(p))
        feat["geometry"] = mapping(unary_union([shape(feat["geometry"]).buffer(0), grow]).buffer(0))
        json.dump(feat, open(p, "w"))
        print("  updated", os.path.relpath(p, ROOT))

    place_shps = [brg.ensure_shapefile(brg.PLACE_URL.format(fips=fips), f"tl_2023_{fips}_place")
                  for fips, _ in cfg["states"]]
    names = merge_into_layer(poi_geo.repo_path(region, "places"),
                             census_pieces(ext, place_shps, ["NAMELSAD"]))
    print("  places:", ", ".join(names) or "(unincorporated)")
    zcta_shp = brg.ensure_shapefile(brg.ZCTA_URL, brg.ZCTA_STEM, brg.ZCTA_CACHE, "(~530 MB) ")
    names = merge_into_layer(poi_geo.repo_path(region, "zctas"),
                             census_pieces(ext, [zcta_shp], ["ZCTA5CE20", "ZCTA5CE10"]))
    print("  zctas:", ", ".join(names))


if __name__ == "__main__":
    sys.path.insert(0, HERE)
    main()
