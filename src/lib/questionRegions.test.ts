import { describe, it, expect } from 'vitest'
import { poiCategoryLabel, QUESTION_POI_CATEGORIES, POI_BY_CATEGORY, nearestPoi, nearestPoiMiles, poiKey } from './poi'
import { poiMatchEliminatedRegion, poiMeasureEliminatedRegion, type LatLngMultiPolygon } from './questionRegions'
import type { QuestionRecord } from '../types'

// ray-cast point-in-ring on a [lat, lon] ring
function pointInRing(lat: number, lon: number, ring: [number, number][]): boolean {
  let inside = false
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [yi, xi] = ring[i]
    const [yj, xj] = ring[j]
    const intersect = yi > lat !== yj > lat && lon < ((xj - xi) * (lat - yi)) / (yj - yi) + xi
    if (intersect) inside = !inside
  }
  return inside
}

// point is inside a multipolygon if it's in an outer ring and in an odd number of
// rings overall (outer minus holes)
function pointInMulti(lat: number, lon: number, mp: LatLngMultiPolygon): boolean {
  for (const poly of mp) {
    if (!pointInRing(lat, lon, poly[0])) continue
    let inHole = false
    for (let h = 1; h < poly.length; h++) {
      if (pointInRing(lat, lon, poly[h])) inHole = true
    }
    if (!inHole) return true
  }
  return false
}

function rec(kind: 'match-poi' | 'measure-poi', params: Record<string, unknown>): QuestionRecord {
  return { id: 'q', kind, createdAt: 0, params, eliminates: true, active: true }
}

const SEEKER = { lat: 37.7749, lon: -122.4194 }

describe('poiCategoryLabel', () => {
  it('singularizes -ies plurals (the librarie bug)', () => {
    expect(poiCategoryLabel('library')).toBe('library')
  })
  it('singularizes plain -s plurals and lowercases', () => {
    expect(poiCategoryLabel('museum')).toBe('museum')
    expect(poiCategoryLabel('stadium')).toBe('sports stadium')
    expect(poiCategoryLabel('movie_theater')).toBe('movie theater')
    expect(poiCategoryLabel('consulate')).toBe('consulate')
  })
})

describe('QUESTION_POI_CATEGORIES', () => {
  it('exposes every category we have data for, including the newly added ones', () => {
    for (const k of ['stadium', 'amusement_park', 'zoo', 'aquarium', 'consulate']) {
      expect(QUESTION_POI_CATEGORIES).toContain(k)
    }
  })
  it('only lists categories that actually have baked POIs', () => {
    for (const k of QUESTION_POI_CATEGORIES) {
      expect((POI_BY_CATEGORY[k] ?? []).length).toBeGreaterThan(0)
    }
  })
})

describe('poiMatchEliminatedRegion agrees with the elimination rule', () => {
  const cat = 'stadium' // sparse → big, clean Voronoi cells
  const seekerNearest = nearestPoi(SEEKER, cat)!

  it('YES: shades outside the seeker cell; a same-nearest point is kept (unshaded)', () => {
    const region = poiMatchEliminatedRegion(rec('match-poi', { poiCat: cat, fromLat: SEEKER.lat, fromLon: SEEKER.lon, answer: 'yes' }))!
    expect(region).toBeTruthy()
    // the seeker's own nearest stadium shares the seeker's cell → must NOT be shaded
    expect(pointInMulti(SEEKER.lat, SEEKER.lon, region)).toBe(false)
    // a POI whose nearest stadium differs sits outside the cell → shaded
    const other = POI_BY_CATEGORY[cat].find((p) => poiKey(nearestPoi(p, cat)!) !== poiKey(seekerNearest))!
    expect(pointInMulti(other.lat, other.lon, region)).toBe(true)
  })

  it('NO: shades inside the seeker cell instead', () => {
    const region = poiMatchEliminatedRegion(rec('match-poi', { poiCat: cat, fromLat: SEEKER.lat, fromLon: SEEKER.lon, answer: 'no' }))!
    expect(pointInMulti(SEEKER.lat, SEEKER.lon, region)).toBe(true)
  })
})

describe('poiMeasureEliminatedRegion agrees with the elimination rule', () => {
  const cat = 'hospital'
  const d = nearestPoiMiles(SEEKER, cat)

  it('CLOSER: shades outside the union of your-distance circles', () => {
    const region = poiMeasureEliminatedRegion(rec('measure-poi', { poiCat: cat, fromLat: SEEKER.lat, fromLon: SEEKER.lon, answer: 'closer' }))!
    expect(region).toBeTruthy()
    // the seeker sits d from its nearest hospital → on the boundary; a point right
    // next to a hospital is well within d (kept), so must be unshaded.
    const near = nearestPoi(SEEKER, cat)!
    expect(pointInMulti(near.lat, near.lon, region)).toBe(false)
    // a far-away spot (no hospital within d) is eliminated → shaded
    expect(nearestPoiMiles({ lat: near.lat + 1, lon: near.lon }, cat)).toBeGreaterThan(d)
    expect(pointInMulti(near.lat + 1, near.lon, region)).toBe(true)
  })

  it('FURTHER: shades the union itself (inside a circle is eliminated)', () => {
    const region = poiMeasureEliminatedRegion(rec('measure-poi', { poiCat: cat, fromLat: SEEKER.lat, fromLon: SEEKER.lon, answer: 'further' }))!
    const near = nearestPoi(SEEKER, cat)!
    expect(pointInMulti(near.lat, near.lon, region)).toBe(true)
  })
})
