import type { LatLng } from '../types'
import { haversineMiles } from './geo'
import { AIRPORTS } from '../data/regions'

// Commercial airports that exist on the active map. The list is scoped to the
// play area in regions.ts (the rule "outside the play area = doesn't exist"), so
// on a map with no in-play airport (e.g. SF Muni) this is empty and the
// nearest-airport questions are demoted to log-only.
export { AIRPORTS }

// Nearest commercial airport to a point, with its straight-line distance (mi).
// Returns an empty code / Infinity when the active map has no in-play airport.
export function nearestAirport(p: LatLng): { code: string; distMiles: number } {
  let code = ''
  let distMiles = Infinity
  for (const [c, a] of Object.entries(AIRPORTS)) {
    const d = haversineMiles(p, a)
    if (d < distMiles) {
      distMiles = d
      code = c
    }
  }
  return { code, distMiles }
}
