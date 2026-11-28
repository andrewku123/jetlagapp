import { describe, expect, it } from 'vitest'
import { arrivalAt, dayTimetable, earliestArrivals, legsTo, pacificTime, quickestTrip, serviceDate, type NetworkFile } from './transitNetwork'
import stations from '../data/stations.json'
import bayarea from '../../public/transit/bayarea.json'

// three stations ~1.1 km apart on a line, plus D 300 m from C (a walk transfer)
const pts = [
  { id: 'A', lat: 37.8, lon: -122.3 },
  { id: 'B', lat: 37.81, lon: -122.3 },
  { id: 'C', lat: 37.82, lon: -122.3 },
  { id: 'D', lat: 37.8227, lon: -122.3 },
]
const net: NetworkFile = {
  v: 1,
  built: '2026-11-28',
  firstDay: '2026-11-28',
  days: 3,
  stations: ['A', 'B', 'C', 'D'],
  services: ['011', '100'],
  patterns: [
    {
      route: 'Test Line',
      stops: [0, 1, 2],
      shapes: [[0, 120, 240]],
      trips: [
        [0, 36_000, 0], // 10:00 on the 29th and 30th
        [0, 36_600, 0], // 10:10
        [1, 86_460, 0], // 24:01 on the 28th's service day
      ],
    },
  ],
}

describe('transit network', () => {
  it('rides the first train it can board and walks the transfer', () => {
    const tt = dayTimetable(net, '2026-11-29', pts)!
    const a = earliestArrivals(tt, pts[0], 36_000 - 60)
    expect(a.arr[2]).toBe(36_240)
    expect(a.arr[3]).toBeCloseTo(36_240 + 300 / (1.3 / 1.25), -1)
    expect(legsTo(tt, a, 3).map((l) => l.kind)).toEqual(['walk', 'ride', 'walk'])
  })

  it('needs a minute to board, so it misses a train leaving now', () => {
    const tt = dayTimetable(net, '2026-11-29', pts)!
    expect(earliestArrivals(tt, pts[0], 36_000).arr[2]).toBe(36_840)
  })

  it('keeps last night’s train running past midnight', () => {
    const tt = dayTimetable(net, '2026-11-29', pts)!
    expect(earliestArrivals(tt, pts[0], 0).arr[1]).toBe(180)
  })

  it('walks to a point when that is faster', () => {
    const tt = dayTimetable(net, '2026-11-29', pts)!
    const a = earliestArrivals(tt, pts[0], 30_000)
    expect(arrivalAt(tt, a, { lat: 37.8005, lon: -122.3 }).station).toBe(-1)
  })

  it('has no timetable outside its days', () => {
    expect(dayTimetable(net, '2026-12-05', pts)).toBeNull()
  })

  it('reads Pacific time', () => {
    expect(pacificTime(Date.parse('2026-11-29T14:15:30-08:00'))).toEqual({ date: '2026-11-29', sec: 14 * 3600 + 15 * 60 + 30 })
  })

  it('reads a game outside the saved days on the same weekday', () => {
    const file = bayarea as unknown as NetworkFile
    expect(serviceDate(file, file.firstDay)).toBe(file.firstDay)
    const stand = serviceDate(file, '2026-08-30')!
    expect(new Date(stand + 'T12:00:00Z').getUTCDay()).toBe(0)
    expect(stand > file.firstDay).toBe(true)
    // 12/6 runs a different BART service; the stand-in is a typical Sunday
    expect(serviceDate(file, '2026-08-30')).not.toBe('2026-12-06')
  })

  it('Bay Area: 12th Street to Embarcadero on a Sunday morning is a short BART ride', () => {
    const file = bayarea as unknown as NetworkFile
    const tt = dayTimetable(file, '2026-11-29', stations)!
    const from = stations.find((s) => s.name.startsWith('12th Street'))!
    const to = file.stations.indexOf(stations.find((s) => s.name.startsWith('Embarcadero') && s.systems.includes('BART'))!.id)
    const a = earliestArrivals(tt, from, 10 * 3600)
    const min = (a.arr[to] - 10 * 3600) / 60
    expect(min).toBeGreaterThan(8)
    expect(min).toBeLessThan(30)
    expect(legsTo(tt, a, to).some((l) => l.kind === 'ride' && l.route.startsWith('BART'))).toBe(true)
  })

  it('Bay Area: riding on from 19th St with no wait reaches West Oakland in a few minutes', () => {
    const file = bayarea as unknown as NetworkFile
    const tt = dayTimetable(file, '2026-11-22', stations)!
    const from = stations.find((s) => s.name.startsWith('19th St'))!
    const to = stations.find((s) => s.name.startsWith('West Oakland'))!
    const t0 = 19 * 3600 + 19 * 60
    const quick = quickestTrip(tt, from, to, t0)
    const scheduled = arrivalAt(tt, earliestArrivals(tt, from, t0), to).at - t0
    expect(quick.secs).toBeLessThanOrEqual(scheduled)
    expect(quick.secs / 60).toBeLessThan(8)
    expect(quick.legs.some((l) => l.kind === 'ride' && l.route.startsWith('BART'))).toBe(true)
  })
})
