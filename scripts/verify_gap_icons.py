"""Icon-check the free OSM gap candidates against Google — CHEAP path:
one searchText per candidate with a field mask that OMITS review fields (so it
bills at the non-review SKU), location-biased to the OSM coordinate. We keep a
candidate only if Google returns a place at ~that spot whose primaryType is the
category's icon (same allowlist as curation). Reviews are NOT fetched — the human
checks those by hand afterwards.

Safety: hard MAX_CALLS cap, and every result is cached to disk so a restart never
re-spends. Reads osm_gap_candidates.json; writes poi_gap_verified.json (+ cache).
"""
import os, sys, json, math, time, urllib.request, urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
KEY = os.environ["GOOGLE_PLACES_API_KEY"]
URL = "https://places.googleapis.com/v1/places:searchText"
# NO places.rating / places.userRatingCount -> cheaper non-review SKU
FIELDS = ",".join(["places.id", "places.displayName", "places.location",
                   "places.primaryType", "places.types"])
MAX_CALLS = 320          # hard cap; 260 candidates + buffer. Stops dead if hit.
MATCH_M = 350.0          # a Google hit counts as "the same place" within this

# same icon allowlist + golf rescue as curate_places_poi.py
ALLOW = {
    "museum": {"museum", "art_museum", "history_museum", "art_gallery"},
    "library": {"library"},
    "movie_theater": {"movie_theater"},
    "hospital": {"hospital", "general_hospital", "medical_center"},
    "zoo": {"zoo"},
    "aquarium": {"aquarium"},
    "amusement_park": {"amusement_park", "water_park", "amusement_center"},
    "golf_course": {"golf_course"},
    "consulate": {"embassy"},
    "mountain": {"mountain_peak"},
}
GOLF_CLUB_PRIMARIES = {"sports_club", "association_or_organization", "country_club"}
GOLF_NAME_EXCLUDE = ("driving range", "topgolf", "top golf", "mini golf",
                     "miniature golf", "disc golf", "golf galaxy", "indoor golf")


def keep_by_type(key, pt, name):
    name = (name or "").lower()
    if key == "golf_course":
        if any(x in name for x in GOLF_NAME_EXCLUDE):
            return False
        if pt == "golf_course":
            return True
        return pt in GOLF_CLUB_PRIMARIES and ("golf" in name or "country club" in name)
    return pt in ALLOW.get(key, set())


def km(a, b, c, d):
    return math.hypot((a - c) * 111000.0, (b - d) * 88000.0)


calls = 0
def search_text(name, lat, lon):
    global calls
    if calls >= MAX_CALLS:
        sys.exit(f"hit MAX_CALLS={MAX_CALLS}; stopping to avoid overspend")
    body = json.dumps({
        "textQuery": name,
        "locationBias": {"circle": {"center": {"latitude": lat, "longitude": lon},
                                    "radius": 800.0}},
        "maxResultCount": 5,
    }).encode()
    req = urllib.request.Request(URL, data=body, headers={
        "Content-Type": "application/json", "X-Goog-Api-Key": KEY,
        "X-Goog-FieldMask": FIELDS})
    for attempt in range(6):
        try:
            calls += 1
            with urllib.request.urlopen(req, timeout=60) as r:
                time.sleep(0.05)
                return json.load(r).get("places", [])
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 503):
                time.sleep(2 * (attempt + 1)); continue
            sys.exit(f"HTTP {e.code}: {e.read().decode()[:200]}")
        except Exception:
            time.sleep(2 * (attempt + 1))
    return []


def main():
    cands = json.load(open(os.path.join(HERE, "osm_gap_candidates.json")))
    cache_path = os.path.join(HERE, "poi_gap_cache.json")
    cache = json.load(open(cache_path)) if os.path.exists(cache_path) else {}

    verified = {}
    for key, items in cands.items():
        kept = []
        for c in items:
            ck = f"{key}|{c['name']}|{round(c['lat'],4)},{round(c['lon'],4)}"
            if ck not in cache:
                hits = search_text(c["name"], c["lat"], c["lon"])
                best = None
                for h in hits:
                    loc = h["location"]
                    d = km(c["lat"], c["lon"], loc["latitude"], loc["longitude"])
                    if d <= MATCH_M and (best is None or d < best[0]):
                        best = (d, h)
                cache[ck] = None if best is None else {
                    "id": best[1]["id"],
                    "name": best[1]["displayName"]["text"],
                    "primaryType": best[1].get("primaryType"),
                    "types": best[1].get("types", []),
                    "lat": best[1]["location"]["latitude"],
                    "lon": best[1]["location"]["longitude"],
                }
                json.dump(cache, open(cache_path, "w"), indent=1)
            hit = cache[ck]
            if hit and keep_by_type(key, hit["primaryType"], hit["name"]):
                kept.append({**hit, "userRatingCount": None, "source": "osm_backfill"})
        verified[key] = kept
        print(f"{key:15s} candidates={len(items):4d} icon-verified={len(kept):4d}")

    # de-dup verified by place id within category
    for key in verified:
        seen, uniq = set(), []
        for p in verified[key]:
            if p["id"] not in seen:
                seen.add(p["id"]); uniq.append(p)
        verified[key] = uniq

    json.dump(verified, open(os.path.join(HERE, "poi_gap_verified.json"), "w"), indent=1)
    print(f"\ntotal API calls: {calls}")
    print("verified per category:",
          {k: len(v) for k, v in verified.items() if v})
    print("wrote poi_gap_verified.json")


if __name__ == "__main__":
    main()
