import { describe, it, expect } from 'vitest'
import rawStations from '../data/stations.json'
import type { Station } from '../types'
import { fitTarget, zoneBoxMeters } from './mapFit'

const STATIONS = rawStations as unknown as Station[]

describe('map fit target', () => {
  it('fits the bounding box of a spread-out board', () => {
    const target = fitTarget(STATIONS.slice(0, 20), null, 0.25)
    expect(target).toEqual({ kind: 'bounds', points: expect.any(Array) })
  })

  // A single point has no bounding box, and with a vector basemap nothing caps
  // the map's zoom, so fitting one would resolve to zoom Infinity and blank the
  // map. Endgame collapses the board to exactly one station.
  it('frames the hiding zone when only one suspect is left', () => {
    const only = STATIONS[0]
    expect(fitTarget([only], null, 0.25)).toEqual({
      kind: 'zone',
      lat: only.lat,
      lon: only.lon,
      sizeM: zoneBoxMeters(0.25),
    })
  })

  it('frames the hiding zone in endgame, whatever the board says', () => {
    const eg = STATIONS[3]
    const target = fitTarget(STATIONS.slice(0, 20), eg, 0.5)
    expect(target).toEqual({ kind: 'zone', lat: eg.lat, lon: eg.lon, sizeM: zoneBoxMeters(0.5) })
  })

  it('frames co-located stations as a zone, not a zero-size box', () => {
    const a = STATIONS[0]
    const b = { ...STATIONS[1], lat: a.lat, lon: a.lon }
    expect(fitTarget([a, b], null, 0.25)).toMatchObject({ kind: 'zone' })
  })

  it('scales the framed box with the cursed zone radius', () => {
    expect(zoneBoxMeters(0.5625)).toBeCloseTo(zoneBoxMeters(0.25) * 2.25, 6)
  })

  it('has nothing to fit on an empty board', () => {
    expect(fitTarget([], null, 0.25)).toBeNull()
  })
})
