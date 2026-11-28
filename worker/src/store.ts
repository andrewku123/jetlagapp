import type { Env, PackedTrip } from './feeds'
import { addDays, pacific, pacificToMs } from './time'
import { gunzip } from './util'

export const RETENTION_DAYS = 30
// D1's free plan caps a database at 500 MB; past this, the oldest days that
// aren't kept or used by a round go first, even inside RETENTION_DAYS.
export const MAX_SNAPSHOT_BYTES = 400 * 1024 * 1024

interface Row {
  fetched_at: number
  feed_ts: number | null
  kind: 'full' | 'diff'
  data: ArrayBuffer | number[]
}

interface RowData {
  ts: number
  trips: PackedTrip[]
  gone?: string[]
}

async function decodeRow(r: Row): Promise<RowData> {
  return JSON.parse(await gunzip(r.data))
}

function expand(t: PackedTrip) {
  return {
    id: t[0],
    route: t[1],
    date: t[2],
    start: t[3],
    ...(t[4] ? { rel: t[4] } : {}),
    stops: t[5].map((s) => ({
      stop: s[0],
      arr: s[1],
      dep: s[2],
      delay: s[3],
      ...(s[4] ? { skipped: true } : {}),
    })),
  }
}

export async function dayIndex(env: Env, source: string, day: string) {
  const feeds = await env.DB.prepare(
    `SELECT feed, COUNT(*) AS polls, SUM(kind = 'full') AS fulls, MIN(fetched_at) AS first, MAX(fetched_at) AS last,
            SUM(bytes) AS bytes, MAX(trips) AS maxTrips
       FROM snapshots WHERE source = ? AND day = ? GROUP BY feed`,
  )
    .bind(source, day)
    .all()
  const kept = await env.DB.prepare('SELECT kept FROM days WHERE source = ? AND day = ?').bind(source, day).first<number>('kept')
  const rounds = await roundDays(env)
  return {
    source,
    day,
    kept: kept === 1,
    hasRound: rounds.has(day),
    expiresAfter: kept === 1 || rounds.has(day) ? null : addDays(day, RETENTION_DAYS),
    feeds: feeds.results,
  }
}

// at: unix ms or Pacific "HH:MM" on `day`.
export function parseAt(day: string, at: string | null): number | null {
  if (!at) return null
  if (/^\d{1,2}:\d{2}$/.test(at)) return pacificToMs(day, at)
  const n = Number(at)
  return Number.isFinite(n) ? n : null
}

// The latest snapshot fetched at or before `at`, rebuilt from its full row and
// the diffs after it. This is what the seekers' apps could have shown at `at`.
export async function snapshotAt(env: Env, source: string, day: string, feed: string, at: number) {
  const full = await env.DB.prepare(
    `SELECT fetched_at FROM snapshots WHERE source = ? AND day = ? AND feed = ? AND kind = 'full' AND fetched_at <= ?
      ORDER BY fetched_at DESC LIMIT 1`,
  )
    .bind(source, day, feed, at)
    .first<number>('fetched_at')
  if (full === null) return null
  const rows = await env.DB.prepare(
    `SELECT fetched_at, feed_ts, kind, data FROM snapshots
      WHERE source = ? AND day = ? AND feed = ? AND fetched_at >= ? AND fetched_at <= ? ORDER BY fetched_at`,
  )
    .bind(source, day, feed, full, at)
    .all<Row>()
  const trips = new Map<string, PackedTrip>()
  let last: Row | null = null
  let ts = 0
  for (const r of rows.results) {
    const d = await decodeRow(r)
    if (r.kind === 'full') trips.clear()
    for (const id of d.gone ?? []) trips.delete(id)
    for (const t of d.trips) trips.set(t[0], t)
    last = r
    ts = d.ts
  }
  return {
    source,
    day,
    feed,
    at,
    fetchedAt: last?.fetched_at ?? full,
    feedTs: ts,
    trips: [...trips.values()].map(expand),
  }
}

const MAX_RANGE_MS = 2 * 3600_000

// Raw rows between from and to (at most 2 hours), oldest first.
export async function rowsBetween(env: Env, source: string, day: string, feed: string, from: number, to: number) {
  if (to - from > MAX_RANGE_MS) to = from + MAX_RANGE_MS
  const rows = await env.DB.prepare(
    `SELECT fetched_at, feed_ts, kind, data FROM snapshots
      WHERE source = ? AND day = ? AND feed = ? AND fetched_at >= ? AND fetched_at <= ? ORDER BY fetched_at`,
  )
    .bind(source, day, feed, from, to)
    .all<Row>()
  const out = []
  for (const r of rows.results) {
    const d = await decodeRow(r)
    out.push({ fetchedAt: r.fetched_at, kind: r.kind, feedTs: d.ts, trips: d.trips.map(expand), gone: d.gone ?? [] })
  }
  return { source, day, feed, from, to, rows: out }
}

export async function setKept(env: Env, source: string, day: string, kept: boolean) {
  await env.DB.prepare(
    'INSERT INTO days (source, day, kept) VALUES (?, ?, ?) ON CONFLICT (source, day) DO UPDATE SET kept = excluded.kept',
  )
    .bind(source, day, kept ? 1 : 0)
    .run()
}

async function roundDays(env: Env): Promise<Set<string>> {
  const rows = await env.DB.prepare('SELECT days FROM rounds').all<{ days: string }>()
  const set = new Set<string>()
  for (const r of rows.results) for (const d of JSON.parse(r.days) as string[]) set.add(d)
  return set
}

// Drops recordings older than RETENTION_DAYS unless the day is kept or a saved
// round touches it.
export async function cleanup(env: Env, now = Date.now()) {
  const cutoff = addDays(pacific(now).day, -RETENTION_DAYS)
  const rounds = await roundDays(env)
  const old = await env.DB.prepare('SELECT source, day FROM days WHERE day < ? AND kept = 0')
    .bind(cutoff)
    .all<{ source: string; day: string }>()
  const deleted: string[] = []
  for (const { source, day } of old.results) {
    if (rounds.has(day)) continue
    await env.DB.batch([
      env.DB.prepare('DELETE FROM snapshots WHERE source = ? AND day = ?').bind(source, day),
      env.DB.prepare('DELETE FROM days WHERE source = ? AND day = ?').bind(source, day),
    ])
    deleted.push(day)
  }
  const today = pacific(now).day
  const sizes = await env.DB.prepare(
    `SELECT s.source, s.day, SUM(s.bytes) AS bytes, d.kept FROM snapshots s
       LEFT JOIN days d ON d.source = s.source AND d.day = s.day GROUP BY s.source, s.day ORDER BY s.day`,
  ).all<{ source: string; day: string; bytes: number; kept: number | null }>()
  let total = sizes.results.reduce((a, r) => a + r.bytes, 0)
  for (const r of sizes.results) {
    if (total <= MAX_SNAPSHOT_BYTES) break
    if (r.kept === 1 || rounds.has(r.day) || r.day === today) continue
    await env.DB.batch([
      env.DB.prepare('DELETE FROM snapshots WHERE source = ? AND day = ?').bind(r.source, r.day),
      env.DB.prepare('DELETE FROM days WHERE source = ? AND day = ?').bind(r.source, r.day),
    ])
    total -= r.bytes
    deleted.push(r.day)
  }
  return deleted
}
