#!/usr/bin/env python3
"""Every map's committed play area holds each station's two-Prosperous endgame disk.

Plain `python3 test_endgame_zones.py` (no pytest, no network). See endgame_zones.py
for the rule: decided map + every station's zone radius x 1.5^2 disk, minus water.
"""
import json
import os
import sys

from shapely.geometry import shape
from shapely.ops import unary_union

import endgame_zones as Z

ROOT = Z.ROOT
# app region id -> (stations, play area, open water the disks are clipped to)
MAPS = {
    "bayarea": ("stations.json", "play-area.geojson.json",
                ["scripts/bay_water_mask.geojson", "scripts/pacific_ocean.geojson.json"]),
    "sfmuni": ("sfmuni.stations.json", "sfmuni.play-area.geojson.json",
               ["scripts/bay_water_mask.geojson", "scripts/pacific_ocean.geojson.json"]),
    "la": ("la.stations.json", "la.play-area.geojson.json", ["scripts/la_ocean.geojson.json"]),
    "dc": ("dc.stations.json", "dc.play-area.geojson.json", []),
}
FAILED = []


def check(name, cond, detail=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  ({detail})" if detail and not cond else ""))
    if not cond:
        FAILED.append(name)


def data(name):
    return json.load(open(os.path.join(ROOT, "src", "data", name)))


sizes = json.load(open(Z.REGION_SIZES))
for rid, size in sizes.items():
    want = Z.BASE_RADIUS_MI[size] * 1.5 ** 2
    check(f"{rid}: endgame disk = {size} zone x 1.5^2", abs(Z.max_hiding_radius_mi(rid) - want) < 1e-12)
check("medium endgame disk is 0.5625 mi", Z.BASE_RADIUS_MI["medium"] * 1.5 ** 2 == 0.5625)
check("every map is covered by this test", set(MAPS) == set(sizes), sorted(set(sizes) ^ set(MAPS)))

for rid, (st, pa, water) in MAPS.items():
    stations = data(st)
    play = unary_union([shape(f["geometry"]).buffer(0) for f in data(pa)["features"]])
    ext = Z.new_land(play, stations, Z.max_hiding_radius_mi(rid), Z.load_water(water))
    check(f"{rid}: play area holds every station's endgame disk", ext.is_empty,
          f"{ext.area * 111.32 ** 2:.4f} km^2 missing")
    check(f"{rid}: with_endgame_zones is idempotent",
          Z.with_endgame_zones(play, stations, Z.max_hiding_radius_mi(rid), Z.load_water(water)) is play)

# The app's city/county/ZIP lookups read only Polygon/MultiPolygon features.
for fn in sorted(os.listdir(os.path.join(ROOT, "src", "data"))):
    if any(fn.endswith(k + ".geojson.json") for k in ("places", "counties", "zctas", "play-area")):
        bad = [f["properties"].get("name", "?") for f in data(fn)["features"]
               if f["geometry"]["type"] not in ("Polygon", "MultiPolygon")]
        check(f"{fn}: polygon-only geometry", not bad, bad)

if FAILED:
    print(f"\n{len(FAILED)} failed")
    sys.exit(1)
print("\nall passed")
