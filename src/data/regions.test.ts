import { describe, it, expect, vi, afterEach } from 'vitest'

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

async function airportBlurb(id: string) {
  await loadFor(id)
  const { QUESTION_CATALOG } = await import('./questions')
  return QUESTION_CATALOG.find((q) => q.kind === 'match-airport')!.blurb
}

afterEach(() => {
  vi.unstubAllGlobals()
  vi.resetModules()
})

describe('play-area scoping and question demotion', () => {
  it('Bay Area contains SFO/OAK/SJC and demotes nothing', async () => {
    const m = await loadFor('bayarea')
    expect(Object.keys(m.AIRPORTS).sort()).toEqual(['OAK', 'SFO', 'SJC'])
    expect(m.HAS_AIRPORTS).toBe(true)
    expect([...m.LOG_ONLY_KINDS]).toEqual([])
    expect([...m.ENDGAME_ELIMINATES_KINDS]).toEqual([])
  })

  it('SF Muni: no in-play airport → airports log-only; county/city endgame-only (line kept)', async () => {
    const m = await loadFor('sfmuni')
    // All three airports are outside San Francisco → the rule "outside the play
    // area = doesn't exist" leaves the SF map with none, so airport questions
    // are useless in every phase.
    expect(Object.keys(m.AIRPORTS)).toEqual([])
    expect(m.HAS_AIRPORTS).toBe(false)
    expect([...m.LOG_ONLY_KINDS].sort()).toEqual(['match-airport', 'measure-airport'])
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
    expect(await airportBlurb('bayarea')).toContain('(SFO/OAK/SJC)')
    expect(await airportBlurb('la')).toContain('(LAX/LGB)')
    // No airport in play → the question is log-only anyway, and the blurb must
    // not name airports the seeker can't reach.
    expect(await airportBlurb('sfmuni')).toBe(
      'Is your nearest commercial airport the same as mine?',
    )
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
