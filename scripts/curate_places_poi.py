#!/usr/bin/env python3
"""Curate the full-area POI pull (poi_full.json) into the final dataset.

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

Reads:  poi_full.json
Writes: poi_full_curated.json, poi_full_review.md
"""
import os, json, math

HERE = os.path.dirname(os.path.abspath(__file__))
raw = json.load(open(os.path.join(HERE, "poi_full.json")))
# Cheap mode (POI_NO_REVIEWS=1): the pull omitted review counts to bill at the
# cheaper Pro SKU, so the >=5-review rule can't be applied here -- keep every
# icon-matching place and let the reviewer drop low-review ones by hand.
NO_REVIEWS = os.environ.get("POI_NO_REVIEWS", "").lower() in ("1", "true", "yes")
MIN_REVIEWS = 5

LABEL = {
    "museum": "Museums", "library": "Libraries", "movie_theater": "Movie Theaters",
    "hospital": "Hospitals", "zoo": "Zoos", "aquarium": "Aquariums",
    "amusement_park": "Amusement Parks", "park": "Parks", "golf_course": "Golf Courses",
    "consulate": "Consulates", "mountain": "Mountains", "stadium": "Sports Stadiums",
}
# categories exempt from the >=5-review rule (natural features rarely have
# reviews; we keep every peak and decide later with the data)
KEEP_ALL = {"mountain"}

# --- icon allowlist -------------------------------------------------------
# We pull broadly (includedTypes matches the place's full `types` array), then
# keep only places whose `primaryType` is the icon Google actually shows. This
# drops the noise the broad pull introduces (urgent-care clinics typed as
# hospitals, shopping malls typed as movie theaters, pet stores as aquariums,
# zoos/Union Square as parks, Topgolf/disc-golf/Golf Galaxy as golf, etc.).
ALLOW = {
    "museum": {"museum", "art_museum", "history_museum", "art_gallery"},
    "library": {"library"},
    "movie_theater": {"movie_theater"},
    "hospital": {"hospital", "general_hospital", "medical_center"},
    "zoo": {"zoo"},
    "aquarium": {"aquarium"},
    "amusement_park": {"amusement_park", "water_park", "amusement_center"},
    "park": {"park", "city_park", "national_park", "state_park", "dog_park",
             "garden", "botanical_garden", "nature_preserve"},
    "golf_course": {"golf_course"},   # + club rescue, see keep_by_type()
    "consulate": {"embassy"},         # honorary consulates are
                                      # local_government_office -> excluded
    "mountain": {"mountain_peak"},
    "stadium": {"stadium", "arena"},  # the sports-venue icon; reviewer then
                                      # limits to professional-sports home venues
}
# real golf/country clubs Google mis-primaries (e.g. SF Golf Club = sports_club)
GOLF_CLUB_PRIMARIES = {"sports_club", "association_or_organization", "country_club"}
GOLF_NAME_EXCLUDE = ("driving range", "topgolf", "top golf", "mini golf",
                     "miniature golf", "disc golf", "golf galaxy", "indoor golf")


def keep_by_type(key, p):
    pt = p.get("primaryType")
    name = (p.get("name") or "").lower()
    if key == "golf_course":
        if any(x in name for x in GOLF_NAME_EXCLUDE):
            return False
        if pt == "golf_course":
            return True
        return pt in GOLF_CLUB_PRIMARIES and ("golf" in name or "country club" in name)
    allow = ALLOW.get(key)
    return True if allow is None else pt in allow

# --- human judgement: nested sub-areas to REMOVE (part of a bigger attraction) -
NESTED_REMOVE = {
    "zoo": {
        "California Trail at Oakland Zoo", "African Savanna",
        "Condor and Jaguar Pavilion", "Giraffe Enclosure", "House of Bugs",
        "Reptile and Amphibian Discovery Room",
    },
    "amusement_park": {
        "South Bay Shores", "Planet Snoopy",
        "California's Great America Passenger Drop Off Area",
        "NorCal County Fair", "Great Barrier Reef", "County Fair Picnic Grove",
        "Water Play Area", "Water Oasis",
    },
}
# closed by name (businessStatus didn't catch it)
NAME_CLOSED = {"FB OUTDOOR (PERM CLOSED)"}

# --- flagged but KEPT (human eyeball; rule keeps them) ----------------------
FLAG_REVIEW = {
    "golf_course": {  # likely driving range / practice center, you wanted these out
        "Norcal Golf Center", "Palm Tree Golf and Event Center",
        "The Pleasanton Golf Center - Golf Course", "Mariners Point Golf Center",
        "Lone Tree Golf & Event Center",
    },
    "aquarium": {"Aquatic Experts"},
    "amusement_park": {
        "ABC Tree Farms & Pick of the Patch Pumpkins ECR",
        "Ortega park splash park", "Water Light Public Plaza",
    },
}


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


curated, md = {}, ["# Full-area POI dataset — icon + >=5-review rule\n",
                   "Coverage = the 5-county play-area polygon. Coordinates are the Google pin.\n"]
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

json.dump(curated, open(os.path.join(HERE, "poi_full_curated.json"), "w"), indent=2)

hdr = ["| Category | Raw in play | >=5 reviews | off-icon dropped | nested removed | **final** |",
       "|---|---|---|---|---|---|"]
for name, rawn, g5, offi, rem, fin in summary:
    hdr.append(f"| {name} | {rawn} | {g5} | {offi} | {rem} | **{fin}** |")
md = [md[0], md[1], "\n".join(hdr), "\n"] + md[2:]
open(os.path.join(HERE, "poi_full_review.md"), "w").write("\n".join(md))
print("\n".join(hdr))
print("\nwrote poi_full_curated.json + poi_full_review.md")
