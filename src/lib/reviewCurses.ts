import type { LatLng, QuestionRecord, Station } from '../types'
import { arrivalAt, earliestArrivals, legsTo, pacificTime, type DayTimetable } from './transitNetwork'

// A curse a reviewer enters in setup. Its window is curse time: nothing inside
// it is ranked. Listing places where it could be cleared (e.g. where a plane was
// visible for Planespotter) adds one check: the fastest trip to any of them.
export interface ReviewCurse {
  id: string
  name: string
  startAt: number // unix ms, cast
  endAt: number // unix ms, cleared
  clearAt?: string[] // station ids the seekers believed would work then
  hindsightAt?: string[] // places learned later: a side note, never minutes lost
  fromStation?: string // where the seekers were when it was cast
}

export interface ClearTrip {
  fastest: number // minutes from the cast to the nearest listed place
  place: string // station id
  via: string
  took: number // minutes the curse lasted
}

export const curseMinutes = (c: ReviewCurse) => Math.max(0, Math.round((c.endAt - c.startAt) / 60_000))

// The curse whose window overlaps the stretch from `from` to `to`, if any.
export function curseOver(curses: ReviewCurse[], from: number, to: number): ReviewCurse | null {
  return curses.find((c) => c.endAt > c.startAt && from < c.endAt && to > c.startAt) ?? null
}

// Where the seekers were when the curse was cast: the entered station, else the
// spot of the last located question asked by then.
export function curseOrigin(
  c: ReviewCurse,
  questions: QuestionRecord[],
  stations: Station[],
  spotOf: (q: QuestionRecord) => LatLng | null,
): LatLng | null {
  const st = c.fromStation ? stations.find((s) => s.id === c.fromStation) : undefined
  if (st) return { lat: st.lat, lon: st.lon }
  let spot: LatLng | null = null
  for (const q of [...questions].sort((a, b) => a.createdAt - b.createdAt)) {
    if (q.createdAt > c.startAt) break
    spot = spotOf(q) ?? spot
  }
  return spot
}

// Fastest scheduled trip from `origin` at the cast to any of `places`.
export function fastestClear(
  tt: DayTimetable,
  origin: LatLng,
  c: ReviewCurse,
  stations: Station[],
  places: string[] = c.clearAt ?? [],
): ClearTrip | null {
  const { sec } = pacificTime(c.startAt)
  const a = earliestArrivals(tt, origin, sec)
  let best: { at: number; station: number; place: string } | null = null
  for (const id of places) {
    const st = stations.find((s) => s.id === id)
    if (!st) continue
    const r = arrivalAt(tt, a, st)
    if (Number.isFinite(r.at) && (!best || r.at < best.at)) best = { ...r, place: id }
  }
  if (!best) return null
  const rides = best.station < 0 ? [] : legsTo(tt, a, best.station).flatMap((l) => (l.kind === 'ride' ? [l.route] : []))
  return {
    fastest: Math.round((best.at - sec) / 60),
    place: best.place,
    via: rides.length ? rides.join(' → ') : 'walking',
    took: curseMinutes(c),
  }
}
