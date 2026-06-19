---
name: reference-pdf
description: >-
  Generate the printable Jet Lag: Hide & Seek (Medium) reference card PDF — a
  front-page question deck (Matching/Measuring/Radar/Thermometer/Tentacles/Photo
  with checkboxes, draw/keep, answer windows, end-game flags and the minimum the
  seeker must reveal) plus back-page play-area reference lists and station
  histograms. Use when asked to (re)build, restyle, or update that PDF.
---

# Reference-card PDF

Two-page (front deck + back reference) Letter PDF for the **Medium** game,
generated from the app's station data + OpenStreetMap POIs.

## Files
- `scripts/fetch_poi.py` — queries Overpass for POIs (peaks, golf, theme parks,
  hospitals, water/bays/reservoirs) within the 5 in-play counties; writes
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

## Back page — play-area reference
Built from `src/data/stations.json` (counties, cities, altitude + name-length
histograms as inline SVG) and `/tmp/poi.json`. Curation: mountains = named
peaks ≥ 1,500 ft; water = bays/straits/lakes/lagoons/named reservoirs (minor
coves/sloughs/ponds dropped). Golf, hospitals, cities, amusement parks are full.

## Gotchas
- **Render with Playwright, not the `google-chrome` CLI.** In this environment
  `google-chrome` is a CDP wrapper that won't write a file; connect over CDP
  (`http://localhost:29229`) and call `page.pdf(...)`. Set `@page { margin:0 }`
  and pass the margins to `page.pdf` (otherwise margins double).
- **Dense stacking** uses `.deck { column-count:3 }` with
  `.card { break-inside:avoid; display:inline-block; width:100% }` — do not
  switch back to a fixed grid or the cards stop packing tightly.
- Overpass is rate-limited; `fetch_poi.py` retries 4×. Reuse `/tmp/poi.json`
  when it's recent instead of re-querying.
