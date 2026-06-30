---
name: play-area-overlay
description: Dim everything outside the play area on the map so the playable area stands out. Use when asked to highlight/shade the game boundary, gray out out-of-play regions, or change what is in play.
---

# Play-area overlay (dim out-of-play area)

The map shades everything **outside the play area** with a translucent gray
mask, leaving the in-play cities clear. This visually communicates the game
boundary without affecting elimination logic.

The play area is the **union of whole city/town/CDP polygons** (no raw circular
disks), with any fully-enclosed hole filled in. It is produced by
`scripts/build_play_area.py` in the POI pipeline by an **opt-out, county-scoped
curation**: start from every Census place in the transit-touched counties, then a
curator deletes the unwanted ones in `play_area_overrides.json` `"drop"`; any kept
unincorporated CDP left completely surrounded by non-playable area is auto-dropped;
the rail line is bridged through the open land between two kept cities (e.g. BART
Rockridge→Orinda, Castro Valley→Dublin) as a hideable corridor; the kept polygons
are unioned and surrounded *unnamed* pockets are filled, but a deleted place is
always carved back out so it never re-appears via hole-fill even when its kept
neighbours ring it (e.g. Moraga inside Orinda/Lafayette stays grey). See the
`gather-poi` skill. The open land between/around the kept cities (parks,
mountains, ranchland) is not a named place, so it stays out.

The app copy additionally has the **open bay water** unioned in for display only,
so the bay renders as water instead of grey: the central + south bay plus the
East-Bay channel up to ~Richmond, bounded on the north-west by a line just east of
Alcatraz/Angel Island (Marin and San Pablo Bay north of Richmond stay grey). That
bay polygon exists only in the app's `play-area.geojson.json`; it is not in the
pipeline's `play_area.geojson` and never affects POI clipping or which places are
in play.

## Data
`src/data/play-area.geojson.json` — a GeoJSON `FeatureCollection` with the
play-area polygon (the union of in-play places, simplified to ~40 m tolerance to
keep the SVG clip-path light). This same file is used for the satellite-imagery
clip + tile culling. Regenerate it by re-running the POI pipeline's
`build_play_area.py`, which writes this file directly.

(`src/data/counties.geojson.json` + `src/lib/playArea.ts`'s `IN_PLAY_COUNTIES`
still exist — they back the county Matching question and the dataset invariant
test — but they are **no longer used to draw the overlay**.)

## Code (`src/components/MapView.tsx`)
- `IN_PLAY_FEATURES` — every feature of `play-area.geojson.json` (no county
  filter).
- `PLAY_POLYS` — the polygons as `[outer, ...holes]` rings.
- `PLAY_RINGS_LATLNG` — **every** ring of every polygon (outer rings AND interior
  holes) converted to Leaflet `[lat, lng]` order. Interior holes must be included
  so the even-odd fill rule re-dims them.
- `DIM_FILL` — gray `#6b7280`, `fillOpacity: 0.35`, no stroke,
  `interactive: false` (so it never intercepts map clicks), `fillRule: 'evenodd'`.
- Rendered as a single world-minus-cities mask: a `<Polygon>` whose positions are
  `[WORLD_RING, ...PLAY_RINGS_LATLNG]` — a near-world outer ring with every play
  ring as a hole. With the even-odd rule the depth alternates: world (dim) → place
  outer ring (in play) → interior hole (dim again). **Including interior holes is
  required** — a deleted place ringed by kept neighbours (e.g. Moraga inside
  Orinda/Lafayette) is an interior hole in the play polygon; if only outer rings
  are used it renders white instead of grey. The satellite-imagery clip-path's
  `<path>` likewise sets `clip-rule="evenodd"` for the same reason. Placed
  **before** the station markers so markers/annotations draw on top of the shading.

## To change what is in play
Change the eligible-place rule and re-run `build_play_area.py` (see the
`gather-poi` skill — station-reachability radius, enclave heuristic, or the
manual `play_area_overrides.json`). That regenerates `play-area.geojson.json`;
the overlay, satellite clip and tile culling all follow it automatically.

## To change the look
Adjust `DIM_FILL` (fill color / `fillOpacity`). Keep `interactive: false` so the
overlay doesn't block seeker-point clicks or station marker clicks.

## Verify
`npm run lint && npx tsc -b --noEmit && npm test`, then `npm run dev`: zoom out
one or two steps and confirm the in-play cities around the bay are clear while
everything else (out-of-play cities, hills, ocean, neighboring counties) is
dimmed gray, and that clicking inside the dimmed area still drops a seeker point
(overlay is non-interactive).
