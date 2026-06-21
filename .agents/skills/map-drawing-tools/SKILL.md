---
name: map-drawing-tools
description: Work on the in-app map drawing tools — compass (circle), straightedge (line), perpendicular bisector, and distance measure. Use when asked to add, change, or fix a drawing/annotation tool on the seeker map.
---

# Map drawing tools

The map has a drawing toolbar (top-right) with six modes, defined by the
`DrawTool` union in `src/types.ts`: `select | compass | line | bisector |
measure | coord`. `select` is the normal "drop a seeker point" mode; `compass /
line / bisector / measure` create **annotations** that persist in the saved game;
`coord` is a transient read-out tool (drops a temporary dot, shows the clicked
lat/lon at 6 dp and auto-copies it to the clipboard — no annotation, clears on
tool switch).

## Data model (`src/types.ts`)
- `CircleAnnotation` — `{ type: 'circle', lat, lon, radiusMiles, color }` (compass).
- `LineAnnotation` — `{ type: 'line' | 'bisector' | 'measure', aLat, aLon, bLat,
  bLon, color, step? }` (two-point tools). `step` (measure only) is the rounding
  granularity in miles; `0`/absent = exact.
- `Annotation = CircleAnnotation | LineAnnotation`, stored on
  `GameState.annotations` and persisted via `src/lib/storage.ts` (localStorage).

## Where it lives (`src/components/MapView.tsx`)
- Toolbar state: `tool`, `radiusMi` + `compassCustom` (compass radius, incl.
  "Custom…"), `measureStep` (measure rounding), `color`, and `pending` (the first
  click of a two-point tool).
- `handleClick(p)`:
  - `compass` → emits a `circle` immediately at the clicked center.
  - `line | bisector | measure` → first click sets `pending`; second click emits
    the annotation (carrying `step: measureStep` for `measure`).
- Rendering: circles via Leaflet `<Circle>` (radius in metres = `miles * 1609.344`,
  `interactive={false}`); lines via `<Polyline>`. Bisector endpoints come from
  `bisectorEndpoints()`; measure shows a permanent `<Tooltip>` label.
- Handlers are owned by `src/App.tsx` (`addAnnotation` / `deleteAnnotation` /
  `updateAnnotation` / `clearAnnotations`) and passed down as props.

## Editing & moving placed annotations
Annotations are **editable after placement**. The key design rule, learned the
hard way: **drag and click-to-snap are mutually ambiguous on one handle** (a
click is a zero-distance drag), so they are **split by mode**, NOT made to
coexist on the same handle:
- **Select (✋) mode:** handles are `draggable` + `interactive` → drag to move,
  click to open edit popups.
- **drawing tool active:** handles are `draggable={false}` + `interactive={false}`
  → clicks fall through to the map, where the 14px snap reuses the point. No
  handle drag, no popup, no ambiguity.

Gate BOTH `draggable={selectMode}` and `interactive={selectMode}` on each
`<Marker>`, and give the marker a `key` that includes `selectMode`
(`` key={`${a.id}-center-${selectMode}`} `` / `` key={`${a.id}${k}-${selectMode}`} ``).
**The key is load-bearing:** react-leaflet does NOT re-initialise a marker's
`interactive`/dragging when the prop flips, so without the remount, switching to
Select mode leaves the handle non-draggable. The `key` forces a fresh marker per
mode. (An even earlier attempt kept handles always interactive+draggable and
tried to let drag+click coexist — drawing-mode drag silently broke because the
handle absorbed the press but, when `draggable=false`, never fired its own click
either; this split-by-mode design is what actually works. Verified via CDP.)

- **Drag handles** — every annotation renders Leaflet `<Marker>`s
  (`draggable={selectMode}`) using the `handleIcon(color, big?)` divIcon. On
  `dragend` we read `e.target.getLatLng()` and call `onMovePoint(from, to)`:
  - compass: one big center handle (moves the circle + any coincident points).
  - line/measure: two handles at the endpoints.
  - bisector: two handles at the **reference points** `a`/`b` (the drawn line is
    recomputed from them via `bisectorPolyline`/`bisectorEndpoints`).
- **Linked drag (coincident points move together).** `dragend` does NOT patch the
  one annotation; it calls `onMovePoint(from, to)` (`movePoint` in `App.tsx`),
  which moves *every* annotation point sitting at exactly `from` to `to`. Because
  snapping copies coords verbatim, points dropped on the same spot are
  bit-identical and therefore drag as a group — a shared point stays shared. Plain
  `===` coord comparison is the linkage (no anchor/id model). Single
  (non-coincident) points behave exactly as before. The radius/step popups still
  use `onUpdateAnnotation`; only position drags use `onMovePoint`.
- **Click-to-snap / reuse a point** — because handles are non-interactive while a
  drawing tool is active, reuse happens entirely through the **map**: `MapClicks`
  snaps any map click within **14 screen pixels** (`map.latLngToContainerPoint`,
  zoom-aware so zooming in lets you place a new point right next to an existing
  one) of a `snapPoints` entry — including a click landing *exactly on* a handle
  (the click passes through to the map). `snapPoints` = all annotation endpoints +
  the in-progress `pending` point, only while a drawing tool is active.
  **Exception: with the compass active, circle centers are excluded from
  `snapPoints`** (see compass rule below). The snap threshold lives in the
  `SNAP_PX` constant (14). (The handle `click` handlers still exist but only fire
  in Select mode — there they open edit popups, not snap.)
- **Snap-target highlight.** The snap dot the *next* click would land on is
  enlarged + tinted so the reuse is obvious. `MapClicks`'s `mousemove`/`mouseout`
  report the nearest in-range `snapPoints` index via `onHover` → `snapHover`
  state; `handleClick` sets `snapPulse` to the just-snapped point and clears it
  ~450ms later (so the snap still reads on touch, which has no hover). In the
  `snapPoints.map`, a snap `CircleMarker` is `active` when its index is
  `snapHover` *or* its coords equal `snapPulse`; active dots render at `radius 11`
  in the draw `color`, idle at `radius 6` white. `onHover` calls with an unchanged
  value are cheap (React `useState` bails out), so per-move re-renders are fine.
  **But never let `mousemove` re-render *during a handle drag*:** react-leaflet
  calls `marker.setLatLng(props.position)` on every render (the `position` array is
  a new ref each time), so a mid-drag re-render snaps the handle back to its
  original spot and cancels the drag. The robust guard is in `MapClicks.mousemove`:
  **skip the hover update whenever a mouse button is held** (`if
  (e.originalEvent?.buttons) return`). It fires before any re-render and is
  independent of which marker (if any) is being dragged. (A `draggingRef` set on
  handle `mousedown`/cleared on `dragend` also exists as a backstop. In practice
  `snapPoints` is empty in Select mode anyway — the only mode where handles drag —
  so hover never fires during a drag, but keep the buttons-guard for safety.)
- **Edit popups render ONLY in Select (✋) mode** (plus the compass special-case).
  This keeps popups from interrupting drawing/snapping:
  - compass center → `<RadiusEditPopup>` (a `<select>` of `RADAR_OPTIONS` +
    "Custom…" number input → `onUpdateAnnotation(id, { radiusMiles })`, with
    **Delete**). Rendered when `selectMode || tool === 'compass'`.
  - measure line → `<MeasureEditPopup>` (rounding `<select>`: exact / ½ / 1 / 5 /
    10 / Custom… → `onUpdateAnnotation(id, { step })`, unit-aware, with
    **Delete**). Rendered + the polyline `interactive` only when
    `selectMode && a.type === 'measure'`.
  - **line / bisector have NO popup** (the old "Straightedge line | Delete" /
    "Perpendicular bisector | Delete" popups were removed at the user's request).
    Delete a line/bisector via **Undo** or just redraw it.
- **A bisector renders ONLY its perpendicular line — no distance label.** Only
  `measure` shows a distance `<Tooltip>`. A bisector is the perpendicular bisector
  of A–B; it deliberately does NOT draw the A–B connector segment or its length
  (an experimental gray A–B connector + distance label was added then removed — it
  cluttered the map with overlapping labels and isn't what the bisector is for;
  use the Measure tool to measure two points).
- **Compass center click rule** — while the compass is active, clicking an
  existing center **opens its edit bar** (via `marker.openPopup()` in the click
  handler) instead of dropping a concentric ring. To draw a deliberate concentric
  ring at the same center, paste the same lat/lon (the 📍 coord tool copies it)
  with a different radius into the **coordinate-entry box**. This is why circle
  centers are dropped from `snapPoints` under the compass (so a near-click can't
  silently stack a ring).
- The toolbar still has **Undo** (removes the in-progress `pending` first click if
  any, otherwise the most-recently-added annotation) and **Clear**
  (`onClearAnnotations`).
- `updateAnnotation(id, patch)` in `App.tsx` maps over `game.annotations` and
  merges the patch onto the matching `id`; persists via storage like the others.

## Toolbar UI conventions
- Vertical slim icon column (`['select','compass','line','bisector','measure','coord']`),
  each `<button>` carries a `data-tip` (CSS hover tooltip to the left) + `aria-label`.
- Undo/Clear sit **horizontal when a tool is open** (panel is already wide from its
  options) and **vertical when closed** (stays slim, never widens on its own).
- Per-tool option rows (`.draw-radius` for compass radius / measure rounding,
  `.draw-colors`, the coord read-out, the coordinate-entry box) are gated on
  `tool === '<mode>'`. The custom-radius `<input>` uses `flex-basis:100%` so it
  drops to its own line inside the wrapping row.

## Gotchas (learned the hard way)
- **Popup buttons must not drop a new point.** In `compass` mode the map `click`
  handler creates a circle on every click. A click on a popup's Delete button
  re-fires as a Leaflet map click and would drop a *second* circle. The reliable
  guard is at **mousedown** (capture phase), NOT at click: when Delete runs,
  React removes the popup from the DOM *before* the map `click` handler reads
  `originalEvent.target`, so checking the target at click time sees a detached
  node and the `.leaflet-popup` lookup fails — a new circle drops exactly where
  the button was. `MapClicks` therefore records on `mousedown`/`touchstart`
  (document, capture) whether the press began inside `.leaflet-popup` /
  `.leaflet-marker-icon` (`inAnnotationControl`) and suppresses the next map
  click (it also still checks the click target as a backstop). Keep this
  mousedown-based guard if you add new immediate-draw tools.
- **Opening a measure-endpoint popup needs `setTimeout(..., 0)`.** The measure
  endpoints (`a`/`b` markers) bind a `<Popup>` and, in Select mode, their `click`
  handler calls `marker.openPopup()` so clicking an endpoint shows the rounding
  editor (clicking the line body works too). Calling `openPopup()` synchronously
  in the click handler is swallowed — the same click cycle immediately re-closes
  it (`closePopupOnClick`), so the popup never appears. Defer it one tick
  (`setTimeout(() => mk.openPopup(), 0)`) and it stays open. The compass-center
  popup happens not to hit this race, but use the deferred call if you add popups
  to other endpoint handles.
- **The measure distance label opens the rounding popup too.** In Select mode the
  measure's permanent `<Tooltip>` (the `measure-label`) is `interactive` with a
  `click` handler, so clicking the label is a third way to reach the rounding
  editor (line body + endpoints being the other two). The popup is bound to the
  `<Polyline>`, not the tooltip, so the click can't use `e.target`: keep the
  Polyline in a `measureLineRefs` ref keyed by `a.id` and call
  `setTimeout(() => ln.openPopup(), 0)` (same close-on-click race as above). The
  tooltip is `interactive` only in Select mode (a `key={`tip-${selectMode}`}`
  forces it to remount when the mode flips so Leaflet re-applies `interactive`),
  so it never eats snap clicks while drawing. `.measure-label-click` just adds a
  pointer cursor.
- **The measure label won't follow a dragged endpoint** unless the `<Polyline>`
  remounts: a Leaflet permanent `<Tooltip permanent direction="center">` anchors
  to the line's center only when (re)bound. The Polyline therefore has a `key`
  that includes the rounded endpoint coords so it remounts on `dragend` and the
  label re-centers.
- **Toolbar custom-value input** (`.draw-radius-input`) uses `flex-basis: 100%`
  inside the `flex-wrap` `.draw-radius` row so it drops to its own line instead of
  overflowing the panel, and is styled dark (`--panel2`) to match. Popup `<label>`
  selects get `margin-left` so the label text isn't flush against the dropdown.

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
shape, confirm the measure label respects the rounding selector, **in Select (✋)
mode drag an endpoint / the compass center and confirm the shape + label update
(incl. linked drag of coincident points)**, **with a drawing tool active click an
existing point — even directly on its handle — and confirm it snaps/reuses it**,
**with compass active click an existing center and confirm it opens the edit bar
instead of stacking a ring**, **confirm a bisector shows only the perpendicular
line (no distance label)**, edit a placed circle's radius / a measure's rounding
via their popups (incl. Custom…) **in Select mode**, confirm line/bisector have no
popup, "Clear drawings", and reload to confirm annotations persist. For
deterministic interaction tests (drag/snap/popup) drive real clicks via CDP and
read `localStorage` — see the `verify-map-interactions` skill. Unit tests for the
helpers live in `src/lib/geo.test.ts`.
