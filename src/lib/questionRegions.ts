import polygonClipping, { type MultiPolygon, type Polygon, type Ring } from 'polygon-clipping'
import type { LatLng, QuestionRecord } from '../types'
import { POI_BY_CATEGORY, nearestPoi, nearestPoiMiles, poiKey } from './poi'
import { projectedDistanceToFeatureMiles, featurePolylines } from './measureFeatures'
import { AIRPORTS, nearestAirport } from './airports'
import { countyAt, countyGeom } from './counties'
import { cityAt, cityGeom } from './cities'
import { bisectorHalfPlane } from './geo'

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

// Buffer polylines by `radiusMiles` into the union "within radius of the line",
// as a [lon, lat] MultiPolygon. Each segment contributes a rectangle whose two
// long edges sit exactly `radiusMiles` off the segment, plus a disk at each
// vertex to round the corners. Because the far edges are exact straight lines
// (not sampled disk arcs) the shaded boundary lands precisely at the measured
// distance, so it agrees with the per-station distance test — no scallop error.
// Geometry is built in an equirectangular projection scaled at `refLat`, matching
// the elimination engine's local straight-line distances.
function bufferPolylines(lines: LatLng[][], radiusMiles: number, refLat: number): MultiPolygon {
  const cosRef = Math.cos((refLat * Math.PI) / 180) || 1e-6
  const r = radiusMiles * DEG_PER_MILE
  // Round the vertex caps finely enough that their worst-case radial error
  // (straddling the true circle) stays under ~0.02 mi even for a 400+ mi radius,
  // where a coarse n-gon's flat edge would otherwise fall a mile or two short of
  // the true distance and wrongly exclude near-boundary stations.
  const EPS_MILES = 0.02
  const capN = Math.max(24, Math.min(512, Math.ceil((Math.PI / 2) * Math.sqrt(radiusMiles / EPS_MILES))))
  const rCap = r * ((1 + 1 / Math.cos(Math.PI / capN)) / 2)
  const polys: Polygon[] = []
  const capRing = (cx: number, cy: number): Ring => {
    const ring: Ring = []
    for (let i = 0; i < capN; i++) {
      const t = (i / capN) * 2 * Math.PI
      ring.push([cx + rCap * Math.cos(t), cy + rCap * Math.sin(t)])
    }
    return ring
  }
  for (const line of lines) {
    const pv = line.map((p) => [p.lon * cosRef, p.lat] as [number, number])
    for (let i = 1; i < pv.length; i++) {
      const [ax, ay] = pv[i - 1]
      const [bx, by] = pv[i]
      let ux = bx - ax
      let uy = by - ay
      const len = Math.hypot(ux, uy)
      if (len < 1e-12) continue
      ux /= len
      uy /= len
      const nx = -uy * r
      const ny = ux * r
      polys.push([
        [
          [ax + nx, ay + ny],
          [bx + nx, by + ny],
          [bx - nx, by - ny],
          [ax - nx, ay - ny],
        ],
      ])
    }
    for (const [vx, vy] of pv) polys.push([capRing(vx, vy)])
  }
  const union = robustUnion(polys)
  return union.map((poly) =>
    poly.map((ring) => ring.map(([x, y]) => [x / cosRef, y] as [number, number])),
  )
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

// Union many polygons robustly. Snap coordinates (the clipper's sweep line can
// hit an "infinite loop over endpoints" on chains of overlapping circles) and
// combine divide-and-conquer — pairwise up a balanced tree — which keeps the
// intermediate polygons small instead of repeatedly re-clipping one giant
// accumulator, turning an O(n²) fold into ~O(n log n). Retries at coarser
// precision if the clipper throws. Returns [] only if every precision fails.
function robustUnion(polys: Polygon[]): MultiPolygon {
  if (polys.length === 0) return []
  for (const dp of [7, 6, 5, 4]) {
    try {
      let layer: MultiPolygon[] = polys.map((p) => [p.map((r) => snapRing(r, dp))])
      while (layer.length > 1) {
        const next: MultiPolygon[] = []
        for (let i = 0; i < layer.length; i += 2) {
          next.push(i + 1 < layer.length ? polygonClipping.union(layer[i], layer[i + 1]) : layer[i])
        }
        layer = next
      }
      return layer[0]
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

export function featureMeasureEliminatedRegion(record: QuestionRecord): LatLngMultiPolygon | null {
  const p = record.params
  const key = String(p.feature)
  const lines = featurePolylines(key)
  if (!lines.length) return null
  const seeker: LatLng = { lat: Number(p.fromLat), lon: Number(p.fromLon) }
  // Radius in the same seeker-centred projection as the buffer + elimination.
  const d = projectedDistanceToFeatureMiles(seeker, key, seeker.lat)
  if (!Number.isFinite(d) || d <= 0) return null
  // Exact straight-edged buffer of the feature so the shaded boundary sits
  // precisely at the measured distance and matches the per-station rule.
  const union = bufferPolylines(lines, d, seeker.lat)
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

// --- Endgame: clip a question's eliminated area to the hiding-zone disk. ---------
// In endgame the board collapses to one station + its hiding zone; endgame-phase
// questions (answered from the hider's real position) sub-divide that zone. We
// reuse the exact same eliminated geometry as the map-wide shading and intersect
// it with the zone circle so the shading always agrees with the elimination rule.

// [lat,lon] display multipolygon → [lon,lat] clipping geometry (inverse toLatLng).
function toGeom(mp: LatLngMultiPolygon): MultiPolygon {
  return mp.map((poly) => poly.map((ring) => ring.map(([lat, lon]) => [lon, lat] as [number, number])))
}

// The eliminated region of any auto-eliminating question, in [lon,lat] geometry.
// Radar and thermometer are built here directly (they're otherwise drawn inline in
// MapView); everything else routes through poiEliminatedRegion.
function eliminatedGeom(record: QuestionRecord): MultiPolygon | null {
  if (!record.active || record.vetoed || !record.eliminates) return null
  const p = record.params
  if (record.kind === 'radar') {
    const c: LatLng = { lat: Number(p.lat), lon: Number(p.lon) }
    const rMi = Number(p.radiusMiles)
    if (!Number.isFinite(rMi)) return null
    const disk: Polygon = [diskRing(c, rMi, 96)]
    // Yes = within → eliminate outside the disk; No = eliminate the disk.
    const elim = p.answer === 'yes' ? polygonClipping.difference([WORLD_RING], disk) : [disk]
    return elim.length ? elim : null
  }
  if (record.kind === 'thermometer') {
    const from: LatLng = { lat: Number(p.fromLat), lon: Number(p.fromLon) }
    const to: LatLng = { lat: Number(p.toLat), lon: Number(p.toLon) }
    // Eliminate the half-plane the hider moved away from: cold side.
    const coldSide = p.answer === 'hotter' ? from : to
    const band = bisectorHalfPlane(from, to, coldSide, 400)
    if (!band.length) return null
    const ring: Ring = band.map((pt) => [pt.lon, pt.lat] as [number, number])
    return [[ring]]
  }
  const latlng = poiEliminatedRegion(record)
  return latlng ? toGeom(latlng) : null
}

// A question's eliminated area, intersected with the hiding-zone disk, as a
// display [lat,lon] multipolygon (or null if it doesn't touch the zone).
export function endgameClippedRegion(
  record: QuestionRecord,
  center: LatLng,
  radiusMiles: number,
): LatLngMultiPolygon | null {
  const geom = eliminatedGeom(record)
  if (!geom || !geom.length) return null
  const disk: Polygon = [diskRing(center, radiusMiles, 128)]
  let clipped: MultiPolygon
  try {
    clipped = polygonClipping.intersection(geom, [disk])
  } catch {
    return null
  }
  return clipped.length ? toLatLng(clipped) : null
}
