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
are unioned and surrounded *unnamed* pockets are filled. A deleted place is then
carved back out **only if it is not fully enclosed by in-play land**: measure the
fraction of the deleted place covered by the hole-filled union, and if it is
`>= ENCLAVE_FILL_FRAC` (0.9) treat it as a true interior enclave and **leave it in
play** (e.g. San Pablo / East Richmond Heights inside Richmond, Shell Ridge / San
Miguel inside Walnut Creek). A deleted place that opens onto out-of-play land
(coverage `< 0.9`, e.g. Moraga onto the EBMUD/Las Trampas hills) is carved out and
stays grey. So "delete" means "grey unless it is a complete enclave"; if a curator
truly wants an enclosed place grey it must border out-of-play land or be excepted
explicitly. See the `gather-poi` skill. The open land between/around the kept
cities (parks, mountains, ranchland) is not a named place, so it stays out.

The app copy additionally has the **open bay water** unioned in for display only,
so the bay renders as water instead of grey. It is built by `bay_water()` in
`build_play_area.py` from a hand-traced `BAY_CORRIDOR_LL` ring **minus every land
place** (so it snaps to the real shoreline and never covers the East Bay hills),
keeping only the connected water component(s) that contain a `BAY_SEEDS_LL` seed.
The corridor currently covers the central + south bay, reaches WEST along the SF
north shore to the **Golden Gate Bridge** (so all the SF piers — Embarcadero,
Wharf, Marina, Crissy — are in), and is capped on the NORTH by the real
**Richmond–San Rafael Bridge** centreline (`RSR_BRIDGE_LL`, traced from OSM way
24315544) so San Pablo Bay north of it stays grey. To make the water **wrap the
real Marin shoreline** instead of cutting a straight diagonal, `BAY_CORRIDOR_LL`
reaches WEST over the Tiburon/Belvedere peninsula and `bay_water()` subtracts
`marin_land.geojson` (the Tiburon/Belvedere/Sausalito landmass, traced from the
OSM coastline — see below) along with the kept places, so the water snaps to the
true coast. **Angel Island is deliberately excluded from `marin_land.geojson`**, so
it is left covered by the corridor and stays **in play**. The Marin land itself
(Sausalito/Tiburon/Belvedere) is not a kept place, so it stays grey. That bay
polygon exists only in the app's `play-area.geojson.json`; it is not in the
pipeline's `play_area.geojson` and never affects POI clipping or which places are
in play.

After the bay is unioned in, the app copy also runs `fill_small_holes(display,
DISPLAY_HOLE_MAX_KM2)` (12 km²): unioning bay water can ring small bits of
unnamed shoreline land (the Albany/Golden Gate Fields flats, a bay-fronting
deleted place like North Richmond) into tiny grey interior holes; this fills any
enclosed hole below the threshold so the waterfront reads clean. It is
**display-only** — `play_area.geojson` and POI clipping are untouched, and large
genuinely-out-of-play enclosed space is left grey.

**Tracing a bay edge to a real bridge/landmark:** pull the geometry from OSM
(Overpass), don't hand-guess. The Overpass main endpoint often times out / 406s
from the VM — send a `User-Agent` header and fall back to a mirror
(`https://maps.mail.ru/osm/tools/overpass/api/interpreter` worked). Query e.g.
`way["bridge"]["name"~"Richmond.San Rafael",i];out geom;`, pick the full-span way,
downsample to ~7 points, and order it east→west before splicing into the corridor.

**Tracing a coastline into a land polygon (`marin_land.geojson`):** query the
`natural=coastline` ways in a bbox around the peninsula (same UA/mirror fallback),
**polygonize** the coastline ways together with the bbox boundary, then classify
each resulting face as land or water by testing a known land point and a known
water point with `.contains()`; union the land faces into a MultiPolygon and save
it. Deliberately **drop any face you want to stay in play** (Angel Island) so it
is not subtracted from the corridor. Verify with point checks (peninsula towns
contained; Richardson Bay and Angel Island NOT contained) before committing.

**Far-offshore island parts** (e.g. the Farallon Islands, which are legally part
of San Francisco city but ~27 mi out in the Pacific) are dropped in
`build_play_area.py`: any MultiPolygon part whose centroid is west of
`ISLAND_LON_CUTOFF` (-122.6) is removed from the place before unioning, so it
never shows as a lone white speck in the ocean.

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
