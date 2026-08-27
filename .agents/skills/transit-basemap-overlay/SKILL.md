---
name: transit-basemap-overlay
description: Work on the map's clean basemap and the colored transit-line overlays (BART, Muni Metro, VTA, Caltrain). Use when asked to change the base tiles, restyle/regenerate the transit lines, or adjust line colors.
---

# Transit basemap + line overlay

The seeker map uses a minimal light basemap with the real rail routes drawn on
top in their official (Google-Maps-style) colors, so transit is the visual focus
instead of freeways.

## Basemap (`src/components/MapView.tsx`)
The base is a **vector** layer: OpenFreeMap's **Positron** style (OSM data,
keyless, unmetered) rendered by MapLibre GL into a canvas that the
`@maplibre/maplibre-gl-leaflet` plugin keeps in sync with Leaflet.

```ts
const BASE_STYLE_URL = 'https://tiles.openfreemap.org/styles/positron'
const style = await fetchBaseStyle()                       // style JSON, edited
L.maplibreGL({ style, attributionControl: false })         // <BaseLayer/>
```
Points to watch:
- `attributionControl: false`, then `map.attributionControl.addAttribution(...)`
  — otherwise MapLibre paints its own credit inside the layer's pane on top of
  Leaflet's. Credit **OpenFreeMap** and **OpenStreetMap**.
- No `maxNativeZoom` needed: vector labels stay crisp at every zoom (that cap is
  a raster-tile concern; only the Esri imagery is raster now).
- Because it's a style JSON, individual layers (freeways, place labels) can be
  restyled or removed client-side — impossible with raster tiles. `fetchBaseStyle()`
  does exactly that: Positron draws every road twice, a grey "subtle" pass at low
  zoom (`highway_major_subtle`, `highway_motorway_subtle`, plus grey
  `highway_path`) and a white casing+fill once the road matters. The grey pass
  reads as clutter under the transit lines, so those layers are dropped and
  `highway_minor` is held to `minzoom 14` and recoloured `#fff` — roads appear
  only once they'd be drawn white. Match layer ids against the live style before
  changing this; OpenFreeMap can rename them.

History / don'ts:
- **Do not use CartoDB Positron** (`{s}.basemaps.cartocdn.com/light_all/…`), the
  original basemap: in Aug 2026 CARTO began stamping every keyless request with a
  diagonal "API KEY REQUIRED" watermark, and the tiles still return HTTP 200 — it
  fails visually rather than loudly.
- Esri **Light Gray Canvas** (`Canvas/World_Light_Gray_Base` +
  `Canvas/World_Light_Gray_Reference`, `maxNativeZoom={16}`) was the stopgap after
  CARTO. It works but its baked-in place labels read as heavy/crude next to the
  transit lines; OpenFreeMap matches the look the app was designed around.
- Any replacement must be keyless (Stadia/MapTiler/Jawg/Geoapify all 401 without
  a key) and, for a static GitHub Pages site, must not need a referrer allow-list.
- `scripts/poi_merge_viz.html` is a standalone CDN page with no bundler, so it
  stays on the Esri raster canvas.

## Satellite layer (`src/components/MapView.tsx`, `SatelliteLayer`)
Optional Esri **World Imagery** layer toggled by the `satellite` prop, restricted
to the play area for both perf and looks:
- Lives in its own `'satellite'` pane (zIndex 250: above base tiles, below the
  400 overlay pane), masked by an **SVG `clip-path`** built from `PLAY_RINGS` and
  rebuilt on `viewreset zoomend moveend resize` so imagery only shows inside the
  play-area polygons. The pane is `leaflet-zoom-hide` so the clip never lags.
- Tiles are culled: `SatelliteTileLayer` overrides `_isValidTile` to skip any tile
  whose bounds don't intersect the play area (`boxIntersectsPlay`), so off-area
  tiles never download.
- The clip/cull shape is `src/data/play-area.geojson.json` — the in-play counties'
  legal **water-inclusive** boundaries **minus the Pacific Ocean** (and the
  offshore Farallones), so the bay shows imagery but the open ocean doesn't.
  Regenerate it with `node scripts/build_play_area.mjs` (uses
  `scripts/play_area_src_water.geojson.json` + `scripts/pacific_ocean.geojson.json`
  and `polygon-clipping`).
- **Labels on top of imagery**: satellite would otherwise hide the basemap's
  road/place names, so `fetchSatelliteLabelStyle()` re-fetches the Positron style,
  keeps **only `type: 'symbol'` layers**, and paints them white with a dark halo.
  Symbol-only means street and place *names* with **zero road geometry** — the
  point of doing it in vector rather than raster.
- That label overlay needs **its own pane** (`'satelliteLabels'`, zIndex 251),
  not the imagery pane. MapLibre's container is `position: static` with a
  `transform`, so it forms a stacking context painted at z-index 0 and any
  z-indexed sibling (the imagery tile container) covers it — the labels render
  but are invisible, and no z-index on the MapLibre element fixes it. Both panes
  get the same play-area `clip-path`, rebuilt together.
- History / don'ts: Esri `Reference/World_Transportation` was the keyless raster
  road-label layer, but it welds **salmon road casings** to the names, and
  fading it with a CSS filter (`grayscale(1) opacity(.5)`) dims the names as much
  as the casings. It also returns HTTP 200 *empty* tiles past z17, so as a raster
  layer it needed `maxNativeZoom: 17` — check tile *byte size*, not status.
  CARTO's `light_only_labels` was the original names-only layer; it went
  key-only. Don't add road labels over the light basemap, which draws roads.

## Transit overlay data (`src/data/transit-lines.geojson.json`)
A GeoJSON `FeatureCollection` of `LineString`s — **one feature per continuous
line chain** — each with `properties = { system, colors }` (`colors` is a single
element, the line's color). Generated by `scripts/fetch_transit_lines.py`, which:
1. Queries OSM Overpass for `route ~ subway|light_rail|tram|train` in a Bay Area
   bbox (send a `User-Agent` header or Overpass returns HTTP 406). While iterating
   on the stitching logic, dump the raw response to a temp file once and load that
   instead of re-hitting Overpass each run.
2. Classifies each relation by operator/network into `BART | Muni | VTA |
   Caltrain` (see `matches()`); everything else (Amtrak, ACE, freight) is dropped.
3. Colors lines from each route's OSM `colour` tag, except **Caltrain** which is
   collapsed to a single color (`CALTRAIN_COLOR`). `COLOR_REMAP` post-tweaks
   specific colors (e.g. VTA orange → a brighter orange `#ea580c` so it differs
   from BART orange). **Cable cars are excluded** (see the `route == "cable_car"`
   guard in `matches()`).
4. **Builds one continuous line per `(system, color)`** — see the
   `continuous-transit-lines` skill for the full algorithm. In short: pick the
   most-complete route relation for each line, `stitch_ways()` its ordered member
   ways into chains (choosing the *straightest* continuation at junctions),
   `bridge_chains()` to close small gaps, then drop chains under `STRAY_MIN_M`.
   Coords are rounded to 5 dp.
5. Appends the **BART Silver line** (Oakland Airport Connector, Coliseum→OAK) from
   `scripts/oak_connector.json` with color `SILVER_COLOR` — this guideway isn't in
   the rail route relations, so it's added explicitly.

Regenerate with `python3 scripts/fetch_transit_lines.py` (writes the JSON). It
typically yields ~25 features (one per line, plus a few real branch stubs).

## Rendering (`src/components/MapView.tsx`)
Each way is rendered as a **single line in its first color** (`colors[0]`) — the
static `TRANSIT` `FeatureCollection` is built once at module load. It is drawn with
`<GeoJSON data={TRANSIT} style={transitStyle} interactive={false} />` placed
**after** the `<TileLayer>` and counties overlay but **before** the station markers,
so stations sit on top. `transitStyle(feature)` returns `{ color:
feature.properties.color, weight: 2.5, opacity: 0.95, interactive: false }`.

## Common changes
- **Recolor a system / line**: edit the OSM `colour` (upstream) is not an option;
  instead tweak `FALLBACK`/`CALTRAIN_COLOR` in the script, or post-process colors
  in `main()`, then regenerate.
- **Thicker/thinner lines**: change `weight` in `transitStyle`.
- **Add another agency**: extend `matches()` with its operator/network keywords.
- **Different basemap**: swap the `<TileLayer>` url (keep attribution correct).

## Verify
`npm run lint && npx tsc -b --noEmit && npm test`, then `npm run dev`: confirm the
basemap is light/clean (no bold freeways or ferry lines), and BART (yellow/orange/
blue/red), VTA (blue/green/orange), Muni (line colors), and a single Caltrain line
render in place under the station markers.
