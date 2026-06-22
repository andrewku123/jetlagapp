---
name: rebuild-station-dataset
description: Regenerate the Bay Area eligible-station dataset (src/data/stations.json) from the GTFS/OSM source data. Use when transit data changes, when stations need re-deduping/re-merging, or when the service-frequency or line rules need updating.
---

# Rebuild the station dataset

The app's only data input is `src/data/stations.json` — an array of enriched
`Station` records (see `src/types.ts`). It is produced by a three-stage pipeline
in `scripts/`. Run the stages in order from inside `scripts/`.

## What each station record contains

`id, name, lat, lon, systems[], lines[], aka[], nameLength, county, city,
elevation, airportDist{SFO,OAK,SJC}, nearestAirport, service{wd,we}` where each
`service` entry is `{served, hourly}`.

## Pipeline

Run everything with the working directory set to `scripts/`:

```bash
cd scripts
python build_stations.py     # 1. build + dedup + cross-system merge -> stations.json
python build_attributes.py   # 2. enrich (county/city/elevation/airport) -> src/data/stations.json
python patch_lines.py        # 3. add canonical BART color lines into src/data/stations.json
```

### 1. `build_stations.py` — assemble + dedup
Inputs (all relative to `scripts/`):
- `gtfs/bart/stops.txt` — BART GTFS (`location_type == 1` rows are stations).
- `caltrain_service.json` — authoritative Caltrain stops with per-day `served`/`hourly` flags, SF (4th & King) → Tamien. **College Park is intentionally absent** (peak-only flag stop, can never meet the hourly rule — do not re-add it).
- `raw_vta.json` — OSM light-rail relations + nodes.
- `raw_muni.json` — OSM relations for Muni N/J/F/K/L/M/T.

Key rules baked in (keep these):
- **Muni = every rail stop** (labeled + unlabeled "Other Stop" dots), deduped **within Muni**: identical stop name clusters together at any distance; otherwise nearest cluster `< 150 m`. Shared subway stops get canonical display names via the `RENAME` dict. Curated drops (keep them):
  - **North Beach (T)** (not in service / not in OSM).
  - The **F-only surface stops on Market St inland of Embarcadero** (any F-only cluster whose name starts with `Market Street &`) — they run directly above the Muni Metro subway and duplicate those stations.
  - The **F node at Market & Stockton** (the F does not stop at Union Square/Market, the Central Subway T station).
  - **NOT Glen Park** — the J's surface stop there (tagged `Glen Park` in OSM) is real and is **kept**, then renamed via `RENAME` to `San Jose Ave/Glen Park Station`. It stays a **separate** Muni-only station from Glen Park BART (see cross-system merge).
- **Cross-system merge is CURATED, not distance-based** (`SHARED_STATIONS` allow-list + `shared_anchor`, `MERGE_RADIUS_M = 250`). Two stops of *different* agencies merge **only if both sit within 250 m of an official "Shared Station" anchor** read off the transit maps (`merge_service` ORs the service flags); the unchanged `isdisjoint` check stops a third same-agency stop from being absorbed. This is what makes 4th & King = Caltrain + Muni, Balboa Park = BART + Muni, Milpitas = BART + VTA, etc. **Proximity alone never merges** — Glen Park BART and the San Jose Ave Muni J stop are ~80 m apart but split by I-280 and shown as two stations on the SFMTA map, so they are NOT in the list and stay separate. **The anchor list is a human judgement call: when adding a city, review every shared station against that system's official map and add anchors by hand — do not reinstate an automatic distance rule.**
- **Disambiguation**: stations sharing a display name across systems get the system appended, e.g. `San Bruno (BART)` vs `San Bruno (Caltrain)`.
- Writes `stations.json` (un-enriched) and prints per-system + eligible counts.

Expected output: **250 unique stations** (BART 50 · Caltrain 24 · VTA 59 · Muni 128), **249 eligible weekday / 250 weekend** after the hourly filter. (The deployed `src/data/stations.json` is **260** = this base + the SFO AirTrain stops added by a later stage.) Glen Park now contributes **two** stations — `Glen Park` (BART) and `San Jose Ave/Glen Park Station` (Muni J) — which is the +1 Muni / +1 total vs the old behaviour that dropped the Glen Park Muni node. If your counts differ, diff against these before proceeding — a changed count usually means an upstream OSM/GTFS pull changed (note: the committed `raw_muni.json` may be a re-pull that drifts from the deployed set, so trust `src/data/stations.json` as the source of truth). (These numbers are asserted in `src/data/stations.test.ts`; update both together on an intentional change.)

> Muni 128 / 250 reflects the **F Wharf one-way loop** (see below) and the N-Judah corrections in `fix_muni_eastbound.py` (kept in the `hideandseek` data dir): the inbound (Jefferson St) and outbound (Beach St) F stops stay distinct, Funston is its own N stop (not merged into 12th Ave), and split NB/SB poles take the **eastbound** pole (SW/SE side of an E-W street, from `muni_stops.json`) as the main name with the other direction as a secondary `aka`. The N terminal is `Judah St & La Playa St (Ocean Beach)` (there is no "48th Ave" stop), and the F's Ferry stop is `The Embarcadero/Ferry Bldg`. Other Muni surface lines (J/K/L/M/T) have not yet had this eastbound-pole audit applied.

### 2. `build_attributes.py` — enrich
Reads `stations.json`, adds `id`, `nameLength`, `county`, `city`, `elevation`
(USGS EPQS), `airportDist`/`nearestAirport` (haversine to SFO/OAK/SJC), and
writes the enriched array to **`src/data/stations.json`** (and caches to
`scripts/stations_enriched.json`). The cache is reused on the next run (keyed by
rounded lat/lon) so only new/moved stations hit the Census + USGS APIs. It rate-
limits itself (~0.5 s/station); a full cold run is a few minutes.

### 3. `patch_lines.py` — canonical BART lines
BART GTFS route names are per-direction; this collapses them into the six BART
color lines (Yellow/Red/Green/Orange/Blue/Beige) using `scripts/bart_lines.json`
so the "matching transit line" question is sensible. Edits `src/data/stations.json`
in place.

### 3c. `compute_headways.py` — service frequency (`headwayMin`)

Adds `headwayMin: {wd, we}` (typical midday minutes between departures, best
direction; `999` = no regular midday service) to every station. This is what the
app's **frequency eligibility** rule uses (`ELIGIBLE_HEADWAY_MIN = 60` in
`src/data/questionSets.ts`): a station is a valid hiding spot only if
`headwayMin[day] <= 60` — i.e. served at least once an hour. This is the
canonical Jet Lag rule (their largest game, Japan, still required "served by at
least one train an hour"), so it's **flat across all sizes**, not size-scaled.
It's a game restriction derived from the data, not a user toggle (the old
`≥hourly` checkbox is gone). Game size is still auto-derived from station count
(`sizeForStationCount`) but only drives the question deck, not eligibility.
A TODO in `questionSets.ts` notes a future auto-relax for genuinely sparse maps;
the Bay Area never triggers it (247 of 248 qualify at ≤60).

How each system gets its headway (kept in the `hideandseek` data dir as
`compute_headways.py`):
- **BART**: computed from the local GTFS (`gtfs/bart`) — resolves the active
  service for a representative weekday + Saturday, takes the median consecutive
  midday (10:00–15:00) gap per direction, and the station's value is the **min
  across directions** (best service). Multi-platform stations aggregate platforms
  within 300 m.
- **Caltrain**: reuses the authoritative `wd_gap`/`we_gap` already in
  `caltrain_service.json` (nearest stop within 600 m).
- **Muni rail & VTA light rail**: representative published midday headways
  (per-line constants in the script; SFMTA/VTA GTFS isn't directly fetchable).
  They all run every ~8–15 min **every day**, comfortably below the smallest
  threshold (30), so the exact value never changes eligibility.

For a station served by several systems, take the **min** over systems. Re-run
after any station rename/add. NOTE: the official rulebook does **not** define a
frequency rule — these thresholds are our playability tuning and are flagged to
reconcile against the original rulebook.

### 3b. `build_station_lines.py` — authoritative line membership (OSM)

`patch_lines.py` only handles BART colors. For a full, accurate audit of which
lines serve which station, run `python scripts/build_station_lines.py` (from the
repo root). It refetches every BART/Muni/VTA/Caltrain **route relation** from
Overpass, reads each relation's ordered `stop` member node coords, and assigns a
line to a station when any of that line's stops is within `MATCH_M = 170 m` of
the station. This is what splits Caltrain into **Local / Limited / Express**
(from the OSM service-pattern relations) and removes false BART colors (e.g.
Milpitas/Bay Fair should not have **Yellow** — only Green/Orange serve the
Berryessa branch).

Important constraints baked in (keep them):
- **`REBUILD_SYSTEMS = {BART, VTA, Caltrain}` only.** Muni membership is left
  **untouched** — its dense overlapping surface/subway stops make 170 m proximity
  unreliable, and several Muni rules are hand-curated (e.g. F is deliberately
  *not* at Union Square/Market; J is *not* at Church St Station). Those are
  guarded by `src/data/stations.test.ts`; do not let an automated pass overwrite
  them.
- **`BART Silver (Coliseum–OAK)`** has no rail route relation in OSM, so it is
  explicitly preserved from the existing data (don't let the rebuild drop it).
- Caltrain Holiday/Game-day/South County Connector variants and the discontinued
  Muni **S** are excluded (`canon_line` / `MUNI_EXCLUDE_REF`).

**Weekday-only services.** Some lines don't run on weekends — Caltrain
**Express** ("Baby Bullet") and **Limited** are weekday-only. They stay in each
station's `lines` (they're real services), but the "Transit line" question's
dropdown filters them out in **Weekend** mode via `WEEKEND_EXCLUDED_LINES` in
`src/lib/style.ts` (the `lines` memo in `App.tsx` depends on `game.dayType`).
Every station carrying Express/Limited also carries **Caltrain Local**, so it
stays selectable on weekends (asserted in `stations.test.ts`). Add any other
weekday-only line to `WEEKEND_EXCLUDED_LINES` — don't remove it from the data.

The line *geometry* overlay (`src/data/transit-lines.geojson.json`) is built
separately by `scripts/fetch_transit_lines.py` (see `continuous-transit-lines`).
Note its `matches()` classifier keys on **operator/network only, never the route
name** — Muni Metro N's name ends "=> Caltrain" (its terminus), which otherwise
misclassifies N as Caltrain and drops it from the overlay. eBART is tagged
`light_rail`, so the BART matcher accepts both `subway` and `light_rail`.

## Muni stop naming (SFMTA standardization)

Raw OSM `name` tags for Muni surface stops are inconsistent — some are full
cross-streets (`Beach Street & Mason Street`), some are bare (`20th Street`,
`Arleta`). The deployed dataset standardizes all **Muni-only** stops to the
abbreviated SFMTA display name. **BART/Caltrain names take precedence on shared
stops** (a stop that also serves BART/Caltrain keeps its rail-station name and is
not renamed).

Reproduced by `standardize_muni_names.py` (kept in the `hideandseek` data dir,
alongside `propose_muni_names.py` which prints the proposal for review):
- **Abbreviate** Street→St, Avenue→Ave, Boulevard→Blvd, Drive→Dr, etc.
- For `X & Y` names: token-set match (order-independent) against the scraped
  SFMTA route pages (`/routes/<line>`); on an exact match use the route page's
  canonical display (it carries landmark suffixes like `(SF State)`,
  `(Stonestown)`). Otherwise keep the abbreviated existing name.
- For **bare** stops: an explicit override map from the route pages
  (`20th Street` → `3rd St & 20th St`, `Arleta` → `Bayshore Blvd & Arleta/Blanken`, …).
- **Skip** named stations/landmarks (anything containing `Station`, plus
  `Ferry Building`, `Saint Francis Circle`, `Chinatown-Rose Pak`, `Union Square/Market Street`, etc.).
- Do **not** coordinate-match to the SF Muni Stops dataset for renaming — our
  station coords are dedup centroids (off by 50–100 m) and stops are ~100 m
  apart, so nearest-stop matching picks the wrong adjacent corner. Trust the
  existing cross-street name + abbreviate.
- Recompute `nameLength = len(name)` for every renamed/added station.

## F Market & Wharves — Wharf terminal loop

The F's north end is a **one-way terminal loop**, not a dead-end: inbound runs up
The Embarcadero, then the loop returns west on **Jefferson St** → south on
**Jones St** → east on **Beach St** → back to The Embarcadero. The overlay
geometry is stitched from the OSM inbound + outbound relations (`clip_f` keeps
the Wharf→Civic Center run; Civic Center is the south terminus — F is dropped
from Castro/Church St/Van Ness, west of Civic Center).

Because it's one-way, the inbound and outbound stops sit on **different streets**
and are genuinely distinct — keep them separate (do not dedup as NB/SB poles):
`Jefferson St & Taylor St` (outbound) vs `Beach St & Mason St` (return), and
`Beach St & Stockton St` vs `The Embarcadero & Stockton St (Pier 39)`. The
standardize script un-merges these and snaps each to its real SFMTA coordinate.

## Verify
```bash
npm run lint && npx tsc -b --noEmit && npm test && npm run build
```
Then `npm run dev` and confirm the map renders all stations and the
weekday/weekend + "≥hourly only" toggles change the "N of M possible" count.
Also regenerate `STATIONS.md` (docs only) with `node scripts/build_stations_md.mjs`
and the standalone `public/stations-map.html` if the set changed (they embed the
station list). `build_stations_md.mjs` lists each station once under its PRIMARY
system (priority `BART > Caltrain > VTA > Muni > SFO AirTrain`), tags shared
stations, and strips the primary system's own line prefix.

## Gotchas
- Run the scripts from `scripts/`; they use relative input paths but `build_attributes.py`/`patch_lines.py` write to an **absolute** app path — update that constant if the repo lives elsewhere.
- Never silently drop the `< 1 hr` frequency rule or re-add College Park.
- The BART GTFS (`gtfs/bart/stops.txt`) is not committed; re-download it from BART's GTFS feed if missing.
