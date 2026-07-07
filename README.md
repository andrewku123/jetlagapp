# Jet Lag: Hide & Seek — Seeker Tool

A web app for playing [Jet Lag: The Game — Hide and Seek](https://jetlag.denull.ru/en/rules)
on San Francisco Bay Area transit. Seekers log each question they ask and the
hider's answer; the app eliminates the stations that are no longer possible and
shows the shrinking set of candidate hiding spots on a map.

## Maps

The app ships two maps, chosen from the **map** picker in the top bar. Each map
keeps its **own saved board** (questions, eliminations, drawings, endgame) so
switching between them never mixes state, and its board code is tagged with the
map so a code from one map is rejected on the other.

- **Bay Area** — the full regional map: BART + Caltrain + VTA + Muni + SFO
  AirTrain across five counties (**264 stations**). This is the default.
- **SF Muni** — a day-pass map scoped to the **City & County of San Francisco**:
  the seven Muni rail lines J/K/L/M/N/T/F only (**132 stations**, one county, one
  city). Every other data file (POIs, play area, coastline/borders, places,
  counties, ZIPs, transit lines) is clipped to San Francisco.

Everything below describes the Bay Area map; the SF Muni map behaves identically
with the SF-scoped data, except that some questions are **demoted** because they
can't discriminate there (see [Question demotion](#question-demotion)).

## Play area

The hider may only hide at an eligible transit **station**; travel is allowed on
any public transit. Eligible systems:

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
stations** (263 eligible on a weekday, 264 on a weekend). Distinct stations that
share a city name are disambiguated by system, e.g. "San Bruno (BART)" vs
"San Bruno (Caltrain)".

The full per-station list is in [STATIONS.md](STATIONS.md).

Stations served less often than once per hour (during the daytime window) are
excluded, and there is a **Weekday / Weekend** toggle (e.g. Broadway/Burlingame
is weekend-only on Caltrain). College Park is dropped entirely as a peak-only
flag stop that can never satisfy the hourly rule.

## Game size

Built for the **medium** game. The full medium question deck is available in the
**Ask** tab, and most of it auto-eliminates. What the app eliminates for:

- **Radar** — "are you within ___ of me?" at 1/4, 1/2, 1, 3, 5, 10, 25, 50,
  100 mi, plus a **custom** radius allowed once per game.
- **Thermometer** — "I've traveled at least ___ — hotter or colder?" at 1/2, 3,
  or 10 mi (draws the perpendicular-bisector boundary and shades the colder half).
- **Matching** — "is your nearest ___ the same as mine?" for **county**,
  **city**, nearest **commercial airport**, **transit line**, **station-name
  length**, and any of the 12 mapped **points of interest** (museum, library,
  movie theater, hospital, zoo, aquarium, amusement park, park, golf course,
  sports stadium, mountain, foreign consulate).
- **Measuring** — "compared to me, are you closer to or further from ___?" for a
  **commercial airport**, **sea level** (altitude), a **coastline**, a **state
  border**, a **county border**, an **international border**, and any of the 12
  mapped **POI** categories (as in Matching). A **ZIP code** smaller/larger
  question is also supported. A **rail station** measuring question also
  auto-eliminates but is only useful in the **endgame** — in the first half every
  hiding station is itself a rail station (distance 0), so it eliminates nothing;
  in the endgame it carves the hiding zone (union of your-distance disks around
  the 264 stations).
- **Tentacles** — "of all the ___ within 1 mi of me, which are you closest to?"
  for **museums, libraries, movie theaters, hospitals** (keeps the stations
  closest to the answered POI and shades the eliminated area).
- **Photo** — logged for reference only (does not auto-eliminate, by design).
- **Inside** — endgame-only floor question; logged for reference only.

The remaining booklet subjects (e.g. street/path, 1st & 4th admin divisions,
landmass, amusement park, zoo, aquarium, sports stadium, foreign consulate,
high-speed-rail line, body of water) are selectable and logged for the seeker's
notes, but don't auto-eliminate. Any question can be flagged as an **endgame
question** — its eliminated area is then clipped to the current hiding-zone
circle (see [TUTORIAL.md](TUTORIAL.md)).

## Question demotion

A question that would normally eliminate is automatically **demoted** on a map
where it can't discriminate. This is derived from the active map's own data, so
it stays correct for any future map — nothing is hand-maintained. The rule
follows the game principle that **anything outside the play area is treated as if
it doesn't exist**, so a feature that's off the map isn't a valid answer.

- **Log-only (always)** — recorded for your notes but eliminates/shades nothing,
  in both the regular game and the endgame. A question is log-only when the
  feature it needs doesn't exist in play, or its value is non-spatial and shared
  by every station. On **SF Muni** this demotes **nearest commercial airport**
  (Matching *and* Measuring — SFO/OAK/SJC are all outside San Francisco, so no
  airport is in play), **transit line** Matching (only one system), and any POI
  category with **0** in-play members (e.g. amusement parks).
- **Endgame-only** — log-only in the regular game, but **fully eliminating in the
  endgame**. **County** and **City** Matching can't split an all-one-county /
  all-one-city station list map-wide, but the boundary is *spatial*: a border
  station's 0.25 mi hiding zone can straddle it (e.g. Bayshore/Sunnydale across
  the SF↔San Mateo line), so "same county/city?" carves the endgame zone. On SF
  Muni these show `(endgame only)` in the Ask form.

In the Ask form a demoted subject is tagged `(log only)` / `(endgame only)`, the
button reads **Log question** (not **…& eliminate**) unless it's an endgame
question that eliminates, and the blurb explains why. The **Bay Area** map
demotes nothing (5 counties, 38 cities, multiple agencies, all 3 airports in
play).

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
mountains, foreign consulates) on the map. Each
category can be toggled and searched by name, and the station layer can be set to
Normal / Faded / Hidden so POIs stand out. A place counts if it carries the Google
Maps category icon and has ≥5 reviews. POI data is gathered from OpenStreetMap.

## Satellite imagery

A **satellite** toggle (top bar) overlays Esri World Imagery, clipped to the
play-area counties (land + bay, ocean and the Farallones excluded) to keep tiles
down. Road and place name labels render on top so streets stay readable. The
**Legend** tab lists the imagery source and per-county capture dates; a quarterly
check (`scripts/check_imagery_dates.py`) flags when Esri refreshes the imagery.

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
```

## Data

Each map is a bundle of same-shaped data files registered in
`src/data/regions.ts`; the app is region-agnostic and reads whatever the active
map supplies. The Bay Area `src/data/*.json` files are generated by the scripts
in `/scripts` from authoritative GTFS (BART, Caltrain) and OpenStreetMap line
relations (Muni, VTA), then enriched with county/city (US Census), elevation
(USGS), and airport distances. The **SF Muni** map (`src/data/sfmuni.*.json`) is
derived from those Bay Area files by `scripts/build_sfmuni_region.py`, which
keeps the 132 Muni-served stations and clips every other data file to the City &
County of San Francisco. Because SF is a **consolidated city-county**, its county
polygon is built from the same high-resolution, water-clipped land boundary as
its city (not the coarse Census county shape) so the endgame "same county?"
reference outline hugs the true shoreline. To extend to another city, produce the
same-shaped data files and register the map in `regions.ts`.
