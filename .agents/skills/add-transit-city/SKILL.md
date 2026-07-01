---
name: add-transit-city
description: Extend the Hide & Seek seeker tool to a new metro area (beyond the SF Bay Area) by producing a stations.json of the same shape. Use when asked to support a different city/region.
---

# Add a new transit city

The app is region-agnostic: it renders and filters whatever is in
`src/data/stations.json`. Adding a city = producing that file for the new region
and adjusting a few region constants. There is no per-city code branching.

## Steps

1. **Gather station sources** for the new region (the same kinds the Bay Area
   uses): rail/metro GTFS `stops.txt` for fixed-station systems, and OSM line
   relations (Overpass) for tram/light-rail/streetcar systems where you want
   every stop. See `scripts/overpass.py` for the Overpass query pattern.

2. **Adapt `scripts/build_stations.py`** to the new systems:
   - Replace the BART/Caltrain/VTA/Muni loaders with the new systems.
   - Keep the dedup logic: within-system clustering (identical name any distance,
     else nearest `< 150 m`) and cross-system merge (`< 200 m`, different systems
     only, OR-ing service flags). Tune thresholds for the city's stop spacing.
   - Keep the name-collision disambiguation (append system).
   - Encode each system's service: frequent systems use the `FREQUENT` constant;
     systems with sparse/peak service need a per-stop `{served, hourly}` per day
     like `caltrain_service.json`.

3. **Update region constants in `scripts/build_attributes.py`**:
   - `AIRPORTS` → the new region's commercial airports (name → lat/lon).
   - County/city come from the **US Census** geocoder, which is **US-only**. For
     non-US regions, swap `census_geo` for a different admin-boundary source
     (e.g. OSM Nominatim reverse geocoding or a local boundary shapefile) and
     keep the returned `county`/`city` shape. Elevation via USGS EPQS is also
     US-only — use a global DEM/elevation API outside the US.

4. **Run the pipeline** (see the `rebuild-station-dataset` skill) and verify the
   enriched `src/data/stations.json` has every field in the `Station` type.

5. **Transit line overlay**: adapt `scripts/fetch_transit_lines.py` for the new
   region (its Overpass bbox + `matches()` operator/network keywords + colors).
   Follow the **`continuous-transit-lines`** skill so the new city's lines come
   out continuous (no gaps / stray yard bits / NB-SB doubling) — the same OSM
   fragmentation problem affects every metro, so reuse that algorithm rather than
   rendering one feature per raw OSM way.

6. **Measuring-feature geometry** (coastline + county/state/international
   borders) and the **county polygons** used by county Matching. These are the
   ONLY city-specific data the Measuring/Matching questions need — the question
   code (`src/lib/measureFeatures.ts`, `src/lib/counties.ts`, elimination +
   shading) is fully city-agnostic and needs no change.
   - Add a per-city entry to the `CITIES` dict at the top of
     `scripts/build_measure_features.py`, then run `CITY=<slug> python3
     scripts/build_measure_features.py`. Each entry supplies:
     - `play_bbox` (lon/lat, generous buffer around all stations)
     - `land` + `saltwater` source geojson (Census land/AREAWATER + ocean)
     - `counties` (a FeatureCollection of the metro + neighbor county polygons;
       reuse the same file the county Matching question reads,
       `src/data/counties.geojson.json`, via the `data:` path prefix)
     - `states` + `countries` source geojson (US states file + Natural Earth
       admin-0 already in `scripts/measure_src/`)
     - `state` + `state_neighbors` (the 1st-admin div the metro is in and the
       adjacent ones whose shared border is the "state border"; a superset is
       harmless — the nearest-point math ignores farther segments)
     - `country` + `country_neighbor` (nearest international border)
   - Output is `src/data/measure-features.geojson.json` (a FeatureCollection of
     `MultiLineString`s keyed `coastline` / `county-border` / `state-border` /
     `intl-border`). Any feature whose sources are missing is skipped, so a
     landlocked/inland city can omit `coastline` or `intl-border`.
   - Skip degenerate questions: e.g. "A Rail Station" (measuring) is useless when
     every hiding station is itself a rail station (distance always 0). It stays
     wired generically for cities whose station set includes non-rail stops.
   - For the county polygons themselves, produce `src/data/counties.geojson.json`
     as GeoJSON `[lon, lat]` polygons with a `properties.name` per county
     (Census TIGER county shapes, clipped to the play area). `counties.ts` reads
     `properties.name` for both point-in-polygon lookup and shading.

7. **Update the map default view** in `src/components/MapView.tsx` (initial
   center/zoom) to the new region, and update copy in `src/App.tsx`, `README.md`,
   `STATIONS.md`, and `public/stations-map.html`.

8. **Question set**: the existing medium-game questions in `src/data/questions.ts`
   are geography-generic and need no change. If the new region lacks an attribute
   a question relies on (e.g. no airports, no coastline), hide that question or
   ensure the attribute is still populated.

## Multi-region (optional)
If you want one deployment to switch between cities, generalize
`src/data/stations.json` into `src/data/<region>.json` files plus a region
picker that selects which JSON to load and which map center to use. Keep each
region file the exact same `Station[]` shape so the elimination engine is
untouched.

## Verify
`npm run lint && npx tsc -b --noEmit && npm test && npm run build`, then `npm run dev` and
confirm the new region renders and the toggles/filters behave.
