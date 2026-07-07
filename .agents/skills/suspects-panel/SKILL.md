---
name: suspects-panel
description: Work on the Suspects tab — the live list of still-possible vs eliminated stations, its search box, the name / agency→line (interlined) sort, per-line bulk eliminate/restore, and the shareable board code. Use when asked to change the suspects list, its search fields, sorting, grouping, the star/eliminate actions, or import/export of eliminations.
---

# Suspects panel

The **Suspects** tab (`tab === 'suspects'` in `src/App.tsx`) lists every eligible
station split into still-possible (`remaining`) and `eliminated`, with per-row
**★ star** (pins to top) and **✕ eliminate / ↩ restore** actions. The header
shows `<remaining>.length of <base>.length still possible`.

## Search (`suspectQuery` state)
- A `type="search"` `<input>` (`.suspect-search`) with a custom **✕ clear**
  button (`.search-clear`). The browser's native search clear-X is hidden in CSS
  (`::-webkit-search-cancel-button { display:none }`) so only one ✕ shows.
- Matching is case-insensitive `includes` over a **fixed field set per station**,
  not the whole JSON record:
  `[name, ...aka, ...systems, ...lines (termini stripped), city, county]`.
- **Line termini are stripped** before matching: line labels embed their
  endpoints, e.g. `BART Blue (Dublin/Pleasanton–Daly City)`, which made
  searching "dublin" match every Blue-line station. The fix is
  `l.replace(/\s*\([^)]*\)/g, '')` so "bart blue" still matches but the
  parenthetical termini don't leak in. Keep this; it also fixes "sfo"
  (lines contained "Millbrae/SFO").
- Deliberately **excluded** from search: coords, elevation, headways, airport
  distances, `nameLength`, ids. Only add a field here if asked — broad fields
  (like county) pull in large result sets.
- Empty query → everything; no-match query → a "No stations match …" hint.

## Sort (`suspectSort`: `'name' | 'agency'`)
- **by name**: flat alphabetical, but starred stations float to the top of
  `remaining` (`Number(starred.has(b))-Number(starred.has(a)) || name.localeCompare`).
  Eliminated are listed below, alphabetical.
- **by agency → line**: `groupByAgencyLine()` groups stations under agency
  headers then line sub-headers. Key behaviors:
  - Agencies ordered by `SYSTEM_ORDER` (`src/lib/style.ts`:
    `BART, Caltrain, VTA, Muni, SFO AirTrain`); unknown agencies sort last.
  - **Interlining**: a station serving multiple lines is listed under **every**
    line it serves (appears in several groups). The agency's count is the number
    of **unique** stations, so it can be less than the sum of its line counts.
  - A station's agency = first matching `SYSTEM_ORDER` prefix of each line
    (`agencyOfLine`); stations with no lines fall under `primarySystem(s)` in a
    `'—'` line bucket.
  - Eliminated render in their own grouped section under an "Eliminated (n)"
    header.

## Per-line bulk eliminate / restore (agency→line sort only)
- Each line sub-header carries a bulk button, controlled by `groupedLis`' third
  arg `lineAction: 'eliminate' | 'restore'` (remaining groups pass `'eliminate'`,
  eliminated groups pass `'restore'`).
  - **✕ all** → `eliminateMany(ids)` adds every station on the line to
    `manualEliminated`. Because of interlining a station is eliminated even if it
    also serves a line you keep — that's the intent of "rule out this line".
  - **↩ all** → `restoreMany(restorable)` removes only stations that are in
    `manualSet` (hand-eliminated); question-eliminated stations stay out, so the
    button is hidden when a line has none restorable.
- Styles: `.sgroup.line` is now a flex row; `.line-name` + `.line-bulk`
  (`.restore` variant) in `src/index.css`.

## Shareable board code (`src/lib/shareCode.ts`)
- A `<details className="share-board">` at the bottom of the panel: **Copy board
  code** (encodes the current `eliminated` list to the clipboard + textarea) and
  **Load code** (decodes the textarea, merging ids into `manualEliminated`).
  State: `shareCode`, `shareMsg`.
- Encoding = a bitmask over **all** station ids sorted ascending, one bit each,
  base64url-packed, prefixed `E1.<count-base36>.`. The embedded count makes
  `decodeElimination` reject a code from a different station dataset instead of
  mis-applying it. Round-trip/edge cases are covered by `shareCode.test.ts`.
- Load is a **merge** (union into hand-eliminations), so tell users to Reset for
  an exact copy. Keep the bit order = `stations.map(id).sort()` on both ends.

## Where to change things
- All of it is in `src/App.tsx`: `groupByAgencyLine` (module scope),
  `suspectSort` / `suspectQuery` / `shareCode` state, the `matches()` predicate,
  `toggleManual` / `eliminateMany` / `restoreMany`, and the `tab === 'suspects'`
  JSX. Row renderers are `remainingLi` / `eliminatedLi`; group rendering is
  `groupedLis`. Share encode/decode live in `src/lib/shareCode.ts`.
- Styles: `.searchbar`, `.suspect-search`, `.search-clear`, `.sortbar`, `.slist`,
  `.sgroup`, `.elimhdr`, `.line-bulk`, `.share-board` in `src/index.css`.

## Verify
`npm run lint && npx tsc -b --noEmit && npm test`, then `npm run dev`: search
"taraval" (≈13 Muni stops), "dublin" (only the two Dublin/Pleasanton BART stops —
NOT all Blue-line), "sfo" (AirTrain + SF Airport BART only); toggle both sort
modes and confirm interlined stations appear under each of their lines while the
agency count stays unique; star a station and confirm it floats to the top in
name sort; eliminate/restore a station.
