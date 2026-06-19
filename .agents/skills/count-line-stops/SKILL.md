---
name: count-line-stops
description: Count how many stops the app has on each transit line, and audit those counts against the authoritative OSM route data. Use when asked how many stops a line has, to tally stops per line, or to verify per-line station membership is accurate.
---

# Count / audit stops per transit line

`scripts/count_line_stops.py` tallies, for every line, how many stations in
`src/data/stations.json` list it (a station counts on every line that serves it,
so shared stations are counted once per line). It groups lines by system and
sorts by descending count, and can cross-check each count against OSM.

## Run it

```bash
python scripts/count_line_stops.py                     # app counts only
python scripts/count_line_stops.py --osm /tmp/osm_full.json   # + OSM audit
python scripts/count_line_stops.py --osm /tmp/osm_full.json --tol 2
```

The `--osm` dump is the same Overpass relation export
`build_station_lines.py` fetches (BART/Muni/VTA/Caltrain route relations with
their `stop` member nodes). If you don't have one cached, re-fetch it the way
`build_station_lines.py` does (`rebuild-station-dataset` skill).

## How the OSM audit works (and why a naive count is wrong)

Do **not** just count `stop` member nodes per line — OSM models each line with
several **directional + short-turn** route relations, so one physical station
appears as many stop nodes:

- A station shows up once per direction (NB/SB). For **BART** the NB/SB stop
  nodes sit **>170 m apart**, so even clustering by proximity still double-counts.
- BART colors also have multiple service variants (e.g. Yellow has
  `Antioch⇒SFO`, `SFO⇒Antioch`, `…⇒Millbrae`, plus 3-stop fragments).

Counting raw nodes gives ~2x the real number. Instead the script **snaps every
stop node to its nearest app station** of the same system (within `match_m =
170 m`, the same rule `build_station_lines.py` uses) and counts the **distinct
stations** each line touches. That yields a physical, app-comparable count.
Stops with no station within 170 m (yards, non-revenue, out-of-area) are ignored.

A line is **flagged** when `|app − OSM| > tol` (default 2).

## Interpreting the result

- **BART / VTA / Caltrain** should match OSM **exactly** — they're rebuilt from
  this same OSM data, so a non-zero diff means `stations.json` drifted from the
  source (re-run `build_station_lines.py`).
- **Muni** may differ by 1-2 on purpose. Muni is hand-curated (not rebuilt from
  proximity), e.g. **J** is dropped at Church St Station and **F** at Union
  Square/Market, so `Muni J` and `Muni F` read one below OSM. That's expected;
  it's why the default tolerance is 2.
- **`BART Silver (Coliseum–OAK)`** has no OSM rail route relation, so it shows
  "no OSM line" — its 2 stops (Coliseum, OAK) are correct and preserved manually.

### Known-good snapshot (246-station Bay Area dataset)

BART: Yellow 28 · Red 24 · Green 22 · Orange 21 · Blue 18 · Silver 2.
Caltrain: Local 24 · Limited 16 · Express 11.
VTA: Blue 26 · Green 26 · Orange 26 (all three really are 26 — verified against
OSM, not a bug).
Muni: N 31 · L 26 · M 25 · T 22 · J 21 · K 21 · F 19.
Total: 409 station-line memberships across 246 stations.

If your run differs, something in the dataset changed — diff against these and
investigate before shipping.
