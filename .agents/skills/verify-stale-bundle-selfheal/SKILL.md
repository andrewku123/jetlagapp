---
name: verify-stale-bundle-selfheal
description: End-to-end verify the stale-bundle self-heal (version.json / BUILD_ID / watchForNewBuild) in a real browser — prove the page does NOT reload when build ids match, reloads exactly once when they differ, preserves the saved board, and stays inert when the version fetch 404s, returns HTML, or is blocked. Use when touching src/lib/version.ts, vite.config.ts's emit-version-json plugin, main.tsx bootstrap, or any cache-busting / service-worker behavior.
---

# Verifying the stale-bundle self-heal

The feature: `vite.config.ts` stamps `__BUILD_ID__` from `git rev-parse --short HEAD` and emits
`dist/version.json` = `{"build":"<sha>"}`. `src/lib/version.ts#watchForNewBuild()` (called at module
scope in `main.tsx`) fetches `version.json` on load and on every `visibilitychange`→visible; on a
mismatch it clears Cache Storage and calls `location.reload()`, guarded once per remote id by
`sessionStorage['bahs.reloadedFor']`.

## You MUST test the production build, not the dev server

`version.json` is emitted by a **rollup `generateBundle` hook**, so it only exists in `dist/`.

```bash
npm run build                       # re-run at current HEAD — dist/version.json goes stale otherwise
cd dist && python3 -m http.server 4173 --bind 127.0.0.1   # `base` defaults to '/', plain static server is correct
```

Always `cat dist/version.json` and compare to `git rev-parse --short HEAD` before trusting any
result — a stale `dist/` silently turns every test into the *mismatch* case.

## The core problem: a silent reload is invisible in a screenshot

A mid-game reload looks identical to no reload (state is restored from localStorage). Instrument the
document before testing, via CDP `Page.addScriptToEvaluateOnNewDocument`:

```js
sessionStorage.setItem('__loads', String(Number(sessionStorage.getItem('__loads') || 0) + 1))
```

`sessionStorage` survives reloads but not new tabs, so `__loads` is an exact **document-load counter**.
Additionally stamp `window.__t = Date.now()` after load: `__t` surviving proves the document was never
replaced; `__t === undefined` proves a real navigation happened. Read both back at each assertion.
A CDP `Page.frameNavigated` listener appending to a log file is a good independent cross-check.

## Driving real visibility changes

Use **real Chrome tab switches** (click another tab, wait ~1.5–3 s, click back) rather than
dispatching a synthetic `visibilitychange` — synthetic events don't change `document.visibilityState`,
so they can produce false passes/failures.

## The four failure modes, and how to actually produce them

| Case | How to produce | Expected |
|---|---|---|
| Match | `dist/version.json` = real sha | no reload, ever |
| Mismatch | `echo -n '{"build":"deadbee1"}' > dist/version.json` | exactly **one** reload; `bahs.reloadedFor` = `deadbee1`; further cycles inert |
| 404 | `mv dist/version.json dist/version.json.bak` | no reload (`!res.ok` → null) |
| Non-JSON | write `<!doctype html>…` into `dist/version.json` | no reload (`res.json()` throws → null) |
| Blocked/offline | CDP `Network.setBlockedURLs(['*version.json*'])` | no reload (fetch throws → null) |

Two gotchas:

- **`Network.setBlockedURLs` is reset when the CDP connection detaches.** The blocking script must
  keep its WebSocket open (e.g. `setInterval(()=>{}, 1<<30)`) for the duration of the test, then
  explicitly clear with `setBlockedURLs({urls: []})`.
- **The Vite dev server is NOT a 404 case.** `npm run dev` serves `index.html` with **HTTP 200 and
  `Content-Type: text/html`** for `/version.json` (SPA fallback), so it exercises the *non-JSON*
  branch. Test 404 separately on the production server.

After a mismatch test, **clear the stale guard** (`sessionStorage.removeItem('bahs.reloadedFor')`)
before the next failure-mode test, or the guard alone suppresses the reload and you get a false pass.

## Always assert the board survived

The reload must not wipe game state. The board key is **`bahs.game.v1.<ACTIVE_REGION_ID>`**
(`bayarea | sfmuni | la | dc`) — note the existing `verify-map-interactions` skill documents the older
unsuffixed `bahs.game.v1`. Check the header count (`131 of 263`) and the `History (n)` tab label
before and after each reload.

## Endgame region outlines are drawn on CANVAS, not SVG

The map uses Leaflet canvas renderers (`preferCanvas`, explicit `L.canvas(...)`). Counting SVG
`<path>` elements to verify an outline returns **0 even when the outline is visibly drawn**. Instead
sample pixels off the Leaflet canvas with `getImageData` and count matching colors:

- question/elimination boundary outline `#3730a3` (indigo, `fill:false`)
- endgame hiding-zone circle `#16a34a` (green)
- elimination shading `#cf222e` (red)

Good adversarial control for an outline fix: toggle **Unmark endgame** / **Mark endgame** in History
and assert the indigo pixel count goes to 0 and back.

## Devin secrets needed

None — the app is unauthenticated and fully local.
