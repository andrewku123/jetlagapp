---
name: reference-pdf
description: >-
  Generate the printable Jet Lag: Hide & Seek reference card PDF for any game
  size (small/medium/large) and any map — a front-page question deck
  (Matching/Measuring/Radar/Thermometer/Tentacles/Photo/Inside with checkboxes,
  draw/keep, answer windows, end-game flags and full per-condition photo
  requirements) plus a play-area reference page built from that map's own
  station and POI data. Use when asked to (re)build, restyle, or update that PDF.
---

# Reference-card PDF

Two-page Letter PDF: page 1 the question deck for one **game size**, page 2 the
**play-area reference** for one **region**. Everything is derived from the app's
own data — no Overpass call, no hand-maintained lists.

## Run
```bash
python3 scripts/make_reference_pdf.py --region bay
# -> ./jetlag_reference_bay_medium.pdf   (git-ignored deliverable)
```
**A map is a game size**: `REGIONS[region]["size"]` decides the deck, so
`--region` alone prints the right card and a new map declares its size in that
one entry (all three maps are `medium` today). `--size small|medium|large`
overrides it; `--out PATH` overrides the filename. Requires
`pip install playwright` and the CDP Chrome on `localhost:29229`.

## Size is the gate, not a copy edit
Every size difference is data on the question, never a separate template. Each
subject carries a gate and `keep()` decides:

| gate | meaning |
|---|---|
| `ALL` | every size |
| `ML` | "add for Medium & Large" |
| `LG` | "add for Large" |
| `OWN` | **our** question, not in the official book — every size |

What that produces (verified against the investigation book):
- **Matching / Measuring** — no size gate; the full subject list in all sizes.
- **Radar** — all 9 distances (¼…100 mi) in all sizes, plus **Custom**: the
  seekers may name any distance, same draw 2 / keep 1 cost, no per-game limit.
- **Thermometer** — ½ + 3 mi all games; **+10** for Medium & Large; **+50** for
  Large.
- **Tentacles** — **does not exist in small games** (the whole card is dropped
  and the remaining cards renumber). Medium = the 1-mile set (Museums,
  Libraries, Movie theaters, Hospitals); Large adds the 15-mile set (Metro
  lines, Zoos, Aquariums, Amusement parks).
- **Photo** — 6 all-games + 8 Medium/Large + 4 Large-only, and the window is
  **10 min in Small/Medium, 20 min in Large** (everything else is 5 min).
- **Our own questions are size-independent** and must stay in every deck:
  Inside (Floor, Traffic), Measuring ZIP code + Temperature, Sports stadium
  (both Matching and Measuring), Photo Longest sightline + Darkest area.

Verbatim card text (including the Large-only photos and the 15-mile tentacles)
is transcribed at <https://jetlag.denull.ru/en/rules/questions/>; lifack.ch's
investigation book lists the titles and size buckets but not the requirements.

## Front page
- **Rules that apply to every question are stated once** in the `.rules` header
  strip, never per card: the missed-window penalty, "send the hider
  coordinates, never place names", the tie rule (equal distance → **closer**,
  same floor → **lower**), and the `†` end-game escape hatch.
- Each card header carries only its **draw/keep** badge and its **answer
  window** badge (`≤ 5 min`). No per-card "send hider" line, no "app"
  auto-eliminate badges — the tool's behaviour is not printed on the card.
- **Photo and Inside** use `detail_boxes()`: checkbox + bold title with the
  requirement underneath. Plain subject lists use `boxes()`; Radar/Thermometer
  use `scale()`, which puts the checkbox **above** each number.
- **Inside** is ours: both sub-questions are draw 3, keep 1, both need both
  players indoors, Floor additionally needs the **same building** and has no
  "Same" answer (a tie answers Lower).
- Cards are numbered after assembly (`n · Title`) so a dropped card can't leave
  a gap.

## Reference page
Built only from `src/data/<prefix>stations.json` and `<prefix>poi.json`:
station-count grids (altitude band, name length, nearest airport), stations per
line, counties, in-play airports with coordinates, the POI inventory, the play
area's edge stations, cities, and a blank **question log** to fill in during
play (Andrew's call: the app logs questions, but this is the paper backup if the
board is reset).

**Airports are filtered by the play-area polygon, not by the station data.**
Every station carries `airportDist` to every site in `AIRPORT_SITES`, so keying
off that printed SFO/OAK/SJC on the SF Muni card while the app treats SF Muni as
having no airport at all. Load the region's polygon through
`poi_geo.make_in_play` and keep only sites inside it; with none in play, drop
**both** airport blocks (mirrors `HAS_AIRPORTS` in `src/data/regions.ts`).

Do **not** re-add raw-OSM POI lists: they disagreed with the curated POI data
the app eliminates on (e.g. OSM gave 3 Bay zoos vs the app's 5, missing SF Zoo).
Print counts from the app's own POI file instead. `scripts/fetch_poi.py` (the
Overpass query that used to feed those lists) is no longer part of this build.

The edge-of-play-area block prints **every tied station**, not the first one the
sort happens to return — ties are common on name length (3 LA stations are 4
characters).

## Layout gotchas
- **Render with Playwright, not the `google-chrome` CLI** — here `google-chrome`
  is a CDP wrapper that won't write a file. Connect to
  `http://localhost:29229`, `emulate_media("print")`, then `page.pdf`.
- **Margins:** `@page { margin:0.5in }` + `prefer_css_page_size=True`. Don't set
  margins in both CSS and `page.pdf`, they double.
- **A reference block must not split across the two columns** — a "Stations per
  line" or "Commercial airports" list half in each column reads as two separate
  lists. `.rblock { break-inside:avoid }` keeps each whole. That costs packing
  density, so **if a bigger map's lists push the reference onto a third page,
  set `.rblock { break-inside:auto }`** and accept the wrap: 3 pages is worse
  than a split list. Check with `pdfinfo out.pdf | grep Pages` after adding a
  map — all three current maps fit in 2 pages with `avoid`.
- `.p1 { column-count:2 }` with `break-inside:avoid` cards: the deck reflows on
  its own, so a Large deck (20 photo conditions) still lands on one page. If a
  card ever spills, tighten spacing rather than moving cards between columns.
- Fonts: IBM Plex Sans/Mono from Google Fonts; the render awaits
  `document.fonts.ready`.
- Check the result by rasterising, not by eye on the HTML:
  `pdftoppm -r 110 -png out.pdf /tmp/page`.
