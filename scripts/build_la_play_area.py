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
import math
import os

from shapely.geometry import LineString, Point, Polygon, box, mapping, shape
from shapely.ops import linemerge, nearest_points, polygonize, unary_union

HERE = os.path.dirname(os.path.abspath(__file__))
CITIES = os.path.join(HERE, "la_play_area_cities.geojson.json")
WATER = os.path.join(HERE, "la_inland_water.geojson.json")
COAST = os.path.join(HERE, "measure_src", "osm_coastline_la.geojson")
DAMS_FILE = os.path.join(HERE, "la_coast_dams.json")
# Recreational ocean piers (Santa Monica, Venice, Manhattan Beach, Redondo,
# Belmont) whose decks jut past the drawn coastline into open water. Their OSM
# footprint polygons are added back as in-play land so the shore traces around
# each pier instead of chopping it off at the beach.
PIERS_FILE = os.path.join(HERE, "la_piers.geojson.json")
OUT = os.path.join(HERE, "..", "src", "data", "la.play-area.geojson.json")

# The OSM coastline dump reaches to lon -118.80; keep the frame just inside it so
# the mainland coast closes cleanly against the frame's west edge.
FRAME = box(-118.78, 33.60, -117.55, 34.40)
# A point in the open Pacific — selects the sea face after polygonizing.
SEA_SEED = (-118.60, 33.85)
RIVER_D = 0.0006  # ~65 m: reach from a playable riverbank to ~mid-channel
FILL_D = 0.008  # ~0.8 km: max beach width bridged from the footprint to the shore
SIMPLIFY_DEG = 0.00008  # ~9 m, keep the shore crisp
# Enclosed water holes (harbor/marina basins, lagoons, reservoirs) up to this
# area are filled back into play: a city's legal polygon carves out its harbor
# water, leaving an out-of-play hole surrounded by in-play land. Per "water
# inland of the coast is in play", fill it. Capped well below the smallest
# non-playable enclave city (~5 km^2 ~ 0.0005 deg^2) so land enclaves stay out,
# and above Marina del Rey (~1.3 km^2 ~ 0.00013 deg^2), the largest such basin.
# The big central San Pedro Bay basin is NOT a hole (it opens to the ocean, so
# it's a boundary bite) and is untouched — it stays out, as the user chose.
HOLE_FILL_MAX = 0.0003
ROUND = 5


def dam_walls(coast_all, dams):
    """Straight bank-to-bank walls across each user-supplied harbor/river mouth.
    Both bank points are snapped to the nearest spot on the real OSM coastline
    (skipped if >~660 m off — that mouth isn't traced there) and the wall is
    extended a hair past each bank so it fully separates the water behind it."""
    walls = []
    for seg in dams:
        p0, p1 = Point(seg[0]), Point(seg[1])
        q0 = nearest_points(coast_all, p0)[0]
        q1 = nearest_points(coast_all, p1)[0]
        if p0.distance(q0) > 0.006 or p1.distance(q1) > 0.006:
            continue
        dx, dy = q1.x - q0.x, q1.y - q0.y
        L = math.hypot(dx, dy) or 1e-9
        ux, uy = dx / L, dy / L
        ext = 0.0006
        walls.append(LineString([(q0.x - ux * ext, q0.y - uy * ext),
                                 (q1.x + ux * ext, q1.y + uy * ext)]))
    return walls


def build_ocean(dams):
    fc = json.load(open(COAST))
    lines = [shape(f["geometry"]) for f in fc["features"]]
    merged = linemerge(unary_union(lines)).intersection(FRAME)
    walls = dam_walls(unary_union(lines), dams) if dams else []
    faces = list(polygonize(unary_union([merged, *walls, FRAME.boundary])))
    seed = Point(*SEA_SEED)
    sea = [f for f in faces if f.contains(seed)]
    if not sea:
        raise SystemExit("no sea face found — check SEA_SEED / coastline data")
    return unary_union(sea).buffer(0)


def load_dams():
    if not os.path.exists(DAMS_FILE):
        return []
    return json.load(open(DAMS_FILE))["dams"]


def fill_small_holes(play):
    """Drop interior rings smaller than HOLE_FILL_MAX so enclosed harbor/marina
    basins and lagoons (water a city polygon carved out) render in-play."""
    polys = play.geoms if play.geom_type == "MultiPolygon" else [play]
    out = []
    for g in polys:
        keep = [r for r in g.interiors if Polygon(r).area >= HOLE_FILL_MAX]
        out.append(Polygon(g.exterior, keep))
    return unary_union(out).buffer(0)


def build_inland_water():
    fc = json.load(open(WATER))
    return unary_union([shape(f["geometry"]) for f in fc["features"]]).buffer(0)


def load_piers():
    if not os.path.exists(PIERS_FILE):
        return None
    fc = json.load(open(PIERS_FILE))
    return unary_union([shape(f["geometry"]) for f in fc["features"]]).buffer(0)


def main():
    footprint = shape(json.load(open(CITIES))["features"][0]["geometry"]).buffer(0)
    water = build_inland_water()
    river_fill = water.intersection(footprint.buffer(RIVER_D))

    dams = load_dams()
    ocean = build_ocean(dams)
    # Water sealed behind the dams (harbor basins/channels inland of the drawn
    # coastline) is what the raw open-ocean fill reached but the dammed one no
    # longer does. Per the rule "everything inland of the coastline is in play",
    # add it to the footprint so those basins render in-play instead of grey.
    harbor_fill = build_ocean([]).difference(ocean) if dams else None
    parts = [footprint, river_fill] + ([harbor_fill] if harbor_fill else [])
    cities = unary_union(parts).buffer(0)

    # Carve the pier decks out of the open ocean so the shore trims around them
    # (leaving the deck as land); harbor_fill above keeps the true dammed ocean.
    piers = load_piers()
    ocean_for_play = ocean.difference(piers).buffer(0) if piers is not None else ocean

    land = FRAME.difference(ocean_for_play)
    trimmed = cities.difference(ocean_for_play)
    beach = land.intersection(cities.buffer(FILL_D)).intersection(ocean.buffer(FILL_D))
    parts_play = [trimmed, beach]
    if piers is not None:
        parts_play.append(piers)
    play = unary_union(parts_play).buffer(0)
    play = fill_small_holes(play)
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
