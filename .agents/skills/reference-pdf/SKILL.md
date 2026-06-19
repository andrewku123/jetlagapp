---
name: reference-pdf
description: >-
  Generate the printable Jet Lag: Hide & Seek (Medium) reference card PDF — a
  front-page question deck (Matching/Measuring/Radar/Thermometer/Tentacles/Photo
  with checkboxes, draw/keep, answer windows, end-game flags, the minimum the
  seeker must reveal, and full per-condition photo requirements) plus play-area
  reference lists and station histograms. Use when asked to (re)build, restyle,
  or update that PDF.
---

# Reference-card PDF

Two-page (front deck + back reference) Letter PDF for the **Medium** game,
generated from the app's station data + OpenStreetMap POIs.

## Files
- `scripts/fetch_poi.py` — queries Overpass for POIs (peaks, golf, theme parks,
  zoos, hospitals, water/bays/reservoirs) within the 5 in-play counties; writes
  `/tmp/poi.json`. Run this first (or whenever the POI lists need refreshing).
- `scripts/make_reference_pdf.py` — builds `/tmp/reference.html` then renders
  `jetlag_reference_medium.pdf` (in the repo root) via Playwright over the
  Chrome CDP endpoint.

## Run
```bash
python3 scripts/fetch_poi.py            # -> /tmp/poi.json (skip if fresh)
python3 scripts/make_reference_pdf.py   # -> ./jetlag_reference_medium.pdf
```
The PDF is a **deliverable**, not app code — it is git-ignored / not committed.

## Front page — the question deck (source of truth)
Specs come from the official **Investigation Book** (lifack.ch `/investigation/*`)
and Quick Start guide (`/docs/quick_start_guide/asking_questions`,
`/the_end_game`). Keep these exact:
- **Draw/keep:** Matching 3/1, Measuring 3/1, Radar 2/1, Thermometer 2/1,
  Tentacles 4/2, Photo **draw 1** (no keep).
- **Medium subject sets:** Matching & Measuring have **no size gate** — include
  all 20 subjects each. Radar = all 9 distances (¼…100 mi). Thermometer =
  ½/3/10 mi (drop the Large-only 50). Tentacles = the 1-mile set only
  (Museums, Libraries, Movie theaters, Hospitals); the 15-mile set is Large-only.
  Photo = All-Games + Medium/Large set = 14 conditions (drop the 4 Large-only).
  Measuring includes admin-division borders **1st-4th** (state/county/city/
  neighborhood) — don't drop the 3rd & 4th.
- **Photo conditions** are stored as `(title, requirement, endgame_blocked)` and
  rendered with the full requirement text under each title (verbatim from the
  official photo cards) — titles alone are not enough.
- **Checkboxes** (`<span class="cb">`) precede every subject. For Radar &
  Thermometer the checkbox sits **above** each number (`.scale`/`.sc`).
- **Answer window / consequence of failing:** ≤5 min (Photo ≤10 min in Medium);
  miss it → hider's clock pauses until answered and they draw **no** card.
- **End game:** all non-photo questions are completable; only Photo conditions
  that need the station or a fixed venue are blocked (marked `†`) — there
  "I cannot answer" is valid and the hider **still draws a card**.
- **"Send hider":** the minimum the seeker must reveal for the question to be
  answerable — Matching = your nearest ___; Measuring = your distance to ___;
  Radar = location pin + radius; Thermometer = start & stop points; Tentacles /
  Photo = nothing (about the hider / hider sends the photo).
- **`app` badge** = the seeker tool auto-eliminates for that subject (airport,
  transit line, station-name length, county, city, sea level, radar, thermometer).

## Layout (current)
- **Page 1** is an explicit 3-column flex (`.p1` / `.col1-3`), not auto-balanced:
  col1 = questions 1-4 + both station graphs (minimized); col2 = Tentacles +
  Photo; col3 = the short reference lists (airports, counties, zoos, amusement
  parks). Keep col1's content within one page height or it overflows the column.
- **Page 2** = the long reference lists (cities, water, mountains, golf,
  hospitals) in `.ref { column-count:3 }`, with the footer after them. If the
  footer spills to a 3rd page, tighten `ul.cols li` font/margins until it fits.
- **Airports**: name left, coords right (`ul.plain.air li` flex, wraps below).
- **Graphs (reversed orientation)**: altitude = `svg_horizontal` (bars run
  horizontally), name-length = `svg_vertical`. Both take a `caption` + `color`.

## Reference data
Built from `src/data/stations.json` (counties, cities, altitude + name-length
histograms as inline SVG) and `/tmp/poi.json`. Curation: mountains = named
peaks ≥ 1,500 ft; water = bays/straits/lakes/lagoons/named reservoirs (minor
coves/sloughs/ponds dropped). Golf, hospitals, cities, amusement parks, zoos
are full.

## Gotchas
- **Render with Playwright, not the `google-chrome` CLI.** In this environment
  `google-chrome` is a CDP wrapper that won't write a file; connect over CDP
  (`http://localhost:29229`) and call `page.pdf(...)`. Set `@page { margin:0 }`
  and pass the margins to `page.pdf` (otherwise margins double).
- **Page-1 columns are explicit** (`.p1` flex with `.col1/.col2/.col3`) so each
  question lands in the column golden asked for; this does NOT paginate, so
  oversized column content is clipped — keep cards/graphs compact.
- Overpass is rate-limited; `fetch_poi.py` retries 4×. Reuse `/tmp/poi.json`
  when it's recent instead of re-querying.
