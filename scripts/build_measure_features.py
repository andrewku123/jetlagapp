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
import os

from shapely.geometry import shape, mapping, MultiLineString, box
from shapely.ops import unary_union, linemerge

HERE = os.path.dirname(__file__)
DATA = os.path.join(HERE, "..", "src", "data")


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


def build_coastline(land, saltwater, clip):
    # shoreline = land boundary adjacent to saltwater, within the play area
    shore = land.boundary.intersection(saltwater.buffer(0.0008))  # ~90 m
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


def build_state_border(states, cfg):
    by = state_by_name(states)
    home = by[cfg["state"]]
    neighbors = unary_union([g for name, g in by.items()
                             if name in cfg["state_neighbors"]])
    # home-state land border = the part of its boundary shared with adjacent
    # states (excludes any coast, which no neighbor touches).
    return home.boundary.intersection(neighbors.buffer(0.02))


def build_intl_border(countries, cfg):
    by = country_by_name(countries)
    home = by.get(cfg["country"]) or by.get("United States")
    neighbor = by.get(cfg["country_neighbor"])
    if home is None or neighbor is None:
        return None
    return home.boundary.intersection(neighbor.buffer(0.03))


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
    counties = feats(load(src(cfg["counties"])))
    states = load(src(cfg["states"]))
    countries = load(src(cfg["countries"]))

    print(f"building features for {slug}…")
    features = (
        ("coastline", to_multiline(build_coastline(land, saltwater, clip), 0.0007)),
        ("county-border", to_multiline(build_county_border(counties, clip), 0.0007)),
        ("state-border", to_multiline(build_state_border(states, cfg), 0.003)),
        ("intl-border", to_multiline(build_intl_border(countries, cfg), 0.003)),
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
