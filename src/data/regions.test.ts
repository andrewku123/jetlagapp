import { describe, it, expect, vi, afterEach } from 'vitest'
import type { Station } from '../types'

// Loads the region registry fresh with a given active region selected, so we can
// assert the per-map question demotion (LOG_ONLY_KINDS) and the play-area airport
// scoping without the page reload the real switcher does.
async function loadFor(id: string) {
  vi.resetModules()
  const store: Record<string, string> = { 'bahs.region': id }
  vi.stubGlobal('localStorage', {
    getItem: (k: string) => store[k] ?? null,
    setItem: () => {},
  })
  return await import('./regions')
}

async function blurbFor(id: string, kind: string) {
  await loadFor(id)
  const { QUESTION_CATALOG } = await import('./questions')
  return QUESTION_CATALOG.find((q) => q.kind === kind)!.blurb
}

afterEach(() => {
  vi.unstubAllGlobals()
  vi.resetModules()
})

describe('game size', () => {
  it('every map declares its own size, and the printed card reads the same file', async () => {
    const m = await loadFor('bayarea')
    const { GAME_SIZES } = await import('./questionSets')
    for (const r of m.REGIONS) {
      expect(GAME_SIZES).toContain(m.REGION_SIZES[r.id])
    }
    // A fresh board plays the active map's declared size — DC is 98 stations
    // and still Medium, so nothing may infer size from the station count.
    const dc = await loadFor('dc')
    expect(dc.MAP_SIZE).toBe('medium')
    const { emptyGame } = await import('../lib/storage')
    expect(emptyGame.gameSize).toBe('medium')
  })
})

describe('every map has one city per station', () => {
  it("Station.city is the polygon lookup's answer, on every map", async () => {
    // Two sources for a station's city is how the app came to print one city and
    // eliminate on another (Bay Fair read "Ashland CDP" from the Census geocoder
    // while sitting in San Leandro). The baked field is written from these same
    // polygons — `build_attributes.py --cities-only` — so they can't drift.
    for (const id of ['bayarea', 'sfmuni', 'la', 'dc']) {
      const m = await loadFor(id)
      const { cityAt } = await import('../lib/cities')
      for (const s of m.ACTIVE_REGION.stations as Station[]) {
        expect([id, s.name, s.city ?? null]).toEqual([id, s.name, cityAt(s)])
      }
    }
  })
})

describe('play-area scoping and question demotion', () => {
  it('Bay Area contains SFO/OAK/SJC and demotes nothing but the single-state question', async () => {
    const m = await loadFor('bayarea')
    expect(Object.keys(m.AIRPORTS).sort()).toEqual(['OAK', 'SFO', 'SJC'])
    expect(m.HAS_AIRPORTS).toBe(true)
    // One state (California) and no state polygons → "same state?" is log-only.
    expect(m.MULTI_STATE).toBe(false)
    expect([...m.LOG_ONLY_KINDS]).toEqual(['match-admin1'])
    expect([...m.ENDGAME_ELIMINATES_KINDS]).toEqual([])
  })

  it('SF Muni: no in-play airport → airports log-only; county/city endgame-only (line kept)', async () => {
    const m = await loadFor('sfmuni')
    // All three airports are outside San Francisco → the rule "outside the play
    // area = doesn't exist" leaves the SF map with none, so airport questions
    // are useless in every phase.
    expect(Object.keys(m.AIRPORTS)).toEqual([])
    expect(m.HAS_AIRPORTS).toBe(false)
    expect([...m.LOG_ONLY_KINDS].sort()).toEqual([
      'match-admin1',
      'match-airport',
      'measure-airport',
    ])
    // County/city can't split the all-SF station list, but they still carve the
    // endgame hiding zone at the SF↔San Mateo border, so they're endgame-only.
    expect([...m.ENDGAME_ELIMINATES_KINDS].sort()).toEqual(['match-city', 'match-county'])
    // 7 Muni lines still discriminate, so line Matching keeps eliminating.
    expect(m.LOG_ONLY_KINDS.has('match-line')).toBe(false)
  })

  it('LA Metro: LAX/LGB in play; single county never carves → county full log-only; multi-city stays live', async () => {
    const m = await loadFor('la')
    // LAX + LGB sit inside the play area; BUR/ONT/SNA fall outside, so the
    // nearest-airport questions stay fully live.
    expect(Object.keys(m.AIRPORTS).sort()).toEqual(['LAX', 'LGB'])
    expect(m.HAS_AIRPORTS).toBe(true)
    // Every station is deep inside Los Angeles County (nearest is ~3 km from the
    // county line, far beyond the 0.25 mi endgame disk), so "same county?" can't
    // split the map OR carve the endgame zone → full log-only, not endgame-only.
    expect(m.LOG_ONLY_KINDS.has('match-county')).toBe(true)
    expect(m.ENDGAME_ELIMINATES_KINDS.has('match-county')).toBe(false)
    // The map spans many cities (LA, Long Beach, Santa Monica, …) so city
    // Matching still discriminates and is neither log-only nor endgame-only.
    expect(m.LOG_ONLY_KINDS.has('match-city')).toBe(false)
    expect(m.ENDGAME_ELIMINATES_KINDS.has('match-city')).toBe(false)
    // 8 Metro lines (A/B/C/D/E/K/G/J) still discriminate.
    expect(m.LOG_ONLY_KINDS.has('match-line')).toBe(false)
  })

  it('the airport blurb names the active map\'s own airports', async () => {
    expect(await blurbFor('bayarea', 'match-airport')).toContain('(SFO/OAK/SJC)')
    expect(await blurbFor('la', 'match-airport')).toContain('(LAX/LGB)')
    // No airport in play → the question is log-only anyway, and the blurb must
    // not name airports the seeker can't reach.
    expect(await blurbFor('sfmuni', 'match-airport')).toBe(
      'Is your nearest commercial airport the same as mine?',
    )
  })

  it('Washington DC: three states make "same state?" a real eliminator; DCA/IAD in play, BWI out', async () => {
    const m = await loadFor('dc')
    // BWI is 10 mi outside the play area, so it is not a valid answer here.
    expect(Object.keys(m.AIRPORTS).sort()).toEqual(['DCA', 'IAD'])
    // Stations split 40 DC / 32 VA / 26 MD, and the map ships state polygons —
    // the first map where the 1st-admin question can eliminate.
    expect(m.MULTI_STATE).toBe(true)
    expect(m.LOG_ONLY_KINDS.has('match-admin1')).toBe(false)
    // Seven county-equivalents and six lines: nothing else demotes.
    expect([...m.LOG_ONLY_KINDS]).toEqual([])
    expect([...m.ENDGAME_ELIMINATES_KINDS]).toEqual([])
  })

  it('every DC station carries the fields the app reads at load', async () => {
    const stations = (await import('./dc.stations.json')).default as unknown as Station[]
    expect(stations.length).toBe(98)
    for (const s of stations) {
      // headwayMin is read on first render (eligibility filter), so a station
      // missing it blanks the whole app rather than degrading.
      expect(typeof s.headwayMin.wd).toBe('number')
      expect(typeof s.headwayMin.we).toBe('number')
      expect(typeof s.service.wd.served).toBe('boolean')
      expect(s.state).toBeTruthy()
      expect(s.county).toBeTruthy()
      expect(s.lines.length).toBeGreaterThan(0)
    }
    // Metrorail's worst branch gap is ~20 min, so every station is eligible on
    // both day types — the map has no "weekend-only ineligible" stations.
    expect(Math.max(...stations.map((s) => Math.max(s.headwayMin.wd, s.headwayMin.we)))).toBeLessThanOrEqual(20)
  })

  it('DC: a coordinate resolves to its real state, county and city across the river', async () => {
    await loadFor('dc')
    const { stateAt } = await import('../lib/states')
    const { countyAt } = await import('../lib/counties')
    const { cityAt } = await import('../lib/cities')
    // Metro Center (DC), Rosslyn (Arlington, VA) and Bethesda (Montgomery, MD)
    // are a mile or two apart but answer the state question three different ways.
    const metroCenter = { lat: 38.8983, lon: -77.0281 }
    const rosslyn = { lat: 38.8963, lon: -77.0716 }
    const bethesda = { lat: 38.9843, lon: -77.0947 }
    expect(stateAt(metroCenter)).toBe('District of Columbia')
    expect(stateAt(rosslyn)).toBe('Virginia')
    expect(stateAt(bethesda)).toBe('Maryland')
    expect(countyAt(metroCenter)).toBe('District of Columbia')
    expect(countyAt(rosslyn)).toBe('Arlington')
    expect(countyAt(bethesda)).toBe('Montgomery')
    expect(cityAt(bethesda)).toBe('Bethesda CDP')
  })

  it('DC: in-play land outside every place has no city, and a station can be on it', async () => {
    await loadFor('dc')
    const { cityAt, inPlayArea } = await import('../lib/cities')
    const stations = (await import('./dc.stations.json')).default as unknown as Station[]
    // New Carrollton station sits ~430 m outside every place polygon, on
    // unincorporated land between the places it is named after — in play (its
    // hiding zone is), but with no municipality to match. With a snap tolerance
    // it read "New Carrollton city" and then wasn't shaded, since the shading
    // draws the polygon the lookup had stretched.
    const nc = stations.find((s) => s.name === 'New Carrollton')!
    expect(cityAt(nc)).toBeNull()
    expect(nc.city ?? null).toBeNull()
    expect(inPlayArea(nc)).toBe(true)
    // The city it is named after is right there, and still resolves.
    expect(cityAt({ lat: 38.9585, lon: -76.8814 })).toBe('New Carrollton city')
  })

  it('DC state Matching eliminates exactly the stations the shading covers', async () => {
    await loadFor('dc')
    const { stationPasses } = await import('../lib/elimination')
    const stations = (await import('./dc.stations.json')).default as unknown as Station[]
    const rosslyn = { lat: 38.8963, lon: -77.0716 } // Virginia
    const record = {
      id: 'q1',
      kind: 'match-admin1' as const,
      params: { value: 'Virginia', fromLat: rosslyn.lat, fromLon: rosslyn.lon, answer: 'yes' },
      active: true,
      vetoed: false,
      eliminates: true,
    }
    const kept = stations.filter((s) => stationPasses(s, record as never))
    expect(kept.length).toBe(stations.filter((s) => s.state === 'Virginia').length)
    expect(kept.every((s) => s.state === 'Virginia')).toBe(true)
    // "No" keeps the exact complement.
    const no = { ...record, params: { ...record.params, answer: 'no' } }
    const keptNo = stations.filter((s) => stationPasses(s, no as never))
    expect(keptNo.length + kept.length).toBe(stations.length)
  })

  it('the state blurb names the active map\'s own state', async () => {
    for (const id of ['bayarea', 'sfmuni', 'la']) {
      expect(await blurbFor(id, 'match-admin1')).toContain('is in California')
    }
    // A map spanning a state line can't claim uniformity, so it gives the other
    // reason instead of naming a state.
    vi.resetModules()
    vi.doMock('./regions', async () => ({
      ...(await vi.importActual<typeof import('./regions')>('./regions')),
      MAP_STATES: ['Illinois', 'Indiana'],
    }))
    const { QUESTION_CATALOG } = await import('./questions')
    expect(QUESTION_CATALOG.find((q) => q.kind === 'match-admin1')!.blurb).toContain(
      'no per-station state data',
    )
    vi.doUnmock('./regions')
  })

  it('SF Muni: border endgame-zone sliver reads its real city/county (Brisbane, San Mateo)', async () => {
    await loadFor('sfmuni')
    const { countyAt } = await import('../lib/counties')
    const { cityAt, inPlayArea } = await import('../lib/cities')
    // Bayshore/Sunnydale's 0.25 mi endgame hiding zone spills south past the SF
    // line into Brisbane (San Mateo). That sliver is still in play, and must name
    // its true city/county so endgame county/city carving is correct — not
    // "unincorporated / outside the play area", nor a wrong "San Francisco".
    const border = { lat: 37.7062, lon: -122.4048 }
    expect(inPlayArea(border)).toBe(true)
    expect(cityAt(border)).toBe('Brisbane city')
    expect(countyAt(border)).toBe('San Mateo')
    // A point just inside SF proper still resolves to San Francisco.
    const central = { lat: 37.76, lon: -122.44 }
    expect(cityAt(central)).toBe('San Francisco city')
    expect(countyAt(central)).toBe('San Francisco')
  })
})
