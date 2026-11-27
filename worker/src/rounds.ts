import { REGIONS, type Env } from './feeds'
import { pacific } from './time'
import { error, json } from './util'

const MAX_BODY = 1_900_000 // D1 rows top out at 2 MB
const ID_RE = /^[A-Za-z0-9._:-]{1,100}$/

interface RoundRow {
  id: string
  region: string
  build: string | null
  saved_at: number
  game: string
  review: string | null
  created_at: number
  updated_at: number
}

// Pacific dates the round's recordings come from: when it was saved, each
// question's createdAt, and the game date typed in setup.
function touchedDays(savedAt: number, game: unknown, review: unknown): string[] {
  const days = new Set<string>([pacific(savedAt).day])
  const qs = (game as { questions?: { createdAt?: unknown }[] })?.questions
  if (Array.isArray(qs)) {
    for (const q of qs) if (typeof q?.createdAt === 'number') days.add(pacific(q.createdAt).day)
  }
  const gd = (review as { gameDate?: unknown })?.gameDate
  if (typeof gd === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(gd)) days.add(gd)
  return [...days].sort()
}

function meta(r: RoundRow) {
  return {
    id: r.id,
    region: r.region,
    build: r.build,
    savedAt: r.saved_at,
    createdAt: r.created_at,
    updatedAt: r.updated_at,
  }
}

function full(r: RoundRow) {
  return { ...meta(r), game: JSON.parse(r.game), review: r.review === null ? null : JSON.parse(r.review) }
}

async function readBody(req: Request): Promise<Record<string, unknown> | Response> {
  const text = await req.text()
  if (text.length > MAX_BODY) return error(413, 'round too large')
  try {
    const body = JSON.parse(text)
    if (!body || typeof body !== 'object' || Array.isArray(body)) return error(400, 'body must be a JSON object')
    return body
  } catch {
    return error(400, 'invalid JSON')
  }
}

async function getRow(env: Env, id: string) {
  return env.DB.prepare('SELECT * FROM rounds WHERE id = ?').bind(id).first<RoundRow>()
}

export async function handleRounds(req: Request, env: Env, id: string | null): Promise<Response> {
  const url = new URL(req.url)
  if (id === null) {
    if (req.method === 'GET') {
      const region = url.searchParams.get('region')
      const withGame = url.searchParams.get('full') === '1'
      const q = region
        ? env.DB.prepare('SELECT * FROM rounds WHERE region = ? ORDER BY saved_at DESC').bind(region)
        : env.DB.prepare('SELECT * FROM rounds ORDER BY saved_at DESC')
      const rows = await q.all<RoundRow>()
      return json({ rounds: rows.results.map(withGame ? full : meta) })
    }
    if (req.method === 'POST') {
      const body = await readBody(req)
      if (body instanceof Response) return body
      const { id: rid, region, build, savedAt, game } = body
      if (typeof rid !== 'string' || !ID_RE.test(rid)) return error(400, 'id must be 1-100 chars of A-Z a-z 0-9 . _ : -')
      if (typeof region !== 'string' || !REGIONS.has(region)) return error(400, 'unknown region')
      if (typeof savedAt !== 'number' || !Number.isFinite(savedAt)) return error(400, 'savedAt must be unix ms')
      if (!game || typeof game !== 'object') return error(400, 'game must be an object')
      if (build !== undefined && build !== null && typeof build !== 'string') return error(400, 'build must be a string')
      const now = Date.now()
      const res = await env.DB.prepare(
        `INSERT OR IGNORE INTO rounds (id, region, build, saved_at, game, review, days, created_at, updated_at)
         VALUES (?, ?, ?, ?, ?, NULL, ?, ?, ?)`,
      )
        .bind(rid, region, build ?? null, savedAt, JSON.stringify(game), JSON.stringify(touchedDays(savedAt, game, null)), now, now)
        .run()
      const row = await getRow(env, rid)
      // Retried uploads are safe: an id already stored is returned unchanged.
      return json({ ...meta(row!), created: res.meta.changes > 0 }, res.meta.changes > 0 ? 201 : 200)
    }
    return error(405, 'method not allowed')
  }

  if (!ID_RE.test(id)) return error(400, 'bad id')
  const row = await getRow(env, id)
  if (!row) return error(404, 'round not found')
  if (req.method === 'GET') return json(full(row))
  if (req.method === 'DELETE') {
    await env.DB.prepare('DELETE FROM rounds WHERE id = ?').bind(id).run()
    return json({ deleted: id })
  }
  if (req.method === 'PUT') {
    const body = await readBody(req)
    if (body instanceof Response) return body
    const { game, review, ifUpdatedAt } = body
    if (ifUpdatedAt !== undefined && ifUpdatedAt !== row.updated_at) {
      return json({ error: 'round changed since you loaded it', current: meta(row) }, 409)
    }
    if (game !== undefined && (!game || typeof game !== 'object')) return error(400, 'game must be an object')
    if (game === undefined && review === undefined) return error(400, 'nothing to update: send game and/or review')
    const newGame = game === undefined ? row.game : JSON.stringify(game)
    const newReview = review === undefined ? row.review : review === null ? null : JSON.stringify(review)
    const days = touchedDays(row.saved_at, JSON.parse(newGame), newReview === null ? null : JSON.parse(newReview))
    const now = Math.max(Date.now(), row.updated_at + 1)
    await env.DB.prepare('UPDATE rounds SET game = ?, review = ?, days = ?, updated_at = ? WHERE id = ?')
      .bind(newGame, newReview, JSON.stringify(days), now, id)
      .run()
    return json(full((await getRow(env, id))!))
  }
  return error(405, 'method not allowed')
}
