import { describe, it, expect } from 'vitest'
import {
  haversineMiles,
  formatMiles,
  formatDistance,
  formatElevation,
  bisectorEndpoints,
  bisectorPolyline,
  bisectorHalfPlane,
  circlePolygon,
  parseLatLng,
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

describe('bisectorPolyline', () => {
  const a = { lat: 37.7, lon: -122.45 }
  const b = { lat: 37.8, lon: -122.25 }

  it('passes exactly through the A–B midpoint (even segment count)', () => {
    const pts = bisectorPolyline(a, b, 60, 64)
    const mid = pts[32]
    expect(mid.lat).toBeCloseTo((a.lat + b.lat) / 2, 9)
    expect(mid.lon).toBeCloseTo((a.lon + b.lon) / 2, 9)
  })

  it('starts and ends at the bisector endpoints', () => {
    const [e0, e1] = bisectorEndpoints(a, b, 60)
    const pts = bisectorPolyline(a, b, 60, 64)
    expect(pts[0].lat).toBeCloseTo(e1.lat, 9)
    expect(pts[0].lon).toBeCloseTo(e1.lon, 9)
    expect(pts[pts.length - 1].lat).toBeCloseTo(e0.lat, 9)
    expect(pts[pts.length - 1].lon).toBeCloseTo(e0.lon, 9)
  })

  it('every sample is equidistant from A and B', () => {
    // equirectangular bisector: equidistant to within a small drift over 60 mi
    for (const pt of bisectorPolyline(a, b, 60, 16)) {
      expect(haversineMiles(pt, a)).toBeCloseTo(haversineMiles(pt, b), 0)
    }
  })
})

describe('bisectorHalfPlane', () => {
  const a = { lat: 38.0, lon: -122.6 } // NW
  const b = { lat: 37.2, lon: -121.8 } // SE

  it('shares its first edge with the (sampled) bisector line (shading aligns)', () => {
    const line = bisectorPolyline(a, b, 300, 64)
    const poly = bisectorHalfPlane(a, b, a, 300, 64)
    // the first half of the ribbon polygon is exactly the sampled bisector, so
    // the shaded edge lies on the drawn boundary line at every sample.
    expect(poly.length).toBe(line.length * 2)
    for (let i = 0; i < line.length; i++) {
      expect(poly[i].lat).toBeCloseTo(line[i].lat, 9)
      expect(poly[i].lon).toBeCloseTo(line[i].lon, 9)
    }
  })

  it('covers the half toward `toward` and not the other half', () => {
    // colder ⇒ shade side toward A. A's side must be inside, B's side outside.
    const poly = bisectorHalfPlane(a, b, a, 300)
    expect(pointInPolygon(a, poly)).toBe(true)
    expect(pointInPolygon(b, poly)).toBe(false)
    // flip the side: toward B now contains B, not A
    const polyB = bisectorHalfPlane(a, b, b, 300)
    expect(pointInPolygon(b, polyB)).toBe(true)
    expect(pointInPolygon(a, polyB)).toBe(false)
  })
})

describe('parseLatLng', () => {
  it('parses plain comma-separated Google Maps coordinates', () => {
    expect(parseLatLng('37.7749, -122.4194')).toEqual({ lat: 37.7749, lon: -122.4194 })
  })
  it('accepts space/tab separators', () => {
    expect(parseLatLng('37.7749  -122.4194')).toEqual({ lat: 37.7749, lon: -122.4194 })
    expect(parseLatLng('37.7749\t-122.4194')).toEqual({ lat: 37.7749, lon: -122.4194 })
  })
  it('handles degree + hemisphere notation', () => {
    expect(parseLatLng('37.7749° N, 122.4194° W')).toEqual({ lat: 37.7749, lon: -122.4194 })
  })
  it('handles leading hemisphere letters', () => {
    expect(parseLatLng('N 37.7749 W 122.4194')).toEqual({ lat: 37.7749, lon: -122.4194 })
  })
  it('handles lon-first when hemispheres disambiguate', () => {
    expect(parseLatLng('122.4194 W, 37.7749 N')).toEqual({ lat: 37.7749, lon: -122.4194 })
  })
  it('rejects junk and out-of-range values', () => {
    expect(parseLatLng('')).toBeNull()
    expect(parseLatLng('hello')).toBeNull()
    expect(parseLatLng('37.7749')).toBeNull()
    expect(parseLatLng('200, 10')).toBeNull()
  })
})

function pointInPolygon(p: { lat: number; lon: number }, poly: { lat: number; lon: number }[]): boolean {
  let inside = false
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const xi = poly[i].lon, yi = poly[i].lat
    const xj = poly[j].lon, yj = poly[j].lat
    const hit = yi > p.lat !== yj > p.lat && p.lon < ((xj - xi) * (p.lat - yi)) / (yj - yi) + xi
    if (hit) inside = !inside
  }
  return inside
}
