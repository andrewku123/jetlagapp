import { describe, it, expect } from 'vitest'
import rawStations from '../data/stations.json'
import type { Station } from '../types'
import { encodeElimination, decodeElimination } from './shareCode'

const STATIONS = rawStations as unknown as Station[]
const IDS = STATIONS.map((s) => s.id)

describe('board share code', () => {
  it('round-trips an arbitrary eliminated set', () => {
    const picked = IDS.filter((_, i) => i % 3 === 0)
    const code = encodeElimination(picked)
    const res = decodeElimination(code)
    expect(res.ok).toBe(true)
    if (res.ok) expect(new Set(res.ids)).toEqual(new Set(picked))
  })

  it('round-trips the empty set and the full set', () => {
    for (const picked of [[], IDS]) {
      const res = decodeElimination(encodeElimination(picked))
      expect(res.ok).toBe(true)
      if (res.ok) expect(new Set(res.ids)).toEqual(new Set(picked))
    }
  })

  it('ignores unknown ids on encode', () => {
    const res = decodeElimination(encodeElimination(['not-a-real-id', IDS[0]]))
    expect(res.ok).toBe(true)
    if (res.ok) expect(res.ids).toEqual([IDS[0]])
  })

  it('rejects malformed codes', () => {
    for (const bad of ['', 'hello', 'E1.foo', 'E2.' + (0).toString(36) + '.AAAA']) {
      expect(decodeElimination(bad).ok).toBe(false)
    }
  })

  it('rejects a code from a different station count', () => {
    const code = encodeElimination([IDS[0]])
    const wrong = code.replace(/^E1\.[^.]+\./, `E1.${(IDS.length + 1).toString(36)}.`)
    const res = decodeElimination(wrong)
    expect(res.ok).toBe(false)
  })

  it('produces a reasonably short code', () => {
    // ~1 bit per station → base64 length ≈ stations * 1/6, well under 100 chars
    const code = encodeElimination(IDS.filter((_, i) => i % 2 === 0))
    expect(code.length).toBeLessThan(IDS.length)
  })
})
