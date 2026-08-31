import type { GameState } from '../types'
import { ACTIVE_REGION_ID, MAP_SIZE } from '../data/regions'
import { normalizeCurses, NO_CURSES } from './hidingZone'

// Each map keeps its own saved board, so switching maps never mixes state.
const KEY = `bahs.game.v1.${ACTIVE_REGION_ID}`

export const emptyGame: GameState = {
  dayType: 'wd',
  gameSize: MAP_SIZE,
  units: 'imperial',
  questions: [],
  manualEliminated: [],
  starred: [],
  notes: {},
  annotations: [],
  endgame: null,
  zoneCurses: { ...NO_CURSES },
}

export function loadGame(): GameState {
  try {
    const raw = localStorage.getItem(KEY)
    if (!raw) return { ...emptyGame }
    const parsed = JSON.parse(raw) as Partial<GameState>
    // gameSize always tracks the current map, never a stale stored value.
    return {
      ...emptyGame,
      ...parsed,
      gameSize: emptyGame.gameSize,
      zoneCurses: normalizeCurses(parsed.zoneCurses),
    }
  } catch {
    return { ...emptyGame }
  }
}

export function saveGame(state: GameState): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(state))
  } catch {
    // ignore quota / serialization errors
  }
}
