import type { QuestionRecord, Station, LatLng } from '../types'
import { haversineMiles } from './geo'
import { AIRPORTS } from './airports'

function n(v: unknown): number {
  return typeof v === 'number' ? v : Number(v)
}
function s(v: unknown): string {
  return typeof v === 'string' ? v : String(v ?? '')
}

function nearestAirportMiles(p: LatLng): number {
  return Math.min(...Object.values(AIRPORTS).map((a) => haversineMiles(p, a)))
}

/**
 * Returns true if `station` is still consistent with the answer of `record`.
 * Photo questions (and inactive / non-eliminating records) always return true.
 */
export function stationPasses(station: Station, record: QuestionRecord): boolean {
  if (!record.active || record.vetoed || !record.eliminates) return true
  const p = record.params

  switch (record.kind) {
    case 'radar': {
      const center: LatLng = { lat: n(p.lat), lon: n(p.lon) }
      const within = haversineMiles(station, center) <= n(p.radiusMiles)
      return within === (p.answer === 'yes')
    }
    case 'thermometer': {
      const from: LatLng = { lat: n(p.fromLat), lon: n(p.fromLon) }
      const to: LatLng = { lat: n(p.toLat), lon: n(p.toLon) }
      const gotCloser = haversineMiles(station, to) < haversineMiles(station, from)
      return gotCloser === (p.answer === 'hotter')
    }
    case 'match-county': {
      const same = station.county != null && station.county === s(p.value)
      return same === (p.answer === 'yes')
    }
    case 'match-city': {
      const same = station.city != null && station.city === s(p.value)
      return same === (p.answer === 'yes')
    }
    case 'match-airport': {
      const same = station.nearestAirport === s(p.value)
      return same === (p.answer === 'yes')
    }
    case 'match-namelength': {
      const same = station.nameLength === n(p.value)
      return same === (p.answer === 'yes')
    }
    case 'match-line': {
      const same = station.lines.includes(s(p.value))
      return same === (p.answer === 'yes')
    }
    case 'match-system': {
      const same = station.systems.includes(s(p.value))
      return same === (p.answer === 'yes')
    }
    case 'measure-airport': {
      const seeker = nearestAirportMiles({ lat: n(p.fromLat), lon: n(p.fromLon) })
      const stationDist = Math.min(...Object.values(station.airportDist)) * (1 / 1609.344)
      return (stationDist < seeker) === (p.answer === 'closer')
    }
    case 'measure-sealevel': {
      if (station.elevation == null) return true // unknown: don't eliminate
      return (station.elevation < n(p.value)) === (p.answer === 'closer')
    }
    case 'photo':
      return true
    default:
      return true
  }
}

export interface FilterResult {
  remaining: Station[]
  eliminatedByQuestion: Set<string>
}

export function applyFilters(
  stations: Station[],
  records: QuestionRecord[],
): FilterResult {
  const eliminated = new Set<string>()
  const remaining: Station[] = []
  for (const st of stations) {
    let ok = true
    for (const r of records) {
      if (!stationPasses(st, r)) {
        ok = false
        break
      }
    }
    if (ok) remaining.push(st)
    else eliminated.add(st.id)
  }
  return { remaining, eliminatedByQuestion: eliminated }
}
