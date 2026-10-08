import { describe, it, expect } from 'vitest'
import { stationPasses, applyFilters, recordZoneMi } from './elimination'
import { indexRegion, regionWithinMiles, pointInRegion } from './zoneFit'
import { zoneElevationRange, ZONE_ELEV_MARGIN_M } from './zoneElevation'
import { defaultHidingRadiusMi, hidingRadiusMi } from './hidingZone'
import type { QuestionRecord, Station } from '../types'
import stationsJson from '../data/stations.json'
import { TENTACLE_INSIDE } from './poi'

// The hider answers from anywhere in their hiding zone: a station survives when
// any in-play point within its zone radius is consistent with the answer.

const MI_PER_DEG_LAT = (6371000 * Math.PI) / 180 / 1609.344
// Inland Oakland, well inside the Bay Area play area in every direction.
const CENTER = { lat: 37.81, lon: -122.25 }
const north = (mi: number) => ({ lat: CENTER.lat + mi / MI_PER_DEG_LAT, lon: CENTER.lon })

function station(overrides: Partial<Station> = {}): Station {
  return {
    id: 'zone-test',
    name: 'Zone Test',
    lat: CENTER.lat,
    lon: CENTER.lon,
    systems: ['BART'],
    lines: [],
    aka: [],
    nameLength: 9,
    county: 'Alameda',
    city: 'Oakland',
    elevation: 50,
    airportDist: {},
    nearestAirport: 'OAK',
    service: { wd: { served: true, hourly: true }, we: { served: true, hourly: true } },
    headwayMin: { wd: 12, we: 12 },
    ...overrides,
  }
}

let seq = 0
function record(kind: QuestionRecord['kind'], params: Record<string, unknown>, zoneMi?: number): QuestionRecord {
  return { id: `z${seq++}`, kind, createdAt: 0, params, eliminates: true, active: true, ...(zoneMi == null ? {} : { zoneMi }) }
}
const radar = (answer: 'yes' | 'no', zoneMi?: number) =>
  record('radar', { lat: CENTER.lat, lon: CENTER.lon, radiusMiles: 1, answer }, zoneMi)

describe('zoneFit', () => {
  // ~1° square around the origin-ish test point
  const square = indexRegion([[[[-122.3, 37.8], [-122.2, 37.8], [-122.2, 37.9], [-122.3, 37.9], [-122.3, 37.8]]]])
  it('inside counts as reachable at any radius', () => {
    expect(pointInRegion({ lat: 37.85, lon: -122.25 }, square)).toBe(true)
    expect(regionWithinMiles({ lat: 37.85, lon: -122.25 }, square, 0)).toBe(true)
  })
  it('outside: reachable only once the radius spans the gap to the nearest edge', () => {
    const p = { lat: 37.8 - 0.5 / MI_PER_DEG_LAT, lon: -122.25 } // 0.5 mi south of the bottom edge
    expect(regionWithinMiles(p, square, 0.45)).toBe(false)
    expect(regionWithinMiles(p, square, 0.55)).toBe(true)
  })
})

describe('radar with a hiding zone', () => {
  it('"yes": a station just outside the radius survives if its zone reaches inside', () => {
    expect(stationPasses(station(north(1.2)), radar('yes', 0))).toBe(false)
    expect(stationPasses(station(north(1.2)), radar('yes', 0.25))).toBe(true)
    expect(stationPasses(station(north(1.3)), radar('yes', 0.25))).toBe(false)
  })
  it('"no": a station just inside the radius survives if its zone reaches outside', () => {
    expect(stationPasses(station(north(0.8)), radar('no', 0))).toBe(false)
    expect(stationPasses(station(north(0.8)), radar('no', 0.25))).toBe(true)
    expect(stationPasses(station(north(0.7)), radar('no', 0.25))).toBe(false)
  })
  it('with no zone the station alone decides (old behaviour)', () => {
    expect(stationPasses(station(north(0.99)), radar('yes', 0))).toBe(true)
    expect(stationPasses(station(north(0.99)), radar('no', 0))).toBe(false)
  })

  // Every curse-adjusted zone for both base sizes: the uncertainty band is the
  // zone radius on either side of the circle.
  const zones = [
    ...[0.5, 0.75, 1, 1.5].map((m) => m * defaultHidingRadiusMi('medium')),
    ...[0.5, 0.75, 1, 1.5].map((m) => m * defaultHidingRadiusMi('large')),
  ]
  for (const z of zones) {
    it(`zone ${z} mi: survives at 0.9 z past the circle, eliminated at 1.1 z`, () => {
      expect(stationPasses(station(north(1 + 0.9 * z)), radar('yes', z))).toBe(true)
      expect(stationPasses(station(north(1 + 1.1 * z)), radar('yes', z))).toBe(false)
      expect(stationPasses(station(north(1 - 0.9 * z)), radar('no', z))).toBe(true)
      expect(stationPasses(station(north(1 - 1.1 * z)), radar('no', z))).toBe(false)
    })
  }
  it('curse radii match the preset sizes', () => {
    expect(hidingRadiusMi('medium', { prosperous: 1, tiny: 0 })).toBeCloseTo(0.375)
    expect(hidingRadiusMi('medium', { prosperous: 1, tiny: 1 })).toBeCloseTo(0.1875)
    expect(hidingRadiusMi('large', { prosperous: 0, tiny: 1 })).toBeCloseTo(0.25)
  })
})

describe('thermometer with a hiding zone', () => {
  // Seeker walked 1 mi north → bisector is the east-west line 0.5 mi north.
  const thermo = (zoneMi: number) =>
    record('thermometer', { fromLat: CENTER.lat, fromLon: CENTER.lon, toLat: north(1).lat, toLon: north(1).lon, answer: 'hotter' }, zoneMi)
  it('a station on the cold side survives if its zone crosses the bisector', () => {
    expect(stationPasses(station(north(0.4)), thermo(0))).toBe(false)
    expect(stationPasses(station(north(0.4)), thermo(0.25))).toBe(true)
    expect(stationPasses(station(north(0.2)), thermo(0.25))).toBe(false)
  })
})

describe('per-question zone radius', () => {
  it('a logged zone wins over the fallback; older records use the fallback', () => {
    expect(recordZoneMi(radar('yes', 0.375), 0.25)).toBe(0.375)
    expect(recordZoneMi(radar('yes'), 0.25)).toBe(0.25)
  })
  it('a curse played later does not change an earlier answer', () => {
    const s = station(north(1.3))
    const before = radar('yes', 0.25) // asked before Prosperous Home
    const after = radar('yes', 0.375) // asked after
    expect(stationPasses(s, before, 0.375)).toBe(false)
    expect(stationPasses(s, after, 0.375)).toBe(true)
  })
  it('applyFilters passes the fallback to old records and combines questions', () => {
    const near = station({ ...north(1.2), id: 'near' })
    const far = station({ ...north(1.4), id: 'far' })
    const q1 = radar('yes')
    const res = applyFilters([near, far], [q1], 0.25)
    expect(res.remaining.map((s) => s.id)).toEqual(['near'])
    // A second question that excludes 'near' even with its zone.
    const q2 = record('radar', { lat: north(3).lat, lon: CENTER.lon, radiusMiles: 1, answer: 'yes' }, 0.25)
    expect(applyFilters([near, far], [q1, q2], 0.25).remaining).toEqual([])
  })
})

describe('questions about "your station" ignore the zone', () => {
  it('line and name length still use the station', () => {
    const r = record('match-line', { value: 'BART Red', answer: 'yes' }, 1)
    expect(stationPasses(station({ lines: ['BART Blue'] }), r)).toBe(false)
  })
})

describe('rail-station measuring and endgame tentacles use the zone', () => {
  it('rail-station "further" keeps a station whose zone reaches far enough from every station', () => {
    const real = (stationsJson as unknown as Station[])[0]
    const seeker = { lat: real.lat + 0.1 / 69, lon: real.lon }
    const further = record('measure-railstation', { fromLat: seeker.lat, fromLon: seeker.lon, answer: 'further' }, 0)
    expect(stationPasses(real, further)).toBe(false)
    const wide = { ...further, zoneMi: 3 }
    expect(stationPasses(real, wide)).toBe(true)
  })
  it('endgame tentacles eliminate map-wide like any other tentacle', () => {
    const r = { ...record('tentacle', { poiCat: 'museum', radiusMi: 1, fromLat: CENTER.lat, fromLon: CENTER.lon, value: TENTACLE_INSIDE }, 0.25), endgame: true }
    expect(stationPasses(station(north(5)), r)).toBe(false)
    expect(stationPasses(station(), r)).toBe(true)
  })
})

describe('sea level with terrain zone ranges', () => {
  const real = (stationsJson as unknown as Station[])[0]
  const range = zoneElevationRange(real.id, 0.25)!
  it('precondition: the active map has terrain ranges', () => {
    expect(range).not.toBeNull()
    expect(range.min).toBeLessThanOrEqual(range.max)
  })
  it('"closer": kept while the lowest ground in the zone is at or below the seeker', () => {
    const s = { ...real, elevation: range.max + 50 } // station itself is higher than the seeker
    const seekerAt = (v: number) => record('measure-sealevel', { value: v, answer: 'closer' }, 0.25)
    expect(stationPasses(s, seekerAt(range.min))).toBe(true)
    expect(stationPasses(s, seekerAt(range.min - 1))).toBe(false)
    expect(stationPasses(s, { ...seekerAt(range.min), zoneMi: 0 })).toBe(false)
  })
  it('"further": kept while the highest ground in the zone is above the seeker', () => {
    const s = { ...real, elevation: range.min - 50 }
    const seekerAt = (v: number) => record('measure-sealevel', { value: v, answer: 'further' }, 0.25)
    expect(stationPasses(s, seekerAt(range.max - 1))).toBe(true)
    expect(stationPasses(s, seekerAt(range.max))).toBe(false)
  })
  it('a zone between presets uses the next larger preset', () => {
    expect(zoneElevationRange(real.id, 0.2)).toEqual(range)
  })
  it('no terrain (unknown station or zone above the largest preset) never eliminates', () => {
    const r = record('measure-sealevel', { value: -500, answer: 'closer' }, 0.25)
    expect(stationPasses({ ...real, id: 'nope', elevation: 100 }, r)).toBe(true)
    expect(stationPasses({ ...real, elevation: 100 }, { ...r, zoneMi: 5 })).toBe(true)
  })
  it('ranges include a safety margin', () => {
    expect(ZONE_ELEV_MARGIN_M).toBeGreaterThan(0)
  })
})
