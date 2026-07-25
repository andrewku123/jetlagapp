import type { LatLng } from '../types'
import type { Polygon as ClipPolygon, Ring } from 'polygon-clipping'
import { zctasData as zctasRaw } from '../data/regions'

// ZCTA (ZIP Code Tabulation Area) polygons used by the "Measuring — ZIP code"
// question. Both the seeker's ZIP (from their coordinate) and each station's ZIP
// are resolved through the SAME zipAt() lookup, so the eliminated-area shading
// (the union of ZCTAs on the kept side) always agrees with which stations are
// kept. Geometry is GeoJSON [lon, lat] = polygon-clipping x/y order. Names are
// the 5-digit ZIP (Census ZCTA5CE20, e.g. "94103"). ZIP codes are only ordinal
// in the US, so this dataset (and question) is US-only.

type ZipPolys = ClipPolygon[]

interface GeoFeature {
  properties: { name: string }
  geometry: { type: string; coordinates: number[][][] | number[][][][] }
}

// A station/seeker point this far (metres) outside every ZCTA still snaps to the
// nearest one — absorbs shoreline-clip / simplification erosion at boundaries.
const SNAP_M = 200

function buildZips(): Record<string, ZipPolys> {
  const out: Record<string, ZipPolys> = {}
  const fc = zctasRaw as unknown as { features: GeoFeature[] }
  for (const f of fc.features) {
    const name = f.properties.name
    const g = f.geometry
    const polys: ZipPolys = []
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

const ZIPS: Record<string, ZipPolys> = buildZips()

export function zipCodes(): string[] {
  return Object.keys(ZIPS)
}

// polygon-clipping-ready geometry (a MultiPolygon) for one ZIP, or [] if none.
export function zipGeom(name: string): ZipPolys {
  return ZIPS[name] ?? []
}

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

function pointInPolys(p: LatLng, polys: ZipPolys): boolean {
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

// Metres between a point and a [lon, lat] segment, via a local equirectangular
// projection (fine at these distances).
function distToSegM(p: LatLng, a: number[], b: number[]): number {
  const mPerDegLat = 111320
  const mPerDegLon = 111320 * Math.cos((p.lat * Math.PI) / 180)
  const px = p.lon * mPerDegLon
  const py = p.lat * mPerDegLat
  const ax = a[0] * mPerDegLon
  const ay = a[1] * mPerDegLat
  const bx = b[0] * mPerDegLon
  const by = b[1] * mPerDegLat
  const dx = bx - ax
  const dy = by - ay
  const len2 = dx * dx + dy * dy
  let t = len2 === 0 ? 0 : ((px - ax) * dx + (py - ay) * dy) / len2
  t = Math.max(0, Math.min(1, t))
  const cx = ax + t * dx
  const cy = ay + t * dy
  return Math.hypot(px - cx, py - cy)
}

function distToPolysM(p: LatLng, polys: ZipPolys): number {
  let best = Infinity
  for (const poly of polys) {
    for (const ring of poly) {
      for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
        const d = distToSegM(p, ring[j], ring[i])
        if (d < best) best = d
      }
    }
  }
  return best
}

// The ZCTA ZIP containing `p`, snapping to the nearest ZCTA within SNAP_M to
// absorb boundary/simplification erosion; otherwise null (outside the play area).
export function zipAt(p: LatLng): string | null {
  for (const [name, polys] of Object.entries(ZIPS)) {
    if (pointInPolys(p, polys)) return name
  }
  let best: string | null = null
  let bestD = SNAP_M
  for (const [name, polys] of Object.entries(ZIPS)) {
    const d = distToPolysM(p, polys)
    if (d < bestD) {
      bestD = d
      best = name
    }
  }
  return best
}
