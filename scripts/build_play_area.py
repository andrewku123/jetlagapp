#!/usr/bin/env python3
"""Build the play-area polygon — opt-out, county-scoped model.

General rule (works for any metro once stations.json exists):
  1. Find the counties the transit network touches (the distinct `county` values
     on the eligible stations).
  2. The candidate set is EVERY Census place (city / town / CDP) in those
     counties.
  3. A curator deletes the places they don't want (play_area_overrides.json
     "drop"). Everything not dropped is kept.
  4. Auto-clean: any kept *unincorporated* place (CDP) left completely surrounded
     by non-playable area — i.e. its border touches no other kept place — is
     dropped too (a lone island in the grey). "keep" in the overrides force-keeps
     a place even if it would be auto-dropped.
  5. Play area = the union of the kept place polygons, then fill any fully
     enclosed hole (a pocket ringed on all sides by in-play land is in play).

The open land between/around the kept places (regional parks, ranchland, the big
mountains, the east-county hills, the Santa Cruz range) is NOT a named place, so
it stays out — the play area trims to the transit cities, not the whole county.

POIs are then clipped to this polygon (see dedup_poi.py): strictly inside for
natural categories (park, mountain); a small 150 m shoreline buffer is allowed
for the other categories so pier/waterfront pins (Exploratorium, USS Hornet…)
that sit just over the water inside an in-play city are kept.

Emits (committed):
  play_area.geojson           raw union of kept places
  play_area_buffered.geojson  union buffered by SHORELINE_BUF_M (pier rescue)
  play_area_cities.json       sorted keep list with the reason each qualified
and copies the raw union into the app at
  ../../<app>/src/data/play-area.geojson.json
"""
import json, math, os, sys, io, zipfile, urllib.request
from shapely.geometry import shape, Point, Polygon, mapping
from shapely.ops import transform, unary_union

HERE = os.path.dirname(os.path.abspath(__file__))
STATIONS = os.environ.get("STATIONS_JSON",
    os.path.join(HERE, "..", "..", "repos", "bayarea-hideandseek", "src", "data", "stations.json"))
APP_PLAY_AREA = os.environ.get("APP_PLAY_AREA",
    os.path.join(HERE, "..", "..", "repos", "bayarea-hideandseek", "src", "data", "play-area.geojson.json"))
OVERRIDES = os.path.join(HERE, "play_area_overrides.json")
CACHE = os.path.join(HERE, "_census_place")
TRANSIT_LINES = os.environ.get("TRANSIT_LINES",
    os.path.join(HERE, "..", "..", "repos", "bayarea-hideandseek", "src", "data", "transit-lines.geojson.json"))

SHORELINE_BUF_M = 150.0        # pier/waterfront rescue for non-natural POIs
ADJ_TOL_M = 150.0              # boundary-adjacency tolerance
SURROUND_MIN_FRAC = 0.02      # a kept CDP touching <2% of its border to another
                              # kept place counts as "surrounded by nonplayable"
ENCLAVE_FILL_FRAC = 0.9       # a dropped place >=90% covered by the filled union is a
                              # fully-enclosed enclave -> keep it in play (not grey)
DISPLAY_HOLE_MAX_KM2 = 12.0   # in the app display, fill interior holes (land ringed by
                              # in-play land + bay water) smaller than this, e.g. the
                              # Albany waterfront / North Richmond shoreline specks
BRIDGE_RADIUS_MI = 0.5        # half-width of a transit-line corridor bridge
BRIDGE_NEAR_M = 60.0          # gap endpoint within this of a kept place = touching
BRIDGE_MAX_MI = 12.0         # only bridge gaps shorter than this between two kept places
ISLAND_LON_CUTOFF = -122.6   # drop place parts west of this (far-offshore Pacific islands, e.g. Farallones)
# Census places: full-resolution TIGER/Line (dense coastline nodes, ~6-7x more
# vertices than the 1:500k cartographic file). These are *legal* limits that
# extend out into the bay, so each place is clipped back to the real shoreline by
# subtracting the dense bay+ocean water mask (build_water_mask.py -> AREAWATER).
# Counties stay on the 1:500k cartographic file (only used for tagging/inclusion).
CBF_URL = "https://www2.census.gov/geo/tiger/TIGER2023/PLACE/tl_2023_06_place.zip"
CBF_STEM = "tl_2023_06_place"
COUNTY_URL = "https://www2.census.gov/geo/tiger/GENZ2023/shp/cb_2023_us_county_500k.zip"
COUNTY_STEM = "cb_2023_us_county_500k"
WATER_MASK = os.path.join(HERE, "bay_water_mask.geojson")
STATE_NAME = "California"      # state the transit counties live in

M = 111320.0


def _proj(lat0):
    cos0 = math.cos(math.radians(lat0))
    def to_m(x, y, z=None): return (x * M * cos0, y * M)
    def to_ll(x, y, z=None): return (x / (M * cos0), y / M)
    return to_m, to_ll


def ensure_shapefile(url, stem):
    shp = os.path.join(CACHE, stem + ".shp")
    if os.path.exists(shp):
        return shp
    os.makedirs(CACHE, exist_ok=True)
    print(f"downloading {url} ...", file=sys.stderr)
    data = urllib.request.urlopen(url, timeout=180).read()
    zipfile.ZipFile(io.BytesIO(data)).extractall(CACHE)
    return shp


def load_counties(names):
    import shapefile
    r = shapefile.Reader(ensure_shapefile(COUNTY_URL, COUNTY_STEM))
    flds = [f[0] for f in r.fields[1:]]
    out = {}
    for sh, rec in zip(r.shapes(), r.records()):
        d = dict(zip(flds, rec))
        if d.get("STATE_NAME") == STATE_NAME and d["NAME"] in names:
            g = shape(sh.__geo_interface__)
            if not g.is_valid:
                g = g.buffer(0)
            out[d["NAME"]] = g
    return out


def _load_water_mask():
    """Dense bay+ocean water polygon (Census AREAWATER, build_water_mask.py),
    in lon/lat. Subtracted from each full-resolution TIGER/Line place so the
    legal limits that reach into the bay are clipped back to the real coast."""
    if not os.path.exists(WATER_MASK):
        return None
    g = shape(json.load(open(WATER_MASK))["geometry"])
    return g.buffer(0) if not g.is_valid else g


def load_county_places(counties):
    """Every Census place with >=10% of its area inside the given counties,
    tagged with the county it overlaps most and whether it is a CDP. Places use
    the full-resolution TIGER/Line geometry clipped to the real shoreline (the
    bay+ocean water mask is subtracted) so coastlines are dense, not 1:500k."""
    import shapefile
    r = shapefile.Reader(ensure_shapefile(CBF_URL, CBF_STEM))
    flds = [f[0] for f in r.fields[1:]]
    water = _load_water_mask()
    out = {}
    for sh, rec in zip(r.shapes(), r.records()):
        d = dict(zip(flds, rec))
        g = shape(sh.__geo_interface__)
        if not g.is_valid:
            g = g.buffer(0)
        if water is not None and g.intersects(water):
            g = g.difference(water)
            if not g.is_valid:
                g = g.buffer(0)
        if g.is_empty:
            continue
        best, bestA = None, 0.0
        for cn, cg in counties.items():
            if g.intersects(cg):
                a = g.intersection(cg).area
                if a > bestA:
                    bestA, best = a, cn
        if best is None or bestA < 0.10 * g.area:
            continue
        nm = d["NAMELSAD"]
        out[nm] = {"geom": g, "county": best, "cdp": nm.endswith("CDP")}
    return out


def transit_bridges(city_m, to_m):
    """Corridors that re-include the transit line where it runs through non-playable
    land *between two kept places* (e.g. BART Rockridge->Orinda over the Berkeley
    hills, or Castro Valley->Dublin up Dublin Canyon). For each line, the part
    outside the kept union is split into gap segments; a segment is bridged only if
    BOTH its ends touch a kept place (so it connects two in-play areas) and it is
    shorter than BRIDGE_MAX_MI (so trailing stubs off the end of a line -- e.g.
    Caltrain south of San Jose toward deleted Gilroy -- are left out). The kept
    gap segments are buffered by BRIDGE_RADIUS_MI into a hideable corridor."""
    if not os.path.exists(TRANSIT_LINES):
        return None
    from shapely.geometry import LineString
    fc = json.load(open(TRANSIT_LINES))
    feats = fc["features"] if isinstance(fc, dict) else fc
    near = city_m.boundary
    segs = []
    maxlen = BRIDGE_MAX_MI * 1609.344
    for f in feats:
        if f["geometry"]["type"] != "LineString":
            continue
        ln = LineString([to_m(x, y) for x, y in f["geometry"]["coordinates"]])
        gap = ln.difference(city_m)
        parts = [gap] if gap.geom_type == "LineString" else list(getattr(gap, "geoms", []))
        for p in parts:
            if p.is_empty or p.geom_type != "LineString" or p.length > maxlen:
                continue
            a, b = Point(p.coords[0]), Point(p.coords[-1])
            if a.distance(near) <= BRIDGE_NEAR_M and b.distance(near) <= BRIDGE_NEAR_M:
                segs.append(p)
    if not segs:
        return None
    return unary_union(segs).buffer(BRIDGE_RADIUS_MI * 1609.344)


def fill_holes(geom):
    """Drop interior rings: any pocket fully enclosed by the play area (ringed on
    all sides by in-play land) becomes in-play too. Concave bays that open to the
    outside are not interior rings, so they stay open."""
    if geom.geom_type == "Polygon":
        return Polygon(geom.exterior)
    return unary_union([Polygon(g.exterior) for g in geom.geoms])


def fill_small_holes(geom, max_area_m2):
    """Like fill_holes but only fills interior rings smaller than max_area_m2,
    so large genuinely-out-of-play enclosed space (if any) is left grey."""
    def one(poly):
        keep = [r for r in poly.interiors if Polygon(r).area >= max_area_m2]
        return Polygon(poly.exterior, keep)
    if geom.geom_type == "Polygon":
        return one(geom)
    return unary_union([one(g) for g in geom.geoms])


# A corridor traced down the open water of the San Francisco Bay: the full central
# + south bay, WEST along the SF north shore out to the Golden Gate Bridge so every
# SF pier (Embarcadero, Wharf, Marina, Crissy) is included, and capped on the NORTH
# by the real Richmond-San Rafael Bridge (traced from OpenStreetMap) so San Pablo
# Bay north of the bridge stays grey. The west boundary runs from the GG bridge up
# through Raccoon Strait, passing east of Sausalito / Tiburon / Belvedere (Marin
# stays grey) but leaving Angel Island inside (in play). It hugs the bay so it
# never covers the East Bay hills; the real shoreline is carved out by subtracting
# the land places. Display-only (dimming + satellite).
#
# Richmond-San Rafael Bridge centreline, EAST (Richmond) -> WEST (San Rafael),
# downsampled from OSM way 24315544. Forms the bay's north edge.
RSR_BRIDGE_LL = [
    (-122.4054, 37.9323), (-122.4228, 37.9336), (-122.4495, 37.9354),
    (-122.4522, 37.9359), (-122.4550, 37.9366), (-122.4687, 37.9407),
    (-122.4778, 37.9425),
]
BAY_CORRIDOR_LL = [
    *RSR_BRIDGE_LL,                                        # N edge: R-SR bridge, E (Richmond) -> W (San Rafael)
    (-122.473, 37.915), (-122.468, 37.895),               # S down the Marin side, in open water
    # Wrap the Tiburon/Belvedere peninsula: the corridor reaches WEST over the
    # peninsula (down to ~-122.47, just east of its Richardson-Bay shore) and the
    # real Marin coastline (MARIN_LAND, traced from OSM) is subtracted in
    # bay_water(), so the water hugs the peninsula's east + south shore instead of
    # a straight diagonal. Angel Island is NOT subtracted, so it stays in play.
    (-122.458, 37.892), (-122.470, 37.884),               # NE corner -> over the peninsula (carved by MARIN_LAND)
    (-122.472, 37.872), (-122.470, 37.860),               # down the peninsula's west side past Belvedere (carved)
    (-122.476, 37.840), (-122.478, 37.823),               # to the GG bridge Marin anchorage / mid-Gate
    (-122.478, 37.808), (-122.466, 37.806), (-122.44, 37.806),  # GG bridge SF anchorage, E along the SF north shore
    (-122.41, 37.78),                                      # Embarcadero
    (-122.37, 37.72), (-122.30, 37.63), (-122.22, 37.55),  # down the peninsula shore
    (-122.13, 37.48), (-122.05, 37.45),                    # south bay SW -> Alviso tip
    (-121.98, 37.50), (-122.02, 37.57), (-122.10, 37.66),  # up the East Bay shore (Union City -> Hayward)
    (-122.18, 37.73), (-122.28, 37.82), (-122.30, 37.87),  # San Leandro -> Berkeley -> Richmond
    (-122.34, 37.92),                                      # back NW toward the bridge east end
]
BAY_SEEDS_LL = [(-122.33, 37.79), (-122.36, 37.88), (-122.13, 37.58), (-122.10, 37.50)]


def _load_bay_land(to_m):
    """Dense bay-shore landmass traced from the OSM coastline, in metres
    (built by build_bay_land.py -> bay_land.geojson, covering the whole bay
    perimeter at OSM resolution). Subtracted from the bay corridor so the water
    follows the real shoreline everywhere instead of spilling over unincorporated
    shoreline the census-place polygons don't cover. Angel Island is deliberately
    excluded from this polygon so it stays in play (covered by the corridor).
    Falls back to the Marin-only marin_land.geojson if the full mask is absent."""
    for fname in ("bay_land.geojson", "marin_land.geojson"):
        path = os.path.join(HERE, fname)
        if os.path.exists(path):
            g = shape(json.load(open(path))["geometry"])
            if not g.is_valid:
                g = g.buffer(0)
            return transform(to_m, g)
    return None


def bay_water(places_all_m, to_m):
    """The open bay water as a polygon: the hand-traced bay corridor minus every
    land place, keeping the connected water component(s) that contain a seed."""
    corr = Polygon([to_m(lon, lat) for lon, lat in BAY_CORRIDOR_LL])
    land = unary_union(list(places_all_m.values()))
    bay_land = _load_bay_land(to_m)
    if bay_land is not None:
        land = unary_union([land, bay_land])
    water = corr.difference(land)
    polys = [water] if water.geom_type == "Polygon" else \
        [g for g in getattr(water, "geoms", []) if g.geom_type == "Polygon"]
    seeds = [Point(*to_m(lon, lat)) for lon, lat in BAY_SEEDS_LL]
    keep = [p for p in polys if any(p.intersects(s) for s in seeds)]
    if not keep and polys:
        keep = [max(polys, key=lambda p: p.area)]
    return unary_union(keep) if keep else None


def main():
    stations = json.load(open(STATIONS))
    lats = [s["lat"] for s in stations]
    lat0 = sum(lats) / len(lats)
    to_m, to_ll = _proj(lat0)

    transit_counties = sorted({s["county"] for s in stations})
    print("transit counties:", ", ".join(transit_counties))
    counties_ll = load_counties(set(transit_counties))
    missing_co = [c for c in transit_counties if c not in counties_ll]
    if missing_co:
        print("WARN counties with no polygon:", missing_co, file=sys.stderr)

    places = load_county_places(counties_ll)
    # Drop far-offshore island parts of any place (e.g. the Farallon Islands, which
    # are legally part of San Francisco city but sit ~27 mi out in the Pacific). A
    # multipolygon part is dropped if its centroid is west of ISLAND_LON_CUTOFF.
    for n, d in places.items():
        g = d["geom"]
        if g.geom_type == "MultiPolygon":
            parts = [p for p in g.geoms if p.centroid.x >= ISLAND_LON_CUTOFF]
            if len(parts) != len(g.geoms):
                d["geom"] = unary_union(parts)
                print(f"dropped {len(g.geoms) - len(parts)} offshore island part(s) from {n}")
    places_m = {n: transform(to_m, d["geom"]) for n, d in places.items()}
    is_cdp = {n: d["cdp"] for n, d in places.items()}

    ov = json.load(open(OVERRIDES)) if os.path.exists(OVERRIDES) else {}
    force_keep = set(ov.get("keep", []))
    drop = set(ov.get("drop", []))
    for n in drop | force_keep:
        if n not in places:
            print(f"WARN override name not in candidate places: {n!r}", file=sys.stderr)

    kept = set(places) - drop
    reason = {n: ("manual-keep" if n in force_keep else "kept") for n in kept}

    # Auto-clean: drop kept CDPs left completely surrounded by non-playable area
    # (border touches no other kept place). Iterate to a fixed point, since
    # removing one island can isolate its neighbour. force_keep is immune.
    auto_dropped = []
    while True:
        kl = sorted(kept)
        removed_this_pass = []
        for n in kl:
            if not is_cdp[n] or n in force_keep:
                continue
            b = places_m[n].boundary
            if not b.length:
                continue
            others = [places_m[x] for x in kept if x != n]
            ou = unary_union(others) if others else None
            fi = (b.intersection(ou.buffer(ADJ_TOL_M)).length / b.length) if ou is not None else 0.0
            if fi < SURROUND_MIN_FRAC:
                removed_this_pass.append(n)
        if not removed_this_pass:
            break
        for n in removed_this_pass:
            kept.discard(n)
            reason.pop(n, None)
            auto_dropped.append(n)
    if auto_dropped:
        print("auto-dropped (surrounded CDP):", ", ".join(sorted(auto_dropped)))
        for n in sorted(auto_dropped):
            reason  # already removed from reason

    keep = sorted(kept)
    city_m = unary_union([places_m[n] for n in keep])
    bridges = transit_bridges(city_m, to_m)
    if bridges is not None:
        print("added transit-line bridges between kept places")
        city_m = unary_union([city_m, bridges])
    union_m = fill_holes(city_m)
    # Carve dropped places back out of the hole-filled union -- but ONLY those
    # that are NOT fully enclosed by in-play land. A deleted place that is an
    # interior hole (fully ringed by kept neighbours, e.g. San Pablo / East
    # Richmond Heights inside Richmond, or Shell Ridge / San Miguel by Walnut
    # Creek) is left FILLED = in play, because an enclave completely surrounded
    # by playable land should itself be playable. A deleted place that opens onto
    # out-of-play land (e.g. Moraga -> EBMUD/Las Trampas hills, coverage ~0)
    # stays carved out = grey. Enclosure is measured as the fraction of the
    # place covered by the hole-filled union.
    removed = []
    refilled = []
    for n in (drop | set(auto_dropped)):
        if n not in places_m:
            continue
        p = places_m[n]
        cov = (p.intersection(union_m).area / p.area) if p.area else 0.0
        if cov >= ENCLAVE_FILL_FRAC:
            refilled.append(n)
        else:
            removed.append(p)
    if removed:
        union_m = union_m.difference(unary_union(removed))
    if refilled:
        print("kept enclosed enclaves in play (not carved out):",
              ", ".join(sorted(refilled)))
    # Manual hand-drawn corridors / fill regions: where the curator wants the play
    # area to reach into open land that has no transit line to bridge it (e.g. the
    # Berkeley-hills valley between Berkeley and Orinda). Both are added AFTER
    # hole-fill and the deleted-place carve-out so they are exactly the geometry the
    # curator drew -- they never close off a wedge and trick fill_holes into
    # gobbling a whole enclosed hillside. A "corridor" is a buffered polyline (thin
    # strip); a "fill_region" is a polygon ring traced around the area to include.
    extra = []
    for c in ov.get("corridors", []):
        from shapely.geometry import LineString
        pts = [to_m(lon, lat) for lon, lat in c["coords"]]
        r = c.get("radius_mi", BRIDGE_RADIUS_MI) * 1609.344
        geom = LineString(pts) if len(pts) > 1 else Point(*pts[0])
        extra.append(geom.buffer(r))
    for fr in ov.get("fill_regions", []):
        ring = [to_m(lon, lat) for lon, lat in fr["ring"]]
        extra.append(Polygon(ring))
    if extra:
        print(f"added {len(extra)} manual corridor/fill region(s)")
        union_m = unary_union([union_m] + extra)
    union_ll = transform(to_ll, union_m)
    buf_ll = transform(to_ll, union_m.buffer(SHORELINE_BUF_M))

    feat = {"type": "Feature", "properties": {"name": "play-area"},
            "geometry": mapping(union_ll)}
    json.dump(feat, open(os.path.join(HERE, "play_area.geojson"), "w"))
    json.dump({"type": "Feature", "properties": {"name": "play-area-buffered"},
               "geometry": mapping(buf_ll)}, open(os.path.join(HERE, "play_area_buffered.geojson"), "w"))
    json.dump({"model": "opt-out-county",
               "transit_counties": transit_counties,
               "shoreline_buffer_m": SHORELINE_BUF_M,
               "candidate_places": len(places),
               "dropped_manual": sorted(drop),
               "dropped_auto_surrounded": sorted(auto_dropped),
               "count": len(keep),
               "cities": [{"name": n, "county": places[n]["county"],
                           "type": "CDP" if is_cdp[n] else "city/town",
                           "reason": reason[n]} for n in keep]},
              open(os.path.join(HERE, "play_area_cities.json"), "w"), indent=1)

    if os.path.exists(os.path.dirname(APP_PLAY_AREA)):
        # The app only uses this polygon for display (out-of-play dimming mask,
        # satellite clip-path / tile culling), not for any correctness check, so
        # ship a simplified version (~40 m tolerance). The open bay water is
        # unioned in for display only so the bay shows as water instead of grey —
        # it is NOT in play_area.geojson and never affects POI clipping.
        bay = bay_water(places_m, to_m)
        display_m = unary_union([union_m, bay]) if bay is not None else union_m
        # Unioning the bay water can ring small bits of unnamed shoreline land
        # (e.g. Albany Hill / the Golden Gate Fields flats, or a bay-fronting
        # deleted place like North Richmond) so they become interior holes — grey
        # specks fully surrounded by in-play land + water. Fill any such enclosed
        # hole below DISPLAY_HOLE_MAX_KM2 so the waterfront reads clean. This is
        # display-only (the gameplay play_area / POI clip is untouched).
        display_m = fill_small_holes(display_m, DISPLAY_HOLE_MAX_KM2 * 1e6)
        simp_ll = transform(to_ll, display_m.simplify(40.0, preserve_topology=True))
        app_feat = {"type": "Feature", "properties": {"name": "play-area"},
                    "geometry": mapping(simp_ll)}
        json.dump({"type": "FeatureCollection", "features": [app_feat]},
                  open(APP_PLAY_AREA, "w"))
        print("updated app play-area:", APP_PLAY_AREA)

    print(f"\nplay area = {len(keep)} kept places "
          f"({len(places)} candidates - {len(drop)} manual - {len(auto_dropped)} auto)")
    by = {}
    for n in keep:
        by.setdefault(places[n]["county"], []).append(n)
    for cn in transit_counties:
        lst = by.get(cn, [])
        print(f"  {cn} ({len(lst)}): " +
              ", ".join(x.replace(" city", "").replace(" town", "").replace(" CDP", "*") for x in lst))


if __name__ == "__main__":
    main()
