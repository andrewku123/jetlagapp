"""Shared, city-agnostic geometry helpers for the POI pipeline.

The per-city input is the set of eligible stations; `build_play_area.py` turns it
into the play-area polygons. For *discovery/recall* (bbox, point-in-polygon,
Overpass area) we use the 150 m-buffered city union (`play_area_buffered.geojson`)
so waterfront/pier places just off the land polygon are still found; the precise
strict clip (raw for parks/mountains, buffered for the rest) happens later in
`dedup_poi.py`. If the buffered file is absent we fall back to the app polygon
(`../src/data/play-area.geojson.json`). No script hard-codes a city/bbox/county.
"""
import os, json

HERE = os.path.dirname(os.path.abspath(__file__))
BUFFERED_PLAY = os.path.join(HERE, "play_area_buffered.geojson")
APP_PLAY = os.path.join(HERE, "..", "src", "data", "play-area.geojson.json")
DEFAULT_PLAY = BUFFERED_PLAY if os.path.exists(BUFFERED_PLAY) else APP_PLAY

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


def load_play(path=DEFAULT_PLAY):
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


def make_in_play(play):
    """Return in_play(lon, lat): even-odd ray cast over outer rings, minus holes."""
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
        return c % 2 == 1
    return in_play
