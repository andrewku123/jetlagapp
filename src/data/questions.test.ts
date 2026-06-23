import { describe, it, expect } from 'vitest'
import { scaleCards, rewardForKind, questionGroupKey } from './questions'

describe('scaleCards — repeat-question reward scaling', () => {
  it('leaves the reward unchanged for the 1st ask (×1)', () => {
    expect(scaleCards('draw 2, keep 1', 1)).toBe('draw 2, keep 1')
    expect(scaleCards('draw 2, keep 1', 0)).toBe('draw 2, keep 1')
  })
  it('multiplies both draw and keep by n', () => {
    expect(scaleCards('draw 2, keep 1', 2)).toBe('draw 4, keep 2')
    expect(scaleCards('draw 3, keep 1', 3)).toBe('draw 9, keep 3')
  })
})

describe('questionGroupKey — thermometer keys on the chosen thermometer', () => {
  it('groups by the explicitly chosen thermometer distance', () => {
    const a = questionGroupKey('thermometer', { thermometerMiles: 0.5, fromLat: 37.8, fromLon: -122.3, toLat: 37.9, toLon: -122.2 })
    const b = questionGroupKey('thermometer', { thermometerMiles: 0.5, fromLat: 37.7, fromLon: -122.4, toLat: 37.6, toLon: -122.5 })
    const c = questionGroupKey('thermometer', { thermometerMiles: 3, fromLat: 37.8, fromLon: -122.3, toLat: 37.9, toLon: -122.2 })
    expect(a).toBe(b) // same chosen thermometer = same question
    expect(a).not.toBe(c) // different thermometer = different question
  })
  it('falls back to inferring from A→B travel when no thermometer chosen', () => {
    const k = questionGroupKey('thermometer', { fromLat: 37.8, fromLon: -122.3, toLat: 37.805, toLon: -122.3 })
    expect(k).toBe('thermometer:0.5')
  })
})

describe('rewardForKind', () => {
  it('returns the base reward, scaled by the ask multiplier', () => {
    expect(rewardForKind('radar')).toBe('draw 2, keep 1')
    expect(rewardForKind('radar', 2)).toBe('draw 4, keep 2')
    expect(rewardForKind('match-county', 3)).toBe('draw 9, keep 3')
  })
})
