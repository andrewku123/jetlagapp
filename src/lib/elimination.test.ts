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
    // city is resolved geometrically from coordinates (not the baked .city field),
    // so shading and elimination always agree.
    const r = record('match-city', { value: 'San Francisco city', fromLat: 37.7749, fromLon: -122.4194, answer: 'yes' })
    expect(stationPasses(station(), r)).toBe(true) // SF coords → same city
    expect(stationPasses(station({ lat: 37.8044, lon: -122.2712 }), r)).toBe(false) // Oakland coords → different
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

describe('stationPasses — match-poi (nearest place of a type)', () => {
  const here = { lat: 37.7749, lon: -122.4194 } // downtown SF
  const far = { lat: 37.3352, lon: -121.8811 } // San Jose (different nearest park)
  it('a station co-located with the seeker shares the nearest park', () => {
    const r = record('match-poi', { poiCat: 'park', fromLat: here.lat, fromLon: here.lon, answer: 'yes' })
    expect(stationPasses(station(here), r)).toBe(true)
    expect(stationPasses(station(here), { ...r, params: { ...r.params, answer: 'no' } })).toBe(false)
  })
  it('a far station has a different nearest park (eliminated on yes)', () => {
    const r = record('match-poi', { poiCat: 'park', fromLat: here.lat, fromLon: here.lon, answer: 'yes' })
    expect(stationPasses(station(far), r)).toBe(false)
    expect(stationPasses(station(far), { ...r, params: { ...r.params, answer: 'no' } })).toBe(true)
  })
  it('unknown category never eliminates', () => {
    const r = record('match-poi', { poiCat: 'nonesuch', fromLat: here.lat, fromLon: here.lon, answer: 'yes' })
    expect(stationPasses(station(far), r)).toBe(true)
  })
})

describe('stationPasses — measure-poi (distance to nearest place of a type)', () => {
  const here = { lat: 37.7749, lon: -122.4194 }
  it('a co-located station is not strictly closer (tie ⇒ not "closer")', () => {
    const r = record('measure-poi', { poiCat: 'park', fromLat: here.lat, fromLon: here.lon, answer: 'closer' })
    expect(stationPasses(station(here), r)).toBe(false)
    expect(stationPasses(station(here), { ...r, params: { ...r.params, answer: 'further' } })).toBe(true)
  })
  it('unknown category never eliminates', () => {
    const r = record('measure-poi', { poiCat: 'nonesuch', fromLat: here.lat, fromLon: here.lon, answer: 'closer' })
    expect(stationPasses(station(here), r)).toBe(true)
  })
})

describe('stationPasses — measure-feature (distance to a coastline / border)', () => {
  // coastal SF station is ~0 mi from the saltwater shore; inland Antioch is ~30 mi
  const coastal = station({ id: 'sf-embarcadero', lat: 37.7955, lon: -122.3937 })
  const inland = station({ id: 'antioch', lat: 38.0169, lon: -121.8009 })
  // seeker at San Jose Diridon (~10 mi from the coast)
  const seeker = { fromLat: 37.3297, fromLon: -121.9024 }

  it('coastline: keeps stations on the seeker\u2019s side of the corridor', () => {
    const closer = record('measure-feature', { feature: 'coastline', ...seeker, answer: 'closer' })
    expect(stationPasses(coastal, closer)).toBe(true) // 0 < 10
    expect(stationPasses(inland, closer)).toBe(false) // 30 !< 10
    const further = record('measure-feature', { feature: 'coastline', ...seeker, answer: 'further' })
    expect(stationPasses(coastal, further)).toBe(false)
    expect(stationPasses(inland, further)).toBe(true)
  })

  it('state border: the eastern station is closer to the Nevada line', () => {
    // Antioch (east) is closer to CA\u2019s land border than SF (west)
    const r = record('measure-feature', { feature: 'state-border', fromLat: 37.7955, fromLon: -122.3937, answer: 'closer' })
    expect(stationPasses(inland, r)).toBe(true) // Antioch closer than an SF seeker
  })

  it('unknown feature never eliminates', () => {
    const r = record('measure-feature', { feature: 'nonesuch', ...seeker, answer: 'closer' })
    expect(stationPasses(coastal, r)).toBe(true)
  })
})

describe('applyFilters', () => {
  it('partitions stations into remaining and eliminated', () => {
    const a = station({ id: 'a', lat: 37.7749, lon: -122.4194 }) // San Francisco
    const b = station({ id: 'b', lat: 37.8044, lon: -122.2712 }) // Oakland
    const { remaining, eliminatedByQuestion } = applyFilters(
      [a, b],
      [record('match-city', { value: 'San Francisco city', fromLat: 37.7749, fromLon: -122.4194, answer: 'yes' })],
    )
    expect(remaining.map((s) => s.id)).toEqual(['a'])
    expect(eliminatedByQuestion.has('b')).toBe(true)
  })
})
