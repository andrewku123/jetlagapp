import { describe, it, expect } from 'vitest'
import { answerOptions, answerOutcomes, worstCaseLeft } from './answerSplit'
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
