#!/usr/bin/env python3
"""Build src/data/la.water.geojson.json from the OSM dump (_la_water_raw.json).

Output features (all clipped to a render frame around the play area):
  - kind="ocean" : the Pacific, derived from natural=coastline using OSM's
                   land-left / water-right way orientation (sample points offset
                   to the right of each coastline segment must fall in the sea).
  - kind="water" : lakes, reservoirs, riverbank/channel polygons (natural=water,
                   waterway=riverbank), the LA River channel included.
  - kind="river" : river/canal centrelines (waterway=river|canal) as lines, for
                   channels too thin to read as a polygon.
This is a cosmetic overlay; it feeds no elimination logic.
"""
import json
import math

from shapely.geometry import (
    LineString, MultiLineString, MultiPolygon, Polygon, box, mapping, shape,
)
from shapely.ops import linemerge, polygonize, unary_union

RAW = "/home/ubuntu/_la_water_raw.json"
OUT = "src/data/la.water.geojson.json"
# render frame: play-area bbox + a little slack for the coast/rivers
FRAME = box(-118.72, 33.68, -117.68, 34.36)
MIN_WATER_M2 = 8000.0  # drop tiny ponds that just add clutter
LAT0 = 34.05
M_LAT = 111320.0
M_LON = 111320.0 * math.cos(math.radians(LAT0))


def area_m2(g):
    return abs(g.area) * M_LAT * M_LON


def coords_of(el):
    return [(p["lon"], p["lat"]) for p in el.get("geometry", [])]


def main():
    data = json.load(open(RAW))
    els = data["elements"]

    water_polys = []   # lakes / reservoirs / riverbanks
    river_lines = []   # river / canal centrelines
    coast_lines = []   # natural=coastline (directed: land left, water right)

    # relations first: assemble multipolygon members
    for e in els:
        if e["type"] != "relation":
            continue
        if e.get("tags", {}).get("natural") != "water":
            continue
        outers, inners = [], []
        for m in e.get("members", []):
            g = m.get("geometry")
            if not g or len(g) < 2:
                continue
            ring = [(p["lon"], p["lat"]) for p in g]
            (outers if m.get("role") != "inner" else inners).append(LineString(ring))
        for poly in polygonize(unary_union(outers)) if outers else []:
            water_polys.append(poly)

    for e in els:
        if e["type"] != "way":
            continue
        t = e.get("tags", {})
        c = coords_of(e)
        if len(c) < 2:
            continue
        if t.get("natural") == "coastline":
            coast_lines.append(LineString(c))
        elif t.get("natural") == "water" or t.get("waterway") == "riverbank":
            if len(c) >= 4 and c[0] == c[-1]:
                p = Polygon(c)
                if not p.is_valid:
                    p = p.buffer(0)
                if not p.is_empty:
                    water_polys.append(p)
        elif t.get("waterway") in ("river", "canal"):
            river_lines.append(LineString(c))

    # No ocean polygon: the CARTO basemap already draws the Pacific, and a custom
    # ocean fill introduced a second coastline that didn't line up with the
    # basemap's (and dragged in tiny offshore islands). We let the basemap water
    # show through and only overlay inland water (lakes/reservoirs/channels/rivers).

    # simplify: this is a cosmetic overlay, full OSM detail is overkill
    SIMP = 0.00025  # ~25 m
    feats = []

    if water_polys:
        merged = unary_union([p for p in water_polys if p.is_valid and not p.is_empty])
        merged = merged.intersection(FRAME)
        parts = merged.geoms if merged.geom_type == "MultiPolygon" else [merged]
        keep = [p for p in parts if not p.is_empty and area_m2(p) >= MIN_WATER_M2]
        keep = [p.simplify(SIMP, preserve_topology=True) for p in keep]
        keep = [p for p in keep if not p.is_empty]
        if keep:
            geom = keep[0] if len(keep) == 1 else MultiPolygon(keep)
            feats.append({"type": "Feature", "properties": {"kind": "water"}, "geometry": mapping(geom)})

    if river_lines:
        merged = unary_union(river_lines).intersection(FRAME)
        merged = linemerge(merged) if merged.geom_type == "MultiLineString" else merged
        merged = merged.simplify(SIMP, preserve_topology=True)
        feats.append({"type": "Feature", "properties": {"kind": "river"}, "geometry": mapping(merged)})

    fc = {"type": "FeatureCollection", "features": feats}
    json.dump(fc, open(OUT, "w"))
    for f in feats:
        g = shape(f["geometry"])
        print(f["properties"]["kind"], g.geom_type,
              round(area_m2(g) / 1e6, 1), "km2" if "Polygon" in g.geom_type else "")


if __name__ == "__main__":
    main()
