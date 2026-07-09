#!/usr/bin/env python3
"""LA county polygons for the Matching -> county question, the countyAt() in-play
fallback, and the county-border Measuring feature.

Output: src/data/la.counties.geojson.json — a FeatureCollection with LA county
(clipped to its shoreline via the LA water mask, like the Bay Area SF land clip)
plus the neighbouring counties (Ventura, Kern, San Bernardino, Orange,
Riverside) as full polygons so a border sliver / the border measure feature
resolve correctly. `properties.name` = county name.

Sources: Census cb_2023_us_county_500k (cartographic) + la_water_mask.geojson.
"""
import json, os, sys
from shapely.geometry import shape, mapping, Polygon, MultiPolygon, GeometryCollection
from shapely.ops import unary_union

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "src", "data")
SCR = os.path.join(HERE, "..", "..", "app-mainpr", "scripts")
COUNTY_SHP = os.path.join(SCR, "_census_place", "cb_2023_us_county_500k.shp")
WATER = os.path.join(HERE, "..", "..", "la_build", "la_water_mask.geojson")

IN_PLAY = "Los Angeles"
NEIGHBORS = ["Ventura", "Kern", "San Bernardino", "Orange", "Riverside"]
SIMPLIFY_DEG = 0.0003
MIN_AREA_DEG2 = 1e-6


def polygonal(g):
    if g.is_empty:
        return g
    if isinstance(g, (Polygon, MultiPolygon)):
        return g
    if isinstance(g, GeometryCollection):
        parts = [p for p in g.geoms if isinstance(p, (Polygon, MultiPolygon))]
        return unary_union(parts) if parts else Polygon()
    return Polygon()


def load_water():
    pj = json.load(open(WATER))
    if pj.get("type") == "FeatureCollection":
        g = unary_union([shape(f["geometry"]) for f in pj["features"]])
    elif pj.get("type") == "Feature":
        g = shape(pj["geometry"])
    else:
        g = shape(pj)
    return g.buffer(0) if not g.is_valid else g


def main():
    import shapefile
    water = load_water()
    r = shapefile.Reader(COUNTY_SHP)
    flds = [f[0] for f in r.fields[1:]]
    want = {IN_PLAY, *NEIGHBORS}
    out = {"type": "FeatureCollection", "features": []}
    for sh, rec in zip(r.shapes(), r.records()):
        d = dict(zip(flds, rec))
        if d.get("STATE_NAME") != "California" or d["NAME"] not in want:
            continue
        g = shape(sh.__geo_interface__)
        if not g.is_valid:
            g = g.buffer(0)
        # Clip the in-play county's ocean fringe back to the real shore; leave
        # neighbours whole (they're only used as reference geometry).
        if d["NAME"] == IN_PLAY:
            g = polygonal(g.difference(water))
        g = polygonal(g.simplify(SIMPLIFY_DEG, preserve_topology=True))
        if g.is_empty or g.area < MIN_AREA_DEG2:
            continue
        out["features"].append({"type": "Feature", "properties": {"name": d["NAME"]},
                                "geometry": mapping(g)})
    order = {n: i for i, n in enumerate([IN_PLAY, *NEIGHBORS])}
    out["features"].sort(key=lambda f: order.get(f["properties"]["name"], 99))
    dest = os.path.join(DATA, "la.counties.geojson.json")
    with open(dest, "w") as f:
        json.dump(out, f)
    print(f"wrote {dest} — {[x['properties']['name'] for x in out['features']]}, "
          f"{os.path.getsize(dest)} bytes")


if __name__ == "__main__":
    main()
