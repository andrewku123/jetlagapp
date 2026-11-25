import { describe, it, expect } from 'vitest'
import { suggestionCandidates, suggestQuestionsSliced, rankSuggestions, SUGGEST_REGION_IDS, type Suggestion } from './questionSuggest'
import { applyFilters } from './elimination'
import { LOG_ONLY_KINDS, ENDGAME_ELIMINATES_KINDS } from '../data/regions'
import type { QuestionRecord, Station } from '../types'
import stationsJson from '../data/stations.json'

const STATIONS = stationsJson as unknown as Station[]
const ZONE = 0.25
// Downtown Oakland (12th St BART)
const OAK = { lat: 37.8037, lon: -122.2715 }

function runAll(stations: Station[], cands: ReturnType<typeof suggestionCandidates>): Promise<Suggestion[]> {
  return new Promise((resolve) => {
    suggestQuestionsSliced(stations, cands, ZONE, (ranked, done) => {
      if (done === cands.length) resolve(ranked)
    })
  })
}

describe('suggestionCandidates', () => {
  const cands = suggestionCandidates(OAK, 'medium', 'wd')

  it('offers only questions that can eliminate on this map, each with 2+ answers', () => {
    expect(cands.length).toBeGreaterThan(10)
    for (const c of cands) {
      expect(LOG_ONLY_KINDS.has(c.kind)).toBe(false)
      expect(ENDGAME_ELIMINATES_KINDS.has(c.kind)).toBe(false)
      expect(c.options.length).toBeGreaterThanOrEqual(2)
    }
    expect(new Set(cands.map((c) => c.id)).size).toBe(cands.length)
  })

  it('skips questions that need more than a location (thermometer, sea level, station name)', () => {
    const kinds = new Set(cands.map((c) => c.kind))
    for (const k of ['thermometer', 'measure-sealevel', 'match-namelength', 'photo'] as const) expect(kinds.has(k)).toBe(false)
    expect(kinds.has('radar')).toBe(true)
    expect(kinds.has('tentacle')).toBe(true)
  })

  it('is limited to Bay Area, SF Muni and LA', () => {
    expect([...SUGGEST_REGION_IDS].sort()).toEqual(['bayarea', 'la', 'sfmuni'])
  })
})

describe('suggestQuestionsSliced', () => {
  it('counts each answer exactly like logging it would', async () => {
    const cands = suggestionCandidates(OAK, 'medium', 'wd')
    const ranked = await runAll(STATIONS, cands)
    expect(ranked).toHaveLength(cands.length)
    for (const s of ranked) {
      const logged = s.options.map((o) => {
        const r: QuestionRecord = { id: 'q', kind: s.kind, createdAt: 0, params: o.params, eliminates: true, active: true, zoneMi: ZONE }
        return applyFilters(STATIONS, [r], ZONE).remaining.length
      })
      expect(s.counts, s.id).toEqual(logged)
      expect(s.worst).toBe(Math.max(...logged))
    }
  }, 60000)

  it('ranks by worst case, best first, and some question splits the board', async () => {
    const ranked = await runAll(STATIONS, suggestionCandidates(OAK, 'medium', 'wd'))
    for (let i = 1; i < ranked.length; i++) expect(ranked[i].worst).toBeGreaterThanOrEqual(ranked[i - 1].worst)
    expect(ranked[0].worst).toBeLessThan(STATIONS.length)
  }, 60000)

  it('reports an empty result for no stations', async () => {
    expect(await runAll([], suggestionCandidates(OAK, 'medium', 'wd'))).toEqual([])
  })

  it('cancels', async () => {
    let calls = 0
    const cancel = suggestQuestionsSliced(STATIONS, suggestionCandidates(OAK, 'medium', 'wd'), ZONE, () => calls++)
    cancel()
    await new Promise((r) => setTimeout(r, 50))
    expect(calls).toBe(0)
  })
})

describe('rankSuggestions', () => {
  const s = (id: string, counts: number[]): Suggestion => ({ id, kind: 'radar', params: {}, options: [], counts, worst: Math.max(...counts) })
  it('breaks worst-case ties by the more even spread', () => {
    const r = rankSuggestions([s('b', [60, 40]), s('a', [60, 60, 10]), s('c', [30, 70])])
    expect(r.map((x) => x.id)).toEqual(['b', 'a', 'c'])
  })
})
