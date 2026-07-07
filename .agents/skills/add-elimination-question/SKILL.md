---
name: add-elimination-question
description: Add a new Jet Lag question type to the seeker tool's auto-elimination engine. Use when asked to support a new Matching/Measuring/Radar/Thermometer/Tentacles question or any new filter.
---

# Add an elimination question

A question type flows through four files. The engine eliminates a station when an
active, `eliminates: true` record says the station is inconsistent with the
recorded answer. Each station carries precomputed attributes so a question is
just a pure predicate over `(station, record.params)`.

## The four touch points

1. **`src/types.ts`** — add the new kind to the `QuestionKind` union.

2. **`src/data/questions.ts`** — add a `QuestionMeta` entry to `QUESTION_CATALOG`
   (`kind`, `category`, `label`, `cards` = the hider's card cost in the medium
   game, `eliminates`, `blurb`). Setting `eliminates: false` makes it log-only
   (like `photo`).

3. **`src/lib/elimination.ts`** — add a `case '<kind>':` to `stationPasses` that
   returns whether the station is **still consistent** with the answer. Pattern:
   compute the station's value, compare to the seeker's, and XOR against the
   answer, e.g.
   ```ts
   case 'match-foo': {
     const same = station.foo != null && station.foo === s(p.value)
     return same === (p.answer === 'yes')
   }
   ```
   Use the `n()` / `s()` coercers for params. **Return `true` when the station's
   attribute is unknown** (`null`) so missing data never wrongly eliminates
   (see `measure-sealevel`).

4. **`src/components/QuestionForm.tsx`** — render the inputs for the new kind
   (the dropdowns/answer buttons) and assemble the `params` bag + `answer` that
   `stationPasses` reads. If the question needs a map point, reuse the existing
   "use last click" pattern (the form receives `lastClick`).
   - **Subject dropdown is flat, not nested.** The primary "Question" `<select>`
     is built from `subjectOptions`/`subjectGroups`: each `QUESTION_CATALOG` kind
     in the active category becomes one option, **except** `match-poi`/`measure-poi`
     which expand into one option per `QUESTION_POI_CATEGORIES` entry (value encoded
     `` `${kind}::${cat}` ``, grouped via `POI_SUBJECT_GROUP`; non-POI kinds via
     `KIND_SUBJECT_GROUP`). `pickSubject` splits on `::` to set `kind` (+ `poiCat`).
     So a new POI category shows up automatically; a new non-POI kind just needs a
     `KIND_SUBJECT_GROUP` entry. Do **not** re-introduce a secondary "Place type"
     select — keep every subject in the one dropdown.

## If the question needs new station data
Add the attribute to the `Station` type and populate it in
`scripts/build_attributes.py` (or `build_stations.py` for line/system data), then
re-run the pipeline — see the `rebuild-station-dataset` skill. Examples of
attributes already available: `county`, `city`, `nearestAirport`, `airportDist`,
`elevation`, `nameLength`, `lines`, `systems`.

For POI-based questions (nearest park/hospital/museum, Tentacles counts within a
radius, etc.) you must first add that POI data per station (e.g. nearest-feature
distance or in-radius counts via OSM/Overpass) in the enrichment step, then the
predicate compares those precomputed values.

### Coastline / "distance to the coast" questions
The satellite-clip work already produced reusable coast geometry under `scripts/`,
so a coast question doesn't need new downloads:
- `scripts/play_area_src_water.geojson.json` — the in-play counties' full **legal
  (water-inclusive)** boundaries (land + bay + a Pacific strip), Census TIGERweb.
- `scripts/pacific_ocean.geojson.json` — Census TIGERweb "Pacific Ocean" areal
  hydrography polygons for the region.
- `scripts/build_play_area.mjs` — computes `water-inclusive ∖ Pacific Ocean` (and
  drops the offshore Farallones) via `polygon-clipping`; its output is
  `src/data/play-area.geojson.json` (land + bay only).

To get a **coastline polyline**: take the boundary of the Pacific Ocean polygons
(or the land∖ocean difference) and keep the rings/segments that border land — that
ring is the Pacific shoreline. For a *bay* shoreline, intersect the land boundary
with the bay water instead. Then precompute per station, in `build_attributes.py`,
`coastDistMi` (min distance from the station to that polyline) for a Measuring
question, and/or `nearestSaltwater` ('Pacific' vs 'Bay') for a Matching question,
following the attribute pattern above.

### Ordinal-region measuring (ZIP code / any polygon layer with a numeric name)
`measure-zip` is the template for "is your <region value> smaller or larger than
mine?" over a polygon layer where each region carries an **ordinal (numeric)**
label (US ZIP via Census ZCTA). Pattern, mirroring `cities.ts`/`counties.ts`:
- **Dataset:** `scripts/build_zctas.py` downloads the national Census ZCTA5
  shapefile, clips to `play-area.geojson.json`, simplifies, drops slivers, and
  writes `src/data/zctas.geojson.json` (`properties.name` = the 5-digit ZIP).
  Re-run like the other `build_*` scripts.
- **Lookup lib `src/lib/zip.ts`:** `zipAt(LatLng): string | null` does
  point-in-polygon, then **snaps to the nearest region within `SNAP_M` (200 m)**
  so shoreline-clip erosion at region edges never leaves a station regionless.
  Also exports `zipCodes()` and `zipGeom(name)` (polygon-clipping-ready) for
  shading. Both the seeker's value and each station's value are resolved through
  the **same** `zipAt`, so shading and elimination can't disagree.
- **Elimination:** resolve `seekerZip = s(p.value) || zipAt(seeker)` and
  `stationZip = zipAt(station)`; return `true` (keep) if either is missing;
  else `return (stationZip <= seekerZip) === (p.answer === 'smaller')`.
- Only add this for maps whose regions have numeric labels (US ZIPs) — postcodes
  elsewhere are alphanumeric and not ordinal.

### Tentacle questions ("of all the X within R of me, which are you closest to?")
Two flavours, both size-gated (never in Small; Medium = 1 mi POI subjects; Large
adds 15 mi POI subjects + Metro Lines). The seeker sets **their own** location +
a fixed-per-subject radius; the in-play set is everything of that subject passing
within R of the seeker; the hider names which in-play member they're closest to.
Key rule: a member **outside R never counts**, even if physically closer to a
station than the answer. Elimination keeps a station iff its nearest **in-play**
member is the answer, ties kept (`answerD <= minD + 1e-9`). If 0/1 in play, or the
answer isn't in the in-play set → eliminate nothing (`return true`).

- **POI tentacles** (`tentacle`, `src/lib/poi.ts`): `TENTACLE_CATEGORIES` lists
  the 7 categories with fixed `radiusMi` + size gating; `poisWithinRadius(seeker,
  cat, r)` is the in-play set; `params = { poiCat, radiusMi, fromLat, fromLon,
  value: poiKey(answer), poiName }`. Shading = restricted-Voronoi complement of
  the answer POI's cell over the in-play set (`tentacleEliminatedRegion`) — exact,
  so per-station `pointInMulti === !stationPasses` holds.
- **Metro Lines tentacle** (`tentacle-line`, `src/lib/metroLines.ts`): line
  geometry, not points. `METRO_LINES` is derived from
  `transit-lines.geojson.json` + `stations.json` line names (each GeoJSON feature
  matched to its station-line by min mean distance); `id = system::color`.
  `metroLineDistanceMiles(p, line, refLat)` = projected distance to the polyline;
  `metroLinesWithinRadius(seeker, 15)` is the in-play set; `nearestMetroLine`.
  Radius is the exported constant `METRO_TENTACLE_RADIUS_MI = 15` — never hardcode.
  `params = { radiusMi, fromLat, fromLon, value: line.id, poiName: line.label }`.
  In `QuestionForm`, gate the subject to `gameSize === 'large'` (return `[]` from
  `subjectOptions` otherwise); it's a single subject (no `::param`), so
  `subjectValue`/`pickSubject` fall through to the bare `kind`.
- **Shading for polylines has no closed-form Voronoi** — sample each in-play line
  into points (spacing `max(0.25, totalMi/600)` to bound ~600 sites), build a
  point-Voronoi over all samples, union the answer line's sample cells = keep
  region, shade the complement (`metroLineEliminatedRegion`). This is approximate
  near the boundary, so the region test only asserts agreement for stations
  `> 1 mi` from the boundary (`|answerD - minD| > 1`). **Union the cells with the
  shared `robustUnion` helper, never an incremental pairwise fold** — the many
  adjacent near-collinear cells along a line trip polygon-clipping's
  "Unable to complete output ring" robustness bug; `robustUnion` (snap +
  divide-and-conquer, retries at coarser precision) handles it.

### Point-set measuring (nearest airport / nearest rail station)
"Closer/further from the nearest <point>" over a **discrete point set**. The two
instances are `measure-airport` (the 3 airports, `src/lib/airports.ts`) and
`measure-railstation` (the 264 on-map stations, `src/lib/railStations.ts`). The
helper module exports the point list + `nearest<Thing>Miles(p)` (min haversine).
- **Elimination** (`stationPasses`): `seekerD = nearest…Miles(seeker)`,
  `stationD = nearest…Miles(station)`; `return (stationD <= seekerD) === (answer
  === 'closer')` (tie folds to closer, per the rule below). Keep on unknown.
- **Shading** (`questionRegions.ts`, `<thing>MeasureEliminatedRegion`): the kept
  set is every point within `seekerD` of the hider, i.e. the **union of disks of
  radius `seekerD` centred on each point** (`diskSegments`/`diskRing` +
  `robustUnion`). `closer` ⇒ eliminate the complement (`WORLD_RING ∖ union`),
  `further` ⇒ eliminate the union. Return null when `seekerD <= 0` (seeker sits on
  a point → nothing eliminated). Wire it into `poiEliminatedRegion` + MapView's
  `isShaded()`/`poiRegions` dep filter like any shaded kind.
- **Rail station is endgame-ONLY: logged-only for the suspect list, shades only
  the endgame zone.** Every candidate hiding station IS a rail station (distance 0
  to nearest rail station = itself). The catch: an endgame answer is asked from the
  hider's *real* position (distance > 0), and if you apply it to the map-wide
  station set — every station at distance 0 — a "further" answer eliminates EVERY
  station (a full board wipe you notice the moment you leave the endgame). So rail
  station must **never eliminate a station** and **never shade map-wide**; it only
  carves the endgame hiding zone. Implement it exactly like this (mirrors the
  endgame-tentacle pattern):
  - `stationPasses` case `measure-railstation` → `return true` (always keep).
  - `poiEliminatedRegion` does NOT dispatch `measure-railstation` (returns null) →
    no map-wide shading, and it's kept OUT of MapView's `isShaded()`/`poiRegions`
    dep filter so no map-wide dot/shade is drawn.
  - `eliminatedGeom` (the endgame path) handles `measure-railstation` **directly**
    (calls `railStationMeasureEliminatedRegion` itself, not via
    `poiEliminatedRegion`), so `endgameClippedRegion` still carves the zone with
    the union-of-disks. `endgameRegions` only runs for `r.endgame` records.
  - Catalog entry stays `eliminates: true` (needed so the endgame shading path
    runs), label `Measuring — Rail station (endgame)`. Do NOT precompute a
    per-station `railStationDist` attribute — distance is computed on the fly from
    `stations.json` via `nearestRailStationMiles`.
  - `railStationMeasureEliminatedRegion` itself is un-gated (computes the disks for
    any record); the endgame-only behavior is enforced by the two routing points
    above. Return null when `seekerD <= 0`.

### Tie rule for ALL measuring questions ("equal → the smaller answer")
Every measuring predicate (`measure-poi`, `measure-feature`, `measure-airport`,
`measure-railstation`, `measure-sealevel`, `measure-zip`) must fold an exact tie into the **smaller/closer/
lower** answer, so a station equal to the seeker survives that answer and can never
drop the true hider on a rounding tie. Concretely the kept side is **inclusive**
on the small answer and **strict** on the large one:
`return (stationVal <= seekerVal) === (answer is the 'smaller/closer/lower' one)`.

### Shading must agree with the predicate (`src/lib/questionRegions.ts`)
Any `eliminates:true` kind that shades the map needs an `<kind>EliminatedRegion`
returning the eliminated `LatLngMultiPolygon`, wired in three places:
1. add `if (record.kind === '<kind>') return <kind>EliminatedRegion(record)` to
   `poiEliminatedRegion`;
2. add the kind to `MapView`'s `isShaded()` **and** the `poiRegions` useMemo
   dependency filter (else the shading won't recompute/appear), giving it a `pin`
   or `pin=null` like county/city;
3. the endgame outline + clipped-shading paths already route through
   `poiEliminatedRegion`, so they work once (1) is done.
For a region-union kind (zip/county/city) build the union of the eliminated-side
polygons with the **same** `<= / >` test as the predicate — a per-station test
`pointInMulti(shaded) === !stationPasses` then holds exactly (see
`questionRegions.test.ts`).

### Out-of-bounds features aren't offered (rulebook: outside the map ⇒ doesn't exist)
For `measure-feature`, the Ask form's subject list is
`AVAILABLE_MEASURE_FEATURE_KEYS = MEASURE_FEATURE_KEYS.filter(k =>
featurePolylines(k).length > 0)` — a feature whose geometry is entirely outside
this map's play area (e.g. the state/international border for the Bay Area) has
empty clipped polylines and is **dropped from the dropdown** rather than returning
null at answer time. Keep the full key in `MEASURE_FEATURE_KEYS` so it returns
automatically for a map where it is in-bounds. This is the general rule for any
feature/subject whose existence is map-dependent.

## Veto (hider refuses to answer)
A question is **vetoed** when the hider refuses to answer. You only know a question
is vetoed at *ask* time (you never get a yes/no), and the normal "Log" path forces
you to pick an answer — so the veto action lives in the **Ask form**, not History.
- `QuestionForm`'s `submit(vetoed)` builds the params as usual, then `delete
  params.answer` and sets `vetoed: true` when vetoed. The "**Hider vetoed**" button
  calls `submit(true)`; it's shown for every kind **including `photo`** (a hider
  can refuse a photo too). It validates the identifying params (center/points/
  value) but not an answer.
- A vetoed record has **no `answer`**. `describeRecord` drops the "→ answer" suffix
  when `params.answer == null`. `stationPasses` returns `true` for any vetoed record
  (eliminates nothing — same gate as inactive / non-eliminating); `MapView`'s
  radar/thermometer overlays + `pickedPoints` skip `vetoed` records.
- On History a vetoed row is struck through, tagged `vetoed`, shows **no** Hider
  reward, and only offers **Delete** (no Disable/Un-veto — there's no answer to
  restore; to use it, ask it again with the answer).

## Repeat-question reward multiplier
Game rule: the **nth time the same question is asked**, the hider's card reward is
multiplied by n (2nd ask → ×2, 3rd → ×3 …). This is independent of veto.
- "Same question" is decided by `questionGroupKey(kind, params)` (exported from
  `src/data/questions.ts`, shared by `App.tsx` and `QuestionForm.tsx`):
  - **radar** keys on `radiusMiles` (`radar:5` vs `radar:10` are different
    questions; two 5mi radars are the same — center is ignored).
  - **thermometer** keys on the thermometer the seeker **explicitly chose**
    (`params.thermometerMiles`, set via the "Thermometer (mi)" dropdown in the Ask
    form — `THERMOMETER_OPTIONS` + Custom). Two asks with the same chosen
    thermometer are the same question; a different thermometer is separate. For
    older logged records with no `thermometerMiles`, `questionGroupKey` falls back
    to inferring the bucket from `haversineMiles(A,B)` snapped to the nearest
    `THERMOMETER_OPTIONS` value. `describeRecord` shows the chosen distance
    (`Thermometer 0.5 mi → hotter`); elimination still uses the A/B points.
    Because elimination only uses the perpendicular bisector of A→B (magnitude
    independent), the chosen `thermometerMiles` is otherwise cosmetic — so
    `QuestionForm.submit` **validates that `haversineMiles(A,B)` matches the chosen
    distance** (tolerance `max(0.1 mi, 5%)`, `thermoTolMiles`) and blocks with a
    clear alert if not; a live A↔B readout in the form shows ✓/⚠ before submit.
  - **photo** keys on the chosen photo card (`photo:<title>`). Each photo card is
    a *different* question, so asking two different photos does NOT stack the
    penalty — only re-asking the same card does. The Ask form shows a dropdown of
    `PHOTO` cards (from `questionSets.ts`) filtered to the current `gameSize`
    (passed as a prop), plus the card's `requirement` text and an optional free
    note (`params.description`). `describeRecord` shows `Photo: <title> — <note>`.
  - every other kind keys on `kind` alone (`match-county` ≠ `match-city`, etc.).
  - If you add a new parameterised question whose cost depends on a param, extend
    `questionGroupKey` to include that param.
- `App.tsx` builds `askOrdinal` (memo): records sorted by `createdAt`, each gets a
  1-based ordinal within its group key. A **vetoed** ask still counts toward the tally.
- The History row shows `rewardForKind(kind, n)` (in `src/data/questions.ts`), which
  applies `scaleCards` — multiplies every integer in the "draw X, keep Y" string by
  n. Base reward per kind is the `cards` field in `QUESTION_CATALOG`.
- **Live cost preview:** the Ask form blurb shows what the *next* ask would cost.
  `App.tsx` passes `askGroupCounts` (a `Map<groupKey, count>` over existing
  questions) to `QuestionForm`, which computes `questionGroupKey` from the *current*
  form params (selected radius / set A-B points) and shows `scaleCards(meta.cards,
  count+1)` with a `×n, nth time asked` note. Updates as the radius dropdown or A/B
  points change.

## Conventions
- Keep predicates pure and total; never throw on missing params.
- Distances: stations store metric (`airportDist` in metres, `elevation` in
  metres); the engine works in miles via `haversineMiles` — convert consistently.
- Geometric questions (radar/thermometer) store the seeker's point(s) in
  `params`; matching/measuring store the seeker's own attribute `value`.

## Verify
`npm run lint && npx tsc -b --noEmit && npm test`, then `npm run dev`: log the new question,
confirm the "N of M possible" count and the map's eliminated markers update, and
that toggling the record off in History restores the stations.
