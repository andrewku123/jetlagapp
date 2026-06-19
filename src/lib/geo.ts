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
