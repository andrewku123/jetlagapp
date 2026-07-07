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
})
