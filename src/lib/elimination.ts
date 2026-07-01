import type { QuestionRecord, Station, LatLng } from '../types'
import { haversineMiles } from './geo'
import { AIRPORTS } from './airports'
import { nearestPoi, nearestPoiMiles, poiKey } from './poi'
import { projectedDistanceToFeatureMiles } from './measureFeatures'
import { cityAt } from './cities'

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
      // Resolve both sides through the same place-polygon lookup so shading and
      // elimination agree. Prefer the stored seeker city; fall back to the
      // seeker coordinate. The station's city comes from its coordinate too (not
      // the baked geocoder value), so a station's shaded/kept status matches
      // exactly where its dot sits relative to the seeker's city polygon.
      const seekerCity = s(p.value) || cityAt({ lat: n(p.fromLat), lon: n(p.fromLon) })
      if (!seekerCity) return true // seeker not in any city: can't eliminate
      const stationCity = cityAt(station)
      const same = stationCity != null && stationCity === seekerCity
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
    case 'match-poi': {
      const cat = s(p.poiCat)
      const seeker = nearestPoi({ lat: n(p.fromLat), lon: n(p.fromLon) }, cat)
      const st = nearestPoi(station, cat)
      if (!seeker || !st) return true // no data for this category: don't eliminate
      const same = poiKey(seeker) === poiKey(st)
      return same === (p.answer === 'yes')
    }
    case 'measure-poi': {
      const cat = s(p.poiCat)
      const seekerD = nearestPoiMiles({ lat: n(p.fromLat), lon: n(p.fromLon) }, cat)
      const stationD = nearestPoiMiles(station, cat)
      if (!Number.isFinite(seekerD) || !Number.isFinite(stationD)) return true
      return (stationD < seekerD) === (p.answer === 'closer')
    }
    case 'measure-feature': {
      const key = s(p.feature)
      const seeker = { lat: n(p.fromLat), lon: n(p.fromLon) }
      // Measure both the seeker and the station in the same seeker-centred flat
      // projection the shading buffer is built in, so eliminate/keep and the
      // shaded boundary always agree (see projectedDistanceToFeatureMiles).
      const seekerD = projectedDistanceToFeatureMiles(seeker, key, seeker.lat)
      const stationD = projectedDistanceToFeatureMiles({ lat: station.lat, lon: station.lon }, key, seeker.lat)
      if (!Number.isFinite(seekerD) || !Number.isFinite(stationD)) return true
      return (stationD < seekerD) === (p.answer === 'closer')
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
