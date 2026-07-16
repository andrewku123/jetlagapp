#!/usr/bin/env python3
"""Refine the LA play area's SEAWARD edge so it follows the real ocean shoreline.

The raw LA play area = the union of the playable Census places' full legal
polygons (rivers/lakes inside a city are already part of that city polygon, so
inland water stays in play). That footprint is committed, un-clipped, at
  scripts/la_play_area_cities.geojson.json           (input, city footprint)
and this script writes the coast-clipped result the app actually ships:
  src/data/la.play-area.geojson.json                 (output)

Coastal cities' legal boundaries do NOT track the beach: some run inland of the
sand (beach greyed out of play) and some run out into the water (open ocean shown
in play). Both are fixed here by clipping the footprint to OSM `natural=coastline`
(the same shoreline the basemap/satellite imagery draws):

  ocean = the sea face west of the OSM mainland coastline (Santa Monica + San
          Pedro bays, harbours included via the harbour mouths).
  play  = (footprint - ocean)                      # trim any ocean overreach
          | (land within FILL_D of BOTH the footprint and the ocean)
                                                    # fill beach gaps up to shore

The fill is intersected with the land side of the coastline, so the play area can
never extend seaward of the shore; inland water is untouched (lakes/river channels
are not `natural=coastline`, so they are never subtracted).

Run: python3 scripts/build_la_play_area.py
"""
import json
import os

from shapely.geometry import box, mapping, shape
from shapely.ops import linemerge, polygonize, unary_union

HERE = os.path.dirname(os.path.abspath(__file__))
CITIES = os.path.join(HERE, "la_play_area_cities.geojson.json")
COAST = os.path.join(HERE, "measure_src", "osm_coastline_la.geojson")
OUT = os.path.join(HERE, "..", "src", "data", "la.play-area.geojson.json")

# The OSM coastline dump reaches to lon -118.80; keep the frame just inside it so
# the mainland coast closes cleanly against the frame's west edge.
FRAME = box(-118.78, 33.60, -117.55, 34.40)
# A point in the open Pacific — selects the sea face after polygonizing.
SEA_SEED = (-118.60, 33.85)
FILL_D = 0.008  # ~0.8 km: max beach width bridged from the footprint to the shore
SIMPLIFY_DEG = 0.00008  # ~9 m, keep the shore crisp
ROUND = 5


def build_ocean():
    fc = json.load(open(COAST))
    lines = [shape(f["geometry"]) for f in fc["features"]]
    merged = linemerge(unary_union(lines)).intersection(FRAME)
    faces = list(polygonize(unary_union([merged, FRAME.boundary])))
    from shapely.geometry import Point
    seed = Point(*SEA_SEED)
    sea = [f for f in faces if f.contains(seed)]
    if not sea:
        raise SystemExit("no sea face found — check SEA_SEED / coastline data")
    return unary_union(sea).buffer(0)


def main():
    cities = shape(json.load(open(CITIES))["features"][0]["geometry"]).buffer(0)
    ocean = build_ocean()
    land = FRAME.difference(ocean)

    trimmed = cities.difference(ocean)
    fill = land.intersection(cities.buffer(FILL_D)).intersection(ocean.buffer(FILL_D))
    play = unary_union([trimmed, fill]).buffer(0)
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
    print(f"  cities area {cities.area:.4f} -> play area {play.area:.4f} "
          f"(delta {play.area - cities.area:+.4f})")
    print(f"  bytes {os.path.getsize(OUT)}")


if __name__ == "__main__":
    main()
