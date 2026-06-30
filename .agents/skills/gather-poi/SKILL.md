---
name: gather-poi
description: End-to-end procedure for building a Jet-Lag-ready POI database (museums, libraries, movie theaters, hospitals, zoos, aquariums, amusement parks, parks, golf courses, foreign consulates, mountains, professional sports stadiums) for ANY play area — collect (OSM-first + minimal Google), curate by the "category icon + >=5 reviews" rule, de-dup (name + footprint + manual overrides), review on an interactive map, and apply to the app. Use when (re)building, quarterly-refreshing, or extending the POI data to a new city/region.
---

# Build a Jet-Lag-ready POI database (any play area)

This is the complete procedure to turn **one play-area polygon** into a clean,
de-duped, per-category POI dataset the game can use. Three question families need
it:
- **Tentacles** — "of all the ___ within R of me, which are you nearest to?"
- **Matching** — "is your nearest ___ the same as mine?"
- **Measuring** — "how far are you from the nearest ___?"

Matching/Measuring have **no radius** (you compare your *nearest*), so the data
must cover the **entire play area**. One full-area build serves all three.

## The one per-city input

The **only** thing that changes between cities is the eligible-station set
(`src/data/stations.json`). `build_play_area.py` turns those stations into the
play-area polygons (see "Defining the play area" below), and everything
downstream — bounding box, point-in-polygon (`in_play`), Google search cells, and
the OSM/Overpass area — is **derived from the play polygon** by `poi_geo.py`. To
build a new city: **drop in that city's `stations.json`, run `build_play_area.py`,
then run the pipeline.** No script hard-codes a city, bbox, or county list.

```python
# poi_geo.py — shared, city-agnostic helpers used by every gather/audit script
play = poi_geo.load_play()                 # 150m-buffered city union (falls back to app polygon)
poi_geo.bbox(play)        -> (lat0,lat1,lon0,lon1)
poi_geo.bbox_swne(play)   -> (S,W,N,E)     # Overpass bbox order
in_play = poi_geo.make_in_play(play)       # even-odd ray cast, holes/ocean handled
```

## The rulebook criterion (keep it objective)

A place counts as a valid POI of a category **iff**:
1. **It has that category's Google Maps icon** — Google's **`primaryType`** is in
   the category's allowlist (book = `library`, ferris wheel = `amusement_park`,
   …). `primaryType` is what actually drives the icon; the secondary `types` array
   does not.
2. **It has >=5 Google reviews** (`userRatingCount >= 5`). Under 5 = assumed
   illegitimate (mis-tagged lot, fake listing, internal department, Little Free
   Library box, …). In cheap/no-review mode this rule is applied **by hand** on
   the de-duped survivors instead.

Do **not** add subjective name filters (a trampoline park or a pet hospital with
the icon + >=5 reviews counts). The only allowed edits:
- drop `CLOSED_PERMANENTLY` (and names that literally say "perm closed");
- **golf only**: rulebook bans mini-golf / driving ranges → name-exclude those,
  and *rescue* real clubs Google mis-primaries (`sports_club`/`country_club` with
  "golf"/"country club" in the name, e.g. SF Golf Club, California Golf Club);
- **movie only**: rescue genuine cinemas Google mis-types (name has
  "cinema"/"cineplex"); keep live performing-arts theaters **out** (no movie icon);
- **nested sub-areas** (a pin that's part of a bigger same-category attraction,
  e.g. "Giraffe Enclosure" inside Oakland Zoo) removed via a human-reviewed list.
- **stadium only**: the rulebook subject is *professional* sports, which Google
  can't encode (the `stadium`/`arena` icon also covers college/high-school/amateur
  fields — the vast majority of hits). So after the icon pass, curate filters the
  category to a **manual `STADIUM_PRO` keep-list** (see Sports stadiums below).

Store the **pin** (`location`), never a polygon centroid.

## Categories (12)

| category | Google `includedTypes` (discovery) | kept `primaryType` (curate allowlist) | tentacle radius |
|---|---|---|---|
| museum | `museum` | museum, art_museum, history_museum, art_gallery | 1 mi |
| library | `library` | library | 1 mi |
| movie_theater | `movie_theater` | movie_theater (+cinema name-rescue) | 1 mi |
| hospital | `hospital` | hospital, general_hospital, medical_center | 1 mi |
| zoo | `zoo` | zoo | 15 mi |
| aquarium | `aquarium` | aquarium | 15 mi |
| amusement_park | `amusement_park` | amusement_park, water_park, amusement_center | 15 mi |
| park | park, national/state/dog_park, garden, botanical_garden | (broad — all kept) | — |
| golf_course | `golf_course` | golf_course (+club rescue, range/mini exclude) | — |
| consulate | `embassy` | embassy (honorary = government_office, excluded) | — |
| mountain | `mountain_peak` | mountain_peak (kept regardless of reviews) | — |
| stadium | `stadium`, `arena` | stadium, arena → then a manual **professional keep-list** (see below) | — |

Discovery uses **`includedTypes`** (matches the full `types` array) so icon-but-
secondary-type places aren't missed; the **`primaryType` allowlist** in curation
then removes the over-inclusion that broad filter causes (urgent-care clinics,
malls, pet stores, Topgolf, etc.). Tentacles also lists "Metro Lines" — answered
from existing transit geometry, no POI gather.

## Prerequisites

- Secret **`GOOGLE_PLACES_API_KEY`** — a Google Maps Platform key with **Places
  API (New)** enabled, billing on.
- Python deps: `requests`, `shapely` (for OSM footprints).
- **Before any paid pull**, in the Google Cloud console: set a low **quota cap**
  (APIs & Services → Places API (New) → Quotas → *requests per day*, e.g. 500) and
  a **budget alert** (Billing → Budgets). The pipeline also caps calls in-script.

## The pipeline (run from `scripts/`)

```bash
cd scripts
# 0. Build the play area from the eligible stations (FREE; see "Defining the play area")
python3 build_play_area.py   # stations.json -> play_area.geojson(+_buffered), app play-area.geojson.json
# 1. Google discovery (paid; use cheap mode by default — see Cost)
POI_NO_REVIEWS=1 GOOGLE_PLACES_API_KEY=... python3 fetch_places_poi.py   # -> poi_full.json
# 2. FREE OSM recall safety net: what Google's pull missed
python3 osm_gap_audit.py                                  # -> osm_gap_candidates.json (+ .md)
#    authoritative registries (3rd source: GeoNames peaks, CMS hospitals, CSV intake)
python3 authoritative_candidates.py                      # -> auth_gap_candidates.json (FREE)
# 3. Cheap icon-verify both candidate sets (no review fields), then fold survivors in
GOOGLE_PLACES_API_KEY=... python3 verify_gap_icons.py     # OSM gaps -> poi_gap_verified.json
GOOGLE_PLACES_API_KEY=... CAND_FILE=auth_gap_candidates.json OUT_FILE=poi_auth_verified.json \
  CACHE_FILE=poi_auth_cache.json SOURCE_TAG=authoritative python3 verify_gap_icons.py
POI_NO_REVIEWS=1 python3 curate_places_poi.py             # -> poi_curated.json (+ poi_review.md)
python3 apply_gap_backfill.py                             # folds poi_gap_verified.json in
IN_FILE=poi_auth_verified.json SOURCE_TAG=authoritative python3 apply_gap_backfill.py
# 3b. Auto-drop closed places: query each pin's Google businessStatus (cheap; cached)
GOOGLE_PLACES_API_KEY=... python3 refresh_business_status.py   # annotates poi_curated.json
# 4. De-dup (OSM footprints + name + manual overrides; drops CLOSED_* pins)
python3 fetch_osm_polys.py                                # -> osm_polys_<cat>.json (FREE)
python3 dedup_poi.py                                      # -> poi_deduped.json, poi_merge_viz.js
```

### 1. `fetch_places_poi.py` — Google discovery
- Reads the play polygon; searches its bbox with a **recursive quadtree** (any
  cell returning the full 20 results — the API's hard cap, no pagination — splits
  into quadrants until <20 or `MIN_RADIUS`; cells > `MAX_RADIUS` 50km pre-split).
- Uses **`includedTypes`** per category; dedupes by place `id`; keeps pins
  **inside the polygon** (`in_play`). Resumable: writes after each category, skips
  cached ones; delete `poi_full.json` to force a fresh pull. 8-retry backoff.
- **`POI_NO_REVIEWS=1`** drops `rating`/`userRatingCount` from the field mask →
  cheaper SKU (see Cost).

### 2. `osm_gap_audit.py` — free recall safety net
A one-time Google pull always has recall holes (see **Why pulls miss places**).
OpenStreetMap is an **independent, free** source, so we diff it against ours: for
each category it pulls named OSM features in the play area (`tourism=museum`,
`amenity=library`, `leisure=golf_course`, `natural=peak`, `diplomatic=consulate`,
…) and lists every one with **no pin within 300m** (or name-match within 1.5km) of
ours. Output `osm_gap_candidates.json` is the candidate set; `osm_gap_audit.md` is
the human-readable list with Google-Maps links. **No Google calls.**

### 3. `verify_gap_icons.py` — cheap icon check + `apply_gap_backfill.py`
For each gap candidate, **one `searchText`** call **biased to the OSM coordinate**,
with a field mask that **omits review fields** (cheaper SKU). Keep it only if
Google returns a place at ~that spot whose `primaryType` is the category icon
(same allowlist + golf/cinema rescue). Safety: **hard `MAX_CALLS` cap** and every
result **cached to disk**, so a restart never re-spends. `apply_gap_backfill.py`
then folds the icon-verified survivors into `poi_curated.json`, flagged
`source=osm_backfill, userRatingCount=None` — the human applies the >=5-review
rule to them by hand. (Bay Area: 260 candidates → **33** carried a real icon.)

### 2b/3b. `authoritative_candidates.py` — official registries (3rd source)
A second free discovery source on top of OSM: **official public registries**. It
normalizes each to the same `{name, lat, lon, query?}` candidate shape and
gap-filters against our pins, so the survivors flow through the **same**
`verify_gap_icons.py` icon-check (run it again with `CAND_FILE=auth_gap_candidates.json`).
The Google icon rule still governs — registries only widen recall.
- **Built-in automated:** `mountain` ← GeoNames country dump (codes PK/MT, real
  coords); `hospital` ← CMS Hospital General Information (address-only → the
  icon-check geocodes via `searchText`).
- **Generic CSV intake:** drop any list as `auth_lists/*.csv` with columns
  `category,name,city,state[,lat,lon]` and it's picked up — this is the
  source-agnostic path for consulates / museums / libraries / zoos / parks and
  for **any city or country** (see the source tables below). Address-only sources
  need the play area's admin areas (`US_COUNTIES` in the script) as a coarse
  pre-filter; precise filtering is the polygon `in_play` check on the Google hit.
- Bay Area result: GeoNames + CMS surfaced 62 gap candidates → 30 icon-verified →
  **0 net-new** (all already had Google IDs in our set) — confirming Google+OSM
  already cover those registries here. The **consulate** CSV (35 official Bay Area
  consular offices via `fetch_consulates_fco.py`) → 22 gap → 21 icon-verified →
  **+3 net-new** (Ecuador, Honduras, Nicaragua) Google's search missed. So the
  authoritative layer's payoff is category-dependent: nil where Google is strong,
  real where its search is weak (consulates).
- Full Bay-Area authoritative sweep result (net-new added back): **consulates +3**
  (Ecuador, Honduras, Nicaragua); **museums +38**, **libraries +2** (IMLS, below);
  mountains / hospitals / zoos / aquariums **+0** (Google+OSM already cover those
  registries here). parks deliberately **not** run: PAD-US is protected-area
  *boundaries*, not Google park-icon POIs, and OSM already has >2000 — it would
  mostly produce non-icon candidates the check drops.
- **IMLS museums + libraries (via ArcGIS, NOT imls.gov):** imls.gov never loaded
  from this env (301→000/timeouts), so instead query the IMLS-derived **ArcGIS
  feature layers** by bbox (free, no key) — `fetch_imls_arcgis.py`:
  museums ← the "GLAMs" layer (`TYPE_MAIN='MUS'`, derived from IMLS's MUDF),
  libraries ← the IMLS PLS "Public Library Outlet" layer (real per-outlet coords).
  Bay-Area run: museum **502 raw → 406 gap → 162 icon-verified → +38 net-new**
  after Google-id dedup (the other ~124 icon hits were pins we already had under a
  different name, e.g. "M.H. de Young" vs "de Young Museum"); library
  **230 raw → 66 gap → 27 icon-verified → +2 net-new**. ~472 no-review calls (~$15).
- Takeaway (use this to decide per future city): the authoritative layer earns its
  keep on **(a) address/registry categories where Google's area-search is weak
  (consulates)** and **(b) museums (IMLS MUDF/GLAMs gave the biggest single-source
  lift, +38 ≈ 18%)**. It is confirmation-only (+0/+2) for hospitals, mountains,
  zoos, aquariums, and **libraries** (PLS is clean but redundant with OSM+Google —
  skip it to save the spend). Caveat: MUDF/GLAMs is over-inclusive (art galleries,
  historical societies, dept collections), so the +38 needs a **manual legitimacy +
  ≥5-review pass** — expect to prune a chunk. So: for a new US metro, run
  **consulates + museums** authoritatively; treat the rest as an optional cheap
  sanity check.

### 4. `curate_places_poi.py` — apply the icon allowlist + review rule
- Keeps only `primaryType in ALLOW[cat]` (+ golf/cinema rescue); applies
  `userRatingCount >= 5` (skipped under `POI_NO_REVIEWS=1`); drops permanently
  closed; removes the human-reviewed `NESTED_REMOVE` sub-areas; surfaces
  `FLAG_REVIEW` for eyeballing. Writes `poi_curated.json` + `poi_review.md`
  (every name links to Google Maps at the pin so the icon can be checked).

### 4b. `refresh_business_status.py` — auto-drop closed places
The icon pull (`poi_full.json`) carries Google's `businessStatus`, and curate
drops `CLOSED_PERMANENTLY`/`CLOSED_TEMPORARILY`. **But the backfilled pins**
(authoritative IMLS + OSM gap recall) are injected straight into
`poi_curated.json` from external sources with `businessStatus: None` — they never
had their status checked, which is how closed places (Madame Tussauds, Habitot,
Carquinez Toy Train, …) used to slip past the audit and waste manual-review time.
- This step queries **Place Details with just the `businessStatus` field** (the
  cheapest SKU) for every pin that has a Google `id` but no status, caches the
  answer by `place_id` in `poi_bizstatus_cache.json` (statuses rarely change, so
  reruns are ~free), and writes it back into `poi_curated.json`.
- `POI_REFRESH_ALL=1` re-queries **every** pin (not just status-less ones) to
  catch places that closed since the last pull — worth running each quarterly
  refresh. A full Bay-Area pass (~3.8k pins) typically flags ~70 closed.
- `dedup_poi.py` then drops only `CLOSED_PERMANENTLY` pins up front (one
  chokepoint for all sources). Manual `drop` overrides that target a now-
  perm-closed pin are silently skipped (not warned).
- **`CLOSED_TEMPORARILY` is deliberately NOT auto-dropped** — Google's temp-closed
  flag is frequently stale (e.g. The Beat Museum, the 49ers Museum read
  "temporarily closed" but are open). Those pins stay in the dataset and surface
  on the review map for a human to judge; drop them by override only once
  confirmed actually gone. Only `CLOSED_PERMANENTLY` is trusted as "really closed."
- So you still need manual `drop` overrides for: (a) temp-closed pins you confirm
  are gone, (b) places Google reports `OPERATIONAL` but are actually closed
  (**stale Google data**, e.g. Aléna Museum), and (c) legit-but-unwanted pins.
- **Limit:** closure status alone can't replace the human eyeball pass — Google
  data lags both ways. Use it to delete the confident (perm) closures
  automatically, then audit the rest.

#### Verifying the `CLOSED_TEMPORARILY` pins (web search, not review age)
Since temp-closed is kept-for-review, you need a cheap way to triage which of those
pins are *actually* gone vs just stale flags. Two tiers, weakest first:
- **Review-recency proxy** (Place Details `reviews` field, Atmosphere SKU ~$0.017/call,
  one-off — do NOT bake into the cached refresh): a temp-closed pin with a review in
  the last ~2 months is almost certainly open; >1yr or none = suspicious. Good for
  *businesses* (museums/theaters/hospitals), **unreliable for parks & libraries**
  (they get few reviews even when wide open — e.g. El Cerrito Historical Society, an
  appointment-only history room, looked "closed" by review age but is open).
- **Real web search per pin (authoritative — prefer this).** Search each pin
  ("<name> <city> open or permanently closed") and read the **operator's own site /
  Google listing / local news**: the live "temporarily/permanently closed" label and
  any reopening date. This beats review age both ways — it correctly *keeps* low-review
  public places and *catches* genuine closures. Findings cluster into:
  - **Stale flag → KEEP** (the ~90% case): open now, Google just never cleared it.
  - **Renovation / seismic / seasonal → KEEP**: really closed *today* but a dated
    reopening exists (Beat Museum retrofit, Antioch Water Park, San Mateo Marina &
    Oakland Brookfield libraries, SJSU Thompson Gallery summer pause). The game wants
    these in.
  - **Genuinely gone → DROP**: closed with no reopening / under legal fight to reopen
    (Seton Coastside — ER+SNF shut since 2024).
  - **Not a real public POI → DROP**: turns out to be a digital repository or a
    defunct/restricted campus facility (NASA "Life Sciences Library" = the online
    NSLSL database; Patten University Library = online-only school, campus library
    defunct). Flag genuinely borderline ones (NDNU/Gellert: campus sold to UC, leasing
    back ≤5 yrs) for the human rather than dropping.
  Encode confirmed-gone pins as manual `drop` overrides (perm-closed ones auto-drop
  and need none). Re-run this per quarterly refresh on the temp-closed set only.

### 5. De-dup — `fetch_osm_polys.py` + `dedup_poi.py`
Google lists one physical place as many pins (a hospital = main building + ER +
each entrance + departments + co-located clinics). `dedup_poi.py` collapses them:
1. **name pass** — proximity-gated union of "real" pins sharing a *distinctive*
   (non-`GENERIC`) word and same-name / token-subset / co-located (<60m).
2. **sub-part pass** — entrances/parking/buildings absorb into the nearest rep.
3. **OSM-footprint pass** — reps inside the SAME OSM polygon collapse
   (`osm_polys_<cat>.json` from `fetch_osm_polys.py`, FREE).
4. **manual overrides** — reviewer decisions from `poi_dedup_overrides.json`, last.

Representative ("main") pick (`rep_score`, most-decisive first) — designed so
**future cities pulled with no review counts still pick a sensible main pin**:
1. reviewer-named merge `parent` (explicit keep).
2. a real pin over a structural sub-part.
3. most reviews — **only decides when review counts exist**; in no-review mode all
   tie at 0 and 4–7 take over.
4. **not** a clinical specialty/department name (`_SPECIALTY_RE`: "Internal
   Medicine …", "Pediatrics …", "Imaging …", "Chemical Dependency …") — a
   department is never the main, even if it carries an anchor noun.
5. carries the category's flagship noun (`ANCHOR`, e.g. hospital → "medical
   center"/"hospital", museum → "museum", park → "regional/state park").
6. a clean, **unqualified** name — no `:` / `|` / trailing `(…)` parenthetical
   (`has_qualifier`), so "Sunnyvale Center" beats "Sunnyvale Center (401)".
7. shorter name.

To add a city/category: extend `ANCHOR` with that category's headline noun(s) and
`_SPECIALTY_RE` with any new department lead-ins. The reviewed Bay-Area set is
unchanged by 4–7 (rule 3 dominates while reviews exist); they only steer the
no-review path. Outputs `poi_deduped.json`, `poi_dedup_review.md`, and
`poi_merge_viz.js` (data for the review map `poi_merge_viz.html`).

#### Campus heuristics (HOSPITAL ONLY — `CAMPUS_CATS`)
Hospital systems list one campus as many strongly-named pins (`Kaiser Permanente
Walnut Creek: Chemical Dependency Services`, `Family House: UCSF Benioff ...`,
`UCSF Medical Records`). The plain name pass misses these because `norm()` keeps
only the pre-`:` head. So `dedup_category(..., campus=True)` (set for
`CAMPUS_CATS = {"hospital"}` in `main()`) adds two extra moves, both keyed on
`distinctive_full()` — brand/place words over the **whole** name (minus
`GENERIC`+`STRUCTURAL`), so the `:`-tail identity still counts:
- **≥2 shared brand words within `BRAND2_D` (700m) ⇒ same complex** (union). The
  two SCVMC and the John Muir Walnut-Creek-vs-Concord pairs sit >700m apart, so
  they stay distinct.
- **minor-satellite absorb:** a pin with `< MINOR_MAX` (60) reviews sharing ≥1
  brand word with a *stronger* anchor within `BRAND1_D` (500m) is absorbed into
  the **nearest** such anchor (e.g. `UCSF Medical Records`→`UCSF Medical
  Center`, `Kaiser ... Child/ado Psy`→`Kaiser Santa Clara`). Only minor pins
  move and only toward a stronger one, so two well-reviewed distinct hospitals
  are never joined.

**Over-merge trap — why this is hospital-only.** An earlier version ran the
whole-name brand match on *every* category and falsely merged distinct generic
places that merely share a descriptor: parks (`Brisbane Dog Park` +
`Clayton Dog Park` on "dog"), museums (`... Historical Society` on "historical",
`Museum of Children's Art` + `Sneaker Museum` on "museum"). For hospitals a
shared brand word ("Kaiser", "UCSF") is real identity; for parks/museums it is
just a category descriptor. So campus stays gated to `CAMPUS_CATS`; every other
category keeps only the conservative pre-`:` `distinctive()` name pass + the OSM
footprint pass. To extend campus to a new category, only do so if its pins carry
a real shared *brand/place* name (not a generic descriptor), and re-validate.

**Validate after any change** with `validate_merges.py`: it re-runs the dedup
with the manual MERGES removed (separates kept as a safety net) and reports, per
category, how many ground-truth merges the auto-logic now catches on its own,
plus **0 separate-override violations** and **0 over-merges** (a pair the target
keeps apart that auto-logic joins) as hard gates. Current Bay Area: 18/32
hospital merges auto-caught, generic counts unchanged.

### 6. Review — interactive map
Deploy `poi_merge_viz.html` + `poi_merge_viz.js` to `public/poi-review/` (see the
`deploy-hideandseek` skill / PR-preview). Multiple reviewers open one URL; legend:
green = kept, **red spoke = name merge**, **orange = OSM footprint**, **purple =
manual override**. Reviewers send merge/separate corrections → record them in
`poi_dedup_overrides.json` and re-run `dedup_poi.py` (the map cache-busts its data
on load, so corrections show without a hard refresh).

### 7. Apply to the app
Once reviewers sign off, write `poi_deduped.json` into the app's `poi.json` and
wire the categories into the POI tab (see `build_poi_data.py` / the POI-tab PR).

## Defining the play area (which cities are in play)

The play area is **not** a hand-drawn boundary or a county list — it is the
**union of the Census places (city / town / CDP) that transit actually serves**,
computed by `build_play_area.py` straight from `stations.json`. This keeps the
playable area tight (only places you can realistically reach/hide near a station),
which also means far fewer POIs to audit. **Use this same rule for every city.**

A place is **in play** if ANY of:
1. **Station-city** — it contains an eligible station.
2. **Reachable / hideable** — any part of it lies within one hiding-zone radius
   (`hide_radius_mi`, the *largest* game size — 0.5 mi for the Bay Area, so it
   covers all smaller game sizes) of an eligible station. Catches places whose
   station sits just over the line (e.g. Dublin → Dublin/Pleasanton BART).
3. **Transit-enclosed enclave** — it is surrounded by in-play places: >30% of its
   perimeter is adjacent to in-play places and <12% adjacent to out-of-play
   places. Keeps islands/enclaves (Alameda, Foster City, Newark, Emeryville,
   Piedmont, East Palo Alto…) while excluding open-space border towns (Los Altos,
   Moraga, Danville…).
4. **Manual keep** — listed in `play_area_overrides.json` `"keep"` (escape hatch;
   Bay Area keeps Cupertino). `"drop"` is the opposite override.

The play-area polygon is **whole-place granularity** — the union of the *entire*
kept place polygons, no raw circular disks. When a station's hiding zone protrudes
out of its own city, rule 2 ("reachable") has already pulled in the **whole**
neighbouring place the zone reaches (e.g. the Dublin/Pleasanton BART disk → both
Dublin and Pleasanton whole-in), so the boundary stays on clean city limits
instead of painting a circle bump into open space. (An earlier version unioned in
the bare disks; that left ugly circles poking into unincorporated open space, so
we reverted to whole-place.)

One geometry step is applied to the union: **fill fully-enclosed holes**
(`fill_holes`). Any pocket ringed on all sides by in-play land is itself in play —
surrounded ⇒ in (e.g. San Bruno Mountain between Daly City/Colma/Brisbane/South
San Francisco, and the unincorporated pockets around Fremont/Newark/Union City).
Concave bays that open to the outside are not interior rings, so far open space
(the East Bay hills, which open east to out-of-play land) stays out.

This drops the no-rail sprawl (Gilroy, Morgan Hill, Half Moon Bay, Livermore, San
Ramon, Brentwood, Los Gatos, Saratoga…) — exactly the clutter we don't want.

**Clipping is strict, with one buffer.** `dedup_poi.py` clips every POI to the
play area before dedup:
- **Parks & mountains (`NATURAL_CATS`) — strict:** must be inside the raw
  play-area polygon (`play_area.geojson` — the whole-place union plus filled
  holes), no shoreline buffer. This deliberately drops big open-space landmarks
  that sit in *out-of-play* unincorporated land (Mt. Diablo, Mission Peak, Tilden,
  Mt. Tam, Rancho San Antonio…), emptying most of the mountains category. That is
  intended. Note open space that is *surrounded* by in-play land (a filled hole,
  e.g. San Bruno Mountain) is in play and its parks/mountains are kept.
- **All other categories — 150 m shoreline buffer** (`play_area_buffered.geojson`)
  so waterfront/pier pins that belong to an in-play city but sit just off the land
  polygon survive (Exploratorium, USS Hornet, USS Pampanito, Musée Mécanique…).
  Discovery (`poi_geo`) also uses the buffered union so these are *found* in the
  first place.

**Outputs of `build_play_area.py`:** `play_area.geojson` (raw whole-place union +
filled holes, used for the strict clip), `play_area_buffered.geojson` (150 m
buffer, used for discovery + the non-natural clip), `play_area_cities.json` (the
keep list + why each qualified), and a **simplified** copy written to the app's
`src/data/play-area.geojson.json` (display only — out-of-play dimming mask +
satellite clip; the app no longer uses counties for the play area). The review map
draws the `play_area.geojson` boundary as a blue outline.

**Bay water is added to the app copy only.** `bay_water()` traces the open San
Francisco Bay (central + south bay, plus the East-Bay channel up to ~Richmond),
subtracts the land places to snap to the real shoreline, and is unioned **only**
into the simplified app `play-area.geojson.json` so the bay renders as water
instead of grey. Its north-west edge (the corridor's closing edge) is a near-N/S
line just **east of Alcatraz / Angel Island**, so the Marin side (Sausalito,
Tiburon, Angel Island) and San Pablo Bay north of Richmond stay grey, while the
north-SF waterfront water and the central channel up to Richmond are in. It is
deliberately **not** in `play_area.geojson`, so it never affects POI clipping or
which places are in play. For a new city, retrace `BAY_CORRIDOR_LL`/`BAY_SEEDS_LL`
(or drop the bay step) to match its waterways.

## Sports stadiums (professional only)

Stadiums power the Matching ("is your nearest sports stadium the same as mine?")
and Measuring ("…closer/further from a sports stadium?") subjects — **not**
Tentacles (no radius). The Jet Lag subject is **professional sports**, so:

1. **Discovery + icon** are normal: `fetch_places_poi.py` pulls `includedTypes =
   [stadium, arena]`; curate keeps `primaryType in {stadium, arena}`. This is the
   right *icon* but far too broad — it returns every college/high-school/amateur
   field too (Bay Area: 75 icon-passing → only **8** professional).
2. **Professional keep-list (the per-city judgment):** in `curate_places_poi.py`,
   `STADIUM_PRO` is a `{place_id: display_name}` dict of the venues **currently
   played in** by a **pro / minor / independent-league** team. The curate loop
   filters the stadium category to exactly these IDs and **relabels** to the
   display name. `stadium` is in `KEEP_ALL` (skips the ≥5-review rule — legitimacy
   comes from the keep-list, and stadiums are pulled no-reviews).
   - **Rule for what qualifies:** pro / minor / independent leagues all count
     (MLB/NBA/NFL/NHL/MLS/WNBA/NWSL, **and** MiLB, AHL, USL, IFL, indie ball, …).
     It must be a team's **current** home — **no historic venues** (e.g. Kezar,
     former 49ers home, is now amateur → excluded; Oakland Arena / Cow Palace have
     no current pro tenant → excluded).
   - **Key on `place_id`, not name** — names drift (Levi's Stadium shows as a Super
     Bowl placeholder "San Francisco Bay Area Stadium"), so we relabel.
3. **For a NEW CITY:** run discovery, open the icon-passing list on the review map,
   and rebuild `STADIUM_PRO` with that city's currently-active pro/minor/indie home
   venues (look up each venue's current tenant). Then re-run curate → dedup.
4. Wire into the deck: add `Sports Stadium`/`A Sports Stadium` cards to
   `src/data/questionSets.ts` (MATCHING + MEASURING) and to the reference-PDF deck
   lists in `make_reference_pdf.py` (`("Sports stadium", False)` /
   `("A sports stadium", False)` — `False` = not yet auto-eliminated).

## Manual overrides (`poi_dedup_overrides.json`)

When a reviewer finds a wrong/missed merge the rules can't safely get, record it
here — **never special-case names in code**:

```json
{ "library": {
    "merge":    [["Main (Gardner) Stacks", "Doe Library"]],
    "separate": [["C.V. Starr East Asian Library", "Earth Science & Map Library"]]
} }
```
- `merge` = force `[child, parent]` into one (use when names share no distinctive
  word, e.g. a parenthesized name `norm()` strips). The named **`parent` is kept
  as the surviving pin** — it wins rep selection and is exempt from satellite
  absorption even if a co-located sibling has more reviews, so the reviewer's
  chosen pin is the one that survives.
  When the `parent` name is **ambiguous** (two same-named pins, e.g. two
  `Telegraph Hill` peaks), append the parent's coords:
  `[child, parent, lat, lon]` — `resolve_near` pins which duplicate survives.
- `separate` = force `[a, b]` to never merge (two distinct same-category places
  wrongly joined).
- `rename` = `[old, new]` or `[old, new, lat, lon]` to also relocate the pin.
- `drop` = remove a pin entirely; `[name]` if unique, else `[name, lat, lon]` to
  pin the exact one in a chain (Sky Zone, ABC Tree Farms, …) the reviewer flagged.
- Matched case-insensitively, `&`/`+`-tolerant, against the real
  `poi_curated.json` names; unresolved ones print `WARN` and are skipped.
- Prefer a **generic fix** first if a whole class is wrong (e.g. two libraries
  merging on the word "library" → add "library" to `GENERIC`). Use a per-pair
  override only for genuine one-offs.

## Cost & the cheap blend (OSM-first + minimal API + manual)

Billing reality (Places API New — confirm in **Billing → Reports → group by
SKU**): there is **no ~$3/1k tier** for *discovery*. Search SKUs are **Pro
(~$32/1k)** and, once you add `rating`/`userRatingCount`, **Enterprise (~$35/1k)**.
The cheap Place-Details Essentials tier is for refreshing known IDs, not
discovery. The real cost driver is **call count** (the quadtree fan-out), and a
full review-mode pull is a few thousand calls (Bay Area's first build ≈ $190 —
don't repeat that).

**The cheap, sustainable blend (use this):**
- **OSM/Overpass = $0** for discovery (`osm_gap_audit.py`) and footprints
  (`fetch_osm_polys.py`). It's also the safety net for Google's recall holes.
- **Google = minimal & capped**: prefer `POI_NO_REVIEWS=1` (Pro SKU) for the
  full pull, and the **icon-only `searchText`** (no review fields) for gap
  verification — only on the gap set, hard-capped. A whole new city ≈ the OSM diff
  ($0) + a few hundred no-review lookups (a few $).
- **Reviews**: handled by one of two procedures below (A is the current default).
- Always set the console quota cap + budget alert.

### The >=5-review check — two procedures

Review count is the one fact only Google can give us, and Google charges for it on
every endpoint. Choose how to pay for it — money or human time:

**Option A — manual (default, ~$0).** Pull in `POI_NO_REVIEWS=1` mode so no review
fields are ever bought. After de-dup, the reviewer opens the review map and, for
each surviving pin, clicks through to Google and confirms **>=5 reviews** (skip
`mountain` — kept regardless). Drop the failures by adding them to the dedup
overrides / a drop list. De-dup runs first, so this is the survivor set, not the
raw firehose, but it is real eyeballing. This is the active mode.

**Option B — survivors-only review top-up (~$60-70 one-time, zero rating
eyeballing).** Same cheap no-review pulls, then run `topup_reviews.py` AFTER
de-dup: it fetches `userRatingCount` via **Place Details by ID for only the
de-duped survivors** (the smallest possible set), drops anything < 5 (keeps
`mountain`), and writes `poi_deduped_reviewed.json`. The reviewer then only
confirms merges — no rating-checking. Hard `MAX_CALLS` cap + on-disk cache so a
restart never re-spends; set the quota cap + budget alert first.

```bash
GOOGLE_PLACES_API_KEY=... python3 topup_reviews.py   # -> poi_deduped_reviewed.json
```

(Why B is cheaper than re-pulling with reviews: it pays for review counts on the
~few-thousand *survivors*, not on every raw pin in the firehose. Switch A->B only
when the user asks.)

### How complete is this? (OSM vs Google — they are NOT nested)

Do **not** assume OSM is a strict superset of Google or vice-versa — neither
contains the other. They are **complementary**:
- OSM is usually *richer* for **mountains/peaks, parks, trails, gardens** and many
  civic places (libraries, museums) — community/enthusiast mapped.
- Google is usually *richer/more current* for **businesses** — movie theaters,
  hospitals, golf courses — and anything with reviews.

What the pipeline guarantees: the final set = Google's area-search results **plus**
any OSM-named place that Google's search missed *and* that still passes a Google
`searchText` icon lookup (step 3-4). So OSM **widens recall** (catches Google's
search holes), and the Google icon-check **keeps precision** (an OSM place not on
Google, or without the icon, is dropped — we never invent POIs OSM-only).

The irreducible hole: a place on **neither** Google's area-search **nor** OSM is
never seen. OSM only helps to the extent it lists places Google's search missed —
it does not need to be a superset, just to contain *some* of the misses. For a
business category where OSM is thin, OSM adds little, so the residual risk is
Google-search's own recall holes; mitigations, strongest first:
1. The OSM diff (free) — already in the pipeline.
2. For a high-stakes category, union an **authoritative list** (e.g. consulates →
   the official diplomatic directory; hospitals → the state's licensed-hospital
   list; peaks → USGS GNIS), then icon-check those names the same way.
3. Human spot-checks on the review map (you already do this).
No automated pipeline is provably complete; two independent sources + manual
review is the practical ceiling.

## Authoritative source registry (per category, per country)

The third discovery source. Feed any of these through `authoritative_candidates.py`
(built-in for the starred ones) or the generic `auth_lists/*.csv` intake, then the
icon-check. Verified reachable as of this writing; deep links rot — search the
agency if a URL 404s.

**United States**
| category | source | access |
|---|---|---|
| mountain ★ | USGS GNIS / GeoNames `US.zip` | `download.geonames.org/export/dump/US.zip` (coords) |
| hospital ★ | CMS Hospital General Information | `data.cms.gov` dataset `xubh-q36u` (JSON API; address) |
| hospital (alt) | HIFLD Hospitals | hifld-geoplatform (ArcGIS; coords) — endpoint moves |
| museum ★ | IMLS MUDF via the ArcGIS "GLAMs" layer | `fetch_imls_arcgis.py` queries the GLAMs FeatureServer by bbox (`TYPE_MAIN='MUS'`, coords) → `auth_lists/museum.csv`. **Use the ArcGIS layer, not imls.gov (which timed out / 000 from this env). +38 net-new in the Bay Area — biggest single-source lift; but over-inclusive, needs manual pruning.** |
| library | IMLS PLS via the ArcGIS "Public Library Outlet" layer | `fetch_imls_arcgis.py` queries the PLS FeatureServer by bbox (real per-outlet coords) → `auth_lists/library.csv`. **Only +2 net-new — clean but redundant with OSM+Google; low priority.** |
| zoo / aquarium ★ | AZA current accreditation list | `fetch_zoos_aza.py` scrapes aza.org → `auth_lists/zoo_aquarium.csv` |
| consulate ★ | US Congressional Directory "Foreign Diplomatic Offices" (govinfo) | `fetch_consulates_fco.py` parses the PDF → `auth_lists/consulate.csv` |
| park | USGS PAD-US / TPL ParkServe | usgs.gov PAD-US; tpl.org — **GIS boundaries, not Google park-icon POIs; OSM already has thousands; opt-in only (skipped — would mostly drop at icon-check)** |

**Canada** (verified reachable)
| category | source | access |
|---|---|---|
| mountain | GeoNames `CA.zip` / CGNDB (Canadian Geographical Names DB) | `download.geonames.org/export/dump/CA.zip`; open.canada.ca |
| hospital | StatCan **ODHF** (Open Database of Healthcare Facilities) | statcan.gc.ca/en/lode/databases/odhf (coords; many facility types) |
| consulate | Global Affairs Canada — foreign representatives in Canada | international.gc.ca/protocol-protocole/reps.aspx |
| zoo / aquarium | **CAZA** accredited members | caza.ca |
| museum / library | provincial directories / Canadian Museums Assoc. | no single national open file → CSV intake |
| park | CARTS / provincial park datasets | open.canada.ca → CSV intake |

**No authoritative public list anywhere** (rely on Google + OSM): `movie_theater`,
`golf_course`, `amusement_park` — there's no government registry; only commercial
or community sites (e.g. Cinema Treasures), which we don't treat as authoritative.

To add a country: point `GEONAMES_COUNTRY` at its dump, set the admin-area
pre-filter, and drop its registries as CSVs. Everything else is unchanged.

## Why one-time Google pulls miss places (and why OSM is the fix)

A `searchNearby`/`includedTypes` pull is **not buggy** — at a place's real
coordinate it returns it. Misses come from:
1. **Data drift** — the place was added/retyped on Google *after* the pull (this
   is what hid Washington Township Museum; OSM already had it).
2. **Mis-primary type** — Google primaries it as a non-category type, so
   `includedTypes` never surfaces it (SF Golf Club = `sports_club`). The curate
   rescue handles the known classes; OSM catches the rest.
3. **20-result cap** in dense cells (mitigated by the quadtree, but edge cases
   slip through).

None are fixed by "call the API harder." The robust, cheap fix is the **free OSM
diff** (step 2) as a recurring safety net + a tiny capped icon check (step 3).
Re-run those two each refresh; they cost ~nothing and catch drift.

## Gotchas

- Run from `scripts/`; everything reads `../src/data/play-area.geojson.json`.
- New city = swap that one file. If a station sits within the largest hiding-zone
  radius (0.5mi) of the play border, add an edge buffer (Bay Area needs none).
- `searchNearby` has **no pagination** — the quadtree is mandatory for dense
  categories (park, hospital, library).
- Keep the **pin**, never a centroid. Never reintroduce subjective keyword filters
  (except the rulebook golf range/mini exclusion + golf/cinema name-rescue).
- Don't push commits touching `.github/workflows/` with the scoped PAT (no
  Workflows permission).
```
