#!/usr/bin/env python3
"""Refresh each POI's Google `businessStatus` so closed places auto-drop.

Why this exists: the icon+review pull (poi_full.json) already carries
`businessStatus`, but the backfilled pins -- authoritative IMLS museums/libraries
and the OSM gap recall -- are injected straight into poi_curated.json from
external sources and so arrive with `businessStatus: None`. They never had their
Google status checked, which let permanently/temporarily-closed places (Madame
Tussauds, Habitot, Carquinez Toy Train, etc.) slip past the audit.

This step queries Place Details (just the `businessStatus` field -- the cheapest
SKU) for every pin that has a Google `id` but no status yet, caches the answer by
place_id (statuses rarely change, so the cache makes reruns ~free), and writes it
back into poi_curated.json. de-dup then drops CLOSED_PERMANENTLY / CLOSED_TEMPORARILY.

Run AFTER the backfills (apply_gap_backfill.py / authoritative_candidates.py) and
BEFORE dedup_poi.py.

Env:
  GOOGLE_PLACES_API_KEY   required
  POI_REFRESH_ALL=1       re-query every pin (not just those missing a status),
                          to catch places that closed since the last pull.

Reads/writes: poi_curated.json
Cache:        poi_bizstatus_cache.json   (place_id -> businessStatus)
"""
import os, json, time, urllib.request, urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
CUR = os.path.join(HERE, "poi_curated.json")
CACHE = os.path.join(HERE, "poi_bizstatus_cache.json")
KEY = os.environ["GOOGLE_PLACES_API_KEY"]
REFRESH_ALL = os.environ.get("POI_REFRESH_ALL", "").lower() in ("1", "true", "yes")


def fetch_status(pid):
    url = (f"https://places.googleapis.com/v1/places/{pid}"
           f"?fields=businessStatus&key={KEY}")
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=20) as r:
                return json.load(r).get("businessStatus", "OPERATIONAL")
        except urllib.error.HTTPError as e:
            # 404/NOT_FOUND => the place id no longer resolves: treat as closed.
            if e.code == 404:
                return "CLOSED_PERMANENTLY"
            time.sleep(1 + attempt)
        except Exception:
            time.sleep(1 + attempt)
    return None  # transient failure: leave status untouched


def main():
    data = json.load(open(CUR))
    cache = json.load(open(CACHE)) if os.path.exists(CACHE) else {}
    queried = updated = 0
    for key, blk in data.items():
        for p in blk.get("places", []):
            pid = p.get("id")
            if not pid:
                continue
            have = p.get("businessStatus")
            if have and not REFRESH_ALL:
                continue
            if pid in cache and not REFRESH_ALL:
                st = cache[pid]
            else:
                st = fetch_status(pid)
                queried += 1
                if st is not None:
                    cache[pid] = st
            if st is not None and st != have:
                p["businessStatus"] = st
                updated += 1
    json.dump(cache, open(CACHE, "w"), indent=2)
    json.dump(data, open(CUR, "w"), indent=2, ensure_ascii=False)
    closed = sum(1 for blk in data.values() for p in blk.get("places", [])
                 if p.get("businessStatus") in ("CLOSED_PERMANENTLY", "CLOSED_TEMPORARILY"))
    print(f"queried {queried} place(s), wrote {updated} status update(s); "
          f"{closed} pin(s) now flagged closed (auto-dropped at dedup).")


if __name__ == "__main__":
    main()
