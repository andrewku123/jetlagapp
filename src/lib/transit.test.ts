import { describe, it, expect } from 'vitest'
import { buildTransit, offsetLine, SPACING_M, type TransitWay } from './transit'

const wayMulti: TransitWay = {
  type: 'Feature',
  properties: { system: 'BART', colors: ['#ff0000', '#00ff00', '#0000ff'] },
  geometry: { type: 'LineString', coordinates: [[-122.4, 37.78], [-122.39, 37.79]] },
}
const waySingle: TransitWay = {
  type: 'Feature',
  properties: { system: 'Caltrain', colors: ['#9b1b30'] },
  geometry: { type: 'LineString', coordinates: [[-122.4, 37.6], [-122.4, 37.7]] },
}

describe('offsetLine', () => {
  it('returns the same coords when offset is zero', () => {
    const c = [[-122.4, 37.78], [-122.39, 37.79]]
    expect(offsetLine(c, 0)).toBe(c)
  })

  it('shifts a north-south line east/west by roughly the requested metres', () => {
    const c = [[-122.4, 37.6], [-122.4, 37.7]]
    const shifted = offsetLine(c, 100)
    // travelling north, the left normal points west (negative lon)
    expect(shifted[0][0]).toBeLessThan(-122.4)
    const metresPerDegLon = 111320 * Math.cos((37.6 * Math.PI) / 180)
    const deltaMetres = (shifted[0][0] - -122.4) * metresPerDegLon
    expect(Math.abs(deltaMetres)).toBeCloseTo(100, 0)
  })
})

describe('buildTransit', () => {
  it('interlines a multi-color way into one centered, offset line per color', () => {
    const fc = buildTransit([wayMulti], true)
    expect(fc.features).toHaveLength(3)
    // centered offsets for k=3 are -SPACING, 0, +SPACING; the middle one is unshifted
    const mid = fc.features[1].geometry as GeoJSON.LineString
    expect(mid.coordinates[0][0]).toBeCloseTo(-122.4, 10)
    const outer = fc.features[0].geometry as GeoJSON.LineString
    expect(outer.coordinates[0][0]).not.toBeCloseTo(-122.4, 6)
  })

  it('collapses a multi-color way to a single line when interlining is off', () => {
    const fc = buildTransit([wayMulti], false)
    expect(fc.features).toHaveLength(1)
    expect((fc.features[0].properties as { color: string }).color).toBe('#ff0000')
  })

  it('never offsets a single-color way (e.g. Caltrain) regardless of toggle', () => {
    for (const on of [true, false]) {
      const fc = buildTransit([waySingle], on)
      expect(fc.features).toHaveLength(1)
      const g = fc.features[0].geometry as GeoJSON.LineString
      expect(g.coordinates).toEqual(waySingle.geometry.coordinates)
    }
  })

  it('uses SPACING_M as the gap between adjacent parallel tracks', () => {
    const fc = buildTransit([wayMulti], true)
    const a = (fc.features[0].geometry as GeoJSON.LineString).coordinates[0]
    const b = (fc.features[1].geometry as GeoJSON.LineString).coordinates[0]
    const lat = 37.78
    const mLon = 111320 * Math.cos((lat * Math.PI) / 180)
    const mLat = 110540
    const d = Math.hypot((a[0] - b[0]) * mLon, (a[1] - b[1]) * mLat)
    expect(d).toBeCloseTo(SPACING_M, 0)
  })
})
