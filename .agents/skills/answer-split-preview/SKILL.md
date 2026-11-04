---
name: answer-split-preview
description: Work on the Ask form's "If the hider answers…" block — the per-answer survivor counts shown before a question is logged, the worst-case verdict, and the map preview of one answer's survivors. Use when changing how answers are enumerated, adding a question kind that should show a split, or changing the preview banner / map framing.
---

# Answer split preview

While a seeker sets up an eliminating question, `QuestionForm` shows one row per
possible answer with how many of the **current** suspects it would leave
(e.g. `Yes 12 left / No 128 left`), plus a verdict line
(`Worst case N left — cuts at least M`). Tapping a row previews that answer on the map.

## Pieces
- `src/lib/answerSplit.ts`
  - `answerOptions(kind, params)` enumerates answers. Binary kinds are found by
    the current `params.answer` value in `ANSWER_PAIRS` (yes/no, hotter/colder,
    closer/further, smaller/larger) — a new binary kind with a new answer word must
    be added there. Tentacles / metro-line tentacles list every in-range place
    (`poisWithinRadius` / `metroLinesWithinRadius`) plus "Not within"; a single
    in-range place collapses to Within / Not within, same as logging does.
  - `answerOutcomes` runs the real `applyFilters` per answer, so counts always
    match what logging that answer would do. Don't reimplement elimination here.
- `QuestionForm.tsx`: `splitParams` reuses `buildParams(false)` (the same params
  submit would log); tentacles build their params directly because
  `buildParams` needs the chosen place. Null for log-only kinds, invalid forms and
  endgame mode → block hidden. With >2 answers, impossible ones fold into one line.
- `App.tsx`: `outcomeKey` (selected row) + `outcome`; `mapBoard` swaps the map's
  remaining/eliminated/records for the preview while on the Ask tab. Picking a row
  closes the phone sheet; logging a question clears the preview.
- `MapView.tsx`: blue `.preview-banner` with Clear; `MapFit` frames the survivors
  when a preview opens (`previewKey`), and leaves the view alone on clear.

## Verify
`src/lib/answerSplit.test.ts` checks each outcome equals logging it via
`applyFilters`. On a preview: unlock the gate (localStorage `bahs.unlock`), open
`?map=<id>`, pick Radar, paste a center into "paste lat, lon" → Set, then tap a row.
