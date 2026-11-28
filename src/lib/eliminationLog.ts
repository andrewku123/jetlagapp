import type { EliminationMark } from '../types'

// Records the hand cross-outs and restores between two manualEliminated lists:
// a newly crossed-out station opens a mark, a restored one closes its open mark.
export function logManualChange(
  log: EliminationMark[],
  before: string[],
  after: string[],
  now: number,
): EliminationMark[] {
  const was = new Set(before)
  const is = new Set(after)
  const next = [...log]
  for (const id of is) if (!was.has(id)) next.push({ stationId: id, outAt: now })
  for (const id of was) {
    if (is.has(id)) continue
    for (let i = next.length - 1; i >= 0; i--) {
      if (next[i].stationId === id && next[i].backAt === undefined) {
        next[i] = { ...next[i], backAt: now }
        break
      }
    }
  }
  return next
}
