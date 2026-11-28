import { describe, expect, it } from 'vitest'
import { emptyGame } from './storage'
import { buildTimeline, remainingAt } from './reviewTimeline'
import type { GameState, QuestionRecord, Station } from '../types'

const st = (id: string): Station => ({ id, name: id, lat: 37.8, lon: -122.27 }) as unknown as Station
const base = ['a', 'b', 'c', 'd'].map(st)
const photo: QuestionRecord = {
  id: 'q1', kind: 'photo', createdAt: 150, params: {}, note: '', eliminates: false, active: true, vetoed: false,
} as unknown as QuestionRecord
const game: GameState = {
  ...emptyGame,
  questions: [photo],
  eliminationLog: [
    { stationId: 'a', outAt: 100 },
    { stationId: 'b', outAt: 100, backAt: 300 },
    { stationId: 'c', outAt: 200 },
  ],
}

describe('review timeline', () => {
  it('uses what was believed at each time', () => {
    const ids = (t: number) => remainingAt(base, game, game.questions, t).map((s) => s.id)
    expect(ids(99)).toEqual(['a', 'b', 'c', 'd'])
    expect(ids(100)).toEqual(['c', 'd'])
    expect(ids(250)).toEqual(['d'])
    expect(ids(300)).toEqual(['b', 'd'])
  })

  it('lists rows oldest first with counts, sharing one count for same-time cross-outs', () => {
    const rows = buildTimeline(base, game, new Set(), 'c')
    expect(rows.map((r) => [r.kind, r.at, r.before, r.left])).toEqual([
      ['out', 100, 4, 4],
      ['out', 100, 4, 2],
      ['question', 150, 2, 2],
      ['out', 200, 2, 1],
      ['back', 300, 1, 2],
    ])
    expect(rows[3].keptHider).toBe(false)
    expect(rows[2].keptHider).toBe(true)
  })

  it('drops unticked questions', () => {
    expect(buildTimeline(base, game, new Set(['q1']))).toHaveLength(4)
  })
})
