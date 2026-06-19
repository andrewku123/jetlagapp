---
name: units-toggle
description: Switch all displayed measurements between imperial (mi/ft) and metric (km/m). Use when asked to change units, add a unit system, or fix how distances/elevations are shown or entered.
---

# Units toggle (imperial / metric)

A single game-wide setting flips every **displayed** measurement between
imperial (miles, feet) and metric (kilometres, metres). Values are always
**stored canonically** — distances in miles, elevations in metres — and only
converted at the display/input boundary. Default is `imperial` (the Jet Lag
cards are US/imperial).

## State
- `UnitSystem = 'imperial' | 'metric'` in `src/types.ts`, stored on
  `GameState.units` and persisted via `src/lib/storage.ts` (`emptyGame.units =
  'imperial'`). `loadGame()` merges with `emptyGame`, so old saves upgrade
  cleanly.
- Header control: `UnitsToggle` in `src/App.tsx` (a `.seg` button pair, `mi/ft`
  vs `km/m`) wired to `update({ units })`. `game.units` is passed to `MapView`,
  `QuestionForm`, and `describeRecord`.

## Conversion helpers (`src/lib/geo.ts`)
- `KM_PER_MILE = 1.609344`, `FEET_PER_METER = 3.280839895`.
- `formatDistance(miles, units, step = 0)` — miles→display unit; `step` snaps in
  the display unit.
- `formatElevation(meters, units)` — metres→`ft` (imperial) or `m` (metric).

## Where units are applied
- **MapView**: station-popup elevation (`formatElevation`), measure-tool label
  (`formatDistance`), and the measure rounding `<select>` labels (`mi`/`km`).
- **describe.ts**: `describeRecord(record, units)` formats radar radius
  (`formatDistance`) and sea-level altitude (`formatElevation`) in History.
- **QuestionForm**: labels show the current unit; **inputs are converted back to
  canonical units before storing** — custom radar km→miles (`/ KM_PER_MILE`),
  altitude ft→metres (`/ FEET_PER_METER`). The fixed `RADAR_OPTIONS` preset
  dropdown stays in miles (those are the literal game-card distances).

## Adding a new measurement display
1. Store the raw value in canonical units (miles / metres).
2. Render it through `formatDistance` / `formatElevation`, passing `game.units`.
3. If it has an input, label it with the current unit and convert the entry back
   to canonical units in `submit()` before putting it in `params`.

## Verify
`npm run lint && npx tsc -b --noEmit && npm test` (unit conversions are covered
in `src/lib/geo.test.ts`). Then `npm run dev`: toggle `km/m`, confirm a station
popup elevation flips m↔ft, a measure label flips mi↔km, and that logging a
custom radar / altitude in metric stores the same physical value (eliminations
unchanged) as the imperial equivalent.
