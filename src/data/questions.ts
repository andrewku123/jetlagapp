import type { QuestionKind } from '../types'
import { haversineMiles } from '../lib/geo'
import { AIRPORTS, MAP_STATES } from './regions'

// The airports the active map actually contains, in the order they're declared,
// so the blurb names the ones a seeker can reach on this map (and nothing at all
// on a map with none) rather than a fixed list.
const AIRPORT_CODES = Object.keys(AIRPORTS).join('/')

// State Matching never eliminates (no station carries a state), but *why* differs:
// on a single-state map the answer is always yes, while a map spanning a state
// line would be answerable if the app had the data. Say whichever is true.
const ADMIN1_REASON =
  MAP_STATES.length === 1
    ? `every station in this play area is in ${MAP_STATES[0]}, so this can never eliminate`
    : 'the app has no per-station state data, so this eliminates nothing'

export const RADAR_OPTIONS = [0.25, 0.5, 1, 3, 5, 10, 25, 50, 100]
// Medium game thermometer travel distances (informational; elimination uses the
// from/to points the seeker records).
export const THERMOMETER_OPTIONS = [0.5, 3, 10]

export interface QuestionMeta {
  kind: QuestionKind
  category: 'Radar' | 'Thermometer' | 'Matching' | 'Measuring' | 'Tentacles' | 'Inside' | 'Photo'
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
  // --- Matching · Transit ---
  {
    kind: 'match-airport',
    category: 'Matching',
    label: 'Matching — Nearest commercial airport',
    cards: 'draw 3, keep 1',
    eliminates: true,
    blurb: AIRPORT_CODES
      ? `Is your nearest commercial airport (${AIRPORT_CODES}) the same as mine?`
      : 'Is your nearest commercial airport the same as mine?',
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
    kind: 'match-street',
    category: 'Matching',
    label: 'Matching — Street or path (log only)',
    cards: 'draw 3, keep 1',
    eliminates: false,
    blurb: 'Is the street or path you are on the same as mine? Log only — the app has no per-station street data, so this is recorded for your reference and eliminates nothing.',
  },
  // --- Matching · Administrative divisions ---
  {
    kind: 'match-admin1',
    category: 'Matching',
    label: 'Matching — State · 1st admin (log only)',
    cards: 'draw 3, keep 1',
    eliminates: false,
    blurb: `Is your state (1st admin division) the same as mine? Log only — ${ADMIN1_REASON}; recorded for your reference.`,
  },
  {
    kind: 'match-county',
    category: 'Matching',
    label: 'Matching — County · 2nd admin',
    cards: 'draw 3, keep 1',
    eliminates: true,
    blurb: 'Is your county the same as mine?',
  },
  {
    kind: 'match-city',
    category: 'Matching',
    label: 'Matching — City · 3rd admin',
    cards: 'draw 3, keep 1',
    eliminates: true,
    blurb: 'Is your municipality the same as mine?',
  },
  {
    kind: 'match-admin4',
    category: 'Matching',
    label: 'Matching — Neighborhood · 4th admin (log only)',
    cards: 'draw 3, keep 1',
    eliminates: false,
    blurb: 'Is your neighborhood (4th admin division) the same as mine? Log only — there is no consistent neighborhood dataset, so this is recorded for your reference and eliminates nothing.',
  },
  // --- Matching · Natural / Places of Interest / Public Utilities (expands per POI category) ---
  {
    kind: 'match-poi',
    category: 'Matching',
    label: 'Matching — Nearest place (park, museum, hospital…)',
    cards: 'draw 3, keep 1',
    eliminates: true,
    blurb: 'Is your nearest place of the chosen type the same as mine? Set your location; the app shows which place it treats as nearest.',
  },
  {
    kind: 'match-landmass',
    category: 'Matching',
    label: 'Matching — Landmass (log only)',
    cards: 'draw 3, keep 1',
    eliminates: false,
    blurb: 'Are you on the same landmass as me? Log only — the whole play area is one connected landmass, so this is always “same”; recorded for your reference.',
  },
  // --- Measuring · Transit ---
  {
    kind: 'measure-airport',
    category: 'Measuring',
    label: 'Measuring — Commercial airport',
    cards: 'draw 3, keep 1',
    eliminates: true,
    blurb: 'Compared to me, are you closer to or further from a commercial airport?',
  },
  {
    kind: 'measure-hsr',
    category: 'Measuring',
    label: 'Measuring — High-speed train line (log only)',
    cards: 'draw 3, keep 1',
    eliminates: false,
    blurb: 'Compared to me, are you closer to or further from a high-speed train line? Log only — there is no high-speed rail in the play area, so this is recorded for your reference and eliminates nothing.',
  },
  {
    kind: 'measure-railstation',
    category: 'Measuring',
    label: 'Measuring — Rail station (endgame)',
    cards: 'draw 3, keep 1',
    eliminates: true,
    blurb: 'Compared to me, are you closer to or further from the nearest rail station? Inert in the first half — every hiding station is itself a rail station (distance 0), so nothing is eliminated — but useful in the endgame, where it carves the hiding zone. Set your location; the app shows your distance to the nearest station.',
  },
  // --- Measuring · Borders / coastline (expands per feature) ---
  {
    kind: 'measure-feature',
    category: 'Measuring',
    label: 'Measuring — Border / coastline',
    cards: 'draw 3, keep 1',
    eliminates: true,
    blurb: 'Compared to me, are you closer to or further from the chosen coastline / border? Set your location; the app shows your distance to the nearest one.',
  },
  // --- Measuring · Natural ---
  {
    kind: 'measure-zip',
    category: 'Measuring',
    label: 'Measuring — ZIP code (smaller / larger)',
    cards: 'draw 3, keep 1',
    eliminates: true,
    blurb: 'Is your current ZIP code smaller or larger than mine? Set your location; the app shows your ZIP. Ties go to “smaller” (if your ZIP equals mine, you answer smaller).',
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
    kind: 'measure-water',
    category: 'Measuring',
    label: 'Measuring — Body of water (log only)',
    cards: 'draw 3, keep 1',
    eliminates: false,
    blurb: 'Compared to me, are you closer to or further from a body of water (lake, river, or bay)? Log only — inland water geometry is not loaded yet, so this is recorded for your reference and eliminates nothing.',
  },
  {
    kind: 'measure-poi',
    category: 'Measuring',
    label: 'Measuring — Nearest place (park, museum, hospital…)',
    cards: 'draw 3, keep 1',
    eliminates: true,
    blurb: 'Compared to me, are you closer to or further from your nearest place of the chosen type? Set your location; the app shows your distance to it.',
  },
  // --- Tentacles (expands per POI category; not available in small games) ---
  {
    kind: 'tentacle',
    category: 'Tentacles',
    label: 'Tentacles — nearest place within a radius',
    cards: 'draw 4, keep 2',
    eliminates: true,
    blurb: 'Of all the places of the chosen type within the fixed radius of me, which one are you closest to? Set your location; the app lists the in-range places — pick the one I answer. Places outside the radius don’t count even if they’re closer to you.',
  },
  {
    kind: 'tentacle-line',
    category: 'Tentacles',
    label: 'Tentacles — nearest metro line within 15 mi',
    cards: 'draw 4, keep 2',
    eliminates: true,
    blurb: 'Of all the metro lines within 15 mi of me, which one are you closest to? Set your location; the app lists the in-range colored lines — pick the one I answer. Lines that don’t pass within 15 mi don’t count even if they’re closer to you. Large games only.',
  },
  {
    kind: 'temperature',
    category: 'Measuring',
    label: 'Measuring — Temperature (log only)',
    cards: 'draw 3, keep 1',
    eliminates: false,
    blurb: 'Is your current temperature higher or lower than mine? Both players read a reputable weather app for their own location (use one agreed source, e.g. Google weather, to avoid app-vs-app disputes). Log only — weather is time-dependent and non-reproducible, so this eliminates nothing.',
  },
  {
    kind: 'inside-floor',
    category: 'Inside',
    label: 'Inside — floor in a building (log only)',
    cards: 'draw 3, keep 1',
    eliminates: false,
    blurb: 'Endgame only. “I’m inside [building] on [floor] — are you on a higher or lower floor?” You reveal the building AND your floor. Answer Higher / Lower / Same / Can’t answer (different building or outside). Logged for reference; does not auto-eliminate stations.',
  },
  {
    kind: 'traffic',
    category: 'Inside',
    label: 'Inside — Traffic (foot count, log only)',
    cards: 'draw 2, keep 1',
    eliminates: false,
    blurb: 'Both players must be indoors (can’t answer if you’re outside). Count everyone who passes within 15 feet of you over the next 5 minutes, by any method, as accurately as you can. Report to 2 significant figures (e.g. 137 → 140). Start the timer as soon as the seekers ask; report right after it ends. Log only — a crowd-density hint for the seeker; eliminates nothing.',
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
  // Each tentacle category (e.g. museums-within-1mi) is its own question.
  if (kind === 'tentacle') return `tentacle:${String(params.poiCat)}`
  // The metro-lines tentacle is a single question regardless of which line is answered.
  if (kind === 'tentacle-line') return 'tentacle-line'
  // Each photo card is its own question, so asking two different photos does not
  // stack the repeat-reward multiplier; only re-asking the same photo does.
  if (kind === 'photo') return `photo:${String(params.photoTitle ?? '')}`
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
