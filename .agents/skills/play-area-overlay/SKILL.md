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
so the bay renders as water instead of grey. It is built by `bay_water()` in
`build_play_area.py` from a hand-traced `BAY_CORRIDOR_LL` ring **minus every land
place** (so it snaps to the real shoreline and never covers the East Bay hills),
keeping only the connected water component(s) that contain a `BAY_SEEDS_LL` seed.
The corridor currently covers the central + south bay, reaches WEST along the SF
north shore to the **Golden Gate Bridge** (so all the SF piers — Embarcadero,
Wharf, Marina, Crissy — are in), and is capped on the NORTH by the real
**Richmond–San Rafael Bridge** centreline (`RSR_BRIDGE_LL`, traced from OSM way
24315544) so San Pablo Bay north of it stays grey. The west boundary threads
Raccoon Strait — east of Sausalito/Tiburon/Belvedere (Marin stays grey) but
leaving **Angel Island inside** (in play). That bay polygon exists only in the
app's `play-area.geojson.json`; it is not in the pipeline's `play_area.geojson`
and never affects POI clipping or which places are in play.

**Tracing a bay edge to a real bridge/landmark:** pull the geometry from OSM
(Overpass), don't hand-guess. The Overpass main endpoint often times out / 406s
from the VM — send a `User-Agent` header and fall back to a mirror
(`https://maps.mail.ru/osm/tools/overpass/api/interpreter` worked). Query e.g.
`way["bridge"]["name"~"Richmond.San Rafael",i];out geom;`, pick the full-span way,
downsample to ~7 points, and order it east→west before splicing into the corridor.

**Far-offshore island parts** (e.g. the Farallon Islands, which are legally part
of San Francisco city but ~27 mi out in the Pacific) are dropped in
`build_play_area.py`: any MultiPolygon part whose centroid is west of
`ISLAND_LON_CUTOFF` (-122.6) is removed from the place before unioning, so it
never shows as a lone white speck in the ocean.

**Dense coastlines (places clipped to the real shore).** Place polygons come from
the **full-resolution TIGER/Line** file (`tl_2023_06_place`, ~6-7x more vertices
than the old 1:500k cartographic `cb_*_place_500k`), so the bayfront/ocean coast
has many segments instead of a coarse straight diagonal that wrongly excluded
shoreline land (e.g. North Richmond / San Pablo Bay). But TIGER/Line are *legal*
limits that reach far out into the bay, so each place is clipped back to the real
shore by subtracting a dense **bay+ocean water mask**:
- `build_water_mask.py` downloads Census TIGER/Line **AREAWATER** for the five
  transit counties, unions it, and keeps only connected components ≥ `MIN_WATER_KM2`
  (15 km²) → `bay_water_mask.geojson` (SF Bay + Pacific only; inland reservoirs/
  ponds are excluded so they don't punch holes in cities).
- `load_county_places()` loads `bay_water_mask.geojson` and does
  `place = place.difference(water_mask)` for every place that intersects it.
This same dense water mask is the intended source for the future **coastline
question** (distance-to-coast / Bay-vs-Pacific). Note: OSM `natural=coastline`
(see `build_bay_land.py`) is **sparse on the inner bay** (only the
ocean-connected coast is tagged), so it is *not* sufficient as the shoreline
source — Census AREAWATER is. `build_bay_land.py` / `marin_land.geojson` is still
used only to subtract Marin land (no census place there) from the bay corridor
and to keep Angel Island in play.

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
