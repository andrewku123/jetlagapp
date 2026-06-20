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

/**
 * The perpendicular bisector as a sampled polyline (not just its two endpoints).
 * Drawing a single straight segment between the far endpoints lets the line bow
 * off the true midpoint by ~1-2% once it's projected to Web Mercator over a long
 * span. Sampling the bisector into many short segments keeps the rendered line
 * on the true bisector — so it passes exactly through the A–B midpoint and reads
 * perpendicular near it. `segments` should be even so the midpoint is a vertex.
 */
export function bisectorPolyline(
  a: LatLng,
  b: LatLng,
  lengthMiles: number,
  segments = 64,
): LatLng[] {
  const midLat = (a.lat + b.lat) / 2
  const midLon = (a.lon + b.lon) / 2
  const cos = Math.cos(toRad(midLat)) || 1e-6
  const dx = (b.lon - a.lon) * cos
  const dy = b.lat - a.lat
  const len = Math.hypot(dx, dy) || 1
  const px = -dy / len
  const py = dx / len
  const ext = lengthMiles * (1 / 69.0)
  const pts: LatLng[] = []
  for (let i = 0; i <= segments; i++) {
    const t = (i / segments) * 2 - 1 // -1 … +1, hitting the midpoint at t=0
    pts.push({ lat: midLat + py * ext * t, lon: midLon + (px * ext * t) / cos })
  }
  return pts
}

/**
 * Polygon covering the half-plane (of the perpendicular bisector of A–B) that
 * lies on the same side as `toward`. One edge is exactly the bisector
 * (`bisectorEndpoints`), so the shaded region aligns precisely with the drawn
 * boundary line. Used to shade the eliminated (colder) half of a thermometer.
 * The offset uses the same equirectangular projection as the bisector, so it is
 * not skewed by longitude compression at non-equatorial latitudes.
 */
export function bisectorHalfPlane(
  a: LatLng,
  b: LatLng,
  toward: LatLng,
  lengthMiles: number,
): LatLng[] {
  const [e0, e1] = bisectorEndpoints(a, b, lengthMiles)
  const midLat = (a.lat + b.lat) / 2
  const midLon = (a.lon + b.lon) / 2
  const cos = Math.cos(toRad(midLat)) || 1e-6
  // unit vector (projected) from the boundary midpoint toward `toward`
  const ox = (toward.lon - midLon) * cos
  const oy = toward.lat - midLat
  const olen = Math.hypot(ox, oy) || 1
  const ux = ox / olen
  const uy = oy / olen
  const ext = lengthMiles * (1 / 69.0)
  const dLat = uy * ext
  const dLon = (ux * ext) / cos
  return [
    e0,
    e1,
    { lat: e1.lat + dLat, lon: e1.lon + dLon },
    { lat: e0.lat + dLat, lon: e0.lon + dLon },
  ]
}

/**
 * Leniently parse a "lat, lon" string the way you'd paste it from Google Maps.
 * Accepts comma/space/tab separators and hemisphere notation, e.g.
 *   "37.7749, -122.4194"
 *   "37.7749 -122.4194"
 *   "37.7749° N, 122.4194° W"
 *   "N 37.7749 W 122.4194"
 * Returns null if it can't read exactly two in-range coordinates.
 */
export function parseLatLng(input: string): LatLng | null {
  if (!input) return null
  const cleaned = input.toUpperCase().replace(/[°º]/g, ' ').replace(/,/g, ' ')
  const tokens = cleaned.match(/[NSEW]|[+-]?\d+(?:\.\d+)?/g)
  if (!tokens) return null

  const nums: { val: number; hemi?: string }[] = []
  let pendingHemi: string | undefined
  let lastWasNumber = false
  for (const tk of tokens) {
    if (/^[NSEW]$/.test(tk)) {
      if (lastWasNumber && nums.length && nums[nums.length - 1].hemi === undefined) {
        nums[nums.length - 1].hemi = tk
      } else {
        pendingHemi = tk
      }
      lastWasNumber = false
    } else {
      nums.push({ val: parseFloat(tk), hemi: pendingHemi })
      pendingHemi = undefined
      lastWasNumber = true
    }
  }
  if (nums.length !== 2) return null

  let lat: number | undefined
  let lon: number | undefined
  const leftover: number[] = []
  for (const n of nums) {
    if (n.hemi === 'N' || n.hemi === 'S') lat = n.hemi === 'S' ? -Math.abs(n.val) : Math.abs(n.val)
    else if (n.hemi === 'E' || n.hemi === 'W') lon = n.hemi === 'W' ? -Math.abs(n.val) : Math.abs(n.val)
    else leftover.push(n.val)
  }
  if (lat === undefined) lat = leftover.shift()
  if (lon === undefined) lon = leftover.shift()
  if (lat === undefined || lon === undefined || !Number.isFinite(lat) || !Number.isFinite(lon)) return null
  if (lat < -90 || lat > 90 || lon < -180 || lon > 180) return null
  return { lat, lon }
}
