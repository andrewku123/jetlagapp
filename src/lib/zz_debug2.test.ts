import { it } from 'vitest'
import { arrivalAt, dayTimetable, earliestArrivals, legsTo, walkSeconds, type NetworkFile } from './transitNetwork'
import stations from '../data/stations.json'
import bayarea from '../../public/transit/bayarea.json'
const file = bayarea as unknown as NetworkFile
const hm = (s: number) => `${Math.floor(s / 3600)}:${String(Math.floor(s / 60) % 60).padStart(2, '0')}`
const nm = (i: number | null) => (i === null ? 'origin' : stations.find((s) => s.id === file.stations[i])?.name ?? i)
const sec = (s: string) => +s.slice(0, 2) * 3600 + +s.slice(3) * 60
// [label, from, to, prevAsked, prevAnswered, asked, answered]
const rows: [string, [number, number], [number, number], string, string, string, string][] = [
  ['18:41 zoo', [37.617706, -122.384941], [37.721401, -122.447017], '18:14', '18:18', '18:36', '18:41'],
  ['19:02 aq', [37.721401, -122.447017], [37.784567, -122.407354], '18:44', '18:48', '18:58', '19:02'],
  ['19:19 radar', [37.784567, -122.407354], [37.808069, -122.268716], '18:58', '19:02', '19:14', '19:19'],
  ['19:27 coast', [37.808069, -122.268716], [37.80475, -122.29514], '19:14', '19:19', '19:24', '19:27'],
  ['19:41 radar', [37.80475, -122.29514], [37.789038, -122.401666], '19:24', '19:27', '19:35', '19:41'],
]
it('debug2', () => {
  // service sets per Sunday
  const sundays: string[] = []
  for (let d = 0; d < file.days; d++) {
    const date = new Date(Date.parse(file.firstDay + 'T12:00:00Z') + d * 86400000)
    if (date.getUTCDay() === 0) sundays.push(date.toISOString().slice(0, 10) + ' ' + file.services.map((s) => s[d]).join('').replace(/0/g, '.'))
  }
  console.log(sundays.join('\n'))
  const tt = dayTimetable(file, '2026-11-22', stations)!
  const sfo = stations.find((s) => s.name.startsWith('San Francisco International'))!
  console.log('walk to SFO BART', Math.round(walkSeconds({ lat: 37.617706, lon: -122.384941 }, sfo) / 60), 'min')
  const si = file.stations.indexOf(sfo.id)
  const deps = new Set<string>()
  for (let i = 0; i < tt.dep.length; i++) if (tt.from[i] === si && tt.dep[i] > sec('17:50') && tt.dep[i] < sec('19:00')) deps.add(`${hm(tt.dep[i])} ${tt.tripRoute[tt.trip[i]]}`)
  console.log('SFO deps', [...deps].sort().join(', '))
  const pw = file.stations.indexOf(stations.find((s) => s.name.startsWith('Powell'))!.id)
  const d2 = new Set<string>()
  for (let i = 0; i < tt.dep.length; i++) if (tt.from[i] === pw && tt.dep[i] > sec('18:50') && tt.dep[i] < sec('19:20') && tt.tripRoute[tt.trip[i]].startsWith('BART')) d2.add(`${hm(tt.dep[i])} ${tt.tripRoute[tt.trip[i]]}`)
  console.log('Powell BART deps', [...d2].sort().join(', '))
  for (const [label, [la, lo], [lb, lob], pa, , qa] of rows) {
    const o = { lat: la, lon: lo }, p = { lat: lb, lon: lob }
    const t0 = sec(pa)
    const a = earliestArrivals(tt, o, t0)
    const r = arrivalAt(tt, a, p)
    console.log(label, 'asked→asked', (sec(qa) - t0) / 60, 'fastest from asked', Math.round((r.at - t0) / 60))
    if (r.station >= 0) for (const l of legsTo(tt, a, r.station)) if (l.kind === 'ride') console.log('    ride', l.route, nm(l.from), hm(l.dep), '->', nm(l.to), hm(l.arr))
  }
})
