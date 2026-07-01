import polygonClipping, { type MultiPolygon, type Polygon, type Ring } from 'polygon-clipping'
import type { LatLng, QuestionRecord } from '../types'
import { POI_BY_CATEGORY, nearestPoi, nearestPoiMiles, poiKey } from './poi'

// Shaded eliminated regions for the POI Matching / Measuring questions, mirroring
// the radar (circle) and thermometer (half-plane) shading. Geometry is computed
// in [lon, lat] (polygon-clipping's x/y order) and returned as Leaflet-ready
// [lat, lon] positions.

// Multipolygon of [lat, lon] rings: array of polygons, each an outer ring plus
// optional holes. Feeds straight into react-leaflet <Polygon positions=… />.
export type LatLngMultiPolygon = [number, number][][][]

const DEG_PER_MILE = 1 / 69.0

// A near-world outer ring in [lon, lat]; "eliminate everything except X" is this
// minus X.
const WORLD_RING: Ring = [
  [-179.9, -85],
  [179.9, -85],
  [179.9, 85],
  [-179.9, 85],
]

// A geodesic circle (equirectangular, fine at metro scale) as a [lon, lat] ring.
function diskRing(c: LatLng, radiusMiles: number, n: number): Ring {
  const cosLat = Math.cos((c.lat * Math.PI) / 180) || 1e-6
  const r = radiusMiles * DEG_PER_MILE
  const ring: Ring = []
  for (let i = 0; i < n; i++) {
    const t = (i / n) * 2 * Math.PI
    ring.push([c.lon + (r * Math.cos(t)) / cosLat, c.lat + r * Math.sin(t)])
  }
  return ring
}

function toLatLng(mp: MultiPolygon): LatLngMultiPolygon {
  return mp.map((poly) => poly.map((ring) => ring.map(([x, y]) => [y, x] as [number, number])))
}

// --- Matching: shade everything outside (Yes) / inside (No) the seeker's
// nearest-POI Voronoi cell. -----------------------------------------------------

interface P2 {
  x: number
  y: number
}

// Clip a convex polygon to the half-plane a*x + b*y + c <= 0 (Sutherland-Hodgman).
function clipHalfPlane(poly: P2[], a: number, b: number, c: number): P2[] {
  if (poly.length === 0) return poly
  const inside = (p: P2) => a * p.x + b * p.y + c <= 1e-12
  const cut = (p: P2, q: P2): P2 => {
    const fp = a * p.x + b * p.y + c
    const fq = a * q.x + b * q.y + c
    const t = fp / (fp - fq)
    return { x: p.x + t * (q.x - p.x), y: p.y + t * (q.y - p.y) }
  }
  const out: P2[] = []
  for (let i = 0; i < poly.length; i++) {
    const cur = poly[i]
    const prev = poly[(i + poly.length - 1) % poly.length]
    const curIn = inside(cur)
    const prevIn = inside(prev)
    if (curIn) {
      if (!prevIn) out.push(cut(prev, cur))
      out.push(cur)
    } else if (prevIn) {
      out.push(cut(prev, cur))
    }
  }
  return out
}

// The Voronoi cell of `sites[idx]` — the region closer to it than to any other
// site — as a [lon, lat] ring. Computed in an equirectangular projection scaled
// at `refLat` so distances read straight-line, matching the elimination engine.
function voronoiCellRing(sites: LatLng[], idx: number, refLat: number): Ring | null {
  const cosRef = Math.cos((refLat * Math.PI) / 180) || 1e-6
  const proj = (p: LatLng): P2 => ({ x: p.lon * cosRef, y: p.lat })
  const p0 = proj(sites[idx])
  const span = 200 // projected degrees; safely covers the metro before world-clip
  let poly: P2[] = [
    { x: p0.x - span, y: p0.y - span },
    { x: p0.x + span, y: p0.y - span },
    { x: p0.x + span, y: p0.y + span },
    { x: p0.x - span, y: p0.y + span },
  ]
  for (let i = 0; i < sites.length && poly.length >= 3; i++) {
    if (i === idx) continue
    const pi = proj(sites[i])
    // keep the side closer to p0: |x-p0|^2 <= |x-pi|^2
    const a = 2 * (pi.x - p0.x)
    const b = 2 * (pi.y - p0.y)
    const c = -(pi.x * pi.x + pi.y * pi.y - (p0.x * p0.x + p0.y * p0.y))
    poly = clipHalfPlane(poly, a, b, c)
  }
  if (poly.length < 3) return null
  return poly.map((p) => [p.x / cosRef, p.y] as [number, number])
}

export function poiMatchEliminatedRegion(record: QuestionRecord): LatLngMultiPolygon | null {
  const p = record.params
  const cat = String(p.poiCat)
  const list = POI_BY_CATEGORY[cat]
  if (!list || list.length === 0) return null
  const seeker: LatLng = { lat: Number(p.fromLat), lon: Number(p.fromLon) }
  const np = nearestPoi(seeker, cat)
  if (!np) return null
  const target = poiKey(np)
  const idx = list.findIndex((q) => poiKey(q) === target)
  if (idx < 0) return null
  const cell = voronoiCellRing(list, idx, seeker.lat)
  if (!cell) return null
  const cellPoly: Polygon = [cell]
  const yes = p.answer === 'yes'
  // Yes keeps the cell → eliminate outside it; No keeps outside → eliminate the cell.
  const elim = yes
    ? polygonClipping.difference([WORLD_RING], cellPoly)
    : polygonClipping.intersection([WORLD_RING], cellPoly)
  return elim.length ? toLatLng(elim) : null
}

// --- Measuring: shade the union of disks (radius = seeker's own nearest-POI
// distance) around every POI, or its complement. --------------------------------

// Denser categories → more disks to union; cap the segment count so parks stay
// responsive while sparse categories still read as clean circles.
function diskSegments(count: number): number {
  if (count > 800) return 16
  if (count > 200) return 20
  return 28
}

export function poiMeasureEliminatedRegion(record: QuestionRecord): LatLngMultiPolygon | null {
  const p = record.params
  const cat = String(p.poiCat)
  const list = POI_BY_CATEGORY[cat]
  if (!list || list.length === 0) return null
  const seeker: LatLng = { lat: Number(p.fromLat), lon: Number(p.fromLon) }
  const d = nearestPoiMiles(seeker, cat)
  if (!Number.isFinite(d) || d <= 0) return null
  const segs = diskSegments(list.length)
  const disks: Polygon[] = list.map((poi) => [diskRing(poi, d, segs)])
  const union = polygonClipping.union(disks[0], ...disks.slice(1))
  if (!union.length) return null
  // Closer keeps stations within d of some POI (inside the union) → eliminate the
  // complement; Further keeps outside → eliminate the union itself.
  const closer = p.answer === 'closer'
  const elim = closer ? polygonClipping.difference([WORLD_RING], union) : union
  return elim.length ? toLatLng(elim) : null
}

// Eliminated region for any shaded POI question record, or null if it has none.
export function poiEliminatedRegion(record: QuestionRecord): LatLngMultiPolygon | null {
  if (!record.active || record.vetoed || !record.eliminates) return null
  if (record.kind === 'match-poi') return poiMatchEliminatedRegion(record)
  if (record.kind === 'measure-poi') return poiMeasureEliminatedRegion(record)
  return null
}
