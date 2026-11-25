import type { DayType, LatLng, QuestionKind, QuestionRecord, Station } from '../types'
import type { GameSize } from '../data/questionSets'
import { QUESTION_CATALOG, RADAR_OPTIONS } from '../data/questions'
import { ACTIVE_REGION_ID, HAS_AIRPORTS, LOG_ONLY_KINDS, ENDGAME_ELIMINATES_KINDS, MULTI_STATE } from '../data/regions'
import { stationPasses } from './elimination'
import { answerOptions, type AnswerOption } from './answerSplit'
import { nearestAirport } from './airports'
import { countyAt } from './counties'
import { cityAt } from './cities'
import { stateAt } from './states'
import { zipAt } from './zip'
import { QUESTION_POI_CATEGORIES, POI_COUNTS, TENTACLE_CATEGORIES, nearestPoi, nearestPoiMiles } from './poi'
import { METRO_TENTACLE_RADIUS_MI } from './metroLines'
import { AVAILABLE_MEASURE_FEATURE_KEYS, featurePolylines, distanceToFeatureMiles } from './measureFeatures'

// "Which question should I ask from here?" — every eliminating question a seeker
// standing at one spot could ask, each counted like the answer-split preview
// (the real stationPasses per answer) and ranked by the worst case it leaves.
// Thermometer (needs a trip), sea level (needs the seeker's altitude) and the
// "your station" questions (name length, line) need input beyond a location, so
// they aren't suggested.

// Maps the prototype is on: Bay Area, SF Muni and LA (not DC or NYC yet).
export const SUGGEST_REGION_IDS: ReadonlySet<string> = new Set(['bayarea', 'sfmuni', 'la'])
export const SUGGEST_ON_THIS_MAP = SUGGEST_REGION_IDS.has(ACTIVE_REGION_ID)

export interface SuggestCandidate {
  // stable id: kind plus its subject (radius, category, feature)
  id: string
  kind: QuestionKind
  // the form's subject parameter: radar radius, POI / tentacle category, feature
  subject?: string
  params: Record<string, unknown>
  options: AnswerOption[]
}

export interface Suggestion extends SuggestCandidate {
  // stations each answer keeps, in `options` order
  counts: number[]
  worst: number
}

// A kind the active map lets eliminate outside the endgame (same demotions as
// the Ask form: log-only kinds, endgame-only county/city).
function askable(kind: QuestionKind): boolean {
  const meta = QUESTION_CATALOG.find((q) => q.kind === kind)
  return !!meta?.eliminates && !LOG_ONLY_KINDS.has(kind) && !ENDGAME_ELIMINATES_KINDS.has(kind)
}

// Every question askable from `at`, with the params the Ask form would log for
// it (one answer picked; answerOptions enumerates the rest). Questions with
// fewer than two possible answers are dropped.
export function suggestionCandidates(at: LatLng, gameSize: GameSize, dayType: DayType): SuggestCandidate[] {
  const from = { fromLat: at.lat, fromLon: at.lon }
  const out: SuggestCandidate[] = []
  const add = (kind: QuestionKind, params: Record<string, unknown>, subject?: string) => {
    if (!askable(kind)) return
    const options = answerOptions(kind, params)
    if (options.length < 2) return
    out.push({ id: subject ? `${kind}::${subject}` : kind, kind, subject, params, options })
  }

  for (const r of RADAR_OPTIONS) add('radar', { lat: at.lat, lon: at.lon, radiusMiles: r, answer: 'yes' }, String(r))

  if (HAS_AIRPORTS) {
    add('match-airport', { value: nearestAirport(at).code, ...from, answer: 'yes' })
    add('measure-airport', { ...from, answer: 'closer' })
  }
  add('measure-railstation', { ...from, answer: 'closer' })
  if (MULTI_STATE) {
    const st = stateAt(at)
    if (st) add('match-admin1', { value: st, ...from, answer: 'yes' })
  }
  const county = countyAt(at)
  if (county) add('match-county', { value: county, ...from, answer: 'yes' })
  const city = cityAt(at)
  if (city) add('match-city', { value: city, ...from, answer: 'yes' })
  const zip = zipAt(at)
  if (zip) add('measure-zip', { value: zip, ...from, answer: 'smaller' })

  for (const cat of QUESTION_POI_CATEGORIES) {
    const n = POI_COUNTS[cat] ?? 0
    const np = n > 1 ? nearestPoi(at, cat) : null
    if (np) add('match-poi', { poiCat: cat, ...from, poiName: np.name, answer: 'yes' }, cat)
    if (n > 0 && Number.isFinite(nearestPoiMiles(at, cat))) add('measure-poi', { poiCat: cat, ...from, answer: 'closer' }, cat)
  }
  for (const f of AVAILABLE_MEASURE_FEATURE_KEYS) {
    if (featurePolylines(f).length === 0 || !Number.isFinite(distanceToFeatureMiles(at, f))) continue
    add('measure-feature', { feature: f, ...from, answer: 'closer' }, f)
  }
  for (const tc of TENTACLE_CATEGORIES) {
    if (!tc.sizes.includes(gameSize)) continue
    add('tentacle', { poiCat: tc.key, radiusMi: tc.radiusMi, ...from }, tc.key)
  }
  if (gameSize === 'large') add('tentacle-line', { radiusMi: METRO_TENTACLE_RADIUS_MI, ...from, day: dayType })
  return out
}

// Best first: smallest worst case, then the smaller expected survivors (sum of
// squared counts) so a question with one bad answer among many good ones beats
// an even 50/50 of the same worst case only when it really is better on average.
export function rankSuggestions(list: Suggestion[]): Suggestion[] {
  const spread = (s: Suggestion) => s.counts.reduce((a, c) => a + c * c, 0)
  return [...list].sort((a, b) => a.worst - b.worst || spread(a) - spread(b) || a.id.localeCompare(b.id))
}

// Counts every candidate over `stations`, a few stations at a time so the form
// stays responsive, one question after another; onUpdate gets the ranked list
// so far after each finished question. Counting is stationPasses on the same
// record logging builds, so each count equals what logging that answer leaves.
// The returned function cancels the run.
export function suggestQuestionsSliced(
  stations: Station[],
  candidates: SuggestCandidate[],
  zoneMi: number,
  onUpdate: (ranked: Suggestion[], doneQuestions: number) => void,
  sliceMs = 12,
): () => void {
  const done: Suggestion[] = []
  let c = 0
  let i = 0
  let records: QuestionRecord[] = []
  let counts: number[] = []
  let timer: ReturnType<typeof setTimeout> | null = null
  const begin = () => {
    const cand = candidates[c]
    records = cand.options.map((o) => ({
      id: 'question-suggest',
      kind: cand.kind,
      createdAt: 0,
      params: o.params,
      eliminates: true,
      active: true,
      zoneMi,
    }))
    counts = cand.options.map(() => 0)
    i = 0
  }
  const step = () => {
    const t0 = performance.now()
    while (c < candidates.length) {
      // at least one station per slice, so a slow station can't stall the run
      do {
        const st = stations[i++]
        if (!st) break
        records.forEach((r, k) => {
          if (stationPasses(st, r, zoneMi)) counts[k]++
        })
      } while (i < stations.length && performance.now() - t0 < sliceMs)
      if (i < stations.length) break
      done.push({ ...candidates[c], counts, worst: Math.max(...counts) })
      c++
      onUpdate(rankSuggestions(done), c)
      if (c < candidates.length) begin()
      if (performance.now() - t0 >= sliceMs) break
    }
    timer = c < candidates.length ? setTimeout(step, 0) : null
  }
  if (candidates.length === 0 || stations.length === 0) {
    timer = setTimeout(() => onUpdate([], candidates.length), 0)
  } else {
    begin()
    timer = setTimeout(step, 0)
  }
  return () => {
    if (timer) clearTimeout(timer)
  }
}
