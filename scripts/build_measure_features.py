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
        # High-detail real shoreline: OSM `natural=coastline` ways for the whole
        # play bbox (the exact data the CARTO basemap draws). The coarse Census
        # water mask above is only used to decide TOPOLOGY (which water is the
        # main bay vs. an upstream creek cut off by a dam); the drawn shore is
        # then snapped onto these OSM lines so it lands on the real coast.
        # Refresh with (Overpass):
        #   [out:json][timeout:170];
        #   way["natural"="coastline"](37.0,-122.7,38.2,-121.4);out geom;
        # then convert each way's geometry to a LineString Feature.
        "coastline_detail": "measure_src/osm_coastline_bayarea.geojson",
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
        # River-mouth / narrow-channel "dams": each is a straight segment
        # [[lon,lat],[lon,lat]] placed bank-to-bank across a waterway that flows
        # into the bay/ocean but is never a full mile across (so, per the game
        # rule, it is NOT coastline). The build cuts the saltwater at each dam,
        # keeps only the main (largest) water body, fills the cut-off upstream
        # water in as land, and traces the shore straight across the mouth.
        # Endpoints sit slightly inland on each bank so the cut fully separates.
        # Ordered roughly N→S down the peninsula, then up the East Bay.
        # User-supplied bank-to-bank endpoint pairs (lon,lat). Each draws a
        # straight line across a river mouth; everything cut off from the main
        # bay (the upstream river/slough) is removed. Added one at a time as the
        # user sends precise coords.
        # Regions clipped OUT of the coastline entirely (not "not coast"): the
        # water there is <1 mi across upstream so it isn't coast, but we don't
        # want a straight bridge line drawn either — the shore just ends at the
        # neck. Each entry is a lon/lat bounding box [w, s, e, n].
        "coast_exclude": [
            [-122.205, 37.87, -121.40, 38.35],  # Suisun Bay + Delta, east of Carquinez Strait neck
        ],
        "dams": [
            [[-122.394497, 37.960102], [-122.395999, 37.958749]],  # Castro Creek (Richmond)
            [[-122.364306, 37.909364], [-122.360530, 37.909635]],  # Albany/Golden Gate Fields
            [[-122.329888, 37.800120], [-122.330704, 37.796797]],  # Oakland Inner Harbor / Alameda W
            [[-122.236118, 37.750460], [-122.236161, 37.747372]],  # San Leandro Bay
            [[-122.203567, 37.712794], [-122.202140, 37.711919]],  # San Leandro shore
            [[-122.191615, 37.704467], [-122.190778, 37.704713]],  # San Leandro Marina / Oyster Bay
        ],
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


def _dam_polys(dams, width_deg=0.0004):
    """Thin polygons (square-capped, ~90 m wide, endpoints extended ~44 m) for a
    list of [[lon,lat],[lon,lat]] dam segments. Subtracting these from the water
    cuts each narrow channel bank-to-bank."""
    from shapely.geometry import LineString
    return unary_union([LineString(seg).buffer(width_deg, cap_style=2) for seg in dams])


def build_coastline(land, saltwater, play, bay, clip, dams=None, exclude=None, detail=None):
    # Fallback for cities without a play-area/bay mask: the plain shore of the
    # land mask adjacent to saltwater (no channel removal).
    if play is None or bay is None:
        return land.boundary.intersection(saltwater.buffer(0.0008)).intersection(clip)

    # Coastline = the FULL-DETAIL shore of in-play LAND that borders qualifying
    # saltwater (ocean + enclosed bay). We trace every meander of the real shore
    # and only bridge across the specific narrow river-mouths / straits listed in
    # cfg["dams"] (each < 1 mi across, so not coastline by the game rule).
    #
    # 1. in-play land: the OSM bay-shore mask (good Pacific/peninsula detail)
    #    unioned with (play area − bay). The play-area term fills the East Bay /
    #    South Bay land that the peninsula-only mask misses.
    all_land = unary_union([play.difference(bay).buffer(0), land]).buffer(0)
    water = saltwater.buffer(0)
    water0 = water  # the un-dammed water, to know which water we filled in as land

    # 2. Cut the water at every dam and fill everything on the LANDWARD side of
    #    each dam line back in as land, so the shore runs straight across the
    #    mouth (the user's line IS the coast) with no leftover coves poking
    #    inland. Landward = the local half-plane of the dam line that does not
    #    hold the open bay. Unmarked shore keeps its full detail.
    dam_lines = None
    if dams:
        from shapely.geometry import LineString, Point
        dam_lines = unary_union([LineString(seg) for seg in dams])
        dam_poly = _dam_polys(dams)
        cut = water.difference(dam_poly)
        comps = list(cut.geoms) if cut.geom_type == "MultiPolygon" else [cut]
        comps.sort(key=lambda p: p.area, reverse=True)
        main = comps[0]  # the open bay/ocean

        fill = [all_land, dam_poly]
        # Any water body fully disconnected from the open bay by the dams
        # (upstream rivers, the Delta) becomes land.
        for c in comps[1:]:
            fill.append(c)
        # Plus, for each dam, the strip of open-bay water that still reaches
        # inland past the line (little coves): everything on the landward side
        # within a local window around the mouth.
        for seg in dams:
            (x0, y0), (x1, y1) = seg
            ls = LineString(seg)
            dx, dy = x1 - x0, y1 - y0
            L = (dx * dx + dy * dy) ** 0.5 or 1e-9
            # unit left normal of A->B
            nx, ny = -dy / L, dx / L
            mx, my = (x0 + x1) / 2, (y0 + y1) / 2
            left_pt = Point(mx + nx * 0.003, my + ny * 0.003)
            # landward = the side NOT containing the open bay near the mouth
            left_is_sea = main.buffer(0.0004).contains(left_pt)
            side = -0.02 if left_is_sea else 0.02
            half = ls.buffer(side, single_sided=True)
            window = ls.buffer(0.008)  # ~0.9 km around the mouth
            landward = half.intersection(window)
            pocket = main.intersection(landward)
            if not pocket.is_empty:
                fill.append(pocket)
        all_land = unary_union(fill).buffer(0)
        water = main.difference(unary_union([g for g in fill if g is not all_land])).buffer(0)
    # the water we turned into land (up-creek channels + coves behind each dam).
    # Keep only substantial pockets — buffer(0) reprocessing leaves hairline
    # slivers all along the coast that would otherwise nick the OSM shore apart.
    filled_region = None
    if dams:
        diff = water0.difference(water)
        polys = list(diff.geoms) if diff.geom_type == "MultiPolygon" else [diff]
        filled_region = unary_union([p for p in polys if p.area > 5e-7])

    # 3. shore. `water.boundary` (wb) is the topologically-correct shore: a set
    #    of continuous closed rings that already carry the straight mouth
    #    crossings the dams created. It comes from the coarse Census mask, so it
    #    sits ~30 m off the real coast. Rather than splice in OSM (which breaks
    #    the line into disconnected pieces at every seam), we KEEP each ring whole
    #    and just pull its vertices onto the high-detail OSM coastline:
    #      • densify the ring to ~17 m so it can take on OSM's shape,
    #      • move every vertex to the nearest point on the OSM shore when that is
    #        within ~66 m — this makes the open-bay shore match CARTO exactly,
    #      • but leave vertices within ~180 m of a dam line untouched, so each
    #        dammed mouth keeps its clean straight crossing.
    #    Because we only move vertices (never cut), every ring stays continuous
    #    and the snapped OSM banks meet the straight bridge with no gap.
    if detail is not None and not detail.is_empty:
        from shapely.geometry import LineString, Point
        from shapely.strtree import STRtree
        from shapely.ops import nearest_points
        wb = water.boundary
        snap_detail = detail
        if filled_region is not None and not filled_region.is_empty:
            # drop OSM that traces up the dammed-off creeks so vertices near a
            # mouth snap to the bay bank, never up the (now landlocked) channel.
            snap_detail = detail.difference(filled_region.buffer(0.0003))
        osm_geoms = (
            list(snap_detail.geoms)
            if snap_detail.geom_type.startswith("Multi")
            else [snap_detail]
        )
        tree = STRtree(osm_geoms)
        snap_tol = 0.0006  # ~66 m
        dz = dam_lines.buffer(0.0016) if dam_lines is not None else None  # ~180 m
        rings = list(wb.geoms) if wb.geom_type == "MultiLineString" else [wb]
        snapped = []
        for ring in rings:
            nc = []
            for x, y in ring.segmentize(0.00015).coords:
                p = Point(x, y)
                if dz is not None and dz.contains(p):
                    nc.append((x, y))
                    continue
                idx = tree.query_nearest(p)
                near_geom = osm_geoms[idx[0] if hasattr(idx, "__len__") else idx]
                q = nearest_points(near_geom, p)[0]
                nc.append((q.x, q.y) if p.distance(q) <= snap_tol else (x, y))
            snapped.append(LineString(nc))
        shore = unary_union(snapped)
    else:
        shore = all_land.boundary.intersection(water.buffer(0.0008))

    # 4. keep only shore on big landmasses — drops marsh islets / small islands
    #    (and any offshore mask edge picked up by the fallback above).
    polys = list(all_land.geoms) if all_land.geom_type == "MultiPolygon" else [all_land]
    big = unary_union([p for p in polys if p.area > 0.0008])
    shore = shore.intersection(big.boundary.buffer(0.0025))
    shore = shore.intersection(clip)

    # 4b. clip out excluded regions (e.g. Suisun Bay / Delta east of Carquinez):
    #     the shore simply ends at the boundary — no bridge line, no sliver.
    if exclude is not None and not exclude.is_empty:
        shore = shore.difference(exclude)

    # 5. drop tiny isolated shore fragments (little cove hooks / stray water
    #    dots left near a dam mouth) — real coastline merges into long lines, so
    #    any standalone piece shorter than ~300 m is an artifact.
    merged = linemerge(shore) if not shore.is_empty else shore
    parts = list(merged.geoms) if merged.geom_type == "MultiLineString" else [merged]
    parts = [p for p in parts if not p.is_empty and p.length >= 0.003]
    return unary_union(parts) if parts else shore


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

    coast_exclude = None
    if cfg.get("coast_exclude"):
        coast_exclude = unary_union([box(*bb) for bb in cfg["coast_exclude"]])

    coast_detail = None
    if cfg.get("coastline_detail"):
        coast_detail = unary_union(feats(load(src(cfg["coastline_detail"]))))

    print(f"building features for {slug}…")
    features = (
        ("coastline", to_multiline(build_coastline(land, saltwater, play, bay, clip, cfg.get("dams"), coast_exclude, coast_detail), 0.00015)),
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
