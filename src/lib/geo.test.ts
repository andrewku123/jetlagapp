import { describe, it, expect } from 'vitest'
import { haversineMiles, formatMiles, bisectorEndpoints } from './geo'

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
