import { describe, it, expect } from 'vitest'
import { scaleCards, rewardForKind } from './questions'

describe('scaleCards — veto reward scaling', () => {
  it('leaves the reward unchanged for the 1st veto (×1)', () => {
    expect(scaleCards('draw 2, keep 1', 1)).toBe('draw 2, keep 1')
    expect(scaleCards('draw 2, keep 1', 0)).toBe('draw 2, keep 1')
  })
  it('multiplies both draw and keep by n', () => {
    expect(scaleCards('draw 2, keep 1', 2)).toBe('draw 4, keep 2')
    expect(scaleCards('draw 3, keep 1', 3)).toBe('draw 9, keep 3')
  })
})

describe('rewardForKind', () => {
  it('returns the base reward, scaled by the veto multiplier', () => {
    expect(rewardForKind('radar')).toBe('draw 2, keep 1')
    expect(rewardForKind('match-county', 2)).toBe('draw 6, keep 2')
  })
})
