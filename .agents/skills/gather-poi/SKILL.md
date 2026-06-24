---
name: gather-poi
description: Gather the Points-of-Interest dataset used by the Tentacles, POI-Matching and POI-Measuring questions (museums, libraries, movie theaters, hospitals, zoos, aquariums, amusement parks, parks, golf courses) from Google Places, over the map's whole play area, using the rulebook's "category icon + >=5 Google reviews" rule and the icon pin coordinate. Use when (re)building or quarterly-refreshing the POI data for the Bay Area or any new city.
---

# Gather the POI dataset (Google Places, icon + review rule)

Three question families need per-category POI data:
- **Tentacles** — "of all the ___ within R of me, which are you nearest to?"
- **Matching** — "is your nearest ___ the same as mine?"
- **Measuring** — "how far are you from the nearest ___?"

Matching/Measuring have **no radius** (you compare your *nearest*), so the data
must cover the **entire play area**, not just near a station. One full-area pull
serves all three (Tentacles just filters by its radius later).

## The rulebook criterion (keep it objective)

A place counts as a valid POI of a category **iff**:
1. **It has that category's Google Maps icon** — Google's `primaryType` is the
   category (book = `library`, ferris wheel = `amusement_park`, …). Enforced by
   `includedPrimaryTypes` at query time.
2. **It has >=5 Google reviews** (`userRatingCount >= 5`). Under 5 = assumed
   illegitimate (mis-tagged parking lot, fake listing, internal department, Little
   Free Library box, …).

That's the whole rule — **do not add subjective name filters** (a trampoline park
or a pet hospital with the icon + >=5 reviews counts). The only allowed edits:
- drop `CLOSED_PERMANENTLY` (and names that literally say "perm closed");
- **golf only**: the rulebook says *no mini-golf / driving ranges* — name-exclude
  those (none fire automatically in the Bay Area; ambiguous "Golf Center" pins are
  flagged for a human);
- **nested sub-areas** (a pin that's part of a bigger same-category attraction,
  e.g. "Giraffe Enclosure" inside Oakland Zoo, "South Bay Shores" inside Great
  America) are removed via an explicit human-reviewed list, cross-checked by a
  proximity heuristic. Only applied to the sparse categories.

Store the **pin** (`location`), never a polygon centroid.

## The search region (generalizes to any city)

The search region is **the map's play-area polygon** —
`src/data/play-area.geojson.json` (here = the 5 in-play counties: SF, San Mateo,
Santa Clara, Alameda, Contra Costa, land+bay). The fetch script searches the
polygon's bounding box and keeps any pin that is **inside the polygon**
(even-odd ray cast, holes/ocean handled). No station dependency and no Bay-Area
assumptions: **to gather a new city, swap in that city's `play-area.geojson.json`
and re-run** — everything else is unchanged. (No edge buffer is needed unless a
station sits within the largest hiding-zone radius, 0.5mi, of the play-area
border; the Bay Area has none.)

## Categories

| category | Google `includedPrimaryTypes` | tentacle radius |
|---|---|---|
| museum | `museum` | 1 mi |
| library | `library` | 1 mi |
| movie_theater | `movie_theater` | 1 mi |
| hospital | `hospital` | 1 mi |
| zoo | `zoo` | 15 mi |
| aquarium | `aquarium` | 15 mi |
| amusement_park | `amusement_park` | 15 mi |
| park | `park, national_park, state_park, dog_park, garden, botanical_garden` | — (matching/measuring only) |
| golf_course | `golf_course` | — |

`park` is intentionally broad ("any park counts, gardens included"). Google
hierarchy-expands these, so results also include `city_park`, `nature_preserve`,
`dog_park`, `wildlife_refuge`, etc. — all kept.
Tentacles also lists "Metro Lines" (15 mi) — answered from existing transit-line
geometry, no POI gather.
**Mountain** and **foreign consulate** are *not* gathered here — Google has no
clean mountain icon type and no honorary-consulate flag; source those from OSM
(named `natural=peak`; `diplomatic=consulate` excluding honorary) separately.

## Prerequisites

- Secret **`GOOGLE_PLACES_API_KEY`** — a Google Maps Platform key with **Places
  API (New)** enabled, billing on (first 10k calls/month free; a full Bay Area
  pull is ~2,500 calls → ~$0). Saved at user scope.
- `userRatingCount` is an **Enterprise**-tier field; it's the only way to apply
  the >=5-review rule, so the pull uses that SKU.

## Run

```bash
cd scripts
GOOGLE_PLACES_API_KEY=... python3 fetch_places_poi.py   # -> scripts/poi_full.json (raw, all in-play)
python3 curate_places_poi.py                             # -> poi_curated.json + poi_review.md
```

### `fetch_places_poi.py`
- Reads `../src/data/play-area.geojson.json`; searches its bbox with a
  **recursive quadtree** (any cell returning the full 20 results — the API's hard
  cap, no pagination — is split into quadrants, recursing until <20 or
  `MIN_RADIUS`; cells > `MAX_RADIUS` 50km are pre-split).
- Dedupes by place `id`; keeps pins **inside the polygon** (`in_play`).
- Field mask: `primaryType, location, rating, userRatingCount, businessStatus,
  displayName, formattedAddress, types`.
- **Resumable/incremental** — writes after each category, skips cached ones.
  Delete `poi_full.json` to force a fresh pull. 8-retry backoff (dense categories
  like park/hospital fan out to hundreds of calls).

### `curate_places_poi.py`
- Keeps `userRatingCount >= 5` & not permanently closed.
- Removes the explicit **nested sub-area** lists (`NESTED_REMOVE`), drops
  `NAME_CLOSED`, and surfaces `FLAG_REVIEW` (golf centers / mis-tags) — all
  human-curated dicts at the top of the file; update them when reviewing a new
  pull.
- Writes `poi_curated.json` (the dataset, with `tentacleRadiusMi` per category)
  and `poi_review.md` (summary table + flags + collapsible per-category lists;
  every name links to Google Maps at the pin so the icon can be eyeballed).

## Expected Bay Area result (sanity check)

~2,500 API calls. Final counts after the rule + nested removal:

| category | final |
|---|---|
| museum | 214 |
| library | 237 |
| movie_theater | 85 |
| hospital | 254 |
| zoo | 7 |
| aquarium | 3 |
| amusement_park | 19 |
| park | 2554 |
| golf_course | 77 |

If counts move a lot, an upstream Google categorization changed — diff the review
list before trusting it.

## Next steps (not this skill)

- Build the compact app data file the **POI browser tab** loads, and derive
  per-station attributes (nearest POI + which POIs fall within the tentacle
  radius, per category) during the station rebuild.
- Implement the questions via `add-elimination-question`.

## Gotchas

- Run from `scripts/`; the fetch script reads `../src/data/play-area.geojson.json`.
- `userRatingCount` needs the Enterprise field mask — don't drop it or the rule
  can't be applied.
- Never reintroduce subjective keyword filters (except the rulebook's golf
  mini/range exclusion). Keep the pin, never a centroid.
- `searchNearby` has no pagination — the quadtree is mandatory for dense
  categories (park, hospital, library).
