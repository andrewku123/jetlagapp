import type { QuestionKind } from '../types'
import { haversineMiles } from '../lib/geo'

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

// Scale a "draw X, keep Y" reward string by a whole-number multiplier. The nth
// time the same question is asked, the hider's reward is multiplied by n.
// e.g. scaleCards('draw 2, keep 1', 2) === 'draw 4, keep 2'.
export function scaleCards(cards: string, mult: number): string {
  if (!Number.isFinite(mult) || mult <= 1) return cards
  return cards.replace(/\d+/g, (d) => String(Number(d) * mult))
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
    kind: 'match-poi',
    category: 'Matching',
    label: 'Matching — Nearest place (park, museum, hospital…)',
    cards: 'draw 3, keep 1',
    eliminates: true,
    blurb: 'Is your nearest place of the chosen type the same as mine? Set your location; the app shows which place it treats as nearest.',
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
    kind: 'measure-poi',
    category: 'Measuring',
    label: 'Measuring — Nearest place (park, museum, hospital…)',
    cards: 'draw 3, keep 1',
    eliminates: true,
    blurb: 'Compared to me, are you closer to or further from your nearest place of the chosen type? Set your location; the app shows your distance to it.',
  },
  {
    kind: 'measure-feature',
    category: 'Measuring',
    label: 'Measuring — Border / coastline',
    cards: 'draw 3, keep 1',
    eliminates: true,
    blurb: 'Compared to me, are you closer to or further from a coastline / county / state / international border? Set your location and pick which; the app shows your distance to the nearest one.',
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

export const QUESTION_BY_KIND: Record<QuestionKind, QuestionMeta> =
  Object.fromEntries(QUESTION_CATALOG.map((q) => [q.kind, q])) as Record<
    QuestionKind,
    QuestionMeta
  >

// The hider's reward for a question, scaled when it's the nth ask of that kind.
export function rewardForKind(kind: QuestionKind, askMult = 1): string {
  return scaleCards(QUESTION_BY_KIND[kind]?.cards ?? '', askMult)
}

// Key that decides whether two asks count as "the same question" for the repeat
// reward multiplier. Most kinds key on kind alone; radar and thermometer also key
// on their distance (a 5mi radar and a 10mi radar are different; two 5mi radars
// are the same). Thermometer travel distance is snapped to the nearest medium
// option so GPS jitter between two same-distance asks still groups them.
export function questionGroupKey(
  kind: QuestionKind,
  params: Record<string, unknown>,
): string {
  if (kind === 'radar') return `radar:${Number(params.radiusMiles)}`
  // POI match/measure of two different subjects (museum vs park) are different
  // questions; two asks of the same subject are the same question.
  if (kind === 'match-poi' || kind === 'measure-poi') {
    return `${kind}:${String(params.poiCat)}`
  }
  // Measuring a different linear feature (coastline vs county line) is a different
  // question; two asks of the same feature are the same question.
  if (kind === 'measure-feature') return `measure-feature:${String(params.feature)}`
  if (kind === 'thermometer') {
    // Prefer the thermometer the seeker explicitly chose; two asks with the same
    // chosen thermometer are "the same question". Fall back to inferring the
    // bucket from the recorded A→B travel distance for older logged questions.
    const chosen = Number(params.thermometerMiles)
    if (Number.isFinite(chosen) && chosen > 0) return `thermometer:${chosen}`
    const travel = haversineMiles(
      { lat: Number(params.fromLat), lon: Number(params.fromLon) },
      { lat: Number(params.toLat), lon: Number(params.toLon) },
    )
    if (!Number.isFinite(travel)) return 'thermometer'
    const bucket = THERMOMETER_OPTIONS.reduce((best, o) =>
      Math.abs(o - travel) < Math.abs(best - travel) ? o : best,
    )
    return `thermometer:${bucket}`
  }
  return kind
}
