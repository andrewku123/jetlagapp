import { describe, it, expect } from 'vitest'
import type { QuestionRecord, Station } from '../types'
import rawStations from '../data/stations.json'
import { stationPasses } from './elimination'
import { endgameClippedRegion, type LatLngMultiPolygon } from './questionRegions'
import { haversineMiles } from './geo'

const STATIONS = rawStations as unknown as Station[]

function pointInRing(lat: number, lon: number, ring: [number, number][]): boolean {
  let inside = false
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [yi, xi] = ring[i]
    const [yj, xj] = ring[j]
    const intersect = yi > lat !== yj > lat && lon < ((xj - xi) * (lat - yi)) / (yj - yi) + xi
    if (intersect) inside = !inside
  }
  return inside
}
function pointInMulti(lat: number, lon: number, mp: LatLngMultiPolygon): boolean {
  for (const poly of mp) {
    if (!pointInRing(lat, lon, poly[0])) continue
    let inHole = false
    for (let h = 1; h < poly.length; h++) if (pointInRing(lat, lon, poly[h])) inHole = true
    if (!inHole) return true
  }
  return false
}

// Zone centred on a mid-map station; a generous radius so a grid of sample
// points straddles the zone edge and the question boundary.
const ZONE = { lat: 37.8716, lon: -122.2727 } // Berkeley
const ZONE_MI = 1.2
const MARGIN = 0.06 // skip points within this of either boundary (n-gon epsilon)

function sampleGrid(): { lat: number; lon: number }[] {
  const pts: { lat: number; lon: number }[] = []
  const span = (ZONE_MI * 1.6) / 69.0
  const cos = Math.cos((ZONE.lat * Math.PI) / 180)
  for (let i = -12; i <= 12; i++) {
    for (let j = -12; j <= 12; j++) {
      pts.push({ lat: ZONE.lat + (i / 12) * span, lon: ZONE.lon + (j / 12) * (span / cos) })
    }
  }
  return pts
}

// endgameClippedRegion(rec, Z, r) must shade a point iff it is BOTH inside the
// zone AND inside the question's eliminated area — i.e. it is exactly the
// eliminated region intersected with the hiding-zone disk. We verify against the
// analytic radar rule (haversine circle), skipping near-boundary points where the
// polygon n-gon approximation is expected to differ by <MARGIN.
describe('endgame shading = eliminated region ∩ hiding zone (radar)', () => {
  const CENTER = { lat: 37.86, lon: -122.25 }
  const RADIUS = 0.9
  for (const answer of ['yes', 'no'] as const) {
    it(`radar / ${answer}`, () => {
      const rec: QuestionRecord = {
        id: 'q',
        kind: 'radar',
        createdAt: 0,
        params: { lat: CENTER.lat, lon: CENTER.lon, radiusMiles: RADIUS, answer },
        eliminates: true,
        active: true,
        endgame: true,
      }
      const clipped = endgameClippedRegion(rec, ZONE, ZONE_MI)
      for (const p of sampleGrid()) {
        const dZone = haversineMiles(p, ZONE)
        const dCircle = haversineMiles(p, CENTER)
        if (Math.abs(dZone - ZONE_MI) < MARGIN) continue
        if (Math.abs(dCircle - RADIUS) < MARGIN) continue
        const inZone = dZone < ZONE_MI
        // yes = within circle kept → eliminate outside; no = eliminate inside.
        const eliminated = answer === 'yes' ? dCircle > RADIUS : dCircle < RADIUS
        const expected = inZone && eliminated
        const shaded = clipped ? pointInMulti(p.lat, p.lon, clipped) : false
        expect(shaded, `(${p.lat.toFixed(4)},${p.lon.toFixed(4)})`).toBe(expected)
      }
    })
  }
})

// The clipped shading never spills outside the zone, and inside the zone it still
// matches the per-hider elimination rule for a coordinate feature question.
describe('endgame shading stays inside the zone and agrees with elimination', () => {
  // A station with several neighbours nearby so the zone contains other stations
  // to act as sample hider positions.
  const center = STATIONS.find((s) => s.city === 'San Francisco') ?? STATIONS[0]
  const zone = { lat: center.lat, lon: center.lon }
  const zoneMi = 6 // wide enough to include multiple SF stations as sample points
  it('measure-feature (coastline) inside SF zone', () => {
    const rec: QuestionRecord = {
      id: 'q',
      kind: 'measure-feature',
      createdAt: 0,
      params: { feature: 'coastline', fromLat: zone.lat, fromLon: zone.lon, answer: 'closer' },
      eliminates: true,
      active: true,
      endgame: true,
    }
    const clipped = endgameClippedRegion(rec, zone, zoneMi)
    for (const st of STATIONS) {
      const dZone = haversineMiles(st, zone)
      const shaded = clipped ? pointInMulti(st.lat, st.lon, clipped) : false
      if (dZone > zoneMi + 0.5) {
        expect(shaded, `${st.name} outside zone must be unshaded`).toBe(false)
        continue
      }
      if (dZone > zoneMi - 0.5) continue // skip zone-edge band (n-gon epsilon)
      const eliminated = !stationPasses(st, rec)
      expect(shaded, `${st.name} in-zone shading`).toBe(eliminated)
    }
  })
})
