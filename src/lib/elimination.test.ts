import { describe, it, expect } from 'vitest'
import { stationPasses, applyFilters } from './elimination'
import type { QuestionRecord, Station } from '../types'

function station(overrides: Partial<Station> = {}): Station {
  return {
    id: 't1',
    name: 'Test Station',
    lat: 37.7749,
    lon: -122.4194,
    systems: ['Muni'],
    lines: ['Muni N'],
    aka: [],
    nameLength: 12,
    county: 'San Francisco',
    city: 'San Francisco',
    elevation: 16,
    airportDist: { SFO: 20000, OAK: 18000, SJC: 70000 },
    nearestAirport: 'OAK',
    service: { wd: { served: true, hourly: true }, we: { served: true, hourly: true } },
    headwayMin: { wd: 12, we: 12 },
    ...overrides,
  }
}

function record(kind: QuestionRecord['kind'], params: Record<string, unknown>): QuestionRecord {
  return { id: 'q1', kind, createdAt: 0, params, eliminates: true, active: true }
}

describe('stationPasses — gating', () => {
  it('always passes when the record is inactive', () => {
    const r = { ...record('match-city', { value: 'Oakland', answer: 'yes' }), active: false }
    expect(stationPasses(station(), r)).toBe(true)
  })
  it('photo questions never eliminate', () => {
    expect(stationPasses(station(), record('photo', {}))).toBe(true)
  })
  it('vetoed questions never eliminate (no answer was given)', () => {
    const far = station({ lat: 37.33, lon: -121.9 })
    const r = record('radar', { lat: 37.7749, lon: -122.4194, radiusMiles: 1, answer: 'yes' })
    expect(stationPasses(far, r)).toBe(false)
    expect(stationPasses(far, { ...r, vetoed: true })).toBe(true)
  })
})

describe('stationPasses — radar', () => {
  const here = { lat: 37.7749, lon: -122.4194 }
  it('keeps a near station on a yes within 1mi', () => {
    expect(stationPasses(station(), record('radar', { ...here, radiusMiles: 1, answer: 'yes' }))).toBe(true)
  })
  it('eliminates a far station on a yes within 1mi', () => {
    const far = station({ lat: 37.33, lon: -121.9 })
    expect(stationPasses(far, record('radar', { ...here, radiusMiles: 1, answer: 'yes' }))).toBe(false)
  })
  it('inverts on a no answer', () => {
    expect(stationPasses(station(), record('radar', { ...here, radiusMiles: 1, answer: 'no' }))).toBe(false)
  })
})

describe('stationPasses — matching', () => {
  it('match-city', () => {
    const r = record('match-city', { value: 'San Francisco', answer: 'yes' })
    expect(stationPasses(station(), r)).toBe(true)
    expect(stationPasses(station({ city: 'Oakland' }), r)).toBe(false)
  })
  it('match-namelength', () => {
    const r = record('match-namelength', { value: 12, answer: 'yes' })
    expect(stationPasses(station({ nameLength: 12 }), r)).toBe(true)
    expect(stationPasses(station({ nameLength: 8 }), r)).toBe(false)
  })
  it('match-line', () => {
    const r = record('match-line', { value: 'Muni N', answer: 'yes' })
    expect(stationPasses(station({ lines: ['Muni N', 'Muni T'] }), r)).toBe(true)
    expect(stationPasses(station({ lines: ['Muni K'] }), r)).toBe(false)
  })
  it('match-system', () => {
    const r = record('match-system', { value: 'BART', answer: 'yes' })
    expect(stationPasses(station({ systems: ['BART', 'Muni'] }), r)).toBe(true)
    expect(stationPasses(station({ systems: ['Caltrain'] }), r)).toBe(false)
    const no = record('match-system', { value: 'BART', answer: 'no' })
    expect(stationPasses(station({ systems: ['BART', 'Muni'] }), no)).toBe(false)
    expect(stationPasses(station({ systems: ['Muni'] }), no)).toBe(true)
  })
})

describe('stationPasses — measuring', () => {
  it('measure-sealevel: lower elevation is "closer" to sea level', () => {
    const r = record('measure-sealevel', { value: 50, answer: 'closer' })
    expect(stationPasses(station({ elevation: 10 }), r)).toBe(true)
    expect(stationPasses(station({ elevation: 200 }), r)).toBe(false)
  })
  it('measure-sealevel: unknown elevation never eliminates', () => {
    const r = record('measure-sealevel', { value: 50, answer: 'closer' })
    expect(stationPasses(station({ elevation: null }), r)).toBe(true)
  })
})

describe('applyFilters', () => {
  it('partitions stations into remaining and eliminated', () => {
    const a = station({ id: 'a', city: 'San Francisco' })
    const b = station({ id: 'b', city: 'Oakland' })
    const { remaining, eliminatedByQuestion } = applyFilters(
      [a, b],
      [record('match-city', { value: 'San Francisco', answer: 'yes' })],
    )
    expect(remaining.map((s) => s.id)).toEqual(['a'])
    expect(eliminatedByQuestion.has('b')).toBe(true)
  })
})
