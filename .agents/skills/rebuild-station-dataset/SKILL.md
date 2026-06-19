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
  - **North Beach (T)** and a spurious **Glen Park** Muni node.
  - The **F-only surface stops on Market St inland of Embarcadero** (any F-only cluster whose name starts with `Market Street &`) — they run directly above the Muni Metro subway and duplicate those stations.
  - The **F node at Market & Stockton** (the F does not stop at Union Square/Market, the Central Subway T station).
- **Cross-system merge** only between *different* systems within `< 200 m` (`merge_service` ORs the service flags). This is what makes 4th & King = Caltrain + Muni, Balboa Park = BART + Muni, Milpitas = BART + VTA, etc.
- **Disambiguation**: stations sharing a display name across systems get the system appended, e.g. `San Bruno (BART)` vs `San Bruno (Caltrain)`.
- Writes `stations.json` (un-enriched) and prints per-system + eligible counts.

Expected output: **246 unique stations** (BART 50 · Caltrain 24 · VTA 59 · Muni 124), **245 eligible weekday / 246 weekend** after the hourly filter. If your counts differ, diff against these before proceeding — a changed count usually means an upstream OSM/GTFS pull changed. (These same numbers are asserted in `src/data/stations.test.ts`; update both together on an intentional change.)

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

## Verify
```bash
npm run lint && npx tsc -b --noEmit && npm test && npm run build
```
Then `npm run dev` and confirm the map renders all stations and the
weekday/weekend + "≥hourly only" toggles change the "N of M possible" count.
Also regenerate `STATIONS.md` and the standalone `public/stations-map.html` if
the set changed (they embed the station list).

## Gotchas
- Run the scripts from `scripts/`; they use relative input paths but `build_attributes.py`/`patch_lines.py` write to an **absolute** app path — update that constant if the repo lives elsewhere.
- Never silently drop the `< 1 hr` frequency rule or re-add College Park.
- The BART GTFS (`gtfs/bart/stops.txt`) is not committed; re-download it from BART's GTFS feed if missing.
