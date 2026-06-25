"""Shared, city-agnostic geometry helpers for the POI pipeline.

The ONLY per-city input is the play-area polygon
(`../src/data/play-area.geojson.json`). Bounding box, point-in-polygon and the
Overpass area clause all derive from it, so no script hard-codes a city, bbox or
county list.
"""
import os, json

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PLAY = os.path.join(HERE, "..", "src", "data", "play-area.geojson.json")


def load_play(path=DEFAULT_PLAY):
    return json.load(open(path))


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
