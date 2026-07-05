---
name: mobile-touch-targets
description: Make the seeker map's station and POI dots reliably clickable, especially on phones/tablets. Use when tapping a station/POI does nothing or places a map point instead of opening its popup.
---

# Clickable stations & POIs (esp. mobile)

Stations (`CircleMarker`, SVG renderer) and POIs (`L.circleMarker` on a shared canvas, see `PoiLayer`) are drawn in `src/components/MapView.tsx`. In select mode a plain map click places a location point via `MapClicks` -> `onPickLocation`.

## The real gotcha: click bubbling places a point

A Leaflet marker click **bubbles to the map** by default (`bubblingMouseEvents: true`). So in select mode, tapping a marker fired BOTH the marker's popup AND the map's `click` handler — the map handler then placed a location point. This was most visible on touch (no hover, fatter finger), and made stations feel "unclickable / it just drops a point."

The POI canvas markers already set `bubblingMouseEvents: false`, which is exactly why POI dots worked while stations didn't. **The fix is to set the same on the station `CircleMarker`s:**

```tsx
<CircleMarker
  center={[st.lat, st.lon]}
  radius={star ? 11 : 6}        // eliminated stations use radius 5
  interactive={selectMode}
  bubblingMouseEvents={false}   // <-- stops the tap from also placing a map point
  renderer={stationRenderer}
  ...
>
```

Apply it to every interactive station marker (both the eliminated and the remaining/starred markers).

## The precision part: invisible larger tap target on touch

`bubblingMouseEvents={false}` stops the stray map point, but a 5–6px station dot is still a tiny finger target. Do **not** enlarge the visible dot (it looks bad and POI dots prove small dots are fine). Instead, on a coarse pointer only, render the visible dot as `interactive={false}` and lay a larger fully-transparent `CircleMarker` over it that carries the popup — its `radius` is also its Leaflet hit area, so the tap area grows without any visual change. This is the same trick the POI audit map uses.

```tsx
const COARSE_POINTER =
  typeof window !== 'undefined' &&
  typeof window.matchMedia === 'function' &&
  window.matchMedia('(pointer: coarse)').matches
const HIT_OPTS = { stroke: false, fill: true, fillColor: '#000', fillOpacity: 0 }

// per station:
if (!COARSE_POINTER) return dot(selectMode)   // desktop: the visible dot is the target
return (
  <Fragment>
    {dot(false)}                               // visible dot, non-interactive
    <CircleMarker center={[st.lat, st.lon]} radius={15}
      interactive={selectMode} bubblingMouseEvents={false}
      renderer={stationRenderer} pathOptions={HIT_OPTS}>
      {popup(st)}                              {/* popup lives on the hit target */}
    </CircleMarker>
  </Fragment>
)
```

Keep the popup content in a shared helper so the visible dot (desktop) and the invisible target (touch) render the same popup without duplication, and make sure the popup is bound to exactly one marker per station (the interactive one) so it doesn't open twice.

## What did NOT help

Enlarging the **visible** dot radii on a coarse pointer was tried and reverted: it made the dots look too big and did **not** fix clicking, because the main problem was bubbling, and precision is solved by an invisible hit target instead. Keep the original visible radii (POI 4; station 5 / 6 / 11).

## Hiding a pane must use `display:none`, not `pointer-events:none`

The POI tab's **Stations: Hidden** toggle (`StationView` in `MapView.tsx`) has to make station dots both invisible **and** un-clickable. Setting `pane.style.pointerEvents = 'none'` on the `stations` pane does NOT work: Leaflet's SVG paths carry `pointer-events: auto` via `.leaflet-interactive` (`.leaflet-pane > svg path.leaflet-interactive { pointer-events: auto }`), and a child's `pointer-events` overrides the parent's, so the hidden stations stayed clickable.

Use `pane.style.display = 'none'` instead — it removes the whole subtree from both rendering and hit-testing, and cannot be overridden by children:

```ts
pane.style.opacity = mode === 'faded' ? '0.4' : '1'   // faded stays clickable context
pane.style.display = mode === 'hidden' ? 'none' : ''  // hidden = gone + non-interactive
```

Same principle for the coord-dot pane, but the opposite direction: a purely-visual pane above the station pane must be `pointer-events:none` so its (canvas) renderer doesn't blanket every click. Rule of thumb: to make an interactive vector pane non-clickable, hide it with `display:none`; `pointer-events:none` only reliably neutralizes a pane whose contents are non-interactive.

## Making an answer/seeker dot win the click over a station under it

Each logged question drops a tappable **answer pin** (radar centre, "your nearest airport" dot, POI answer, "asked from here"). When that pin lands exactly on a station — the classic case is the *nearest-airport* dot sitting on the **OAK Airport** station — the station dot swallowed the click, so on desktop *and* mobile you couldn't open the question popup.

Fix: give the answer pins their **own pane above the stations pane** (`answerPin`, z-index 500 > stations 450 < markerPane 600) so the pin wins the overlap; everywhere else the pane is click-through so stations stay clickable.

The non-obvious trap: the map is `<MapContainer ... preferCanvas>`, so a `CircleMarker` with only `pane="answerPin"` (no explicit renderer) falls back to a **canvas** renderer — one opaque `<canvas>` that blankets the *whole* pane and then swallows every click over the map (breaks all station clicks). You MUST give the pin an **SVG** renderer in that pane, exactly like `StationRenderer`:

```tsx
function AnswerPinRenderer({ onChange }: { onChange: (r: L.SVG | null) => void }) {
  const map = useMap()
  useEffect(() => {
    const name = 'answerPin'
    let pane = map.getPane(name) ?? map.createPane(name)
    pane.style.zIndex = '500'                    // above stations (450)
    const renderer = L.svg({ padding: 0.5, pane: name }).addTo(map)
    onChange(renderer)
    return () => { renderer.remove(); onChange(null) }
  }, [map, onChange])
  return null
}
const [answerPinRenderer, setAnswerPinRenderer] = useState<L.SVG | null>(null)
```

And — critically — **gate the pin markers on the renderer** so they mount into the SVG pane. react-leaflet fixes a `CircleMarker`'s renderer at creation time and never re-assigns it, so a pin rendered while `answerPinRenderer` is still `null` is stuck on the default canvas forever. Mount only once it exists (same pattern the station markers use):

```tsx
{pin && answerPinRenderer && (
  <CircleMarker center={[pin.lat, pin.lon]} radius={6}
    renderer={answerPinRenderer} bubblingMouseEvents={false} ... />
)}
```

Where to place the pin: drop a seeker-asked question's dot at its **ask location** (`params.fromLat/fromLon`), not at the answer airport/POI/coastline point. Putting it on the answer POI both hides it under that POI's own dot and makes two questions about the same POI (e.g. a matching-zoo + a measuring-zoo) pile their dots on one spot; the answer detail still shows in the tap popup. The exception is **Tentacles**, which is the hider's reveal (no seeker ask-location) — its dot belongs on the hider's answer POI (`poiRegions` builder in `MapView.tsx`).

Do NOT stack a second dot on that ask location. `App.tsx`'s `pickedPoints` also renders seeker markers (a `seeker-pin` **divIcon** `Marker`, which lives in the default **markerPane, z 600 — ABOVE the answerPin SVG pane, z 500**). If a question kind gets its dot from `poiRegions` (airport/POI/county/city/zip/…), it must NOT also be added to `pickedPoints`, or the higher markerPane marker sits exactly on top and **swallows the tap**, showing only its plain `{label}` popup instead of the rich `.answer-popup`. Symptom: the pin looks right but tapping shows a bare one-line popup. `pickedPoints` should only carry things `poiRegions` does *not* pin (e.g. thermometer A/B endpoints, the transient "Last click"). Detect it over CDP with `document.elementsFromPoint(x,y)` at the pin centre: a `DIV.seeker-pin-dot` on top means a duplicate marker is stealing the click.

Verify deterministically over CDP: with a `match-airport` question (`params:{fromLat,fromLon,value:'OAK',answer:'yes'}`) in `localStorage['bahs.game.v1']`, `document.elementFromPoint` at the pin centre must resolve into `.leaflet-answerPin-pane` (pin wins), while a station elsewhere still resolves into `.leaflet-stations-pane` (no blanket). See the `verify-map-interactions` skill for the CDP harness.

## Notes

- The app layout is already responsive: at `<=760px` the sidebar becomes a slide-up bottom sheet and the map goes full-screen (`@media (max-width: 760px)` in `src/index.css`). No layout change needed.
- Z-order is intentional: stations SVG pane z450 sits above the POI canvas pane z410 so a station wins the click where they overlap; a POI takes it elsewhere.
- Verify with `npm run typecheck` and `npm run lint`.
