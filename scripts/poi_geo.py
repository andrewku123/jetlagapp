"""Shared, city-agnostic geometry helpers + the region registry for the POI pipeline.

The per-city input is the set of eligible stations; `build_play_area.py` turns it
into the play-area polygons. For *discovery/recall* (bbox, point-in-polygon,
Overpass area) we use the 150 m-buffered city union (`play_area_buffered.geojson`)
so waterfront/pier places just off the land polygon are still found; the precise
strict clip (raw for parks/mountains, buffered for the rest) happens later in
`dedup_poi.py`. If the buffered file is absent we fall back to the app polygon.

**Adding a city is one `REGIONS` entry.** Every stage takes `--region` and derives
its files from that entry, so two cities can be built side by side instead of one
overwriting the other's `poi_full.json`. The Bay Area was built before regions
existed, so its `suffix` is empty and its files keep their historical names; every
other region suffixes each working file (`poi_full.la.json`, `play_area.la.geojson`
…). Nothing else in the pipeline may hard-code a city, bbox, county or filename.
"""
import os, json, math

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# Per-region wiring. Paths are repo-relative; `suffix` names the working files
# each stage writes under scripts/ (see `work()`).
REGIONS = {
    "bay": {
        "label": "Bay Area",
        "suffix": "",
        "play": "src/data/play-area.geojson.json",
        "viz": "scripts/poi_merge_viz.js",
        "ledger": "scripts/poi_decisions.bay.json",
        "poi": "src/data/poi.json",
        # Admin areas the play area covers + the GeoNames dump to use, for the
        # address-only registries that can't be filtered by bbox.
        "counties": ["Alameda", "Contra Costa", "Marin", "Napa", "San Francisco",
                     "San Mateo", "Santa Clara", "Solano", "Sonoma"],
        "geonamesCountry": "US",
        # Its review map predates review counts (no per-place primaryType), so the
        # app data is built from its de-dup survivors instead. See build_poi_data.py.
        "applyFrom": "deduped",
        # Categories whose first manual pass is still unfinished: survivors seed
        # `pending` (not yet human-confirmed) instead of `keep`.
        "pendingCats": [],
        # --- map build (stations + geometry) ---
        "states": [("06", "California")],
        "stations": "src/data/stations.json",
        "transitLines": "src/data/transit-lines.geojson.json",
        "places": "src/data/places.geojson.json",
        "countiesGeo": "src/data/counties.geojson.json",
        "zctas": "src/data/zctas.geojson.json",
        # `agencies`/`airports` drive build_attributes.py, so they only exist on
        # the regions whose station file that script builds (LA's came from the
        # Metro GTFS import). Airport coordinates are each one's Google Maps pin
        # — the point the official rules measure from — not the aerodrome
        # centroid, and must match AIRPORT_SITES in src/data/regions.ts.
        "agencies": ["BART", "Caltrain", "VTA", "Muni"],
        "airports": {"SFO": (37.619083, -122.381597),
                     "OAK": (37.719016, -122.219595),
                     "SJC": (37.363510, -121.928648)},
        # Dense bay+ocean water (build_water_mask.py): legal city limits reach
        # into the bay, so each place is clipped back to the real shore.
        "waterMask": "scripts/bay_water_mask.geojson",
        "displayWater": "bay",
        # Farallon Islands: legally San Francisco, ~27 mi out in the Pacific.
        "islandLonCutoff": -122.6,
    },
    "dc": {
        "label": "Washington DC",
        "suffix": ".dc",
        "play": "src/data/dc.play-area.geojson.json",
        "viz": "scripts/poi_merge_viz.dc.js",
        "ledger": "scripts/poi_decisions.dc.json",
        "poi": "src/data/dc.poi.json",
        "counties": ["District of Columbia", "Arlington", "Alexandria city",
                     "Fairfax", "Loudoun", "Montgomery", "Prince George's"],
        "geonamesCountry": "US",
        "pendingCats": [],
        # --- map build (stations + geometry); see build_region_geo.py ---
        "states": [("11", "District of Columbia"), ("24", "Maryland"),
                   ("51", "Virginia")],
        "stations": "src/data/dc.stations.json",
        "transitLines": "src/data/dc.transit-lines.geojson.json",
        "places": "src/data/dc.places.geojson.json",
        "countiesGeo": "src/data/dc.counties.geojson.json",
        "zctas": "src/data/dc.zctas.geojson.json",
        # Multi-state map: state polygons back the "same state?" question and the
        # state-border measure feature. Single-state maps have no such file.
        "statesGeo": "src/data/dc.states.geojson.json",
        "agencies": ["Metrorail"],
        # BWI is kept even though it sits outside the play area: the app filters
        # airports to the ones inside the polygon (regions.ts), so carrying the
        # distance costs nothing if that boundary ever moves.
        "airports": {"DCA": (38.850108, -77.039176),
                     "IAD": (38.952248, -77.457889),
                     "BWI": (39.177414, -76.668394)},
        # Metrorail's counties run out to Purcellville, Damascus and the
        # Patuxent — thousands of square miles the trains never reach — so the
        # play-area curation is seeded by dropping every candidate place no
        # station comes within this distance of.
        "autoDropBeyondMi": 2.0,
    },
    "la": {
        "label": "LA Metro",
        "suffix": ".la",
        "play": "src/data/la.play-area.geojson.json",
        "viz": "scripts/poi_merge_viz.la.js",
        # while a city is under review its map is also served from the review
        # branch's preview site; that copy wins when present (see viz_path).
        "vizPreview": "public/poi-la-review/poi_merge_viz.js",
        "ledger": "scripts/poi_decisions.la.json",
        "poi": "src/data/la.poi.json",
        "counties": ["Los Angeles"],
        "geonamesCountry": "US",
        "pendingCats": [],
        # --- map build (stations + geometry) ---
        # LA's play area predates the opt-out curation: it is a hand-curated
        # city footprint corrected for rivers and the coast
        # (build_la_play_area.py), so build_play_area.py does not run for LA.
        "states": [("06", "California")],
        "stations": "src/data/la.stations.json",
        "transitLines": "src/data/la.transit-lines.geojson.json",
        "places": "src/data/la.places.geojson.json",
        "countiesGeo": "src/data/la.counties.geojson.json",
        "zctas": "src/data/la.zctas.geojson.json",
    },
}

# Every stage defaults to this region, so a whole session can be pointed at one
# city with `export POI_REGION=la` instead of passing --region to each script.
DEFAULT_REGION = os.environ.get("POI_REGION", "bay")


def repo_path(region, key):
    """Absolute path of a registry entry (`play` / `viz` / `ledger` / `poi`)."""
    return os.path.join(ROOT, REGIONS[region][key])


def work(region, name):
    """Absolute path of a working file under scripts/, region-suffixed.

    `work("la", "poi_full.json") -> scripts/poi_full.la.json`, while the Bay Area
    (suffix "") keeps `scripts/poi_full.json`.
    """
    stem, ext = os.path.splitext(name)
    return os.path.join(HERE, stem + REGIONS[region]["suffix"] + ext)


def add_region_arg(ap):
    """The one flag every stage of the pipeline shares."""
    ap.add_argument("--region", default=DEFAULT_REGION, choices=sorted(REGIONS),
                    help=f"which city to build (default {DEFAULT_REGION})")
    return ap


def region_from_argv(argv=None):
    """`--region x` for the stages that are plain top-level scripts, not CLIs."""
    import argparse
    ap = add_region_arg(argparse.ArgumentParser())
    known, _ = ap.parse_known_args(argv)
    return known.region

# --- the category rulebook (shared by discovery, curation and refresh) --------
# Discovery searches `includedTypes` (matches a place's whole `types` array) so
# icon-but-secondary-type places aren't missed; curation then keeps only places
# whose `primaryType` is the icon Google actually draws. Both halves live here so
# a refresh can never drift from the original pull.

PARK_TYPES = ["park", "national_park", "state_park", "dog_park",
              "garden", "botanical_garden"]

# (category key, includedTypes, tentacle radius in mi or None)
CATS = [
    ("museum", ["museum"], 1),
    ("library", ["library"], 1),
    ("movie_theater", ["movie_theater"], 1),
    ("hospital", ["hospital"], 1),
    ("zoo", ["zoo"], 15),
    ("aquarium", ["aquarium"], 15),
    ("amusement_park", ["amusement_park"], 15),
    ("park", PARK_TYPES, None),
    ("golf_course", ["golf_course"], None),
    ("consulate", ["embassy"], None),       # real consulates; honorary ones are
                                            # government_office, so excluded
    ("mountain", ["mountain_peak"], None),  # natural peaks (kept regardless of
                                            # review count -- see curation)
    ("stadium", ["stadium", "arena"], None),  # sports venues; curation keeps the
                                            # stadium/arena icon, then the reviewer
                                            # limits to professional-sports homes
]

LABEL = {
    "museum": "Museums", "library": "Libraries", "movie_theater": "Movie Theaters",
    "hospital": "Hospitals", "zoo": "Zoos", "aquarium": "Aquariums",
    "amusement_park": "Amusement Parks", "park": "Parks", "golf_course": "Golf Courses",
    "consulate": "Consulates", "mountain": "Mountains", "stadium": "Sports Stadiums",
}

MIN_REVIEWS = 5
# exempt from the >=5-review rule: mountains (natural features rarely have
# reviews) and stadiums (limited to a manual professional keep-list instead)
KEEP_ALL = {"mountain", "stadium"}

ALLOW = {
    "museum": {"museum", "art_museum", "history_museum", "art_gallery"},
    "library": {"library"},
    "movie_theater": {"movie_theater"},
    "hospital": {"hospital", "general_hospital", "medical_center"},
    "zoo": {"zoo"},
    "aquarium": {"aquarium"},
    "amusement_park": {"amusement_park", "water_park", "amusement_center"},
    "park": {"park", "city_park", "national_park", "state_park", "dog_park",
             "garden", "botanical_garden", "nature_preserve"},
    "golf_course": {"golf_course"},   # + club rescue, see keep_by_type()
    "consulate": {"embassy"},         # honorary consulates are
                                      # local_government_office -> excluded
    "mountain": {"mountain_peak"},
    "stadium": {"stadium", "arena"},  # the sports-venue icon; reviewer then
                                      # limits to professional-sports home venues
}
# real golf/country clubs Google mis-primaries (e.g. SF Golf Club = sports_club)
GOLF_CLUB_PRIMARIES = {"sports_club", "association_or_organization", "country_club"}
GOLF_NAME_EXCLUDE = ("driving range", "topgolf", "top golf", "mini golf",
                     "miniature golf", "disc golf", "golf galaxy", "indoor golf")


def keep_by_type(key, p):
    """Does place `p` carry category `key`'s Google icon? (+ the golf rescue)"""
    pt = p.get("primaryType")
    name = (p.get("name") or "").lower()
    if key == "golf_course":
        if any(x in name for x in GOLF_NAME_EXCLUDE):
            return False
        if pt == "golf_course":
            return True
        return pt in GOLF_CLUB_PRIMARIES and ("golf" in name or "country club" in name)
    allow = ALLOW.get(key)
    return True if allow is None else pt in allow


def load_play(region=None, path=None):
    """A region's discovery polygon: its 150 m-buffered city union if built, else
    the app polygon (`--region` picks the city; `path` overrides both)."""
    if path is None:
        region = region or DEFAULT_REGION
        buf = work(region, "play_area_buffered.geojson")
        path = buf if os.path.exists(buf) else repo_path(region, "play")
    g = json.load(open(path))
    # normalize a bare Feature (build_play_area's output) to a FeatureCollection
    if g.get("type") == "Feature":
        return {"type": "FeatureCollection", "features": [g]}
    return g


def _rings(geom):
    """All linear rings (outer + holes) as lists of (lon,lat)."""
    t, c = geom["type"], geom["coordinates"]
    if t == "Polygon":
        return list(c)
    if t == "MultiPolygon":
        return [ring for poly in c for ring in poly]
    return []


def all_rings(play):
    out = []
    for f in play["features"]:
        out += _rings(f["geometry"])
    return out


def bbox(play):
    """(lat0, lat1, lon0, lon1) over every vertex."""
    xs, ys = [], []
    for ring in all_rings(play):
        for lon, lat in ring:
            xs.append(lon); ys.append(lat)
    return min(ys), max(ys), min(xs), max(xs)


def bbox_swne(play):
    """(S, W, N, E) — the order Overpass bbox filters want."""
    lat0, lat1, lon0, lon1 = bbox(play)
    return lat0, lon0, lat1, lon1


def m2_per_deg2(play):
    """Square metres per square degree at this play area's mid latitude.

    Footprint sizes (park area, campus radius) are computed in degrees and must be
    scaled by the *city's* latitude: baking in one city's cosine mis-sizes every
    other city's parks (the Bay Area and LA differ by ~5%).
    """
    lat0, lat1, _, _ = bbox(play)
    return (111320.0 * math.cos(math.radians((lat0 + lat1) / 2))) * 110574.0


def make_in_play(play, tolerance_m=0.0):
    """Return in_play(lon, lat): even-odd ray cast over outer rings, minus holes.

    `tolerance_m` also accepts a point that far *outside* the boundary: the play
    polygon is a simplified city union, so a pier or a park on the line can sit a
    few metres out (the discovery pass buffers by 150 m for the same reason).
    """
    polys = []
    for f in play["features"]:
        for ring in _rings(f["geometry"]):
            polys.append(ring)

    def _in_ring(lon, lat, ring):
        inside = False
        n = len(ring)
        for i in range(n):
            x1, y1 = ring[i]
            x2, y2 = ring[(i + 1) % n]
            if ((y1 > lat) != (y2 > lat)) and \
               (lon < (x2 - x1) * (lat - y1) / (y2 - y1) + x1):
                inside = not inside
        return inside

    # treat every ring independently with even-odd union (holes flip back out).
    def in_play(lon, lat):
        c = 0
        for ring in polys:
            if _in_ring(lon, lat, ring):
                c += 1
        if c % 2 == 1:
            return True
        return tolerance_m > 0 and edge_distance_m(polys, lon, lat) <= tolerance_m
    return in_play


def edge_distance_m(rings, lon, lat):
    """Metres from (lon,lat) to the nearest boundary segment of `rings`."""
    best, coslat = float("inf"), math.cos(math.radians(lat))
    for ring in rings:
        for i in range(len(ring)):
            x1, y1 = ring[i]
            x2, y2 = ring[(i + 1) % len(ring)]
            ax, ay = (x1 - lon) * 111320 * coslat, (y1 - lat) * 111320
            bx, by = (x2 - lon) * 111320 * coslat, (y2 - lat) * 111320
            dx, dy = bx - ax, by - ay
            t = 0.0 if dx == dy == 0 else max(0, min(1, -(ax * dx + ay * dy) / (dx * dx + dy * dy)))
            best = min(best, math.hypot(ax + t * dx, ay + t * dy))
    return best
