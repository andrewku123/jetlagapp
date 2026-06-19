---
name: question-map-overlays
description: Draw logged questions on the map — radar circles and the thermometer hotter/colder boundary — shading the eliminated area, and keep them click-through so stations stay selectable. Use when asked to visualize a question type, shade eliminated area, or fix overlay click-blocking.
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

## Shade the ELIMINATED area (not the kept area)
The convention is to shade what a question **removes**, using the shared
`ELIM_FILL` style (translucent red, `weight: 0`, `interactive: false`). The kept
area is left clear. Overlapping eliminations stack (darker = removed by more than
one question), which is the desired read.

## Radar circles
Filter `records` to `active && eliminates && kind === 'radar'`. Build the circle
as a polygon ring with `circlePolygon(center, radiusMiles)` (from `geo.ts`):
- `answer === 'yes'` (within X → keep inside): shade **outside** with a
  `<Polygon positions={[WORLD_RING, ring]} />` — the near-world outer ring minus
  the circle as a hole.
- `answer === 'no'` (keep outside): shade **inside** with
  `<Polygon positions={[ring]} />`.
- Always also draw a thin non-filled `<Circle>` outline so the radius is visible.
- All `interactive={false}` (via `ELIM_FILL`).

## Thermometer boundary
Filter to `active && eliminates && kind === 'thermometer'`. The hotter/colder
boundary is the **perpendicular bisector** of the `from → to` segment:
```ts
const ends = bisectorEndpoints(from, to, LINE_LENGTH_MI)  // from geo.ts
const hotSide = params.answer === 'hotter' ? to : from
```
Render: (1) a `<Polygon>` shading the **colder (eliminated) half-plane** — a wide
band built from `bisectorEndpoints(from, to, 300)` pushed ~8° toward the cold
side (`coldSide = hotter ? from : to`); (2) a dashed `<Polyline>` through `ends`
(purple); (3) a `<CircleMarker>` with a permanent "hotter" `<Tooltip>` placed
*between* the boundary midpoint and `hotSide` (so it clears the A/B pins). All
`interactive={false}`. Note the `from`/`to` endpoints already get pins via
`pickedPoints` in `App.tsx`, so a marker exactly on an endpoint is hidden under
its pin. The engine truth is in
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
