---
name: station-identity
description: Verify and correct a station's identity attributes — its city/county (for the Matching question), and merge two near-duplicate stops into one multi-agency station. Use when a station's city looks wrong, when two stops are really one place, or when auditing station accuracy.
---

# Station identity: city/county verification & merging

The dataset pipeline (see `rebuild-station-dataset`) auto-fills each station's
`city`/`county` and merges nearby stops, but both are **best-effort and can be
wrong** in edge cases that matter for the **Matching → City/County** question.
This skill is the procedure to verify and correct them.

## How city/county is assigned (and why it can be wrong)
- `build_attributes.py` reverse-geocodes each `lat/lon` via the **US Census
  geocoder** and writes `city`/`county`. It effectively snaps to a nearby place,
  so a point in **unincorporated** land gets the *nearest* city name rather than
  "unincorporated" — which is wrong for the City question.
- Real example: **SFO** (BART + AirTrain) came out as `South San Francisco city`,
  but SFO is **not in any city** — it's unincorporated San Mateo County (land
  owned by the City & County of San Francisco). Always sanity-check airport,
  port, and other large-parcel stations.

## Independently verify a city (two sources, agree before trusting)
1. **US Census geocoder — Incorporated Places layer.** Query the coordinate
   against the *Incorporated Places* layer specifically. If it returns **no
   place** (only a "… CCD" County Census Subdivision, which is a stats area, not
   a city), the point is **unincorporated** — there is no city.
2. **OSM Nominatim reverse geocode.** For unincorporated points it resolves to
   just the county (e.g. "San Mateo County") with no city/town.

If both return no city, the location is unincorporated; do not invent one. When a
station has no real city, decide with the user how to file it for the City
question (for SFO the user chose **San Francisco** — airport owned by City &
County of SF, SFO mailing address — applied to BART + all AirTrain stops so they
group together).

Apply a correction consistently to **all** stops at that place (e.g. every
AirTrain stop + the SFO BART stop), and regenerate the reference PDF
(`reference-pdf`) since it lists stations by city.

## When are two stops one station? (it's a judgement call, not a formula)
**Merging is decided by the official transit map + real-world facts, never by
distance alone.** The authority is the map's **"Shared Station"** designation
(plus physical reality: shared concourse/fare gates, same grade, walkability).
Proximity is only a hint and is often wrong:
- **Merge** — *Balboa Park* (BART + Muni) and the downtown stations (Embarcadero,
  Montgomery, Powell, Civic Center): the SFMTA Metro map draws these as shared
  stations, so they are one record.
- **Keep separate** — *Glen Park BART* vs the *San Jose Ave/Glen Park Station*
  Muni J stop: only ~80 m apart, but split by **I-280** (grade change, no shared
  concourse) and drawn as two distinct stations on the map. They are **two**
  records (`Glen Park` = BART, `San Jose Ave/Glen Park Station` = Muni J).

How this is encoded:
- **Curated allow-list** (the right way): `build_stations.py` only merges a
  cross-agency pair if both stops sit within `MERGE_RADIUS_M` (250 m) of an entry
  in the hand-maintained **`SHARED_STATIONS`** anchor list (read off the official
  maps). There is **no** automatic "merge anything within X metres" rule, on
  purpose — that rule wrongly fused Glen Park. **Expanding to a new city: review
  every shared station on that system's map and add anchors by hand.**
- **Manual one-off**: when two records are really the same place (e.g. SFO BART
  "San Francisco International Airport" and the AirTrain "Garage G / BART" stop,
  ~74 m apart), merge into **one** station whose `systems` is the union (BART +
  SFO AirTrain), `lines` is the union, keep one canonical name, and keep it as a
  stop on each line that served either (so per-line counts/legend stay right).
  The merge drops the unique-station count by one but a line that ran through the
  absorbed stop keeps its stop count.

## Adding a missing line to a station vs. making a new node
When a line's stop is missing because it shares a corner with an existing
station, **add the line to that station** rather than creating a near-duplicate
node. Example: the J's surface **Church & Market** stop was missing; that corner
already existed as `s097 Church St Station` (K/L/M), so the fix was appending
`Muni J` to its `lines` + a `Church & Market` alias — not a new record. (Note the
J/N never enter the *underground* Church Station; they portal at Duboce to the
north, so only K/L/M call there.) Cross-check the real stop list against OSM
route relations (`count-line-stops`) and the SFMTA stop export
(`muni_stops.json`, ~3260 platforms with `onstreet`/`atstreet`).

## Splitting one conflated record into two real stops
The inverse of merging: when a single record actually represents **two distinct
real platforms** (e.g. the J's **Right Of Way/Liberty St** vs **/21st St**, ~90 m
apart, both real SFMTA stops at different cross-streets — only one was kept, the
other folded in as an alias), split them:
1. Correct the kept record's `lat/lon` to its true platform and clean its `aka`.
2. **Append** the second record at the **end** of `stations.json` with a fresh
   `id` (`s{NNN}`, next number up). Do **not** re-run `build_attributes.py` to add
   it — that reassigns every `id` positionally (`s{i:03d}`) and would shift all
   later ids, breaking saved state. Compute the new record's fields offline
   instead: `elevation` from USGS (`epqs.nationalmap.gov/v1/json?...&units=Meters`),
   `airportDist` via haversine to the three `AIRPORTS` pins in `build_attributes.py`
   (then `nearestAirport = min`), and copy `county`/`city`/`headwayMin`/`service`
   from the sibling stop tens of metres away. Set `nameLength = base-name length`.
3. Write with `json.dump(..., indent=1, ensure_ascii=False)` — the file keeps
   literal UTF-8 (en-dashes), so `ensure_ascii=True` would rewrite the whole file.

After any merge or split: update the station-count assertions in
`src/data/stations.test.ts` (total, per-system membership, eligible wd/we), rerun
`npm test`, and regenerate the PDF.

## Verify
`npm run lint && npx tsc -b --noEmit && npm test && npm run build`. Spot-check the
corrected station in the **Suspects** search (by city) and in the **Matching →
City** flow, and confirm merged stations show all their agencies/lines in the
popup and legend. Re-confirm counts in `src/data/stations.test.ts` match.

## Standing audit
A full train-station accuracy audit (names, coords, line membership, missing/extra
stops across BART/Caltrain/VTA/Muni/SFO AirTrain) is an open task — pair this with
`count-line-stops` (audits per-line membership against OSM route data).
