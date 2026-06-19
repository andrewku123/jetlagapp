---
name: question-map-overlays
description: Draw logged questions on the map — radar circles and the thermometer hotter/colder boundary — and keep them click-through so stations stay selectable. Use when asked to visualize a question type or fix overlay click-blocking.
---

# Question map overlays

Active, eliminating questions are drawn on the map in `src/components/MapView.tsx`
from the `records` prop (`game.questions`). These overlays are **decorations**:
they must never intercept clicks, or stations underneath them become
unselectable.

## Click-through rule (important)
Every question overlay (and the thermometer markers) sets
`interactive={false}`. Overlays render *after* the station markers, so an
interactive overlay would sit on top and swallow clicks — this is exactly the
"can't select stations inside a radar" bug. Keep `interactive={false}` on all of
them. (Manual compass/line annotations are a separate, intentionally clickable
layer — see `map-drawing-tools`.)

## Radar circles
Filter `records` to `active && eliminates && kind === 'radar'` and render a
Leaflet `<Circle>`:
- center `[params.lat, params.lon]`, radius `params.radiusMiles * 1609.344` (m).
- green solid fill for `answer === 'yes'` (inside kept), red dashed for `no`.
- `interactive={false}`.

## Thermometer boundary
Filter to `active && eliminates && kind === 'thermometer'`. The hotter/colder
boundary is the **perpendicular bisector** of the `from → to` segment:
```ts
const ends = bisectorEndpoints(from, to, LINE_LENGTH_MI)  // from geo.ts
const hotSide = params.answer === 'hotter' ? to : from
```
Render a dashed `<Polyline>` through `ends` (purple) plus a small
`<CircleMarker>` dot on `hotSide` (red) so it's clear which half-plane is
"hotter". Both `interactive={false}`. The engine truth is in
`src/lib/elimination.ts` (`gotCloser === (answer === 'hotter')`) — the line is
purely the visual of that boundary; keep them consistent.

## Adding an overlay for a new question kind
1. Add a `records.filter(...)` block keyed to the kind.
2. Derive geometry from `params` (reuse `geo.ts` helpers; don't inline math).
3. Render Leaflet shapes with `interactive={false}`.
4. If it shows a distance/elevation, format via `formatDistance` /
   `formatElevation` with `units` (see `units-toggle`).

## Verify
`npm run lint && npx tsc -b --noEmit && npm test`, then `npm run dev`: log a
radar and confirm you can still click a station inside it; log a thermometer and
confirm the dashed bisector appears with the hot-side dot on the correct end.
