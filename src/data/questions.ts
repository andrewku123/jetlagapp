import type { QuestionKind } from '../types'

export const RADAR_OPTIONS = [0.25, 0.5, 1, 3, 5, 10, 25, 50, 100]
// Medium game thermometer travel distances (informational; elimination uses the
// from/to points the seeker records).
export const THERMOMETER_OPTIONS = [0.5, 3, 10]

export interface QuestionMeta {
  kind: QuestionKind
  category: 'Radar' | 'Thermometer' | 'Matching' | 'Measuring' | 'Inside' | 'Photo'
  label: string
  // cards the hider draws (medium game) — shown to the seeker as the cost
  cards: string
  // does it auto-eliminate stations on the map?
  eliminates: boolean
  blurb: string
}

// Only the medium-game-legal questions that the engine can auto-apply, plus a
// generic Photo logger. POI-based matching/measuring/tentacles are tracked
// separately as they require extra geodata.
export const QUESTION_CATALOG: QuestionMeta[] = [
  {
    kind: 'radar',
    category: 'Radar',
    label: 'Radar — within a distance',
    cards: 'draw 2, keep 1',
    eliminates: true,
    blurb: 'Are you within X of me? Eliminates everything inside (or outside) the circle.',
  },
  {
    kind: 'thermometer',
    category: 'Thermometer',
    label: 'Thermometer — hotter / colder',
    cards: 'draw 2, keep 1',
    eliminates: true,
    blurb: 'After traveling from A to B, am I hotter or colder? Keeps the half-plane.',
  },
  {
    kind: 'match-county',
    category: 'Matching',
    label: 'Matching — County (2nd admin division)',
    cards: 'draw 3, keep 1',
    eliminates: true,
    blurb: 'Is your county the same as mine?',
  },
  {
    kind: 'match-city',
    category: 'Matching',
    label: 'Matching — City (3rd admin division)',
    cards: 'draw 3, keep 1',
    eliminates: true,
    blurb: 'Is your municipality the same as mine?',
  },
  {
    kind: 'match-airport',
    category: 'Matching',
    label: 'Matching — Nearest commercial airport',
    cards: 'draw 3, keep 1',
    eliminates: true,
    blurb: 'Is your nearest commercial airport (SFO/OAK/SJC) the same as mine?',
  },
  {
    kind: 'match-line',
    category: 'Matching',
    label: 'Matching — Transit line (ask while riding)',
    cards: 'draw 3, keep 1',
    eliminates: true,
    blurb: 'Will the line I am riding stop at your station?',
  },
  {
    kind: 'match-namelength',
    category: 'Matching',
    label: 'Matching — Station name length',
    cards: 'draw 3, keep 1',
    eliminates: true,
    blurb: 'Is your station name the same number of characters as mine?',
  },
  {
    kind: 'measure-airport',
    category: 'Measuring',
    label: 'Measuring — Commercial airport',
    cards: 'draw 3, keep 1',
    eliminates: true,
    blurb: 'Compared to me, are you closer to or further from a commercial airport?',
  },
  {
    kind: 'measure-sealevel',
    category: 'Measuring',
    label: 'Measuring — Sea level (altitude)',
    cards: 'draw 3, keep 1',
    eliminates: true,
    blurb: 'Compared to me, are you closer to or further from sea level (lower altitude)?',
  },
  {
    kind: 'inside-floor',
    category: 'Inside',
    label: 'Inside — floor in a building (endgame)',
    cards: 'draw 3, keep 1',
    eliminates: false,
    blurb: 'Endgame only. “I’m inside [building] on [floor] — are you on a higher or lower floor?” You reveal the building AND your floor. Answer Higher / Lower / Same / Can’t answer (different building or outside). Logged for reference; does not auto-eliminate stations.',
  },
  {
    kind: 'photo',
    category: 'Photo',
    label: 'Photo — log only (no auto-eliminate)',
    cards: 'draw 1, keep 1',
    eliminates: false,
    blurb: 'Record a photo question + response for your own reference.',
  },
]
