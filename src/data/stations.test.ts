import { describe, it, expect } from 'vitest'
import rawStations from './stations.json'
import counties from './counties.geojson.json'
import { IN_PLAY_COUNTIES } from '../lib/playArea'
import { WEEKEND_EXCLUDED_LINES } from '../lib/style'
import { ELIGIBLE_HEADWAY_MIN } from './questionSets'
import type { Station } from '../types'

const STATIONS = rawStations as unknown as Station[]

function count(system: string) {
  return STATIONS.filter((s) => s.systems.includes(system)).length
}
// Eligibility mirrors the app: a station counts if it's served at least hourly.
function eligible(day: 'wd' | 'we') {
  return STATIONS.filter((s) => s.headwayMin[day] <= ELIGIBLE_HEADWAY_MIN).length
}

describe('station dataset invariants', () => {
  it('has 249 unique stations', () => {
    expect(STATIONS.length).toBe(249)
  })

  it('has the expected per-system membership counts', () => {
    expect(count('BART')).toBe(50)
    expect(count('Caltrain')).toBe(24)
    expect(count('VTA')).toBe(59)
    expect(count('Muni')).toBe(127)
  })

  it('has the expected eligible counts (weekday/weekend)', () => {
    expect(eligible('wd')).toBe(248)
    expect(eligible('we')).toBe(249)
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

  it('weekday-only Caltrain services exist in the data but are weekend-excluded', () => {
    const all = new Set(STATIONS.flatMap((s) => s.lines))
    // Express/Limited are real lines in the data (weekday service)...
    for (const l of WEEKEND_EXCLUDED_LINES) expect(all.has(l)).toBe(true)
    // ...and Caltrain Local is never excluded (it runs on weekends).
    expect(WEEKEND_EXCLUDED_LINES).not.toContain('Caltrain Local')
    // Any station with Express/Limited must also offer Local (so it stays
    // selectable in Weekend mode after the weekday-only lines are filtered out).
    for (const s of STATIONS) {
      if (s.lines.some((l) => WEEKEND_EXCLUDED_LINES.includes(l))) {
        expect(s.lines).toContain('Caltrain Local')
      }
    }
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
      expect(typeof s.headwayMin.wd).toBe('number')
      expect(typeof s.headwayMin.we).toBe('number')
    }
  })
})
