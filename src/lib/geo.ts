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
