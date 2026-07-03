import { describe, it, expect } from 'vitest'
import { stationPasses, applyFilters } from './elimination'
import { poisWithinRadius, poiKey, TENTACLE_INSIDE, TENTACLE_OUTSIDE } from './poi'
import { metroLinesWithinRadius, nearestMetroLine, metroLineDistanceMiles, METRO_LINES } from './metroLines'
import type { QuestionRecord, Station } from '../types'

function station(overrides: Partial<Station> = {}): Station {
  return {
    id: 't1',
    name: 'Test Station',
    lat: 37.7749,
    lon: -122.4194,
    systems: ['Muni'],
    lines: ['Muni N'],
    aka: [],
    nameLength: 12,
    county: 'San Francisco',
    city: 'San Francisco',
    elevation: 16,
    airportDist: { SFO: 20000, OAK: 18000, SJC: 70000 },
    nearestAirport: 'OAK',
    service: { wd: { served: true, hourly: true }, we: { served: true, hourly: true } },
    headwayMin: { wd: 12, we: 12 },
    ...overrides,
  }
}

function record(kind: QuestionRecord['kind'], params: Record<string, unknown>): QuestionRecord {
  return { id: 'q1', kind, createdAt: 0, params, eliminates: true, active: true }
}

describe('stationPasses — gating', () => {
  it('always passes when the record is inactive', () => {
    const r = { ...record('match-city', { value: 'Oakland', answer: 'yes' }), active: false }
    expect(stationPasses(station(), r)).toBe(true)
  })
  it('photo questions never eliminate', () => {
    expect(stationPasses(station(), record('photo', {}))).toBe(true)
  })
  it('vetoed questions never eliminate (no answer was given)', () => {
    const far = station({ lat: 37.33, lon: -121.9 })
    const r = record('radar', { lat: 37.7749, lon: -122.4194, radiusMiles: 1, answer: 'yes' })
    expect(stationPasses(far, r)).toBe(false)
    expect(stationPasses(far, { ...r, vetoed: true })).toBe(true)
  })
})

describe('stationPasses — radar', () => {
  const here = { lat: 37.7749, lon: -122.4194 }
  it('keeps a near station on a yes within 1mi', () => {
    expect(stationPasses(station(), record('radar', { ...here, radiusMiles: 1, answer: 'yes' }))).toBe(true)
  })
  it('eliminates a far station on a yes within 1mi', () => {
    const far = station({ lat: 37.33, lon: -121.9 })
    expect(stationPasses(far, record('radar', { ...here, radiusMiles: 1, answer: 'yes' }))).toBe(false)
  })
  it('inverts on a no answer', () => {
    expect(stationPasses(station(), record('radar', { ...here, radiusMiles: 1, answer: 'no' }))).toBe(false)
  })
})

describe('stationPasses — matching', () => {
  it('match-city', () => {
    // city is resolved geometrically from coordinates (not the baked .city field),
    // so shading and elimination always agree.
    const r = record('match-city', { value: 'San Francisco city', fromLat: 37.7749, fromLon: -122.4194, answer: 'yes' })
    expect(stationPasses(station(), r)).toBe(true) // SF coords → same city
    expect(stationPasses(station({ lat: 37.8044, lon: -122.2712 }), r)).toBe(false) // Oakland coords → different
  })
  it('match-namelength', () => {
    const r = record('match-namelength', { value: 12, answer: 'yes' })
    expect(stationPasses(station({ nameLength: 12 }), r)).toBe(true)
    expect(stationPasses(station({ nameLength: 8 }), r)).toBe(false)
  })
  it('match-line', () => {
    const r = record('match-line', { value: 'Muni N', answer: 'yes' })
    expect(stationPasses(station({ lines: ['Muni N', 'Muni T'] }), r)).toBe(true)
    expect(stationPasses(station({ lines: ['Muni K'] }), r)).toBe(false)
  })
})

describe('stationPasses — measuring', () => {
  it('measure-sealevel: lower elevation is "closer" to sea level', () => {
    const r = record('measure-sealevel', { value: 50, answer: 'closer' })
    expect(stationPasses(station({ elevation: 10 }), r)).toBe(true)
    expect(stationPasses(station({ elevation: 200 }), r)).toBe(false)
  })
  it('measure-sealevel: unknown elevation never eliminates', () => {
    const r = record('measure-sealevel', { value: 50, answer: 'closer' })
    expect(stationPasses(station({ elevation: null }), r)).toBe(true)
  })
})

describe('stationPasses — match-poi (nearest place of a type)', () => {
  const here = { lat: 37.7749, lon: -122.4194 } // downtown SF
  const far = { lat: 37.3352, lon: -121.8811 } // San Jose (different nearest park)
  it('a station co-located with the seeker shares the nearest park', () => {
    const r = record('match-poi', { poiCat: 'park', fromLat: here.lat, fromLon: here.lon, answer: 'yes' })
    expect(stationPasses(station(here), r)).toBe(true)
    expect(stationPasses(station(here), { ...r, params: { ...r.params, answer: 'no' } })).toBe(false)
  })
  it('a far station has a different nearest park (eliminated on yes)', () => {
    const r = record('match-poi', { poiCat: 'park', fromLat: here.lat, fromLon: here.lon, answer: 'yes' })
    expect(stationPasses(station(far), r)).toBe(false)
    expect(stationPasses(station(far), { ...r, params: { ...r.params, answer: 'no' } })).toBe(true)
  })
  it('unknown category never eliminates', () => {
    const r = record('match-poi', { poiCat: 'nonesuch', fromLat: here.lat, fromLon: here.lon, answer: 'yes' })
    expect(stationPasses(station(far), r)).toBe(true)
  })
})

describe('stationPasses — measure-poi (distance to nearest place of a type)', () => {
  const here = { lat: 37.7749, lon: -122.4194 }
  it('a co-located station ties the seeker; tie folds into "closer" (kept on closer, dropped on further)', () => {
    const r = record('measure-poi', { poiCat: 'park', fromLat: here.lat, fromLon: here.lon, answer: 'closer' })
    expect(stationPasses(station(here), r)).toBe(true)
    expect(stationPasses(station(here), { ...r, params: { ...r.params, answer: 'further' } })).toBe(false)
  })
  it('unknown category never eliminates', () => {
    const r = record('measure-poi', { poiCat: 'nonesuch', fromLat: here.lat, fromLon: here.lon, answer: 'closer' })
    expect(stationPasses(station(here), r)).toBe(true)
  })
  it('sea level: an equal altitude ties and folds into "closer" (lower)', () => {
    // station.elevation (16) exactly equals the seeker’s stated altitude.
    const r = record('measure-sealevel', { value: 16, answer: 'closer' })
    expect(stationPasses(station({ elevation: 16 }), r)).toBe(true)
    expect(stationPasses(station({ elevation: 16 }), { ...r, params: { ...r.params, answer: 'further' } })).toBe(false)
  })
})

describe('stationPasses — measure-zip (ZIP smaller / larger)', () => {
  // Real ZCTA-resolved ZIPs: SF downtown 94102, Oakland 94612, San Jose 95113.
  const sf = station({ id: 'sf', lat: 37.7793, lon: -122.4193 }) // 94102
  const oak = station({ id: 'oak', lat: 37.8044, lon: -122.2712 }) // 94612
  const sj = station({ id: 'sj', lat: 37.3352, lon: -121.8938 }) // 95113
  // Seeker stands in Oakland (94612); pass the resolved ZIP as value.
  const seeker = { fromLat: 37.8044, fromLon: -122.2712, value: '94612' }

  it('"smaller" keeps ZIPs <= the seeker (tie folds into smaller)', () => {
    const r = record('measure-zip', { ...seeker, answer: 'smaller' })
    expect(stationPasses(sf, r)).toBe(true) // 94102 < 94612
    expect(stationPasses(oak, r)).toBe(true) // 94612 == 94612 tie → kept
    expect(stationPasses(sj, r)).toBe(false) // 95113 > 94612
  })
  it('"larger" keeps ZIPs strictly greater (equal is dropped)', () => {
    const r = record('measure-zip', { ...seeker, answer: 'larger' })
    expect(stationPasses(sf, r)).toBe(false)
    expect(stationPasses(oak, r)).toBe(false) // tie is on the smaller side
    expect(stationPasses(sj, r)).toBe(true)
  })
  it('falls back to the seeker coordinate when no ZIP value is stored', () => {
    const r = record('measure-zip', { fromLat: 37.8044, fromLon: -122.2712, answer: 'smaller' })
    expect(stationPasses(sf, r)).toBe(true)
    expect(stationPasses(sj, r)).toBe(false)
  })
})

describe('stationPasses — measure-feature (distance to a coastline / border)', () => {
  // coastal SF station is ~0 mi from the saltwater shore; inland Antioch is ~30 mi
  const coastal = station({ id: 'sf-embarcadero', lat: 37.7955, lon: -122.3937 })
  const inland = station({ id: 'antioch', lat: 38.0169, lon: -121.8009 })
  // seeker at San Jose Diridon (~10 mi from the coast)
  const seeker = { fromLat: 37.3297, fromLon: -121.9024 }

  it('coastline: keeps stations on the seeker\u2019s side of the corridor', () => {
    const closer = record('measure-feature', { feature: 'coastline', ...seeker, answer: 'closer' })
    expect(stationPasses(coastal, closer)).toBe(true) // 0 < 10
    expect(stationPasses(inland, closer)).toBe(false) // 30 !< 10
    const further = record('measure-feature', { feature: 'coastline', ...seeker, answer: 'further' })
    expect(stationPasses(coastal, further)).toBe(false)
    expect(stationPasses(inland, further)).toBe(true)
  })

  it('state border is outside the Bay Area play area, so it has no geometry and never eliminates', () => {
    // Rulebook: a feature outside the map boundary doesn't exist for the game.
    // The CA state line is far east of the play area, so state-border is clipped
    // to empty and any state-border question is a no-op (also not offered).
    const r = record('measure-feature', { feature: 'state-border', fromLat: 37.7955, fromLon: -122.3937, answer: 'closer' })
    expect(stationPasses(inland, r)).toBe(true)
    expect(stationPasses(coastal, r)).toBe(true)
  })

  it('unknown feature never eliminates', () => {
    const r = record('measure-feature', { feature: 'nonesuch', ...seeker, answer: 'closer' })
    expect(stationPasses(coastal, r)).toBe(true)
  })
})

describe('stationPasses — tentacle (nearest in-radius place)', () => {
  // Downtown SF has several museums within 1 mi; an ocean point has none. We
  // derive the in-play set with the same helper the engine uses so the test
  // stays correct regardless of the exact POI data.
  const seeker = { lat: 37.7749, lon: -122.4194 }
  const inPlay = poisWithinRadius(seeker, 'museum', 1)
  const base = { poiCat: 'museum', radiusMi: 1, fromLat: seeker.lat, fromLon: seeker.lon }

  it('precondition: at least two museums are in play', () => {
    expect(inPlay.length).toBeGreaterThanOrEqual(2)
  })

  it('keeps a station whose nearest in-play museum is the answer, drops it otherwise', () => {
    // A station co-located with inPlay[0] is nearest to inPlay[0].
    const at0 = station({ lat: inPlay[0].lat, lon: inPlay[0].lon })
    const keep = record('tentacle', { ...base, value: poiKey(inPlay[0]) })
    const drop = record('tentacle', { ...base, value: poiKey(inPlay[1]) })
    expect(stationPasses(at0, keep)).toBe(true)
    expect(stationPasses(at0, drop)).toBe(false)
  })

  it('an out-of-radius museum closer to the station never counts', () => {
    // San Jose has its own museums; but the answer set is fixed to SF's in-play
    // museums, so a San Jose station's nearest *in-play* museum is an SF one.
    const sj = station({ lat: 37.3352, lon: -121.8938 })
    // Whatever SF in-play museum is nearest to the SJ station is the only answer
    // that keeps it; pick a different one and it is eliminated.
    let nearestIdx = 0
    let best = Infinity
    inPlay.forEach((p, i) => {
      const d = Math.hypot(p.lat - sj.lat, p.lon - sj.lon)
      if (d < best) { best = d; nearestIdx = i }
    })
    const other = inPlay[(nearestIdx + 1) % inPlay.length]
    const drop = record('tentacle', { ...base, value: poiKey(other) })
    expect(stationPasses(sj, drop)).toBe(false)
  })

  it('answer not among the in-play set never eliminates', () => {
    const r = record('tentacle', { ...base, value: 'not-a-real-poi-key' })
    expect(stationPasses(station(seeker), r)).toBe(true)
  })

  it('no in-play POIs (seeker offshore) never eliminates', () => {
    const r = record('tentacle', { poiCat: 'museum', radiusMi: 1, fromLat: 37.70, fromLon: -122.55, value: 'anything' })
    expect(stationPasses(station(seeker), r)).toBe(true)
  })

  it('radar answer: "within" keeps the disk, "not within" drops it', () => {
    const near = station(seeker) // on the seeker → inside the 1 mi disk
    const far = station({ lat: 37.90, lon: -122.40 }) // ~14 mi away → outside
    const inside = record('tentacle', { ...base, value: TENTACLE_INSIDE })
    const outside = record('tentacle', { ...base, value: TENTACLE_OUTSIDE })
    expect(stationPasses(near, inside)).toBe(true)
    expect(stationPasses(far, inside)).toBe(false)
    expect(stationPasses(near, outside)).toBe(false)
    expect(stationPasses(far, outside)).toBe(true)
  })
})

describe('stationPasses — tentacle-line (nearest in-radius metro line)', () => {
  // Downtown SF: many BART/Muni lines pass within 15 mi. Derive the in-play set
  // with the same helper the engine uses so the test tracks the real geometry.
  const seeker = { lat: 37.7749, lon: -122.4194 }
  const inPlay = metroLinesWithinRadius(seeker, 15, seeker.lat)
  const base = { radiusMi: 15, fromLat: seeker.lat, fromLon: seeker.lon }

  it('precondition: at least two metro lines are in play', () => {
    expect(inPlay.length).toBeGreaterThanOrEqual(2)
  })

  it('keeps a station on the answer line, drops it when the answer is a line it is far from', () => {
    // A station sitting on the seeker point lies ~on the closest in-play line.
    const near = nearestMetroLine(seeker, inPlay, seeker.lat)!
    const keep = record('tentacle-line', { ...base, value: near.line.id })
    expect(stationPasses(station(seeker), keep)).toBe(true)
    // Pick an in-play line the station is NOT closest to → eliminated.
    const other = inPlay.find((l) => l.id !== near.line.id)!
    const drop = record('tentacle-line', { ...base, value: other.id })
    // Only assert elimination when that other line is genuinely farther.
    const dOther = metroLineDistanceMiles(seeker, other, seeker.lat)
    if (dOther > near.d + 1e-6) expect(stationPasses(station(seeker), drop)).toBe(false)
  })

  it('a line outside the radius never counts', () => {
    // Seeker in San Jose; VTA lines are in play, far-north BART/Muni may be out
    // of 15 mi. An out-of-range line id is not among the in-play set → never
    // eliminates (treated as "answer line not in play").
    const sj = { lat: 37.3352, lon: -121.8938 }
    const inPlaySj = metroLinesWithinRadius(sj, 15, sj.lat)
    const outOfRange = METRO_LINES.find((l) => !inPlaySj.some((p) => p.id === l.id))
    if (outOfRange) {
      const r = record('tentacle-line', { radiusMi: 15, fromLat: sj.lat, fromLon: sj.lon, value: outOfRange.id })
      expect(stationPasses(station(sj), r)).toBe(true)
    }
  })

  it('answer not among the in-play set never eliminates', () => {
    const r = record('tentacle-line', { ...base, value: 'not-a-real-line-id' })
    expect(stationPasses(station(seeker), r)).toBe(true)
  })

  it('no in-play lines (seeker far offshore) never eliminates', () => {
    const r = record('tentacle-line', { radiusMi: 15, fromLat: 36.0, fromLon: -124.5, value: 'anything' })
    expect(stationPasses(station(seeker), r)).toBe(true)
  })
})

describe('applyFilters', () => {
  it('partitions stations into remaining and eliminated', () => {
    const a = station({ id: 'a', lat: 37.7749, lon: -122.4194 }) // San Francisco
    const b = station({ id: 'b', lat: 37.8044, lon: -122.2712 }) // Oakland
    const { remaining, eliminatedByQuestion } = applyFilters(
      [a, b],
      [record('match-city', { value: 'San Francisco city', fromLat: 37.7749, fromLon: -122.4194, answer: 'yes' })],
    )
    expect(remaining.map((s) => s.id)).toEqual(['a'])
    expect(eliminatedByQuestion.has('b')).toBe(true)
  })
})
