import type { MultiPolygon } from 'polygon-clipping'
import type { LatLng } from '../types'

// Answers "does any point of a radius-r disk around p fall inside this region?"
// for a polygon-clipping [lon, lat] MultiPolygon, fast enough to run for every
// station against every logged question. Edges are grouped into blocks with a
// bounding box so most of a large region (a union of 1,500 park disks, a county
// coastline) is skipped without touching its edges.

const MILES_PER_DEG_LAT = (6371000 * Math.PI) / 180 / 1609.344
const BLOCK = 32

export interface RegionIndex {
  // x1, y1, x2, y2 per edge, in [lon, lat]
  edges: Float64Array
  // minX, minY, maxX, maxY per block of BLOCK edges
  boxes: Float64Array
}

export function indexRegion(mp: MultiPolygon): RegionIndex {
  const flat: number[] = []
  for (const poly of mp)
    for (const ring of poly)
      for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
        const [x1, y1] = ring[j]
        const [x2, y2] = ring[i]
        if (x1 === x2 && y1 === y2) continue
        flat.push(x1, y1, x2, y2)
      }
  const edges = Float64Array.from(flat)
  const count = edges.length / 4
  const boxes = new Float64Array(Math.ceil(count / BLOCK) * 4)
  for (let b = 0; b * BLOCK < count; b++) {
    let minX = Infinity
    let minY = Infinity
    let maxX = -Infinity
    let maxY = -Infinity
    for (let e = b * BLOCK; e < Math.min(count, (b + 1) * BLOCK); e++) {
      const o = e * 4
      minX = Math.min(minX, edges[o], edges[o + 2])
      maxX = Math.max(maxX, edges[o], edges[o + 2])
      minY = Math.min(minY, edges[o + 1], edges[o + 3])
      maxY = Math.max(maxY, edges[o + 1], edges[o + 3])
    }
    boxes.set([minX, minY, maxX, maxY], b * 4)
  }
  return { edges, boxes }
}

// Even-odd ray cast over every ring: polygon-clipping output never overlaps
// itself, so holes and separate pieces both come out right.
export function pointInRegion(p: LatLng, idx: RegionIndex): boolean {
  const { edges } = idx
  let inside = false
  for (let o = 0; o < edges.length; o += 4) {
    const x1 = edges[o]
    const y1 = edges[o + 1]
    const x2 = edges[o + 2]
    const y2 = edges[o + 3]
    if (y1 > p.lat !== y2 > p.lat && p.lon < ((x2 - x1) * (p.lat - y1)) / (y2 - y1) + x1) inside = !inside
  }
  return inside
}

// Whether the region comes within `radiusMiles` of p (inside counts as 0).
// Distances are straight-line in an equirectangular frame at p's latitude —
// exact to well under a metre over a hiding zone.
export function regionWithinMiles(p: LatLng, idx: RegionIndex, radiusMiles: number): boolean {
  if (pointInRegion(p, idx)) return true
  if (!(radiusMiles > 0)) return false
  const ky = MILES_PER_DEG_LAT
  const kx = MILES_PER_DEG_LAT * Math.cos((p.lat * Math.PI) / 180)
  const r2 = radiusMiles * radiusMiles
  const { edges, boxes } = idx
  const padLat = radiusMiles / ky
  const padLon = radiusMiles / Math.max(kx, 1e-9)
  for (let b = 0; b < boxes.length / 4; b++) {
    const o = b * 4
    if (p.lon < boxes[o] - padLon || p.lon > boxes[o + 2] + padLon) continue
    if (p.lat < boxes[o + 1] - padLat || p.lat > boxes[o + 3] + padLat) continue
    const end = Math.min(edges.length, (b + 1) * BLOCK * 4)
    for (let e = b * BLOCK * 4; e < end; e += 4) {
      const ax = (edges[e] - p.lon) * kx
      const ay = (edges[e + 1] - p.lat) * ky
      const bx = (edges[e + 2] - p.lon) * kx
      const by = (edges[e + 3] - p.lat) * ky
      const dx = bx - ax
      const dy = by - ay
      const len2 = dx * dx + dy * dy
      const t = len2 > 0 ? Math.max(0, Math.min(1, -(ax * dx + ay * dy) / len2)) : 0
      const cx = ax + t * dx
      const cy = ay + t * dy
      if (cx * cx + cy * cy <= r2) return true
    }
  }
  return false
}
