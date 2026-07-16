---
name: add-transit-city
description: Extend the Hide & Seek seeker tool to a new metro area (beyond the SF Bay Area) by producing a stations.json of the same shape. Use when asked to support a different city/region.
---

# Add a new transit city

The app is region-agnostic: it renders and filters whatever is in a region's
data files. Adding a city = producing those files for the new region and adding
**one** `REGIONS` entry. There is no per-city code branching.

## Quick-start checklist (current multi-region model)

The app is now multi-region: every map is **8 data files + one `REGIONS` entry**
in `src/data/regions.ts`. The Bay Area uses unprefixed filenames; every other
map uses a `<slug>.` prefix (e.g. `la.stations.json`). The 8 files are:
`stations.json · poi.json · play-area.geojson.json · measure-features.geojson.json
· places.geojson.json · counties.geojson.json · zctas.geojson.json ·
transit-lines.geojson.json`.

1. **Lock the station set** with the user (systems in scope, names, per-line
   stop order). Then build `<slug>.stations.json` — see the detailed Steps 1–4
   below and the `rebuild-station-dataset` skill. Enrich every station
   (`county`, `city`, `elevation`, per-airport distance + `nearestAirport`,
   per-day `service`/`headwayMin`).
2. **Pick the play area WITH the user** — it drives every clip + the demotion
   rules. Options seen so far: place-based whole-city + enclaves (Bay Area, LA)
   vs a corridor buffer. Build `<slug>.play-area.geojson.json`, then clip
   `places` / `counties` / `zctas` to it. LA rule the user chose: include every
   whole city any line touches, auto-add enclosed enclaves, and if an endgame
   disk carves into a not-yet-included city **whose county is already in play**,
   pull in that whole city (union just the sliver if the county is NOT in play).
3. **Geography files**: `<slug>.counties.geojson.json`,
   `<slug>.places.geojson.json`, `<slug>.zctas.geojson.json` (Steps 3/6 below).
4. **Measure features** (`<slug>.measure-features.geojson.json`) via the per-slug
   entry in `scripts/build_measure_features.py` (Step 3 below). For an **open
   ocean coast** where OSM tags inland river channels as `natural=coastline`
   (LA: LA River / San Gabriel River), use the coastline mode that keeps only
   segments within a small buffer of the open-water mask (`coast_water_clip`).
5. **Transit line overlay** (`<slug>.transit-lines.geojson.json`) via
   `fetch_transit_lines.py` + the `continuous-transit-lines` skill (Step 5).
   Each feature needs `{system, colors[]}` props; `colors[0]` is the line color.
6. **POI** (`<slug>.poi.json`) via the `gather-poi` skill. **Shipping without POI
   is fine and often preferred**: create `<slug>.poi.json` with every category as
   `[]` — the app checks `POI_COUNTS[cat]===0` and auto-demotes every POI
   Matching/Measuring/Tentacle subject to log-only, no per-region flag. Then land
   the curated POI later. For the audit, mirror the Bay Area POI review PR:
   `public/poi-<slug>-review/` (copy `index.html`, only change the map
   `setView` center/zoom; drop in `poi_merge_viz.js` + `play_area.geojson.json`).
   `fetch_places_poi.py` takes a `POI_PLAY_FILE` env override for the play polygon.
7. **Register the region** — add the 8 imports + one `REGIONS` entry
   (`id, name, center, zoom, inPlayCounties`, + the 8 data objects) to
   `src/data/regions.ts`, and a single-agency dot color in `src/lib/style.ts` if
   the map is one agency. **Demotion is derived from the region's own geometry —
   never a hand-maintained per-city list:**
   - single line only → `match-line` log-only;
   - single county/city AND no endgame disk reaches its boundary
     (`boundaryCarves()` false) → **full log-only** (useless in both phases — LA:
     all stations ~3 km from the county line, beyond the 0.25 mi disk → county
     Matching log-only);
   - single county/city whose boundary a disk **does** cross → **endgame-only**
     (SF Muni county case);
   - no in-play airport / no coastline / no state·intl border geometry → that
     subject log-only (kept in the dropdown, eliminates nothing).
   Add region assertions to `regions.test.ts` + `poiDemotion.test.ts`.
8. **Verify + PR**: `npm run lint && npx tsc -b --noEmit && npm test && npm run
   build`. Ship the main map as its own PR; the POI audit as a **separate,
   review-only** PR. (The PR-preview CI only runs `npm run build`; lint/test gate
   runs on push to `main`, so run them locally before pushing.)

The rest of this doc is the detailed reference for each step.

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
   - **Auto-demote map-useless questions** via two region-derived sets in
     `src/data/regions.ts` — do NOT hand-maintain a per-city list. Both are
     derived from the active region's own data. There are TWO demotion tiers:

     **`LOG_ONLY_KINDS` — never eliminate (useless in the regular game AND the
     endgame).** A question lands here when:
     1. **Feature absent from the play area** — apply the core game rule
        *"anything outside the play area is treated as if it doesn't exist."* The
        `AIRPORTS` list is scoped by point-in-play-area test (`pointInPlayArea`)
        to airports actually inside the active map. If none are in play
        (`!HAS_AIRPORTS`), demote BOTH `match-airport` and `measure-airport`.
        SFO/OAK/SJC are inside the Bay Area play area but all outside SF, so SF
        Muni has zero in-play airports.
     2. **Single NON-spatial value** — every station shares one value and the
        attribute can't carve a hiding zone. `match-line` when the map has `<= 1`
        distinct line.

     **`ENDGAME_ELIMINATES_KINDS` — log-only in the regular game, but fully
     eliminating in the endgame.** `match-county` / `match-city` when the map is
     single-county / single-city (`<= 1` distinct value). They can't split the
     station list map-wide, but county/city are *spatial* — a border station's
     0.25 mi endgame hiding zone can straddle the boundary (Sunnydale/Bayshore
     across the SF↔San Mateo line), so "same county/city as mine?" carves the
     zone. Do NOT put these in `LOG_ONLY_KINDS` (that would kill zone-carving).

     `QuestionForm` combines them:
     `endgameOnlyKind = ENDGAME_ELIMINATES_KINDS.has(kind)` and
     `eliminatesEffective = meta.eliminates && !LOG_ONLY_KINDS.has(kind) && !poiKindDemoted(...) && (!endgameOnlyKind || endgameFlag)`.
     This drives the logged record's `eliminates`, the primary-button label
     ("Log question" vs "Log question & eliminate"), and the dropdown suffix
     ("(log only)" for full log-only, "(endgame only)" for endgame-only). The
     **Endgame checkbox is shown when `eliminatesEffective || endgameOnlyKind`**
     so an endgame-only kind can still be toggled on. `DEMOTION_NOTE` gives the
     per-kind reason; endgame-only kinds point the seeker to the checkbox.

     **Per-category POI demotion** is separate (`poiKindDemoted` in
     `QuestionForm`, driven by `POI_COUNTS[cat]`): a POI subject with **0**
     in-play POIs of that category is log-only for both match/measure; with
     exactly **1** it's log-only for `match-poi` only (a lone POI can't split a
     "nearest" match, but Measuring distances still vary). SF Muni has 0
     amusement parks → both amusement-park questions log-only.

     **Measure-feature demotion** (coastline / borders) works the same way but
     must still keep the subject in the dropdown. Build the `measure-feature`
     subject options from the UNFILTERED `MEASURE_FEATURE_KEYS`, not from
     `AVAILABLE_MEASURE_FEATURE_KEYS` (which drops features with no in-play
     geometry and made them silently disappear). Tag ` (log only)` when
     `featureDemoted(f) = featurePolylines(f).length === 0`, treat those as
     non-eliminating in `eliminatesEffective`, and allow logging them in
     `submit()` (skip the distance-geometry check). Neither map has a state or
     international border in play, so those stay listed as "(log only)".

     Net: SF Muni demotes airports + amusement park (log-only), county + city
     (endgame-only), keeps line (7 Muni lines); Bay Area demotes nothing.
     `src/data/regions.test.ts` asserts both per-region sets.

   - **CITY/COUNTY polygons must be the TRUE municipal boundary, not the play
     area.** `build_sfmuni_region.py` sets the SF play area = city land unioned
     with each station's 0.25 mi endgame circle (so edge zones stay in play), but
     the metro's OWN `places` (city Matching) polygon must be the un-padded `land`
     — using `play_area` bleeds the SF polygon south across the county line into
     Brisbane and mislabels border points as "San Francisco city", which also
     breaks the endgame county/city carving that depends on the real border.
   - **Include neighbour city/county slivers that fall inside the play area** so
     the out-of-metro part of a border station's endgame zone reads its REAL
     place, not "unincorporated / outside the play area". A 0.25 mi endgame circle
     on an edge station (Bayshore/Sunnydale) spills past the SF↔San Mateo line
     into Brisbane; that sliver is still in play and endgame county/city must
     carve it. Two coordinated pieces:
     - `build_sfmuni_region.py` adds each neighbouring Census place, clipped to
       the play area (`place.difference(water).intersection(play_area)`), to
       `sfmuni.places.geojson.json` alongside SF's true `land`. Each meets SF
       along the real census border, so no station falls in a neighbour and
       carving stays exact. (Verify: all stations still resolve to the metro
       city, and the border point reads the neighbour — e.g. Brisbane.)
     - `countyAt()` in `counties.ts` first tries `IN_PLAY_COUNTIES`; if the point
       is still `inPlayArea()` but in none of them, it falls back to the real
       neighbouring county from `counties.geojson.json` (San Mateo for the SF
       sliver). Points genuinely outside the play area stay `null`.
   - For the county polygons themselves, produce `src/data/counties.geojson.json`
     as GeoJSON `[lon, lat]` polygons with a `properties.name` per county
     (Census TIGER county shapes, clipped to the play area). `counties.ts` reads
     `properties.name` for both point-in-polygon lookup and shading.
   - **Admin divisions are per-city and only the in-play ones matter for
     Matching.** "2nd admin division" = county in the US, borough (also a county)
     in NYC, regional municipality / census division in Canada, etc. — same file
     shape, different source. The hider is always in one of the divisions that
     hold stations, so `countyAt()` in `counties.ts` first considers the names in
     `IN_PLAY_COUNTIES` (`src/lib/playArea.ts`); a seeker on the far side of the
     world is definitively "not the same county" as every station, and the exact
     identity of that outside division never changes an elimination. So **do NOT
     try to ship the world's counties**: set `IN_PLAY_COUNTIES` to the divisions
     containing stations. The one exception is the in-play-area fallback above —
     a point still inside the play area but outside every in-play county (a border
     endgame sliver) resolves to its real neighbouring county so the endgame can
     carve it; everything genuinely outside the play area still reads "outside the
     play area". (The wider `counties.geojson.json` set also feeds the county-
     *border* measure feature and the dim overlay.)
   - **City (3rd-admin) polygons** used by city Matching live in
     `src/data/places.geojson.json`, built by `scripts/build_city_places.py`
     from the state Census **place** file. Emit **every place that lies inside
     the play area — city, town AND CDP — each clipped to the play-area
     polygon**, not just the ones that hold stations. Two reasons:
     - the play area (built by `build_play_area.py`) refills unincorporated
       **CDP enclaves** (e.g. Fairview) that no station sits in, and a seeker can
       stand in one — it must read out its real name, so it has to be in the set;
     - clipping to the play area (already shoreline-clipped) drops the parts of
       edge places (Tiburon, Belvedere) that stick out into greyed-out land.
     `cityAt()` in `cities.ts` is point-in-place with a small `SNAP_M` (~150 m)
     snap; a coordinate in a **named** place → that place, in the play area but no
     named place → **null → the form shows "Unincorporated"** (in play, no
     municipality to match), outside the play area → null → **"Outside the play
     area."** (`inPlayArea()` distinguishes the two). Keep the seeker AND station
     lookups on this SAME `cityAt()` so shading and elimination always agree.
   - **Airport-on-unincorporated-land override:** an airport owned by a city but
     physically on unincorporated land (SFO is owned by the City & County of San
     Francisco but sits in San Mateo County) is folded into its owning city by
     `unary_union`-ing the airport footprint (convex hull of that airport's
     stations, buffered, minus any other place it laps) into that city's polygon
     in `build_city_places.py`. That makes every airport station AND a click on
     the airport resolve to the owning city. This is the one Bay-specific
     override; a new metro only needs it if it has the same ownership quirk.
     Verify **no hiding station resolves to null** after building — if one does,
     it's on unincorporated land and either needs a CDP added or an override.

7. **Update the map default view** in `src/components/MapView.tsx` (initial
   center/zoom) to the new region, and update copy in `src/App.tsx`, `README.md`,
   `STATIONS.md`, and `public/stations-map.html`.

8. **Question set**: the existing medium-game questions in `src/data/questions.ts`
   are geography-generic and need no change. If the new region lacks an attribute
   a question relies on (e.g. no airports, no coastline), hide that question or
   ensure the attribute is still populated.

## Multi-region — a second selectable map (IMPLEMENTED)
One deployment can hold several maps, switched by a header picker. This is done
via the **region registry** `src/data/regions.ts` — do NOT reintroduce direct
`import x from '../data/<file>.json'` in lib code; always go through the registry.

Pattern:
- Each map ships the **same 8 data files**: `stations.json`, `poi.json`,
  `play-area.geojson.json`, `measure-features.geojson.json`,
  `places.geojson.json`, `counties.geojson.json`, `zctas.geojson.json`,
  `transit-lines.geojson.json`. The original **Bay Area keeps the unprefixed
  names**; every other map uses a `<slug>.` prefix (e.g. `sfmuni.stations.json`).
  Don't rename Bay Area's files — pure diff churn.
- `regions.ts` imports every map's files, builds a `REGIONS: RegionData[]`
  (each entry = `id, name, center, zoom, inPlayCounties` + its 8 data objects),
  reads the active id from `localStorage['bahs.region']` (fallback the first =
  Bay Area, which is also what tests/SSR get since there's no localStorage), and
  re-exports the active map's data: `stationsData`, `poiData`, `playAreaData`,
  `measureFeaturesData`, `placesData`, `countiesData`, `zctasData`,
  `transitLinesData`, plus `IN_PLAY_COUNTIES`, `MAP_NAME`, `MAP_CENTER`,
  `MAP_ZOOM`. `setActiveRegion(id)` persists + `location.reload()`.
- **Every consumer imports from the registry**, not raw JSON: `App.tsx`,
  `MapView.tsx` (center/zoom now `MAP_CENTER`/`MAP_ZOOM`, not hard-coded),
  `railStations.ts`, `metroLines.ts`, `cities.ts`, `counties.ts`, `zip.ts`,
  `poi.ts`, `measureFeatures.ts`, `shareCode.ts` (`MAP_NAME`), `playArea.ts`
  (`IN_PLAY_COUNTIES` re-exported from the registry).
- **Per-map isolation for free:** namespace the storage key
  (`` `bahs.game.v1.${ACTIVE_REGION_ID}` `` in `storage.ts`) so eliminations
  don't bleed across maps; the board code already fingerprints the station id
  set (FNV-1a in `shareCode.ts`), so a code from one map is rejected on another.
- **Picker UI:** a `<select>` in the `App.tsx` header `.toggles-more` group
  (so on mobile it collapses behind the ⚙) whose `onChange` calls
  `setActiveRegion`. The brand shows `{MAP_NAME} Hide & Seek`.

### A map that is a SUBSET of an existing region (no new data)
When the new map is just a filter/clip of a region you already ship (e.g. **SF
Muni** = Bay Area restricted to Muni rail lines J/K/L/M/N/T/F within SF), you do
NOT gather anything — write one build script (`scripts/build_sfmuni_region.py`
is the template) that reads the Bay Area files and:
- keeps only the wanted stations (by line/system), and **strips the other
  systems/lines off shared stops** (a downtown stop shared with BART/Caltrain
  becomes Muni-only) so agency colours/counts read correctly;
- clips every geometry/POI/place/county/ZCTA to the new play-area polygon;
- writes the 8 `<slug>.*` files. Then add one `REGIONS` entry. That's it —
  keep each file the exact same shape so the elimination engine is untouched.

**Subset play area = water-clip + endgame-zone union.** A raw TIGER place/county
polygon includes bay-water wedges reaching toward neighbours (the symptom: "a bit
of Alameda" shows in-play / a city Matching returns the wrong across-the-water
city). Clip it: `place.difference(water)` with the same `bay_water_mask.geojson`
the Bay Area pipeline uses. Then **union each station's 0.25 mi endgame hiding
disk** into the play area (and re-clip to land), otherwise an edge station's
endgame zone (e.g. Bayshore/Sunnydale on SF Muni) gets dimmed out of play. Build
the disk with a geodesic circle at **R = 6371 km** so it matches
`circlePolygon()` in `src/lib/geo.ts` exactly (pad ~0.01 mi so the rendered
128-gon sits fully inside). Keep waterfront POIs that sit just offshore with a
tiny `play_area.buffer(0.0006)` (~40 m) containment test — big enough for pier
museums, far too small to re-admit across-the-bay islands. `scripts/build_sfmuni_region.py`
is the worked example. Note the SF **city** polygon lives in the SHARED
`places.geojson.json` (used by city Matching on *both* maps), so clip the wedge
there too, not just in the `<slug>.*` copy.

### Region-adaptive UI (don't hardcode per map)
A subset/single-agency map should hide controls that are meaningless for it, but
by a **derived condition**, never `if (region==='sfmuni')`:
- **Agency chip** (`.ssys` in `App.tsx` suspects rows): hide when
  `SINGLE_AGENCY` (from `regions.ts` — `AGENCIES.length <= 1`). SF Muni = 1 agency
  ("Muni") → hidden; Bay Area = 5 → shown. The `Systems` legend list likewise
  filters to `SYSTEM_ORDER.filter(sys => STATIONS.some(s => s.systems.includes(sys)))`
  so zero-count agencies don't render.
- **Weekday/Weekend toggle** (`DayToggle` in the header): compute
  `dayTypeMatters` = the eligible-station **id set** differs between `wd`/`we`
  (`headwayMin[day] <= ELIGIBLE_HEADWAY_MIN`) **OR** any station is on a
  `WEEKEND_EXCLUDED_LINES` line. Hide the toggle when false and collapse the
  legend eligibility line to a single count. SF Muni runs daily → hidden; Bay
  Area has weekday-only Caltrain (263 vs 264 eligible) → shown.
- **Tab title**: `index.html` ships a non-region-specific static `<title>`
  ("Jet Lag: Hide & Seek"); a `useEffect` in `App.tsx` then sets
  `document.title = \`${MAP_NAME} Hide & Seek\`` so it tracks the active map.

## Verify
`npm run lint && npx tsc -b --noEmit && npm test && npm run build`, then `npm run dev` and
confirm the new region renders and the toggles/filters behave.
