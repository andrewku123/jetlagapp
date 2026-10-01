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

describe('password gate', () => {
  beforeEach(() => store.clear())

  it('ships the hash of the current password', async () => {
    expect(await hashPassword('jetlag')).toBe(PASSWORD_HASH)
  })

  it('stays locked on a wrong password', async () => {
    expect(await tryUnlock('nope')).toBe(false)
    expect(isUnlocked()).toBe(false)
  })

  it('remembers a correct password across loads', async () => {
    expect(await tryUnlock(' jetlag ')).toBe(true)
    expect(isUnlocked()).toBe(true)
  })

  it('locks again once the password changes, without touching saved boards', async () => {
    store.set('bahs.game.v1.bayarea', '{"questions":[1]}')
    await tryUnlock('jetlag')
    const next = await hashPassword('newpass')
    expect(isUnlocked(next)).toBe(false)
    expect(store.get('bahs.game.v1.bayarea')).toBe('{"questions":[1]}')
  })
})
