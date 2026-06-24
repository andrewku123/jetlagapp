---
name: gather-tentacle-poi
description: Gather the Tentacles POI dataset (museums, libraries, movie theaters, hospitals, zoos, aquariums, amusement parks) from Google Places, using the rulebook's "category icon + >=5 Google reviews" legitimacy rule and storing the icon pin coordinate. Use when (re)building the Tentacles POI data for the Bay Area or any new city, or when refreshing it quarterly.
---

# Gather Tentacles POI data (Google Places, icon + review rule)

Tentacles asks: "Of all the ___ within ___ of me, which are you nearest to?"
To answer/eliminate it the app needs, for every Tentacle category, the set of
**legitimate** POIs with their **map-pin coordinate**.

## The rulebook criterion (this is the whole rule — keep it objective)

A place counts as a valid POI of a category **iff**:
1. **It has that category's Google Maps icon** — i.e. Google's place
   `primaryType` is the category (book icon = `library`, ferris wheel =
   `amusement_park`, etc.). We get this for free by filtering the search on
   `includedPrimaryTypes`.
2. **It has >=5 Google reviews** (`userRatingCount >= 5`). Anything with <5
   reviews is assumed illegitimate (a mis-tagged parking lot, a fake listing, an
   internal department, a Little Free Library box, …).

That's it. **Do not add subjective name/keyword filters.** Under this rule a
trampoline park (`amusement_park` icon, 1000+ reviews) and even a pet hospital
(`hospital` icon, 100+ reviews) legitimately count. The rulebook's only escape
hatch is "legitimate unless **all players agree** otherwise" — a human call, not
something to bake into automated filters. We also drop `CLOSED_PERMANENTLY`
places (they no longer exist) and, for sparse categories, *surface* (never
auto-remove) likely **nested sub-areas** for the players to optionally collapse.

Store the **pin** (`location` from the API), **not** a polygon centroid.

## Categories & radii

From the official Medium/Large deck (`TENTACLES` in `src/data/questionSets.ts`):

| radius | categories (`primaryType`) | game sizes |
|---|---|---|
| 1 mi | `museum`, `library`, `movie_theater`, `hospital` | Medium, Large |
| 15 mi | `zoo`, `aquarium`, `amusement_park` | Large only |

("Metro Lines" is also a 15-mi Tentacle but is answered from the existing
transit-line geometry — no POI gather needed.)

### Why the search buffer is 1.5 mi / 15.5 mi, not 1 / 15

The hider is not a point on a station — they're somewhere in the **hiding zone**
around it (radius **0.25 mi** Small/Medium, **0.5 mi** Large). So a POI can be a
valid answer if it's within `tentacle_radius + hiding_zone` of a station. We
gather at the **largest** case so one dataset covers all sizes:
`1 + 0.5 = 1.5 mi` and `15 + 0.5 = 15.5 mi` (`BUFFER_MI = 0.5` in the script).
Trim to 1.25/1.0 later in the elimination logic if needed.

## Prerequisites

- Secret **`GOOGLE_PLACES_API_KEY`** (a Google Maps Platform key with **Places
  API (New)** enabled; billing must be enabled but the first 10k calls/month are
  free and a full Bay Area gather is ~850 calls). Saved at user scope.
- `userRatingCount` is an **Enterprise**-tier field on Places (New); it's the
  only way to apply the >=5-review rule, so the pull uses that SKU. Still free at
  this volume / under the $300 trial credit.

## Run

```bash
cd scripts
GOOGLE_PLACES_API_KEY=... python3 fetch_tentacle_poi.py    # -> scripts/tentacle_poi.json (raw)
python3 curate_tentacle_poi.py                              # -> tentacle_poi_curated.json + tentacle_poi_review.md
```

### `fetch_tentacle_poi.py` — pull every icon-matching place

- Reads station coords from `../src/data/stations.json`.
- For each category, searches the bounding box of all stations (+buffer) with
  `places:searchNearby`, `includedPrimaryTypes=[category]`.
- **Quadtree subdivision** beats the API's hard cap: `searchNearby` returns at
  most **20** results and has **no pagination**, so any cell that comes back with
  the full 20 is split into 4 quadrants and re-searched, recursing until a cell
  returns <20 (or hits `MIN_RADIUS`). Cells larger than `MAX_RADIUS = 50 km` are
  pre-split.
- Dedupes by place `id`, then keeps a place only if it's within
  `(radius + 0.5mi)` of **some** station (union of disks = the hidable+buffer
  area; no wasted scanning where no one can hide).
- Field mask pulls `primaryType, location, rating, userRatingCount,
  businessStatus, displayName, formattedAddress, types`.
- **Resumable & incremental**: writes `tentacle_poi.json` after each category and
  skips categories already present, so a network crash mid-run doesn't force a
  full re-pull. To force a fresh pull, delete `tentacle_poi.json` first.
- Robust backoff (8 retries, longer timeouts) — Google occasionally 429/503s on
  the dense categories (library/hospital each fan out to 300+ calls).

### `curate_tentacle_poi.py` — apply the rule

- Keeps `userRatingCount >= 5` and `businessStatus != CLOSED_PERMANENTLY`.
- **No name filtering.**
- For the sparse 15-mi categories only (`zoo`/`aquarium`/`amusement_park`),
  flags **nested sub-areas** — a kept place within **400 m** of another kept
  place of the same category that has **>=10x** its reviews (e.g. the "Lions"
  exhibit inside SF Zoo, "Shark Experience" inside Aquarium of the Bay). These
  pass the rule and are **kept by default**; they're only listed under "possible
  exceptions" so a human can collapse them into the parent attraction. Do **not**
  run this flag on the dense urban categories — distinct downtown museums
  legitimately sit <400 m apart and would false-positive.
- Writes `tentacle_poi_curated.json` (the dataset) and `tentacle_poi_review.md`
  (per-category: a summary table, the "possible exceptions" list, a collapsible
  full kept list, and the dropped-<5 list — every name is a clickable Google
  Maps link at the pin so a human can eyeball the icon).

## Expected Bay Area result (sanity check)

~840 API calls. After the >=5-review rule:

| category | raw | legit (>=5 reviews) |
|---|---|---|
| museum | 220 | ~151 |
| library | 522 | ~168 |
| movie_theater | 74 | ~64 |
| hospital | 758 | ~194 |
| zoo | 33 | ~16 |
| aquarium | 11 | ~4 |
| amusement_park | 44 | ~29 |

If counts differ wildly, an upstream Google categorization changed — diff the
review list before trusting it.

## Adding a new city

Point `stations.json` at the new city's stations and re-run; the bounding-box +
quadtree adapts automatically. Each city is a one-time ~1–2k call gather (re-run
to refresh). Stagger city refreshes across months to stay under the 10k/month
free tier (~5 cities/month free).

## Next step (not this skill)

Turn `tentacle_poi_curated.json` into per-station Tentacle attributes (nearest
POI + which POIs are within the radius, per category) during the station
rebuild, then implement the question via `add-elimination-question`.

## Gotchas

- Run from `scripts/`; the fetch script reads `../src/data/stations.json`.
- `userRatingCount` requires the Enterprise SKU field mask — don't drop it or the
  rule can't be applied.
- Never re-introduce subjective keyword filters; the rule is icon + >=5 reviews.
- Keep the pin (`location`), never a centroid.
- `searchNearby` has no pagination — the quadtree is mandatory, not optional, for
  dense categories.
