---
name: continuous-transit-lines
description: Build clean, continuous transit lines from fragmented OSM route data (no gaps, no stray yard/crossover bits, no NB/SB doubling). Use when transit lines render broken/gappy, have extra stray segments, or when adding transit for a new city.
---

# Continuous transit lines

Raw OSM route relations are made of many small "way" segments, plus duplicate
direction tracks (NB/SB ~13 m apart), passing tracks, crossovers and yard leads.
Rendering one feature per OSM way looks **broken** (gaps between fragments) and
**noisy** (stray bits). This skill is the algorithm in
`scripts/fetch_transit_lines.py` that turns that into one continuous, correctly
colored `LineString` per line. It is city-agnostic — reuse it for new metros (see
`add-transit-city`).

## Classification: which relations to keep (`matches()`)
Classify a relation by **operator/network + `route` + `ref`** — never by the
route *name* (a line's name can mention another system's terminus, e.g. Muni N's
name ends "=> Caltrain", which misclassifies it). Gotchas baked in:
- **Allowlist the lines you actually draw.** Muni uses `MUNI_LINES = {F,J,K,L,M,N,T}`
  and keeps a relation only if its `ref` is in that set. This drops overlay-only
  shuttles that share an alignment — the **S-Shuttle** (`#ffcc00`) runs the
  Embarcadero on top of the N/F and otherwise renders as a duplicate yellow line
  beside the N.
- **eBART is `route=light_rail`, not `subway`.** Accept BOTH for BART, or the
  Pittsburg/Bay Point→Antioch diesel extension is silently dropped and Yellow
  stops short of Antioch.
- Exclude cable cars (`route=cable_car`).

## The core idea
A transit **line** is `(system, color)`. In OSM a line has several route
relations: one per direction, plus service variants (short-turns, weekend,
extensions like eBART). Each single relation is a **linear, single-direction**
path whose member ways are listed in order and share end nodes. `build_line()`
assembles all of a line's relations into continuous chains:

1. **Group relations by `(system, color)`.** Start from the **single longest
   continuous chain** of the most-complete relation (largest total way length).
   Using one direction's relation as the base — instead of unioning every way of
   the line — avoids the classic failure where stitching NB + SB tracks produces
   a self-doubling zigzag "blob". **Take only its longest stitched chain, and add
   that relation's other pieces only where they reach uncovered ground**
   (`_covered()` skip). A single relation often carries the running track AND a
   parallel string of short stop/platform ways on the *same* alignment; if those
   get bridged in, you draw a **second straight-chord copy that cuts across blocks
   instead of following the track** — this was the F's "two straight lines near
   the Ferry Building" bug. Dropping the covered pieces leaves only real,
   road-following track.
   Then **augment**: for each other relation, add its chains only where they
   *don't* already overlap (`_covered()` samples the candidate and skips it if
   ≥60% of points lie within `COVER_TOL_M`≈140 m of an existing chain). This adds
   genuine **extensions/branches** (eBART onto Yellow) without re-drawing the
   opposite direction as a parallel double.
2. **`stitch_ways(ways)`** — concatenate ways that meet end-to-end (within
   `STITCH_TOL_M`, currently 25 m, which also bridges the tiny gaps OSM leaves
   between consecutive ways). At a junction where more than one way meets the
   chain's current end, pick the **straightest** continuation (smallest heading
   change via `_heading`/`_angdiff`); this keeps the mainline together and leaves
   a short spur/siding as its own chain.
3. **`bridge_chains(chains, BRIDGE_TOL_M)`** — join chains whose nearest
   endpoints are within `BRIDGE_TOL_M` (currently 350 m). This closes real breaks
   where a connecting way was missing or got dropped, so a line reads continuous.
   Each pass joins the **globally closest** pair under the tolerance (not the
   first match found), so a near pair is never skipped in favor of a worse early
   one.
4. **Drop strays** — discard any remaining chain shorter than `STRAY_MIN_M`
   (currently 800 m): yard leads, crossovers, station passing tracks. Real
   branches are far longer and survive.
5. **Same-line generous bridge** — bridge the *surviving* real chains again at
   `LINE_BRIDGE_TOL_M` (currently 650 m). Crucially this runs **after** the stray
   drop, so only real same-line pieces participate. This stitches a line that
   genuinely breaks into multiple long pieces (e.g. the **F**, which OSM splits
   into ~10 km + ~3 km + ~2 km chunks around Market/Embarcadero) into one line,
   *without* the over-raise problem below (small strays are already gone, so they
   can't be daisy-chained into surviving junk).

Result for the Bay Area: ~17 features, one continuous line each (plus the
explicitly-added OAK Silver connector), with the redundant stop-fragment doubles
removed.

**Geographic clipping (game scope).** Some lines run beyond the play area; the
drawn overlay is trimmed to what the game uses. Caltrain is clipped at **Tamien**
via `clip_caltrain()` (the South County service Tamien→Gilroy is dropped): for
each Caltrain chain, keep the contiguous part from the SF-ward end to the point
nearest Tamien, then discard any chain a longer kept one already `_covered`s (a
Diridon↔Gilroy variant otherwise leaves a redundant Diridon↔Tamien overlap stub).
Add a similar clip for any future line that extends past the play boundary.

## Tuning the constants
- `STITCH_TOL_M` (25 m): endpoint join tolerance. Raise if a line is fragmented
  into many short pieces; lower if unrelated parallel tracks get joined.
- `BRIDGE_TOL_M` (350 m): gap-closing distance applied **before** the stray drop.
  **Don't over-raise this one** — counter-intuitively a larger value yields *more*
  features, because it fuses several sub-`STRAY_MIN_M` strays into chains long
  enough to survive the stray filter. 350 is the sweet spot.
- `STRAY_MIN_M` (800 m): below this a chain is a stray. Raise to prune more small
  stubs (risks deleting a short real branch); lower to keep more.
- `LINE_BRIDGE_TOL_M` (650 m): same-line bridge applied **after** the stray drop,
  so raising it is safe — only real (≥`STRAY_MIN_M`) pieces of one line/color can
  combine. Raise it if a single line still renders in disconnected long pieces
  (the F). It cannot resurrect junk because junk was already dropped.
- `COVER_TOL_M` (140 m): overlap radius for `_covered()`. Raise if a reverse
  direction still doubles a line; lower if a genuine close-by branch gets
  swallowed and dropped.

To re-tune, sweep values and print the resulting feature count + the small
(`< few km`) chains' midpoints to see what is being kept/dropped.

## Pitfalls (learned the hard way)
- **Don't stitch all of a line's ways together** (both directions): the greedy
  join walks down one track and back up the parallel one, drawing a back-and-
  forth scribble. Pick one relation instead.
- **Don't merge-colocate then group by color-set then stitch**: shared trunks
  fragment because adjacent ways carry slightly different OSM color sets. Per-line
  building sidesteps this entirely.
- A **shared trunk** (e.g. BART's 4 lines up Broadway) is simply several per-line
  features drawn on top of each other; the topmost color shows. That's expected,
  not a bug.
- A dense cluster of one color on the map is usually the **station markers**
  (`stationColor` in `src/lib/style.ts`), not the lines — check before chasing a
  line "blob".

## Verify
1. `python3 scripts/fetch_transit_lines.py` — expect "features: ~18".
2. Sanity-check in Python: each `(system, color)` should be 1 chain (a few lines
   legitimately 2–4 because of real branches); Caltrain should be a single chain.
3. `npm run lint && npx tsc -b --noEmit && npm test && npm run build`.
4. `npm run dev` and eyeball the known-tricky spots: BART trunk Oakland 12th–19th,
   Muni along Market St, VTA on Tasman, Caltrain end-to-end — all continuous.
