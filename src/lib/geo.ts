import type { LatLng } from '../types'

export const MILES_PER_METER = 1 / 1609.344

export function haversineMeters(a: LatLng, b: LatLng): number {
  const R = 6371000
  const dLat = toRad(b.lat - a.lat)
  const dLon = toRad(b.lon - a.lon)
  const lat1 = toRad(a.lat)
  const lat2 = toRad(b.lat)
  const x =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLon / 2) ** 2
  return 2 * R * Math.asin(Math.sqrt(x))
}

export function haversineMiles(a: LatLng, b: LatLng): number {
  return haversineMeters(a, b) * MILES_PER_METER
}

function toRad(deg: number): number {
  return (deg * Math.PI) / 180
}

/**
 * Format a mileage label, optionally snapped to a coarser step.
 * step = 0 → exact (2 dp); step = 1 → nearest whole mile; step = 0.5 → nearest half, etc.
 */
export function formatMiles(miles: number, step = 0): string {
  if (step > 0) {
    const snapped = Math.round(miles / step) * step
    const dp = step < 1 ? 1 : 0
    return `${snapped.toFixed(dp)} mi`
  }
  return `${miles.toFixed(2)} mi`
}

export type Units = 'imperial' | 'metric'
export const KM_PER_MILE = 1.609344
export const FEET_PER_METER = 3.280839895

/**
 * Format a distance (stored canonically in miles) for display in the chosen
 * unit system. `step` is a coarseness in the *display* unit (0 = exact, 2 dp).
 */
export function formatDistance(miles: number, units: Units, step = 0): string {
  const val = units === 'metric' ? miles * KM_PER_MILE : miles
  const unit = units === 'metric' ? 'km' : 'mi'
  if (step > 0) {
    const snapped = Math.round(val / step) * step
    return `${snapped.toFixed(step < 1 ? 1 : 0)} ${unit}`
  }
  return `${val.toFixed(2)} ${unit}`
}

/** Format an elevation (stored canonically in meters) for the chosen units. */
export function formatElevation(meters: number, units: Units): string {
  if (units === 'imperial') return `${Math.round(meters * FEET_PER_METER)} ft`
  return `${Math.round(meters)} m`
}

/**
 * Approximate a geodesic circle as a ring of `n` points (equirectangular, fine
 * at metro scale). Used to shade the eliminated area outside/inside a radar.
 */
export function circlePolygon(center: LatLng, radiusMiles: number, n = 72): LatLng[] {
  const cos = Math.cos(toRad(center.lat)) || 1e-6
  const degPerMile = 1 / 69.0
  const r = radiusMiles * degPerMile
  const pts: LatLng[] = []
  for (let i = 0; i < n; i++) {
    const t = (i / n) * 2 * Math.PI
    pts.push({ lat: center.lat + r * Math.sin(t), lon: center.lon + (r * Math.cos(t)) / cos })
  }
  return pts
}

/**
 * Endpoints of the perpendicular bisector of segment A–B, extended `lengthMiles`
 * either side of the midpoint. Uses a local equirectangular approximation (good
 * enough at metro scale). This is the hotter/colder boundary for a thermometer.
 */
export function bisectorEndpoints(
  a: LatLng,
  b: LatLng,
  lengthMiles: number,
): [LatLng, LatLng] {
  const midLat = (a.lat + b.lat) / 2
  const midLon = (a.lon + b.lon) / 2
  const cos = Math.cos(toRad(midLat)) || 1e-6
  const dx = (b.lon - a.lon) * cos
  const dy = b.lat - a.lat
  const len = Math.hypot(dx, dy) || 1
  // unit vector perpendicular to A→B
  const px = -dy / len
  const py = dx / len
  const degPerMile = 1 / 69.0
  const ext = lengthMiles * degPerMile
  return [
    { lat: midLat + py * ext, lon: midLon + (px * ext) / cos },
    { lat: midLat - py * ext, lon: midLon - (px * ext) / cos },
  ]
}
