import type { GameState } from '../types'

const KEY = 'bahs.game.v1'

export const emptyGame: GameState = {
  dayType: 'wd',
  hourlyOnly: true,
  questions: [],
  manualEliminated: [],
  starred: [],
  notes: {},
}

export function loadGame(): GameState {
  try {
    const raw = localStorage.getItem(KEY)
    if (!raw) return { ...emptyGame }
    const parsed = JSON.parse(raw) as Partial<GameState>
    return { ...emptyGame, ...parsed }
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
