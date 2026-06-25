#!/usr/bin/env python3
"""Fetch OSM footprint polygons for each POI category over the play-area bbox.

Used by the de-dup pass: pins that fall inside the SAME OSM footprint (one
hospital campus, one park) collapse to a single POI. Output per category:
osm_polys_<cat>.json = [{id, name, wkt}, ...]   (wkt = (multi)polygon)
"""
import os, json, time, sys
import requests
from shapely.geometry import LineString, Polygon, MultiPolygon
from shapely.ops import polygonize, unary_union
import poi_geo

HERE = os.path.dirname(os.path.abspath(__file__))
BBOX = poi_geo.bbox_swne(poi_geo.load_play())   # S,W,N,E from the play polygon
UA = {"User-Agent": "jetlag-poi/1.0 (dedup footprints)"}
ENDPOINTS = ["https://overpass-api.de/api/interpreter",
             "https://overpass.kumi.systems/api/interpreter"]

# category -> list of OSM tag filters (key=value)
TAGS = {
    "hospital": ["amenity=hospital"],
    "park": ["leisure=park", "leisure=garden", "leisure=nature_reserve",
             "boundary=protected_area", "leisure=dog_park"],
    "museum": ["tourism=museum"],
    "library": ["amenity=library"],
    "movie_theater": ["amenity=cinema"],
    "zoo": ["tourism=zoo"],
    "aquarium": ["tourism=aquarium"],
    "amusement_park": ["tourism=theme_park", "leisure=water_park"],
    "golf_course": ["leisure=golf_course"],
}


def query(cat):
    s, w, n, e = BBOX
    parts = []
    for t in TAGS[cat]:
        k, v = t.split("=")
        parts.append(f'way["{k}"="{v}"]({s},{w},{n},{e});')
        parts.append(f'relation["{k}"="{v}"]({s},{w},{n},{e});')
    return f"[out:json][timeout:300];({''.join(parts)});out geom;"


def fetch(cat):
    data = query(cat)
    last = None
    for ep in ENDPOINTS:
        for attempt in range(3):
            try:
                r = requests.post(ep, data={"data": data}, headers=UA, timeout=320)
                if r.status_code == 200:
                    return r.json()
                last = f"{ep} -> {r.status_code}"
            except Exception as ex:
                last = f"{ep} -> {ex}"
            time.sleep(5)
    raise RuntimeError(f"overpass failed: {last}")


def to_polys(js):
    feats = []
    for el in js.get("elements", []):
        name = (el.get("tags") or {}).get("name", "")
        geom = None
        if el["type"] == "way" and el.get("geometry"):
            pts = [(p["lon"], p["lat"]) for p in el["geometry"]]
            if len(pts) >= 4 and pts[0] == pts[-1]:
                try:
                    geom = Polygon(pts)
                except Exception:
                    geom = None
        elif el["type"] == "relation":
            lines = []
            for m in el.get("members", []):
                if m.get("type") == "way" and m.get("geometry") and \
                        m.get("role") in ("outer", "", None):
                    pts = [(p["lon"], p["lat"]) for p in m["geometry"]]
                    if len(pts) >= 2:
                        lines.append(LineString(pts))
            if lines:
                try:
                    polys = list(polygonize(unary_union(lines)))
                    if polys:
                        geom = unary_union(polys)
                except Exception:
                    geom = None
        if geom is not None and not geom.is_empty:
            if not geom.is_valid:
                geom = geom.buffer(0)
            if not geom.is_empty:
                feats.append({"id": f'{el["type"]}/{el["id"]}',
                              "name": name, "wkt": geom.wkt})
    return feats


def main():
    cats = sys.argv[1:] or list(TAGS)
    for cat in cats:
        print(f"fetching {cat} ...", flush=True)
        js = fetch(cat)
        feats = to_polys(js)
        json.dump(feats, open(os.path.join(HERE, f"osm_polys_{cat}.json"), "w"))
        print(f"  {cat}: {len(feats)} polygons", flush=True)
        time.sleep(3)


if __name__ == "__main__":
    main()
