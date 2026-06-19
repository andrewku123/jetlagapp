import { describe, it, expect } from 'vitest'
import rawStations from './stations.json'
import counties from './counties.geojson.json'
import { IN_PLAY_COUNTIES } from '../lib/playArea'
import type { Station } from '../types'

const STATIONS = rawStations as unknown as Station[]

function count(system: string) {
  return STATIONS.filter((s) => s.systems.includes(system)).length
}
function eligible(day: 'wd' | 'we') {
  return STATIONS.filter((s) => s.service[day].served && s.service[day].hourly).length
}

describe('station dataset invariants', () => {
  it('has 246 unique stations', () => {
    expect(STATIONS.length).toBe(246)
  })

  it('has the expected per-system membership counts', () => {
    expect(count('BART')).toBe(50)
    expect(count('Caltrain')).toBe(24)
    expect(count('VTA')).toBe(59)
    expect(count('Muni')).toBe(124)
  })

  it('has the expected eligible counts (weekday/weekend)', () => {
    expect(eligible('wd')).toBe(245)
    expect(eligible('we')).toBe(246)
  })

  it('has no F-only surface stops on Market St inland of Embarcadero', () => {
    const offenders = STATIONS.filter(
      (s) => s.lines.length === 1 && s.lines[0] === 'Muni F' && s.name.startsWith('Market Street &'),
    )
    expect(offenders).toEqual([])
  })

  it('does not list the F at Union Square/Market', () => {
    const usm = STATIONS.find((s) => s.name === 'Union Square/Market Street')
    expect(usm).toBeDefined()
    expect(usm!.lines).not.toContain('Muni F')
  })

  it('drops College Park entirely', () => {
    expect(STATIONS.find((s) => s.name.includes('College Park'))).toBeUndefined()
  })

  it('keeps the in-play counties consistent with the station data and overlay', () => {
    // Every county that has a station must be marked in-play.
    const stationCounties = new Set(STATIONS.map((s) => s.county).filter(Boolean) as string[])
    for (const c of stationCounties) expect(IN_PLAY_COUNTIES.has(c)).toBe(true)
    // The overlay GeoJSON must contain a polygon for every in-play county to dim around.
    const overlayNames = new Set(counties.features.map((f) => f.properties.name))
    for (const c of IN_PLAY_COUNTIES) expect(overlayNames.has(c)).toBe(true)
  })

  it('gives every station a unique id and required attributes', () => {
    const ids = new Set(STATIONS.map((s) => s.id))
    expect(ids.size).toBe(STATIONS.length)
    for (const s of STATIONS) {
      expect(typeof s.lat).toBe('number')
      expect(typeof s.lon).toBe('number')
      expect(s.systems.length).toBeGreaterThan(0)
      expect(s.nameLength).toBe(s.name.length)
    }
  })
})
