import type { LatLng } from '../types'
import type { Polygon as ClipPolygon, Ring } from 'polygon-clipping'
import { placesData as placesRaw, playAreaData as playAreaRaw, CITY_SNAP_M } from '../data/regions'

// Census-place (3rd-admin / "city") polygons used by the "Matching — city"
// question. Both the seeker's city (from their coordinate) and each station's
// city are resolved through the SAME cityAt() lookup, so the eliminated-area
// shading (the seeker's city polygon) always agrees with which stations are
// kept. Geometry is GeoJSON [lon, lat] = polygon-clipping x/y order. Names are
// the Census NAMELSAD (e.g. "Oakland city", "Ashland CDP").

type CityPolys = ClipPolygon[]

interface GeoFeature {
  properties: { name: string }
  geometry: { type: string; coordinates: number[][][] | number[][][][] }
}

// A station/seeker point this far (metres) outside every polygon still snaps to
// the nearest place — absorbs shoreline-clip / simplification erosion at
// boundaries (e.g. a station sitting ~100 m outside its city outline). Genuinely
// unincorporated points (e.g. SFO airport land, ~300 m+ from any city) stay null.
// Per-region (see RegionData.citySnapM): LA uses a tight value so county-island
// gaps aren't wrongly snapped into a neighbouring city.
const SNAP_M = CITY_SNAP_M

function readPolys(f: GeoFeature): CityPolys {
  const g = f.geometry
  const polys: CityPolys = []
  if (g.type === 'Polygon') {
    polys.push((g.coordinates as number[][][]).map((r) => r as Ring))
  } else if (g.type === 'MultiPolygon') {
    for (const poly of g.coordinates as number[][][][]) {
      polys.push(poly.map((r) => r as Ring))
    }
  }
  return polys
}

// The play-area polygon (union of kept places + transit-line bridges + filled
// enclaves — see scripts/build_play_area.py). Parts of it are genuinely
// unincorporated (a BART corridor over the hills, an enclave the census-place
// set doesn't name), so a point can be inside the play area yet inside no city
// polygon — those read as "unincorporated" rather than "outside the play area".
function buildPlayArea(): CityPolys {
  const fc = playAreaRaw as unknown as { features: GeoFeature[] }
  const polys: CityPolys = []
  for (const f of fc.features) {
    const g = f.geometry
    if (g.type === 'Polygon') {
      polys.push((g.coordinates as number[][][]).map((r) => r as Ring))
    } else if (g.type === 'MultiPolygon') {
      for (const poly of g.coordinates as number[][][][]) {
        polys.push(poly.map((r) => r as Ring))
      }
    }
  }
  return polys
}

const PLAY_AREA: CityPolys = buildPlayArea()

function ringBounds(ring: Ring): [number, number, number, number] {
  let minX = Infinity
  let minY = Infinity
  let maxX = -Infinity
  let maxY = -Infinity
  for (const [x, y] of ring) {
    if (x < minX) minX = x
    if (x > maxX) maxX = x
    if (y < minY) minY = y
    if (y > maxY) maxY = y
  }
  return [minX, minY, maxX, maxY]
}

// A place's polygon can enclose land the place itself excludes. Two kinds:
// another municipality (Newark inside Fremont, Piedmont inside Oakland, Beverly
// Hills inside LA), and an unnamed inholding the Census outline simply omits
// (a 31-acre parcel inside Fort Belvoir CDP). The first must stay a hole — it
// is a different answer to "same municipality?". The second must NOT: cityAt()
// snaps a point there to the surrounding place, so leaving the hole makes the
// shading contradict the answer the app just gave (you're told "Fort Belvoir"
// while standing on unshaded ground). Fill those, so lookup and shading are the
// same geometry. A hole reaching outside the play area is left alone — that land
// is off-map, not part of any city.
function fillUnclaimedHoles(raw: Record<string, CityPolys>): Record<string, CityPolys> {
  // Outer rings of every place, with bounds, so the "does another place sit in
  // this hole?" test is a box check before any ray-casting (this runs at module
  // load, before first render).
  const outers: { name: string; ring: Ring; box: [number, number, number, number] }[] = []
  for (const [name, polys] of Object.entries(raw)) {
    for (const poly of polys) outers.push({ name, ring: poly[0], box: ringBounds(poly[0]) })
  }
  const out: Record<string, CityPolys> = {}
  for (const [name, polys] of Object.entries(raw)) {
    out[name] = polys.map((poly) => {
      if (poly.length < 2) return poly
      const kept: Ring[] = [poly[0]]
      for (let h = 1; h < poly.length; h++) {
        const hole = poly[h]
        const [hx0, hy0, hx1, hy1] = ringBounds(hole)
        const mid = { lat: (hy0 + hy1) / 2, lon: (hx0 + hx1) / 2 }
        const midInHole = pointInRing(mid, hole)
        const holdsPlace = outers.some(({ name: other, ring, box }) => {
          if (other === name) return false
          if (box[2] < hx0 || box[0] > hx1 || box[3] < hy0 || box[1] > hy1) return false
          // Either the hole is (part of) that place, or that place swallows it.
          return (
            ring.some(([x, y]) => pointInRing({ lat: y, lon: x }, hole)) ||
            (midInHole && pointInRing(mid, ring))
          )
        })
        // Sampled rather than exhaustive: a hole is either wholly inside the
        // play area or clearly straddles its edge.
        const step = Math.max(1, Math.floor(hole.length / 16))
        let inPlay = true
        for (let i = 0; i < hole.length && inPlay; i += step) {
          inPlay = pointInPolys({ lat: hole[i][1], lon: hole[i][0] }, PLAY_AREA)
        }
        if (holdsPlace || !inPlay) kept.push(hole)
      }
      return kept
    })
  }
  return out
}

const CITIES: Record<string, CityPolys> = fillUnclaimedHoles(
  Object.fromEntries(
    (placesRaw as unknown as { features: GeoFeature[] }).features.map(
      (f) => [f.properties.name, readPolys(f)] as const,
    ),
  ),
)

export function cityNames(): string[] {
  return Object.keys(CITIES)
}

// polygon-clipping-ready geometry (a MultiPolygon) for one city, or [] if none.
export function cityGeom(name: string): CityPolys {
  return CITIES[name] ?? []
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

function pointInPolys(p: LatLng, polys: CityPolys): boolean {
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

function distToPolysM(p: LatLng, polys: CityPolys): number {
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

// Whether `p` is inside the play area (used to tell "unincorporated" — in play
// but in no named place — apart from "outside the play area").
export function inPlayArea(p: LatLng): boolean {
  return pointInPolys(p, PLAY_AREA)
}

// The Census place (city / town / CDP) containing `p`, snapping to the nearest
// place within SNAP_M to absorb boundary/simplification erosion; otherwise null.
// A null result inside the play area is unincorporated land (a transit corridor
// over the hills, filled bay water); outside it is off-map. Every hiding station
// resolves to a place (the SFO stops fold into San Francisco), so only a seeker
// coordinate can be null.
export function cityAt(p: LatLng): string | null {
  for (const [name, polys] of Object.entries(CITIES)) {
    if (pointInPolys(p, polys)) return name
  }
  let best: string | null = null
  let bestD = SNAP_M
  for (const [name, polys] of Object.entries(CITIES)) {
    const d = distToPolysM(p, polys)
    if (d < bestD) {
      bestD = d
      best = name
    }
  }
  return best
}
