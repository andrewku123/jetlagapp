import type { LatLng } from '../types'
import { haversineMeters } from './geo'

// Review only: the timetable built by scripts/build_transit_network.py
// (public/transit/<region>.json) and an earliest-arrival search over it
// (connection scan). Times are seconds after midnight Pacific on the game date.

export interface NetworkFile {
  v: 1
  built: string
  firstDay: string // YYYY-MM-DD, day 0 of each service bitstring
  days: number
  stations: string[]
  services: string[] // '0'/'1' per day from firstDay
  patterns: { route: string; stops: number[]; shapes: number[][]; trips: [number, number, number][] }[]
}

// Walking is 1.3 m/s along streets, about 1.25x the straight line.
export const WALK_MPS = 1.3 / 1.25
export const TRANSFER_WALK_M = 500
export const BOARD_BUFFER_S = 60

export interface StationPoint {
  id: string
  lat: number
  lon: number
}

export interface DayTimetable {
  date: string
  stations: StationPoint[]
  dep: Int32Array
  arr: Int32Array
  from: Int32Array
  to: Int32Array
  trip: Int32Array
  tripRoute: string[]
  foot: { to: number; s: number }[][]
}

export const walkSeconds = (a: LatLng, b: LatLng) => haversineMeters(a, b) / WALK_MPS

const dayNumber = (ymd: string) => Math.round(Date.UTC(+ymd.slice(0, 4), +ymd.slice(5, 7) - 1, +ymd.slice(8, 10)) / 86_400_000)

// Every connection (one train between two consecutive stations) running on
// `date`, sorted by departure. Trips of the day before that run past midnight
// are included with their times shifted back a day.
// The date whose timetable stands in for `date`: itself when the saved file
// covers it, else the first covered date on the same weekday (an older game is
// read on today's schedule). Skips the first day so last night's late trips exist.
export function serviceDate(net: NetworkFile, date: string): string | null {
  const first = dayNumber(net.firstDay)
  const day = dayNumber(date)
  if (day - first >= 0 && day - first < net.days) return date
  for (let d = first + 1; d < first + net.days; d++) {
    if ((((d - day) % 7) + 7) % 7 === 0) return new Date(d * 86_400_000).toISOString().slice(0, 10)
  }
  return null
}

export function dayTimetable(net: NetworkFile, date: string, points: StationPoint[]): DayTimetable | null {
  const day = dayNumber(date) - dayNumber(net.firstDay)
  if (day < 0 || day >= net.days) return null
  const byId = new Map(points.map((p) => [p.id, p]))
  const stations = net.stations.map((id) => byId.get(id) ?? { id, lat: NaN, lon: NaN })
  const conns: [number, number, number, number, number][] = []
  const tripRoute: string[] = []
  for (const p of net.patterns) {
    for (const [svc, start, shape] of p.trips) {
      const bits = net.services[svc]
      const offs = p.shapes[shape]
      const shifts: number[] = []
      if (bits[day] === '1') shifts.push(0)
      if (day > 0 && bits[day - 1] === '1' && start + offs[offs.length - 1] >= 86_400) shifts.push(-86_400)
      for (const shift of shifts) {
        const t = tripRoute.length
        tripRoute.push(p.route)
        for (let k = 0; k + 1 < p.stops.length; k++) {
          conns.push([start + offs[k] + shift, start + offs[k + 1] + shift, p.stops[k], p.stops[k + 1], t])
        }
      }
    }
  }
  conns.sort((a, b) => a[0] - b[0] || a[1] - b[1])
  const n = conns.length
  const tt: DayTimetable = {
    date,
    stations,
    dep: new Int32Array(n),
    arr: new Int32Array(n),
    from: new Int32Array(n),
    to: new Int32Array(n),
    trip: new Int32Array(n),
    tripRoute,
    foot: stations.map(() => []),
  }
  conns.forEach(([d, a, f, t, tr], i) => {
    tt.dep[i] = d
    tt.arr[i] = a
    tt.from[i] = f
    tt.to[i] = t
    tt.trip[i] = tr
  })
  for (let i = 0; i < stations.length; i++) {
    for (let j = i + 1; j < stations.length; j++) {
      const m = haversineMeters(stations[i], stations[j])
      if (m <= TRANSFER_WALK_M) {
        tt.foot[i].push({ to: j, s: m / WALK_MPS })
        tt.foot[j].push({ to: i, s: m / WALK_MPS })
      }
    }
  }
  return tt
}

export interface Arrivals {
  origin: LatLng
  t0: number
  arr: Float64Array // earliest arrival per station (seconds)
  viaConn: Int32Array // last ride into the station, or -1
  viaFoot: Int32Array // station walked from, or -1
  boardConn: Int32Array // per trip: the connection it was boarded at
}

// Earliest arrival at every station leaving `origin` at t0, walking or riding.
export function earliestArrivals(tt: DayTimetable, origin: LatLng, t0: number, until = t0 + 6 * 3600): Arrivals {
  const ns = tt.stations.length
  const arr = new Float64Array(ns)
  const viaConn = new Int32Array(ns).fill(-1)
  const viaFoot = new Int32Array(ns).fill(-1)
  const boardConn = new Int32Array(tt.tripRoute.length).fill(-1)
  for (let s = 0; s < ns; s++) {
    const p = tt.stations[s]
    arr[s] = Number.isFinite(p.lat) ? t0 + walkSeconds(origin, p) : Infinity
  }
  let lo = 0
  let hi = tt.dep.length
  while (lo < hi) {
    const mid = (lo + hi) >> 1
    if (tt.dep[mid] < t0) lo = mid + 1
    else hi = mid
  }
  for (let i = lo; i < tt.dep.length && tt.dep[i] <= until; i++) {
    const trip = tt.trip[i]
    if (boardConn[trip] < 0) {
      if (arr[tt.from[i]] + BOARD_BUFFER_S > tt.dep[i]) continue
      boardConn[trip] = i
    }
    const to = tt.to[i]
    const a = tt.arr[i]
    if (a >= arr[to]) continue
    arr[to] = a
    viaConn[to] = i
    viaFoot[to] = -1
    for (const f of tt.foot[to]) {
      if (a + f.s < arr[f.to]) {
        arr[f.to] = a + f.s
        viaConn[f.to] = -1
        viaFoot[f.to] = to
      }
    }
  }
  return { origin, t0, arr, viaConn, viaFoot, boardConn }
}

// Earliest arrival at any point: walk there directly, or ride to a station and walk.
export function arrivalAt(tt: DayTimetable, a: Arrivals, point: LatLng): { at: number; station: number } {
  let best = a.t0 + walkSeconds(a.origin, point)
  let station = -1
  for (let s = 0; s < tt.stations.length; s++) {
    if (!Number.isFinite(a.arr[s])) continue
    const t = a.arr[s] + walkSeconds(tt.stations[s], point)
    if (t < best) {
      best = t
      station = s
    }
  }
  return { at: best, station }
}

// The quickest trip when the first train needs no wait (the seekers were already
// on it): the shortest door-to-door time over every start in the next `window`.
export function quickestTrip(
  tt: DayTimetable,
  origin: LatLng,
  point: LatLng,
  t0: number,
  window = 30 * 60,
): { secs: number; legs: Leg[] } {
  let best: { secs: number; a: Arrivals; station: number } | null = null
  for (let w = 0; w <= window; w += 60) {
    const a = earliestArrivals(tt, origin, t0 + w, t0 + w + 3 * 3600)
    const r = arrivalAt(tt, a, point)
    const secs = r.at - (t0 + w)
    if (!best || secs < best.secs) best = { secs, a, station: r.station }
  }
  const b = best!
  return { secs: b.secs, legs: b.station < 0 ? [] : legsTo(tt, b.a, b.station) }
}

export type Leg =
  | { kind: 'walk'; from: number | null; to: number }
  | { kind: 'ride'; route: string; from: number; to: number; dep: number; arr: number }

// The legs of the fastest way to station s, first leg first.
export function legsTo(tt: DayTimetable, a: Arrivals, s: number): Leg[] {
  const legs: Leg[] = []
  let cur = s
  for (let guard = 0; guard < 200; guard++) {
    if (a.viaFoot[cur] >= 0) {
      legs.push({ kind: 'walk', from: a.viaFoot[cur], to: cur })
      cur = a.viaFoot[cur]
    } else if (a.viaConn[cur] >= 0) {
      const c = a.viaConn[cur]
      const b = a.boardConn[tt.trip[c]]
      legs.push({ kind: 'ride', route: tt.tripRoute[tt.trip[c]], from: tt.from[b], to: cur, dep: tt.dep[b], arr: tt.arr[c] })
      cur = tt.from[b]
    } else {
      legs.push({ kind: 'walk', from: null, to: cur })
      break
    }
  }
  return legs.reverse()
}

const PACIFIC = new Intl.DateTimeFormat('en-CA', {
  timeZone: 'America/Los_Angeles',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
  hourCycle: 'h23',
})

// Unix ms -> the Pacific calendar date and seconds after its midnight.
export function pacificTime(ms: number): { date: string; sec: number } {
  const parts = Object.fromEntries(PACIFIC.formatToParts(new Date(ms)).map((p) => [p.type, p.value]))
  return { date: `${parts.year}-${parts.month}-${parts.day}`, sec: +parts.hour * 3600 + +parts.minute * 60 + +parts.second }
}
