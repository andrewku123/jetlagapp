import type { GameState } from '../types'
import { ACTIVE_REGION_ID } from '../data/regions'
import { BUILD_ID } from './version'

// Rounds saved for the postgame review. Reset saves the board here before
// clearing it, and each saved round waits in an upload queue until the shared
// review backend (VITE_REVIEW_API_URL) accepts it.
export interface SavedRound {
  id: string
  region: string
  build: string
  savedAt: number
  game: GameState
}

const ROUNDS_KEY = `bahs.review.v1.${ACTIVE_REGION_ID}`
const QUEUE_KEY = `bahs.review.queue.v1.${ACTIVE_REGION_ID}`
export const REVIEW_API_URL: string = import.meta.env.VITE_REVIEW_API_URL ?? ''

function read<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key)
    return raw ? (JSON.parse(raw) as T) : fallback
  } catch {
    return fallback
  }
}

function write(key: string, value: unknown): void {
  try {
    localStorage.setItem(key, JSON.stringify(value))
  } catch {
    // ignore quota / serialization errors
  }
}

export function isEmptyBoard(g: GameState): boolean {
  return (
    g.questions.length === 0 &&
    g.manualEliminated.length === 0 &&
    g.eliminationLog.length === 0 &&
    g.starred.length === 0 &&
    Object.keys(g.notes).length === 0 &&
    g.annotations.length === 0 &&
    g.endgame === null
  )
}

export function loadSavedRounds(): SavedRound[] {
  const rounds = read<SavedRound[]>(ROUNDS_KEY, [])
  return Array.isArray(rounds) ? rounds : []
}

export function pendingUploads(): string[] {
  const ids = read<string[]>(QUEUE_KEY, [])
  return Array.isArray(ids) ? ids : []
}

// Saves a non-empty board as a round and queues it for upload. Returns null for
// an empty board, which isn't worth reviewing.
export function saveRound(game: GameState, now: number = Date.now()): SavedRound | null {
  if (isEmptyBoard(game)) return null
  const round: SavedRound = {
    id: `${ACTIVE_REGION_ID}-${now}-${Math.random().toString(36).slice(2, 8)}`,
    region: ACTIVE_REGION_ID,
    build: BUILD_ID,
    savedAt: now,
    game,
  }
  write(ROUNDS_KEY, [...loadSavedRounds(), round])
  write(QUEUE_KEY, [...pendingUploads(), round.id])
  return round
}

// Uploads queued rounds in order, stopping at the first failure (e.g. offline)
// so the rest retry next time. Returns how many were uploaded.
export async function flushUploads(
  apiUrl: string = REVIEW_API_URL,
  fetchFn: typeof fetch = (...args) => fetch(...args),
): Promise<number> {
  if (!apiUrl) return 0
  const queue = pendingUploads()
  if (queue.length === 0) return 0
  const byId = new Map(loadSavedRounds().map((r) => [r.id, r]))
  let sent = 0
  let i = 0
  for (; i < queue.length; i++) {
    const round = byId.get(queue[i])
    if (!round) continue
    try {
      const res = await fetchFn(`${apiUrl.replace(/\/$/, '')}/rounds`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(round),
      })
      if (!res.ok) break
      sent++
    } catch {
      break
    }
  }
  write(QUEUE_KEY, queue.slice(i))
  return sent
}
