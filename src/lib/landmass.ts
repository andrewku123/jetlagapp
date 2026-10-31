import type { LatLng } from '../types'
import { landmassesData } from '../data/regions'
import { polysByName, pointInPolys, type NamedPolys } from './polys'

// Landmass polygons used by the "Matching — landmass" question: connected land,
// where bridges and tunnels never join two pieces (Manhattan, Staten Island,
// Roosevelt Island… on NYC; Alameda and Treasure Island apart from the East Bay
// mainland on the Bay Area). Both the seeker's landmass and each station's are
// resolved through the same lookup, so shading and elimination agree. A map with
// no landmass file has one landmass and the question stays log-only.

const LANDMASSES: Record<string, NamedPolys> = landmassesData ? polysByName(landmassesData) : {}

export function landmassNames(): string[] {
  return Object.keys(LANDMASSES)
}

export function landmassGeom(name: string): NamedPolys {
  return LANDMASSES[name] ?? []
}

/** The landmass `p` stands on, or null (water, or off the map). */
export function landmassAt(p: LatLng): string | null {
  for (const [name, polys] of Object.entries(LANDMASSES)) if (pointInPolys(p, polys)) return name
  return null
}

// A station on a pier (NYC Ferry landings) stands just off the shoreline the
// polygons trace; it belongs to the landmass whose shore is within this distance.
const PIER_SNAP_MI = 0.1

function distToRingMiles(p: LatLng, ring: number[][]): number {
  const cos = Math.cos((p.lat * Math.PI) / 180)
  let best = Infinity
  for (let i = 1; i < ring.length; i++) {
    const ax = (ring[i - 1][0] - p.lon) * cos
    const ay = ring[i - 1][1] - p.lat
    const bx = (ring[i][0] - p.lon) * cos
    const by = ring[i][1] - p.lat
    const dx = bx - ax
    const dy = by - ay
    const len2 = dx * dx + dy * dy
    const t = len2 > 0 ? Math.max(0, Math.min(1, -(ax * dx + ay * dy) / len2)) : 0
    best = Math.min(best, Math.hypot(ax + t * dx, ay + t * dy) * 69.0)
  }
  return best
}

/** The landmass a station belongs to: the one it stands on, else the nearest
 *  shore within PIER_SNAP_MI (a landing on a pier), else null. */
export function stationLandmass(p: LatLng): string | null {
  const on = landmassAt(p)
  if (on) return on
  let best: string | null = null
  let bestD = PIER_SNAP_MI
  for (const [name, polys] of Object.entries(LANDMASSES))
    for (const poly of polys) {
      const d = distToRingMiles(p, poly[0] as number[][])
      if (d <= bestD) {
        bestD = d
        best = name
      }
    }
  return best
}
