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

## Notes

- The app layout is already responsive: at `<=760px` the sidebar becomes a slide-up bottom sheet and the map goes full-screen (`@media (max-width: 760px)` in `src/index.css`). No layout change needed.
- Z-order is intentional: stations SVG pane z450 sits above the POI canvas pane z410 so a station wins the click where they overlap; a POI takes it elsewhere.
- Verify with `npm run typecheck` and `npm run lint`.
