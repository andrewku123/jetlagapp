#!/usr/bin/env python3
"""Curate a region's full-area POI pull into its curated dataset.

    python3 curate_places_poi.py --region la

Rulebook rule: a place counts iff it has the category's Google icon
(`primaryType`, already enforced at pull time) AND has >=5 Google reviews.
We also drop permanently-closed places. Beyond that the only edits are:

 - NESTED SUB-AREAS (sparse 15-mi cats + golf): a pin that is really a part of a
   bigger same-category attraction (e.g. the "Giraffe Enclosure" inside Oakland
   Zoo, "South Bay Shores" inside Great America) does NOT count -- removed by an
   explicit, human-reviewed name list (cross-checked by a proximity heuristic).
 - GOLF excludes mini-golf / driving ranges / practice ranges per the rulebook
   ("no mini golf or driving range"). No such names fire automatically in the
   Bay Area pull, but ambiguous "Golf Center" pins are FLAGGED for human review.
 - A few obvious category mis-tags (a pumpkin patch tagged water_park, etc.) are
   FLAGGED (kept by default per the rule; the players can drop under the
   "legitimate unless all players agree otherwise" clause).

Reads:  the region's `poi_full[.<region>].json` and its curation overrides
Writes: the region's `poi_curated[.<region>].json` + `poi_review[.<region>].md`
"""
import os, json, math

import poi_geo
# The category rulebook (labels, review exemptions, icon allowlist + golf rescue)
# lives in poi_geo so discovery, curation and the refresh cycle share one copy.
from poi_geo import (ALLOW, GOLF_CLUB_PRIMARIES, GOLF_NAME_EXCLUDE,  # noqa: F401
                     KEEP_ALL, LABEL, MIN_REVIEWS, keep_by_type)

HERE = os.path.dirname(os.path.abspath(__file__))
REGION = poi_geo.region_from_argv()
raw = json.load(open(poi_geo.work(REGION, "poi_full.json")))
# Cheap mode (POI_NO_REVIEWS=1): the pull omitted review counts to bill at the
# cheaper Pro SKU, so the >=5-review rule can't be applied here -- keep every
# icon-matching place and let the reviewer drop low-review ones by hand.
NO_REVIEWS = os.environ.get("POI_NO_REVIEWS", "").lower() in ("1", "true", "yes")

# --- per-city human judgement, as data ---------------------------------------
# These lists are a *city's* reviewed decisions, not pipeline logic, so they live
# in `poi_curate_overrides[.<region>].json` rather than in code:
#   nestedRemove  {cat: [name]}  a pin that is really part of a bigger same-category
#                                attraction ("Giraffe Enclosure" inside Oakland Zoo)
#   nameClosed    [name]         closed, but businessStatus didn't say so
#   flagReview    {cat: [name]}  kept per the rule, but printed for a human eyeball
#   stadiumPro    {place_id: name}  see below
OVR_PATH = poi_geo.work(REGION, "poi_curate_overrides.json")
OVR = json.load(open(OVR_PATH)) if os.path.exists(OVR_PATH) else {}
NESTED_REMOVE = {k: set(v) for k, v in OVR.get("nestedRemove", {}).items()}
NAME_CLOSED = set(OVR.get("nameClosed", []))
FLAG_REVIEW = {k: set(v) for k, v in OVR.get("flagReview", {}).items()}

# STADIUM: the icon rule surfaces EVERY stadium/arena, but the rulebook subject is
# "professional sports", which Google can't encode -- the overwhelming majority of
# icon hits are college / high-school / amateur fields. So a city lists the home
# venues *currently played in* by a pro / minor / independent-league team (no
# historic venues), keyed by Google place_id (stable; display names drift -- e.g.
# Levi's shows a Super Bowl placeholder -- so the list relabels too).
# A city with no list yet keeps every icon hit and says so: dropping the category
# silently would hide the work, and keeping junk is visible on the review map.
STADIUM_PRO = OVR.get("stadiumPro")


def hav(a, b, c, d):
    R = 6371000.0
    import math as m
    dp, dl = m.radians(c - a), m.radians(d - b)
    x = m.sin(dp / 2) ** 2 + m.cos(m.radians(a)) * m.cos(m.radians(c)) * m.sin(dl / 2) ** 2
    return 2 * R * m.asin(m.sqrt(x))


def maps_link(p):
    return f"https://www.google.com/maps/search/?api=1&query={p['lat']}%2C{p['lon']}&query_place_id={p['id']}"


def proximity_nested(kept):
    """cross-check: kept place <=800m from a same-cat place with >=3x reviews."""
    flagged = {}
    for p in kept:
        pn = p.get("userRatingCount") or 0
        for q in kept:
            if q is p:
                continue
            if (q.get("userRatingCount") or 0) >= 3 * max(pn, 1) and \
               hav(p["lat"], p["lon"], q["lat"], q["lon"]) <= 800:
                flagged[p["id"]] = q["name"]
                break
    return flagged


curated, md = {}, [f"# {poi_geo.REGIONS[REGION]['label']} POI dataset — icon + >=5-review rule\n",
                   "Coverage = the play-area polygon. Coordinates are the Google pin.\n"]
summary = []
SPARSE = {"zoo", "aquarium", "amusement_park", "golf_course"}

for key in [k for k in LABEL if k in raw]:
    blk = raw[key]
    min_rev = 0 if (NO_REVIEWS or key in KEEP_ALL) else MIN_REVIEWS
    ge5 = [p for p in blk["places"]
           if (p.get("userRatingCount") or 0) >= min_rev
           and p.get("businessStatus") != "CLOSED_PERMANENTLY"
           and p["name"] not in NAME_CLOSED]
    typed = [p for p in ge5 if keep_by_type(key, p)]
    off_icon = len(ge5) - len(typed)
    if key == "stadium" and STADIUM_PRO is not None:   # keep-list + relabel
        typed = [dict(p, name=STADIUM_PRO[p["id"]]) for p in typed if p["id"] in STADIUM_PRO]
    elif key == "stadium":
        print(f"  ! no professional-venue keep-list in {os.path.basename(OVR_PATH)} — "
              f"keeping all {len(typed)} stadium/arena icons for the review map")
    nested = NESTED_REMOVE.get(key, set())
    removed = [p for p in typed if p["name"] in nested]
    kept = [p for p in typed if p["name"] not in nested]
    kept.sort(key=lambda x: -(x.get("userRatingCount") or 0))
    curated[key] = {"tentacleRadiusMi": blk.get("tentacleRadiusMi"),
                    "count": len(kept), "places": kept}

    prox = proximity_nested([p for p in kept]) if key in SPARSE else {}
    flags = FLAG_REVIEW.get(key, set())
    summary.append((LABEL[key], blk["count"], len(ge5), off_icon, len(removed), len(kept)))

    md.append(f"\n## {LABEL[key]} — {len(kept)} legitimate "
              f"({'tentacle ' + str(blk['tentacleRadiusMi']) + 'mi; ' if blk.get('tentacleRadiusMi') else ''}"
              f"matching/measuring)\n")
    if removed:
        md.append(f"\n**Removed as nested sub-areas ({len(removed)}):** "
                  + ", ".join(f"[{p['name']}]({maps_link(p)})" for p in removed) + "\n")
    review = [p for p in kept if p["name"] in flags or p["id"] in prox]
    if review:
        md.append(f"\n**Flagged to eyeball ({len(review)}) — kept per rule, drop if you disagree:**\n")
        for p in review:
            why = f"nested near {prox[p['id']]}" if p["id"] in prox else "possible mis-tag / driving range"
            md.append(f"- [{p['name']}]({maps_link(p)}) — {p.get('userRatingCount')} reviews, "
                      f"`{p.get('primaryType')}` — _{why}_")
    md.append(f"\n<details><summary>All {len(kept)} kept</summary>\n")
    for p in kept:
        md.append(f"- [{p['name']}]({maps_link(p)}) — {p.get('userRatingCount')} reviews "
                  f"({p.get('rating')}★) · `{p.get('primaryType')}`")
    md.append("\n</details>\n")

cur_path = poi_geo.work(REGION, "poi_curated.json")
md_path = poi_geo.work(REGION, "poi_review.md")
json.dump(curated, open(cur_path, "w"), indent=2)

hdr = ["| Category | Raw in play | >=5 reviews | off-icon dropped | nested removed | **final** |",
       "|---|---|---|---|---|---|"]
for name, rawn, g5, offi, rem, fin in summary:
    hdr.append(f"| {name} | {rawn} | {g5} | {offi} | {rem} | **{fin}** |")
md = [md[0], md[1], "\n".join(hdr), "\n"] + md[2:]
open(md_path, "w").write("\n".join(md))
print("\n".join(hdr))
print(f"\nwrote {os.path.basename(cur_path)} + {os.path.basename(md_path)}")
