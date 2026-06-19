---
name: map-drawing-tools
description: Work on the in-app map drawing tools — compass (circle), straightedge (line), perpendicular bisector, and distance measure. Use when asked to add, change, or fix a drawing/annotation tool on the seeker map.
---

# Map drawing tools

The map has a drawing toolbar (top-right) with five modes, defined by the
`DrawTool` union in `src/types.ts`: `select | compass | line | bisector |
measure`. `select` is the normal "drop a seeker point" mode; the other four
create **annotations** that persist in the saved game.

## Data model (`src/types.ts`)
- `CircleAnnotation` — `{ type: 'circle', lat, lon, radiusMiles, color }` (compass).
- `LineAnnotation` — `{ type: 'line' | 'bisector' | 'measure', aLat, aLon, bLat,
  bLon, color, step? }` (two-point tools). `step` (measure only) is the rounding
  granularity in miles; `0`/absent = exact.
- `Annotation = CircleAnnotation | LineAnnotation`, stored on
  `GameState.annotations` and persisted via `src/lib/storage.ts` (localStorage).

## Where it lives (`src/components/MapView.tsx`)
- Toolbar state: `tool`, `radiusMi` (compass), `measureStep` (measure rounding),
  `color`, and `pending` (the first click of a two-point tool).
- `handleClick(p)`:
  - `compass` → emits a `circle` immediately at the clicked center.
  - `line | bisector | measure` → first click sets `pending`; second click emits
    the annotation (carrying `step: measureStep` for `measure`).
- Rendering: circles via Leaflet `<Circle>` (radius in metres = `miles * 1609.344`);
  lines via `<Polyline>`. Bisector endpoints come from `bisectorEndpoints()`;
  measure shows a permanent `<Tooltip>` label.
- Every annotation is click-to-delete (`onDeleteAnnotation`). The toolbar also has
  **Undo** (removes the in-progress `pending` first click if any, otherwise the
  most-recently-added annotation via `onDeleteAnnotation(annotations.at(-1).id)`)
  and **Clear** (`onClearAnnotations`).
- Handlers are owned by `src/App.tsx` (`addAnnotation` / `deleteAnnotation` /
  `clearAnnotations`) and passed down as props.

## Geometry helpers (`src/lib/geo.ts`)
- `haversineMiles(a, b)` — great-circle miles (used for the measure label and the
  radar/thermometer engine; keep it the single source of distance truth).
- `formatMiles(miles, step = 0)` — legacy mile-only label formatter (kept for tests).
- `formatDistance(miles, units, step = 0)` — unit-aware measure label formatter;
  converts to km when `units === 'metric'`. `step > 0` snaps to that bucket in the
  *display* unit, else 2 decimals. The measure tool uses this (see the
  `units-toggle` skill).
- `bisectorEndpoints(a, b, lengthMiles)` — endpoints of the perpendicular
  bisector of A–B (the thermometer hotter/colder boundary), via a local
  equirectangular projection. `LINE_LENGTH_MI` in MapView sets the half-length.

## Adding or changing a tool
1. Add the mode to the `DrawTool` union and (if a new shape) an annotation type.
2. Add a toolbar button to the `['select','compass',…]` map + its icon/label.
3. Handle it in `handleClick` (immediate vs. two-point) and in the render loop.
4. If it needs an option (like compass radius / measure rounding), add a small
   `<select>` gated on `tool === '<mode>'`, store it in state, and persist any
   per-annotation choice on the annotation object.
5. Keep all distances in miles via `geo.ts`; never inline a haversine.

## Verify
`npm run lint && npx tsc -b --noEmit && npm test`, then `npm run dev`: draw each
shape, confirm the measure label respects the rounding selector, delete a single
annotation, "Clear drawings", and reload the page to confirm annotations persist.
Unit tests for the helpers live in `src/lib/geo.test.ts`.
