import { describe, expect, it } from 'vitest'
import { shouldReload } from './version'

describe('stale-bundle reload decision', () => {
  it('stays put when the served build is the running one', () => {
    expect(shouldReload('abc123', 'abc123', null)).toBe(false)
  })

  it('reloads once when the server has moved on', () => {
    expect(shouldReload('abc123', 'def456', null)).toBe(true)
  })

  it('never reloads twice for the same build, so a stubborn cache cannot loop', () => {
    expect(shouldReload('abc123', 'def456', 'def456')).toBe(false)
  })

  it('reloads again once a newer build appears after a failed attempt', () => {
    expect(shouldReload('abc123', 'ghi789', 'def456')).toBe(true)
  })

  it('leaves the page alone when version.json is unreachable (offline mid-game)', () => {
    expect(shouldReload('abc123', null, null)).toBe(false)
  })
})
