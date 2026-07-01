import { describe, it, expect } from 'vitest'
import rawStations from '../data/stations.json'
import type { QuestionRecord, Station } from '../types'
import { stationPasses } from './elimination'
import { poiEliminatedRegion, type LatLngMultiPolygon } from './questionRegions'
import { MEASURE_FEATURE_KEYS } from './measureFeatures'

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

// A few seekers spread across the play area: near the coast, inland, and up/down
// the latitude range so the seeker-centred projection is exercised.
const SEEKERS = [
  { lat: 37.6688, lon: -122.0808 }, // Hayward (the reported failure)
  { lat: 37.8716, lon: -122.2727 }, // Berkeley
  { lat: 37.3382, lon: -121.8863 }, // San Jose
]

// Every station's shaded/unshaded state must match its eliminate/keep decision
// for the border & coastline measuring questions — the shading buffer and the
// elimination rule share one projected metric, so they should never disagree.
describe('measure-feature shading agrees with elimination for every station', () => {
  for (const feature of MEASURE_FEATURE_KEYS) {
    for (const answer of ['closer', 'further'] as const) {
      for (const seeker of SEEKERS) {
        it(`${feature} / ${answer} @ ${seeker.lat},${seeker.lon}`, () => {
          const rec: QuestionRecord = {
            id: 'q',
            kind: 'measure-feature',
            createdAt: 0,
            params: { feature, fromLat: seeker.lat, fromLon: seeker.lon, answer },
            eliminates: true,
            active: true,
          }
          const region = poiEliminatedRegion(rec)
          for (const st of STATIONS) {
            const kept = stationPasses(st, rec)
            const shaded = region ? pointInMulti(st.lat, st.lon, region) : false
            // kept ⇒ unshaded, eliminated ⇒ shaded
            expect(kept, `${st.name} (${feature}/${answer})`).toBe(!shaded)
          }
        })
      }
    }
  }
})
