import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { keepRg, packTrip } from '../src/feeds'
import { decodeFeed } from '../src/gtfsrt'
import { addDays, inWindow, pacific, pacificToMs } from '../src/time'
import { gunzip, gzip } from '../src/util'

describe('decodeFeed', () => {
  // BART's GTFS-RT trip updates, fetched 2026-11-27 04:10 PST.
  const feed = decodeFeed(new Uint8Array(readFileSync(new URL('./bart.pb', import.meta.url))))

  it('reads the header and every trip update', () => {
    expect(feed.ts).toBe(1795781453)
    expect(feed.trips).toHaveLength(16)
    expect(feed.trips.reduce((n, t) => n + t.stops.length, 0)).toBe(238)
  })

  it('reads stop times', () => {
    const t = feed.trips[0]
    expect(t.id).toBe('1965575')
    expect(t.stops[0]).toEqual({ stop: 'M90-2', arr: 1795783179, dep: 1795783239, delay: 0 })
  })

  it('round-trips through the stored form', async () => {
    const body = JSON.stringify(feed.trips.map(packTrip))
    expect(await gunzip(new Uint8Array(await gzip(body)))).toBe(body)
  })
})

describe('keepRg', () => {
  it('keeps map lines and drops buses', () => {
    expect(keepRg('SF:N', 'SF:1')).toBe(true)
    expect(keepRg('SF:14', 'SF:2')).toBe(false)
    expect(keepRg('SC:Blue Line', 'SC:3')).toBe(true)
    expect(keepRg('SC:22', 'SC:4')).toBe(false)
    expect(keepRg('CT:Local Weekday', 'CT:5')).toBe(true)
    expect(keepRg('SB:OAS', 'SB:6')).toBe(true)
    expect(keepRg('AC:86', 'AC:7')).toBe(false)
    expect(keepRg('BA:Red-N', 'BA:8')).toBe(false)
  })
})

describe('Pacific time', () => {
  it('finds the window across DST', () => {
    expect(inWindow(pacificToMs('2026-11-29', '07:29'))).toBe(false)
    expect(inWindow(pacificToMs('2026-11-29', '07:30'))).toBe(true)
    expect(inWindow(pacificToMs('2026-07-04', '21:59'))).toBe(true)
    expect(inWindow(pacificToMs('2026-07-04', '22:00'))).toBe(false)
    expect(pacificToMs('2026-11-29', '07:30')).toBe(Date.UTC(2026, 10, 29, 15, 30))
    expect(pacificToMs('2026-07-04', '07:30')).toBe(Date.UTC(2026, 6, 4, 14, 30))
  })

  it('names the Pacific day, not the UTC one', () => {
    expect(pacific(Date.UTC(2026, 10, 29, 7, 0))).toEqual({ day: '2026-11-28', minute: 23 * 60 })
    expect(addDays('2026-11-29', 3)).toBe('2026-12-02')
    expect(addDays('2026-03-01', -1)).toBe('2026-02-28')
  })
})
