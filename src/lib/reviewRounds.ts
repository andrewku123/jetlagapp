import type { GameState } from '../types'
import { ACTIVE_REGION_ID } from '../data/regions'
import { BUILD_ID } from './version'
import { groupPassword } from './gate'

// Rounds saved for the postgame review. Reset saves the board here before
// clearing it, and each saved round waits in an upload queue until the shared
// review backend (the jetlag-recorder Worker, POST /rounds) accepts it.
export interface SavedRound {
  id: string
  region: string
  build: string
  savedAt: number
  game: GameState
  // imported from a file: stays on this phone, never uploaded or shared
  phoneOnly?: boolean
}

const ROUNDS_KEY = `bahs.review.v1.${ACTIVE_REGION_ID}`
const QUEUE_KEY = `bahs.review.queue.v1.${ACTIVE_REGION_ID}`
export const REVIEW_API_URL: string =
  import.meta.env.VITE_REVIEW_API_URL ?? 'https://jetlag-recorder.andrew-js-ku.workers.dev'

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
  password: string = groupPassword(),
): Promise<number> {
  if (!apiUrl || !password) return 0
  const queue = pendingUploads()
  if (queue.length === 0) return 0
  const byId = new Map(loadSavedRounds().map((r) => [r.id, r]))
  let sent = 0
  let i = 0
  for (; i < queue.length; i++) {
    const round = byId.get(queue[i])
    if (!round || round.phoneOnly) continue
    try {
      const res = await fetchFn(`${apiUrl.replace(/\/$/, '')}/rounds`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Group-Password': password },
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

// --- Review page side ---

// What a reviewer fills in for a round (design §2). Saved locally and, when the
// round is on the Worker, with PUT /rounds/<id> so every phone sees the same.
export interface ReviewSetup {
  gameDate?: string // YYYY-MM-DD
  startAt?: number // unix ms, seekers released
  startStation?: string
  hiderStation?: string // hindsight only, never scoring
  cutoffMin?: number
  endgameStartAt?: number
  foundAt?: number
  excluded?: string[] // question ids unticked in cleanup
}

export interface ReviewRound extends SavedRound {
  review: ReviewSetup | null
  remote: boolean // stored on the Worker
  updatedAt?: number
}

const SETUP_KEY = `bahs.review.setup.v1.${ACTIVE_REGION_ID}`

export function loadLocalSetups(): Record<string, ReviewSetup> {
  const s = read<Record<string, ReviewSetup>>(SETUP_KEY, {})
  return s && typeof s === 'object' && !Array.isArray(s) ? s : {}
}

function apiBase(apiUrl: string): string {
  return apiUrl.replace(/\/$/, '')
}

export async function fetchRemoteRounds(
  apiUrl: string = REVIEW_API_URL,
  fetchFn: typeof fetch = (...args) => fetch(...args),
  password: string = groupPassword(),
): Promise<ReviewRound[]> {
  if (!apiUrl || !password) throw new Error('no review server')
  const res = await fetchFn(`${apiBase(apiUrl)}/rounds?region=${encodeURIComponent(ACTIVE_REGION_ID)}&full=1`, {
    headers: { 'X-Group-Password': password },
  })
  if (!res.ok) throw new Error(`server said ${res.status}`)
  const body = (await res.json()) as { rounds?: (SavedRound & { review: ReviewSetup | null; updatedAt?: number })[] }
  return (body.rounds ?? []).map((r) => ({ ...r, build: r.build ?? '', remote: true }))
}

// Local and Worker copies of the same round are one entry; the Worker's setup
// wins unless this phone has edits it hasn't sent yet.
export function mergeRounds(local: SavedRound[], remote: ReviewRound[], setups: Record<string, ReviewSetup>): ReviewRound[] {
  const byId = new Map<string, ReviewRound>()
  for (const r of local) byId.set(r.id, { ...r, review: setups[r.id] ?? null, remote: false })
  for (const r of remote) {
    const mine = byId.get(r.id)
    if (mine?.phoneOnly) continue
    byId.set(r.id, { ...r, review: setups[r.id] ?? r.review ?? mine?.review ?? null, remote: true })
  }
  return [...byId.values()].sort((a, b) => b.savedAt - a.savedAt)
}

export async function saveSetup(
  round: ReviewRound,
  setup: ReviewSetup,
  apiUrl: string = REVIEW_API_URL,
  fetchFn: typeof fetch = (...args) => fetch(...args),
  password: string = groupPassword(),
): Promise<boolean> {
  const all = loadLocalSetups()
  all[round.id] = setup
  write(SETUP_KEY, all)
  if (!round.remote || !apiUrl || !password) return false
  try {
    const res = await fetchFn(`${apiBase(apiUrl)}/rounds/${encodeURIComponent(round.id)}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', 'X-Group-Password': password },
      body: JSON.stringify({ review: setup }),
    })
    if (!res.ok) return false
    delete all[round.id]
    write(SETUP_KEY, all)
    return true
  } catch {
    return false
  }
}

export async function deleteRound(
  round: ReviewRound,
  apiUrl: string = REVIEW_API_URL,
  fetchFn: typeof fetch = (...args) => fetch(...args),
  password: string = groupPassword(),
): Promise<boolean> {
  write(ROUNDS_KEY, loadSavedRounds().filter((r) => r.id !== round.id))
  write(QUEUE_KEY, pendingUploads().filter((id) => id !== round.id))
  const setups = loadLocalSetups()
  delete setups[round.id]
  write(SETUP_KEY, setups)
  if (!round.remote) return true
  try {
    const res = await fetchFn(`${apiBase(apiUrl)}/rounds/${encodeURIComponent(round.id)}`, {
      method: 'DELETE',
      headers: { 'X-Group-Password': password },
    })
    return res.ok
  } catch {
    return false
  }
}

export function exportRound(r: SavedRound): string {
  return JSON.stringify({ v: 1, id: r.id, region: r.region, build: r.build, savedAt: r.savedAt, game: r.game })
}

// Reads an exported file back in. A file from another map is rejected, like a
// board code from another map.
export function importRound(text: string): SavedRound | string {
  let data: Partial<SavedRound> & { v?: number }
  try {
    data = JSON.parse(text)
  } catch {
    return "That file isn't a saved round."
  }
  if (!data || data.v !== 1 || typeof data.savedAt !== 'number' || !data.game || !Array.isArray(data.game.questions)) {
    return "That file isn't a saved round."
  }
  if (data.region !== ACTIVE_REGION_ID) return `That round is from another map (${data.region}).`
  const round: SavedRound = {
    id: typeof data.id === 'string' ? data.id : `${ACTIVE_REGION_ID}-${data.savedAt}-import`,
    region: ACTIVE_REGION_ID,
    build: typeof data.build === 'string' ? data.build : '',
    savedAt: data.savedAt,
    game: { ...data.game, eliminationLog: Array.isArray(data.game.eliminationLog) ? data.game.eliminationLog : [] },
    phoneOnly: true,
  }
  const rounds = loadSavedRounds()
  if (!rounds.some((r) => r.id === round.id)) write(ROUNDS_KEY, [...rounds, round])
  return round
}
