---
name: seeker-location-input
description: Set a seeker location for a question by clicking the map OR typing lat/lon coordinates, and set a custom radar radius. Use when asked to change how locations/coordinates or radar sizes are entered in the Ask form.
---

# Seeker location & radius input

Location-based questions (radar center, thermometer A/B, airport-measure
location) accept a point either from the **last map click** or from **typed
lat/lon coordinates**. The radar also supports a **custom radius** beyond the
fixed game presets. All of this lives in `src/components/QuestionForm.tsx`.

## CoordPicker (typed coordinates)
`CoordPicker({ label, point, setPoint, lastClick })` renders two rows:
1. the label, the current point (`fmt(point)`), and a **Use last click** button
   (disabled until the map has been clicked).
2. `latitude` / `longitude` number inputs + a **Set** button. `apply()`
   validates both are finite and in range (lat −90..90, lon −180..180) before
   calling `setPoint({ lat, lon })`.

Use it for every point a question needs:
```tsx
<CoordPicker label="Center"  point={center} setPoint={setCenter} lastClick={lastClick} />
<CoordPicker label="Start A" point={ptA}    setPoint={setPtA}    lastClick={lastClick} />
<CoordPicker label="End B"   point={ptB}    setPoint={setPtB}    lastClick={lastClick} />
```
Styling: `.coordpick`, `.coordin` in `src/index.css` (the inputs are indented
under the label and use a smaller font).

## Custom radar radius
The radar **Radius (mi)** `<select>` lists `RADAR_OPTIONS` plus a `Custom…`
option. When `radius === 'custom'`, an extra number input (`customRadius`) shows.
In `submit()`:
```ts
const radiusMiles = radius === 'custom'
  ? (metric ? Number(customRadius) / KM_PER_MILE : Number(customRadius))
  : Number(radius)
if (!Number.isFinite(radiusMiles) || radiusMiles <= 0) return alert(...)
```
The custom field is labelled in the current unit (see the `units-toggle` skill)
and converted to canonical miles before storing. Remember to reset
`customRadius` in the post-submit reset.

## Adding coordinate entry to a new question
1. Hold the point(s) in state (`useState<LatLng | null>`).
2. Render a `<CoordPicker>` per point instead of a bare "Use last click" row.
3. In `submit()`, validate the point(s) exist and put their `lat`/`lon` in
   `params` (canonical units).

## Verify
`npm run lint && npx tsc -b --noEmit && npm test`, then `npm run dev`: log a
radar by typing coordinates (no map click) and confirm the circle lands there;
try an out-of-range lat to confirm the alert; pick `Custom…` and confirm an
arbitrary radius is honored.
