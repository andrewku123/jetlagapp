import type { LatLng } from '../types'
import rawGeo from '../data/transit-lines.geojson.json'
import rawStations from '../data/stations.json'
import type { Station } from '../types'

// Metro Lines tentacle: the physical, colour-coded transit lines drawn on the
// map (one per GeoJSON feature). Unlike the POI tentacles these are line
// geometry, so "within R of the seeker" means the line passes within R miles,
// and the hider's answer is which in-play line is closest to them. Everything is
// derived from the same transit geometry + station line names the app already
// ships, so it generalises to any city that has both.

const MILES_PER_DEG = 69.0

// Fixed radius for the Metro Lines tentacle (Large games only).
export const METRO_TENTACLE_RADIUS_MI = 15

export interface MetroLine {
  id: string // stable, geometry-derived key: `${system}::${color}`
  system: string
  color: string
  name: string // full line name from station.lines, e.g. "BART Yellow (Antioch–SFO/Millbrae)"
  label: string // cleaned display name, e.g. "BART Yellow"
  polylines: LatLng[][]
}

interface RawFeature {
  properties: { system: string; colors: string[] }
  geometry:
    | { type: 'LineString'; coordinates: number[][] }
    | { type: 'MultiLineString'; coordinates: number[][][] }
}

function segmentsOf(f: RawFeature): number[][][] {
  return f.geometry.type === 'LineString' ? [f.geometry.coordinates] : f.geometry.coordinates
}

function toPolylines(f: RawFeature): LatLng[][] {
  return segmentsOf(f).map((seg) => seg.map(([lon, lat]) => ({ lat, lon })))
}

// Distance (miles) from p to a single a–b segment in an equirectangular
// projection scaled at cosRef (matches the shading + feature-distance metric).
function projDistToSegmentMiles(p: LatLng, a: LatLng, b: LatLng, cosRef: number): number {
  const ax = (a.lon - p.lon) * cosRef
  const ay = a.lat - p.lat
  const bx = (b.lon - p.lon) * cosRef
  const by = b.lat - p.lat
  const dx = bx - ax
  const dy = by - ay
  const len2 = dx * dx + dy * dy
  let t = len2 > 0 ? -(ax * dx + ay * dy) / len2 : 0
  if (t < 0) t = 0
  else if (t > 1) t = 1
  const cx = ax + t * dx
  const cy = ay + t * dy
  return Math.hypot(cx, cy) * MILES_PER_DEG
}

// Projected distance (miles) from p to the whole line, at reference latitude
// refLat. Both the seeker's in-play radius and every station's nearest-line
// distance use this so elimination and the shaded region agree.
export function metroLineDistanceMiles(p: LatLng, line: MetroLine, refLat: number): number {
  const cosRef = Math.cos((refLat * Math.PI) / 180) || 1e-6
  let best = Infinity
  for (const poly of line.polylines) {
    for (let i = 1; i < poly.length; i++) {
      const d = projDistToSegmentMiles(p, poly[i - 1], poly[i], cosRef)
      if (d < best) best = d
    }
  }
  return best
}

// Derive each feature's line name from the station set: the station-line whose
// member stations have the smallest mean distance to the feature is its name.
// Purely for display/identity — correctness of elimination/shading only depends
// on the geometry. Runs once at module load.
function deriveNames(features: RawFeature[]): string[] {
  const stations = rawStations as unknown as Station[]
  const byLine = new Map<string, LatLng[]>()
  for (const s of stations) {
    for (const l of s.lines ?? []) {
      const arr = byLine.get(l) ?? []
      arr.push({ lat: s.lat, lon: s.lon })
      byLine.set(l, arr)
    }
  }
  const names = [...byLine.keys()]
  // reference latitude = mean of all feature vertices
  let latSum = 0
  let latN = 0
  for (const f of features)
    for (const seg of segmentsOf(f))
      for (const [, lat] of seg) {
        latSum += lat
        latN++
      }
  const refLat = latN ? latSum / latN : 0
  const cosRef = Math.cos((refLat * Math.PI) / 180) || 1e-6
  return features.map((f) => {
    let best = Infinity
    let bestName = `${f.properties.system} line`
    for (const nm of names) {
      const pts = byLine.get(nm)!
      let sum = 0
      for (const p of pts) {
        let d = Infinity
        for (const seg of segmentsOf(f)) {
          for (let i = 1; i < seg.length; i++) {
            const dd = projDistToSegmentMiles(
              p,
              { lat: seg[i - 1][1], lon: seg[i - 1][0] },
              { lat: seg[i][1], lon: seg[i][0] },
              cosRef,
            )
            if (dd < d) d = dd
          }
        }
        sum += d
      }
      const mean = sum / pts.length
      if (mean < best) {
        best = mean
        bestName = nm
      }
    }
    return bestName
  })
}

function buildMetroLines(): MetroLine[] {
  const features = (rawGeo as { features: RawFeature[] }).features
  const names = deriveNames(features)
  return features.map((f, i) => {
    const system = f.properties.system
    const color = f.properties.colors[0]
    const name = names[i]
    const label = name.replace(/\s*\(.*\)\s*$/, '').trim() // drop the "(Antioch–SFO…)" tail
    return { id: `${system}::${color}`, system, color, name, label, polylines: toPolylines(f) }
  })
}

export const METRO_LINES: MetroLine[] = buildMetroLines()

export const METRO_LINE_BY_ID: Record<string, MetroLine> = Object.fromEntries(
  METRO_LINES.map((l) => [l.id, l]),
)

// Lines passing within radiusMi of the seeker (the in-play set).
export function metroLinesWithinRadius(seeker: LatLng, radiusMi: number, refLat = seeker.lat): MetroLine[] {
  return METRO_LINES.filter((l) => metroLineDistanceMiles(seeker, l, refLat) <= radiusMi)
}

// The line in `lines` nearest to p (and its distance). null if `lines` empty.
export function nearestMetroLine(
  p: LatLng,
  lines: MetroLine[],
  refLat: number,
): { line: MetroLine; d: number } | null {
  let best: { line: MetroLine; d: number } | null = null
  for (const line of lines) {
    const d = metroLineDistanceMiles(p, line, refLat)
    if (!best || d < best.d) best = { line, d }
  }
  return best
}
