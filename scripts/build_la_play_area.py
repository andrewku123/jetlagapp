#!/usr/bin/env python3
"""Build the LA play area: playable-city footprint + inland rivers, clipped to the shore.

Inputs (both committed, so this is reproducible without the raw TIGER dumps):
  scripts/la_play_area_cities.geojson.json   city footprint = union of the playable
                                             Census places' full legal polygons
  scripts/la_inland_water.geojson.json       TIGER AREAWATER rivers/canals/lakes
                                             (H3010/H3020/H2040/H2030) near the footprint
  scripts/measure_src/osm_coastline_la.geojson   OSM natural=coastline
Output (what the app ships): src/data/la.play-area.geojson.json

Two corrections are applied to the raw city footprint:

1. RIVERS. A city's legal line usually runs along the *bank* of the LA River /
   Rio Hondo / etc., so the concrete channel falls out of every city polygon and
   shows as an out-of-play gash cutting through the map. The user wants the water
   next to a playable city IN (up to ~mid-channel). We add
       river_fill = inland_water & footprint.buffer(RIVER_D)
   RIVER_D (~mid-channel) reaches from a playable bank to the middle; a channel
   with playable cities on both banks fills completely; a channel with no playable
   city within RIVER_D stays out. Intersecting with the water polygons means only
   water (never neighbouring land) is ever added.

2. SHORE. Coastal cities' legal boundaries don't track the beach — some run inland
   of the sand (beach greyed out) and some run into the water (open ocean shown in
   play). We clip to OSM `natural=coastline` (the shoreline the basemap draws):
       ocean = sea face west of the mainland coastline (harbours included)
       play  = (cities - ocean) | (land within FILL_D of BOTH cities and ocean)
   The beach fill is intersected with the land side, so play never extends seaward.

Run: python3 scripts/build_la_play_area.py
"""
import json
import os

from shapely.geometry import Point, box, mapping, shape
from shapely.ops import linemerge, polygonize, unary_union

HERE = os.path.dirname(os.path.abspath(__file__))
CITIES = os.path.join(HERE, "la_play_area_cities.geojson.json")
WATER = os.path.join(HERE, "la_inland_water.geojson.json")
COAST = os.path.join(HERE, "measure_src", "osm_coastline_la.geojson")
OUT = os.path.join(HERE, "..", "src", "data", "la.play-area.geojson.json")

# The OSM coastline dump reaches to lon -118.80; keep the frame just inside it so
# the mainland coast closes cleanly against the frame's west edge.
FRAME = box(-118.78, 33.60, -117.55, 34.40)
# A point in the open Pacific — selects the sea face after polygonizing.
SEA_SEED = (-118.60, 33.85)
RIVER_D = 0.0006  # ~65 m: reach from a playable riverbank to ~mid-channel
FILL_D = 0.008  # ~0.8 km: max beach width bridged from the footprint to the shore
SIMPLIFY_DEG = 0.00008  # ~9 m, keep the shore crisp
ROUND = 5


def build_ocean():
    fc = json.load(open(COAST))
    lines = [shape(f["geometry"]) for f in fc["features"]]
    merged = linemerge(unary_union(lines)).intersection(FRAME)
    faces = list(polygonize(unary_union([merged, FRAME.boundary])))
    seed = Point(*SEA_SEED)
    sea = [f for f in faces if f.contains(seed)]
    if not sea:
        raise SystemExit("no sea face found — check SEA_SEED / coastline data")
    return unary_union(sea).buffer(0)


def build_inland_water():
    fc = json.load(open(WATER))
    return unary_union([shape(f["geometry"]) for f in fc["features"]]).buffer(0)


def main():
    footprint = shape(json.load(open(CITIES))["features"][0]["geometry"]).buffer(0)
    water = build_inland_water()
    river_fill = water.intersection(footprint.buffer(RIVER_D))
    cities = unary_union([footprint, river_fill]).buffer(0)

    ocean = build_ocean()
    land = FRAME.difference(ocean)
    trimmed = cities.difference(ocean)
    beach = land.intersection(cities.buffer(FILL_D)).intersection(ocean.buffer(FILL_D))
    play = unary_union([trimmed, beach]).buffer(0)
    play = play.simplify(SIMPLIFY_DEG, preserve_topology=True)

    def rnd(c):
        return ([round(c[0], ROUND), round(c[1], ROUND)]
                if isinstance(c[0], (int, float)) else [rnd(x) for x in c])

    geom = mapping(play)
    geom["coordinates"] = rnd(geom["coordinates"])
    out = {"type": "FeatureCollection",
           "features": [{"type": "Feature",
                         "properties": {"name": "LA Metro"},
                         "geometry": geom}]}
    with open(OUT, "w") as f:
        json.dump(out, f)
    print(f"wrote {OUT}")
    print(f"  footprint {footprint.area:.4f} +river {river_fill.area:.5f} "
          f"-> play {play.area:.4f} (delta {play.area - footprint.area:+.4f})")
    print(f"  bytes {os.path.getsize(OUT)}")


if __name__ == "__main__":
    main()
