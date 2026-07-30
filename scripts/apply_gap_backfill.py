"""Fold the icon-verified OSM gap backfill (poi_gap_verified.json) into the
curated set (poi_curated.json) so the de-dup + review map pick them up. Backfill
places have no review count of their own (the icon check buys the cheap non-review
SKU), so the >=5-review rule is applied by hand on the review map. Idempotent:
skips ids already present and any backfill pin within 60m of an existing
same-named place.

**The sweep's verdict wins.** A backfill candidate is meant to be a place the paid
sweep *missed*; when the sweep did return that place id and it failed the review
rule, re-adding it silently undoes curation (DC put a 0-review "museum" back on the
map that way). So a candidate whose review count the sweep already knows is gated
on that count, and the known count is stamped onto the pin so the map shows "0
reviews" instead of nothing. Registry backfills are exempt: a State Department
embassy or an IMLS-listed museum is real whether or not Google has reviews for it.
Earlier runs' pins are re-gated too, so the prune is just this rule applied again.

Input file + source tag are configurable so the same step folds in OSM gaps and
authoritative-list backfills:
  IN_FILE     (default poi_gap_verified.json)
  SOURCE_TAG  (default osm_backfill)
  GATED       1 / 0 to force the review gate on or off (default: off for
              registry sources, on for everything else)
"""
import os, json, math

import poi_geo

HERE = os.path.dirname(os.path.abspath(__file__))
REGION = poi_geo.region_from_argv()
IN_FILE = os.environ.get("IN_FILE", "poi_gap_verified.json")
SOURCE_TAG = os.environ.get("SOURCE_TAG", "osm_backfill")
REGISTRY_TAGS = {"authoritative"}
GATED = os.environ.get("GATED")
GATED = SOURCE_TAG not in REGISTRY_TAGS if GATED is None else GATED == "1"
cur_path = poi_geo.work(REGION, "poi_curated.json")
curated = json.load(open(cur_path))
verified = json.load(open(poi_geo.work(REGION, IN_FILE)))

# what the paid sweep saw: place id -> review count (None if it never returned it)
swept = {}
for blk in json.load(open(poi_geo.work(REGION, "poi_full.json"))).values():
    if isinstance(blk, dict):
        for p in blk.get("places", []):
            swept[p.get("id")] = p.get("userRatingCount")


def m(a, b, c, d):
    return math.hypot((a - c) * 111000.0, (b - d) * 88000.0)


def gated_out(cat, pid):
    """True if the sweep already scored this place below the review rule."""
    if not GATED or cat in poi_geo.KEEP_ALL:
        return False
    n = swept.get(pid)
    return n is not None and n < poi_geo.MIN_REVIEWS


added, gated, pruned = {}, {}, {}
for key, items in verified.items():
    blk = curated.setdefault(key, {"count": 0, "places": []})

    n_pre = len(blk["places"])
    blk["places"] = [p for p in blk["places"]
                     if p.get("source") != SOURCE_TAG or not gated_out(key, p.get("id"))]
    if n_pre != len(blk["places"]):
        pruned[key] = n_pre - len(blk["places"])

    have_ids = {p.get("id") for p in blk["places"]}
    n = 0
    for p in items:
        if p["id"] in have_ids:
            continue
        if gated_out(key, p["id"]):
            gated[key] = gated.get(key, 0) + 1
            continue
        if any(m(p["lat"], p["lon"], q["lat"], q["lon"]) < 60
               and p["name"].lower() == (q["name"] or "").lower()
               for q in blk["places"]):
            continue
        blk["places"].append({
            "id": p["id"], "name": p["name"], "primaryType": p["primaryType"],
            "types": p.get("types", []), "address": "", "rating": None,
            "userRatingCount": swept.get(p["id"]), "businessStatus": None,
            "lat": p["lat"], "lon": p["lon"], "source": p.get("source", SOURCE_TAG),
        })
        n += 1
    blk["count"] = len(blk["places"])
    if n:
        added[key] = n

json.dump(curated, open(cur_path, "w"), indent=1)
print("added per category:", added, "| total:", sum(added.values()))
if GATED:
    print(f"under the >={poi_geo.MIN_REVIEWS}-review rule (the sweep's own count) — "
          f"skipped: {gated or '{}'} | pruned from earlier runs: {pruned or '{}'}")
