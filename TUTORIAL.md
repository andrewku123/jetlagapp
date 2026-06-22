# Tutorial — Bay Area Hide & Seek seeker tool

A step-by-step guide to playing [Jet Lag: Hide and Seek](https://jetlag.denull.ru/en/rules)
as the **seeker** with this app. The app never talks to the hider — you type in
each question you ask and the answer you get back, and it eliminates the stations
that are no longer possible so you can see where the hider can still be.

See [README.md](README.md) for the play area and the list of supported questions.

## 1. The screen at a glance

- **Map** (left / main): every eligible station as a dot. Possible stations are
  solid; eliminated ones are dimmed (toggle with **show eliminated**).
- **Top bar:**
  - **Weekday / Weekend** — which service day you're playing. It changes which
    stations are eligible (some stops only run often enough on one of them).
  - **mi/ft / km/m** — imperial or metric for every distance and elevation in the
    app (inputs and labels both switch).
  - **show eliminated** — show or hide the dimmed, ruled-out stations.
  - **satellite** — overlay aerial imagery on the play area (see §6).
  - **Reset** — clear the whole game (questions, manual eliminations, drawings).
  - The count "**N of M possible**" is your live progress.
- **Right panel tabs:** **Ask**, **History**, **Suspects**, **Legend**.

On a phone the panel is a bottom sheet — tap the grab handle to open/close it.

## 2. Set up the game

1. Pick **Weekday** or **Weekend** to match when you're playing.
2. Pick your **units** (mi/ft or km/m).
3. That's it — the board starts with every eligible station "possible".

## 3. Ask a question (the core loop)

Each time you ask the hider a question and get an answer, log it here so the app
can eliminate stations.

1. Go to the **Ask** tab.
2. **Type** — pick a category: Radar, Thermometer, Matching, Measuring, Inside,
   or Photo. Matching/Measuring then show a second dropdown for the specific
   question (e.g. county, city, airport, line, name length).
3. Read the **blurb** — it explains the question and shows the **hider's card
   reward**, e.g. `(draw 2, keep 1)`. This number updates live (see §5).
4. Fill in the parameters:
   - **Radar** — choose a radius (or Custom…), then set the **center**: click the
     map and press **Use last click**, or paste `lat, lon` and press **Set**.
   - **Thermometer** — set **Start A** and **End B** (the two points you traveled
     between), same click-or-paste pickers.
   - **Measuring (airport)** / **Radar** use your location as a point; **Measuring
     (sea level)** and **Matching (name length)** take a number; the other
     **Matching** questions take a dropdown value.
   - **Inside** — type the building and floor.
5. Record the hider's answer (Yes/No, Hotter/Colder, Closer/Further, …).
6. (Optional) add a **Note**.
7. Press **Log question & eliminate**. The app applies the filter and the
   "possible" count drops. You'll land on the **History** tab.

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

Tick **satellite** in the top bar to overlay aerial imagery, clipped to the
play-area counties (land + bay; ocean and the Farallon Islands are excluded).
Road and place names are drawn on top so streets stay readable. The **Legend**
tab lists the imagery source and per-county capture dates.

## 7. Suspects — work the candidate list

The **Suspects** tab is the text list of stations, split into still-possible and
eliminated.

- **Search** — filter by name, alias, system, line, city, or county.
- **Sort** — by name, or grouped by agency → line.
- **★** stars a station (pins it to the top) — handy for ones you're watching.
- **✕** eliminates a station by hand (e.g. you ruled it out by reasoning the app
  can't); **↩** restores it.
- Clicking a station **name** flies the map to it.

## 8. Endgame

When you're down to one suspected station, open its popup on the map and choose
**🎯 Endgame here**. The board collapses to that station and draws its **hiding
zone** — the circle the hider must be within for the endgame — shading everything
outside it. A banner shows the station and the zone radius. Choose **Exit
endgame** (popup or banner) to go back to the full board.

## 9. The map toolbox (drawing tools)

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

## 10. Tips

- Log questions in the order you ask them; the repeat-cost multiplier counts in
  ask order.
- Use **Disable** instead of Delete if you suspect you mis-entered an answer and
  want to compare the board with/without it.
- **Reset** wipes everything — only use it to start a brand-new game.
