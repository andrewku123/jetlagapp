import polygonClipping, { type MultiPolygon, type Polygon, type Ring } from 'polygon-clipping'
import type { LatLng, QuestionRecord } from '../types'
import { POI_BY_CATEGORY, nearestPoi, nearestPoiMiles, poiKey } from './poi'
import { distanceToFeatureMiles, featurePolylines } from './measureFeatures'
import { AIRPORTS, nearestAirport } from './airports'
import { countyAt, countyGeom } from './counties'
import { cityAt, cityGeom } from './cities'
import { haversineMiles } from './geo'

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
// The regular n-gon is inflated to the mean of its inscribed and circumscribed
// radius so it straddles the true circle, halving the worst-case radial error —
// keeps boundary stations on the correct side of the shading.
function diskRing(c: LatLng, radiusMiles: number, n: number): Ring {
  const cosLat = Math.cos((c.lat * Math.PI) / 180) || 1e-6
  const r = radiusMiles * DEG_PER_MILE * ((1 + 1 / Math.cos(Math.PI / n)) / 2)
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

// Snap a ring's vertices to a coordinate grid. polygon-clipping's sweep line can
// hit an "infinite loop over endpoints" on chains of overlapping circles (as a
// corridor of disks along a wiggly coastline produces); snapping to a coarse grid
// removes the near-coincident intersections that trigger it.
function snapRing(ring: Ring, dp: number): Ring {
  const f = 10 ** dp
  return ring.map(([x, y]) => [Math.round(x * f) / f, Math.round(y * f) / f])
}

// Union many polygons robustly: fold them in one at a time (more stable than one
// big multi-arg union) and snap coordinates, retrying at coarser precision if the
// clipper throws. Returns [] only if every precision fails.
function robustUnion(polys: Polygon[]): MultiPolygon {
  if (polys.length === 0) return []
  for (const dp of [7, 6, 5, 4]) {
    try {
      let acc: MultiPolygon = [polys[0].map((r) => snapRing(r, dp))]
      for (let i = 1; i < polys.length; i++) {
        acc = polygonClipping.union(acc, [polys[i].map((r) => snapRing(r, dp))])
      }
      return acc
    } catch {
      // coarser snap on the next pass
    }
  }
  return []
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

// Finite lon/lat box the Voronoi cells are bounded to. A Voronoi cell can be an
// unbounded wedge; without a finite frame it extends to absurd coordinates and,
// once clipped to the world (lat ±85), renders as a giant triangle/bowtie across
// the map. This box comfortably wraps the play area (bbox -122.7,37.0 →
// -121.4,38.2) with padding, so every cell is a sane bounded polygon and the edge
// of the frame sits well off-screen.
const CELL_FRAME = { minLon: -124, minLat: 36, maxLon: -120, maxLat: 39 }

// The Voronoi cell of `sites[idx]` — the region closer to it than to any other
// site — as a [lon, lat] ring, clipped to CELL_FRAME. Computed in an
// equirectangular projection scaled at `refLat` so distances read straight-line,
// matching the elimination engine.
function voronoiCellRing(sites: LatLng[], idx: number, refLat: number): Ring | null {
  const cosRef = Math.cos((refLat * Math.PI) / 180) || 1e-6
  const proj = (p: LatLng): P2 => ({ x: p.lon * cosRef, y: p.lat })
  const p0 = proj(sites[idx])
  const bl = proj({ lat: CELL_FRAME.minLat, lon: CELL_FRAME.minLon })
  const tr = proj({ lat: CELL_FRAME.maxLat, lon: CELL_FRAME.maxLon })
  let poly: P2[] = [
    { x: bl.x, y: bl.y },
    { x: tr.x, y: bl.y },
    { x: tr.x, y: tr.y },
    { x: bl.x, y: tr.y },
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
  if (count > 800) return 24
  if (count > 200) return 32
  return 48
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

// --- Measuring a linear feature (coastline / borders): shade the corridor
// within the seeker's own distance of the feature, or its complement. -----------

// Resample a polyline to points spaced ~`spacingMiles` apart along its length
// (endpoints always kept). Used to seed the corridor's union of disks.
function resamplePolyline(line: LatLng[], spacingMiles: number): LatLng[] {
  if (line.length < 2) return line.slice()
  const out: LatLng[] = [line[0]]
  let carry = 0
  for (let i = 1; i < line.length; i++) {
    const a = line[i - 1]
    const b = line[i]
    const segLen = haversineMiles(a, b)
    if (segLen === 0) continue
    let dpos = spacingMiles - carry
    while (dpos < segLen) {
      const t = dpos / segLen
      out.push({ lat: a.lat + t * (b.lat - a.lat), lon: a.lon + t * (b.lon - a.lon) })
      dpos += spacingMiles
    }
    carry = (carry + segLen) % spacingMiles
    out.push(b)
  }
  return out
}

export function featureMeasureEliminatedRegion(record: QuestionRecord): LatLngMultiPolygon | null {
  const p = record.params
  const key = String(p.feature)
  const lines = featurePolylines(key)
  if (!lines.length) return null
  const seeker: LatLng = { lat: Number(p.fromLat), lon: Number(p.fromLon) }
  const d = distanceToFeatureMiles(seeker, key)
  if (!Number.isFinite(d) || d <= 0) return null
  // Sample density: fine enough that adjacent disks overlap, but capped so a
  // seeker sitting almost on the feature doesn't spawn thousands of tiny disks.
  const totalLen = lines.reduce((sum, l) => {
    for (let i = 1; i < l.length; i++) sum += haversineMiles(l[i - 1], l[i])
    return sum
  }, 0)
  const spacing = Math.max(d * 0.4, totalLen / 900, 0.35)
  const pts: LatLng[] = []
  for (const l of lines) pts.push(...resamplePolyline(l, spacing))
  if (!pts.length) return null
  const disks: Polygon[] = pts.map((c) => [diskRing(c, d, 20)])
  const union = robustUnion(disks)
  if (!union.length) return null
  // Closer keeps stations within d of the feature (inside the corridor) →
  // eliminate the complement; Further keeps outside → eliminate the corridor.
  const closer = p.answer === 'closer'
  const elim = closer ? polygonClipping.difference([WORLD_RING], union) : union
  return elim.length ? toLatLng(elim) : null
}

// --- Matching a nearest airport: shade outside (Yes) / inside (No) the seeker's
// airport Voronoi cell (only 3 airports → clean thirds). ------------------------

export function airportMatchEliminatedRegion(record: QuestionRecord): LatLngMultiPolygon | null {
  const p = record.params
  const seeker: LatLng = { lat: Number(p.fromLat), lon: Number(p.fromLon) }
  if (!Number.isFinite(seeker.lat) || !Number.isFinite(seeker.lon)) return null
  const codes = Object.keys(AIRPORTS)
  const sites = codes.map((c) => AIRPORTS[c])
  const idx = codes.indexOf(nearestAirport(seeker).code)
  if (idx < 0) return null
  const cell = voronoiCellRing(sites, idx, seeker.lat)
  if (!cell) return null
  const cellPoly: Polygon = [cell]
  const yes = p.answer === 'yes'
  const elim = yes
    ? polygonClipping.difference([WORLD_RING], cellPoly)
    : polygonClipping.intersection([WORLD_RING], cellPoly)
  return elim.length ? toLatLng(elim) : null
}

// --- Measuring a nearest airport: shade the union of your-distance disks around
// the airports, or its complement. ----------------------------------------------

export function airportMeasureEliminatedRegion(record: QuestionRecord): LatLngMultiPolygon | null {
  const p = record.params
  const seeker: LatLng = { lat: Number(p.fromLat), lon: Number(p.fromLon) }
  if (!Number.isFinite(seeker.lat) || !Number.isFinite(seeker.lon)) return null
  const d = nearestAirport(seeker).distMiles
  if (!Number.isFinite(d) || d <= 0) return null
  const disks: Polygon[] = Object.values(AIRPORTS).map((a) => [diskRing(a, d, 48)])
  const union = robustUnion(disks)
  if (!union.length) return null
  const closer = p.answer === 'closer'
  const elim = closer ? polygonClipping.difference([WORLD_RING], union) : union
  return elim.length ? toLatLng(elim) : null
}

// --- Matching a county (2nd admin): shade outside (Yes) / inside (No) the
// seeker's county polygon. -------------------------------------------------------

export function countyMatchEliminatedRegion(record: QuestionRecord): LatLngMultiPolygon | null {
  const p = record.params
  const seeker: LatLng = { lat: Number(p.fromLat), lon: Number(p.fromLon) }
  // Prefer the stored county, falling back to a point-in-polygon lookup.
  const name = String(p.value || '') || countyAt(seeker) || ''
  const geom = countyGeom(name)
  if (!geom.length) return null
  const yes = p.answer === 'yes'
  const elim = yes
    ? polygonClipping.difference([WORLD_RING], geom)
    : polygonClipping.intersection([WORLD_RING], geom)
  return elim.length ? toLatLng(elim) : null
}

// --- Matching a city (3rd admin): shade outside (Yes) / inside (No) the
// seeker's city polygon. -----------------------------------------------------

export function cityMatchEliminatedRegion(record: QuestionRecord): LatLngMultiPolygon | null {
  const p = record.params
  const seeker: LatLng = { lat: Number(p.fromLat), lon: Number(p.fromLon) }
  const name = String(p.value || '') || cityAt(seeker) || ''
  const geom = cityGeom(name)
  if (!geom.length) return null
  const yes = p.answer === 'yes'
  const elim = yes
    ? polygonClipping.difference([WORLD_RING], geom)
    : polygonClipping.intersection([WORLD_RING], geom)
  return elim.length ? toLatLng(elim) : null
}

// Eliminated region for any shaded question record, or null if it has none.
export function poiEliminatedRegion(record: QuestionRecord): LatLngMultiPolygon | null {
  if (!record.active || record.vetoed || !record.eliminates) return null
  if (record.kind === 'match-poi') return poiMatchEliminatedRegion(record)
  if (record.kind === 'measure-poi') return poiMeasureEliminatedRegion(record)
  if (record.kind === 'measure-feature') return featureMeasureEliminatedRegion(record)
  if (record.kind === 'match-airport') return airportMatchEliminatedRegion(record)
  if (record.kind === 'measure-airport') return airportMeasureEliminatedRegion(record)
  if (record.kind === 'match-county') return countyMatchEliminatedRegion(record)
  if (record.kind === 'match-city') return cityMatchEliminatedRegion(record)
  return null
}
