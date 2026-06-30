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
