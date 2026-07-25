// Shareable "board code": a compact, copy-pasteable string encoding exactly which
// stations are eliminated, so a co-seeker on another device can load the same
// board state. It is a bitmask over ALL stations (sorted by id) — one bit per
// station, set when that station is eliminated — base64url-packed with a version
// tag, a map fingerprint, and the station count so a code from a different map
// (e.g. an LA board loaded on the SF map) or dataset is rejected rather than
// silently mis-applied.
import { stationsData, MAP_NAME } from '../data/regions'
import type { Station } from '../types'

const STATIONS = stationsData as unknown as Station[]

// The canonical bit order: every station id, sorted, so both ends agree on which
// bit means which station regardless of file order.
const ALL_IDS: string[] = STATIONS.map((s) => s.id).sort()

// Human-readable name of the current map, shown in the UI so it's clear which map
// a board code belongs to. Comes from the active region.
export { MAP_NAME }

// A short, stable fingerprint of the station set (FNV-1a over the sorted ids), so
// two different maps get different codes even if their station *counts* collide.
// Auto-derived from the data — no per-city bookkeeping needed.
function fnv1a(str: string): number {
  let h = 0x811c9dc5
  for (let i = 0; i < str.length; i++) {
    h ^= str.charCodeAt(i)
    h = Math.imul(h, 0x01000193)
  }
  return h >>> 0
}
const MAP_FP = fnv1a(ALL_IDS.join(',')).toString(36)

const VERSION = 'E2'
const B64 = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_'

function bytesToBase64url(bytes: Uint8Array): string {
  let out = ''
  for (let i = 0; i < bytes.length; i += 3) {
    const b0 = bytes[i]
    const b1 = i + 1 < bytes.length ? bytes[i + 1] : 0
    const b2 = i + 2 < bytes.length ? bytes[i + 2] : 0
    out += B64[b0 >> 2]
    out += B64[((b0 & 0x03) << 4) | (b1 >> 4)]
    if (i + 1 < bytes.length) out += B64[((b1 & 0x0f) << 2) | (b2 >> 6)]
    if (i + 2 < bytes.length) out += B64[b2 & 0x3f]
  }
  return out
}

function base64urlToBytes(str: string): Uint8Array | null {
  const clean = str.trim()
  const out: number[] = []
  let buf = 0
  let bits = 0
  for (const ch of clean) {
    const v = B64.indexOf(ch)
    if (v < 0) return null
    buf = (buf << 6) | v
    bits += 6
    if (bits >= 8) {
      bits -= 8
      out.push((buf >> bits) & 0xff)
    }
  }
  return new Uint8Array(out)
}

// Encode the eliminated set into a board code. Unknown ids are ignored.
export function encodeElimination(eliminatedIds: Iterable<string>): string {
  const set = new Set(eliminatedIds)
  const bytes = new Uint8Array(Math.ceil(ALL_IDS.length / 8))
  ALL_IDS.forEach((id, i) => {
    if (set.has(id)) bytes[i >> 3] |= 0x80 >> (i & 7)
  })
  return `${VERSION}.${MAP_FP}.${ALL_IDS.length.toString(36)}.${bytesToBase64url(bytes)}`
}

export type DecodeResult = { ok: true; ids: string[] } | { ok: false; error: string }

// Decode a board code back into the list of eliminated station ids. Rejects codes
// from a different map (fingerprint mismatch), a different station dataset (count
// mismatch), or malformed input.
export function decodeElimination(code: string): DecodeResult {
  const parts = code.trim().split('.')
  if (parts.length !== 4 || parts[0] !== VERSION)
    return { ok: false, error: 'Not a valid board code.' }
  if (parts[1] !== MAP_FP)
    return { ok: false, error: `This code is for a different map (this is the ${MAP_NAME} map).` }
  const count = parseInt(parts[2], 36)
  if (!Number.isFinite(count))
    return { ok: false, error: 'Not a valid board code.' }
  if (count !== ALL_IDS.length)
    return { ok: false, error: 'This code is from a different station dataset.' }
  const bytes = base64urlToBytes(parts[3])
  if (!bytes || bytes.length < Math.ceil(ALL_IDS.length / 8))
    return { ok: false, error: 'Board code looks corrupted.' }
  const ids: string[] = []
  ALL_IDS.forEach((id, i) => {
    if (bytes[i >> 3] & (0x80 >> (i & 7))) ids.push(id)
  })
  return { ok: true, ids }
}
