---
name: crash-recovery
description: Diagnose and recover from the app rendering a blank/black page on a device (usually a saved board that makes React throw). Use when a player reports a black screen, when incognito works but the normal tab doesn't, or when changing the crash screen / saved-board format.
---

# Black screen = a crash, not a broken deploy

Symptom triage, in order — it tells you where to look without a console (Chrome iOS has none):

| What the player sees | Cause |
| --- | --- |
| Black edge-to-edge, only the URL bar | `index.css` loaded, JS threw before painting → a render crash, almost always the saved board |
| White page | `index.html` is cached but its hashed assets 404 → stale bundle, hard-refresh fixes it |
| Header/tabs but no map | map layer failure (WebGL / tile provider), not state |
| Works in incognito or another browser, not the normal tab | per-profile stored state, i.e. `localStorage`, not the code |

Board state lives in `localStorage` under `bahs.game.v1.${ACTIVE_REGION_ID}` (`src/lib/storage.ts`),
one key per map. `loadGame()` is `try`/`catch`-guarded, so *parsing* never crashes — what crashes is
**rendering** a board that parsed fine but no longer matches the code (a question kind that was
renamed, a station id that no longer exists, an annotation shape that changed). That is why a
migration guard inside `loadGame()` is not enough on its own.

## The recovery screen

`CrashBoundary` in `src/components/CrashScreen.tsx` wraps `<App/>` in `src/main.tsx`. On a caught
render error it shows the error + first 8 stack frames, a **Copy saved board** button, the raw save
in a `readonly` textarea (clipboard is often blocked on mobile — the textarea is the fallback, never
drop it), **Clear saved board and reload** (`clearSave()` + `location.reload()`), and plain Reload.

Rules when touching it:

- Keep it dependency-free and outside the map/React-Leaflet tree — it has to render when everything
  else is broken.
- Show the save *before* offering to wipe it. Clearing is destructive and the player may be mid-game;
  the board code can only be re-imported if they copied it out.
- It only catches **render** errors. Errors from Leaflet/async callbacks after mount, or a module
  that throws at import time, still blank the page — for those, hard-refresh/clear site data.

## Verifying it

Temporarily `throw` at the top of `App()` behind `location.search.includes('crashtest')`, drive the
dev server over CDP (see `verify-map-interactions`), screenshot at phone and desktop widths, click
**Clear saved board and reload** and assert `localStorage.getItem(key) === null`, then remove the
trigger. Do not ship the trigger.

## What to tell the player

Clearing site data for `andrewku123.github.io` in that browser fixes it immediately, but wipes that
device's board — copy the board code off a working device first (Suspects tab). Incognito is the
zero-risk workaround, and a board code pasted into it restores the game.
