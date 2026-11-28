import { beforeEach, describe, expect, it } from 'vitest'
import { emptyGame } from './storage'
import { flushUploads, isEmptyBoard, loadSavedRounds, pendingUploads, saveRound } from './reviewRounds'
import type { GameState } from '../types'

const store = new Map<string, string>()
Object.defineProperty(globalThis, 'localStorage', {
  value: {
    getItem: (k: string) => store.get(k) ?? null,
    setItem: (k: string, v: string) => void store.set(k, v),
    removeItem: (k: string) => void store.delete(k),
  },
  configurable: true,
})

const played: GameState = { ...emptyGame, manualEliminated: ['x'], eliminationLog: [{ stationId: 'x', outAt: 5 }] }
const ok = (() => Promise.resolve(new Response('{}', { status: 200 }))) as typeof fetch

describe('saved review rounds', () => {
  beforeEach(() => store.clear())

  it('skips an empty board', () => {
    expect(isEmptyBoard(emptyGame)).toBe(true)
    expect(saveRound(emptyGame)).toBeNull()
    expect(loadSavedRounds()).toEqual([])
  })

  it('saves a played board and queues it for upload', () => {
    const r = saveRound(played, 1000)!
    expect(r.savedAt).toBe(1000)
    expect(loadSavedRounds()).toEqual([r])
    expect(pendingUploads()).toEqual([r.id])
  })

  it('keeps the queue when no backend is configured', async () => {
    saveRound(played)
    expect(await flushUploads('', ok, 'pw')).toBe(0)
    expect(pendingUploads()).toHaveLength(1)
  })

  it('keeps the queue when no group password is stored', async () => {
    saveRound(played)
    expect(await flushUploads('https://api.example', ok, '')).toBe(0)
    expect(pendingUploads()).toHaveLength(1)
  })

  it('uploads queued rounds and clears them from the queue', async () => {
    const a = saveRound(played, 1)!
    const b = saveRound(played, 2)!
    const posted: string[] = []
    const fetchFn = ((url: string, init: RequestInit) => {
      posted.push(`${url} ${JSON.parse(init.body as string).id} ${(init.headers as Record<string, string>)['X-Group-Password']}`)
      return Promise.resolve(new Response('{}', { status: 200 }))
    }) as unknown as typeof fetch
    expect(await flushUploads('https://api.example/', fetchFn, 'pw')).toBe(2)
    expect(posted).toEqual([`https://api.example/rounds ${a.id} pw`, `https://api.example/rounds ${b.id} pw`])
    expect(pendingUploads()).toEqual([])
  })

  it('stops at the first failure so the rest retry later', async () => {
    saveRound(played, 1)
    const b = saveRound(played, 2)!
    let calls = 0
    const fetchFn = (() => {
      calls++
      return calls === 1 ? Promise.resolve(new Response('{}', { status: 200 })) : Promise.reject(new Error('offline'))
    }) as typeof fetch
    expect(await flushUploads('https://api.example', fetchFn, 'pw')).toBe(1)
    expect(pendingUploads()).toEqual([b.id])
  })
})
