#!/usr/bin/env python3
"""Build the per-ZIP (ZCTA) polygons used by the Measuring -> ZIP code question:
the seeker's ZIP is looked up from their coordinate (point-in-polygon) and the
eliminated-area shading is the union of every ZCTA whose ZIP is <= the seeker's
(for a "smaller" answer). Same per-feature shape as build_city_places.py.

Output: src/data/zctas.geojson.json — a FeatureCollection of Polygon /
MultiPolygon features, one per in-play ZCTA, `properties.name` set to the 5-digit
ZIP (ZCTA5CE20, e.g. "94103"), each clipped to the play-area polygon.

ZIP codes are only meaningfully ordinal in the US (numeric postal codes), so this
question is US-only; a non-US map simply omits this dataset and the question.

REPLICABILITY: a new US metro supplies its own play area; the question code
(src/lib/zip.ts, elimination + shading) is ZIP-agnostic — it reads whatever ZCTAs
this script clips to that play area.

Source: Census TIGER/Line 2023 national ZCTA5 (tl_2023_us_zcta520).
"""
import io
import json
import os
import sys
import zipfile
import urllib.request

from shapely.geometry import shape, mapping, Polygon, MultiPolygon, GeometryCollection
from shapely.ops import unary_union


def polygonal(g):
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
CACHE = os.path.join(HERE, "_census_zcta")
PLAY_AREA = os.path.join(DATA, "play-area.geojson.json")

ZCTA_URL = "https://www2.census.gov/geo/tiger/TIGER2023/ZCTA520/tl_2023_us_zcta520.zip"
ZCTA_STEM = "tl_2023_us_zcta520"
SIMPLIFY_DEG = 0.0002  # ~22 m; plenty for point-in-polygon + shading, keeps file small
MIN_AREA_DEG2 = 1e-7   # drop sliver clip artifacts (~1000 m^2)


def ensure_shapefile(url, stem):
    shp = os.path.join(CACHE, stem + ".shp")
    if os.path.exists(shp):
        return shp
    os.makedirs(CACHE, exist_ok=True)
    print(f"downloading {url} (~530 MB) ...", file=sys.stderr)
    data = urllib.request.urlopen(url, timeout=600).read()
    zipfile.ZipFile(io.BytesIO(data)).extractall(CACHE)
    return shp


def load_play_area():
    fc = json.load(open(PLAY_AREA))
    g = shape(fc["features"][0]["geometry"])
    return g.buffer(0) if not g.is_valid else g


def main():
    import shapefile

    play = load_play_area()
    minx, miny, maxx, maxy = play.bounds
    r = shapefile.Reader(ensure_shapefile(ZCTA_URL, ZCTA_STEM))
    flds = [f[0] for f in r.fields[1:]]
    zip_field = "ZCTA5CE20" if "ZCTA5CE20" in flds else "ZCTA5CE10"

    clipped = {}
    for sh, rec in zip(r.iterShapes(), r.iterRecords()):
        # cheap bbox reject before building shapely geometry (national file)
        bx0, by0, bx1, by1 = sh.bbox
        if bx1 < minx or bx0 > maxx or by1 < miny or by0 > maxy:
            continue
        d = dict(zip(flds, rec))
        zc = str(d[zip_field])
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
        clipped[zc] = g

    out = {"type": "FeatureCollection", "features": []}
    for zc in sorted(clipped):
        g = polygonal(clipped[zc].simplify(SIMPLIFY_DEG, preserve_topology=True))
        if g.is_empty or g.area < MIN_AREA_DEG2:
            continue
        out["features"].append({
            "type": "Feature",
            "properties": {"name": zc},
            "geometry": mapping(g),
        })

    dest = os.path.join(DATA, "zctas.geojson.json")
    with open(dest, "w") as f:
        json.dump(out, f)
    print(f"wrote {dest} — {len(out['features'])} ZCTAs, {os.path.getsize(dest)} bytes")


if __name__ == "__main__":
    main()
