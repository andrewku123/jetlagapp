---
name: endgame-mode
description: Work on the seeker tool's endgame mode — locking onto a single suspected station, drawing its hiding-zone circle with the eliminated area shaded, the endgame banner, and entering/exiting. Use when asked to change endgame behavior, the hiding zone, its shading, or the banner.
---

# Endgame mode

Endgame is when the seeker has narrowed it to one station and wants to see the
final hiding zone around it (the radius the hider is allowed to be within for the
end-game phase). It collapses the whole board to that one station + a circle.

## State & wiring
- `GameState.endgame: string | null` (in `src/types.ts`, persisted via
  `src/lib/storage.ts`) — the locked station id, or null.
- `App.tsx`:
  - `endgameStation` = the `Station` for `game.endgame` looked up in the
    eligible `base` list (null if cleared).
  - `hidingRadiusMi = hidingRadiusMi(game.gameSize, game.zoneCurses)` from
    `src/lib/hidingZone.ts` — the size default from `SIZE_PARAMS`
    (`src/data/questionSets.ts`, size auto-derived from station count) times the
    curse multiplier (see *Curse-resized zone* below). Every consumer reads this
    one value; never re-read `SIZE_PARAMS` at a call site.
  - While `endgameStation` is set, `remaining = [endgameStation]` and everything
    else is `eliminated` — so the suspects list and map reduce to the one station.
  - `onStartEndgame(id)` sets `endgame: id`; `onExitEndgame()` sets it back to
    null. Both are triggered from station popups in `MapView`.
- Entry/exit UI (`MapView.tsx`):
  - A station popup shows **🎯 Endgame here** (when not in endgame) /
    **↩ Exit endgame** (when this is the endgame station).
  - A floating **`.endgame-banner`** (top-left, positioned to clear the Leaflet
    zoom `+/−` controls — keep that offset) shows
    `Endgame: <name> — hider within <formatDistance(hidingRadiusMi, units)>` and
    an **Exit** button.

## Map rendering (the shading rule)
The hiding zone uses the **same convention as radar/thermometer questions: shade
the ELIMINATED area, leave the in-play area clear** (see `question-map-overlays`).
For endgame that means shade *outside* the circle, keep the inside clear:
- A `<Polygon>` with two rings — `WORLD_RING` (near-world outer rectangle) and the
  hiding-zone circle (`circlePolygon(center, hidingRadiusMi)`) as the hole —
  filled with `ELIM_FILL` (translucent red, `interactive:false`). Leaflet's
  even-odd rule shades the ring-minus-hole = everything except the zone.
- A `<Circle>` outline (green `#16a34a`, `fill:false`, `interactive:false`) marks
  the zone boundary.
- `MapFit` auto-zooms to the zone when endgame locks on: it fits
  `zoneBoxMeters(hidingRadiusMi)` (`src/lib/mapFit.ts`) once per distinct endgame
  id (manual pan/zoom afterwards is left alone).

### Fitting a one-point board (the blank-map trap)
Endgame collapses `remaining` to one station, so the **first-load** fit gets a
zero-size bounding box. Since the basemap became a MapLibre GL layer there is no
raster `TileLayer` to contribute a `maxZoom`, so `map.getMaxZoom()` is `Infinity`
and `getBoundsZoom(zeroBox)` returns `Infinity` → pixel origin `Infinity` →
`getCenter()` is `(NaN, NaN)` → **the whole map renders white**. It only bites on
reload-with-endgame (or any load where exactly one suspect is left), which is why
entering endgame in a live session looked fine.
Two guards, both required:
- `MapContainer` carries an explicit `maxZoom={MAP_MAX_ZOOM}` so every
  `fitBounds` is clamped. Re-add this if the basemap layer ever changes again.
- `fitTarget(remaining, endgame, radiusMi)` returns a `zone` target (station +
  `zoneBoxMeters`) whenever the board is a single point — endgame, one suspect
  left, or several co-located stations (a multi-agency stop listed twice) — and
  padded station bounds otherwise. `MapFit`'s init effect uses it, so the initial
  fit and the endgame fit frame the zone identically. Regression: `mapFit.test.ts`.

## Curse-resized zone (Prosperous / Tiny Home)
Hider curses resize the zone mid-game. `GameState.zoneCurses:
{ prosperous: number; tiny: number }` counts **casts, not a toggle**, because
Duplicate lets the same curse be played twice.
- `src/lib/hidingZone.ts` owns the maths: each Prosperous is `×1.5`, each Tiny is
  `×0.5`, **compounding** on the current zone (2 Prosperous = `×2.25`, not `×2`);
  `castCurse` / `removeCurse` add and undo one cast; `curseMultiplier` is clamped
  to `[1/64, 64]` and `castCurse` refuses a cast that would leave that range.
- `normalizeCurses` runs in `loadGame`, so pre-curse saves and junk values load as
  zero counts.
- UI is `ZoneCurseControl` in the top-bar settings group (`.zonecurse`), not a new
  tab: a `zone <radius> ×<multiplier>` readout, `+50%` / `−50%`, per-card undo
  showing the count, and `✕` to clear. Each press applies immediately.
- Changing the radius must move the circle, the outside shading,
  `endgameClippedRegion`, `MapFit` and the suspects focus together — they all read
  the one `hidingRadiusMi` prop, so keep it that way rather than passing a size.

## Per-question endgame flag (zone sub-division)
Any auto-eliminating question can be tagged as an **endgame question** — a
`QuestionRecord.endgame?: boolean` (in `src/types.ts`). What matters is *when* it
was asked, not its type: a pre-endgame question was answered from the station
centre (anti-cheese rule), an endgame question from the hider's real position.
- **Create form** (`QuestionForm.tsx`): an "Endgame question" checkbox, shown only
  for eliminating kinds, defaulting to `endgameActive` (whether `game.endgame` is
  set) and re-syncing via `useEffect` when that changes — overridable per question.
- **History tab** (`App.tsx`): a **Mark/Unmark endgame** button beside
  Disable/Delete (`toggleEndgame`), fully reversible. This handles the
  wrong-station case: untag the ones you marked at the wrong station, then only the
  ones you (re)mark carve up the real zone.
- **Semantics:** endgame questions **still eliminate map-wide** (unchanged
  `stationPasses`/`applyFilters`, so a wrong station guess doesn't lose
  eliminations). The flag only changes *shading*: while `endgameStation` is set,
  the normal map-wide overlays (radar/thermometer/`poiRegions`) are suppressed and
  each endgame-flagged question's eliminated area is **clipped to the hiding-zone
  disk** and shaded (`endgameClippedRegion` in `questionRegions.ts`), so the clear
  part of the zone is where the hider can still be. Exiting endgame restores every
  overlay — nothing is deleted, so an accidental exit is harmless.
- `endgameClippedRegion` reuses the exact same eliminated geometry as the map-wide
  shading (`eliminatedGeom`, which also builds radar/thermometer regions) and
  intersects it with the zone disk, so sub-zone shading always agrees with the
  elimination rule. Regression: `endgameShading.test.ts`.

### Tentacles in endgame (shading vs station elimination diverge)
Tentacles (`tentacle`, `tentacle-line`) are **logged-only for station elimination
in endgame**: the hider answers from their real position, not the station centre,
so `tentacleEliminatedRegion` / `metroLineEliminatedRegion` (and therefore
`poiEliminatedRegion`) return `null` when `record.endgame` — a wrong-station guess
must not wipe stations off the board. **But the zone shading is still valid** (the
hider must be within the radius and nearest the answer POI/line even from their
real position), so `eliminatedGeom` deliberately builds a `forNonEndgame` copy
(`{ ...record, endgame: false }`) for tentacles before calling
`poiEliminatedRegion`, so endgame tentacles **do** sub-divide the hiding zone
while the map-wide path stays `null`. Don't "simplify" this back to a single call
— it would either stop endgame tentacles from shading or make them eliminate
stations map-wide. Covered by the endgame-tentacle case in `endgameShading.test.ts`.

## Gotchas
- **Don't invert the shading.** A regression once shaded the *inside* of the zone;
  the rule is eliminated-area-shaded, hiding-zone-clear, matching every other
  question overlay.
- **Banner must clear the zoom controls.** It floats over the map top-left; keep
  it offset right of the `+/−` buttons or it covers them.
- Radius is in **miles**; convert to metres with `* 1609.344` for Leaflet, and
  always display via `formatDistance(mi, units)` so it respects the unit toggle.
- Endgame radius is the **size default × curse multiplier**, not the compass
  `radiusMi` — don't confuse the two.
- **Never `fitBounds` a single point.** Go through `fitTarget`/`zoneBoxMeters`; a
  degenerate box plus an uncapped max zoom blanks the map (see above).

## Verify
`npm run lint && npx tsc -b --noEmit && npm test`, then `npm run dev`: click a
station → **🎯 Endgame here**; confirm the map zooms to the zone, the area
outside the circle is shaded red, the zone interior is clear with a green
outline, the banner shows the right name + radius and does not cover the zoom
controls, the suspects list collapses to the one station, **Exit** restores the
full board, and the state survives a page reload. Also **reload while endgame is
active** — the map must frame the zone, not go white — and press `+50%` twice to
confirm the readout reads `×2.25`, the circle and shading grow with it, undo
steps back one cast, and the counts survive a reload. For deterministic checks drive
it via CDP (`verify-map-interactions`).
