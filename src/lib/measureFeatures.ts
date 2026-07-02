import type { LatLng } from '../types'
import { haversineMiles } from './geo'
import featuresRaw from '../data/measure-features.geojson.json'

// Linear geographic features used by the "Measuring — border / coastline"
// question: the seeker and every station are compared by straight-line distance
// to the nearest point of a chosen feature. Geometry is baked by
// scripts/build_measure_features.py into src/data/measure-features.geojson.json
// as MultiLineString features keyed by `key`.

export type MeasureFeatureKey =
  | 'coastline'
  | 'county-border'
  | 'state-border'
  | 'intl-border'

export const MEASURE_FEATURE_KEYS: MeasureFeatureKey[] = [
  'coastline',
  'county-border',
  'state-border',
  'intl-border',
]

export const MEASURE_FEATURE_LABELS: Record<MeasureFeatureKey, string> = {
  coastline: 'a coastline',
  'county-border': 'a county border (2nd admin)',
  'state-border': 'a state border (1st admin)',
  'intl-border': 'an international border',
}

// The feature label without its leading article ("a state border …" →
// "state border …"), for phrases like "nearest state border" that already
// supply their own article.
export function measureFeatureNoun(key: string): string {
  return (MEASURE_FEATURE_LABELS[key as MeasureFeatureKey] ?? key).replace(/^an? /, '')
}

// polyline = list of vertices; a feature is one or more polylines.
type Polyline = LatLng[]

interface GeoJsonFeature {
  properties: { key: string }
  geometry: { type: string; coordinates: number[][][] }
}

// Douglas–Peucker simplification tolerance, in miles. Some features (the county
// borders especially) ship with thousands of ~0.25 mi segments; buffering every
// one to shade the eliminated area is O(n²) in the polygon union and takes tens
// of seconds. Simplifying to this tolerance cuts the segment count ~10× while
// shifting any distance by at most ~0.03 mi. Crucially the SAME simplified
// geometry backs both the station distance test and the shading, so they stay in
// lockstep regardless of the tolerance.
const SIMPLIFY_MILES = 0.03
const SIMPLIFY_DEG = SIMPLIFY_MILES / 69.0

// Perpendicular distance (in a local equirectangular metric) from p to line a–b.
function perpDist(p: LatLng, a: LatLng, b: LatLng, cosLat: number): number {
  const ax = (a.lon - p.lon) * cosLat
  const ay = a.lat - p.lat
  const bx = (b.lon - p.lon) * cosLat
  const by = b.lat - p.lat
  const dx = bx - ax
  const dy = by - ay
  const len2 = dx * dx + dy * dy
  if (len2 === 0) return Math.hypot(ax, ay)
  let t = -(ax * dx + ay * dy) / len2
  if (t < 0) t = 0
  else if (t > 1) t = 1
  return Math.hypot(ax + t * dx, ay + t * dy)
}

function simplify(line: Polyline, tolDeg: number): Polyline {
  if (line.length < 3) return line
  const cosLat = Math.cos((line[0].lat * Math.PI) / 180) || 1e-6
  const keep = new Array<boolean>(line.length).fill(false)
  keep[0] = true
  keep[line.length - 1] = true
  const stack: [number, number][] = [[0, line.length - 1]]
  while (stack.length) {
    const [lo, hi] = stack.pop()!
    let maxD = -1
    let idx = -1
    for (let i = lo + 1; i < hi; i++) {
      const d = perpDist(line[i], line[lo], line[hi], cosLat)
      if (d > maxD) {
        maxD = d
        idx = i
      }
    }
    if (idx > 0 && maxD > tolDeg) {
      keep[idx] = true
      stack.push([lo, idx], [idx, hi])
    }
  }
  return line.filter((_, i) => keep[i])
}

function buildPolylines(): Record<string, Polyline[]> {
  const out: Record<string, Polyline[]> = {}
  const fc = featuresRaw as unknown as { features: GeoJsonFeature[] }
  for (const f of fc.features) {
    const key = f.properties.key
    // MultiLineString coords: [ [ [lon,lat], … ], … ]
    out[key] = f.geometry.coordinates.map((line) =>
      simplify(
        line.map(([lon, lat]) => ({ lat, lon })),
        SIMPLIFY_DEG,
      ),
    )
  }
  return out
}

const POLYLINES: Record<string, Polyline[]> = buildPolylines()

export function featurePolylines(key: string): Polyline[] {
  return POLYLINES[key] ?? []
}

// Straight-line (miles) distance from `p` to the nearest point of segment a–b,
// projecting locally at `p`'s latitude so the comparison matches the haversine
// engine used everywhere else.
function distToSegmentMiles(p: LatLng, a: LatLng, b: LatLng): number {
  const cosLat = Math.cos((p.lat * Math.PI) / 180) || 1e-6
  const ax = (a.lon - p.lon) * cosLat
  const ay = a.lat - p.lat
  const bx = (b.lon - p.lon) * cosLat
  const by = b.lat - p.lat
  const dx = bx - ax
  const dy = by - ay
  const len2 = dx * dx + dy * dy
  let t = len2 > 0 ? -(ax * dx + ay * dy) / len2 : 0
  if (t < 0) t = 0
  else if (t > 1) t = 1
  const nlat = a.lat + t * (b.lat - a.lat)
  const nlon = a.lon + t * (b.lon - a.lon)
  return haversineMiles(p, { lat: nlat, lon: nlon })
}

export function distanceToFeatureMiles(p: LatLng, key: string): number {
  const lines = featurePolylines(key)
  let best = Infinity
  for (const line of lines) {
    for (let i = 1; i < line.length; i++) {
      const d = distToSegmentMiles(p, line[i - 1], line[i])
      if (d < best) best = d
    }
  }
  return best
}

const MILES_PER_DEG = 69.0

// Distance (miles) from `p` to the nearest point of segment a–b in an
// equirectangular projection scaled at a fixed reference longitude factor
// `cosRef` (= cos(refLat)). Unlike distToSegmentMiles this projects EVERY point
// at the same reference latitude, so it exactly matches the flat buffer used to
// shade the eliminated area — keeping the map shading and the station list in
// lockstep even for far-off borders where a per-point projection would drift.
function projDistToSegmentMiles(p: LatLng, a: LatLng, b: LatLng, cosRef: number): number {
  const ax = (a.lon - p.lon) * cosRef
  const ay = a.lat - p.lat
  const bx = (b.lon - p.lon) * cosRef
  const by = b.lat - p.lat
  const dx = bx - ax
  const dy = by - ay
  const len2 = dx * dx + dy * dy
  let t = len2 > 0 ? -(ax * dx + ay * dy) / len2 : 0
  if (t < 0) t = 0
  else if (t > 1) t = 1
  const cx = ax + t * dx
  const cy = ay + t * dy
  return Math.hypot(cx, cy) * MILES_PER_DEG
}

// Projected distance (miles) from `p` to the whole feature, at reference
// latitude `refLat`. This is the metric the shading buffer is built in; both the
// seeker's radius and every station's distance are measured with it so the
// shaded boundary and the eliminate/keep decision always agree.
export function projectedDistanceToFeatureMiles(p: LatLng, key: string, refLat: number): number {
  const cosRef = Math.cos((refLat * Math.PI) / 180) || 1e-6
  const lines = featurePolylines(key)
  let best = Infinity
  for (const line of lines) {
    for (let i = 1; i < line.length; i++) {
      const d = projDistToSegmentMiles(p, line[i - 1], line[i], cosRef)
      if (d < best) best = d
    }
  }
  return best
}

// The nearest point on the feature to `p` (for the map pin). null if empty.
export function nearestPointOnFeature(p: LatLng, key: string): LatLng | null {
  const lines = featurePolylines(key)
  let best = Infinity
  let bestPt: LatLng | null = null
  const cosLat = Math.cos((p.lat * Math.PI) / 180) || 1e-6
  for (const line of lines) {
    for (let i = 1; i < line.length; i++) {
      const a = line[i - 1]
      const b = line[i]
      const ax = (a.lon - p.lon) * cosLat
      const ay = a.lat - p.lat
      const bx = (b.lon - p.lon) * cosLat
      const by = b.lat - p.lat
      const dx = bx - ax
      const dy = by - ay
      const len2 = dx * dx + dy * dy
      let t = len2 > 0 ? -(ax * dx + ay * dy) / len2 : 0
      if (t < 0) t = 0
      else if (t > 1) t = 1
      const nlat = a.lat + t * (b.lat - a.lat)
      const nlon = a.lon + t * (b.lon - a.lon)
      const d = haversineMiles(p, { lat: nlat, lon: nlon })
      if (d < best) {
        best = d
        bestPt = { lat: nlat, lon: nlon }
      }
    }
  }
  return bestPt
}


