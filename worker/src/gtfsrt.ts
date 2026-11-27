// Minimal GTFS-Realtime TripUpdate decoder. It reads only the fields the recorder
// keeps and skips every other field, so a large regional feed costs little CPU.
// Schema: https://gtfs.org/realtime/reference/

export interface StopUpdate {
  stop: string
  arr: number | null // predicted arrival, unix seconds
  dep: number | null // predicted departure, unix seconds
  delay: number | null // seconds, when the feed gives one
  skipped?: true
}

export interface TripUpdate {
  id: string
  route: string
  date: string
  start: string
  rel?: number // TripDescriptor.ScheduleRelationship when not SCHEDULED (0)
  stops: StopUpdate[]
}

export interface Feed {
  ts: number // header timestamp, unix seconds
  trips: TripUpdate[]
}

const td = new TextDecoder()

class Reader {
  buf: Uint8Array
  pos: number
  end: number
  constructor(buf: Uint8Array, start = 0, end = buf.length) {
    this.buf = buf
    this.pos = start
    this.end = end
  }
  varint(): number {
    let result = 0
    let mul = 1
    for (;;) {
      const b = this.buf[this.pos++]
      result += (b & 0x7f) * mul
      if (b < 0x80) return result
      mul *= 128
    }
  }
  // int32/int64 fields are two's complement varints; negatives are 10 bytes.
  signed(): number {
    const v = this.varint()
    return v >= 2 ** 63 ? v - 2 ** 64 : v
  }
  bytes(): [number, number] {
    const len = this.varint()
    const s = this.pos
    this.pos += len
    return [s, this.pos]
  }
  string(): string {
    const [s, e] = this.bytes()
    return td.decode(this.buf.subarray(s, e))
  }
  skip(wire: number): void {
    if (wire === 0) this.varint()
    else if (wire === 1) this.pos += 8
    else if (wire === 2) this.bytes()
    else if (wire === 5) this.pos += 4
    else throw new Error(`unsupported wire type ${wire}`)
  }
}

interface Event {
  time: number | null
  delay: number | null
}

function readEvent(buf: Uint8Array, s: number, e: number): Event {
  const r = new Reader(buf, s, e)
  const ev: Event = { time: null, delay: null }
  while (r.pos < r.end) {
    const tag = r.varint()
    const f = tag >>> 3
    if (f === 1 && (tag & 7) === 0) ev.delay = r.signed()
    else if (f === 2 && (tag & 7) === 0) ev.time = r.signed()
    else r.skip(tag & 7)
  }
  return ev
}

function readStopUpdate(buf: Uint8Array, s: number, e: number): StopUpdate {
  const r = new Reader(buf, s, e)
  const u: StopUpdate = { stop: '', arr: null, dep: null, delay: null }
  while (r.pos < r.end) {
    const tag = r.varint()
    const f = tag >>> 3
    if (f === 2 && (tag & 7) === 2) {
      const ev = readEvent(buf, ...r.bytes())
      u.arr = ev.time
      if (ev.delay !== null) u.delay = ev.delay
    } else if (f === 3 && (tag & 7) === 2) {
      const ev = readEvent(buf, ...r.bytes())
      u.dep = ev.time
      if (u.delay === null && ev.delay !== null) u.delay = ev.delay
    } else if (f === 4 && (tag & 7) === 2) u.stop = r.string()
    else if (f === 5 && (tag & 7) === 0) {
      if (r.varint() === 1) u.skipped = true
    } else r.skip(tag & 7)
  }
  return u
}

function readTripDescriptor(buf: Uint8Array, s: number, e: number, t: TripUpdate): void {
  const r = new Reader(buf, s, e)
  while (r.pos < r.end) {
    const tag = r.varint()
    const f = tag >>> 3
    if (f === 1 && (tag & 7) === 2) t.id = r.string()
    else if (f === 2 && (tag & 7) === 2) t.start = r.string()
    else if (f === 3 && (tag & 7) === 2) t.date = r.string()
    else if (f === 4 && (tag & 7) === 0) {
      const rel = r.varint()
      if (rel !== 0) t.rel = rel
    } else if (f === 5 && (tag & 7) === 2) t.route = r.string()
    else r.skip(tag & 7)
  }
}

// keep(route, tripId) runs right after the trip descriptor is read, before the
// stop updates are decoded, so dropped trips are skipped cheaply.
function readTripUpdate(
  buf: Uint8Array,
  s: number,
  e: number,
  keep: (route: string, tripId: string) => boolean,
): TripUpdate | null {
  const r = new Reader(buf, s, e)
  const t: TripUpdate = { id: '', route: '', date: '', start: '', stops: [] }
  const stopRanges: [number, number][] = []
  let haveTrip = false
  while (r.pos < r.end) {
    const tag = r.varint()
    const f = tag >>> 3
    if (f === 1 && (tag & 7) === 2) {
      readTripDescriptor(buf, ...r.bytes(), t)
      haveTrip = true
      if (!keep(t.route, t.id)) return null
    } else if (f === 2 && (tag & 7) === 2) stopRanges.push(r.bytes())
    else r.skip(tag & 7)
  }
  if (!haveTrip || !keep(t.route, t.id)) return null
  for (const [a, b] of stopRanges) t.stops.push(readStopUpdate(buf, a, b))
  return t
}

export function decodeFeed(
  buf: Uint8Array,
  keep: (route: string, tripId: string) => boolean = () => true,
): Feed {
  const r = new Reader(buf)
  const feed: Feed = { ts: 0, trips: [] }
  while (r.pos < r.end) {
    const tag = r.varint()
    const f = tag >>> 3
    if (f === 1 && (tag & 7) === 2) {
      const h = new Reader(buf, ...r.bytes())
      while (h.pos < h.end) {
        const ht = h.varint()
        if (ht >>> 3 === 3 && (ht & 7) === 0) feed.ts = h.varint()
        else h.skip(ht & 7)
      }
    } else if (f === 2 && (tag & 7) === 2) {
      const en = new Reader(buf, ...r.bytes())
      let deleted = false
      let trip: TripUpdate | null = null
      while (en.pos < en.end) {
        const et = en.varint()
        const ef = et >>> 3
        if (ef === 2 && (et & 7) === 0) deleted = en.varint() === 1
        else if (ef === 3 && (et & 7) === 2) trip = readTripUpdate(buf, ...en.bytes(), keep)
        else en.skip(et & 7)
      }
      if (trip && !deleted) feed.trips.push(trip)
    } else r.skip(tag & 7)
  }
  return feed
}
