import type { LatLng } from '../types'
import type { Polygon as ClipPolygon, Ring } from 'polygon-clipping'
import { countiesData as countiesRaw, IN_PLAY_COUNTIES } from '../data/regions'
import { inPlayArea } from './cities'

// County polygons used by the "Matching — county (2nd admin)" question. The
// seeker's county is looked up from their coordinate (point-in-polygon), and the
// eliminated-area shading uses the same polygons. Geometry is GeoJSON [lon, lat],
// which is already polygon-clipping's x/y order.

// A polygon-clipping Polygon is [outerRing, ...holes]; a county may be several
// (islands), so each county maps to a list of polygons (a MultiPolygon).
type CountyPolys = ClipPolygon[]

interface GeoFeature {
  properties: { name: string }
  geometry: { type: string; coordinates: number[][][] | number[][][][] }
}

function buildCounties(): Record<string, CountyPolys> {
  const out: Record<string, CountyPolys> = {}
  const fc = countiesRaw as unknown as { features: GeoFeature[] }
  for (const f of fc.features) {
    const name = f.properties.name
    const g = f.geometry
    const polys: CountyPolys = []
    if (g.type === 'Polygon') {
      polys.push((g.coordinates as number[][][]).map((r) => r as Ring))
    } else if (g.type === 'MultiPolygon') {
      for (const poly of g.coordinates as number[][][][]) {
        polys.push(poly.map((r) => r as Ring))
      }
    }
    out[name] = polys
  }
  return out
}

const COUNTIES: Record<string, CountyPolys> = buildCounties()

export function countyNames(): string[] {
  return Object.keys(COUNTIES)
}

// polygon-clipping-ready geometry (a MultiPolygon) for one county, or [] if none.
export function countyGeom(name: string): CountyPolys {
  return COUNTIES[name] ?? []
}

// Ray-cast point-in-ring on a [lon, lat] ring.
function pointInRing(p: LatLng, ring: Ring): boolean {
  let inside = false
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i]
    const [xj, yj] = ring[j]
    const intersect =
      yi > p.lat !== yj > p.lat &&
      p.lon < ((xj - xi) * (p.lat - yi)) / (yj - yi) + xi
    if (intersect) inside = !inside
  }
  return inside
}

function pointInPolys(p: LatLng, polys: CountyPolys): boolean {
  for (const poly of polys) {
    if (!pointInRing(p, poly[0])) continue
    let inHole = false
    for (let h = 1; h < poly.length; h++) {
      if (pointInRing(p, poly[h])) inHole = true
    }
    if (!inHole) return true
  }
  return false
}

// The county containing `p`. Prefers an in-play county (one that holds hiding
// stations); the hider is always in one of these, so for the regular game these
// are all that matter. But a border station's endgame hiding zone can straddle
// into a neighbouring county (e.g. Bayshore/Sunnydale's zone spills from SF into
// San Mateo/Brisbane), so if `p` is still inside the play area but not in an
// in-play county, fall back to the real neighbouring county — that names the
// out-of-play sliver correctly and lets the endgame county carve it. Points
// genuinely outside the play area stay null (their county never changes an
// elimination, so we don't carry the rest of the world).
export function countyAt(p: LatLng): string | null {
  for (const [name, polys] of Object.entries(COUNTIES)) {
    if (!IN_PLAY_COUNTIES.has(name)) continue
    if (pointInPolys(p, polys)) return name
  }
  if (!inPlayArea(p)) return null
  for (const [name, polys] of Object.entries(COUNTIES)) {
    if (IN_PLAY_COUNTIES.has(name)) continue
    if (pointInPolys(p, polys)) return name
  }
  return null
}
