import { describe, it, expect } from 'vitest'
import { answerOptions, answerOutcomes, answerOutcomesSliced, worstCaseLeft } from './answerSplit'
import type { AnswerOutcome } from './answerSplit'
import { applyFilters } from './elimination'
import { TENTACLE_OUTSIDE, TENTACLE_INSIDE } from './poi'
import type { QuestionRecord, Station } from '../types'
import stationsJson from '../data/stations.json'

const STATIONS = stationsJson as unknown as Station[]
const ZONE = 0.25
const template = (kind: QuestionRecord['kind']): Omit<QuestionRecord, 'params'> => ({
  id: 'preview',
  kind,
  createdAt: 0,
  eliminates: true,
  active: true,
  zoneMi: ZONE,
})
// Downtown Oakland (12th St BART)
const OAK = { lat: 37.8037, lon: -122.2715 }

describe('answerOptions', () => {
  it('flips the binary answer whichever side the form has picked', () => {
    for (const [picked, other] of [['yes', 'no'], ['colder', 'hotter'], ['further', 'closer'], ['larger', 'smaller']]) {
      const keys = answerOptions('radar', { answer: picked }).map((o) => o.key)
      expect(keys).toContain(picked)
      expect(keys).toContain(other)
      expect(keys).toHaveLength(2)
    }
  })

  it('returns nothing for a question without an answer to split', () => {
    expect(answerOptions('photo', { photoTitle: 'x' })).toEqual([])
    expect(answerOptions('traffic', { value: 3 })).toEqual([])
  })

  it('lists every in-range tentacle place plus "not within", ignoring a picked answer', () => {
    const opts = answerOptions('tentacle', {
      poiCat: 'museum', radiusMi: 1, fromLat: OAK.lat, fromLon: OAK.lon, value: 'stale', poiName: 'stale',
    })
    expect(opts.length).toBeGreaterThan(2)
    expect(opts[opts.length - 1].key).toBe(TENTACLE_OUTSIDE)
    expect(opts.every((o) => o.params.value === o.key)).toBe(true)
  })

  it('treats a single in-range place as a within / not-within radar', () => {
    // far out in the play area, no museum within a tenth of a mile
    const opts = answerOptions('tentacle', { poiCat: 'museum', radiusMi: 0.0001, fromLat: OAK.lat, fromLon: OAK.lon })
    expect(opts).toEqual([])
    const one = answerOptions('tentacle', { poiCat: 'museum', radiusMi: 1, fromLat: OAK.lat, fromLon: OAK.lon })
    if (one.length === 2) expect(one.map((o) => o.key)).toEqual([TENTACLE_INSIDE, TENTACLE_OUTSIDE])
  })
})

describe('answerOutcomes', () => {
  it('matches logging each answer for real', () => {
    const params = { lat: OAK.lat, lon: OAK.lon, radiusMiles: 3, answer: 'yes' }
    const outcomes = answerOutcomes(STATIONS, template('radar'), answerOptions('radar', params), ZONE)
    for (const o of outcomes) {
      const real = applyFilters(STATIONS, [{ ...template('radar'), params: o.params }], ZONE).remaining
      expect(o.keep.map((s) => s.id)).toEqual(real.map((s) => s.id))
    }
    const [yes, no] = outcomes
    expect(yes.keep.length).toBeGreaterThan(0)
    expect(no.keep.length).toBeGreaterThan(0)
    // the zone overlaps both answers near the circle's edge, so they can share stations
    expect(yes.keep.length + no.keep.length).toBeGreaterThanOrEqual(STATIONS.length)
    expect(worstCaseLeft(outcomes)).toBe(Math.max(yes.keep.length, no.keep.length))
  })

  it('only counts the stations it is given', () => {
    const some = STATIONS.slice(0, 10)
    const outcomes = answerOutcomes(some, template('radar'), answerOptions('radar', { lat: OAK.lat, lon: OAK.lon, radiusMiles: 500, answer: 'no' }), ZONE)
    expect(outcomes.find((o) => o.key === 'yes')!.keep).toHaveLength(10)
    expect(outcomes.find((o) => o.key === 'no')!.keep).toHaveLength(0)
  })
})

describe('answerOutcomesSliced', () => {
  const sliced = (kind: QuestionRecord['kind'], params: Record<string, unknown>, sliceMs: number) =>
    new Promise<{ outcomes: AnswerOutcome[]; progress: number[] }>((resolve) => {
      const progress: number[] = []
      answerOutcomesSliced(STATIONS, template(kind), answerOptions(kind, params), ZONE, (n) => progress.push(n), (outcomes) =>
        resolve({ outcomes, progress }),
      sliceMs)
    })

  it('gives the same result as counting in one go, across many slices', async () => {
    const cases: [QuestionRecord['kind'], Record<string, unknown>][] = [
      ['radar', { lat: OAK.lat, lon: OAK.lon, radiusMiles: 3, answer: 'yes' }],
      ['measure-airport', { fromLat: OAK.lat, fromLon: OAK.lon, answer: 'closer' }],
      ['tentacle', { poiCat: 'museum', radiusMi: 1, fromLat: OAK.lat, fromLon: OAK.lon }],
    ]
    for (const [kind, params] of cases) {
      const { outcomes, progress } = await sliced(kind, params, 1)
      expect(progress.length).toBeGreaterThan(1)
      const once = answerOutcomes(STATIONS, template(kind), answerOptions(kind, params), ZONE)
      expect(outcomes.map((o) => [o.key, o.keep.map((s) => s.id)])).toEqual(once.map((o) => [o.key, o.keep.map((s) => s.id)]))
    }
  }, 30000)

  it('stops when cancelled', async () => {
    let done = false
    const cancel = answerOutcomesSliced(STATIONS, template('radar'), answerOptions('radar', { lat: OAK.lat, lon: OAK.lon, radiusMiles: 3, answer: 'yes' }), ZONE, () => {}, () => {
      done = true
    }, 0)
    cancel()
    await new Promise((r) => setTimeout(r, 50))
    expect(done).toBe(false)
  })
})

describe('every station survives some answer (Bay Area)', () => {
  // The hider is somewhere, so no station may be ruled out by every answer.
  it('holds for each question type from downtown Oakland', () => {
    const at = { fromLat: OAK.lat, fromLon: OAK.lon }
    const cases: [QuestionRecord['kind'], Record<string, unknown>][] = [
      ['radar', { lat: OAK.lat, lon: OAK.lon, radiusMiles: 5, answer: 'yes' }],
      ['thermometer', { ...at, toLat: OAK.lat + 0.02, toLon: OAK.lon, thermometerMiles: 1, answer: 'hotter' }],
      ['measure-airport', { ...at, answer: 'closer' }],
      ['match-county', { ...at, value: 'Alameda', answer: 'yes' }],
      ['tentacle', { poiCat: 'museum', radiusMi: 1, ...at }],
    ]
    for (const [kind, params] of cases) {
      const outcomes = answerOutcomes(STATIONS, template(kind), answerOptions(kind, params), ZONE)
      expect(outcomes.length, kind).toBeGreaterThan(1)
      const union = new Set(outcomes.flatMap((o) => o.keep.map((s) => s.id)))
      expect(union.size, kind).toBe(STATIONS.length)
    }
  })
})
