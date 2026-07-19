#!/usr/bin/env python3
"""Fetch OSM river/wash channel polygons within the LA play-area bbox.

Rivers and flood-control channels (LA River, Rio Hondo, San Gabriel River,
Ballona Creek, Tujunga Wash, ...) are cut out of the Census "place" polygons as
unincorporated land, so the "Matching -> city" shading shows ugly thin gaps
running along them. build_la_places.py folds each river's area into the cities
on its banks so the shading is gap-free; this module supplies those polygons.

Run standalone to refresh the cache, or import `load(cache_path)` from the build.
"""
import json, os, sys, time, urllib.request, urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "_cache", "la_rivers.geojson.json")
S, W, N, E = 33.70, -118.67, 34.34, -117.71

# river / canal / stream channel polygons (areas) — NOT open sea or lakes:
QUERY = f"""
[out:json][timeout:180];
(
  way["natural"="water"]["water"~"river|canal|stream"]({S},{W},{N},{E});
  relation["natural"="water"]["water"~"river|canal|stream"]({S},{W},{N},{E});
  way["waterway"="riverbank"]({S},{W},{N},{E});
  relation["waterway"="riverbank"]({S},{W},{N},{E});
);
out geom;
"""

ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]


def _overpass():
    last = None
    for ep in ENDPOINTS:
        for attempt in range(3):
            try:
                print(f"POST {ep} (try {attempt+1})", file=sys.stderr)
                req = urllib.request.Request(ep, data=("data=" + QUERY).encode(),
                                             headers={"User-Agent": "jetlag-la-rivers/1"})
                return json.load(urllib.request.urlopen(req, timeout=200))
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                last = e
                print("  failed:", e, file=sys.stderr)
                time.sleep(5)
    raise SystemExit(f"all Overpass endpoints failed: {last}")


def _ring(coords):
    r = [[p["lon"], p["lat"]] for p in coords]
    if r and r[0] != r[-1]:
        r.append(r[0])
    return r


def _to_features(data):
    feats = []
    for el in data["elements"]:
        if el["type"] == "way" and "geometry" in el:
            rr = _ring(el["geometry"])
            if len(rr) >= 4:
                feats.append({"type": "Feature", "properties": {"id": el["id"]},
                              "geometry": {"type": "Polygon", "coordinates": [rr]}})
        elif el["type"] == "relation" and "members" in el:
            outers, inners = [], []
            for m in el["members"]:
                if "geometry" not in m:
                    continue
                rr = _ring(m["geometry"])
                if len(rr) < 4:
                    continue
                (outers if m.get("role") == "outer" else inners).append(rr)
            for o in outers:
                feats.append({"type": "Feature", "properties": {"id": el["id"]},
                              "geometry": {"type": "Polygon", "coordinates": [o] + inners}})
    return {"type": "FeatureCollection", "features": feats}


def refresh(cache_path=CACHE):
    fc = _to_features(_overpass())
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    json.dump(fc, open(cache_path, "w"))
    print(f"wrote {cache_path} — {len(fc['features'])} river polygons")
    return fc


def load(cache_path=CACHE):
    """Return the river FeatureCollection, fetching + caching it if absent."""
    if os.path.exists(cache_path):
        return json.load(open(cache_path))
    return refresh(cache_path)


if __name__ == "__main__":
    refresh()
