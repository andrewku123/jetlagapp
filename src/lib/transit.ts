import type { Feature } from 'geojson'

export interface TransitWay {
  type: 'Feature'
  properties: { system: string; colors: string[] }
  geometry: { type: 'LineString'; coordinates: number[][] }
}

// perpendicular spacing between interlined (parallel) tracks, in metres
export const SPACING_M = 16

// Shift a [lon,lat] polyline perpendicular (left of travel) by `meters`, using a
// local metres-per-degree approximation per vertex.
export function offsetLine(coords: number[][], meters: number): number[][] {
  if (meters === 0 || coords.length < 2) return coords
  const n = coords.length
  const out: number[][] = []
  for (let i = 0; i < n; i++) {
    const [lon, lat] = coords[i]
    const [ax, ay] = coords[Math.max(i - 1, 0)]
    const [bx, by] = coords[Math.min(i + 1, n - 1)]
    const mx = 111320 * Math.cos((lat * Math.PI) / 180)
    const my = 110540
    let tx = (bx - ax) * mx
    let ty = (by - ay) * my
    const len = Math.hypot(tx, ty) || 1
    tx /= len
    ty /= len
    const nx = -ty
    const ny = tx
    out.push([lon + (nx * meters) / mx, lat + (ny * meters) / my])
  }
  return out
}

// Expand per-way features into the rendered collection. With interlining on, each
// shared track is drawn once per line color, offset in parallel; off draws one
// line per track (first color wins).
export function buildTransit(ways: TransitWay[], interline: boolean): GeoJSON.FeatureCollection {
  const features: Feature[] = []
  for (const w of ways) {
    const colors = w.properties.colors
    const base = w.geometry.coordinates
    if (interline && colors.length > 1) {
      const k = colors.length
      colors.forEach((color, i) => {
        const off = (i - (k - 1) / 2) * SPACING_M
        features.push({
          type: 'Feature',
          properties: { color },
          geometry: { type: 'LineString', coordinates: offsetLine(base, off) },
        } as Feature)
      })
    } else {
      features.push({
        type: 'Feature',
        properties: { color: colors[0] },
        geometry: { type: 'LineString', coordinates: base },
      } as Feature)
    }
  }
  return { type: 'FeatureCollection', features }
}
