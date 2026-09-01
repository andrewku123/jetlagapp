import { describe, it, expect } from 'vitest'
import {
  NO_CURSES,
  castCurse,
  curseMultiplier,
  defaultHidingRadiusMi,
  hidingRadiusMi,
  normalizeCurses,
} from './hidingZone'

const cast = (n: number, card: 'prosperous' | 'tiny') => {
  let c = NO_CURSES
  for (let i = 0; i < n; i++) c = castCurse(c, card)
  return c
}

describe('hiding zone curses', () => {
  it('leaves the size default alone with no curses', () => {
    expect(hidingRadiusMi('medium', NO_CURSES)).toBe(0.25)
    expect(hidingRadiusMi('large', NO_CURSES)).toBe(0.5)
    expect(hidingRadiusMi('small')).toBe(defaultHidingRadiusMi('small'))
  })

  it('grows the zone 50% per Prosperous Home, compounding', () => {
    expect(hidingRadiusMi('medium', cast(1, 'prosperous'))).toBeCloseTo(0.375, 10)
    expect(hidingRadiusMi('medium', cast(2, 'prosperous'))).toBeCloseTo(0.5625, 10)
    expect(curseMultiplier(cast(3, 'prosperous'))).toBeCloseTo(3.375, 10)
  })

  it('halves the zone per Tiny Home, compounding', () => {
    expect(hidingRadiusMi('medium', cast(1, 'tiny'))).toBeCloseTo(0.125, 10)
    expect(hidingRadiusMi('medium', cast(2, 'tiny'))).toBeCloseTo(0.0625, 10)
  })

  it('cancels a Prosperous Home against a Tiny Home in any order', () => {
    const a = castCurse(castCurse(NO_CURSES, 'prosperous'), 'tiny')
    const b = castCurse(castCurse(NO_CURSES, 'tiny'), 'prosperous')
    expect(curseMultiplier(a)).toBeCloseTo(0.75, 10)
    expect(curseMultiplier(a)).toBe(curseMultiplier(b))
  })

  it('refuses a cast that would run the zone off the scale', () => {
    expect(curseMultiplier(cast(40, 'prosperous'))).toBeLessThanOrEqual(64)
    expect(curseMultiplier(cast(40, 'tiny'))).toBeGreaterThanOrEqual(1 / 64)
  })

  it('repairs saves written before curses existed, and junk values', () => {
    expect(normalizeCurses(undefined)).toEqual(NO_CURSES)
    expect(normalizeCurses({ prosperous: -3, tiny: 2.7 })).toEqual({ prosperous: 0, tiny: 2 })
    expect(normalizeCurses({ prosperous: Number.NaN } as never)).toEqual(NO_CURSES)
  })
})
