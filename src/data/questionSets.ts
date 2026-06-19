import type { QuestionKind } from '../types'

/**
 * Per-game-size question sets for Jet Lag: Hide & Seek.
 *
 * Single source of truth: every card is tagged with the game sizes it belongs
 * to. Derive a concrete deck with `questionsForSize(size)`.
 *
 * Source: the (fan-made) Investigation Book + Quick Start guide at
 * https://www.lifack.ch (read June 2026). This is NOT the official rulebook;
 * andrew will reconcile against the original rulebook later (see the reminder in
 * the deck-building todo). Per-size availability is taken from the Investigation
 * Book's size labels:
 *   - Matching & Measuring list no size labels → every subject is available in
 *     all sizes.
 *   - Radar distances are all labelled "All Games".
 *   - Thermometer, Tentacles, and Photo carry explicit "All Games /
 *     Add for Medium & Large / Add for Large" labels, encoded below.
 *
 * `appKind` is set when the Bay Area seeker tool can already auto-eliminate for
 * that card (maps to `QuestionKind`); `undefined` means it still needs geodata /
 * wiring. This doubles as a roadmap of what's left to implement.
 */

export type GameSize = 'small' | 'medium' | 'large'

export const GAME_SIZES: GameSize[] = ['small', 'medium', 'large']

/** Cards the hider draws / keeps per category (constant across sizes). */
export const DRAW_KEEP = {
  Matching: { draw: 3, keep: 1 },
  Measuring: { draw: 3, keep: 1 },
  Radar: { draw: 2, keep: 1 },
  Thermometer: { draw: 2, keep: 1 },
  Tentacles: { draw: 4, keep: 2 },
  Photo: { draw: 1, keep: 1 },
} as const

/** Minutes the hider has to answer a non-photo question (all sizes). */
export const ANSWER_WINDOW_MIN = 5

/** Round/setup parameters per size (from the Quick Start guide). */
export const SIZE_PARAMS: Record<GameSize, {
  hidingPeriodMin: number
  hidingZoneRadiusMi: number
  photoAnswerWindowMin: number
}> = {
  small: { hidingPeriodMin: 30, hidingZoneRadiusMi: 0.25, photoAnswerWindowMin: 10 },
  medium: { hidingPeriodMin: 60, hidingZoneRadiusMi: 0.25, photoAnswerWindowMin: 10 },
  large: { hidingPeriodMin: 180, hidingZoneRadiusMi: 0.5, photoAnswerWindowMin: 20 },
}

const ALL: GameSize[] = ['small', 'medium', 'large']
const ML: GameSize[] = ['medium', 'large']
const L: GameSize[] = ['large']

// ---------------------------------------------------------------------------
// Matching — "Is your nearest ___ the same as my nearest ___?" → Yes / No
// Every subject is available in all game sizes (no size labels in the book).
// ---------------------------------------------------------------------------
export interface SubjectCard {
  subject: string
  group: 'Transit' | 'Administrative Divisions' | 'Borders' | 'Natural' | 'Places of Interest' | 'Public Utilities'
  note?: string
  sizes: GameSize[]
  /** set when the app can auto-eliminate for this card */
  appKind?: QuestionKind
}

export const MATCHING: SubjectCard[] = [
  { subject: 'Commercial Airport', group: 'Transit', note: 'nearest airport with scheduled passenger flights', sizes: ALL, appKind: 'match-airport' },
  { subject: 'Transit Line', group: 'Transit', note: 'the line your closest station sits on (ask while riding)', sizes: ALL, appKind: 'match-line' },
  { subject: "Station's Name Length", group: 'Transit', note: 'same character count', sizes: ALL, appKind: 'match-namelength' },
  { subject: 'Street or Path', group: 'Transit', note: 'the named street/path you are on', sizes: ALL },
  { subject: '1st Admin. Division', group: 'Administrative Divisions', note: 'state', sizes: ALL },
  { subject: '2nd Admin. Division', group: 'Administrative Divisions', note: 'county', sizes: ALL, appKind: 'match-county' },
  { subject: '3rd Admin. Division', group: 'Administrative Divisions', note: 'city / municipality', sizes: ALL, appKind: 'match-city' },
  { subject: '4th Admin. Division', group: 'Administrative Divisions', note: 'neighborhood / ward (where it exists)', sizes: ALL },
  { subject: 'Mountain', group: 'Natural', note: 'nearest named peak', sizes: ALL },
  { subject: 'Landmass', group: 'Natural', note: 'same contiguous landmass / island', sizes: ALL },
  { subject: 'Park', group: 'Natural', note: 'nearest park', sizes: ALL },
  { subject: 'Amusement Park', group: 'Places of Interest', note: 'nearest', sizes: ALL },
  { subject: 'Zoo', group: 'Places of Interest', note: 'nearest', sizes: ALL },
  { subject: 'Aquarium', group: 'Places of Interest', note: 'nearest', sizes: ALL },
  { subject: 'Golf Course', group: 'Places of Interest', note: 'nearest', sizes: ALL },
  { subject: 'Museum', group: 'Places of Interest', note: 'nearest', sizes: ALL },
  { subject: 'Movie Theater', group: 'Places of Interest', note: 'nearest', sizes: ALL },
  { subject: 'Hospital', group: 'Public Utilities', note: 'nearest', sizes: ALL },
  { subject: 'Library', group: 'Public Utilities', note: 'nearest', sizes: ALL },
  { subject: 'Foreign Consulate', group: 'Public Utilities', note: 'nearest', sizes: ALL },
]

// ---------------------------------------------------------------------------
// Measuring — "Compared to me, are you closer to or further from ___?"
// Every subject is available in all game sizes. (The lifack book lists only
// International / 1st / 2nd admin-division borders, but we keep 3rd/4th too.)
// ---------------------------------------------------------------------------
export const MEASURING: SubjectCard[] = [
  { subject: 'A Commercial Airport', group: 'Transit', note: 'distance to nearest airport', sizes: ALL, appKind: 'measure-airport' },
  { subject: 'A High Speed Train Line', group: 'Transit', note: 'distance to nearest HSR line', sizes: ALL },
  { subject: 'A Rail Station', group: 'Transit', note: 'distance to nearest station', sizes: ALL },
  { subject: 'An International Border', group: 'Borders', sizes: ALL },
  { subject: 'A 1st Admin. Div. Border', group: 'Borders', note: 'state line', sizes: ALL },
  { subject: 'A 2nd Admin. Div. Border', group: 'Borders', note: 'county line', sizes: ALL },
  { subject: 'A 3rd Admin. Div. Border', group: 'Borders', note: 'city line', sizes: ALL },
  { subject: 'A 4th Admin. Div. Border', group: 'Borders', note: 'neighborhood line (where it exists)', sizes: ALL },
  { subject: 'Sea Level', group: 'Natural', note: 'higher vs lower elevation', sizes: ALL, appKind: 'measure-sealevel' },
  { subject: 'A Body of Water', group: 'Natural', note: 'nearest lake / bay / ocean', sizes: ALL },
  { subject: 'A Coastline', group: 'Natural', note: 'distance to the coast', sizes: ALL },
  { subject: 'A Mountain', group: 'Natural', note: 'nearest peak', sizes: ALL },
  { subject: 'A Park', group: 'Natural', note: 'nearest park', sizes: ALL },
  { subject: 'An Amusement Park', group: 'Places of Interest', note: 'nearest', sizes: ALL },
  { subject: 'A Zoo', group: 'Places of Interest', note: 'nearest', sizes: ALL },
  { subject: 'An Aquarium', group: 'Places of Interest', note: 'nearest', sizes: ALL },
  { subject: 'A Golf Course', group: 'Places of Interest', note: 'nearest', sizes: ALL },
  { subject: 'A Museum', group: 'Places of Interest', note: 'nearest', sizes: ALL },
  { subject: 'A Movie Theater', group: 'Places of Interest', note: 'nearest', sizes: ALL },
  { subject: 'A Hospital', group: 'Public Utilities', note: 'nearest', sizes: ALL },
  { subject: 'A Library', group: 'Public Utilities', note: 'nearest', sizes: ALL },
  { subject: 'A Foreign Consulate', group: 'Public Utilities', note: 'nearest', sizes: ALL },
]

// ---------------------------------------------------------------------------
// Radar — "Are you within ___ of me?" → Yes / No. All distances: All Games.
// ---------------------------------------------------------------------------
export interface ScaleCard {
  /** radius / travel distance in miles */
  miles: number
  sizes: GameSize[]
}

export const RADAR: ScaleCard[] = [
  { miles: 0.25, sizes: ALL },
  { miles: 0.5, sizes: ALL },
  { miles: 1, sizes: ALL },
  { miles: 3, sizes: ALL },
  { miles: 5, sizes: ALL },
  { miles: 10, sizes: ALL },
  { miles: 25, sizes: ALL },
  { miles: 50, sizes: ALL },
  { miles: 100, sizes: ALL },
]

/** A custom radar radius ("CHOOSE") may be selected once per game. */
export const RADAR_CUSTOM = { allowed: true, perGame: 1, sizes: ALL }

// ---------------------------------------------------------------------------
// Thermometer — "I've just traveled (at least) ___. Am I hotter or colder?"
// ---------------------------------------------------------------------------
export const THERMOMETER: ScaleCard[] = [
  { miles: 0.5, sizes: ALL },
  { miles: 3, sizes: ALL },
  { miles: 10, sizes: ML },
  { miles: 50, sizes: L },
]

// ---------------------------------------------------------------------------
// Tentacles — "Of all the ___ within ___ of me, which are you closest to?"
// (Not available in small games.)
// ---------------------------------------------------------------------------
export interface TentacleCard {
  radiusMi: number
  poiTypes: string[]
  sizes: GameSize[]
}

export const TENTACLES: TentacleCard[] = [
  { radiusMi: 1, poiTypes: ['Museums', 'Libraries', 'Movie Theaters', 'Hospitals'], sizes: ML },
  { radiusMi: 15, poiTypes: ['Metro Lines', 'Zoos', 'Aquariums', 'Amusement Parks'], sizes: L },
]

// ---------------------------------------------------------------------------
// Photo — "Send a photo of ___." Draw 1. Answer window: S/M 10 min, L 20 min.
// Requirement text is verbatim from the cards.
// ---------------------------------------------------------------------------
export interface PhotoCard {
  title: string
  requirement: string
  sizes: GameSize[]
  /** true if the condition can be impossible to fulfil during the end game */
  endgameBlocked?: boolean
}

export const PHOTO: PhotoCard[] = [
  // All Games
  { title: 'A Tree', requirement: 'Must include the entire tree.', sizes: ALL },
  { title: 'The Sky', requirement: 'Place phone on ground, shoot directly up, no zoom.', sizes: ALL },
  { title: 'You', requirement: 'Selfie mode, perpendicular to ground, arm extended, default lens, no zoom.', sizes: ALL },
  { title: 'Widest Street', requirement: 'Must include both sides of the street; background not required.', sizes: ALL },
  { title: 'Tallest Structure in Your Sightline', requirement: 'Tallest building from your perspective (not objectively tallest). Include top and both sides; top in the top 1/3 of the frame.', sizes: ALL },
  { title: 'Any Building Visible from Station', requirement: 'Stand directly outside a station entrance (pick one if several). Include roof and both sides; top of building in the top 1/3 of the frame.', sizes: ALL, endgameBlocked: true },
  // Add for Medium & Large
  { title: 'Tallest Building Visible from Station', requirement: 'As above, standing directly outside a station entrance. The station itself can\u2019t count unless unrelated (e.g. MetLife building atop Grand Central).', sizes: ML, endgameBlocked: true },
  { title: 'Trace Nearest Street/Path', requirement: 'Street/path must be visible on a mapping app; trace intersection to intersection (photo-editing app or trace on paper).', sizes: ML },
  { title: 'Two Buildings', requirement: 'Bottom up to four stories.', sizes: ML },
  { title: 'Restaurant Interior', requirement: 'No zoom. Take the picture through the window from outside.', sizes: ML, endgameBlocked: true },
  { title: 'Train Platform', requirement: "5'\u00d75' section with 3 distinct elements.", sizes: ML, endgameBlocked: true },
  { title: 'Park', requirement: 'No zoom, perpendicular to ground. Must stand 5 feet from any obstruction.', sizes: ML, endgameBlocked: true },
  { title: 'Grocery Store Aisle', requirement: 'No zoom. Stand at the end of the aisle, shoot directly down.', sizes: ML, endgameBlocked: true },
  { title: 'Place of Worship', requirement: "5'\u00d75' section with 3 distinct elements (litmus test: could someone match it by visiting the spot?).", sizes: ML, endgameBlocked: true },
  // Add for Large
  { title: '\u00bd Mile of Streets Traced', requirement: 'Must be continuous, include 5 turns, with no doubling back. Send north-south oriented. Streets must appear on a mapping app. (Trace by blacking out everything but the street in a photo-editing app, or by tracing over the phone on paper.)', sizes: L },
  { title: 'Tallest Mountain Visible from Station', requirement: 'Tallest from your perspective/sightline — a nearby mountain that looks taller beats a distant taller one (e.g. a far-off Everest). Max 3x zoom; top of mountain in the top 1/3 of the frame.', sizes: L, endgameBlocked: true },
  { title: 'Biggest Body of Water in Your Zone', requirement: 'Max 3x zoom. Must include both sides of the body of water or the horizon. A body of water visible from but not touching the zone does not count; if a large body only partially touches the zone, it still counts as the largest even when its in-zone portion is smaller than another body fully inside the zone.', sizes: L },
  { title: 'Five Buildings', requirement: 'Must include bottom and up to four stories.', sizes: L },
]

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
const inSize = <T extends { sizes: GameSize[] }>(arr: T[], size: GameSize): T[] =>
  arr.filter((c) => c.sizes.includes(size))

export interface QuestionSet {
  size: GameSize
  params: (typeof SIZE_PARAMS)[GameSize]
  matching: SubjectCard[]
  measuring: SubjectCard[]
  radar: ScaleCard[]
  thermometer: ScaleCard[]
  tentacles: TentacleCard[]
  photo: PhotoCard[]
}

/** The exact deck (all 6 categories) for a given game size. */
export function questionsForSize(size: GameSize): QuestionSet {
  return {
    size,
    params: SIZE_PARAMS[size],
    matching: inSize(MATCHING, size),
    measuring: inSize(MEASURING, size),
    radar: inSize(RADAR, size),
    thermometer: inSize(THERMOMETER, size),
    tentacles: inSize(TENTACLES, size),
    photo: inSize(PHOTO, size),
  }
}

export const QUESTION_SETS: Record<GameSize, QuestionSet> = {
  small: questionsForSize('small'),
  medium: questionsForSize('medium'),
  large: questionsForSize('large'),
}

// ---------------------------------------------------------------------------
// Size selection (so the map's size is suggested automatically, not chosen by a
// person). Official criteria — Quick Start → Choosing a Transit System:
//   SMALL  : 30 – 100 stations   | 10 – 100 sq. miles
//   MEDIUM : 100 – 500 stations  | 100 – 1,000 sq. miles
//   LARGE  : 500+ stations       | 1,000+ sq. miles
// The ranges overlap at the round numbers; we treat 100 / 500 as the station
// boundaries and 100 / 1,000 as the area boundaries.
// ---------------------------------------------------------------------------
export const SIZE_STATION_THRESHOLDS = { smallMax: 100, mediumMax: 500 }
export const SIZE_AREA_THRESHOLDS = { smallMaxSqMi: 100, mediumMaxSqMi: 1000 }

export function sizeForStationCount(stationCount: number): GameSize {
  if (stationCount <= SIZE_STATION_THRESHOLDS.smallMax) return 'small'
  if (stationCount <= SIZE_STATION_THRESHOLDS.mediumMax) return 'medium'
  return 'large'
}

export function sizeForAreaSqMi(areaSqMi: number): GameSize {
  if (areaSqMi <= SIZE_AREA_THRESHOLDS.smallMaxSqMi) return 'small'
  if (areaSqMi <= SIZE_AREA_THRESHOLDS.mediumMaxSqMi) return 'medium'
  return 'large'
}

/**
 * Suggest a size from both signals (station count + area). When they disagree,
 * prefer the larger — a map with many stations or a wide footprint plays better
 * with the bigger ruleset. Returns each signal so the UI can show its reasoning.
 */
export function suggestGameSize(stationCount: number, areaSqMi?: number): {
  size: GameSize
  byStations: GameSize
  byArea?: GameSize
} {
  const byStations = sizeForStationCount(stationCount)
  if (areaSqMi == null) return { size: byStations, byStations }
  const byArea = sizeForAreaSqMi(areaSqMi)
  const rank: Record<GameSize, number> = { small: 0, medium: 1, large: 2 }
  const size = rank[byStations] >= rank[byArea] ? byStations : byArea
  return { size, byStations, byArea }
}

// ---------------------------------------------------------------------------
// Station eligibility by service frequency (a game restriction, not a seeker
// toggle). A station is only a valid hiding spot if it's served by at least one
// train per hour — a typical midday headway of 60 min or less. This is the
// canonical Jet Lag rule: their largest game (Japan, ~8,500 stations) still
// required "served by at least one train an hour," so the cutoff does NOT loosen
// for large maps — it's flat across all sizes.
//
// TODO (sparse maps): a small/rural map may not have enough stations served this
// often. When we add the first such map, relax the cap automatically (60 → 90 →
// 120 → none) until at least a small game's minimum (~30) stations qualify. The
// Bay Area never triggers this (247 qualify at ≤60), so it's deferred for now.
// ---------------------------------------------------------------------------
export const ELIGIBLE_HEADWAY_MIN = 60

/** True if a station's midday headway (min) is frequent enough to hide at. */
export function isHeadwayEligible(headwayMin: number): boolean {
  return headwayMin <= ELIGIBLE_HEADWAY_MIN
}
