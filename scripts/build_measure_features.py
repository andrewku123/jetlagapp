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

    from shapely.geometry import LineString, Point
    from shapely.ops import substring

    merged = linemerge(unary_union(detail))
    parts = list(merged.geoms) if merged.geom_type == "MultiLineString" else [merged]
    parts.sort(key=lambda g: g.length, reverse=True)
    main = parts[0]  # the single continuous coast line

    # Dam bridges: each dam is two bank coords. The stretch of the continuous
    # shore BETWEEN the two banks is the up-river/slough excursion — we drop it
    # and jump straight bank-to-bank, so the coast runs across the mouth. A
    # length cap keeps this local (never removes a big real headland).
    if dams:
        intervals = []
        for seg in dams:
            pa, pb = Point(seg[0]), Point(seg[1])
            a = main.project(pa)
            b = main.project(pb)
            # only bridge when both banks actually sit on the main coastline —
            # if a mouth is >~600 m off, its shore isn't traced by OSM coastline
            # here (separate creek/absent), so the dam is a no-op, not a bridge
            # applied at the wrong spot.
            if pa.distance(main.interpolate(a)) > 0.0055:
                continue
            if pb.distance(main.interpolate(b)) > 0.0055:
                continue
            lo, hi = sorted((a, b))
            if 0 < hi - lo <= 0.08:  # a local mouth detour (~<9 km of shore)
                intervals.append((lo, hi))
        intervals.sort()
        merged_iv = []
        for lo, hi in intervals:
            if merged_iv and lo <= merged_iv[-1][1]:
                merged_iv[-1] = (merged_iv[-1][0], max(merged_iv[-1][1], hi))
            else:
                merged_iv.append((lo, hi))
        if merged_iv:
            coords = []
            cursor = 0.0
            for lo, hi in merged_iv:
                if lo > cursor:
                    piece = substring(main, cursor, lo)
                    if not piece.is_empty:
                        coords.extend(list(piece.coords))
                coords.append(main.interpolate(hi).coords[0])  # straight bridge
                cursor = hi
            if cursor < main.length:
                piece = substring(main, cursor, main.length)
                if not piece.is_empty:
                    coords.extend(list(piece.coords))
            main = LineString(coords)

    # Keep real islands (sizeable closed OSM loops); drop tiny islets / stray
    # creek fragments that OSM leaves as separate short open lines.
    shore_parts = [main]
    for g in parts[1:]:
        if g.length >= 0.01 and g.is_ring:
            shore_parts.append(g)
    shore = unary_union(shore_parts)

    # Clip to the play area; remove excluded regions (Suisun Bay / Delta east of
    # Carquinez) — the shore just ends cleanly at the neck, no bridge, no sliver.
    shore = shore.intersection(clip)
    # Keep only shore inside the actual playable area — coast outside it can't
    # eliminate anything (Marin/North Bay/Pacific coast beyond the play area), so
    # it's dropped. Buffer a little so the shoreline right along the play-area
    # edge (census-place polygons sit slightly inland of the OSM coast) is kept.
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
