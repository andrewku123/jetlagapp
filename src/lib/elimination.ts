import type { QuestionRecord, Station, LatLng } from '../types'
import { haversineMiles } from './geo'
import { AIRPORTS } from './airports'
import { nearestPoi, nearestPoiMiles, poiKey, poisWithinRadius, TENTACLE_OUTSIDE, TENTACLE_INSIDE } from './poi'
import { metroLineDistanceMiles, metroLinesWithinRadius } from './metroLines'
import { projectedDistanceToFeatureMiles } from './measureFeatures'
import { cityAt } from './cities'
import { zipAt } from './zip'

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
      // Tie rule: an equal value counts as the smaller side, so the hider
      // answers "closer" when exactly equidistant. Keep the smaller side
      // inclusive (<=) so an equal station survives "closer" (never dropping the
      // true hider); "further" stays strict (>).
      return (stationD <= seekerD) === (p.answer === 'closer')
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
      // Tie folds into the smaller side ("closer"): keep <= inclusive.
      return (stationD <= seekerD) === (p.answer === 'closer')
    }
    case 'measure-airport': {
      const seeker = nearestAirportMiles({ lat: n(p.fromLat), lon: n(p.fromLon) })
      const stationDist = Math.min(...Object.values(station.airportDist)) * (1 / 1609.344)
      // Tie folds into the smaller side ("closer"): keep <= inclusive.
      return (stationDist <= seeker) === (p.answer === 'closer')
    }
    case 'measure-sealevel': {
      if (station.elevation == null) return true // unknown: don't eliminate
      // Tie folds into the smaller side ("closer" = lower altitude): keep <=.
      return (station.elevation <= n(p.value)) === (p.answer === 'closer')
    }
    case 'measure-zip': {
      // Resolve both sides through the same ZCTA lookup so shading and
      // elimination agree. Prefer the stored seeker ZIP; fall back to the seeker
      // coordinate. The station's ZIP comes from its coordinate too.
      const seekerZipStr = s(p.value) || zipAt({ lat: n(p.fromLat), lon: n(p.fromLon) }) || ''
      const stationZipStr = zipAt(station) || ''
      if (!seekerZipStr || !stationZipStr) return true // no ZIP data: don't eliminate
      const seekerZip = Number(seekerZipStr)
      const stationZip = Number(stationZipStr)
      // Tie folds into the smaller side ("smaller"): keep <= inclusive so an
      // equal-ZIP station survives "smaller" (never dropping the true hider);
      // "larger" stays strict (>).
      return (stationZip <= seekerZip) === (p.answer === 'smaller')
    }
    case 'tentacle': {
      // "Of all the <cat> within <radius> of me, which are you closest to?"
      // Only POIs within the radius of the seeker are in play; the answer
      // (p.value = poiKey) is the in-play POI the hider is closest to. Keep a
      // station iff its nearest *in-play* POI is that answer — a POI outside the
      // radius never counts, even if it is physically closer to the station.
      const cat = s(p.poiCat)
      const radius = n(p.radiusMi)
      const answerKey = s(p.value)
      if (!answerKey || !Number.isFinite(radius)) return true
      const seeker: LatLng = { lat: n(p.fromLat), lon: n(p.fromLon) }
      // Radar-style answers: the hider revealed only whether they are within the
      // radius of the seeker (used when 0-or-1 POI is in play, and as the always-
      // available "not within" answer). Keep the disk for "within", drop it for
      // "not within" — exactly a radar yes/no centred on the seeker.
      if (answerKey === TENTACLE_INSIDE) return haversineMiles(station, seeker) <= radius
      if (answerKey === TENTACLE_OUTSIDE) return haversineMiles(station, seeker) > radius
      const inPlay = poisWithinRadius(seeker, cat, radius)
      if (inPlay.length === 0) return true // nothing in play: eliminate nothing
      // A normal (named-POI) answer means the hider is within the radius of the
      // seeker — otherwise they'd answer "not within". So, like a radar "yes",
      // everything outside the disk is eliminated too. This holds even in endgame
      // (the hider must still be within the radius to answer). Skipped only for the
      // 0/1-POI case, which is asked as a radar (handled by the sentinels above).
      if (inPlay.length >= 2 && haversineMiles(station, seeker) > radius) return false
      let minD = Infinity
      let answerD = Infinity
      for (const poi of inPlay) {
        const d = haversineMiles(station, poi)
        if (d < minD) minD = d
        if (poiKey(poi) === answerKey && d < answerD) answerD = d
      }
      if (!Number.isFinite(answerD)) return true // answer not among in-play POIs
      // Keep when the answer POI is (tied for) the station's nearest in-play POI.
      // The tiny epsilon folds an exact tie into "keep" so a station equidistant
      // between the answer and another POI is never wrongly eliminated.
      return answerD <= minD + 1e-9
    }
    case 'tentacle-line': {
      // Metro Lines tentacle: "Of all the metro lines within <radius> of me,
      // which are you closest to?" In-play lines are those passing within the
      // radius of the seeker; the answer (p.value = line id) is the in-play line
      // the hider is closest to. Keep a station iff its nearest in-play line is
      // that answer. All distances use the seeker-centred projection so the
      // keep/drop decision agrees with the shaded region.
      const radius = n(p.radiusMi)
      const answerId = s(p.value)
      if (!answerId || !Number.isFinite(radius)) return true
      const seeker: LatLng = { lat: n(p.fromLat), lon: n(p.fromLon) }
      // Radar-style answers (see the 'tentacle' case): within/not-within the disk.
      if (answerId === TENTACLE_INSIDE) return haversineMiles(station, seeker) <= radius
      if (answerId === TENTACLE_OUTSIDE) return haversineMiles(station, seeker) > radius
      const inPlay = metroLinesWithinRadius(seeker, radius, seeker.lat)
      if (inPlay.length === 0) return true // nothing in play: eliminate nothing
      // Normal answer ⇒ hider within the radius (else they'd answer "not within"),
      // so eliminate everything outside the disk too — like a radar "yes". Holds
      // even in endgame; skipped only for the 0/1-line radar case (sentinels above).
      if (inPlay.length >= 2 && haversineMiles(station, seeker) > radius) return false
      let minD = Infinity
      let answerD = Infinity
      for (const line of inPlay) {
        const d = metroLineDistanceMiles({ lat: station.lat, lon: station.lon }, line, seeker.lat)
        if (d < minD) minD = d
        if (line.id === answerId && d < answerD) answerD = d
      }
      if (!Number.isFinite(answerD)) return true // answer line not in play
      return answerD <= minD + 1e-9 // keep when answer line is (tied) nearest
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
