import { describe, it, expect } from 'vitest'
import { poiCategoryLabel, QUESTION_POI_CATEGORIES, POI_BY_CATEGORY, nearestPoi, nearestPoiMiles, poiKey } from './poi'
import { poiMatchEliminatedRegion, poiMeasureEliminatedRegion, featureMeasureEliminatedRegion, airportMatchEliminatedRegion, airportMeasureEliminatedRegion, countyMatchEliminatedRegion, cityMatchEliminatedRegion, zipMeasureEliminatedRegion, tentacleEliminatedRegion, metroLineEliminatedRegion, type LatLngMultiPolygon } from './questionRegions'
import { metroLinesWithinRadius, nearestMetroLine, metroLineDistanceMiles } from './metroLines'
import { poisWithinRadius } from './poi'
import { nearestAirport } from './airports'
import { countyAt } from './counties'
import { cityAt, inPlayArea } from './cities'
import { zipAt } from './zip'
import { haversineMiles } from './geo'
import { stationPasses } from './elimination'
import rawStations from '../data/stations.json'
import type { QuestionRecord, Station } from '../types'

// ray-cast point-in-ring on a [lat, lon] ring
function pointInRing(lat: number, lon: number, ring: [number, number][]): boolean {
  let inside = false
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [yi, xi] = ring[i]
    const [yj, xj] = ring[j]
    const intersect = yi > lat !== yj > lat && lon < ((xj - xi) * (lat - yi)) / (yj - yi) + xi
    if (intersect) inside = !inside
  }
  return inside
}

// point is inside a multipolygon if it's in an outer ring and in an odd number of
// rings overall (outer minus holes)
function pointInMulti(lat: number, lon: number, mp: LatLngMultiPolygon): boolean {
  for (const poly of mp) {
    if (!pointInRing(lat, lon, poly[0])) continue
    let inHole = false
    for (let h = 1; h < poly.length; h++) {
      if (pointInRing(lat, lon, poly[h])) inHole = true
    }
    if (!inHole) return true
  }
  return false
}

function rec(
  kind: 'match-poi' | 'measure-poi' | 'measure-feature' | 'match-airport' | 'measure-airport' | 'match-county' | 'match-city',
  params: Record<string, unknown>,
): QuestionRecord {
  return { id: 'q', kind, createdAt: 0, params, eliminates: true, active: true }
}

const SEEKER = { lat: 37.7749, lon: -122.4194 }

describe('poiCategoryLabel', () => {
  it('singularizes -ies plurals (the librarie bug)', () => {
    expect(poiCategoryLabel('library')).toBe('library')
  })
  it('singularizes plain -s plurals and lowercases', () => {
    expect(poiCategoryLabel('museum')).toBe('museum')
    expect(poiCategoryLabel('stadium')).toBe('sports stadium')
    expect(poiCategoryLabel('movie_theater')).toBe('movie theater')
    expect(poiCategoryLabel('consulate')).toBe('foreign consulate')
  })
})

describe('QUESTION_POI_CATEGORIES', () => {
  it('exposes every category we have data for, including the newly added ones', () => {
    for (const k of ['stadium', 'amusement_park', 'zoo', 'aquarium', 'consulate']) {
      expect(QUESTION_POI_CATEGORIES).toContain(k)
    }
  })
  it('only lists categories that actually have baked POIs', () => {
    for (const k of QUESTION_POI_CATEGORIES) {
      expect((POI_BY_CATEGORY[k] ?? []).length).toBeGreaterThan(0)
    }
  })
})

describe('poiMatchEliminatedRegion agrees with the elimination rule', () => {
  const cat = 'stadium' // sparse → big, clean Voronoi cells
  const seekerNearest = nearestPoi(SEEKER, cat)!

  it('YES: shades outside the seeker cell; a same-nearest point is kept (unshaded)', () => {
    const region = poiMatchEliminatedRegion(rec('match-poi', { poiCat: cat, fromLat: SEEKER.lat, fromLon: SEEKER.lon, answer: 'yes' }))!
    expect(region).toBeTruthy()
    // the seeker's own nearest stadium shares the seeker's cell → must NOT be shaded
    expect(pointInMulti(SEEKER.lat, SEEKER.lon, region)).toBe(false)
    // a POI whose nearest stadium differs sits outside the cell → shaded
    const other = POI_BY_CATEGORY[cat].find((p) => poiKey(nearestPoi(p, cat)!) !== poiKey(seekerNearest))!
    expect(pointInMulti(other.lat, other.lon, region)).toBe(true)
  })

  it('NO: shades inside the seeker cell instead', () => {
    const region = poiMatchEliminatedRegion(rec('match-poi', { poiCat: cat, fromLat: SEEKER.lat, fromLon: SEEKER.lon, answer: 'no' }))!
    expect(pointInMulti(SEEKER.lat, SEEKER.lon, region)).toBe(true)
  })
})

describe('poiMeasureEliminatedRegion agrees with the elimination rule', () => {
  const cat = 'hospital'
  const d = nearestPoiMiles(SEEKER, cat)

  it('CLOSER: shades outside the union of your-distance circles', () => {
    const region = poiMeasureEliminatedRegion(rec('measure-poi', { poiCat: cat, fromLat: SEEKER.lat, fromLon: SEEKER.lon, answer: 'closer' }))!
    expect(region).toBeTruthy()
    // the seeker sits d from its nearest hospital → on the boundary; a point right
    // next to a hospital is well within d (kept), so must be unshaded.
    const near = nearestPoi(SEEKER, cat)!
    expect(pointInMulti(near.lat, near.lon, region)).toBe(false)
    // a far-away spot (no hospital within d) is eliminated → shaded
    expect(nearestPoiMiles({ lat: near.lat + 1, lon: near.lon }, cat)).toBeGreaterThan(d)
    expect(pointInMulti(near.lat + 1, near.lon, region)).toBe(true)
  })

  it('FURTHER: shades the union itself (inside a circle is eliminated)', () => {
    const region = poiMeasureEliminatedRegion(rec('measure-poi', { poiCat: cat, fromLat: SEEKER.lat, fromLon: SEEKER.lon, answer: 'further' }))!
    const near = nearestPoi(SEEKER, cat)!
    expect(pointInMulti(near.lat, near.lon, region)).toBe(true)
  })
})

describe('poiMeasureEliminatedRegion boundary is geodesic (no equirectangular drift)', () => {
  // Pleasanton seeker, ~12.3 mi from its nearest zoo (Oakland Zoo). At that
  // radius the old equirectangular disk put the shaded boundary ~36 m off the
  // true circle, so it rendered visibly beside the seeker dot at high zoom. The
  // disk is now a true geodesic circle (same metric as the elimination test), so
  // the boundary must sit on the seeker's own distance d to within a few metres.
  const seeker = { lat: 37.699713, lon: -121.928372 }
  const cat = 'zoo'
  const zoo = nearestPoi(seeker, cat)!
  const d = nearestPoiMiles(seeker, cat)

  // unit direction from the zoo toward the seeker, in local equirectangular space
  const cosLat = Math.cos((zoo.lat * Math.PI) / 180)
  const vx = (seeker.lon - zoo.lon) * cosLat
  const vy = seeker.lat - zoo.lat
  const vlen = Math.hypot(vx, vy)
  const at = (miFromSeeker: number) => {
    const st = miFromSeeker / 69.0
    return { lat: seeker.lat + (vy / vlen) * st, lon: seeker.lon + (vx / vlen) * st / cosLat }
  }

  it('the CLOSER shading boundary sits on d along the seeker radial (<0.01 mi drift)', () => {
    const region = poiMeasureEliminatedRegion(
      rec('measure-poi', { poiCat: cat, fromLat: seeker.lat, fromLon: seeker.lon, answer: 'closer' }),
    )!
    // bisect along the radial: outside d is eliminated (in the complement region),
    // inside d is kept — find where membership flips and compare to d.
    let lo = -0.5
    let hi = 0.5
    for (let i = 0; i < 40; i++) {
      const m = (lo + hi) / 2
      const p = at(m)
      if (pointInMulti(p.lat, p.lon, region)) hi = m
      else lo = m
    }
    const boundary = at((lo + hi) / 2)
    const drift = Math.abs(haversineMiles(zoo, boundary) - d)
    expect(drift).toBeLessThan(0.01) // <~16 m; the old equirect disk drifted ~36 m
  })
})

describe('featureMeasureEliminatedRegion agrees with the elimination rule', () => {
  // seeker ~11 mi from the coast (San Jose); coastal spot ~0 mi, inland ~36 mi
  const seeker = { fromLat: 37.3297, fromLon: -121.9024 }
  const onCoast = { lat: 37.7955, lon: -122.3937 } // SF Embarcadero, inside the corridor
  const inland = { lat: 37.7397, lon: -121.4252 } // Tracy, well past the East Bay shore

  it('CLOSER: shades the complement of the coastal corridor', () => {
    const region = featureMeasureEliminatedRegion(rec('measure-feature', { feature: 'coastline', ...seeker, answer: 'closer' }))!
    expect(region).toBeTruthy()
    expect(pointInMulti(onCoast.lat, onCoast.lon, region)).toBe(false) // kept ⇒ unshaded
    expect(pointInMulti(inland.lat, inland.lon, region)).toBe(true) // eliminated ⇒ shaded
  })

  it('FURTHER: shades the corridor itself', () => {
    const region = featureMeasureEliminatedRegion(rec('measure-feature', { feature: 'coastline', ...seeker, answer: 'further' }))!
    expect(pointInMulti(onCoast.lat, onCoast.lon, region)).toBe(true)
    expect(pointInMulti(inland.lat, inland.lon, region)).toBe(false)
  })
})

describe('airportMatchEliminatedRegion shades the seeker airport Voronoi cell', () => {
  // seeker in SF → nearest airport SFO; SJC is a spot in San Jose
  const sf = { lat: 37.7749, lon: -122.4194 }
  const sanJose = { lat: 37.3382, lon: -121.8863 }

  it('YES keeps the seeker cell (unshaded); a different-airport point is shaded', () => {
    expect(nearestAirport(sf).code).toBe('SFO')
    expect(nearestAirport(sanJose).code).toBe('SJC')
    const region = airportMatchEliminatedRegion(rec('match-airport', { fromLat: sf.lat, fromLon: sf.lon, value: 'SFO', answer: 'yes' }))!
    expect(pointInMulti(sf.lat, sf.lon, region)).toBe(false) // same airport ⇒ kept
    expect(pointInMulti(sanJose.lat, sanJose.lon, region)).toBe(true) // different ⇒ eliminated
  })

  it('NO shades the seeker cell instead', () => {
    const region = airportMatchEliminatedRegion(rec('match-airport', { fromLat: sf.lat, fromLon: sf.lon, value: 'SFO', answer: 'no' }))!
    expect(pointInMulti(sf.lat, sf.lon, region)).toBe(true)
    expect(pointInMulti(sanJose.lat, sanJose.lon, region)).toBe(false)
  })

  // Regression: an unbounded Voronoi cell used to run to lat ±85 and render as a
  // giant triangle/bowtie. The NO region (the cell itself) must stay bounded
  // within the play-area frame (well under lat 40).
  it('NO region stays bounded to the play area (no runaway bowtie)', () => {
    const oak = { lat: 37.7190, lon: -122.2196 } // sits in OAK's cell
    const region = airportMatchEliminatedRegion(rec('match-airport', { fromLat: oak.lat, fromLon: oak.lon, value: 'OAK', answer: 'no' }))!
    const lats = region.flat(2).map(([lat]) => lat)
    expect(Math.max(...lats)).toBeLessThan(40)
    expect(Math.min(...lats)).toBeGreaterThan(35)
  })
})

describe('airportMeasureEliminatedRegion shades the your-distance airport disks', () => {
  const seeker = { lat: 37.7749, lon: -122.4194 } // ~11 mi from SFO

  it('CLOSER: a point on top of SFO is inside the union (kept ⇒ unshaded)', () => {
    const region = airportMeasureEliminatedRegion(rec('measure-airport', { fromLat: seeker.lat, fromLon: seeker.lon, answer: 'closer' }))!
    expect(pointInMulti(37.6191, -122.3816, region)).toBe(false) // SFO itself: within d ⇒ kept
  })

  it('FURTHER: the union around SFO is shaded', () => {
    const region = airportMeasureEliminatedRegion(rec('measure-airport', { fromLat: seeker.lat, fromLon: seeker.lon, answer: 'further' }))!
    expect(pointInMulti(37.6191, -122.3816, region)).toBe(true)
  })
})

describe('countyMatchEliminatedRegion shades outside/inside the seeker county', () => {
  const sf = { lat: 37.7749, lon: -122.4194 }
  const sanJose = { lat: 37.3382, lon: -121.8863 }

  it('YES keeps the seeker county (unshaded); another county is shaded', () => {
    const county = countyAt(sf)
    expect(county).toBe('San Francisco')
    const region = countyMatchEliminatedRegion(rec('match-county', { fromLat: sf.lat, fromLon: sf.lon, value: 'San Francisco', answer: 'yes' }))!
    expect(pointInMulti(sf.lat, sf.lon, region)).toBe(false)
    expect(pointInMulti(sanJose.lat, sanJose.lon, region)).toBe(true)
  })

  it('NO shades the seeker county instead', () => {
    const region = countyMatchEliminatedRegion(rec('match-county', { fromLat: sf.lat, fromLon: sf.lon, value: 'San Francisco', answer: 'no' }))!
    expect(pointInMulti(sf.lat, sf.lon, region)).toBe(true)
    expect(pointInMulti(sanJose.lat, sanJose.lon, region)).toBe(false)
  })
})

describe('cityMatchEliminatedRegion shades outside/inside the seeker city', () => {
  const oakland = { lat: 37.8044, lon: -122.2712 }
  const sanJose = { lat: 37.3382, lon: -121.8863 }

  it('YES keeps the seeker city (unshaded); another city is shaded', () => {
    const city = cityAt(oakland)
    expect(city).toBe('Oakland city')
    const region = cityMatchEliminatedRegion(rec('match-city', { fromLat: oakland.lat, fromLon: oakland.lon, value: 'Oakland city', answer: 'yes' }))!
    expect(pointInMulti(oakland.lat, oakland.lon, region)).toBe(false)
    expect(pointInMulti(sanJose.lat, sanJose.lon, region)).toBe(true)
  })

  it('NO shades the seeker city instead', () => {
    const region = cityMatchEliminatedRegion(rec('match-city', { fromLat: oakland.lat, fromLon: oakland.lon, value: 'Oakland city', answer: 'no' }))!
    expect(pointInMulti(oakland.lat, oakland.lon, region)).toBe(true)
    expect(pointInMulti(sanJose.lat, sanJose.lon, region)).toBe(false)
  })

  it('an in-play but unincorporated point (hills / bridge corridor) is null but in play', () => {
    // ~320 m into the Oakland hills off a BART corridor: no census place names
    // this land, so cityAt is null — but it IS inside the play area, so the form
    // reads it as "unincorporated" rather than "outside the play area".
    const hills = { lat: 37.8845, lon: -122.2311 }
    expect(cityAt(hills)).toBeNull()
    expect(inPlayArea(hills)).toBe(true)
  })

  it('a named unincorporated CDP (Fairview) resolves to its own name', () => {
    expect(cityAt({ lat: 37.6759, lon: -122.0472 })).toBe('Fairview CDP')
  })

  it('SFO airport land resolves to San Francisco city (SF owns SFO)', () => {
    // International Terminal area — unincorporated San Mateo land, SF-owned.
    expect(cityAt({ lat: 37.6156, lon: -122.3921 })).toBe('San Francisco city')
  })

  it('a point outside the play area is null and not in play', () => {
    // out past the Utah line
    const utah = { lat: 41.1621, lon: -112.4561 }
    expect(cityAt(utah)).toBeNull()
    expect(inPlayArea(utah)).toBe(false)
  })
})

describe('tentacleEliminatedRegion agrees with the elimination rule', () => {
  // Downtown SF: several museums within 1 mi → a real restricted Voronoi.
  const cat = 'museum'
  const radiusMi = 1
  const inPlay = poisWithinRadius(SEEKER, cat, radiusMi)

  it('precondition: at least two in-play museums', () => {
    expect(inPlay.length).toBeGreaterThanOrEqual(2)
  })

  it('shades the complement of the answer cell (answer POI kept, others shaded)', () => {
    // answer = the in-play museum nearest the seeker
    let ai = 0, best = Infinity
    inPlay.forEach((p, i) => { const d = haversineMiles(SEEKER, p); if (d < best) { best = d; ai = i } })
    const answer = inPlay[ai]
    const r: QuestionRecord = {
      id: 'q', kind: 'tentacle', createdAt: 0,
      params: { poiCat: cat, radiusMi, fromLat: SEEKER.lat, fromLon: SEEKER.lon, value: poiKey(answer) },
      eliminates: true, active: true,
    }
    const region = tentacleEliminatedRegion(r)!
    expect(region).toBeTruthy()
    // the answer POI is in its own cell → not shaded
    expect(pointInMulti(answer.lat, answer.lon, region)).toBe(false)
    // a different in-play museum sits in another cell → shaded
    const other = inPlay[(ai + 1) % inPlay.length]
    expect(pointInMulti(other.lat, other.lon, region)).toBe(true)
  })

  it('per-station shading matches elimination across the whole dataset', () => {
    const STATIONS = rawStations as unknown as Station[]
    const answer = inPlay[0]
    const r: QuestionRecord = {
      id: 'q', kind: 'tentacle', createdAt: 0,
      params: { poiCat: cat, radiusMi, fromLat: SEEKER.lat, fromLon: SEEKER.lon, value: poiKey(answer) },
      eliminates: true, active: true,
    }
    const region = tentacleEliminatedRegion(r)
    for (const st of STATIONS) {
      const shaded = region ? pointInMulti(st.lat, st.lon, region) : false
      const eliminated = !stationPasses(st, r)
      expect(shaded, `${st.name} shading vs elimination`).toBe(eliminated)
    }
  })
})

describe('metroLineEliminatedRegion (sampled Voronoi) tracks the elimination rule', () => {
  const radiusMi = 15
  const inPlay = metroLinesWithinRadius(SEEKER, radiusMi, SEEKER.lat)

  it('precondition: at least two in-play metro lines', () => {
    expect(inPlay.length).toBeGreaterThanOrEqual(2)
  })

  it('answer line kept (unshaded), a far non-answer line shaded', () => {
    // answer = the in-play line nearest the seeker
    const near = nearestMetroLine(SEEKER, inPlay, SEEKER.lat)!
    const r: QuestionRecord = {
      id: 'q', kind: 'tentacle-line', createdAt: 0,
      params: { radiusMi, fromLat: SEEKER.lat, fromLon: SEEKER.lon, value: near.line.id },
      eliminates: true, active: true,
    }
    const region = metroLineEliminatedRegion(r)!
    expect(region).toBeTruthy()
    // a vertex on the answer line is in its own keep cell → not shaded
    const onAnswer = near.line.polylines[0][0]
    expect(pointInMulti(onAnswer.lat, onAnswer.lon, region)).toBe(false)
    // the farthest in-play line's midpoint sits in another cell → shaded
    let far = inPlay[0], fd = -1
    for (const l of inPlay) {
      const d = metroLineDistanceMiles(SEEKER, l, SEEKER.lat)
      if (d > fd) { fd = d; far = l }
    }
    if (far.id !== near.line.id) {
      const poly = far.polylines[0]
      const mid = poly[Math.floor(poly.length / 2)]
      expect(pointInMulti(mid.lat, mid.lon, region)).toBe(true)
    }
  })

  it('per-station shading matches elimination away from the sampled boundary', () => {
    const STATIONS = rawStations as unknown as Station[]
    const answer = nearestMetroLine(SEEKER, inPlay, SEEKER.lat)!.line
    const r: QuestionRecord = {
      id: 'q', kind: 'tentacle-line', createdAt: 0,
      params: { radiusMi, fromLat: SEEKER.lat, fromLon: SEEKER.lon, value: answer.id },
      eliminates: true, active: true,
    }
    const region = metroLineEliminatedRegion(r)
    for (const st of STATIONS) {
      // margin between the station's nearest in-play line and the answer line;
      // near the boundary the sampled shading can differ from the exact rule, so
      // only assert where the decision is unambiguous (> 1 mi from the boundary).
      let minD = Infinity, answerD = Infinity
      for (const l of inPlay) {
        const d = metroLineDistanceMiles({ lat: st.lat, lon: st.lon }, l, SEEKER.lat)
        if (d < minD) minD = d
        if (l.id === answer.id) answerD = d
      }
      if (Math.abs(answerD - minD) <= 1) continue
      const shaded = region ? pointInMulti(st.lat, st.lon, region) : false
      const eliminated = !stationPasses(st, r)
      expect(shaded, `${st.name} shading vs elimination`).toBe(eliminated)
    }
  })
})

describe('zipMeasureEliminatedRegion agrees with the per-station rule', () => {
  const STATIONS = rawStations as unknown as Station[]
  // Seekers spread across the ZIP range so both answers shade a real split.
  const seekers = [
    { lat: 37.7793, lon: -122.4193 }, // SF 94102
    { lat: 37.8044, lon: -122.2712 }, // Oakland 94612
    { lat: 37.3352, lon: -121.8938 }, // San Jose 95113
  ]
  for (const seeker of seekers) {
    for (const answer of ['smaller', 'larger'] as const) {
      it(`${answer} @ ${seeker.lat},${seeker.lon}: every station's shading matches elimination`, () => {
        const zip = zipAt(seeker)!
        const r: QuestionRecord = {
          id: 'q', kind: 'measure-zip', createdAt: 0,
          params: { fromLat: seeker.lat, fromLon: seeker.lon, value: zip, answer },
          eliminates: true, active: true,
        }
        const region = zipMeasureEliminatedRegion(r)
        for (const st of STATIONS) {
          const shaded = region ? pointInMulti(st.lat, st.lon, region) : false
          const eliminated = !stationPasses(st, r)
          expect(shaded, `${st.name} shading vs elimination`).toBe(eliminated)
        }
      })
    }
  }
})
