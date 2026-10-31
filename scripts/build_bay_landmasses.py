#!/usr/bin/env python3
"""Bay Area landmasses for the Matching -> landmass question.

The play area is one polygon, but it holds islands: every closed ring of the
OSM coastline (measure_src/osm_coastline_bayarea.geojson) is land that bridges,
causeways and tubes don't join to anything else. Alameda, Treasure Island and
Coast Guard Island are the ones people know. Each island larger than MIN_KM2
inside the play area is its own landmass; the rest of the play area is the
mainland. No station stands on an island (Fruitvale, the nearest to Alameda,
is ~0.5 mi away), so the question stays log-only here, but the seeker can now be
told truthfully which landmass they are on.

    python3 scripts/build_bay_landmasses.py
"""
import json
import os

from shapely.geometry import Polygon, mapping, shape
from shapely.ops import linemerge, unary_union

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
COAST = os.path.join(HERE, "measure_src", "osm_coastline_bayarea.geojson")
PLAY = os.path.join(ROOT, "src", "data", "play-area.geojson.json")
OUT = os.path.join(ROOT, "src", "data", "landmasses.geojson.json")
MIN_KM2 = 0.25
KM2_PER_DEG2 = 111.32 * 111.32 * 0.79  # cos(37.8)
SIMPLIFY_DEG = 0.0001
# Names for the islands people know; the rest are named by where they are.
NAMES = [("Alameda", 37.7652, -122.2416), ("Treasure Island", 37.8236, -122.3706),
         ("Coast Guard Island", 37.7822, -122.2495), ("Angel Island", 37.8608, -122.4326),
         ("Brooks Island", 37.8978, -122.3559)]


def main():
    lines = [shape(f["geometry"]) for f in json.load(open(COAST))["features"]]
    merged = linemerge(unary_union(lines))
    rings = [g for g in getattr(merged, "geoms", [merged]) if g.is_ring]
    play = unary_union([shape(f["geometry"]) for f in json.load(open(PLAY))["features"]])
    islands = []
    for r in rings:
        p = Polygon(r).buffer(0).intersection(play)
        if p.area * KM2_PER_DEG2 >= MIN_KM2:
            islands.append(p)
    islands.sort(key=lambda p: -p.area)
    feats = []
    for p in islands:
        name = next((n for n, la, lo in NAMES if p.buffer(0.002).contains(shape(
            {"type": "Point", "coordinates": [lo, la]}))), None)
        if name is None:
            c = p.representative_point()
            name = f"Island at {c.y:.3f}, {c.x:.3f}"
        feats.append((name, p))
    mainland = play.difference(unary_union(islands))
    out = [("Mainland", mainland)] + feats
    fc = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"name": n},
         "geometry": json.loads(json.dumps(mapping(g.simplify(SIMPLIFY_DEG)),
                                           ), parse_float=lambda v: round(float(v), 6))}
        for n, g in out]}
    json.dump(fc, open(OUT, "w"), separators=(",", ":"))
    for n, g in out:
        print(f"  {n}: {g.area * KM2_PER_DEG2:.1f} km2")
    print(f"wrote {OUT} ({os.path.getsize(OUT) // 1024} KB)")


if __name__ == "__main__":
    main()
