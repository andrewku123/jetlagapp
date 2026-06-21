---
name: verify-map-interactions
description: Deterministically verify Leaflet map interactions (drawing-tool snap, handle dragging, popups, label positions, coordinate copy) by driving the running Chrome over CDP and reading localStorage. Use when a change to MapView/drawing tools needs to be proven working beyond unit tests, or when a UI bug only reproduces through real clicks.
---

# Verify map interactions (CDP harness)

Unit tests cover the geometry helpers, but the map's *interaction* behaviour
(snap-to-point, drag vs click, popups opening, tooltip/label positions, the 📍
coordinate-copy) only exists in the rendered Leaflet DOM. The reliable way to
prove these work — and to debug "sometimes it does X" reports — is to drive the
**already-running** Chrome over the Chrome DevTools Protocol, fire real
mouse/drag events, and then read the persisted state back out of `localStorage`.
This is far more trustworthy than eyeballing a screenshot.

## Prerequisites
- Dev server running: `cd <repo> && npm run dev` → `http://localhost:5173`.
- Chrome is already running with a CDP endpoint at **`http://localhost:29229`**.
- App persistence key: the game (including `annotations`) is saved to
  `localStorage` under **`bahs.game.v1`** (see `src/lib/storage.ts`). Annotations
  carry exact coords, so you can assert on them numerically.

## Pattern
Write a small Node ESM script (`node script.mjs`, Node 20+ has global `WebSocket`
and `fetch`). Skeleton:

```js
const base = 'http://localhost:29229'
const page = (await (await fetch(`${base}/json`)).json()).find((t) => t.type === 'page')
const ws = new WebSocket(page.webSocketDebuggerUrl)
await new Promise((r) => (ws.onopen = r))
let id = 0; const pending = new Map()
ws.onmessage = (m) => { const j = JSON.parse(m.data); if (j.id && pending.has(j.id)) { pending.get(j.id)(j.result); pending.delete(j.id) } }
const send = (method, params = {}) => new Promise((res) => { const i = ++id; pending.set(i, res); ws.send(JSON.stringify({ id: i, method, params })) })
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const ev = async (e) => (await send('Runtime.evaluate', { expression: e, returnByValue: true, awaitPromise: true })).result?.value

async function click(x, y) {
  await send('Input.dispatchMouseEvent', { type: 'mouseMoved', x, y })
  await send('Input.dispatchMouseEvent', { type: 'mousePressed', x, y, button: 'left', clickCount: 1 })
  await send('Input.dispatchMouseEvent', { type: 'mouseReleased', x, y, button: 'left', clickCount: 1 })
  await sleep(400)
}
async function drag(x1, y1, x2, y2) { // move in steps so Leaflet treats it as a drag, not a click
  await send('Input.dispatchMouseEvent', { type: 'mouseMoved', x: x1, y: y1 })
  await send('Input.dispatchMouseEvent', { type: 'mousePressed', x: x1, y: y1, button: 'left', clickCount: 1 })
  for (let i = 1; i <= 6; i++) { await send('Input.dispatchMouseEvent', { type: 'mouseMoved', x: x1 + (x2 - x1) * i / 6, y: y1 + (y2 - y1) * i / 6, button: 'left' }); await sleep(30) }
  await send('Input.dispatchMouseEvent', { type: 'mouseReleased', x: x2, y: y2, button: 'left', clickCount: 1 })
  await sleep(400)
}

// helpers that compute screen coords from the live DOM (never hard-code pixels):
const anns = async () => JSON.parse((await ev(`localStorage.getItem('bahs.game.v1')`)) || '{}').annotations || []
const btnXY = async (label) => await ev(`(()=>{const b=[...document.querySelectorAll('button')].find(x=>(x.getAttribute('aria-label')||'')===${JSON.stringify(label)});const r=b.getBoundingClientRect();return [r.x+r.width/2,r.y+r.height/2]})()`)
const mapXY = async (fx, fy) => await ev(`(()=>{const m=document.querySelector('.leaflet-container');const r=m.getBoundingClientRect();return [r.x+r.width*${fx},r.y+r.height*${fy}]})()`)

await send('Page.enable'); await send('Runtime.enable')
await send('Page.navigate', { url: 'http://localhost:5173/index.html' }); await sleep(3500)
await ev(`localStorage.removeItem('bahs.game.v1')`)              // start clean
await send('Page.reload'); await sleep(3500)
// ... select tools by aria-label, click/drag at map fractions, then assert on anns()
```

## Key techniques
- **Pick toolbar tools by `aria-label`** (`select|compass|line|bisector|measure|coord`)
  via `btnXY`, then `click()`. Don't hard-code button pixels.
- **Express map clicks as fractions** of `.leaflet-container` (`mapXY(0.5,0.4)`),
  so the test is resolution-independent.
- **Drag vs click**: a `drag()` must move the pointer in several steps with the
  button held — Leaflet emits `dragend` (not `click`) only past its move
  tolerance. A press/release at one spot is a click (used for snap/reuse).
- **Assert numerically on `localStorage`**: e.g. after snapping a measure onto a
  line endpoint, `measure.aLat === line.aLat && measure.aLon === line.aLon`
  (exact equality — snap copies the stored coord, it doesn't re-read the pixel).
- **Drag handles' own `click` fires under CDP**, but Leaflet's *implicit*
  bound-popup-on-click is flaky under synthetic events — if you need a popup to
  open, the handler calls `marker.openPopup()` explicitly (see `map-drawing-tools`),
  which IS observable via CDP (`document.querySelector('.leaflet-popup')`).
- **Reading a label's position**: compare the screen distance from a label's DOM
  rect to the handle's rect at two radii to prove a label scales/repositions.

## Examples in repo history
Throwaway scripts like `cdp_verify.mjs` / `cdp_compass.mjs` / `cdp_snaptest.mjs`
(written to `/home/ubuntu`, not committed) verified: snap reuses exact coords;
dragging works while a drawing tool is active; clicking a compass center with the
compass active opens the edit bar and does NOT add a concentric ring; no
line/bisector popup; coordinate copy lands the right lat/lon. Keep these as
disposable scratch scripts — they are test harness, not app code.

## Verify
The harness itself needs no build step. After using it, still run
`npm run lint && npx tsc -b --noEmit && npm test && npm run build` on any code you
changed.
