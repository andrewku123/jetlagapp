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
            # (No full-width San Pablo cutoff: the play-buffer clip already drops
            # the out-of-play north/west San Pablo shore, and a hard 38.0021 box
            # would also strip the IN-PLAY Point Pinole / Pinole shore, which faces
            # San Pablo Bay and rises to ~38.013.)
            # Out-of-play Marin/North-Bay shore. Marin is one continuous landmass
            # with the in-play East Bay (they join around the north of the bbox),
            # so it can't be told apart topologically — we exclude it by region.
            # Two boxes shaped to spare Angel Island (lon -122.446..-122.418, up
            # to lat 37.872): box A is north of Raccoon Strait and stops at lon
            # -122.43 (keeps Point Molate/San Pablo); box B is west of Angel.
            [-122.70, 37.873, -122.43, 38.0021],  # Tiburon + San Pablo west shore (San Rafael/San Quentin)
            [-122.70, 37.820, -122.448, 37.873],  # Sausalito / Richardson Bay (west of Angel Island)
        ],
        "dams": [
            [[-122.394497, 37.960102], [-122.395999, 37.958749]],  # Castro Creek (Richmond)
            [[-122.364306, 37.909364], [-122.360530, 37.909635]],  # Albany/Golden Gate Fields
            [[-122.329888, 37.800120], [-122.330704, 37.796797]],  # Oakland Inner Harbor / Alameda W
            [[-122.236118, 37.750460], [-122.236161, 37.747372]],  # San Leandro Bay
            [[-122.203567, 37.712794], [-122.202140, 37.711919]],  # San Leandro shore
            [[-122.191615, 37.704467], [-122.190778, 37.704713]],  # San Leandro Marina / Oyster Bay
            [[-122.335317, 37.909127], [-122.335188, 37.909618]],  # Albany Bulb neck
            [[-122.325082, 37.901830], [-122.325103, 37.900950]],  # Albany marina
            [[-122.317700, 37.863487], [-122.317400, 37.862657]],  # Berkeley marina
            [[-122.298474, 37.776507], [-122.301114, 37.774268]],  # San Lorenzo / Sulphur Creek
            [[-122.329845, 37.800103], [-122.330704, 37.796848]],  # Oakland Inner Harbor (refined)
            [[-122.236247, 37.750528], [-122.237105, 37.747575]],  # San Leandro Bay (refined)
            [[-122.053084, 37.493060], [-122.053127, 37.490915]],  # Newark / Mowry Slough area
            [[-122.035768, 37.463822], [-122.033107, 37.459990]],  # Newark slough
            [[-122.063148, 37.445375], [-122.064178, 37.445971]],  # Ravenswood / Dumbarton E
            [[-122.077074, 37.448254], [-122.078533, 37.448220]],  # Ravenswood slough
            [[-122.089756, 37.451814], [-122.091751, 37.452104]],  # Ravenswood slough
            [[-122.094004, 37.453313], [-122.094326, 37.454412]],  # Ravenswood slough
            [[-122.100313, 37.457077], [-122.101707, 37.457708]],  # Ravenswood slough
            [[-122.112275, 37.463328], [-122.113563, 37.463669]],  # Ravenswood / East Palo Alto
            [[-122.115462, 37.465338], [-122.116385, 37.465985]],  # East Palo Alto slough
            [[-122.201271, 37.522695], [-122.203760, 37.525077]],  # Redwood City / Bair Island
            [[-122.223673, 37.542621], [-122.226098, 37.544373]],  # Redwood City / Bair Island
            [[-122.228458, 37.549035], [-122.229381, 37.550498]],  # Belmont Slough
            [[-122.243028, 37.552335], [-122.245345, 37.555992]],  # Belmont / Foster City
            [[-122.293432, 37.571096], [-122.294998, 37.570960]],  # San Mateo / Seal Slough
            [[-122.337570, 37.591757], [-122.338986, 37.591689]],  # Burlingame shore
            [[-122.375679, 37.746693], [-122.376151, 37.749001]],  # SF / Islais Creek area
            [[-122.389905, 37.776439], [-122.390571, 37.777117]],  # SF / Mission Creek
            [[-122.389884, 37.776244], [-122.390699, 37.777228]],  # SF / Mission Creek
        ],
    },
    "la": {
        # LA Metro sits on the open Pacific (Santa Monica Bay + San Pedro Bay).
        # Far from any state/international line, so those come back empty and the
        # questions demote to log-only in the app (kept in the dropdown).
        "play_bbox": (-118.80, 33.60, -117.55, 34.45),
        # LA has no separate land-polygon mask; the OSM coastline + a flooded
        # open-ocean polygon are enough. `la_ocean.geojson.json` is the raw sea
        # face flooded from the OSM coastline (scripts/build_la_play_area.py's
        # build_ocean([]) — reaches into the harbors); it's used only as the
        # topology reference for "which polygonized face is the open ocean".
        # Reproducible from committed data (the old out-of-repo la_build mask is
        # gone). Regenerate: python3 -c "import build_la_play_area as m, json;
        # from shapely.geometry import mapping;
        # json.dump({'type':'FeatureCollection','features':[{'type':'Feature',
        # 'properties':{},'geometry':mapping(m.build_ocean([]))}]},
        # open('la_ocean.geojson.json','w'))".
        "land": "la_ocean.geojson.json",
        "saltwater": ["la_ocean.geojson.json"],
        "play": "data:la.play-area.geojson.json",
        "bay": "la_ocean.geojson.json",
        "coastline_detail": "measure_src/osm_coastline_la.geojson",
        "counties": "data:la.counties.geojson.json",
        "states": "measure_src/us-states.geojson",
        "countries": "measure_src/countries.geojson",
        "state": "California",
        "state_neighbors": ["Nevada", "Arizona"],
        "country": "United States of America",
        "country_neighbor": "Mexico",
        # Dam mode: the shore is drawn straight across each harbor/river mouth in
        # la_coast_dams.json (the SAME file build_la_play_area.py uses for the
        # ocean border), so the coastline question and the play-area edge match.
        # Everything sealed behind a dam is treated as inland (not coast).
        "dams_file": "la_coast_dams.json",
        # Regions where the shore is dropped from the coastline entirely (the
        # play area is out of play there, so the beach can't eliminate anyone).
        # [w, s, e, n] lon/lat. Hermosa Beach gap: the Santa Monica shore
        # terminates at the north edge (33.868349) and the southern stretch
        # resumes at the south edge (33.859814); Hermosa in between is out.
        "coast_exclude": [
            [-118.43, 33.859814, -118.39, 33.868349],
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


def build_coastline(land, saltwater, play, bay, clip, dams=None, exclude=None, detail=None,
                    water_clip=None):
    # Open-ocean mode (cfg["coast_water_clip"]): keep only the OSM coastline that
    # hugs the big open-water mask (Pacific + major harbors). Inland waterways
    # that OSM tags natural=coastline (LA River, Rio Hondo, San Gabriel River)
    # and tiny marina inlets (Marina del Rey) are NOT in that mask, so their
    # coastline sits >water_clip from any mask water and drops out — no per-mouth
    # dams needed. Precision stays at OSM detail (the mask is only used to select
    # WHICH shore is ocean-facing). Used for simple open-coast metros like LA.
    if water_clip is not None and detail is not None and not detail.is_empty:
        merged = linemerge(unary_union(detail))
        coast_all = unary_union(list(merged.geoms) if merged.geom_type == "MultiLineString" else [merged])
        near = saltwater.boundary.buffer(water_clip)
        shore = coast_all.intersection(near)
        if play is not None and not play.is_empty:
            shore = shore.intersection(play.buffer(0.004))
        if exclude is not None and not exclude.is_empty:
            shore = shore.difference(exclude)
        shore = shore.intersection(clip)
        merged = linemerge(shore) if not shore.is_empty else shore
        parts = list(merged.geoms) if merged.geom_type == "MultiLineString" else [merged]
        parts = [g for g in parts if not g.is_empty and g.length >= 0.003]
        return unary_union(parts) if parts else shore

    # Fallback for cities without a play-area/bay mask: the plain shore of the
    # land mask adjacent to saltwater (no channel removal).
    if play is None or bay is None:
        return land.boundary.intersection(saltwater.buffer(0.0008)).intersection(clip)

    # Build the shore DIRECTLY from the high-detail OSM `natural=coastline`
    # (the exact data CARTO's basemap draws). linemerge stitches the 852 raw
    # ways into one continuous ~11 deg line covering the whole coast, plus
    # island loops. We take that continuous line as the shore, replace each
    # marked river-mouth with a straight bank-to-bank bridge, keep real
    # islands, then clip to the play area and drop the excluded Delta.
    if detail is None or detail.is_empty:
        # Fallback (no OSM detail): coarse mask shore.
        all_land = unary_union([play.difference(bay).buffer(0), land]).buffer(0)
        shore = all_land.boundary.intersection(saltwater.buffer(0.0008))
        return shore.intersection(clip)

    import math
    from shapely.geometry import LineString, Point
    from shapely.ops import polygonize, nearest_points

    merged = linemerge(unary_union(detail))
    lines = list(merged.geoms) if merged.geom_type == "MultiLineString" else [merged]
    coast_all = unary_union(lines)

    # Seal each marked river/slough/estuary mouth with a straight "dam" wall.
    # Snap both user-supplied bank coords to the nearest point on the real OSM
    # coastline, then draw the wall bank-to-bank (extended a hair past each bank
    # so it fully crosses). A wall turns the narrow waterway behind it into a
    # closed region separate from the open bay. A mouth whose banks are >~660 m
    # off any coastline (not actually traced by OSM here) is skipped, not walled
    # at the wrong place.
    walls = []
    if dams:
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

    # Polygonize the coastline + dam walls + clip boundary into faces, then keep
    # only the single largest WATER face — the open bay (connected out the Golden
    # Gate to the ocean). Islands in the bay come back as holes (kept); each
    # sealed slough / estuary / marsh interior is its own separate face (dropped),
    # so its shore AND the islets inside it disappear. This matches "draw a line
    # across the mouth and everything cut off from the bay is removed".
    net = unary_union(lines + walls + [clip.exterior])
    faces = list(polygonize(net))
    # The bay is the face that overlaps the saltwater mask the most (a coarse
    # rep-point-in-mask test is unreliable — far-offshore rep points fall outside
    # the Census water polygon). The open bay + ocean is one connected face here.
    bayface = max(faces, key=lambda f: f.intersection(saltwater).area)
    shore = bayface.boundary
    # Drop the artificial clip-bbox edges we added only to close the ocean side.
    shore = shore.difference(clip.exterior.buffer(0.0008))
    shore = shore.intersection(clip)
    # Keep only shore near the play area — coast far outside it can't eliminate
    # anything. A small buffer keeps every real in-play shore, including shoreline
    # parks that aren't census places (e.g. Point Pinole). Out-of-play shore that
    # still sits next to play water (Marin: Tiburon/Sausalito/Richardson Bay) is
    # removed by the region excludes below, since Marin is one continuous landmass
    # with the in-play East Bay and can't be told apart topologically.
    if play is not None and not play.is_empty:
        shore = shore.intersection(play.buffer(0.004))
    if exclude is not None and not exclude.is_empty:
        shore = shore.difference(exclude)

    # Drop tiny leftover fragments (stray cove hooks / clipped nubs).
    merged = linemerge(shore) if not shore.is_empty else shore
    parts = list(merged.geoms) if merged.geom_type == "MultiLineString" else [merged]
    parts = [g for g in parts if not g.is_empty and g.length >= 0.003]
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
    if cfg.get("dams_file"):
        cfg = {**cfg, "dams": load(src(cfg["dams_file"]))["dams"]}
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
        ("coastline", to_multiline(build_coastline(land, saltwater, play, bay, clip, cfg.get("dams"), coast_exclude, coast_detail, cfg.get("coast_water_clip")), 0.00015)),
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

    prefix = "" if slug == "bayarea" else f"{slug}."
    dest = os.path.join(DATA, f"{prefix}measure-features.geojson.json")
    with open(dest, "w") as f:
        json.dump(out, f)
    print("wrote", dest, os.path.getsize(dest), "bytes")


if __name__ == "__main__":
    main()
