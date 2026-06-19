import { describe, it, expect } from 'vitest'
import {
  haversineMiles,
  formatMiles,
  formatDistance,
  formatElevation,
  bisectorEndpoints,
  circlePolygon,
} from './geo'

describe('haversineMiles', () => {
  it('is zero for the same point', () => {
    expect(haversineMiles({ lat: 37.7, lon: -122.4 }, { lat: 37.7, lon: -122.4 })).toBe(0)
  })

  it('matches a known SF→SJ distance (~42 mi)', () => {
    // SF (4th & King) to San Jose Diridon, great-circle ~42 miles
    const d = haversineMiles({ lat: 37.7766, lon: -122.3946 }, { lat: 37.3297, lon: -121.9024 })
    expect(d).toBeGreaterThan(40)
    expect(d).toBeLessThan(44)
  })

  it('is symmetric', () => {
    const a = { lat: 37.8, lon: -122.27 }
    const b = { lat: 37.33, lon: -121.9 }
    expect(haversineMiles(a, b)).toBeCloseTo(haversineMiles(b, a), 9)
  })
})

describe('formatMiles', () => {
  it('shows 2 decimals when exact', () => {
    expect(formatMiles(33.448)).toBe('33.45 mi')
  })
  it('snaps to whole miles', () => {
    expect(formatMiles(33.448, 1)).toBe('33 mi')
    expect(formatMiles(33.6, 1)).toBe('34 mi')
  })
  it('snaps to half miles', () => {
    expect(formatMiles(2.3, 0.5)).toBe('2.5 mi')
  })
  it('snaps to 5 and 10 mi buckets', () => {
    expect(formatMiles(33.448, 5)).toBe('35 mi')
    expect(formatMiles(33.448, 10)).toBe('30 mi')
  })
})

describe('formatDistance', () => {
  it('shows miles for imperial', () => {
    expect(formatDistance(33.448, 'imperial')).toBe('33.45 mi')
    expect(formatDistance(33.448, 'imperial', 1)).toBe('33 mi')
  })
  it('converts to km for metric', () => {
    expect(formatDistance(1, 'metric')).toBe('1.61 km')
    expect(formatDistance(10, 'metric', 1)).toBe('16 km')
  })
})

describe('circlePolygon', () => {
  it('returns n points all ~radius miles from the center', () => {
    const center = { lat: 37.7, lon: -122.2 }
    const ring = circlePolygon(center, 10, 36)
    expect(ring).toHaveLength(36)
    for (const p of ring) {
      expect(haversineMiles(center, p)).toBeGreaterThan(9.5)
      expect(haversineMiles(center, p)).toBeLessThan(10.5)
    }
  })
})

describe('formatElevation', () => {
  it('converts meters to feet for imperial', () => {
    expect(formatElevation(100, 'imperial')).toBe('328 ft')
  })
  it('shows meters for metric', () => {
    expect(formatElevation(67, 'metric')).toBe('67 m')
  })
})

describe('bisectorEndpoints', () => {
  it('returns a midpoint equidistant from both input points', () => {
    const a = { lat: 37.7, lon: -122.45 }
    const b = { lat: 37.8, lon: -122.25 }
    const [p, q] = bisectorEndpoints(a, b, 30)
    // every point on the perpendicular bisector is equidistant from a and b;
    // the two returned endpoints should be too.
    for (const pt of [p, q]) {
      expect(haversineMiles(pt, a)).toBeCloseTo(haversineMiles(pt, b), 1)
    }
  })
})
