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

## The core idea
A transit **line** is `(system, color)`. In OSM a line has several route
relations: one per direction, plus service variants (short-turns, weekend). Each
single relation is a **linear, single-direction** path whose member ways are
listed in order and share end nodes. So:

1. **Group relations by `(system, color)`.** For each line, keep only the
   **most-complete relation** (largest total way length). Using one direction's
   relation — instead of unioning every way of the line — is what avoids the
   classic failure where stitching NB + SB tracks produces a self-doubling
   zigzag "blob".
2. **`stitch_ways(ways)`** — concatenate ways that meet end-to-end (within
   `STITCH_TOL_M`, currently 25 m, which also bridges the tiny gaps OSM leaves
   between consecutive ways). At a junction where more than one way meets the
   chain's current end, pick the **straightest** continuation (smallest heading
   change via `_heading`/`_angdiff`); this keeps the mainline together and leaves
   a short spur/siding as its own chain.
3. **`bridge_chains(chains, BRIDGE_TOL_M)`** — join chains whose nearest
   endpoints are within `BRIDGE_TOL_M` (currently 350 m). This closes real breaks
   where a connecting way was missing or got dropped, so a line reads continuous.
4. **Drop strays** — discard any remaining chain shorter than `STRAY_MIN_M`
   (currently 800 m): yard leads, crossovers, station passing tracks. Real
   branches are far longer and survive.

Result for the Bay Area: ~25 features, one continuous line each, plus a few
genuine branch stubs (Oakland BART wye, downtown San Jose VTA loop, the F-line
wharf segment).

## Tuning the three constants
- `STITCH_TOL_M` (25 m): endpoint join tolerance. Raise if a line is fragmented
  into many short pieces; lower if unrelated parallel tracks get joined.
- `BRIDGE_TOL_M` (350 m): gap-closing distance. **Don't over-raise** — counter-
  intuitively, a larger value yields *more* features, because it fuses several
  sub-`STRAY_MIN_M` strays into chains long enough to survive the stray filter.
  350 was the empirical minimum-feature sweet spot.
- `STRAY_MIN_M` (800 m): below this a chain is a stray. Raise to prune more small
  stubs (risks deleting a short real branch); lower to keep more.

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
1. `python3 scripts/fetch_transit_lines.py` — expect "features: ~25".
2. Sanity-check in Python: each `(system, color)` should be 1 chain (a few lines
   legitimately 2–4 because of real branches); Caltrain should be a single chain.
3. `npm run lint && npx tsc -b --noEmit && npm test && npm run build`.
4. `npm run dev` and eyeball the known-tricky spots: BART trunk Oakland 12th–19th,
   Muni along Market St, VTA on Tasman, Caltrain end-to-end — all continuous.
