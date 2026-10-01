import { beforeEach, describe, expect, it } from 'vitest'
import { hashPassword, isUnlocked, PASSWORD_HASH, tryUnlock } from './gate'

const store = new Map<string, string>()
Object.defineProperty(globalThis, 'localStorage', {
  value: {
    getItem: (k: string) => store.get(k) ?? null,
    setItem: (k: string, v: string) => void store.set(k, v),
    removeItem: (k: string) => void store.delete(k),
  },
  configurable: true,
})

// node scripts/gate_hash.mjs fixture-pw
const FIXTURE = 'f5d3ec6c4019d26870029be40d2030932c64f66e948f402d63ca98fd3159347a'

describe('password gate', () => {
  beforeEach(() => store.clear())

  it('hashes exactly like scripts/gate_hash.mjs, so a rotated hash can be pasted in', async () => {
    expect(await hashPassword('fixture-pw')).toBe(FIXTURE)
    expect(PASSWORD_HASH).toMatch(/^[0-9a-f]{64}$/)
  })

  it('stays locked on a wrong password', async () => {
    expect(await tryUnlock('nope', FIXTURE)).toBe(false)
    expect(isUnlocked(FIXTURE)).toBe(false)
  })

  it('remembers a correct password across loads', async () => {
    expect(await tryUnlock(' fixture-pw ', FIXTURE)).toBe(true)
    expect(isUnlocked(FIXTURE)).toBe(true)
  })

  it('locks again once the password changes, without touching saved boards', async () => {
    store.set('bahs.game.v1.bayarea', '{"questions":[1]}')
    await tryUnlock('fixture-pw', FIXTURE)
    expect(isUnlocked(await hashPassword('newpass'))).toBe(false)
    expect(store.get('bahs.game.v1.bayarea')).toBe('{"questions":[1]}')
  })
})
