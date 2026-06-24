#!/usr/bin/env python3
"""Gather Tentacles POI data via Google Places API (New), with review counts.

A POI counts (per the Jet Lag rulebook) if it shows up with the category's
Google Maps icon (= Google `primaryType`) AND has >=5 Google reviews. This
script pulls the icon-matching places plus their `userRatingCount` so the
>=5-review legitimacy rule can be applied in curation. The stored coordinate
is the place's pin (`location`), not a polygon centroid.

Categories:
  1-mile  : museum, library, movie_theater, hospital
  15-mile : zoo, aquarium, amusement_park   (Metro Lines handled by transit data)

searchNearby caps at 20 results with no pagination, so each category's region
is covered with a recursive quadtree: any cell returning the full 20 is split
into quadrants until it stops saturating. Results dedupe by place id, then are
kept only within the relevant buffer of a station (1-mile cards: radius + 0.5mi
max hiding zone = 1.5mi; 15-mile: 15.5mi).

Env: GOOGLE_PLACES_API_KEY
Writes: tentacle_poi.json (next to this script)
"""
import os, sys, json, math, time, urllib.request, urllib.error

KEY = os.environ["GOOGLE_PLACES_API_KEY"]
URL = "https://places.googleapis.com/v1/places:searchNearby"
FIELDS = ",".join([
    "places.id", "places.displayName", "places.location",
    "places.primaryType", "places.types", "places.formattedAddress",
    "places.rating", "places.userRatingCount", "places.businessStatus",
])
MAX = 20
MAX_RADIUS = 50000.0
MIN_RADIUS = 25.0
MI = 1609.344

CATS = {
    1.0: ["museum", "library", "movie_theater", "hospital"],
    15.0: ["zoo", "aquarium", "amusement_park"],
}
BUFFER_MI = 0.5  # largest hiding-zone radius (Large game)

HERE = os.path.dirname(os.path.abspath(__file__))
STATIONS = json.load(open(os.path.join(HERE, "..", "src", "data", "stations.json")))
calls = 0


def haversine(lat1, lon1, lat2, lon2):
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def nearby(ptype, clat, clon, radius):
    global calls
    body = json.dumps({
        "includedPrimaryTypes": [ptype],
        "maxResultCount": MAX,
        "locationRestriction": {"circle": {"center": {"latitude": clat, "longitude": clon}, "radius": radius}},
    }).encode()
    req = urllib.request.Request(URL, data=body, method="POST", headers={
        "Content-Type": "application/json",
        "X-Goog-Api-Key": KEY,
        "X-Goog-FieldMask": FIELDS,
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
                time.sleep(2 * (attempt + 1))
                continue
            sys.exit(last)
        except Exception as e:
            last = repr(e)
            time.sleep(2 * (attempt + 1))
    sys.exit(f"repeated request failures; last error: {last}")


def search_box(ptype, lat0, lat1, lon0, lon1, out):
    clat, clon = (lat0 + lat1) / 2, (lon0 + lon1) / 2
    radius = haversine(clat, clon, lat1, lon1)
    if radius > MAX_RADIUS:
        m0, m1 = clat, clon
        search_box(ptype, lat0, m0, lon0, m1, out)
        search_box(ptype, lat0, m0, m1, lon1, out)
        search_box(ptype, m0, lat1, lon0, m1, out)
        search_box(ptype, m0, lat1, m1, lon1, out)
        return
    places = nearby(ptype, clat, clon, radius)
    for p in places:
        out[p["id"]] = p
    if len(places) >= MAX and radius > MIN_RADIUS:
        m0, m1 = clat, clon
        search_box(ptype, lat0, m0, lon0, m1, out)
        search_box(ptype, lat0, m0, m1, lon1, out)
        search_box(ptype, m0, lat1, lon0, m1, out)
        search_box(ptype, m0, lat1, m1, lon1, out)


def near_station(lat, lon, max_m):
    for s in STATIONS:
        if haversine(lat, lon, s["lat"], s["lon"]) <= max_m:
            return True
    return False


def main():
    lats = [s["lat"] for s in STATIONS]
    lons = [s["lon"] for s in STATIONS]
    out_path = os.path.join(HERE, "tentacle_poi.json")
    result = json.load(open(out_path)) if os.path.exists(out_path) else {}
    for radius_mi, types in CATS.items():
        keep_m = (radius_mi + BUFFER_MI) * MI
        dlat = keep_m / 111320.0
        dlon = keep_m / (111320.0 * math.cos(math.radians(sum(lats) / len(lats))))
        b = (min(lats) - dlat, max(lats) + dlat, min(lons) - dlon, max(lons) + dlon)
        for ptype in types:
            if ptype in result:
                print(f"{ptype:15s} (cached, skip)", flush=True)
                continue
            found = {}
            search_box(ptype, *b, found)
            kept = []
            for p in found.values():
                loc = p["location"]
                if near_station(loc["latitude"], loc["longitude"], keep_m):
                    kept.append({
                        "id": p["id"],
                        "name": p.get("displayName", {}).get("text", ""),
                        "primaryType": p.get("primaryType"),
                        "types": p.get("types", []),
                        "address": p.get("formattedAddress", ""),
                        "rating": p.get("rating"),
                        "userRatingCount": p.get("userRatingCount", 0),
                        "businessStatus": p.get("businessStatus"),
                        "lat": loc["latitude"],
                        "lon": loc["longitude"],
                    })
            kept.sort(key=lambda x: x["name"])
            result[ptype] = {"radiusMi": radius_mi, "count": len(kept), "places": kept}
            json.dump(result, open(out_path, "w"), indent=2)
            ge5 = sum(1 for x in kept if (x["userRatingCount"] or 0) >= 5)
            print(f"{ptype:15s} raw={len(found):5d} kept={len(kept):5d} >=5rev={ge5:5d} calls={calls}", flush=True)
    print(f"\ntotal API calls: {calls}\nwrote {out_path}")


if __name__ == "__main__":
    main()
