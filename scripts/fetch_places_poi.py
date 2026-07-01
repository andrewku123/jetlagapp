#!/usr/bin/env python3
"""Gather all POI categories used by Tentacles + Matching + Measuring over the
full 5-county play area (point-in-polygon), via Google Places API (New).

Matching/Measuring have no radius (you compare your NEAREST X), so coverage must
be the entire playable area, not just near a station. We search the play-area
bounding box with a recursive quadtree (beats the 20-result, no-pagination cap)
and keep any place whose pin lies inside the play-area polygon.

A place counts iff it has the category's Google icon AND >=5 Google reviews
(reviews applied later in curation; here we just pull `userRatingCount`). We match
the icon via `includedTypes` (matches the place's full `types` array), NOT
`includedPrimaryTypes` -- some places carry the icon as a secondary type (e.g.
private golf clubs are primaryType `sports_club` but have `golf_course` in
`types`), and primaryType-only filtering wrongly drops them. Stored coordinate is
the icon pin (`location`).

Env: GOOGLE_PLACES_API_KEY
Reads:  ../src/data/play-area.geojson.json  (the map's play-area polygon =
        the search region; swap this file to gather a different city)
Writes: poi_full.json
"""
import os, sys, json, math, time, urllib.request, urllib.error

KEY = os.environ["GOOGLE_PLACES_API_KEY"]
URL = "https://places.googleapis.com/v1/places:searchNearby"

# Cheap mode: drop `rating`+`userRatingCount` from the field mask. Those two
# fields are what push every Nearby Search call into the pricey *Enterprise* SKU;
# without them the call bills at the cheaper *Pro* SKU (and is far likelier to sit
# inside the monthly free tier). The trade-off is we can't apply the >=5-review
# rule automatically -- the reviewer checks the (de-duped) survivors by hand. Turn
# on with POI_NO_REVIEWS=1.
NO_REVIEWS = os.environ.get("POI_NO_REVIEWS", "").lower() in ("1", "true", "yes")
_BASE_FIELDS = [
    "places.id", "places.displayName", "places.location",
    "places.primaryType", "places.types", "places.formattedAddress",
    "places.businessStatus",
]
FIELDS = ",".join(_BASE_FIELDS if NO_REVIEWS
                  else _BASE_FIELDS + ["places.rating", "places.userRatingCount"])
MAX = 20
MAX_RADIUS = 50000.0
MIN_RADIUS = 25.0

PARK_TYPES = ["park", "national_park", "state_park", "dog_park",
              "garden", "botanical_garden"]

# (category key, includedTypes, tentacle radius in mi or None)
CATS = [
    ("museum", ["museum"], 1),
    ("library", ["library"], 1),
    ("movie_theater", ["movie_theater"], 1),
    ("hospital", ["hospital"], 1),
    ("zoo", ["zoo"], 15),
    ("aquarium", ["aquarium"], 15),
    ("amusement_park", ["amusement_park"], 15),
    ("park", PARK_TYPES, None),
    ("golf_course", ["golf_course"], None),
    ("consulate", ["embassy"], None),       # real consulates; honorary ones are
                                            # government_office, so excluded
    ("mountain", ["mountain_peak"], None),  # natural peaks (kept regardless of
                                            # review count -- see curation)
    ("stadium", ["stadium", "arena"], None),  # sports venues; curation keeps the
                                            # stadium/arena icon, then the reviewer
                                            # limits to professional-sports homes
]

HERE = os.path.dirname(os.path.abspath(__file__))
PLAY = json.load(open(os.path.join(HERE, "..", "src", "data", "play-area.geojson.json")))
calls = 0


def rings_of(geom):
    polys = [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]
    for poly in polys:
        for ring in poly:
            yield ring


ALL_RINGS = [r for f in PLAY["features"] for r in rings_of(f["geometry"])]
xs = [p[0] for r in ALL_RINGS for p in r]
ys = [p[1] for r in ALL_RINGS for p in r]
BBOX = (min(ys), max(ys), min(xs), max(xs))  # lat0, lat1, lon0, lon1


def in_play(lon, lat):
    # even-odd ray casting over every ring (counties are non-overlapping and
    # holes -- e.g. carved-out ocean -- are extra rings, so even-odd is correct)
    inside = False
    for ring in ALL_RINGS:
        n = len(ring)
        j = n - 1
        for i in range(n):
            xi, yi = ring[i]
            xj, yj = ring[j]
            if ((yi > lat) != (yj > lat)) and \
               (lon < (xj - xi) * (lat - yi) / (yj - yi) + xi):
                inside = not inside
            j = i
    return inside


def haversine(lat1, lon1, lat2, lon2):
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def nearby(types, clat, clon, radius):
    global calls
    body = json.dumps({
        "includedTypes": types,
        "maxResultCount": MAX,
        "locationRestriction": {"circle": {"center": {"latitude": clat, "longitude": clon}, "radius": radius}},
    }).encode()
    req = urllib.request.Request(URL, data=body, method="POST", headers={
        "Content-Type": "application/json", "X-Goog-Api-Key": KEY, "X-Goog-FieldMask": FIELDS,
    })
    last = None
    for attempt in range(8):
        try:
            calls += 1
            with urllib.request.urlopen(req, timeout=90) as r:
                time.sleep(0.05)
                return json.load(r).get("places", [])
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}: {e.read().decode()[:300]}"
            if e.code in (429, 500, 503):
                time.sleep(2 * (attempt + 1)); continue
            sys.exit(last)
        except Exception as e:
            last = repr(e); time.sleep(2 * (attempt + 1))
    sys.exit(f"repeated request failures; last error: {last}")


def search_box(types, lat0, lat1, lon0, lon1, out):
    clat, clon = (lat0 + lat1) / 2, (lon0 + lon1) / 2
    radius = haversine(clat, clon, lat1, lon1)
    quad = lambda: (search_box(types, lat0, clat, lon0, clon, out),
                    search_box(types, lat0, clat, clon, lon1, out),
                    search_box(types, clat, lat1, lon0, clon, out),
                    search_box(types, clat, lat1, clon, lon1, out))
    if radius > MAX_RADIUS:
        quad(); return
    places = nearby(types, clat, clon, radius)
    for p in places:
        out[p["id"]] = p
    if len(places) >= MAX and radius > MIN_RADIUS:
        quad()


def main():
    out_path = os.path.join(HERE, "poi_full.json")
    result = json.load(open(out_path)) if os.path.exists(out_path) else {}
    for key, types, tradius in CATS:
        if key in result:
            print(f"{key:15s} (cached, skip)", flush=True); continue
        found = {}
        search_box(types, *BBOX, found)
        kept = []
        for p in found.values():
            loc = p["location"]
            if in_play(loc["longitude"], loc["latitude"]):
                kept.append({
                    "id": p["id"], "name": p.get("displayName", {}).get("text", ""),
                    "primaryType": p.get("primaryType"), "types": p.get("types", []),
                    "address": p.get("formattedAddress", ""), "rating": p.get("rating"),
                    "userRatingCount": p.get("userRatingCount", 0),
                    "businessStatus": p.get("businessStatus"),
                    "lat": loc["latitude"], "lon": loc["longitude"],
                })
        kept.sort(key=lambda x: x["name"])
        result[key] = {"includedTypes": types, "tentacleRadiusMi": tradius,
                       "count": len(kept), "places": kept}
        json.dump(result, open(out_path, "w"), indent=2)
        ge5 = sum(1 for x in kept if (x["userRatingCount"] or 0) >= 5)
        print(f"{key:15s} raw_in_bbox={len(found):5d} in_play={len(kept):5d} "
              f">=5rev={ge5:5d} calls={calls}", flush=True)
    print(f"\ntotal API calls: {calls}\nwrote {out_path}")


if __name__ == "__main__":
    main()
