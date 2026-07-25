---
name: verify-region-poi-eliminations
description: Prove that a non-default region (LA, SF Muni, …) really loads its own POI/station data at runtime and that POI Matching / Measuring / Tentacles eliminate the correct stations, by driving the UI and cross-checking every result against an independent great-circle oracle. Use when changing a region's poi.json / stations.json, adding a region, or touching the POI elimination predicates.
---

# Verify region-scoped POI data + eliminations

## Why this needs a runtime test at all

The unit suite **cannot** catch a broken non-default region:

- `src/data/regions.ts` reads the active region from `localStorage` (**`bahs.region`**)
  **at module load** and exports a frozen `ACTIVE_REGION`.
- `src/lib/poi.ts` builds `POI_BY_CATEGORY` / `POI_COUNTS` from that region's POI file,
  also **at module load**.

So under Vitest the active region is always the default (Bay Area) and only
`src/data/poi.json` is ever exercised. A region's own `*.poi.json` can be empty, stale, or
full of another city's places and every unit test still passes. Always verify a region
change through the running UI.

## Setup

```bash
cd <repo> && npm install --no-audit --no-fund && npm run dev   # http://localhost:5173
```

Switch region **through the UI**, not by poking localStorage: header → `map` `<select>` →
pick the region. `setActiveRegion` persists `bahs.region` and calls `window.location.reload()`,
which is exactly the code path you want to prove. Reset state between questions with
header **Reset** (accept the native confirm dialog).

## The oracle (do not skip this)

Never validate the app against itself. Compute expectations with a standalone haversine
script over the raw JSON, then compare **counts *and* the full station-name sets**.

```python
import json, math
R = 3958.7613  # miles, matches src/lib/geo.ts
def hav(a, b, c, d):
    p1, p2 = math.radians(a), math.radians(c)
    dp, dl = math.radians(c - a), math.radians(d - b)
    x = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2 * R * math.asin(math.sqrt(x))

poi = json.load(open('src/data/la.poi.json'))          # keys: category -> [{n,lat,lon,t,r}]
st  = [s for s in json.load(open('src/data/la.stations.json'))
       if s['headwayMin']['wd'] <= 60]                 # ELIGIBLE_HEADWAY_MIN
near = lambda lat, lon, cat: min((hav(lat, lon, p['lat'], p['lon']), p['n']) for p in poi[cat])
```

Predicate semantics to mirror (`src/lib/elimination.ts`):

| Question | Keeps a station when |
|---|---|
| `match-poi` | `nearestPoi(seeker,cat) == nearestPoi(station,cat)` equals (`answer == 'yes'`) |
| `measure-poi` | `(dist(station) <= dist(seeker))` equals (`answer == 'closer'`) — note `<=` |
| `tentacle` (named POI) | station within radius **and** its nearest *in-radius* POI is the named one |
| `tentacle` `__inside__` / `__outside__` | keeps stations in / out of the radius |

## What to assert in the UI

1. **Data really swapped** — brand text, `N of N possible`, and *all* POI-tab category
   counts plus the "`N` shown" total. Write down the other region's counts first; seeing
   any of them is an immediate fail. Then search a region-unique POI name
   (e.g. `Aquarium of the Pacific`, `Los Angeles Zoo`) and confirm it flies to the right city.
2. **Matching** — the form prints the seeker's nearest POI by name; it must equal the
   oracle's. Log Yes, check count + exact suspect names; delete, re-ask No, check the count
   is the complement and that a Yes-survivor is now struck through in the suspects list
   (search the suspects box by name to find it fast).
3. **Measuring** — the form prints the seeker's distance (rounded); log Closer then Further
   and assert `closer + further == eligible total`. The map shading should invert.
4. **Tentacles** — the in-range `<select>` shows "`N` places in range"; count the options and
   confirm they're all local. Pick one and verify the kept set.
5. **Sparse categories are the best signal** — a 1–4 POI category (aquarium, zoo) gives a
   dramatic, eyeball-checkable geographic split.

## Log-only (demotion) rules

`src/components/QuestionForm.tsx` demotes by **count**, so demotion is data-driven and differs
per region: `match-poi` is log-only when `POI_COUNTS[cat] <= 1`; `measure-poi` only when the
count is `0`. Verify both halves:

- the dropdown label gains **"(log only)"**, the blurb explains why, the submit button becomes
  plain **"Log question"** and the Endgame checkbox disappears;
- logging it leaves the counter unchanged and the History row carries an **info** tag with only
  a Delete action;
- the *Measuring* variant of the same category still eliminates;
- a normal category shows none of the above.
Cross-check against the other region, where the same category may have >1 POI and so must
show no suffix.

## Gotchas

- **Layout shift**: changing the Question dropdown re-renders the panel, so a coordinate paste
  fired immediately after can land in the wrong input. Re-click the visible
  `paste lat, lon` field, type, then click **Set**, and confirm the label echoes the coords.
- Distances in the UI are rounded to 2 dp — compare against the oracle at that precision.
- Eligible-station counts differ per region (LA 158/158, Bay 263/264 at `wd <= 60`); derive
  them from the data, don't assume.
- Encoding regressions: if the POI JSON was re-encoded (UTF-8 vs `\uXXXX`), search an accented
  name (e.g. `Galería de la Raza`) and confirm no `GalerÃ­a` mojibake.

## Verify

Runtime checks only; no build step. If you changed app code, still run
`npm run lint && npm run typecheck && npm test && npm run build`, plus
`python3 scripts/test_poi_pipeline.py` for pipeline changes.

## Devin Secrets Needed

None — the app runs fully locally with no auth.
