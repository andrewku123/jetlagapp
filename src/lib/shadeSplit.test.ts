import { describe, it, expect } from 'vitest'
import { shadeSplit, composeShading, type LatLngMultiPolygon } from './questionRegions'
import { stationPasses } from './elimination'
import { haversineMiles } from './geo'
import type { QuestionRecord, Station } from '../types'
import stationsJson from '../data/stations.json'

const STATIONS = stationsJson as unknown as Station[]
const ZONE = 0.25

function rec(kind: QuestionRecord['kind'], params: QuestionRecord['params'], id = 'q'): QuestionRecord {
  return { id, kind, createdAt: 0, params, eliminates: true, active: true, zoneMi: ZONE }
}

function inRing(lat: number, lon: number, ring: [number, number][]): boolean {
  let inside = false
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [yi, xi] = ring[i]
    const [yj, xj] = ring[j]
    if ((yi > lat) !== (yj > lat) && lon < ((xj - xi) * (lat - yi)) / (yj - yi) + xi) inside = !inside
  }
  return inside
}
function inRegion(p: { lat: number; lon: number }, mp: LatLngMultiPolygon): boolean {
  return mp.some((poly) => inRing(p.lat, p.lon, poly[0]) && !poly.slice(1).some((h) => inRing(p.lat, p.lon, h)))
}

// Pick a station with in-play land around it to anchor a radar.
const anchor = STATIONS[0]
const north = (mi: number) => ({ lat: anchor.lat + mi / 69, lon: anchor.lon })

describe('solid vs striped split', () => {
  const radarNo = rec('radar', { lat: anchor.lat, lon: anchor.lon, radiusMiles: 1, answer: 'no' })
  const split = shadeSplit(radarNo, ZONE)!
  const { solids, stripes } = composeShading([split])

  it('radar "no": solid is the disk shrunk by the zone, stripes the inner rim', () => {
    expect(inRegion(north(0.5), solids[0])).toBe(true)
    expect(inRegion(north(0.5), stripes)).toBe(false)
    expect(inRegion(north(0.85), stripes)).toBe(true)
    expect(inRegion(north(0.85), solids[0])).toBe(false)
    expect(inRegion(north(1.2), solids[0]) || inRegion(north(1.2), stripes)).toBe(false)
  })

  it('every station centred in solid is eliminated; stations in stripes survive', () => {
    for (const st of STATIONS) {
      const d = haversineMiles(st, anchor)
      if (Math.abs(d - 0.75) < 0.02 || Math.abs(d - 1) < 0.02) continue
      const pass = stationPasses(st, radarNo, ZONE)
      if (inRegion(st, solids[0])) expect(pass, st.name).toBe(false)
      if (inRegion(st, stripes)) expect(pass, st.name).toBe(true)
    }
  })

  it('zone 0 leaves everything solid', () => {
    const z0 = shadeSplit(radarNo, 0)!
    expect(z0.stripes).toEqual([])
  })
})

describe('composition', () => {
  const a = shadeSplit(rec('radar', { lat: anchor.lat, lon: anchor.lon, radiusMiles: 1, answer: 'no' }, 'a'), ZONE)!
  const shifted = { lat: anchor.lat + 0.6 / 69, lon: anchor.lon }
  const b = shadeSplit(rec('radar', { ...shifted, radiusMiles: 1, answer: 'no' }, 'b'), ZONE)!

  it("solid supersedes another question's stripes", () => {
    const { stripes } = composeShading([a, b])
    // 0.85 mi north of anchor: a's stripe rim, but deep inside b's solid disk.
    expect(inRegion(north(0.85), stripes)).toBe(false)
  })

  it('only solids stack: one solid + one stripe is a single solid layer', () => {
    const { solids } = composeShading([a, b])
    const p = north(0.85)
    expect(solids.filter((s) => inRegion(p, s)).length).toBe(1)
    const both = north(0.3)
    expect(solids.filter((s) => inRegion(both, s)).length).toBe(2)
  })

  it('dropping a question brings its covered stripes back', () => {
    const { stripes } = composeShading([a])
    expect(inRegion(north(0.85), stripes)).toBe(true)
  })
})

describe('disk-union fast path agrees with elimination', () => {
  const sf = { lat: 37.7749, lon: -122.4194 }
  for (const answer of ['closer', 'further']) {
    it(`measure-poi museum ${answer}: stations centred in solid are eliminated`, () => {
      const r = rec('measure-poi', { poiCat: 'museum', fromLat: sf.lat, fromLon: sf.lon, answer })
      const { solids } = composeShading([shadeSplit(r, ZONE)!])
      let checked = 0
      for (const st of STATIONS) {
        if (solids.length && inRegion(st, solids[0])) {
          checked++
          expect(stationPasses(st, r, ZONE), st.name).toBe(false)
        }
      }
      expect(checked).toBeGreaterThan(0)
    })
  }
})
