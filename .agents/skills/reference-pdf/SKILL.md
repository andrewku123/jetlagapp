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
- **Font:** IBM Plex Sans (+ IBM Plex Mono for coords), loaded from Google
  Fonts via `<link>`; the render waits on `document.fonts.ready` before
  `page.pdf`. Verify with `document.fonts.check('14px "IBM Plex Sans"')`.
- **Page 1** is a 2-column flex (`.p1` / `.col`, `flex:1`): col1 = questions
  1-3 (Matching, Measuring, Radar); col2 = questions 4-6 (Thermometer,
  Tentacles, Photo). Flex does NOT paginate cleanly — each column must fit
  within one page or the trailing card spills. Keep page-1 spacing tight.
- **Page 2** = both station tables + reference lists in `.ref { column-count:2 }`.
  `.rblock { break-inside:auto }` + `h3 { break-after:avoid }` lets long lists
  flow across the column break so everything packs onto one page.
- **Station profiles are horizontal grid TABLES, not graphs** (`html_hgrid`):
  laid out **3 rows × n columns**, each cell = bin label (small, on top) over
  its station count (bold). altitude = elevation band; name-length = length.
  Zero-count rows are filtered out. The old `svg_*` / `html_table` helpers are
  unused.
- **Reference lists included:** airports, counties, zoos, amusement parks,
  cities. **Golf, mountains, hospitals, and bodies of water are intentionally
  excluded** (per request). They're still fetched/curated — just not rendered.
- **Airports**: name left, coords right (`ul.plain.air li` flex, wraps below).
- **Radar** has a **Custom** checkbox after the presets (`scale(RADAR,
  custom=True)`), labelled once-per-game in the prompt.

## Reference data
Built from `src/data/stations.json` (counties, cities, altitude + name-length
tables) and `/tmp/poi.json`. Curation: mountains = named
peaks ≥ 1,500 ft. Cities, amusement parks, zoos are full.

## Gotchas
- **Render with Playwright, not the `google-chrome` CLI.** In this environment
  `google-chrome` is a CDP wrapper that won't write a file; connect over CDP
  (`http://localhost:29229`) and call `page.pdf(...)`. Set `@page { margin:0 }`
  and pass the margins to `page.pdf` (otherwise margins double).
- **Page-1 is a 2-column flex** (`.p1` with two `.col`s) so questions land in
  fixed columns; flex does NOT paginate well, so if a column's content exceeds
  one page the last card spills onto page 2 — keep page-1 spacing tight.
- **Margins:** `@page { margin:0 }` + `page.pdf(margin=0.5in all sides)` gives a
  true 0.5in printable border. Don't set both CSS and pdf margins to non-zero.
- Overpass is rate-limited; `fetch_poi.py` retries 4×. Reuse `/tmp/poi.json`
  when it's recent instead of re-querying.
