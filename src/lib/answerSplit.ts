import type { DayType, QuestionKind, QuestionRecord, Station } from '../types'
import { applyFilters, stationPasses } from './elimination'
import { poiKey, poisWithinRadius, TENTACLE_INSIDE, TENTACLE_OUTSIDE } from './poi'
import { metroLinesWithinRadius } from './metroLines'

// "What would each answer leave?" — the seeker sets up a question, and before
// the hider replies the Ask form shows how many stations every possible answer
// keeps, so the seeker can pick the question that splits the field best.

export interface AnswerOption {
  // stable id for this answer within the question (the answer / value it sets)
  key: string
  label: string
  params: Record<string, unknown>
}

export interface AnswerOutcome extends AnswerOption {
  record: QuestionRecord
  keep: Station[]
}

const ANSWER_PAIRS: [string, string][] = [
  ['yes', 'no'],
  ['hotter', 'colder'],
  ['closer', 'further'],
  ['smaller', 'larger'],
]

const capitalize = (s: string) => s.charAt(0).toUpperCase() + s.slice(1)

// Every answer the hider could give to a question set up with `params` (the
// form's params, which carry the seeker's currently-picked answer, if any).
// Binary questions flip `answer`; tentacles list each in-range place (or line)
// plus the radar fallback. Returns [] when the question has no answer to split.
export function answerOptions(kind: QuestionKind, params: Record<string, unknown>): AnswerOption[] {
  if (kind === 'tentacle' || kind === 'tentacle-line') {
    const seeker = { lat: Number(params.fromLat), lon: Number(params.fromLon) }
    const radius = Number(params.radiusMi)
    if (!Number.isFinite(seeker.lat) || !Number.isFinite(seeker.lon) || !(radius > 0)) return []
    const base = { ...params }
    delete base.value
    delete base.poiName
    const radar = (inside: boolean): AnswerOption => {
      const value = inside ? TENTACLE_INSIDE : TENTACLE_OUTSIDE
      return { key: value, label: inside ? 'Within' : 'Not within', params: { ...base, value } }
    }
    const inPlay =
      kind === 'tentacle'
        ? poisWithinRadius(seeker, String(params.poiCat), radius).map((p) => ({ key: poiKey(p), label: p.name }))
        : metroLinesWithinRadius(seeker, radius, seeker.lat, params.day as DayType | undefined).map((l) => ({
            key: l.id,
            label: l.label,
          }))
    if (inPlay.length === 0) return []
    if (inPlay.length === 1) return [radar(true), radar(false)]
    return [
      ...inPlay.map((o) => ({ key: o.key, label: o.label, params: { ...base, value: o.key, poiName: o.label } })),
      radar(false),
    ]
  }
  const pair = ANSWER_PAIRS.find((p) => p.includes(String(params.answer)))
  if (!pair) return []
  return pair.map((a) => ({ key: a, label: capitalize(a), params: { ...params, answer: a } }))
}

// How many of `stations` survive each answer. `template` supplies the rest of
// the record (kind, zone, endgame flag); each option's params replace its own.
export function answerOutcomes(
  stations: Station[],
  template: Omit<QuestionRecord, 'params'>,
  options: AnswerOption[],
  fallbackZoneMi: number,
): AnswerOutcome[] {
  return options.map((o) => {
    const record: QuestionRecord = { ...template, params: o.params }
    return { ...o, record, keep: applyFilters(stations, [record], fallbackZoneMi).remaining }
  })
}

// answerOutcomes computed a few stations at a time, yielding between slices so
// slow questions (coastline, nearest park, metro-line tentacles over hundreds of
// stations) never freeze the form. Calls onDone with the same result as
// answerOutcomes; the returned function cancels the run.
export function answerOutcomesSliced(
  stations: Station[],
  template: Omit<QuestionRecord, 'params'>,
  options: AnswerOption[],
  fallbackZoneMi: number,
  onProgress: (done: number) => void,
  onDone: (outcomes: AnswerOutcome[]) => void,
  sliceMs = 12,
): () => void {
  const records: QuestionRecord[] = options.map((o) => ({ ...template, params: o.params }))
  const keeps: Station[][] = options.map(() => [])
  let i = 0
  let timer: ReturnType<typeof setTimeout> | null = null
  const step = () => {
    const t0 = performance.now()
    // at least one station per slice, so a slow station can't stall the run
    do {
      const st = stations[i++]
      if (!st) break
      records.forEach((r, k) => {
        if (stationPasses(st, r, fallbackZoneMi)) keeps[k].push(st)
      })
    } while (i < stations.length && performance.now() - t0 < sliceMs)
    if (i < stations.length) {
      onProgress(i)
      timer = setTimeout(step, 0)
      return
    }
    timer = null
    onDone(options.map((o, k) => ({ ...o, record: records[k], keep: keeps[k] })))
  }
  timer = setTimeout(step, 0)
  return () => {
    if (timer) clearTimeout(timer)
  }
}

// Stations the seeker is guaranteed to keep whatever the answer: the largest
// outcome. Smaller is better; an answer that keeps everything splits nothing.
export function worstCaseLeft(outcomes: AnswerOutcome[]): number {
  return outcomes.reduce((m, o) => Math.max(m, o.keep.length), 0)
}
