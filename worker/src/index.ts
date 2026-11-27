import { REGION_SOURCES, SOURCE, type Env } from './feeds'
import { Recorder } from './recorder'
import { handleRounds } from './rounds'
import { cleanup, dayIndex, parseAt, rowsBetween, setKept, snapshotAt } from './store'
import { pacific } from './time'
import { CORS, error, json } from './util'

export { Recorder }

const SALT = 'bahs-gate:'

// The header carries the same group password the app's gate asks for; the
// Worker only stores its salted hash (src/lib/gate.ts PASSWORD_HASH format).
async function authorized(req: Request, env: Env): Promise<boolean> {
  const pw = req.headers.get('X-Group-Password')
  if (!pw || !env.GROUP_PASSWORD_HASH) return false
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(SALT + pw.trim()))
  const got = new TextEncoder().encode([...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, '0')).join(''))
  const want = new TextEncoder().encode(env.GROUP_PASSWORD_HASH.trim().toLowerCase())
  return got.byteLength === want.byteLength && crypto.subtle.timingSafeEqual(got, want)
}

function recorder(env: Env) {
  return env.RECORDER.get(env.RECORDER.idFromName(SOURCE))
}

async function status(env: Env): Promise<Response> {
  const rec = (await (await recorder(env).fetch('https://recorder/status')).json()) as Record<string, unknown>
  const today = pacific(Date.now()).day
  const idx = await dayIndex(env, SOURCE, today)
  return json({ window: '07:30-22:00 America/Los_Angeles', ...rec, today: idx })
}

const DAY_RE = /^\d{4}-\d{2}-\d{2}$/

async function route(req: Request, env: Env): Promise<Response> {
  const url = new URL(req.url)
  const parts = url.pathname.split('/').filter(Boolean)
  if (req.method === 'OPTIONS') return new Response(null, { status: 204, headers: CORS })
  if (parts.length === 0) {
    return json({
      service: 'jetlag train recorder',
      docs: 'https://github.com/andrewku123/jetlagapp/tree/main/worker#readme',
    })
  }
  if (parts[0] === 'status' && parts.length === 1 && req.method === 'GET') return status(env)

  if (!(await authorized(req, env))) return error(401, 'missing or wrong X-Group-Password')

  if (parts[0] === 'rounds' && parts.length <= 2) return handleRounds(req, env, parts[1] ? decodeURIComponent(parts[1]) : null)

  // /<region>/<date>[/<feed>|/keep]
  const source = REGION_SOURCES[parts[0]]
  if (parts.length >= 2 && DAY_RE.test(parts[1])) {
    if (!source) return error(404, `no recordings for region ${parts[0]}`)
    const day = parts[1]
    if (parts.length === 2 && req.method === 'GET') return json(await dayIndex(env, source, day))
    if (parts.length === 3 && parts[2] === 'keep' && (req.method === 'POST' || req.method === 'DELETE')) {
      await setKept(env, source, day, req.method === 'POST')
      return json(await dayIndex(env, source, day))
    }
    if (parts.length === 3 && req.method === 'GET') {
      const feed = parts[2]
      const at = parseAt(day, url.searchParams.get('at'))
      if (at !== null) {
        const snap = await snapshotAt(env, source, day, feed, at)
        return snap ? json(snap) : error(404, 'no snapshot at or before that time')
      }
      const from = parseAt(day, url.searchParams.get('from'))
      const to = parseAt(day, url.searchParams.get('to'))
      if (from === null || to === null) return error(400, 'pass ?at= or ?from=&to= (unix ms or HH:MM Pacific)')
      return json(await rowsBetween(env, source, day, feed, from, to))
    }
  }
  return error(404, 'not found')
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    try {
      return await route(req, env)
    } catch (e) {
      console.error(e)
      return error(500, String((e as Error)?.message ?? e))
    }
  },

  // Every 10 min: make sure the recorder is polling while inside the window (it
  // stops itself outside it). Once a night, drop expired recordings.
  async scheduled(event: ScheduledController, env: Env, ctx: ExecutionContext): Promise<void> {
    ctx.waitUntil(recorder(env).fetch('https://recorder/kick'))
    const { minute } = pacific(event.scheduledTime)
    if (minute >= 3 * 60 && minute < 3 * 60 + 10) ctx.waitUntil(cleanup(env, event.scheduledTime))
  },
}
