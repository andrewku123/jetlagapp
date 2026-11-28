import type { TripUpdate } from './gtfsrt'

export interface FeedDef {
  id: string
  intervalMs: number
  url: (env: Env) => string | null
  keep: (route: string, tripId: string) => boolean
}

export interface Env {
  DB: D1Database
  RECORDER: DurableObjectNamespace
  GROUP_PASSWORD_HASH?: string
  SF511_API_KEY?: string
  // Local testing only: record outside 07:30-22:00.
  ALWAYS_RECORD?: string
}

// Lines on the Bay Area / SF Muni maps (src/data/stations.json `lines`), as
// 511 RG route ids. BART comes from its own 30 s feed. Muni and VTA buses, owl buses and other operators are dropped.
const RG_ROUTES: Record<string, Set<string> | 'all'> = {
  SF: new Set(['J', 'K', 'L', 'M', 'N', 'T', 'F', 'S']),
  SC: new Set(['Blue Line', 'Green Line', 'Orange Line']),
  CT: 'all',
  SB: new Set(['OAS']), // Oakland Alameda Water Shuttle (511 lists it as not monitored)
}

export function keepRg(route: string, tripId: string): boolean {
  const src = route || tripId
  const i = src.indexOf(':')
  if (i < 0) return false
  const rule = RG_ROUTES[src.slice(0, i)]
  if (!rule) return false
  if (rule === 'all') return true
  return route !== '' && rule.has(route.slice(i + 1))
}

export const FEEDS: FeedDef[] = [
  {
    id: 'bart',
    intervalMs: 30_000,
    url: () => 'https://api.bart.gov/gtfsrt/tripupdate.aspx',
    keep: () => true,
  },
  {
    // 60 requests per hour per key by default: 61 s keeps it at 59.
    id: '511',
    intervalMs: 61_000,
    url: (env) =>
      env.SF511_API_KEY
        ? `https://api.511.org/transit/tripupdates?agency=RG&api_key=${encodeURIComponent(env.SF511_API_KEY)}`
        : null,
    keep: keepRg,
  },
]

// The recorded network: both Bay Area maps read the same feeds.
export const SOURCE = 'bayarea'
export const REGION_SOURCES: Record<string, string> = { bayarea: SOURCE, sfmuni: SOURCE }
export const REGIONS = new Set(['bayarea', 'sfmuni', 'la', 'dc'])

// Compact stored form: [tripId, route, startDate, startTime, rel, [[stop, arr, dep, delay, skipped]]]
export type PackedTrip = [string, string, string, string, number, (string | number | null)[][]]

export function packTrip(t: TripUpdate): PackedTrip {
  return [
    t.id,
    t.route,
    t.date,
    t.start,
    t.rel ?? 0,
    t.stops.map((s) => (s.skipped ? [s.stop, s.arr, s.dep, s.delay, 1] : [s.stop, s.arr, s.dep, s.delay])),
  ]
}
