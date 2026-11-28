import { describe, expect, it } from 'vitest'
import stationsJson from '../data/stations.json'
import bayarea from '../../public/transit/bayarea.json'
import { curseOrigin, curseOver, fastestClear, type ReviewCurse } from './reviewCurses'
import { dayTimetable, serviceDate, type NetworkFile } from './transitNetwork'
import type { QuestionRecord, Station } from '../types'

const stations = stationsJson as unknown as Station[]
const t = (hm: string) => Date.parse(`2026-08-30T${hm}:00-07:00`)
const plane: ReviewCurse = { id: 'c1', name: 'Planespotter', startAt: t('17:47'), endAt: t('18:14') }
const q = (at: string, params: Record<string, unknown>): QuestionRecord =>
  ({ id: at, kind: 'radar', createdAt: t(at), params, eliminates: true, active: true }) as QuestionRecord
const spot = (r: QuestionRecord) => (typeof r.params.lat === 'number' ? { lat: r.params.lat, lon: r.params.lon as number } : null)

describe('review curses', () => {
  it('finds the curse a stretch of play overlaps', () => {
    expect(curseOver([plane], t('17:38'), t('18:18'))).toBe(plane)
    expect(curseOver([plane], t('18:14'), t('18:24'))).toBeNull()
    expect(curseOver([plane], t('17:30'), t('17:47'))).toBeNull()
  })

  it('starts from the entered station, else the last located question by the cast', () => {
    const qs = [q('17:21', { lat: 37.6, lon: -122.4 }), q('17:38', {}), q('18:20', { lat: 37.7, lon: -122.4 })]
    expect(curseOrigin(plane, qs, stations, spot)).toEqual({ lat: 37.6, lon: -122.4 })
    const sb = stations.find((s) => s.id === 's040')!
    expect(curseOrigin({ ...plane, fromStation: 's040' }, qs, stations, spot)).toEqual({ lat: sb.lat, lon: sb.lon })
  })

  it('picks the nearest listed place on the schedule: San Bruno to SFO beats Oakland Airport', () => {
    const net = bayarea as unknown as NetworkFile
    expect(serviceDate(net, '2026-08-30')).toBe('2026-11-22')
    const tt = dayTimetable(net, serviceDate(net, '2026-08-30')!, stations)!
    const sb = stations.find((s) => s.id === 's040')!
    const trip = fastestClear(tt, sb, { ...plane, clearAt: ['s032', 's041'] }, stations)!
    expect(trip.place).toBe('s041')
    expect(trip.fastest).toBeGreaterThan(2)
    expect(trip.fastest).toBeLessThan(27)
    expect(trip.took).toBe(27)
    expect(fastestClear(tt, sb, plane, stations)).toBeNull()
    const later = fastestClear(tt, sb, { ...plane, hindsightAt: ['s037'] }, stations, ['s037'])!
    expect(later.place).toBe('s037')
    expect(later.fastest).toBeGreaterThan(trip.fastest)
  })
})
