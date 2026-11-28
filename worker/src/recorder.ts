import { decodeFeed } from './gtfsrt'
import { FEEDS, SOURCE, packTrip, type Env, type FeedDef } from './feeds'
import { inWindow, pacific } from './time'
import { gzip } from './util'

const BUCKET_MS = 10 * 60_000

interface FeedStat {
  polls: number
  lastOkAt: number | null
  lastTrips: number | null
  lastBytes: number | null
  lastError: string | null
  lastErrorAt: number | null
}

const emptyStat = (): FeedStat => ({
  polls: 0,
  lastOkAt: null,
  lastTrips: null,
  lastBytes: null,
  lastError: null,
  lastErrorAt: null,
})

// One instance (named after the source) polls every feed on an alarm while the
// Pacific clock is inside 07:30-22:00 and stops outside it. A cron kicks it.
export class Recorder implements DurableObject {
  private prev = new Map<string, { bucket: number; trips: Map<string, string> }>()
  private stats: Record<string, FeedStat> | null = null

  constructor(
    private state: DurableObjectState,
    private env: Env,
  ) {}

  private async loadStats(): Promise<Record<string, FeedStat>> {
    if (!this.stats) {
      this.stats = (await this.state.storage.get<Record<string, FeedStat>>('stats')) ?? {}
      for (const f of FEEDS) this.stats[f.id] ??= emptyStat()
    }
    return this.stats
  }

  private recording(now: number): boolean {
    return this.env.ALWAYS_RECORD === '1' || inWindow(now)
  }

  async fetch(req: Request): Promise<Response> {
    const path = new URL(req.url).pathname
    if (path === '/kick') {
      const now = Date.now()
      if (this.recording(now) && (await this.state.storage.getAlarm()) === null) {
        await this.state.storage.setAlarm(now)
        return Response.json({ started: true })
      }
      return Response.json({ started: false })
    }
    if (path === '/status') {
      const alarm = await this.state.storage.getAlarm()
      return Response.json({ recording: alarm !== null, nextPollAt: alarm, feeds: await this.loadStats() })
    }
    return new Response('not found', { status: 404 })
  }

  async alarm(): Promise<void> {
    const now = Date.now()
    if (!this.recording(now)) {
      this.prev.clear()
      return
    }
    const stats = await this.loadStats()
    const due = (await this.state.storage.get<Record<string, number>>('due')) ?? {}
    const toPoll = FEEDS.filter((f) => (due[f.id] ?? 0) <= now)
    for (const f of toPoll) due[f.id] = now + f.intervalMs
    // Saved before polling so an eviction mid-poll can't make 511 poll early.
    await this.state.storage.put('due', due)
    await Promise.all(
      toPoll.map(async (f) => {
        const st = stats[f.id]
        try {
          const extra = await this.poll(f, now, st)
          if (extra) due[f.id] = now + extra
        } catch (e) {
          st.lastError = String((e as Error)?.message ?? e).slice(0, 300)
          st.lastErrorAt = now
        }
      }),
    )
    await this.state.storage.put({ due, stats })
    const next = Math.min(...FEEDS.map((f) => due[f.id] ?? now + f.intervalMs))
    await this.state.storage.setAlarm(Math.max(next, Date.now() + 1000))
  }

  // Returns a longer wait in ms when the feed asks us to back off.
  private async poll(f: FeedDef, now: number, st: FeedStat): Promise<number | void> {
    const url = f.url(this.env)
    if (!url) {
      st.lastError = 'no API key configured'
      st.lastErrorAt = now
      return
    }
    st.polls++
    const res = await fetch(url, { signal: AbortSignal.timeout(25_000) })
    if (res.status === 429) {
      st.lastError = 'HTTP 429 (rate limited)'
      st.lastErrorAt = now
      return 5 * f.intervalMs
    }
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const buf = new Uint8Array(await res.arrayBuffer())
    const feed = decodeFeed(buf, f.keep)

    const trips = new Map<string, string>()
    for (const t of feed.trips) trips.set(t.id, JSON.stringify(packTrip(t)))
    const bucket = Math.floor(now / BUCKET_MS)
    const prev = this.prev.get(f.id)
    let kind: 'full' | 'diff'
    let body: string
    let n: number
    if (!prev || prev.bucket !== bucket) {
      kind = 'full'
      n = trips.size
      body = `{"ts":${feed.ts},"trips":[${[...trips.values()].join(',')}]}`
    } else {
      kind = 'diff'
      const changed: string[] = []
      for (const [id, s] of trips) if (prev.trips.get(id) !== s) changed.push(s)
      const gone = [...prev.trips.keys()].filter((id) => !trips.has(id))
      n = changed.length
      body = `{"ts":${feed.ts},"trips":[${changed.join(',')}],"gone":${JSON.stringify(gone)}}`
    }
    const data = await gzip(body)
    const day = pacific(now).day
    await this.env.DB.batch([
      this.env.DB.prepare('INSERT OR IGNORE INTO days (source, day) VALUES (?, ?)').bind(SOURCE, day),
      this.env.DB.prepare(
        'INSERT INTO snapshots (source, day, feed, fetched_at, feed_ts, kind, trips, bytes, data) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
      ).bind(SOURCE, day, f.id, now, feed.ts, kind, n, data.byteLength, data),
    ])
    this.prev.set(f.id, { bucket, trips })
    st.lastOkAt = now
    st.lastTrips = trips.size
    st.lastBytes = buf.byteLength
  }
}
