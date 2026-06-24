#!/usr/bin/env python3
"""Apply the Jet Lag legitimacy rule to the raw Tentacles POI pull.

Objective rule (from the rulebook): a place counts if it has the category's
Google Maps icon (already guaranteed by the `primaryType` filter at pull time)
AND has >=5 Google reviews. Anything with <5 reviews is assumed illegitimate.
Permanently-closed places are also dropped (they no longer exist).

No subjective name filtering. We additionally surface a small "possible
mis-tag" list (places that pass the >=5 rule but look category-mismatched) for
human eyeballing -- these are NOT removed, per the rule ("legitimate unless all
players agree otherwise").

Reads:  tentacle_poi.json
Writes: tentacle_poi_curated.json, tentacle_poi_review.md
"""
import os, json, math

HERE = os.path.dirname(os.path.abspath(__file__))


def haversine(lat1, lon1, lat2, lon2):
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def nested_subareas(kept):
    """Flag places that sit inside a much bigger same-category attraction
    (<=400m from a kept place with >=10x the reviews) -- e.g. the 'Lions'
    exhibit inside a zoo. Objective signal for the 'sub-area, not a distinct
    attraction' case."""
    flagged = set()
    for i, p in enumerate(kept):
        pn = p.get("userRatingCount") or 0
        for q in kept:
            qn = q.get("userRatingCount") or 0
            if q is p:
                continue
            if qn >= 10 * max(pn, 1) and haversine(p["lat"], p["lon"], q["lat"], q["lon"]) <= 400:
                flagged.add(p["id"])
                break
    return flagged


raw = json.load(open(os.path.join(HERE, "tentacle_poi.json")))

MIN_REVIEWS = 5

# No subjective name filtering: the rulebook is icon + >=5 reviews, full stop.
# (A trampoline park or pet hospital with the icon and >=5 reviews counts.)
# The only thing we surface for human review is the objective "nested sub-area"
# signal below, which the players can choose to collapse under the
# "legitimate unless all players agree otherwise" clause.

ICON = {
    "museum": "Museums", "library": "Libraries", "movie_theater": "Movie Theaters",
    "hospital": "Hospitals", "zoo": "Zoos", "aquarium": "Aquariums",
    "amusement_park": "Amusement Parks",
}


def maps_link(p):
    return (f"https://www.google.com/maps/search/?api=1&query={p['lat']}%2C{p['lon']}"
            f"&query_place_id={p['id']}")


curated = {}
md = ["# Tentacles POI — legitimacy rule applied (>=5 Google reviews)\n",
      "Each place has its category's Google icon (`primaryType`) **and** >=5 reviews. "
      "Permanently-closed places dropped. Coordinates are the Google pin.\n"]

summary = []
for ptype, blk in raw.items():
    places = blk["places"]
    kept, dropped_few, dropped_closed = [], [], []
    for p in places:
        n = p.get("userRatingCount") or 0
        if p.get("businessStatus") == "CLOSED_PERMANENTLY":
            dropped_closed.append(p)
        elif n >= MIN_REVIEWS:
            kept.append(p)
        else:
            dropped_few.append(p)
    kept.sort(key=lambda x: -(x.get("userRatingCount") or 0))
    curated[ptype] = {"radiusMi": blk["radiusMi"], "count": len(kept), "places": kept}
    summary.append((ICON[ptype], blk["radiusMi"], len(places), len(kept),
                    len(dropped_few), len(dropped_closed)))

    # nested sub-area flagging only for sparse 15-mi cats (zoo/aquarium/amusement);
    # dense urban cats legitimately cluster distinct venues within 400m.
    nested = nested_subareas(kept) if ptype in ("zoo", "aquarium", "amusement_park") else set()
    mistags = [p for p in kept if p["id"] in nested]

    md.append(f"\n## {ICON[ptype]}  (within {blk['radiusMi']:g} mi, {len(kept)} legitimate)\n")
    if mistags:
        md.append(f"\n**Possible exceptions to eyeball ({len(mistags)}) — pass the >=5-review "
                  f"rule but look like a sub-area of a bigger attraction or a mis-tag; kept per "
                  f"rule, remove only if you (the players) agree:**\n")
        for p in mistags:
            md.append(f"- [{p['name']}]({maps_link(p)}) — {p.get('userRatingCount')} reviews, "
                      f"`{p.get('primaryType')}` — _nested in bigger same-category attraction_")
    md.append(f"\n<details><summary>All {len(kept)} legitimate places</summary>\n")
    for p in kept:
        md.append(f"- [{p['name']}]({maps_link(p)}) — {p.get('userRatingCount')} reviews "
                  f"({p.get('rating')}★) · `{p.get('primaryType')}`")
    md.append("\n</details>\n")
    md.append(f"\n<details><summary>Dropped: {len(dropped_few)} with &lt;5 reviews"
              f"{', '+str(len(dropped_closed))+' permanently closed' if dropped_closed else ''}"
              f"</summary>\n")
    for p in sorted(dropped_few, key=lambda x: x["name"]):
        md.append(f"- {p['name']} — {p.get('userRatingCount') or 0} reviews")
    md.append("\n</details>\n")

json.dump(curated, open(os.path.join(HERE, "tentacle_poi_curated.json"), "w"), indent=2)

hdr = ["| Category | Radius | Raw | Legit (>=5) | Dropped <5 | Closed |",
       "|---|---|---|---|---|---|"]
for name, r, raw_n, kept_n, few, closed in summary:
    hdr.append(f"| {name} | {r:g} mi | {raw_n} | **{kept_n}** | {few} | {closed} |")
md = [md[0], md[1], "\n".join(hdr), "\n"] + md[2:]
open(os.path.join(HERE, "tentacle_poi_review.md"), "w").write("\n".join(md))

print("\n".join(hdr))
print("\nwrote tentacle_poi_curated.json + tentacle_poi_review.md")
