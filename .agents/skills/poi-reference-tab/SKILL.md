---
name: poi-reference-tab
description: Work on the POI tab — the reference layer for composing Tentacles/Matching/Measuring questions. Its category toggles, name search, top-5 search-suggestions dropdown (fly map to a POI), station Normal/Faded/Hidden override, and per-category counts. Use when asked to change the POI tab UI, its search, or how POI dots are shown.
---

# POI reference tab

The **POI** tab (`tab === 'poi'` in `src/App.tsx`) is a read-only reference layer:
it overlays every enabled POI category as colored dots on the map so you can
compose Tentacles / Matching / Measuring questions. POIs only draw while this tab
is open (`visiblePois = tab === 'poi' ? pois : []`).

## Data
- `POI_CATEGORIES` (key/label/color) and `POI_BY_CATEGORY` (key → `PoiPlace[]`)
  come from `src/lib/poi.ts`. A `RenderPoi` is a `PoiPlace` with `categoryKey`,
  `label`, `color` folded in for drawing.
- Eligibility rule shown in the hint: a place counts if it has the Google Maps
  category icon and >=5 reviews (that filter happens in the data build, not here).

## Category toggles + counts
- `poiEnabled: Set<string>` (category keys). `togglePoi(key)` flips one; "Show
  all" / "Hide all" set the whole set. Defaults to all categories enabled.
- `pois` (the drawn set) = every enabled category, name-filtered by `poiQuery`.
- `poiFilteredCounts` = per-category match count after the search filter, shown
  next to each toggle. `<n> shown` in `.poi-actions` is `pois.length`.

## Name search + suggestions dropdown
- `poiQuery` state drives a `type="search"` `<input>` (`.suspect-search`, reused
  from the Suspects tab) with a custom **✕ clear** button (`.search-clear`).
- `poiSuggestions` = top **5** POIs whose name `includes` the query, searched
  across **every** category (regardless of toggle) so anything is findable.
  Sort: names that **startWith** the query rank first, then alphabetical.
- Rendered as `.poi-suggest` list under the search box: colored category dot +
  name + category label. Clicking a suggestion:
  1. enables that category (`setPoiEnabled(s => new Set(s).add(categoryKey))`)
     so its dot is visible, and
  2. sets `poiFocus = { lat, lon, nonce: Date.now() }` to fly the map to it.
- The dropdown only shows when `poiSuggestions.length > 0`.

## Map focus (fly-to)
- `poiFocus` is passed to `MapView`; `MapFocusPoi` (in `src/components/MapView.tsx`)
  watches it and `map.flyTo([lat, lon], max(currentZoom, 14))` on each new
  `nonce`. This mirrors `MapFocus` (which re-centers on a Suspects-list station),
  but takes a bare lat/lon instead of a `Station` and uses a fixed min zoom
  rather than the endgame bounds fit.
- The nonce pattern (bump `Date.now()`) lets the same POI be re-focused on
  repeated clicks (a plain lat/lon prop wouldn't retrigger the effect).

## Station view override
- `stationView: 'normal' | 'faded' | 'hidden'` — a `.seg` toggle that dims/hides
  the station dots while the POI tab is open so POI dots stand out. It only
  applies on the POI tab and resets to `normal` on leaving the tab
  (`useEffect` on `tab`). Passed to `MapView` as
  `stationView={tab === 'poi' ? stationView : 'normal'}`.

## Where to change things
- All UI + state is in `src/App.tsx` (`tab === 'poi'` JSX, `poiQuery`,
  `poiFocus`, `poiEnabled`, `stationView`, `pois`, `poiSuggestions`,
  `poiFilteredCounts`).
- Map fly-to: `MapFocusPoi` + the `poiFocus` prop in `src/components/MapView.tsx`.
- Styles: `.poi-suggest*`, `.poi-actions`, `.poi-list`, `.poi-row`, `.poi-stations`
  and the shared `.searchbar` / `.suspect-search` / `.search-clear` in
  `src/index.css`.

## Verify
`npm run lint && npx tsc -b --noEmit && npm test`, then `npm run dev`: open the
POI tab, type a known place (e.g. "de young"), confirm the top-5 dropdown shows
name + category, click it and confirm the map flies to the POI and its category
dot appears. Toggle Show all / Hide all and the station Normal/Faded/Hidden seg.
