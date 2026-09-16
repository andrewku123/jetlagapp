import type { GameSize } from '../data/questionSets'
import { SIZE_PARAMS } from '../data/questionSets'
import type { ZoneCurses } from '../types'

export const NO_CURSES: ZoneCurses = { prosperous: 0, tiny: 0 }

// Curse of the Prosperous Home grows the hiding zone, Curse of the Tiny Home
// shrinks it. They compound: each card acts on the zone as it stands when the
// curse is cast, so two Prosperous Homes give x1.5 x 1.5 = x2.25, not x2.
const PROSPEROUS_FACTOR = 1.5
const TINY_FACTOR = 0.5
// zone sizes past these are either off the map or smaller than the GPS error
// the game is played with; also keeps the map fit from degenerating
const MAX_MULTIPLIER = 64
const MIN_MULTIPLIER = 1 / 64

export function curseMultiplier(curses: ZoneCurses): number {
  const n = clampCount(curses.prosperous)
  const t = clampCount(curses.tiny)
  const raw = PROSPEROUS_FACTOR ** n * TINY_FACTOR ** t
  return Math.min(MAX_MULTIPLIER, Math.max(MIN_MULTIPLIER, raw))
}

export function defaultHidingRadiusMi(size: GameSize): number {
  return SIZE_PARAMS[size].hidingZoneRadiusMi
}

// The zone radius every consumer should use: the map's default for the game
// size, resized by whatever curses are in play.
export function hidingRadiusMi(size: GameSize, curses: ZoneCurses = NO_CURSES): number {
  return defaultHidingRadiusMi(size) * curseMultiplier(curses)
}

// A cast that would push the multiplier past its bounds is refused rather than
// silently clamped, so the counter can't drift out of sync with the zone.
export function castCurse(curses: ZoneCurses, card: keyof ZoneCurses): ZoneCurses {
  const next = { ...normalizeCurses(curses), [card]: clampCount(curses[card]) + 1 }
  const raw = PROSPEROUS_FACTOR ** next.prosperous * TINY_FACTOR ** next.tiny
  if (raw > MAX_MULTIPLIER || raw < MIN_MULTIPLIER) return normalizeCurses(curses)
  return next
}

// Older saved games have no zoneCurses at all, and a hand-edited board code
// could carry junk; both must land on a sane object.
export function normalizeCurses(curses: Partial<ZoneCurses> | null | undefined): ZoneCurses {
  return {
    prosperous: clampCount(curses?.prosperous),
    tiny: clampCount(curses?.tiny),
  }
}

function clampCount(n: unknown): number {
  return typeof n === 'number' && Number.isFinite(n) && n > 0 ? Math.floor(n) : 0
}
