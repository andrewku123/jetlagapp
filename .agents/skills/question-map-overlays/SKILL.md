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
const ends = bisectorPolyline(from, to, LINE_LENGTH_MI)  // from geo.ts
const hotSide = params.answer === 'hotter' ? to : from
```
**Mercator-bowing gotcha (this bit people twice):** do NOT draw the boundary or
build the shading from `bisectorEndpoints` (just the two far endpoints). A single
straight lat/lon segment over a long span (LINE_LENGTH_MI=60 → 120 mi, and the
300-mi shading band → 600 mi) bows visibly once projected to Web Mercator, so the
line stops passing through the A–B midpoint ("the line doesn't bisect") and the
4-corner shading polygon lands on the wrong area. Always **sample** both: draw the
line through `bisectorPolyline(from, to, LINE_LENGTH_MI)`, and shade with
`bisectorHalfPlane(...)`, which is itself a *sampled ribbon* (one long edge is the
sampled bisector, the other is that polyline offset toward the cold side) so both
long edges hug the true geometry. `bisectorEndpoints` is fine only for math
(e.g. tests), not for long rendered geometry.

Render: (1) a `<Polygon>` shading the **colder (eliminated) half-plane** via
`bisectorHalfPlane(from, to, coldSide, 300)` (`coldSide = hotter ? from : to`);
(2) a dashed `<Polyline>` through `ends` (purple); (3) a `<CircleMarker>` with a
"hotter" `<Tooltip>` placed *between* the boundary midpoint and `hotSide` (so it
clears the A/B pins). The A/B/answer tooltips are **not permanent** — they show
for ~5s when the overlay appears/changes then hide (a `thermoLabels` state +
5s `setTimeout`, keyed on a signature of the active thermometer records), so they
don't clutter the map. All `interactive={false}`. Note the `from`/`to` endpoints
already get pins via
`pickedPoints` in `App.tsx`, so a marker exactly on an endpoint is hidden under
its pin. The engine truth is in
`src/lib/elimination.ts` (`gotCloser === (answer === 'hotter')`) — the line is
purely the visual of that boundary; keep them consistent.

## POI Matching / Measuring shading (`match-poi` / `measure-poi`)
Unlike radar/thermometer (whose geometry is simple `geo.ts` helpers inlined in
JSX), POI shading is heavy — a Voronoi cell over up to ~1,583 sites, or a union
of that many disks — so the geometry lives in its own module
`src/lib/questionRegions.ts` and is **memoized** in `MapView`, not recomputed
every render.

- `poiMatchEliminatedRegion(record)` — the seeker's nearest-POI **Voronoi cell**,
  computed by Sutherland–Hodgman half-plane clipping (perpendicular bisectors of
  the seeker's site vs every other site) in an equirectangular projection scaled
  at the seeker's latitude, so it matches the haversine "nearest" the engine
  uses. `answer==='yes'` eliminates **outside** the cell (world-ring minus cell),
  `'no'` eliminates the cell itself.
- `poiMeasureEliminatedRegion(record)` — the **union of disks** (radius = the
  seeker's own nearest-POI distance) around every POI, via `polygon-clipping`.
  `'closer'` eliminates the **complement** of the union, `'further'` eliminates
  the union. Disk segment count adapts to category size (`diskSegments`) so parks
  stay responsive.
- Both return a `LatLngMultiPolygon` (`[lat,lon][][][]`) that drops straight into
  `<Polygon positions={poly} pathOptions={ELIM_FILL} />`.

In `MapView`, `poiRegions = useMemo(...)` keys on a signature string of the active
POI records (`id:active:vetoed:eliminates:poiCat:fromLat:fromLon:answer`) so the
Voronoi/union work only reruns when a POI question actually changes. Each region
also renders a non-interactive `<CircleMarker>` on the seeker's nearest place
(tooltip `your nearest {poiCategoryLabel(cat)}: {name}`). `polygon-clipping` is a
**runtime** dependency (in `dependencies`, not `devDependencies`) because app code
imports it. Keep the shading consistent with the engine truth in
`src/lib/elimination.ts` (`match-poi` / `measure-poi` cases).

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
