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

// polyline = list of vertices; a feature is one or more polylines.
type Polyline = LatLng[]

interface GeoJsonFeature {
  properties: { key: string }
  geometry: { type: string; coordinates: number[][][] }
}

function buildPolylines(): Record<string, Polyline[]> {
  const out: Record<string, Polyline[]> = {}
  const fc = featuresRaw as unknown as { features: GeoJsonFeature[] }
  for (const f of fc.features) {
    const key = f.properties.key
    // MultiLineString coords: [ [ [lon,lat], … ], … ]
    out[key] = f.geometry.coordinates.map((line) =>
      line.map(([lon, lat]) => ({ lat, lon })),
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

// Per-station distance is reused across every filter pass, so cache it by
// station id + feature key (geometry is static).
const stationCache = new Map<string, number>()

export function stationFeatureDistanceMiles(
  station: { id: string; lat: number; lon: number },
  key: string,
): number {
  const ck = `${key}:${station.id}`
  const hit = stationCache.get(ck)
  if (hit !== undefined) return hit
  const d = distanceToFeatureMiles({ lat: station.lat, lon: station.lon }, key)
  stationCache.set(ck, d)
  return d
}
