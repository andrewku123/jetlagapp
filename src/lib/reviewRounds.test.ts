import { beforeEach, describe, expect, it } from 'vitest'
import { emptyGame } from './storage'
import {
  exportRound,
  fetchRemoteRounds,
  flushUploads,
  importRound,
  isEmptyBoard,
  loadLocalSetups,
  loadSavedRounds,
  mergeRounds,
  pendingUploads,
  saveRound,
  saveSetup,
} from './reviewRounds'
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

describe('review page rounds', () => {
  beforeEach(() => store.clear())

  it('exports and imports a round, queueing it for upload once', () => {
    const r = saveRound(played, 1000)!
    const text = exportRound(r)
    store.clear()
    const back = importRound(text)
    expect(back).toEqual(r)
    importRound(text)
    expect(loadSavedRounds()).toHaveLength(1)
    expect(pendingUploads()).toEqual([r.id])
  })

  it('rejects a file from another map or not a round', () => {
    const r = saveRound(played, 1000)!
    expect(importRound(exportRound({ ...r, region: 'elsewhere' }))).toMatch(/another map/)
    expect(importRound('nope')).toMatch(/isn't a saved round/)
  })

  it('merges phone and server copies into one entry, newest first', () => {
    const a = saveRound(played, 1000)!
    const b = saveRound(played, 2000)!
    const merged = mergeRounds([a, b], [{ ...a, review: { cutoffMin: 50 }, remote: true }], {})
    expect(merged.map((r) => [r.id, r.remote])).toEqual([
      [b.id, false],
      [a.id, true],
    ])
    expect(merged[1].review).toEqual({ cutoffMin: 50 })
    expect(mergeRounds([a], [{ ...a, review: null, remote: true }], { [a.id]: { cutoffMin: 9 } })[0].review).toEqual({
      cutoffMin: 9,
    })
  })

  it('fetches full rounds with the group password', async () => {
    let seen: [string, RequestInit | undefined] | null = null
    const f = ((url: string, init?: RequestInit) => {
      seen = [url, init]
      return Promise.resolve(new Response(JSON.stringify({ rounds: [{ id: 'r1', savedAt: 1, game: played, review: null }] })))
    }) as typeof fetch
    const rounds = await fetchRemoteRounds('https://x.test/', f, 'pw')
    expect(rounds[0]).toMatchObject({ id: 'r1', remote: true })
    expect(seen![0]).toMatch(/^https:\/\/x\.test\/rounds\?region=.+&full=1$/)
    expect((seen![1]!.headers as Record<string, string>)['X-Group-Password']).toBe('pw')
  })

  it('keeps setup on the phone when the server is unreachable', async () => {
    const r = { ...saveRound(played, 1000)!, review: null, remote: true }
    const down = (() => Promise.reject(new Error('offline'))) as typeof fetch
    expect(await saveSetup(r, { cutoffMin: 40 }, 'https://x.test', down, 'pw')).toBe(false)
    expect(loadLocalSetups()[r.id]).toEqual({ cutoffMin: 40 })
    expect(await saveSetup(r, { cutoffMin: 41 }, 'https://x.test', ok, 'pw')).toBe(true)
    expect(loadLocalSetups()[r.id]).toBeUndefined()
  })
})
