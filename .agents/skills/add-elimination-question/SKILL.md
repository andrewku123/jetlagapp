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

## Conventions
- Keep predicates pure and total; never throw on missing params.
- Distances: stations store metric (`airportDist` in metres, `elevation` in
  metres); the engine works in miles via `haversineMiles` — convert consistently.
- Geometric questions (radar/thermometer) store the seeker's point(s) in
  `params`; matching/measuring store the seeker's own attribute `value`.

## Verify
`npm run lint && npx tsc -b --noEmit`, then `npm run dev`: log the new question,
confirm the "N of M possible" count and the map's eliminated markers update, and
that toggling the record off in History restores the stations.
