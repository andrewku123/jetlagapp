import type { LatLng } from '../types'
import { countiesData as countiesRaw, IN_PLAY_COUNTIES } from '../data/regions'
import { inPlayArea } from './cities'
import { polysByName, pointInPolys, type NamedPolys } from './polys'

// County polygons used by the "Matching — county (2nd admin)" question. The
// seeker's county is looked up from their coordinate (point-in-polygon), and the
// eliminated-area shading uses the same polygons.

const COUNTIES: Record<string, NamedPolys> = polysByName(countiesRaw)

export function countyNames(): string[] {
  return Object.keys(COUNTIES)
}

// polygon-clipping-ready geometry (a MultiPolygon) for one county, or [] if none.
export function countyGeom(name: string): NamedPolys {
  return COUNTIES[name] ?? []
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
