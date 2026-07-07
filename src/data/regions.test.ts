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
  })

  it('SF Muni has no in-play airport, so airport/county/city are log-only (line kept)', async () => {
    const m = await loadFor('sfmuni')
    // All three airports are outside San Francisco → the rule "outside the play
    // area = doesn't exist" leaves the SF map with none.
    expect(Object.keys(m.AIRPORTS)).toEqual([])
    expect(m.HAS_AIRPORTS).toBe(false)
    expect([...m.LOG_ONLY_KINDS].sort()).toEqual([
      'match-airport',
      'match-city',
      'match-county',
      'measure-airport',
    ])
    // 7 Muni lines still discriminate, so line Matching keeps eliminating.
    expect(m.LOG_ONLY_KINDS.has('match-line')).toBe(false)
  })
})
