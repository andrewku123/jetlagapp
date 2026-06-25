"""OPTION B (survivors-only review top-up). Only run this when you want Google to
do the >=5-review check instead of doing it by hand.

After de-dup, fetch the review count for ONLY the de-duped survivors (the smallest
possible set) via Place Details by ID, then drop anything under MIN_REVIEWS.
Mountains are kept regardless (rulebook). This isolates the one fact only Google
can give us (review count) to survivors, so you pay once and never hand-check
ratings -- you still confirm merges on the review map.

Cost: one Place Details call per survivor. userRatingCount is an Enterprise-tier
field (~$20/1k), so the Bay Area's ~3.3k survivors ~= $60-70 one-time. Hard
MAX_CALLS cap + on-disk cache so a restart never re-spends. Set the console quota
cap + budget alert first.

Input  : poi_deduped.json   (the survivor set)
Output : poi_deduped_reviewed.json + review_topup_cache.json
"""
import os, sys, json, time, urllib.request, urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
KEY = os.environ["GOOGLE_PLACES_API_KEY"]
MIN_REVIEWS = 5
KEEP_ALL = {"mountain"}          # kept regardless of review count
MAX_CALLS = 4000                 # hard stop; raise only if a city has more pins


def details(pid):
    req = urllib.request.Request(
        f"https://places.googleapis.com/v1/places/{pid}",
        headers={"X-Goog-Api-Key": KEY,
                 "X-Goog-FieldMask": "id,userRatingCount,businessStatus"})
    for attempt in range(6):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                time.sleep(0.05)
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 503):
                time.sleep(2 * (attempt + 1)); continue
            if e.code == 404:
                return {}
            sys.exit(f"HTTP {e.code}: {e.read().decode()[:200]}")
        except Exception:
            time.sleep(2 * (attempt + 1))
    return {}


def main():
    data = json.load(open(os.path.join(HERE, "poi_deduped.json")))
    cache_path = os.path.join(HERE, "review_topup_cache.json")
    cache = json.load(open(cache_path)) if os.path.exists(cache_path) else {}
    calls = 0

    out = {}
    for key, blk in data.items():
        places = blk["places"] if isinstance(blk, dict) else blk
        kept = []
        for p in places:
            if key in KEEP_ALL:
                kept.append(p); continue
            # already have a real count from an earlier enterprise pull? trust it.
            rc = p.get("userRatingCount")
            pid = p.get("id")
            if rc is None and pid:
                if pid not in cache:
                    if calls >= MAX_CALLS:
                        sys.exit(f"hit MAX_CALLS={MAX_CALLS}; stopping")
                    calls += 1
                    d = details(pid)
                    cache[pid] = d.get("userRatingCount")
                    json.dump(cache, open(cache_path, "w"))
                rc = cache[pid]
            if rc is not None and rc >= MIN_REVIEWS:
                p = {**p, "userRatingCount": rc}
                kept.append(p)
        out[key] = {"count": len(kept), "places": kept} if isinstance(blk, dict) else kept
        print(f"{key:15s} survivors={len(places):5d} kept(>= {MIN_REVIEWS})={len(kept):5d}")

    json.dump(out, open(os.path.join(HERE, "poi_deduped_reviewed.json"), "w"), indent=1)
    print(f"\ntotal Place Details calls: {calls}")
    print("wrote poi_deduped_reviewed.json")


if __name__ == "__main__":
    main()
