"""Fold the icon-verified OSM gap backfill (poi_gap_verified.json) into the
curated set (poi_curated.json) so the de-dup + review map pick them up. Backfill
places have no review count (userRatingCount=None, source='osm_backfill') -- the
human applies the >=5-review rule to them by hand. Idempotent: skips ids already
present and any backfill pin within 60m of an existing same-named place.

Input file + source tag are configurable so the same step folds in OSM gaps and
authoritative-list backfills:
  IN_FILE     (default poi_gap_verified.json)
  SOURCE_TAG  (default osm_backfill)
"""
import os, json, math

HERE = os.path.dirname(os.path.abspath(__file__))
IN_FILE = os.environ.get("IN_FILE", "poi_gap_verified.json")
SOURCE_TAG = os.environ.get("SOURCE_TAG", "osm_backfill")
cur_path = os.path.join(HERE, "poi_curated.json")
curated = json.load(open(cur_path))
verified = json.load(open(os.path.join(HERE, IN_FILE)))


def m(a, b, c, d):
    return math.hypot((a - c) * 111000.0, (b - d) * 88000.0)


added = {}
for key, items in verified.items():
    blk = curated.setdefault(key, {"count": 0, "places": []})
    have_ids = {p.get("id") for p in blk["places"]}
    n = 0
    for p in items:
        if p["id"] in have_ids:
            continue
        if any(m(p["lat"], p["lon"], q["lat"], q["lon"]) < 60
               and p["name"].lower() == (q["name"] or "").lower()
               for q in blk["places"]):
            continue
        blk["places"].append({
            "id": p["id"], "name": p["name"], "primaryType": p["primaryType"],
            "types": p.get("types", []), "address": "", "rating": None,
            "userRatingCount": None, "businessStatus": None,
            "lat": p["lat"], "lon": p["lon"], "source": p.get("source", SOURCE_TAG),
        })
        n += 1
    blk["count"] = len(blk["places"])
    if n:
        added[key] = n

json.dump(curated, open(cur_path, "w"), indent=1)
print("added per category:", added, "| total:", sum(added.values()))
