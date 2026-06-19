---
name: interlining
description: Work on how transit lines that share the same physical track are drawn as parallel offset ("interlined") tracks, and the toggle that turns it on/off. Use when asked to change interlining, the offset spacing, the toggle, or which systems interline.
---

# Interlining (parallel offset tracks)

Where several lines of a system run on the **same physical track** (BART's
downtown trunk, Muni's Market St subway, VTA's Tasman/First St segment), drawing
one line per route would hide all but the topmost color. Interlining instead
draws each color as a **parallel offset track** so every line is visible, the
way Google/Apple Maps render shared corridors.

It is **toggleable** from the top-bar **"interline"** checkbox; off = a single
line per physical track (only the first color shows).

## Data shape (`src/data/transit-lines.geojson.json`)
One `LineString` feature **per physical OSM way**, with
`properties = { system, colors }` (`colors` = every line color on that way).
Produced by `scripts/fetch_transit_lines.py` (see the **transit-basemap-overlay**
skill). **Caltrain is bucketed separately** in the script so its ways never merge
with another system and it always stays one line (`colors.length === 1`).

**Direction tracks are merged**: OSM models each route's two directions as
separate tracks ~13m apart, which would draw every line twice. `merge_colocated()`
collapses co-located tracks (NB/SB pairs, stacked BART/Muni tunnels, and short
sub-ways lying on a longer one) into a single representative centerline and unions
the colors on it — using a corridor-cover test with tolerance `MERGE_TOL_M` (~35m).
So one route = one line, and shared corridors carry all their colors for the
offsetting step below.

> The script does NOT pre-compute offsets — it only records the color list per
> way. Offsets are computed in the app so the toggle is instant (no refetch).

## Rendering (`src/components/MapView.tsx`)
- `interline: boolean` prop (from `App.tsx`, top-bar checkbox state).
- `buildTransit(interline)` builds the rendered `FeatureCollection`:
  - `interline && colors.length > 1` → emit one feature per color, each shifted
    by `offsetLine(base, off)` where `off = (i - (k-1)/2) * SPACING_M`, so the
    `k` colors are centered/symmetric around the true track.
  - otherwise → emit a single feature using `colors[0]`.
- `offsetLine(coords, meters)` shifts a `[lon,lat]` polyline perpendicular (left
  normal of travel) by `meters`, using a local metres-per-degree approximation
  per vertex (`111320·cos(lat)` per °lon, `110540` per °lat).
- `SPACING_M = 16` (metres between adjacent parallel tracks).
- `const transit = useMemo(() => buildTransit(interline), [interline])`, drawn via
  `<GeoJSON key={interline ? 'il' : 'flat'} data={transit} … />`. The `key`
  forces react-leaflet to rebuild the layer when the toggle flips.

## Notes / gotchas
- Interlining only groups colors on the **same OSM way**. Two systems in
  separate-but-adjacent tunnels (e.g. BART vs Muni under Market St) each fan out
  independently; both render but as two nearby bundles, not one merged fan.
- Big offsets make exclusive (single-color) segments look shifted off-street, so
  keep `SPACING_M` small (~16 m) and only offset when `colors.length > 1`.

## Common changes
- **Wider/narrower spacing**: change `SPACING_M`.
- **Make a system never interline** (like Caltrain): bucket it separately in the
  script so each way carries only one color.
- **Default toggle state**: `useState(true)` for `interline` in `App.tsx`.

## Verify
`npm run lint && npx tsc -b --noEmit && npm test`, then `npm run dev`: toggle the
"interline" checkbox and confirm the BART downtown trunk / Muni Market St subway
switch between a single line (off) and parallel colored tracks (on); Caltrain
stays a single line either way.
