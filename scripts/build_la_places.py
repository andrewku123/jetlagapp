#!/usr/bin/env python3
"""LA per-city (Census "place") polygons for the Matching -> city question.

Output: src/data/la.places.geojson.json — a FeatureCollection of Polygon /
MultiPolygon features, one per in-play Census place, `properties.name` = Census
NAMELSAD (e.g. "Los Angeles city", "East Los Angeles CDP").

Same shape/logic as build_city_places.py (Bay Area): emit EVERY Census place
that lies inside the play area (city, town OR CDP), each clipped to the play-area
polygon. No SFO-style airport-ownership override (LA has no equivalent quirk).

Source: Census TIGER/Line 2023 CA places (shared _census_place cache).
"""
import io, json, os, sys, zipfile, urllib.request
from shapely.geometry import shape, mapping, Polygon, MultiPolygon, GeometryCollection
from shapely.ops import unary_union

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "src", "data")
CACHE = os.path.join(HERE, "..", "..", "app-mainpr", "scripts", "_census_place")
PLAY_AREA = os.path.join(DATA, "la.play-area.geojson.json")
PLACE_URL = "https://www2.census.gov/geo/tiger/TIGER2023/PLACE/tl_2023_06_place.zip"
PLACE_STEM = "tl_2023_06_place"
SIMPLIFY_DEG = 0.0002
MIN_AREA_DEG2 = 1e-7


def polygonal(g):
    if g.is_empty:
        return g
    if isinstance(g, (Polygon, MultiPolygon)):
        return g
    if isinstance(g, GeometryCollection):
        parts = [p for p in g.geoms if isinstance(p, (Polygon, MultiPolygon))]
        return unary_union(parts) if parts else Polygon()
    return Polygon()


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


def main():
    import shapefile
    play = load_play_area()
    r = shapefile.Reader(ensure_shapefile(PLACE_URL, PLACE_STEM))
    flds = [f[0] for f in r.fields[1:]]
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

    out = {"type": "FeatureCollection", "features": []}
    for name in sorted(clipped):
        g = polygonal(clipped[name].simplify(SIMPLIFY_DEG, preserve_topology=True))
        if g.is_empty or g.area < MIN_AREA_DEG2:
            continue
        out["features"].append({"type": "Feature", "properties": {"name": name},
                                "geometry": mapping(g)})
    dest = os.path.join(DATA, "la.places.geojson.json")
    with open(dest, "w") as f:
        json.dump(out, f)
    print(f"wrote {dest} — {len(out['features'])} places, {os.path.getsize(dest)} bytes")


if __name__ == "__main__":
    main()
