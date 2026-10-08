---
name: verify-zone-aware-elimination
description: E2E-verify the Jet Lag seeker app's hiding-zone-aware station elimination (zoneMi stamping, curse multipliers, old-board fallback, USGS sea-level fill) against an independent geometry oracle. Use when changing elimination.ts / zoneFit / zoneElevation / hidingZone or the sea-level Ask form.
---

# Verifying zone-aware elimination

## Setup
- `npm run build && (cd dist && python3 -m http.server 4173 --bind 127.0.0.1)`; the production build may show a soft password gate (password comes from the lead/PR, e.g. `jetlag`).
- Drive Chrome over CDP (`http://localhost:29229`). Clear the board via the header **Reset** → native confirm **OK** (header should show `262 of 262` for Bay Area weekday).
- Board state: `localStorage['bahs.game.v1.<regionId>']` → `.questions[]` each with `zoneMi`, plus `.zoneCurses`.

## Discriminating oracle (key idea)
Write an independent Python/Shapely oracle (do NOT import app code): a station survives iff its center passes OR `distance(station, playArea ∩ keptSide) <= zoneMi`. Compute counts for zone 0 (old center-only behavior), the default zone (0.25 mi medium / 0.5 large), and the curse-adjusted zone. Choose a test whose counts differ at each zone, so every count observed in the UI tells you which behavior is running.
- Example (Bay Area, weekday, medium): radar centered on 37.7599,-122.4148 with a 1 mi radius gives YES 10/17/20 and NO 252/256/260 at zone 0/0.25/0.375.
- Sea level: use `src/data/zone-elev.json` (`bandsMi`, per-station `[min,max]`, +3 m margin). For closer, a station survives if `min-3 < v`; for further, if `max+3 > v`. Compare against center-only counts that use `station.elevation`.

## Checks
1. When a question is logged, its record gets `zoneMi` set to the current header zone (curse-adjusted). The UI rounds 0.375 to `0.38 mi`; that rounding is expected.
2. Adding a curse later must NOT change counts from records logged before it. Use History Disable/Enable to show the wider band from the newer record on its own.
3. Old board fallback: inject records without `zoneMi` plus `zoneCurses:{prosperous:1,tiny:0}`, then reload. The count must match the default zone, not the curse-adjusted one.
4. Sea level: type coordinates into "Your location" and press Set; the altitude should be filled from USGS EPQS (meters, converted to ft). Toggle km/m to check the conversion. Typing an altitude by hand without a location must still submit (the record then has no fromLat/fromLon).
5. Rail-station Measuring in endgame should draw an indigo outline but never eliminate stations map-wide (after Exit, the count returns to its earlier value).

## Gotchas
- The Ask form re-lays itself out after each Set (distance lines and city names appear), so the Log button moves down. Zoom or re-screenshot before clicking. A missed click can silently tick the "Endgame question" checkbox.
- Native `<select>` options: click the select, type the option's prefix ("City", "Museum", "Rail"), then press Enter.
- Map overlays are drawn on canvas. Check them by sampling pixels, not by counting SVG paths.
- For console errors, attach over CDP (`Runtime.enable`, `Log.enable`, then `Page.reload`) and listen ~15 s. The `browser_console` tool only shows output from after it attached. The software-WebGL fallback warning and MapLibre worker "Expected value to be of type number, but found null" warnings are ambient environment/basemap noise.
- USGS EPQS (`epqs.nationalmap.gov`) sends CORS `*`; check it is reachable before testing the sea-level fill.

## Devin Secrets Needed
None (the soft password is supplied in the task/PR).
