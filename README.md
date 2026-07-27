# Jet Lag: Hide & Seek — Seeker Tool

A web app for playing [Jet Lag: The Game — Hide and Seek](https://jetlag.denull.ru/en/rules)
on real transit. Seekers log each question they ask and the hider's answer; the
app eliminates the stations that are no longer possible and shows the shrinking
set of candidate hiding spots on a map.

## Maps

The app ships three maps, chosen from the **map** picker in the top bar. Each map
keeps its **own saved board** (questions, eliminations, drawings, endgame) so
switching between them never mixes state, and its board code is tagged with the
map so a code from one map is rejected on the other.

| Map | Transit | Stations | Play area |
|---|---|--:|--:|
| **Bay Area** (default) | BART + Caltrain + VTA + Muni + SFO AirTrain, five counties | 264 | 1,236 sq mi |
| **SF Muni** | the 7 Muni rail lines J/K/L/M/N/T/F, one city/county | 132 | 46 sq mi |
| **LA Metro** | Metro rail A/B/C/D/E/K + the G and J busways, Los Angeles County | 158 | 907 sq mi |

A map is a self-contained bundle of data files — stations, play area, POIs,
places, counties, ZIPs, transit lines, measure features — and the app itself is
region-agnostic: it reads whatever the active map supplies. Two consequences
worth knowing:

- **The map decides the game size**, from its station count against the
  rulebook's own thresholds (small ≤100, medium ≤500, large beyond), and the
  question deck follows. All three maps are **medium** games; the **Legend** tab
  names the size under *About this map*.
- **A question that can't discriminate on a map is demoted automatically**, from
  that map's data rather than a hand-kept list (see
  [Question demotion](#question-demotion)).

The rest of this file describes any map; where the maps differ, the difference is
called out.

## Play area

The hider may only hide at an eligible transit **station**; travel is allowed on
any public transit. A station is only eligible if it is served **at least once an
hour** through the daytime window, counting all lines together per direction — a
rule that does not loosen on bigger maps.

### Bay Area

- **BART** — all stations (50)
- **Caltrain** — SF (4th & King) → San Jose Diridon → Tamien (24)
- **VTA light rail** — full system (59)
- **Muni Metro & Streetcars** — lines N, J, F, K, L, M, T (132)
- **SFO AirTrain** — all people-mover stops (11)

Muni includes **every rail stop** (both the labeled stations and the smaller
intermediate "Other Stop" dots) on lines N/J/F/K/L/M/T, pulled from OpenStreetMap
and deduped: the two directional platforms of a stop are merged, shared subway
stops (Embarcadero/Montgomery/Powell/Civic Center/Church/Castro/Forest Hill/West
Portal) are counted once, and North Beach on the T is excluded. The 10 F-only
surface stops on Market St inland of Embarcadero are also excluded — they run
directly above the Muni Metro subway and duplicate those stations. After merging
stations shared across systems (e.g. 4th & King = Caltrain + Muni N/T; Balboa
Park = BART + Muni; Milpitas = BART + VTA) the play area has **264 unique
stations**. Distinct stations that share a city name are disambiguated by system,
e.g. "San Bruno (BART)" vs "San Bruno (Caltrain)".

Service differs by day here, so the **Weekday / Weekend** toggle is live: **263**
stations are eligible on a weekday and **264** at the weekend (Broadway/
Burlingame is weekend-only on Caltrain). College Park is dropped entirely as a
peak-only flag stop that can never satisfy the hourly rule.

### SF Muni

The same 132 Muni rail stops, scoped to the **City & County of San Francisco**
and played as a day-pass map. Every other data file (POIs, play area,
coastline/borders, places, counties, ZIPs, transit lines) is clipped to San
Francisco. Service is identical both days, so the Weekday / Weekend toggle is
hidden.

### LA Metro

Metro rail — **A, B, C, D, E, K** — plus the **G** and **J** busways, which the
rulebook counts as rapid transit; every busway stop is a hiding station in its
own right, including the J stops that share a street corner with a rail station.
All 158 stations run at least hourly both days. The play area is the transit-
served cities of Los Angeles County, clipped to the real shoreline (full beach
in, ocean out, harbor basins and the piers traced in), so the coastline question
measures against the same edge the map draws.

The full per-station list for every map is in [STATIONS.md](STATIONS.md).

## The question deck

Each map's size selects the deck (all three are **medium** today). The full deck
for the size is available in the **Ask** tab, and most of it auto-eliminates.
What the app eliminates for:

- **Radar** — "are you within ___ of me?" at 1/4, 1/2, 1, 3, 5, 10, 25, 50,
  100 mi, plus a **custom** radius allowed once per game.
- **Thermometer** — "I've traveled at least ___ — hotter or colder?" at 1/2, 3 or
  10 mi (the 50 mi card is large-game only). Draws the perpendicular-bisector
  boundary and shades the colder half.
- **Matching** — "is your nearest ___ the same as mine?" for **county**,
  **city**, nearest **commercial airport**, **transit line**, **station-name
  length**, and any of the 12 mapped **points of interest** (museum, library,
  movie theater, hospital, zoo, aquarium, amusement park, park, golf course,
  sports stadium, mountain, foreign consulate).
- **Measuring** — "compared to me, are you closer to or further from ___?" for a
  **commercial airport**, **sea level** (altitude), a **coastline**, a **county
  border**, and any of the 12 mapped **POI** categories (as in Matching). The
  **state** and **international border** subjects are offered too, but no map
  ships one in play today, so they are `(log only)`. A **ZIP code** smaller/larger
  question is also supported. A **rail station** measuring question also
  auto-eliminates but is only useful in the **endgame** — in the first half every
  hiding station is itself a rail station (distance 0), so it eliminates nothing;
  in the endgame it carves the hiding zone (union of your-distance disks around
  every station on the map).
- **Tentacles** — "of all the ___ within 1 mi of me, which are you closest to?"
  for **museums, libraries, movie theaters, hospitals** (keeps the stations
  closest to the answered POI and shades the eliminated area). The 15 mi
  categories (zoo, aquarium, amusement park) are large-game only, so no map
  offers them yet. If only one POI sits in the circle, answer **within / not
  within** instead and the tentacle behaves as a radar of that radius.
- **Photo** — logged for reference only (does not auto-eliminate, by design).
- **Inside** — endgame-only floor question; logged for reference only.

The remaining booklet subjects (e.g. street/path, 1st & 4th admin divisions,
landmass, high-speed-rail line, body of water) are selectable and logged for the
seeker's notes, but don't auto-eliminate. Any question can be flagged as an
**endgame question** — its eliminated area is then clipped to the current
hiding-zone circle (see [TUTORIAL.md](TUTORIAL.md)).

## Question demotion

A question that would normally eliminate is automatically **demoted** on a map
where it can't discriminate. This is derived from the active map's own data, so
it stays correct for any future map — nothing is hand-maintained. The rule
follows the game principle that **anything outside the play area is treated as if
it doesn't exist**, so a feature that's off the map isn't a valid answer.

- **Log-only (always)** — recorded for your notes but eliminates/shades nothing,
  in both the regular game and the endgame. A question is log-only when the
  feature it needs doesn't exist in play, or its value is shared by every station
  and its boundary is out of reach of any hiding zone.
- **Endgame-only** — log-only in the regular game, but **fully eliminating in the
  endgame**. **County** and **City** Matching can't split an all-one-county /
  all-one-city station list map-wide, but the boundary is *spatial*: a border
  station's 0.25 mi hiding zone can straddle it (e.g. Bayshore/Sunnydale across
  the SF↔San Mateo line), so "same county/city?" carves the endgame zone.

What each map demotes today, all of it derived, none of it listed by hand:

| Map | Log-only | Endgame-only |
|---|---|---|
| **Bay Area** | — | — |
| **SF Muni** | nearest commercial airport (Matching *and* Measuring — SFO/OAK/SJC all lie outside San Francisco), plus any POI category with no in-play member (e.g. amusement parks) | County Matching, City Matching |
| **LA Metro** | County Matching | — |

LA's county case shows why the rule is geometric rather than "is this value
uniform?": every LA Metro station is one county's worth of the same answer, and
the nearest one is ~3 km from the county line — far outside a 0.25 mi hiding
zone — so the question is dead in the endgame too, unlike SF Muni's border
stations. LA keeps **line** Matching (8 lines) and both airport questions (LAX
and LGB are inside the play area; BUR/ONT/SNA are not, and so do not exist).

In the Ask form a demoted subject is tagged `(log only)` / `(endgame only)`, the
button reads **Log question** (not **…& eliminate**) unless it's an endgame
question that eliminates, and the blurb explains why.

## Card rewards and repeat cost

Every logged question shows the hider's card reward. Re-asking the **same**
question costs the hider more: the nth ask of a question multiplies the reward by
n (radar/thermometer count as "the same" only at the same radius/travel distance).
The Ask form previews this cost live as you choose parameters. If the hider
**vetoes** a question (refuses to answer), use the **Hider vetoed** button to log
it without an answer — it's recorded but eliminates nothing, and still counts
toward the repeat-cost tally.

## POI reference tab

The **POI** tab overlays the points of interest used to compose Tentacles /
Matching / Measuring questions (museums, libraries, movie theaters, hospitals,
zoos, aquariums, amusement parks, parks, golf courses, sports stadiums,
mountains, foreign consulates) on the map. Each category can be toggled and
searched by name, and the station layer can be set to Normal / Faded / Hidden so
POIs stand out.

A place is in the game only if it carries the Google Maps **category icon** and
has **≥5 reviews** — the rulebook's legitimacy test, which keeps a resident's
"library" pin or a strip of grass tagged as a park out of the answers. Mountains
are the exception (a peak has a summit, not a review count). Discovery is
OpenStreetMap-first, checked against Google and, where one exists, an official
registry (e.g. the State Department's consulate list), then de-duplicated so one
physical place is one pin: **Bay Area 2,340 · SF Muni 502 · LA Metro 2,056**
places. The pipeline and its 6-monthly refresh live in
`.agents/skills/gather-poi/`.

## Satellite imagery

A **satellite** toggle (top bar) overlays Esri World Imagery, clipped to the
active map's play area — tiles outside it are never requested, and the layer is
masked to the in-play polygons, so out-of-play land stays grey. Road and place
name labels render on top so streets stay readable. The **Legend** tab lists the
imagery source and capture dates; a quarterly check
(`scripts/check_imagery_dates.py`) flags when Esri refreshes the imagery.

## Printable reference card

`scripts/make_reference_pdf.py --region bay|sfmuni|la` prints the two-page card
for a map: page 1 is the question deck for that map's game size (every card with
its draw/keep cost, answer window and subject checkboxes, with the rules that
apply to all of them stated once in the header), page 2 is the play-area
reference — station name lengths and altitudes, counties, cities, in-play
airports and the POI inventory. It reads the same data files the app does, so the
card can't disagree with the board.

## Map drawing tools (toolbox)

A toolbar on the right of the map lets seekers annotate by hand (drawings persist
locally):

- **Compass** — pick a radius and click a center to draw a circle.
- **Line** — click two points to draw a straightedge line.
- **Bisector** — click two points to draw their perpendicular bisector (the
  hotter/colder boundary for a thermometer).
- **Measure** — click two points to read the great-circle distance in miles.
- **Select** — default mode; clicking the map drops a seeker point for questions.

Click any drawing to delete it, or use **Clear drawings**. See
[TUTORIAL.md](TUTORIAL.md) for a full step-by-step walkthrough of the app and
toolbox.

## Develop

```bash
npm install
npm run dev        # local dev server
npm run build      # typecheck + production build to dist/
npm run lint
npx vitest run     # tests
```

## Data

Each map is a bundle of same-shaped data files registered in
`src/data/regions.ts`; the app is region-agnostic and reads whatever the active
map supplies.

- **Bay Area** (`src/data/*.json`) is generated by the scripts in `/scripts` from
  authoritative GTFS (BART, Caltrain) and OpenStreetMap line relations (Muni,
  VTA), then enriched with county/city (US Census), elevation (USGS) and airport
  distances.
- **SF Muni** (`sfmuni.*.json`) is derived from those files by
  `scripts/build_sfmuni_region.py`, which keeps the 132 Muni-served stations and
  clips every other file to the City & County of San Francisco. Because SF is a
  **consolidated city-county**, its county polygon is built from the same
  high-resolution, water-clipped land boundary as its city (not the coarse Census
  county shape) so the endgame "same county?" outline hugs the true shoreline.
- **LA Metro** (`la.*.json`) comes from Metro's GTFS plus OSM route relations,
  through the same attribute, play-area and POI pipelines.

Station eligibility is computed per direction by `scripts/compute_headways.py`
(the longest gap between consecutive departures, not a median), so a station that
looks frequent on average but has a 90-minute hole is correctly excluded.
[STATIONS.md](STATIONS.md) is regenerated from the shipped data by
`node scripts/build_stations_md.mjs` — it exists so a data change is reviewable as
a diff; edit the data, never that file.

To extend to another city, produce the same-shaped data files and register the
map in `regions.ts`; the procedure is written up in
`.agents/skills/add-transit-city/`.
