#!/usr/bin/env python3
"""Build the per-city (3rd-admin / Census "place") polygons used by the
Matching -> city question: seeker's city is looked up from their coordinate
(point-in-polygon) and the eliminated-area shading uses the same polygons.

Output: src/data/places.geojson.json — a FeatureCollection of Polygon /
MultiPolygon features, one per in-play Census place, `properties.name` set to the
Census NAMELSAD (e.g. "Oakland city", "Ashland CDP") so it matches the `city`
field baked onto each station by build_attributes.py.

Only the play-area kept cities (scripts/play_area_cities.json -> cities[].name)
are emitted, so the set is exactly the cities a station can be in — and the
geometry is clipped to the real shoreline with the same AREAWATER water mask the
play area uses, so a coastal click doesn't fall in the bay.

REPLICABILITY: same per-city shape as build_measure_features.py. A new metro
supplies its own kept-cities list + state place shapefile; the question code
(src/lib/cities.ts, elimination + shading) is city-agnostic.

Source: Census TIGER/Line 2023 places for CA (tl_2023_06_place), the same file
build_play_area.py downloads (shared _census_place cache).
"""
import io
import json
import os
import sys
import zipfile
import urllib.request

from shapely.geometry import shape, mapping
from shapely.ops import unary_union

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "src", "data")
CACHE = os.path.join(HERE, "_census_place")
WATER_MASK = os.path.join(HERE, "bay_water_mask.geojson")
KEPT = os.path.join(HERE, "play_area_cities.json")

PLACE_URL = "https://www2.census.gov/geo/tiger/TIGER2023/PLACE/tl_2023_06_place.zip"
PLACE_STEM = "tl_2023_06_place"
SIMPLIFY_DEG = 0.0002  # ~22 m; plenty for point-in-polygon + shading, keeps file small


def ensure_shapefile(url, stem):
    shp = os.path.join(CACHE, stem + ".shp")
    if os.path.exists(shp):
        return shp
    os.makedirs(CACHE, exist_ok=True)
    print(f"downloading {url} ...", file=sys.stderr)
    data = urllib.request.urlopen(url, timeout=180).read()
    zipfile.ZipFile(io.BytesIO(data)).extractall(CACHE)
    return shp


def load_water_mask():
    if not os.path.exists(WATER_MASK):
        return None
    g = shape(json.load(open(WATER_MASK))["geometry"])
    return g.buffer(0) if not g.is_valid else g


def main():
    import shapefile

    kept = {c["name"] for c in json.load(open(KEPT))["cities"]}
    water = load_water_mask()
    r = shapefile.Reader(ensure_shapefile(PLACE_URL, PLACE_STEM))
    flds = [f[0] for f in r.fields[1:]]

    out = {"type": "FeatureCollection", "features": []}
    seen = set()
    for sh, rec in zip(r.shapes(), r.records()):
        d = dict(zip(flds, rec))
        name = d["NAMELSAD"]
        if name not in kept:
            continue
        g = shape(sh.__geo_interface__)
        if not g.is_valid:
            g = g.buffer(0)
        if water is not None and g.intersects(water):
            g = g.difference(water)
            if not g.is_valid:
                g = g.buffer(0)
        if g.is_empty:
            continue
        g = g.simplify(SIMPLIFY_DEG, preserve_topology=True)
        if g.is_empty:
            continue
        out["features"].append({
            "type": "Feature",
            "properties": {"name": name},
            "geometry": mapping(g),
        })
        seen.add(name)

    missing = kept - seen
    if missing:
        print(f"WARNING: {len(missing)} kept cities had no place polygon: "
              f"{sorted(missing)}", file=sys.stderr)

    dest = os.path.join(DATA, "places.geojson.json")
    with open(dest, "w") as f:
        json.dump(out, f)
    print(f"wrote {dest} — {len(out['features'])} places, "
          f"{os.path.getsize(dest)} bytes")


if __name__ == "__main__":
    main()
