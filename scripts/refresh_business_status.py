#!/usr/bin/env python3
"""Verify backfilled POIs against Google: `businessStatus` and review count.

Why this exists: the icon+review pull (poi_full.json) already carries both, but
the backfilled pins -- authoritative IMLS museums/libraries, State Department
embassies, the OSM gap recall -- are injected straight into poi_curated.json from
external sources and so arrive with neither. Unchecked status let closed places
(Madame Tussauds, Habitot, Carquinez Toy Train) slip past the audit; unchecked
review counts let pins the >=5-review rule should have cut stay on the map, which
is worse, because the rule is the whole basis of "is this a real place a hider
could pick". A registry listing says a place exists, not that it qualifies.

So for every pin with a Google `id` that is missing either field this queries
Place Details for exactly the missing ones, caches by place_id (both rarely
change, so reruns are ~free), writes them back, and then **drops any pin that now
fails the review rule** -- the same >=5 gate curation applies to the sweep, with
the same mountain/stadium exemptions. de-dup then drops CLOSED_PERMANENTLY.

Run AFTER the backfills (apply_gap_backfill.py / authoritative_candidates.py) and
BEFORE dedup_poi.py.

Env:
  GOOGLE_PLACES_API_KEY   required
  POI_REFRESH_ALL=1       re-query every pin (not just those missing a field),
                          to catch places that closed since the last pull.

Reads/writes: poi_curated.json
Cache:        poi_bizstatus_cache.json   (place_id -> {status, reviews})
"""
import os, json, time, urllib.request, urllib.error

import poi_geo

HERE = os.path.dirname(os.path.abspath(__file__))
REGION = poi_geo.region_from_argv()
CUR = poi_geo.work(REGION, "poi_curated.json")
CACHE = poi_geo.work(REGION, "poi_bizstatus_cache.json")
KEY = os.environ["GOOGLE_PLACES_API_KEY"]
REFRESH_ALL = os.environ.get("POI_REFRESH_ALL", "").lower() in ("1", "true", "yes")


def fetch(pid):
    """-> {'status': ..., 'reviews': ...}; a 404 means the id is dead, i.e. closed."""
    url = (f"https://places.googleapis.com/v1/places/{pid}"
           f"?fields=businessStatus,userRatingCount&key={KEY}")
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=20) as r:
                d = json.load(r)
                return {"status": d.get("businessStatus", "OPERATIONAL"),
                        "reviews": d.get("userRatingCount", 0)}
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return {"status": "CLOSED_PERMANENTLY", "reviews": None}
            time.sleep(1 + attempt)
        except Exception:
            time.sleep(1 + attempt)
    return None  # transient failure: leave the pin untouched


def cached(cache, pid):
    v = cache.get(pid)
    if isinstance(v, str):                 # pre-review-count cache: status only
        return {"status": v, "reviews": None}
    return v


def main():
    data = json.load(open(CUR))
    cache = json.load(open(CACHE)) if os.path.exists(CACHE) else {}
    queried = updated = 0
    for key, blk in data.items():
        for p in blk.get("places", []):
            pid = p.get("id")
            if not pid:
                continue
            want_status = p.get("businessStatus") is None
            want_reviews = p.get("userRatingCount") is None
            if not (want_status or want_reviews or REFRESH_ALL):
                continue
            hit = cached(cache, pid)
            if hit is None or REFRESH_ALL or (want_reviews and hit["reviews"] is None):
                hit = fetch(pid)
                queried += 1
                if hit is None:
                    continue
                cache[pid] = hit
            if hit["status"] and hit["status"] != p.get("businessStatus"):
                p["businessStatus"] = hit["status"]
                updated += 1
            if hit["reviews"] is not None and p.get("userRatingCount") is None:
                p["userRatingCount"] = hit["reviews"]
                updated += 1

    # the review rule, applied to the pins that never went through curation
    cut = {}
    for key, blk in data.items():
        if key in poi_geo.KEEP_ALL:
            continue
        keep = []
        for p in blk.get("places", []):
            n = p.get("userRatingCount")
            if p.get("source") and n is not None and n < poi_geo.MIN_REVIEWS:
                cut.setdefault(key, []).append(f"{p['name']} ({n})")
            else:
                keep.append(p)
        blk["places"] = keep

    json.dump(cache, open(CACHE, "w"), indent=2)
    json.dump(data, open(CUR, "w"), indent=2, ensure_ascii=False)
    closed = sum(1 for blk in data.values() for p in blk.get("places", [])
                 if p.get("businessStatus") in ("CLOSED_PERMANENTLY", "CLOSED_TEMPORARILY"))
    print(f"queried {queried} place(s), wrote {updated} field update(s); "
          f"{closed} pin(s) now flagged closed (auto-dropped at dedup).")
    if cut:
        print(f"cut {sum(len(v) for v in cut.values())} backfilled pin(s) under "
              f"{poi_geo.MIN_REVIEWS} reviews:")
        for key, names in sorted(cut.items()):
            print(f"  {key:15} " + "; ".join(names))


if __name__ == "__main__":
    main()
