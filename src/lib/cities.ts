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

// Whether `p` is inside the play area (used to tell "unincorporated" — in play
// but in no named place — apart from "outside the play area").
export function inPlayArea(p: LatLng): boolean {
  return pointInPolys(p, PLAY_AREA)
}

// What the UI shows where cityAt() is null and the point is in play. "No city"
// rather than "Unincorporated": many named places here (Bethesda, McLean,
// Tysons, Fairview) are unincorporated CDPs that DO answer the question, so that
// word describes the wrong thing — what matters to a seeker is that there is no
// municipality to match.
export const NO_CITY_LABEL = 'No city'

// The Census place (city / town / CDP) whose polygon contains `p`, or null.
// Strictly inside-the-polygon: the boundary is the answer to "same municipality?",
// so land a place excludes — the gaps between places, and the inholdings their
// outlines cut out (Accotink inside Fort Belvoir) — must read as unincorporated
// rather than borrow a neighbour's name. A null inside the play area is
// unincorporated land, outside it is off-map; the question form tells them apart.
// Stations resolve through this same lookup, so a station on unincorporated land
// (Colma, Bayshore/NASA, Del Amo, New Carrollton) is null too and can only be
// kept by "no".
export function cityAt(p: LatLng): string | null {
  for (const [name, polys] of Object.entries(CITIES)) {
    if (pointInPolys(p, polys)) return name
  }
  return null
}
