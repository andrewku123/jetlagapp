import { describe, it, expect, vi, afterEach } from 'vitest'

// resolveActiveRegion runs at module load, so each case re-imports the registry
// with a stubbed localStorage and page URL.
async function load(store: Record<string, string>, href = 'https://example.test/jetlagapp/') {
  vi.resetModules()
  vi.stubGlobal('localStorage', {
    getItem: (k: string) => store[k] ?? null,
    setItem: (k: string, v: string) => {
      store[k] = v
    },
  })
  const replaced: string[] = []
  vi.stubGlobal('window', {
    location: { href, reload: () => {} },
    history: { state: null, replaceState: (_s: unknown, _t: string, url: string) => replaced.push(url) },
  })
  const m = await import('./regions')
  return { m, store, replaced }
}

afterEach(() => {
  vi.unstubAllGlobals()
  vi.resetModules()
})

describe('first-visit map picker', () => {
  it('a first visit opens on the picker', async () => {
    const { m } = await load({})
    expect(m.NEEDS_MAP_PICK).toBe(true)
    expect(m.ACTIVE_REGION_ID).toBe('bayarea')
  })

  it('a returning player opens straight to the last map used', async () => {
    const { m } = await load({ 'bahs.region': 'la' })
    expect(m.NEEDS_MAP_PICK).toBe(false)
    expect(m.ACTIVE_REGION_ID).toBe('la')
  })

  it('a pre-picker player with a saved Bay Area board skips the picker', async () => {
    const { m, store } = await load({ 'bahs.game.v1.bayarea': '{}' })
    expect(m.NEEDS_MAP_PICK).toBe(false)
    expect(m.ACTIVE_REGION_ID).toBe('bayarea')
    expect(store['bahs.region']).toBe('bayarea')
  })

  it('a remembered map missing from this build shows the picker', async () => {
    const { m } = await load({ 'bahs.region': 'nowhere', 'bahs.game.v1.bayarea': '{}' })
    expect(m.NEEDS_MAP_PICK).toBe(true)
    expect(m.ACTIVE_REGION_ID).toBe('bayarea')
  })

  it('a link naming a map skips the picker, is remembered, and leaves the URL', async () => {
    const { m, store, replaced } = await load({}, 'https://example.test/jetlagapp/?map=sfmuni&x=1#top')
    expect(m.NEEDS_MAP_PICK).toBe(false)
    expect(m.ACTIVE_REGION_ID).toBe('sfmuni')
    expect(store['bahs.region']).toBe('sfmuni')
    expect(replaced).toEqual(['https://example.test/jetlagapp/?x=1#top'])
  })

  it('a link map overrides the last map used', async () => {
    const { m } = await load({ 'bahs.region': 'la' }, 'https://example.test/?map=dc')
    expect(m.ACTIVE_REGION_ID).toBe('dc')
  })

  it('an unknown link map falls back to the usual rules', async () => {
    const a = await load({ 'bahs.region': 'la' }, 'https://example.test/?map=nowhere')
    expect(a.m.ACTIVE_REGION_ID).toBe('la')
    expect(a.m.NEEDS_MAP_PICK).toBe(false)
    const b = await load({}, 'https://example.test/?map=nowhere')
    expect(b.m.NEEDS_MAP_PICK).toBe(true)
  })
})
