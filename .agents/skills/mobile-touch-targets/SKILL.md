---
name: mobile-touch-targets
description: Make the seeker map's station and POI dots easy to tap on phones/tablets. Use when stations or POI points are hard to click on mobile/touch devices.
---

# Mobile touch targets (stations & POIs)

The seeker map renders stations (`CircleMarker`, SVG renderer) and POIs (`L.circleMarker` on a shared canvas, see `PoiLayer`) in `src/components/MapView.tsx`. For both, the **visual radius is also the Leaflet hit area** — there is no separate hit padding. The default radii (POI r4; station eliminated r5, base r6, starred r11) are only a few px wide, so they are very hard to tap on a touch screen.

## The fix

Enlarge the radii **only on a coarse pointer** (touch), so desktop stays byte-for-byte identical. At module scope in `MapView.tsx`:

```ts
const COARSE_POINTER =
  typeof window !== 'undefined' &&
  typeof window.matchMedia === 'function' &&
  window.matchMedia('(pointer: coarse)').matches
const STATION_R = { elim: COARSE_POINTER ? 8 : 5, base: COARSE_POINTER ? 10 : 6, star: COARSE_POINTER ? 14 : 11 }
const POI_R = COARSE_POINTER ? 7 : 4
```

Then use `POI_R` for the POI `circleMarker` radius, `STATION_R.elim` for the eliminated-station marker, and `star ? STATION_R.star : STATION_R.base` for the remaining-station marker.

## Notes

- Prefer enlarging the radius over adding a second invisible hit marker: it's simpler and keeps the carefully-tuned overlap/z-order (stations SVG pane z450 wins clicks over the POI canvas pane z410) intact.
- The app layout is **already** responsive: at `<=760px` the sidebar becomes a slide-up bottom sheet and the map goes full-screen (see the `@media (max-width: 760px)` block in `src/index.css`). Don't re-add a responsive layout — only the tap targets needed fixing.
- `(pointer: coarse)` is evaluated once at load; that's fine because device pointer type doesn't change mid-session.
- Verify with `npm run typecheck` and `npm run lint`.
