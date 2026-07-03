# Bay Area Hide & Seek — Seeker Tool

A web app for playing [Jet Lag: The Game — Hide and Seek](https://jetlag.denull.ru/en/rules)
in the San Francisco Bay Area. Seekers log each question they ask and the hider's
answer; the app eliminates the stations that are no longer possible and shows the
shrinking set of candidate hiding spots on a map.

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
  question is also supported.
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

`src/data/stations.json` is generated by the scripts in `/scripts` (and the
data pipeline in the project notes) from authoritative GTFS (BART, Caltrain) and
OpenStreetMap line relations (Muni, VTA), then enriched with county/city
(US Census), elevation (USGS), and airport distances. To extend to another city,
produce a `stations.json` with the same shape.
