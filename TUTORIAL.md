# Tutorial — Jet Lag: Hide & Seek seeker tool

A step-by-step guide to playing [Jet Lag: Hide and Seek](https://jetlag.denull.ru/en/rules)
as the **seeker** with this app. The app never talks to the hider — you type in
each question you ask and the answer you get back, and it eliminates the stations
that are no longer possible so you can see where the hider can still be.

See [README.md](README.md) for the maps, play area, and the list of supported
questions.

## 0. Pick a map

The **map** picker in the top bar chooses which map you're playing:

- **Bay Area** — the full regional map (BART/Caltrain/VTA/Muni/AirTrain, 264
  stations, five counties). Default.
- **SF Muni** — a day-pass map scoped to San Francisco (the 7 Muni rail lines,
  132 stations, one county/city).
- **LA Metro** — Los Angeles County (rail A/B/C/D/E/K plus the G and J busways,
  158 stations).

Each map keeps its **own saved board**, so switching maps never mixes state, and
you can hand off a game by its board code (a code from one map won't load on the
other). Each map also sets its own **game size** from how many stations it has —
all three are `medium` today, which is what decides the deck of questions you can
ask; the **Legend** tab names it under *About this map*. A question that can't
tell that map's stations apart is demoted automatically — see §12.

## 1. The screen at a glance

- **Map** (left / main): every eligible station as a dot. Possible stations are
  solid; eliminated ones are dimmed (toggle with **show eliminated**).
- **Top bar:**
  - **map** — which map you're playing (see §0).
  - **Weekday / Weekend** — which service day you're playing. It changes which
    stations are eligible (some stops only run often enough on one of them). This
    toggle is **hidden** on maps where the service day makes no difference (SF
    Muni and LA Metro, where every station runs often enough on both days).
  - **mi/ft / km/m** — imperial or metric for every distance and elevation in the
    app (inputs and labels both switch).
  - **show eliminated** — show or hide the dimmed, ruled-out stations.
  - **satellite** — overlay aerial imagery on the play area (see §6).
  - **Reset** — clear the whole game (questions, manual eliminations, drawings).
  - The count "**N of M possible**" is your live progress.
- **Right panel tabs:** **Ask**, **History**, **Suspects**, **POI**, **Legend**.

On a phone the map fills the screen and the panel becomes a slide-up bottom
sheet — tap the **Controls** button (or the grab handle) to open/close it. Station
and POI dots have enlarged invisible tap targets so they're easy to tap by finger.

## 2. Set up the game

1. Pick **Weekday** or **Weekend** to match when you're playing.
2. Pick your **units** (mi/ft or km/m).
3. That's it — the board starts with every eligible station "possible".

## 3. Ask a question (the core loop)

Each time you ask the hider a question and get an answer, log it here so the app
can eliminate stations.

1. Go to the **Ask** tab.
2. **Type** — pick a category from the buttons: Radar, Thermometer, Matching,
   Measuring, Tentacles, Inside, or Photo. Categories with more than one subject
   (Matching, Measuring, Tentacles, Photo) then show a second dropdown for the
   specific question (e.g. county, city, airport, line, name length, a coastline,
   nearest museum/park/hospital…).
3. Read the **blurb** — it explains the question and shows the **hider's card
   reward**, e.g. `(draw 2, keep 1)`. This number updates live (see §5).
4. Fill in the parameters:
   - **Radar** — choose a radius (or Custom…), then set the **center**: click the
     map and press **Use last click**, or paste `lat, lon` and press **Set**.
   - **Thermometer** — set **Start A** and **End B** (the two points you traveled
     between), same click-or-paste pickers.
   - **Measuring** / **Matching** (airport, coastline, borders, sea level, and the
     POI subjects) use your location as a point — click the map or paste
     `lat, lon`; **Matching (name length)** takes a number; the admin-division
     **Matching** questions take a dropdown value.
   - **Tentacles** — set your location; the app lists the in-range POIs of the
     chosen category and you pick the one the hider answers.
   - **Inside** — type the building and floor.
5. Record the hider's answer (Yes/No, Hotter/Colder, Closer/Further, …).
6. (Optional) add a **Note**.
7. (Optional) tick **Endgame question** — the question still eliminates stations
   map-wide, but its shading is clipped to the current hiding-zone circle so you
   can pinpoint the hider inside it. It defaults on once you're in the endgame.
8. Press **Log question & eliminate** (or **Log question** for the reference-only
   and demoted subjects — see §12). The app applies the filter and the "possible"
   count drops. You'll land on the **History** tab.

Switching to another tab (POI/Suspects/Legend/History) and back to **Ask** keeps
your current selection and parameters, so you don't lose a half-composed
question.

### If the hider vetoes
If the hider refuses to answer (a veto), press **Hider vetoed** instead of Log.
The question is recorded (so you remember you can ask it again) but **eliminates
nothing** and has no answer. It still counts toward the repeat-cost tally (§5).

## 4. History — review and manage questions

The **History** tab lists every question you've logged, newest first. Each row
shows the question, the answer, and the hider's reward. You can:

- **Disable / Enable** — temporarily turn a question's elimination off/on without
  deleting it.
- **Delete** — remove the question entirely.
- Vetoed questions are struck through and tagged `vetoed`; they only offer Delete.

## 5. Repeat-question cost

Re-asking the **same** question makes the hider draw more cards: the nth time you
ask a question, its reward is multiplied by n (2nd ask → ×2, 3rd → ×3, …).

- Radar and Thermometer count as "the same" only at the **same radius / travel
  distance** (a 5 mi radar and a 10 mi radar are different questions). Every other
  question type counts by type.
- The **Ask** tab previews this live: pick a radius you've already used and the
  blurb shows e.g. `(draw 4, keep 2 — ×2, 2nd time asked)`; switch to a fresh
  radius and it drops back to the base cost.
- The **History** row for each ask shows the reward it actually cost.

## 6. Satellite view

Tick **satellite** in the top bar to overlay aerial imagery, clipped to the play
area — anything out of play stays grey, so the boundary is obvious. Road and
place names are drawn on top so streets stay readable. The **Legend** tab lists
the imagery source and its capture dates.

## 7. POI — reference layer for POI questions

The **POI** tab overlays the points of interest used to compose Tentacles,
Matching and Measuring questions (museums, libraries, movie theaters, hospitals,
zoos, aquariums, amusement parks, parks, golf courses, sports stadiums,
mountains, foreign consulates) on the map while the tab is open.

- Toggle any category on/off, or use **Show all** / **Hide all**.
- **Search POI name…** filters the dots and offers a top-5 suggestion dropdown;
  picking one flies the map to it.
- Set the **Stations** layer to **Normal / Faded / Hidden** so the POIs stand out.
- A place counts if it carries the Google Maps category icon and has ≥5 reviews
  — so if the hider names something that isn't on this layer, it isn't a legal
  answer. Mountains are the exception (peaks aren't reviewed).
- Each map has its own set: **2,340** places on Bay Area, **502** on SF Muni,
  **2,056** on LA Metro.

## 8. Suspects — work the candidate list

The **Suspects** tab is the text list of stations, split into still-possible and
eliminated.

- **Search** — filter by name, alias, system, line, city, or county.
- **Sort** — by name, or grouped by agency → line.
- **★** stars a station (pins it to the top) — handy for ones you're watching.
- **✕** eliminates a station by hand (e.g. you ruled it out by reasoning the app
  can't); **↩** restores it.
- Clicking a station **name** flies the map to it.

## 9. Endgame

When you're down to one suspected station, open its popup on the map and choose
**🎯 Endgame here**. The board collapses to that station and draws its **hiding
zone** — the circle the hider must be within for the endgame — shading everything
outside it. A banner shows the station and the zone radius. Choose **Exit
endgame** (popup or banner) to go back to the full board.

The **Measuring — Rail station** question is designed for this phase: in the
first half it eliminates nothing (every hiding station is itself a rail station,
so your distance is 0), but in the endgame the hider answers from their real
position, and "closer/further from the nearest rail station" carves the hiding
zone just like the airport measuring question.

**County / City Matching are endgame tools on single-county / single-city maps.**
On SF Muni every station is in the same county and city, so those questions can't
split the board in the regular game (they're `(endgame only)` — see §12). But a
border station's hiding zone can straddle the county/city line (e.g.
Bayshore/Sunnydale across the SF↔San Mateo line), so ticking **Endgame question**
and asking "same county/city?" carves the zone along that boundary. On LA Metro
**County** Matching is dead even here — the nearest station is about 3 km inside
the county line, further than any hiding zone reaches — so it's plain
`(log only)`; City Matching there is a normal, fully eliminating question.

## 10. The map toolbox (drawing tools)

A slim vertical toolbar sits on the right edge of the map. Drawings are saved
locally and survive a reload. The tools (top to bottom):

- **✋ Select** (default) — clicking the map drops a seeker point for questions.
  **This is also the only mode where you can move or edit existing drawings:**
  drag a drawing's handle to move it, or click it to open its edit popup.
- **Compass (circle)** — pick a radius, then click a center to draw a circle.
  Great for sanity-checking a radar by hand. In Select mode, drag the center to
  move it, or click it to change the radius / delete it.
- **Line (straightedge)** — click two points to draw a straight line.
- **Bisector** — click two points; it draws the **perpendicular bisector** of
  them — i.e. the hotter/colder boundary for a thermometer between those points —
  plus a short connector labeled with the A–B distance.
- **Measure** — click two points to read the great-circle distance between them.
  In Select mode, click the line to change its rounding (exact, ½, 1, 5, 10, or
  custom).
- **📍 Coord** — click anywhere to read that point's `lat, lon` (it's also copied
  to your clipboard). It's a quick read-out — it doesn't leave a drawing.

Helpful behaviors:

- **Snap / reuse a point.** While a drawing tool is active, clicking within a few
  pixels of an existing point reuses that exact point (the target dot enlarges so
  you can see what you'll snap to). This lets you, e.g., start a line exactly at a
  circle's edge point. Zoom in to place points close together.
- **Linked move.** In Select mode, dragging a point that several drawings share
  moves them all together.
- **Undo / Clear.** **Undo** removes the in-progress click (or the last drawing);
  **Clear drawings** removes them all.
- **Delete one.** In Select mode, open a circle's or measure line's popup and
  press **Delete**. Lines and bisectors have no popup — remove them with Undo or
  by redrawing.

## 11. Tips

- Log questions in the order you ask them; the repeat-cost multiplier counts in
  ask order.
- **Hand the board to a teammate** with the **Legend** tab's *Board code*: copy
  the code, they paste it. It carries your eliminations only, merges into
  whatever they've already ruled out (Reset first for an exact copy), and a code
  from another map is rejected.
- Use **Disable** instead of Delete if you suspect you mis-entered an answer and
  want to compare the board with/without it.
- **Reset** wipes everything — only use it to start a brand-new game.

## 12. Demoted questions (per map)

Some questions can't tell any stations apart on a given map, so the app **demotes**
them automatically (worked out from that map's own data — nothing hand-listed).
The game rule is that anything outside the play area doesn't exist, so a feature
that's off the map can't be an answer.

- **`(log only)`** — you can still record it for your notes, but it eliminates and
  shades **nothing**, in the regular game and the endgame.
- **`(endgame only)`** — log-only in the regular game, but it **does** eliminate
  once you're in the endgame (see §9): useless map-wide, but it carves a border
  station's hiding zone.

What that means per map:

| Map | `(log only)` | `(endgame only)` |
|---|---|---|
| **Bay Area** | nothing | nothing |
| **SF Muni** | nearest **commercial airport**, Matching and Measuring (SFO/OAK/SJC are all outside San Francisco, so no airport exists in play), and any POI category with no in-play locations (e.g. amusement parks) | **County** and **City** Matching |
| **LA Metro** | **County** Matching | nothing |

On every map the **state border** and **international border** Measuring
subjects are `(log only)` too — none of these play areas has one.

The Ask form marks the subject with the tag, the button changes to **Log
question**, and the blurb tells you why.
