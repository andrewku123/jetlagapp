#!/usr/bin/env python3
"""Build the compact POI data file the app's POI tab loads.

Reads the curated dataset (scripts/poi_curated.json -- produced by
curate_places_poi.py) and writes src/data/poi.json keyed by category, each a
list of {n: name, lat, lon, t: primaryType, r: userRatingCount}. Coordinates are
rounded to 6 dp. Category labels/colors live in the app (src/lib/poi.ts).
"""
import os, json

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "poi_curated.json")
OUT = os.path.join(HERE, "..", "src", "data", "poi.json")

# allow an override input (e.g. an out-of-repo scratch curated file)
import sys
if len(sys.argv) > 1:
    SRC = sys.argv[1]

curated = json.load(open(SRC))
out = {}
for key, blk in curated.items():
    places = []
    for p in blk["places"]:
        places.append({
            "n": p["name"],
            "lat": round(p["lat"], 6),
            "lon": round(p["lon"], 6),
            "t": p.get("primaryType"),
            "r": p.get("userRatingCount") or 0,
        })
    places.sort(key=lambda x: x["n"].lower())
    out[key] = places

json.dump(out, open(OUT, "w"), separators=(",", ":"))
total = sum(len(v) for v in out.values())
print(f"wrote {OUT}: {total} POIs across {len(out)} categories")
for k, v in out.items():
    print(f"  {k:15s} {len(v)}")
