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

## Merging two stops into one station
Two situations:
- **Automated**: `build_stations.py` does a cross-system merge of stops `< 200 m`
  apart across *different* systems (ORs their service flags) — this is what makes
  e.g. 4th & King = Caltrain + Muni. Tunable threshold; see `rebuild-station-dataset`.
- **Manual one-off**: when two records are really the same place (e.g. SFO BART
  "San Francisco International Airport" and the AirTrain "Garage G / BART" stop,
  ~74 m apart), merge into **one** station whose `systems` is the union (BART +
  SFO AirTrain), `lines` is the union, keep one canonical name, and keep it as a
  stop on each line that served either (so per-line counts/legend stay right).
  The merge drops the unique-station count by one but a line that ran through the
  absorbed stop keeps its stop count.

After any merge: update the station-count assertions in
`src/data/stations.test.ts`, rerun `npm test`, and regenerate the PDF.

## Verify
`npm run lint && npx tsc -b --noEmit && npm test && npm run build`. Spot-check the
corrected station in the **Suspects** search (by city) and in the **Matching →
City** flow, and confirm merged stations show all their agencies/lines in the
popup and legend. Re-confirm counts in `src/data/stations.test.ts` match.

## Standing audit
A full train-station accuracy audit (names, coords, line membership, missing/extra
stops across BART/Caltrain/VTA/Muni/SFO AirTrain) is an open task — pair this with
`count-line-stops` (audits per-line membership against OSM route data).
