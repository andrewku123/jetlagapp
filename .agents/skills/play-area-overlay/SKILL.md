---
name: play-area-overlay
description: Dim everything outside the play area on the map so the playable area stands out. Use when asked to highlight/shade the game boundary, gray out out-of-play regions, or change what is in play.
---

# Play-area overlay (dim out-of-play area)

The map shades everything **outside the play area** with a translucent gray
mask, leaving the in-play cities clear. This visually communicates the game
boundary without affecting elimination logic.

The play area is the **union of transit-served city/town/CDP polygons** (not
counties), plus the 0.5 mi hiding-zone disk around every station and any
fully-enclosed hole filled in. It is produced by `scripts/build_play_area.py` in
the POI pipeline (a place qualifies if any part of it is within a hiding zone of
an eligible station, or it is a transit-enclosed enclave, plus a manual keep/drop
override; then station disks are unioned in and surrounded pockets filled — see
the `gather-poi` skill) and shipped to the app as a single (simplified) polygon.

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
- `PLAY_POLYS` / `PLAY_OUTER_LATLNG` — the polygons as `[outer, ...holes]` rings
  and, separately, each outer ring converted to Leaflet `[lat, lng]` order.
- `DIM_FILL` — gray `#6b7280`, `fillOpacity: 0.35`, no stroke,
  `interactive: false` (so it never intercepts map clicks).
- Rendered as a single world-minus-cities mask: a `<Polygon>` whose positions are
  `[WORLD_RING, ...PLAY_OUTER_LATLNG]` — a near-world outer ring with each in-play
  place punched out as a hole. Placed **before** the station markers so
  markers/annotations draw on top of the shading.

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
