#!/usr/bin/env python3
"""Gather all POI categories used by Tentacles + Matching + Measuring over a
region's whole play area (point-in-polygon), via Google Places API (New).

    python3 fetch_places_poi.py --region la

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
Reads:  the region's play-area polygon (`poi_geo.REGIONS`) — that is the search
        area; a different city is `--region`, never an edited file.
Writes: the region's `poi_full[.<region>].json`
"""
import os, sys, json, math, time, urllib.request, urllib.error

from shapely.geometry import box, shape
from shapely.ops import unary_union

import poi_geo
from poi_geo import CATS, PARK_TYPES  # noqa: F401  (the shared category rulebook)

KEY = os.environ.get("GOOGLE_PLACES_API_KEY", "")
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
# Stop before the bill runs away: 0 = no cap. Each finished category is written
# out and skipped on the next run, so a capped sweep is restartable.
MAX_CALLS = int(os.environ.get("POI_MAX_CALLS", "0"))

HERE = os.path.dirname(os.path.abspath(__file__))
REGION = poi_geo.region_from_argv()
OUT_FILE = poi_geo.work(REGION, "poi_full.json")
PLAY = poi_geo.load_play(REGION)
BBOX = poi_geo.bbox(PLAY)               # lat0, lat1, lon0, lon1
in_play = poi_geo.make_in_play(PLAY)    # even-odd over every ring, holes included
calls = 0

# A play area never fills its own bounding box (DC's covers about a third of
# it), and the quadtree would otherwise pay to search the empty rest — the bulk
# of the sweep's cost. Cells missing the polygon entirely are skipped: an
# in-play place near such a cell is still returned by the neighbouring cell that
# does hit it. The margin absorbs the search circle circumscribing each cell.
SKIP_MARGIN_M = 500.0
_PLAY_GEOM = unary_union([shape(f["geometry"]) for f in PLAY["features"]]).buffer(
    SKIP_MARGIN_M / (111320.0 * math.cos(math.radians((BBOX[0] + BBOX[1]) / 2))))
skipped = 0


class BudgetExhausted(Exception):
    """POI_MAX_CALLS reached — unwind without discarding finished categories."""


def haversine(lat1, lon1, lat2, lon2):
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def nearby(types, clat, clon, radius):
    global calls
    if MAX_CALLS and calls >= MAX_CALLS:
        raise BudgetExhausted()
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
    global skipped
    clat, clon = (lat0 + lat1) / 2, (lon0 + lon1) / 2
    radius = haversine(clat, clon, lat1, lon1)
    quad = lambda: (search_box(types, lat0, clat, lon0, clon, out),
                    search_box(types, lat0, clat, clon, lon1, out),
                    search_box(types, clat, lat1, lon0, clon, out),
                    search_box(types, clat, lat1, clon, lon1, out))
    if not _PLAY_GEOM.intersects(box(lon0, lat0, lon1, lat1)):
        skipped += 1; return
    if radius > MAX_RADIUS:
        quad(); return
    places = nearby(types, clat, clon, radius)
    for p in places:
        out[p["id"]] = p
    if len(places) >= MAX and radius > MIN_RADIUS:
        quad()


def main():
    if not KEY:
        sys.exit("set GOOGLE_PLACES_API_KEY (this pull is billable)")
    out_path = OUT_FILE
    result = json.load(open(out_path)) if os.path.exists(out_path) else {}
    for key, types, tradius in CATS:
        if key in result:
            print(f"{key:15s} (cached, skip)", flush=True); continue
        found = {}
        try:
            search_box(types, *BBOX, found)
        except BudgetExhausted:
            print(f"{key:15s} stopped at POI_MAX_CALLS={MAX_CALLS}; {key} left "
                  f"uncached — rerun to finish it", flush=True)
            break
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
    print(f"\ntotal API calls: {calls} (cells skipped as out of play: {skipped})"
          f"\nwrote {out_path} ({REGION})")


if __name__ == "__main__":
    main()
