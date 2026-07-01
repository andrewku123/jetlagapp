import { describe, it, expect } from 'vitest'
import { poiCategoryLabel, QUESTION_POI_CATEGORIES, POI_BY_CATEGORY, nearestPoi, nearestPoiMiles, poiKey } from './poi'
import { poiMatchEliminatedRegion, poiMeasureEliminatedRegion, featureMeasureEliminatedRegion, airportMatchEliminatedRegion, airportMeasureEliminatedRegion, countyMatchEliminatedRegion, type LatLngMultiPolygon } from './questionRegions'
import { nearestAirport } from './airports'
import { countyAt } from './counties'
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

function rec(
  kind: 'match-poi' | 'measure-poi' | 'measure-feature' | 'match-airport' | 'measure-airport' | 'match-county',
  params: Record<string, unknown>,
): QuestionRecord {
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

describe('featureMeasureEliminatedRegion agrees with the elimination rule', () => {
  // seeker ~10 mi from the coast (San Jose); coastal spot ~0 mi, inland ~30 mi
  const seeker = { fromLat: 37.3297, fromLon: -121.9024 }
  const onCoast = { lat: 37.7955, lon: -122.3937 } // SF Embarcadero, inside the corridor
  const inland = { lat: 38.0169, lon: -121.8009 } // Antioch, outside the corridor

  it('CLOSER: shades the complement of the coastal corridor', () => {
    const region = featureMeasureEliminatedRegion(rec('measure-feature', { feature: 'coastline', ...seeker, answer: 'closer' }))!
    expect(region).toBeTruthy()
    expect(pointInMulti(onCoast.lat, onCoast.lon, region)).toBe(false) // kept ⇒ unshaded
    expect(pointInMulti(inland.lat, inland.lon, region)).toBe(true) // eliminated ⇒ shaded
  })

  it('FURTHER: shades the corridor itself', () => {
    const region = featureMeasureEliminatedRegion(rec('measure-feature', { feature: 'coastline', ...seeker, answer: 'further' }))!
    expect(pointInMulti(onCoast.lat, onCoast.lon, region)).toBe(true)
    expect(pointInMulti(inland.lat, inland.lon, region)).toBe(false)
  })
})

describe('airportMatchEliminatedRegion shades the seeker airport Voronoi cell', () => {
  // seeker in SF → nearest airport SFO; SJC is a spot in San Jose
  const sf = { lat: 37.7749, lon: -122.4194 }
  const sanJose = { lat: 37.3382, lon: -121.8863 }

  it('YES keeps the seeker cell (unshaded); a different-airport point is shaded', () => {
    expect(nearestAirport(sf).code).toBe('SFO')
    expect(nearestAirport(sanJose).code).toBe('SJC')
    const region = airportMatchEliminatedRegion(rec('match-airport', { fromLat: sf.lat, fromLon: sf.lon, value: 'SFO', answer: 'yes' }))!
    expect(pointInMulti(sf.lat, sf.lon, region)).toBe(false) // same airport ⇒ kept
    expect(pointInMulti(sanJose.lat, sanJose.lon, region)).toBe(true) // different ⇒ eliminated
  })

  it('NO shades the seeker cell instead', () => {
    const region = airportMatchEliminatedRegion(rec('match-airport', { fromLat: sf.lat, fromLon: sf.lon, value: 'SFO', answer: 'no' }))!
    expect(pointInMulti(sf.lat, sf.lon, region)).toBe(true)
    expect(pointInMulti(sanJose.lat, sanJose.lon, region)).toBe(false)
  })
})

describe('airportMeasureEliminatedRegion shades the your-distance airport disks', () => {
  const seeker = { lat: 37.7749, lon: -122.4194 } // ~11 mi from SFO

  it('CLOSER: a point on top of SFO is inside the union (kept ⇒ unshaded)', () => {
    const region = airportMeasureEliminatedRegion(rec('measure-airport', { fromLat: seeker.lat, fromLon: seeker.lon, answer: 'closer' }))!
    expect(pointInMulti(37.6191, -122.3816, region)).toBe(false) // SFO itself: within d ⇒ kept
  })

  it('FURTHER: the union around SFO is shaded', () => {
    const region = airportMeasureEliminatedRegion(rec('measure-airport', { fromLat: seeker.lat, fromLon: seeker.lon, answer: 'further' }))!
    expect(pointInMulti(37.6191, -122.3816, region)).toBe(true)
  })
})

describe('countyMatchEliminatedRegion shades outside/inside the seeker county', () => {
  const sf = { lat: 37.7749, lon: -122.4194 }
  const sanJose = { lat: 37.3382, lon: -121.8863 }

  it('YES keeps the seeker county (unshaded); another county is shaded', () => {
    const county = countyAt(sf)
    expect(county).toBe('San Francisco')
    const region = countyMatchEliminatedRegion(rec('match-county', { fromLat: sf.lat, fromLon: sf.lon, value: 'San Francisco', answer: 'yes' }))!
    expect(pointInMulti(sf.lat, sf.lon, region)).toBe(false)
    expect(pointInMulti(sanJose.lat, sanJose.lon, region)).toBe(true)
  })

  it('NO shades the seeker county instead', () => {
    const region = countyMatchEliminatedRegion(rec('match-county', { fromLat: sf.lat, fromLon: sf.lon, value: 'San Francisco', answer: 'no' }))!
    expect(pointInMulti(sf.lat, sf.lon, region)).toBe(true)
    expect(pointInMulti(sanJose.lat, sanJose.lon, region)).toBe(false)
  })
})
