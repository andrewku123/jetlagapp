#!/usr/bin/env python3
"""Build the per-city (3rd-admin / Census "place") polygons used by the
Matching -> city question: seeker's city is looked up from their coordinate
(point-in-polygon) and the eliminated-area shading uses the same polygons.

Output: src/data/places.geojson.json — a FeatureCollection of Polygon /
MultiPolygon features, one per in-play Census place, `properties.name` set to the
Census NAMELSAD (e.g. "Oakland city", "Ashland CDP", "Fairview CDP").

We emit EVERY Census place that lies inside the play area (city, town OR CDP),
each clipped to the play-area polygon. That way every *named* place — including
unincorporated CDPs like Fairview that build_play_area.py refilled as enclaves —
resolves to its own name, and only genuinely unnamed land (a BART bridge corridor
over the hills, filled bay water) is left uncovered so cityAt() can report it as
"unincorporated". Clipping to the play area (which is already shoreline-clipped)
also keeps a coastal click out of the bay and drops the bits of edge places
(Tiburon, Belvedere) that stick out into greyed-out land.

SFO exception: San Francisco International Airport sits on unincorporated San
Mateo County land but is owned by the City & County of San Francisco, so the
airport footprint (convex hull of the SFO/AirTrain stations, buffered) is merged
into "San Francisco city" — every SFO station and any click on the airport
resolves to SF.

REPLICABILITY: same per-city shape as build_measure_features.py. A new metro
supplies its own state place shapefile + play area; the question code
(src/lib/cities.ts, elimination + shading) is city-agnostic. The SFO merge is the
one Bay-specific override (an airport on unincorporated land owned by a city).

Source: Census TIGER/Line 2023 places for CA (tl_2023_06_place), the same file
build_play_area.py downloads (shared _census_place cache).
"""
import io
import json
import os
import sys
import zipfile
import urllib.request

from shapely.geometry import shape, mapping, MultiPoint, Polygon, MultiPolygon, GeometryCollection
from shapely.ops import unary_union


def polygonal(g):
    """Keep only the (multi)polygon part of a geometry — a clip against the play
    area can yield a GeometryCollection with stray boundary lines/points."""
    if g.is_empty:
        return g
    if isinstance(g, (Polygon, MultiPolygon)):
        return g
    if isinstance(g, GeometryCollection):
        parts = [p for p in g.geoms if isinstance(p, (Polygon, MultiPolygon))]
        return unary_union(parts) if parts else Polygon()
    return Polygon()

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "src", "data")
CACHE = os.path.join(HERE, "_census_place")
WATER_MASK = os.path.join(HERE, "bay_water_mask.geojson")
PLAY_AREA = os.path.join(DATA, "play-area.geojson.json")
STATIONS = os.path.join(DATA, "stations.json")

PLACE_URL = "https://www2.census.gov/geo/tiger/TIGER2023/PLACE/tl_2023_06_place.zip"
PLACE_STEM = "tl_2023_06_place"
SIMPLIFY_DEG = 0.0002  # ~22 m; plenty for point-in-polygon + shading, keeps file small
MIN_AREA_DEG2 = 1e-7   # drop sliver clip artifacts (~1000 m^2)
SFO_BUFFER_DEG = 0.006  # ~650 m buffer around the SFO station hull
STATE_OWNED_AIRPORT = "San Francisco International Airport"  # station name substring
AIRPORT_CITY = "San Francisco city"


def ensure_shapefile(url, stem):
    shp = os.path.join(CACHE, stem + ".shp")
    if os.path.exists(shp):
        return shp
    os.makedirs(CACHE, exist_ok=True)
    print(f"downloading {url} ...", file=sys.stderr)
    data = urllib.request.urlopen(url, timeout=180).read()
    zipfile.ZipFile(io.BytesIO(data)).extractall(CACHE)
    return shp


def load_play_area():
    fc = json.load(open(PLAY_AREA))
    g = shape(fc["features"][0]["geometry"])
    return g.buffer(0) if not g.is_valid else g


def sfo_hull():
    """Convex hull of the SFO airport / AirTrain stations, buffered — the airport
    footprint that gets folded into San Francisco city (SF owns SFO)."""
    sts = json.load(open(STATIONS))
    pts = [(s["lon"], s["lat"]) for s in sts
           if STATE_OWNED_AIRPORT in s["name"] or "SFO AirTrain" in s.get("lines", [])]
    if not pts:
        return None
    return MultiPoint(pts).convex_hull.buffer(SFO_BUFFER_DEG)


def main():
    import shapefile

    play = load_play_area()
    r = shapefile.Reader(ensure_shapefile(PLACE_URL, PLACE_STEM))
    flds = [f[0] for f in r.fields[1:]]

    # First pass: clip every place that overlaps the play area to the play area.
    clipped = {}
    for sh, rec in zip(r.shapes(), r.records()):
        d = dict(zip(flds, rec))
        name = d["NAMELSAD"]
        g = shape(sh.__geo_interface__)
        if not g.is_valid:
            g = g.buffer(0)
        if not g.intersects(play):
            continue
        g = polygonal(g.intersection(play))
        if not g.is_valid:
            g = g.buffer(0)
        if g.is_empty or g.area < MIN_AREA_DEG2:
            continue
        clipped[name] = g

    # SFO -> San Francisco: merge the airport footprint (minus any other place it
    # laps, so it only claims the genuinely-unincorporated airport land) into SF.
    hull = sfo_hull()
    if hull is not None:
        others = unary_union([g for n, g in clipped.items() if n != AIRPORT_CITY])
        sfo = polygonal(hull.intersection(play).difference(others))
        if not sfo.is_empty:
            base = clipped.get(AIRPORT_CITY)
            clipped[AIRPORT_CITY] = unary_union([base, sfo]) if base is not None else sfo
            print(f"merged SFO airport footprint into {AIRPORT_CITY}")

    out = {"type": "FeatureCollection", "features": []}
    for name in sorted(clipped):
        g = polygonal(clipped[name].simplify(SIMPLIFY_DEG, preserve_topology=True))
        if g.is_empty or g.area < MIN_AREA_DEG2:
            continue
        out["features"].append({
            "type": "Feature",
            "properties": {"name": name},
            "geometry": mapping(g),
        })

    dest = os.path.join(DATA, "places.geojson.json")
    with open(dest, "w") as f:
        json.dump(out, f)
    print(f"wrote {dest} — {len(out['features'])} places, "
          f"{os.path.getsize(dest)} bytes")


if __name__ == "__main__":
    main()
