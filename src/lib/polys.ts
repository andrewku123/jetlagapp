import type { LatLng } from '../types'
import type { Polygon as ClipPolygon, Ring } from 'polygon-clipping'

// Named-polygon layers (counties, states, …): the same GeoJSON FeatureCollection
// shape, looked up by point and handed to polygon-clipping for shading. Geometry
// is GeoJSON [lon, lat], which is already polygon-clipping's x/y order.

// A polygon-clipping Polygon is [outerRing, ...holes]; a named area may be
// several (islands), so each name maps to a list of polygons (a MultiPolygon).
export type NamedPolys = ClipPolygon[]

interface GeoFeature {
  properties: { name: string }
  geometry: { type: string; coordinates: number[][][] | number[][][][] }
}

/** name → MultiPolygon, from a FeatureCollection whose features carry a name. */
export function polysByName(raw: unknown): Record<string, NamedPolys> {
  const out: Record<string, NamedPolys> = {}
  const fc = raw as { features: GeoFeature[] }
  for (const f of fc.features) {
    const g = f.geometry
    const polys: NamedPolys = []
    if (g.type === 'Polygon') {
      polys.push((g.coordinates as number[][][]).map((r) => r as Ring))
    } else if (g.type === 'MultiPolygon') {
      for (const poly of g.coordinates as number[][][][]) polys.push(poly.map((r) => r as Ring))
    }
    out[f.properties.name] = polys
  }
  return out
}

// Ray-cast point-in-ring on a [lon, lat] ring.
function pointInRing(p: LatLng, ring: Ring): boolean {
  let inside = false
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i]
    const [xj, yj] = ring[j]
    const intersect = yi > p.lat !== yj > p.lat && p.lon < ((xj - xi) * (p.lat - yi)) / (yj - yi) + xi
    if (intersect) inside = !inside
  }
  return inside
}

/** Is `p` inside the MultiPolygon (outer ring, and not in one of its holes)? */
export function pointInPolys(p: LatLng, polys: NamedPolys): boolean {
  for (const poly of polys) {
    if (!pointInRing(p, poly[0])) continue
    let inHole = false
    for (let h = 1; h < poly.length; h++) if (pointInRing(p, poly[h])) inHole = true
    if (!inHole) return true
  }
  return false
}
