import type { LatLng } from '../types'
import type { Polygon as ClipPolygon, Ring } from 'polygon-clipping'
import { placesData as placesRaw, playAreaData as playAreaRaw } from '../data/regions'

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
const SNAP_M = 150

function buildCities(): Record<string, CityPolys> {
  const out: Record<string, CityPolys> = {}
  const fc = placesRaw as unknown as { features: GeoFeature[] }
  for (const f of fc.features) {
    const name = f.properties.name
    const g = f.geometry
    const polys: CityPolys = []
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

const CITIES: Record<string, CityPolys> = buildCities()

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
