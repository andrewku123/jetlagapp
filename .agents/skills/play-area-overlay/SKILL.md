---
name: play-area-overlay
description: Dim the counties that are NOT in play on the map so the playable area stands out. Use when asked to highlight/shade the game boundary, gray out out-of-play regions, or change which counties are in play.
---

# Play-area overlay (dim out-of-play counties)

The map shades every county that is **not in play** with a translucent gray
polygon, leaving the in-play counties clear. This visually communicates the game
boundary without affecting elimination logic.

## Data
`src/data/counties.geojson.json` — a trimmed GeoJSON `FeatureCollection` of Bay
Area + neighboring California counties. Each feature has a single property
`name` (e.g. `"Marin"`). It uses **high-resolution** boundaries from the US
Census 1:500k cartographic boundary file (`cb_2022_us_county_500k`, clipped to
shoreline) so the gray edges follow the coast smoothly instead of looking blocky.
Produced by:
1. Convert the Census county shapefile to GeoJSON, filtering `STATEFP == '06'`
   (California): `npx mapshaper cb_2022_us_county_500k.shp -filter "'06'==STATEFP"
   -o format=geojson`.
2. Keep only the ~25 counties already present (match by `NAME`), rename `NAME` →
   `name`, drop all other properties.
3. Round coordinates to 4 decimal places to shrink the file (~356 KB).

To regenerate (e.g. to widen the region or add counties), re-run those steps with
a short Node script. (An older version used the lower-res click_that_hood file,
which made San Francisco only 26 points and looked blocky.)

## Code (`src/components/MapView.tsx`)
- `IN_PLAY_COUNTIES: Set<string>` — the county names that are in play. Currently
  `Alameda, Contra Costa, San Francisco, San Mateo, Santa Clara` (the counties
  that actually contain eligible stations — verify with
  `[...new Set(stations.map(s => s.county))]`).
- `countyStyle(feature)` — returns Leaflet path options per feature:
  - in play → `{ stroke: false, fill: false, interactive: false }` (invisible).
  - out of play → gray `#6b7280`, `fillOpacity: 0.35`, thin outline,
    `interactive: false` (so it never intercepts map clicks).
- Rendered as `<GeoJSON data={COUNTIES} style={countyStyle} interactive={false} />`
  placed **immediately after `<TileLayer>`** and **before** the station markers,
  so markers/annotations draw on top of the shading.

## To change which counties are in play
Edit the `IN_PLAY_COUNTIES` set. Keep the names exactly matching the `name`
property in `counties.geojson.json`. If you add a county that isn't in the
GeoJSON yet, regenerate the data with a wider region first.

## To change the look
Adjust `countyStyle` (fill color / `fillOpacity` / outline). Keep
`interactive: false` so the overlay doesn't block seeker-point clicks or station
marker clicks.

## Verify
`npm run lint && npx tsc -b --noEmit && npm test`, then `npm run dev`: zoom out
one or two steps and confirm the in-play counties around the bay are clear while
surrounding counties (Marin, Sonoma, Napa, Solano, San Joaquin, Santa Cruz, …)
are dimmed gray, and that clicking inside a dimmed county still drops a seeker
point (overlay is non-interactive).
