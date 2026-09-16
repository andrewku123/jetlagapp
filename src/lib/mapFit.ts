import type { Station } from '../types'

// The vector basemap is a MapLibre GL layer, not a raster TileLayer, so it
// contributes no maxZoom of its own. Without this the map's max zoom is
// Infinity and fitting a zero-size box (a single remaining suspect) resolves to
// zoom Infinity, which makes the centre NaN and blanks the whole map.
export const MAP_MAX_ZOOM = 20

const METRES_PER_MILE = 1609.344
// how much wider than the hiding-zone diameter the fitted box is, so the circle
// has some breathing room around it
const ZONE_FIT_FACTOR = 1.3

// Side length, in metres, of the square box that frames a hiding zone.
export function zoneBoxMeters(radiusMi: number): number {
  return radiusMi * 2 * METRES_PER_MILE * ZONE_FIT_FACTOR
}

export type FitTarget =
  | { kind: 'bounds'; points: [number, number][] }
  | { kind: 'zone'; lat: number; lon: number; sizeM: number }

// Where the view should sit for a given board. A spread of suspects fits their
// bounding box; a board narrowed to a single point (endgame, or the last
// suspect standing) fits that station's hiding zone instead, because a
// zero-size bounding box has no zoom that fits it.
export function fitTarget(
  remaining: Station[],
  endgame: Station | null,
  radiusMi: number,
): FitTarget | null {
  const focus = endgame ?? (remaining.length === 1 ? remaining[0] : null)
  if (focus) return { kind: 'zone', lat: focus.lat, lon: focus.lon, sizeM: zoneBoxMeters(radiusMi) }
  if (remaining.length === 0) return null
  const points = remaining.map((s) => [s.lat, s.lon] as [number, number])
  const lats = points.map((p) => p[0])
  const lons = points.map((p) => p[1])
  // stations can be co-located (a multi-agency stop listed twice); their box is
  // degenerate too, so fall back to the zone framing
  if (Math.max(...lats) === Math.min(...lats) && Math.max(...lons) === Math.min(...lons)) {
    return { kind: 'zone', lat: lats[0], lon: lons[0], sizeM: zoneBoxMeters(radiusMi) }
  }
  return { kind: 'bounds', points }
}
