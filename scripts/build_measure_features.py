#!/usr/bin/env python3
"""Build the linear-feature geometries used by the Measuring questions
(coastline, county border, state border, international border).

Output: src/data/measure-features.geojson.json — a FeatureCollection of
MultiLineString features, one per key, each simplified for runtime use in the
app (seeker/station distance-to-nearest + eliminated-area shading).

REPLICABILITY (new cities): nothing in the geometry logic below is Bay-Area
specific — it all reads from the CITY config dict. To port to NY / LA / etc.,
add a new entry to CITIES (bbox, source files, the state the metro is in + its
neighbouring states, the country + its neighbour) and run with CITY=<slug>. The
question code in the app is already city-agnostic; only this data step changes.

Sources (all local unless noted):
  - scripts/bay_land.geojson            land polygons (Census)
  - scripts/bay_water_mask.geojson      Census AREAWATER (SF Bay + big water)
  - scripts/pacific_ocean.geojson.json  Census Pacific Ocean polygons
  - src/data/counties.geojson.json      county polygons (metro + neighbors)
  - scripts/measure_src/us-states.geojson    US states (PublicaMundi)
  - scripts/measure_src/countries.geojson    Natural Earth 50m admin-0
"""
import json
import math
import os

from shapely.geometry import shape, mapping, MultiLineString, box
from shapely.ops import unary_union, linemerge, transform

HERE = os.path.dirname(__file__)
DATA = os.path.join(HERE, "..", "src", "data")

# Local equirectangular projection (metres) used only for the coastline's
# morphological opening, where an isotropic buffer in metres is required.
_REF_LAT = 37.8
_M_PER_LAT = 111320.0
_M_PER_LON = _M_PER_LAT * math.cos(math.radians(_REF_LAT))
_MILE_M = 1609.34


def _to_m(geom):
    return transform(lambda x, y, z=None: (x * _M_PER_LON, y * _M_PER_LAT), geom)


def _to_deg(geom):
    return transform(lambda x, y, z=None: (x / _M_PER_LON, y / _M_PER_LAT), geom)


# --- Per-city configuration --------------------------------------------------
# Every field a new city needs. Paths are relative to `scripts/` unless they
# start with "data:" (then relative to src/data/). `state`/`state_neighbors`
# name the 1st-admin division the metro sits in and the adjacent ones whose
# shared border is the "state border"; `country`/`country_neighbor` the same for
# the international border. Any feature whose sources are missing is skipped.
CITIES = {
    "bayarea": {
        "play_bbox": (-122.7, 37.0, -121.4, 38.2),  # lon/lat, generous
        "land": "bay_land.geojson",
        "saltwater": ["bay_water_mask.geojson", "pacific_ocean.geojson.json"],
        # the game play-area polygon (used to extend in-play land past the
        # OSM bay-shore mask into the East/South Bay) and the enclosed-bay water
        # mask (subtracted from the play area to recover that land).
        "play": "data:play-area.geojson.json",
        "bay": "bay_water_mask.geojson",
        "counties": "data:counties.geojson.json",
        "states": "measure_src/us-states.geojson",
        "countries": "measure_src/countries.geojson",
        "state": "California",
        # the metro's nearest state line — for the Bay Area every station's
        # nearest CA land border is the Nevada segment, so Nevada alone suffices;
        # OR/AZ are kept as a harmless superset (the nearest-point math ignores
        # the farther ones). A new city lists whatever states it borders.
        "state_neighbors": ["Nevada", "Oregon", "Arizona"],
        "country": "United States of America",
        "country_neighbor": "Mexico",
    },
}


def src(cfg_path):
    """Resolve a config path (supports the 'data:' prefix)."""
    if cfg_path.startswith("data:"):
        return os.path.join(DATA, cfg_path[len("data:"):])
    return os.path.join(HERE, cfg_path)


def load(path):
    with open(path) as f:
        return json.load(f)


def feats(fc):
    if fc.get("type") == "FeatureCollection":
        return [shape(f["geometry"]) for f in fc["features"]]
    if fc.get("type") == "Feature":
        return [shape(fc["geometry"])]
    return [shape(fc)]


def state_by_name(states):
    return {f["properties"].get("name", f["properties"].get("NAME", "")): shape(f["geometry"])
            for f in states["features"]}


def country_by_name(countries):
    by = {}
    for f in countries["features"]:
        p = f["properties"]
        name = p.get("ADMIN") or p.get("NAME") or p.get("name")
        by[name] = shape(f["geometry"])
    return by


def build_coastline(land, saltwater, play, bay, clip):
    # Fallback for cities without a play-area/bay mask: the plain shore of the
    # land mask adjacent to saltwater (no channel removal).
    if play is None or bay is None:
        return land.boundary.intersection(saltwater.buffer(0.0008)).intersection(clip)

    # Coastline = the shore of in-play LAND that borders qualifying saltwater
    # (ocean + enclosed bay), with sub-1-mile channels/straits removed.
    #
    # 1. in-play land: the OSM bay-shore mask (good Pacific/peninsula detail)
    #    unioned with (play area − bay). The play-area term fills the East Bay /
    #    South Bay land that the peninsula-only mask misses.
    all_land = unary_union([play.difference(bay).buffer(0), land]).buffer(0)
    water = saltwater.buffer(0)

    # 2. morphological opening on the water (erode by r then dilate by r) drops
    #    every channel/strait narrower than 2r (~1 mi) and any sub-2r protrusion,
    #    so the opened water never reaches into narrow straits (Oakland-Alameda
    #    estuary, Carquinez strait). Along a wide shore the dilate returns the
    #    edge to the shore, so wide bays stay captured.
    r = 0.5 * _MILE_M
    opened = _to_deg(_to_m(water).buffer(-r).buffer(r)).buffer(0)

    # 3. shore = land boundary adjacent to the opened (>=1 mi wide) water. Where
    #    the opening deleted a narrow channel the shore runs straight across its
    #    mouth instead of tracing both banks. Small pad (~275 m) closes gaps so
    #    the shore stays visually continuous.
    shore = all_land.boundary.intersection(opened.buffer(0.0025))

    # 4. keep only shore on big landmasses — drops marsh islets / small islands.
    polys = list(all_land.geoms) if all_land.geom_type == "MultiPolygon" else [all_land]
    big = unary_union([p for p in polys if p.area > 0.0008])
    shore = shore.intersection(big.boundary.buffer(0.0015))
    return shore.intersection(clip)


def build_county_border(counties, clip):
    # internal shared boundaries between adjacent county polygons (no coast:
    # coast edges belong to only one county so never appear in a pairwise
    # intersection)
    lines = []
    n = len(counties)
    for i in range(n):
        bi = counties[i].boundary
        for j in range(i + 1, n):
            inter = bi.intersection(counties[j].boundary)
            if not inter.is_empty and inter.length > 0:
                lines.append(inter)
    return unary_union(lines).intersection(clip)


def build_state_border(states, cfg, clip):
    by = state_by_name(states)
    home = by[cfg["state"]]
    neighbors = unary_union([g for name, g in by.items()
                             if name in cfg["state_neighbors"]])
    # home-state land border = the part of its boundary shared with adjacent
    # states (excludes any coast, which no neighbor touches). Clipped to the
    # play area: a border outside the map doesn't exist for the game, so if the
    # metro is nowhere near a state line this comes back empty and the question
    # is dropped (see main()).
    return home.boundary.intersection(neighbors.buffer(0.02)).intersection(clip)


def build_intl_border(countries, cfg, clip):
    by = country_by_name(countries)
    home = by.get(cfg["country"]) or by.get("United States")
    neighbor = by.get(cfg["country_neighbor"])
    if home is None or neighbor is None:
        return None
    # Clipped to the play area — an international border outside the map doesn't
    # exist for the game (empty here → question dropped in main()).
    return home.boundary.intersection(neighbor.buffer(0.03)).intersection(clip)


def to_multiline(geom, simplify_deg):
    if geom is None or geom.is_empty:
        return None
    g = geom.simplify(simplify_deg, preserve_topology=False) if simplify_deg else geom
    parts = []

    def collect(gg):
        t = gg.geom_type
        if t == "LineString":
            if len(gg.coords) >= 2:
                parts.append(list(gg.coords))
        elif t in ("MultiLineString", "GeometryCollection"):
            for sub in gg.geoms:
                collect(sub)

    try:
        m = linemerge(g)
    except Exception:
        m = g
    collect(m)
    if not parts:
        collect(g)
    return MultiLineString(parts) if parts else None


def stats(name, ml):
    if ml is None:
        print(f"  {name}: EMPTY")
        return 0
    nverts = sum(len(p.coords) for p in ml.geoms)
    print(f"  {name}: parts={len(ml.geoms)} verts={nverts} length_deg={ml.length:.3f}")
    return nverts


def main():
    slug = os.environ.get("CITY", "bayarea")
    if slug not in CITIES:
        raise SystemExit(f"unknown CITY={slug!r}; known: {', '.join(CITIES)}")
    cfg = CITIES[slug]
    lon0, lat0, lon1, lat1 = cfg["play_bbox"]
    clip = box(lon0, lat0, lon1, lat1)

    land = unary_union(feats(load(src(cfg["land"]))))
    saltwater = unary_union([g for p in cfg["saltwater"]
                             for g in feats(load(src(p)))])
    play = unary_union(feats(load(src(cfg["play"])))) if cfg.get("play") else None
    bay = unary_union(feats(load(src(cfg["bay"])))) if cfg.get("bay") else None
    counties = feats(load(src(cfg["counties"])))
    states = load(src(cfg["states"]))
    countries = load(src(cfg["countries"]))

    print(f"building features for {slug}…")
    features = (
        ("coastline", to_multiline(build_coastline(land, saltwater, play, bay, clip), 0.0007)),
        ("county-border", to_multiline(build_county_border(counties, clip), 0.0007)),
        ("state-border", to_multiline(build_state_border(states, cfg, clip), 0.003)),
        ("intl-border", to_multiline(build_intl_border(countries, cfg, clip), 0.003)),
    )

    out = {"type": "FeatureCollection", "features": []}
    for key, ml in features:
        stats(key, ml)
        if ml is None:
            continue
        out["features"].append({
            "type": "Feature",
            "properties": {"key": key},
            "geometry": mapping(ml),
        })

    dest = os.path.join(DATA, "measure-features.geojson.json")
    with open(dest, "w") as f:
        json.dump(out, f)
    print("wrote", dest, os.path.getsize(dest), "bytes")


if __name__ == "__main__":
    main()
