import type { GameState, QuestionRecord, Station } from '../types'
import { applyFilters } from './elimination'
import { defaultHidingRadiusMi } from './hidingZone'

export const REVIEW_CUTOFF_MIN = { small: 35, medium: 65, large: 270 } as const

export type TimelineEvent =
  | { kind: 'question'; at: number; record: QuestionRecord; left: number; before: number; keptHider: boolean | null }
  | { kind: 'out' | 'back'; at: number; stationId: string; left: number; before: number; keptHider: boolean | null }

// Questions the review counts: ticked in cleanup and not vetoed. Unticking only
// changes the review copy, never the saved game.
export function countedQuestions(game: GameState, excluded: Set<string>): QuestionRecord[] {
  return game.questions.filter((q) => !excluded.has(q.id) && !q.vetoed)
}

// Stations the seekers still believed possible at time t: every counted answer
// logged by then and every hand cross-out in force then (outAt <= t < backAt).
export function remainingAt(
  base: Station[],
  game: GameState,
  questions: QuestionRecord[],
  t: number,
): Station[] {
  const records = questions.filter((q) => q.createdAt <= t).map((q) => ({ ...q, active: true }))
  const out = new Set(
    game.eliminationLog.filter((m) => m.outAt <= t && (m.backAt === undefined || m.backAt > t)).map((m) => m.stationId),
  )
  return applyFilters(base, records, defaultHidingRadiusMi(game.gameSize)).remaining.filter((s) => !out.has(s.id))
}

// One row per logged question, hand cross-out and put-back, oldest first, with
// how many stations were left before and after it.
export function buildTimeline(
  base: Station[],
  game: GameState,
  excluded: Set<string>,
  hiderStation?: string,
): TimelineEvent[] {
  const questions = countedQuestions(game, excluded)
  type Raw = { at: number; order: number } & (
    | { kind: 'question'; record: QuestionRecord }
    | { kind: 'out' | 'back'; stationId: string }
  )
  const raw: Raw[] = []
  questions.forEach((q, i) => raw.push({ kind: 'question', at: q.createdAt, order: i, record: q }))
  game.eliminationLog.forEach((m, i) => {
    raw.push({ kind: 'out', at: m.outAt, order: 10_000 + i, stationId: m.stationId })
    if (m.backAt !== undefined) raw.push({ kind: 'back', at: m.backAt, order: 20_000 + i, stationId: m.stationId })
  })
  raw.sort((a, b) => a.at - b.at || a.order - b.order)
  const has = (list: Station[]) => (hiderStation ? list.some((s) => s.id === hiderStation) : null)
  let prev = raw.length ? remainingAt(base, game, questions, raw[0].at - 1) : base
  const events: TimelineEvent[] = []
  for (let i = 0; i < raw.length; i++) {
    const r = raw[i]
    // rows at the same instant (a line cross-out) share one count after the last
    const nextAt = raw[i + 1]?.at
    const now = nextAt === r.at ? null : remainingAt(base, game, questions, r.at)
    const after = now ?? prev
    const common = { at: r.at, before: prev.length, left: after.length, keptHider: now ? has(now) : null }
    if (r.kind === 'question') events.push({ ...common, kind: 'question', record: r.record })
    else events.push({ ...common, kind: r.kind, stationId: r.stationId })
    if (now) prev = now
  }
  return events
}
