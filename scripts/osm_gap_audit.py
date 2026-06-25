"""Free OSM-vs-ours recall audit. For each category, find named OSM places that
have no matching pin near one of ours -> candidates that searchNearby missed.
No Google API calls. Writes osm_gap_audit.md + osm_gap_candidates.json.
"""
import os, json, math, re, urllib.request, urllib.parse, time
import poi_geo

HERE = os.path.dirname(os.path.abspath(__file__))
curated = json.load(open(os.path.join(HERE, "poi_curated.json")))
_play = poi_geo.load_play()
BBOX_SWNE = poi_geo.bbox_swne(_play)          # derived from the play polygon
IN_PLAY = poi_geo.make_in_play(_play)         # city-agnostic point-in-polygon

# category -> list of OSM tag filters (key, value)
OSM_TAGS = {
    "museum": [("tourism", "museum")],
    "library": [("amenity", "library")],
    "movie_theater": [("amenity", "cinema")],
    "hospital": [("amenity", "hospital")],
    "zoo": [("tourism", "zoo")],
    "aquarium": [("tourism", "aquarium")],
    "amusement_park": [("tourism", "theme_park"), ("leisure", "water_park")],
    "golf_course": [("leisure", "golf_course")],
    "consulate": [("diplomatic", "consulate"), ("office", "diplomatic")],
    "mountain": [("natural", "peak")],
    # park omitted from gap audit: leisure=park is enormous and noisy; handle
    # separately if needed.
}

def overpass(filters):
    s, w, n, e = BBOX_SWNE
    sel = "".join(
        f'nwr["{k}"="{v}"]["name"]({s},{w},{n},{e});' for k, v in filters)
    q = f"[out:json][timeout:180];({sel});out tags center;"
    data = urllib.parse.urlencode({"data": q}).encode()
    req = urllib.request.Request("https://overpass-api.de/api/interpreter",
                                 data=data, headers={"User-Agent": "jetlag-audit/1.0"})
    for attempt in range(4):
        try:
            return json.load(urllib.request.urlopen(req, timeout=200))["elements"]
        except Exception as e:
            print("  overpass retry:", e); time.sleep(8)
    return []


def norm(s):
    s = s.lower().replace("&", " and ").replace("+", " and ")
    s = re.sub(r"[^\w\s]", " ", s)
    return " ".join(s.split())


def km(a_lat, a_lon, b_lat, b_lon):
    return math.hypot((a_lat - b_lat) * 111.0, (a_lon - b_lon) * 88.0)


md = ["# OSM-vs-ours recall audit (free, no Google calls)\n",
      "Named OSM places with **no** matching pin within 300m of one of ours — "
      "i.e. candidates `searchNearby` likely missed.\n"]
candidates = {}
summary = []
for key, tags in OSM_TAGS.items():
    ours = curated.get(key, {}).get("places", [])
    els = overpass(tags)
    osm = []
    for e in els:
        n = (e.get("tags", {}).get("name") or "").strip()
        lat = e.get("lat") or (e.get("center") or {}).get("lat")
        lon = e.get("lon") or (e.get("center") or {}).get("lon")
        if n and lat and lon and IN_PLAY(lon, lat):
            osm.append((n, lat, lon))
    miss = []
    for n, lat, lon in osm:
        nn = norm(n)
        covered = False
        for p in ours:
            d = km(lat, lon, p["lat"], p["lon"])
            if d < 0.3:                       # within 300m -> same place
                covered = True; break
            if d < 1.5 and (nn in norm(p["name"]) or norm(p["name"]) in nn):
                covered = True; break
        if not covered:
            miss.append({"name": n, "lat": lat, "lon": lon})
    candidates[key] = miss
    summary.append((key, len(ours), len(osm), len(miss)))
    print(f"{key:15s} ours={len(ours):4d} osm={len(osm):4d} gap={len(miss):4d}")
    md.append(f"\n## {key} — ours {len(ours)}, OSM {len(osm)}, **gap {len(miss)}**\n")
    for m in sorted(miss, key=lambda x: x["name"]):
        q = urllib.parse.quote(f"{m['name']} {m['lat']},{m['lon']}")
        md.append(f"- [{m['name']}](https://www.google.com/maps/search/?api=1&query={q})")

md.append("\n\n## Summary\n\n| category | ours | OSM named | gap (OSM-only) |")
md.append("|---|---|---|---|")
for k, o, s, g in summary:
    md.append(f"| {k} | {o} | {s} | {g} |")
md.append(f"| **total** | — | — | **{sum(g for *_, g in summary)}** |")

open(os.path.join(HERE, "osm_gap_audit.md"), "w").write("\n".join(md))
json.dump(candidates, open(os.path.join(HERE, "osm_gap_candidates.json"), "w"), indent=1)
print("\nwrote osm_gap_audit.md + osm_gap_candidates.json; total gap =",
      sum(g for *_, g in summary))
