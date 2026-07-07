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
tool switch). The coord dot is rendered in its own dedicated `coordDot` pane
(z 690, `CoordPane`) so it sits ABOVE the station dots (station SVG pane z 450)
and the marker/tooltip panes (measure endpoints z 600 / labels z 650) — a
`CircleMarker` in the default overlay pane (z 400) would be hidden under the very
station you clicked to read its coordinate.

**GOTCHA — a canvas renderer in a high pane blankets ALL clicks (shipped a
"stations unclickable until refresh" bug).** The map runs with `preferCanvas`,
so any vector (e.g. the coord dot `CircleMarker`) placed in a pane lazily gets a
**canvas** renderer in that pane. Unlike SVG — where only the individual `<path>`s
are hit targets and the empty svg is click-through — a canvas is one opaque
element spanning the whole map that captures every click in its box. Because the
`coordDot` pane sits above the station pane, that canvas swallowed every
station/POI/map click, and it lingered after leaving the coord tool, so the map
stayed dead until a page refresh. Fix: the coord dot is a purely visual read-out
(copy is via the toolbar button, not the dot), so `CoordPane` sets the pane
`pointer-events: none` and the `CircleMarker` is `interactive={false}`. **Rule:
any pane stacked above the station pane that holds only visual (non-clickable)
content MUST be `pointer-events: none`, or its canvas renderer will eat all
clicks.** This is why the station pane itself uses an **SVG** renderer (see the
`StationRenderer` note / mobile-touch-targets skill) — so a miss falls through to
the POI layer below.

## Data model (`src/types.ts`)
- `CircleAnnotation` — `{ type: 'circle', lat, lon, radiusMiles, color }` (compass).
- `LineAnnotation` — `{ type: 'line' | 'bisector' | 'measure', aLat, aLon, bLat,
  bLon, color }` (two-point tools). The measure label always shows the exact
  distance (2 dp) — there is no rounding option.
- `Annotation = CircleAnnotation | LineAnnotation`, stored on
  `GameState.annotations` and persisted via `src/lib/storage.ts` (localStorage).

## Where it lives (`src/components/MapView.tsx`)
- Toolbar state: `tool`, `radiusMi` + `compassCustom` (compass radius, incl.
  "Custom…"), `color`, and `pending` (the first
  click of a two-point tool).
- `handleClick(p)`:
  - `compass` → emits a `circle` immediately at the clicked center.
  - `line | bisector | measure` → first click sets `pending`; second click emits
    the annotation.
- Rendering: circles via Leaflet `<Circle>` (radius in metres = `miles * 1609.344`,
  `interactive={false}`); lines via `<Polyline>`. Each circle also draws a dashed
  **radius spoke** (center → edge) with the distance label at its midpoint; the
  spoke points **due east** — it's `circlePolygon(center, r)[n/4]` (index 32 of the
  128-point ring = bearing 90°). Use `[0]` for north, `[n/4]` east, `[n/2]` south.
  Bisector endpoints come from
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
  (non-coincident) points behave exactly as before. The compass radius popup still
  uses `onUpdateAnnotation`; only position drags use `onMovePoint`.
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
  - measure line → `<MeasureEditPopup>` (just a **Delete** button; the measure
    tool has no rounding option). Rendered + the polyline `interactive` only when
    `selectMode && a.type === 'measure'`.
  - **line / bisector have NO popup** (the old "Straightedge line | Delete" /
    "Perpendicular bisector | Delete" popups were removed at the user's request).
    Delete a line/bisector via **Undo** or just redraw it.
- **A bisector draws TWO polylines.** (1) the long perpendicular bisector line
  (orange dashed, recomputed from A/B), and (2) a short gray dashed **A–B
  connector** carrying a permanent `<Tooltip>` distance label (the length of the
  segment being bisected). Like the measure label, this connector MUST have a
  `key` that includes the rounded endpoint coords (`` key={`bcon-${a.id}-…`} ``) so
  it remounts on `dragend` — otherwise the permanent `Tooltip permanent
  direction="center"` stays anchored to the *stale* center and the label appears
  detached from the line after dragging endpoints around (the exact bug class as
  the measure label; see the remount gotcha below).
- **Compass center click rule** — while the compass is active, clicking an
  existing center **opens its edit bar** (via `marker.openPopup()` in the click
  handler) instead of dropping a concentric ring. To draw a deliberate concentric
  ring at the same center, paste the same lat/lon (the 📍 coord tool copies it)
  with a different radius into the **coordinate-entry box**. This is why circle
  centers are dropped from `snapPoints` under the compass (so a near-click can't
  silently stack a ring). **IMPORTANT exception to the mode-split rule:** the
  compass-center `<Marker>` must be `interactive={selectMode || tool === 'compass'}`
  (NOT just `selectMode`) — otherwise in compass mode the center is click-through,
  the click falls to the map, and since centers aren't in `snapPoints` it drops a
  *new* circle instead of opening the edit bar. Keep `tool === 'compass'` in that
  marker's remount `key` too. (`draggable` stays `selectMode`-only — compass mode
  edits, it doesn't drag.) Endpoint handles for line/bisector/measure keep the
  plain `interactive={selectMode}`.
- The toolbar still has **Undo** (removes the in-progress `pending` first click if
  any, otherwise the most-recently-added annotation) and **Clear**
  (`onClearAnnotations`).
- `updateAnnotation(id, patch)` in `App.tsx` maps over `game.annotations` and
  merges the patch onto the matching `id`; persists via storage like the others.

## Toolbar UI conventions
- **The whole toolbar collapses to a single 1×1 🧰 button** (`.draw-toggle`, state
  `toolbarOpen` in MapView) so it barely covers the map while you're panning /
  searching / eliminating. Tapping 🧰 opens the tool column; tapping it again
  **closes AND calls `selectTool('select')`** (drops back to pan/select mode) so a
  drawing tool is never left armed behind a collapsed box. Everything below the
  toggle — the tool icon column AND the per-tool option rows — is gated on
  `{toolbarOpen && (…)}`, so a closed toolbar renders literally just the 🧰. This
  keeps the expanded options (radius/colors/coords/undo/clear) from ever blanketing
  ~40% of a phone screen the way the old always-open panel did.
- Tool icon column (`['select','compass','line','bisector','measure','coord']`),
  each `<button>` carries a `data-tip` (CSS hover tooltip to the left) + `aria-label`.
- **The 🧰 toggle is right-aligned** at the top of the panel: `.draw-toolbar` is a
  `display:flex; flex-direction:column` and `.draw-toggle { align-self: flex-end }`.
- The coord tool's empty-state hint is kept short (`"Click map to copy coords."`
  with `.cr-hint { white-space: nowrap }`) so the panel width matches the populated
  `lat, lon` / `Copied ✓` state instead of ballooning into a 2-line blurb.
- Undo/Clear sit **horizontal when a tool is open** (panel is already wide from its
  options) and **vertical when closed** (stays slim, never widens on its own).
- Per-tool option rows (`.draw-radius` for compass radius,
  the coord read-out, the coordinate-entry box) are gated on
  `toolbarOpen && tool === '<mode>'`. The custom-radius `<input>` uses
  `flex-basis:100%` so it drops to its own line inside the wrapping row.
- **Colour swatches sit vertically beside the tool icons**, not in a row below.
  The tool icon column and `.draw-colors` are wrapped in `.draw-tools-row`
  (`display:flex; flex-direction:row; align-items:center`); the swatches render
  only for colour-drawing tools (`tool !== 'select' && tool !== 'coord'`). CSS
  `.draw-tools-row .draw-colors { flex-direction:column; margin-top:0;
  align-items:center; justify-content:center }` stacks them and centres them
  vertically against the taller icon column. This uses the otherwise-empty space
  next to the icons so the panel gains no height from the swatches. (There is only
  ONE `.draw-colors` block now — inside `.draw-tools-row` — don't leave the old
  horizontal one below `.draw-radius`.)

## Popups auto-close after an action (`closePopup`)
Station-popup action buttons (Star aside — Eliminate / Restore / Endgame here /
Exit endgame) **close their own popup after acting** so the map/zone is
immediately visible on mobile. MapView captures the live Leaflet map via a tiny
child that calls `useMap()` (`MapRefCapture`, rendered inside `<MapContainer>`)
into `mapInstanceRef`; `const closePopup = () => mapInstanceRef.current?.closePopup()`.
Each action is wired `onClick={() => { onToggleEliminate(st.id); closePopup() }}`
etc. `useMap()` only works **inside** the MapContainer subtree, hence the helper
component — don't try to read the map instance from the outer component.

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
  handler calls `marker.openPopup()` so clicking an endpoint shows the edit
  (Delete) popup (clicking the line body works too). Calling `openPopup()` synchronously
  in the click handler is swallowed — the same click cycle immediately re-closes
  it (`closePopupOnClick`), so the popup never appears. Defer it one tick
  (`setTimeout(() => mk.openPopup(), 0)`) and it stays open. The compass-center
  popup happens not to hit this race, but use the deferred call if you add popups
  to other endpoint handles.
- **The measure distance label opens the edit popup too.** In Select mode the
  measure's permanent `<Tooltip>` (the `measure-label`) is `interactive` with a
  `click` handler, so clicking the label is a third way to reach the edit
  (Delete) popup (line body + endpoints being the other two). The popup is bound to the
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
- `formatMiles(miles, step = 0)` — legacy mile-only label formatter (kept for tests;
  the app no longer passes a `step`).
- `formatDistance(miles, units)` — unit-aware measure label formatter; converts to
  km when `units === 'metric'`, always 2 decimals. The measure tool uses this (see
  the `units-toggle` skill). (It still accepts an optional `step` bucket arg for
  back-compat, but the measure tool no longer passes one.)
- `bisectorEndpoints(a, b, lengthMiles)` — endpoints of the perpendicular
  bisector of A–B (the thermometer hotter/colder boundary), via a local
  equirectangular projection. `LINE_LENGTH_MI` in MapView sets the half-length.

## Adding or changing a tool
1. Add the mode to the `DrawTool` union and (if a new shape) an annotation type.
2. Add a toolbar button to the `['select','compass',…]` map + its icon/label.
3. Handle it in `handleClick` (immediate vs. two-point) and in the render loop.
4. If it needs an option (like compass radius), add a small `<select>` gated on
   `tool === '<mode>'`, store it in state, and persist any per-annotation choice
   on the annotation object.
5. Keep all distances in miles via `geo.ts`; never inline a haversine.

## Verify
`npm run lint && npx tsc -b --noEmit && npm test`, then `npm run dev`: draw each
shape, confirm the measure label shows the exact distance, **in Select (✋)
mode drag an endpoint / the compass center and confirm the shape + label update
(incl. linked drag of coincident points)**, **with a drawing tool active click an
existing point — even directly on its handle — and confirm it snaps/reuses it**,
**with compass active click an existing center and confirm it opens the edit bar
instead of stacking a ring**, **drag a bisector endpoint several times and confirm
its distance label stays glued to the A–B connector midpoint (not stranded at a
stale spot)**, edit a placed circle's radius via its popup (incl. Custom…) /
delete a measure via its popup **in Select mode**, confirm line/bisector have no
popup, "Clear drawings", and reload to confirm annotations persist. For
deterministic interaction tests (drag/snap/popup) drive real clicks via CDP and
read `localStorage` — see the `verify-map-interactions` skill. Unit tests for the
helpers live in `src/lib/geo.test.ts`.
