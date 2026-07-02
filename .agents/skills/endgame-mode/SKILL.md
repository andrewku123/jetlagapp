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
  - `hidingRadiusMi = SIZE_PARAMS[game.gameSize].hidingZoneRadiusMi` — the zone
    radius comes from the **game size** params in `src/data/questionSets.ts`
    (size is auto-derived from station count), NOT a user input.
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
  `L.latLng(center).toBounds(hidingRadiusMi * 1609.344 * 2.6)` once per distinct
  endgame id (manual pan/zoom afterwards is left alone).

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

## Gotchas
- **Don't invert the shading.** A regression once shaded the *inside* of the zone;
  the rule is eliminated-area-shaded, hiding-zone-clear, matching every other
  question overlay.
- **Banner must clear the zoom controls.** It floats over the map top-left; keep
  it offset right of the `+/−` buttons or it covers them.
- Radius is in **miles**; convert to metres with `* 1609.344` for Leaflet, and
  always display via `formatDistance(mi, units)` so it respects the unit toggle.
- Endgame radius is per **game size** (`SIZE_PARAMS[...].hidingZoneRadiusMi`), not
  the compass `radiusMi` — don't confuse the two.

## Verify
`npm run lint && npx tsc -b --noEmit && npm test`, then `npm run dev`: click a
station → **🎯 Endgame here**; confirm the map zooms to the zone, the area
outside the circle is shaded red, the zone interior is clear with a green
outline, the banner shows the right name + radius and does not cover the zoom
controls, the suspects list collapses to the one station, **Exit** restores the
full board, and the state survives a page reload. For deterministic checks drive
it via CDP (`verify-map-interactions`).
