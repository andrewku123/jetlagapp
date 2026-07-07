// The set of rail stations used by the "Measuring — Rail station" question.
// Every eligible hiding station in this map IS a rail station, so this question
// is inert in the first half (a hider at a station is distance 0 from a rail
// station, so the honest answer is always "closer"/tie and nothing is
// eliminated). It becomes useful in the ENDGAME, where the hider answers from
// their real position inside the hiding zone: "closer/further from the nearest
// rail station" then carves the zone (union of your-distance disks around the
// stations), exactly like the airport measuring question.
import { stationsData } from '../data/regions'
import type { Station, LatLng } from '../types'
import { haversineMiles } from './geo'

const STATIONS = stationsData as unknown as Station[]

// The station points, as plain lat/lon, for building the your-distance disks.
export const RAIL_STATIONS: LatLng[] = STATIONS.map((s) => ({ lat: s.lat, lon: s.lon }))

export interface NearestRail {
  name: string
  lat: number
  lon: number
  distMiles: number
}

export function nearestRailStation(p: LatLng): NearestRail {
  let best = STATIONS[0]
  let bestD = Infinity
  for (const s of STATIONS) {
    const d = haversineMiles(p, s)
    if (d < bestD) {
      bestD = d
      best = s
    }
  }
  return { name: best.name, lat: best.lat, lon: best.lon, distMiles: bestD }
}

export function nearestRailStationMiles(p: LatLng): number {
  let bestD = Infinity
  for (const s of STATIONS) {
    const d = haversineMiles(p, s)
    if (d < bestD) bestD = d
  }
  return bestD
}
