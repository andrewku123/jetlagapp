import type { GameState } from '../types'
import { sizeForStationCount } from '../data/questionSets'
import rawStations from '../data/stations.json'

const KEY = 'bahs.game.v1'

// Size is derived from the map itself, not chosen by a person.
const DEFAULT_SIZE = sizeForStationCount((rawStations as unknown[]).length)

export const emptyGame: GameState = {
  dayType: 'wd',
  gameSize: DEFAULT_SIZE,
  units: 'imperial',
  questions: [],
  manualEliminated: [],
  starred: [],
  notes: {},
  annotations: [],
  endgame: null,
}

export function loadGame(): GameState {
  try {
    const raw = localStorage.getItem(KEY)
    if (!raw) return { ...emptyGame }
    const parsed = JSON.parse(raw) as Partial<GameState>
    // gameSize always tracks the current map, never a stale stored value.
    return { ...emptyGame, ...parsed, gameSize: emptyGame.gameSize }
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
