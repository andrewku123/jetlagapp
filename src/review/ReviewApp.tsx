import { useCallback, useEffect, useMemo, useState } from 'react'
import MapView from '../components/MapView'
import { describeRecord } from '../lib/describe'
import { emptyGame, loadGame, saveGame } from '../lib/storage'
import { hidingRadiusMi } from '../lib/hidingZone'
import { haversineMeters } from '../lib/geo'
import { countyAt } from '../lib/counties'
import { ELIGIBLE_HEADWAY_MIN } from '../data/questionSets'
import { ACTIVE_REGION_ID, MAP_NAME, REGIONS, setActiveRegion, stationsData } from '../data/regions'
import {
  deleteRound,
  exportRound,
  fetchRemoteRounds,
  flushUploads,
  importRound,
  isEmptyBoard,
  loadLocalSetups,
  loadSavedRounds,
  mergeRounds,
  pendingUploads,
  saveRound,
  saveSetup,
  type ReviewRound,
  type ReviewSetup,
} from '../lib/reviewRounds'
import { asActive, buildTimeline, countedQuestions, remainingAt, REVIEW_CUTOFF_MIN, type TimelineEvent } from '../lib/reviewTimeline'
import { arrivalAt, dayTimetable, earliestArrivals, legsTo, pacificTime, serviceDate, type DayTimetable, type NetworkFile } from '../lib/transitNetwork'
import { curseMinutes, curseOrigin, curseOver, fastestClear, type ClearTrip, type ReviewCurse } from '../lib/reviewCurses'
import type { LatLng, QuestionRecord, Station } from '../types'

const STATIONS = stationsData as Station[]
const NAME = new Map(STATIONS.map((s) => [s.id, s.name]))
const noop = () => {}

// Where the seekers stood when they asked: every located question stores it.
function spotOf(q: QuestionRecord): LatLng | null {
  const lat = Number(q.params.fromLat ?? q.params.lat)
  const lon = Number(q.params.fromLon ?? q.params.lon)
  return Number.isFinite(lat) && Number.isFinite(lon) && (lat !== 0 || lon !== 0) ? { lat, lon } : null
}

// A question asked from a moving train (ticked in cleanup, or a spot in the
// water like the Transbay Tube) counts travel from the nearest station.
function travelSpot(q: QuestionRecord, onTrain: Set<string>): { spot: LatLng; onBoard?: string } | null {
  const spot = spotOf(q)
  if (!spot) return null
  if (!onTrain.has(q.id) && countyAt(spot)) return { spot }
  let near: Station | null = null
  let d = Infinity
  for (const s of STATIONS) {
    const m = haversineMeters(spot, s)
    if (m < d) [near, d] = [s, m]
  }
  return near ? { spot: { lat: near.lat, lon: near.lon }, onBoard: near.name } : { spot }
}

interface Travel {
  fastest: number // minutes, leaving the previous spot when that question was asked
  took: number
  via: string
  onBoard: string[]
}

function useNetwork(): NetworkFile | null | 'none' {
  const [net, setNet] = useState<NetworkFile | null | 'none'>(null)
  useEffect(() => {
    let live = true
    fetch(`${import.meta.env.BASE_URL}transit/${ACTIVE_REGION_ID}.json`)
      .then((r): Promise<NetworkFile | 'none'> | 'none' => (r.ok ? r.json() : 'none'))
      .catch((): 'none' => 'none')
      .then((n) => {
        if (live) setNet(n)
      })
    return () => {
      live = false
    }
  }, [])
  return net
}

// One timetable per game day, read on a stand-in day when the saved file
// doesn't cover it.
const dayCache = new WeakMap<NetworkFile, Map<string, DayTimetable | null>>()
function timetables(net: NetworkFile) {
  let days = dayCache.get(net)
  if (!days) dayCache.set(net, (days = new Map()))
  return (t: number) => {
    const { date, sec } = pacificTime(t)
    if (!days.has(date)) {
      const d = serviceDate(net, date)
      days.set(date, d ? dayTimetable(net, d, STATIONS) : null)
    }
    return { tt: days.get(date) ?? null, sec }
  }
}

// Fastest transit time between consecutive question spots, against how long it
// took. A stretch that overlaps a curse is curse time, and anything from the
// endgame start on is endgame; neither gets a comparison.
function travelBetweenQuestions(
  net: NetworkFile,
  questions: QuestionRecord[],
  curses: ReviewCurse[],
  onTrain: Set<string>,
  endgameAt?: number,
): Map<string, Travel> {
  const out = new Map<string, Travel>()
  const day = timetables(net)
  let prev: { q: QuestionRecord; spot: LatLng; onBoard?: string } | null = null
  for (const q of [...questions].sort((a, b) => a.createdAt - b.createdAt)) {
    const here = travelSpot(q, onTrain)
    if (!here) continue
    const { spot } = here
    if (endgameAt !== undefined && q.createdAt >= endgameAt) break
    if (prev && !curseOver(curses, prev.q.createdAt, q.createdAt)) {
      const { tt, sec } = day(prev.q.createdAt)
      if (tt) {
        const a = earliestArrivals(tt, prev.spot, sec)
        const best = arrivalAt(tt, a, spot)
        const rides = best.station < 0 ? [] : legsTo(tt, a, best.station).flatMap((l) => (l.kind === 'ride' ? [l.route] : []))
        out.set(q.id, {
          fastest: Math.round((best.at - sec) / 60),
          took: Math.round((q.createdAt - prev.q.createdAt) / 60_000),
          via: rides.length ? rides.join(' → ') : 'walking',
          onBoard: [prev.onBoard, here.onBoard].filter((n): n is string => !!n),
        })
      }
    }
    prev = { q, ...here }
  }
  return out
}

// Each question whose stretch since the previous one overlaps a curse.
function cursedQuestions(questions: QuestionRecord[], curses: ReviewCurse[], startAt?: number): Map<string, ReviewCurse> {
  const out = new Map<string, ReviewCurse>()
  let prev = startAt
  for (const q of [...questions].sort((a, b) => a.createdAt - b.createdAt)) {
    const c = prev === undefined ? null : curseOver(curses, prev, q.createdAt)
    if (c) out.set(q.id, c)
    prev = q.createdAt
  }
  return out
}

interface CurseTrips {
  listed: ClearTrip | null
  hindsight: ClearTrip | null
}

function curseTrips(net: NetworkFile, curses: ReviewCurse[], questions: QuestionRecord[], onTrain: Set<string>): Map<string, CurseTrips> {
  const out = new Map<string, CurseTrips>()
  const day = timetables(net)
  for (const c of curses) {
    if (!c.clearAt?.length && !c.hindsightAt?.length) continue
    const origin = curseOrigin(c, questions, STATIONS, (q) => travelSpot(q, onTrain)?.spot ?? null)
    const { tt } = day(c.startAt)
    if (!origin || !tt) continue
    out.set(c.id, {
      listed: c.clearAt?.length ? fastestClear(tt, origin, c, STATIONS) : null,
      hindsight: c.hindsightAt?.length ? fastestClear(tt, origin, c, STATIONS, c.hindsightAt) : null,
    })
  }
  return out
}

const clock = (t: number) => new Date(t).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
const day = (t: number) => new Date(t).toLocaleDateString([], { weekday: 'short', month: 'numeric', day: 'numeric' })
const dayKey = (t: number) => new Date(t).toDateString()
const startOf = (r: ReviewRound) => r.review?.startAt ?? r.game.questions[0]?.createdAt ?? r.savedAt

// "Sat 11/28, round 3, 2:10 pm": rounds are numbered within their day
function roundLabels(rounds: ReviewRound[]): Map<string, string> {
  const byDay = new Map<string, ReviewRound[]>()
  for (const r of rounds) {
    const k = dayKey(startOf(r))
    byDay.set(k, [...(byDay.get(k) ?? []), r])
  }
  const out = new Map<string, string>()
  for (const list of byDay.values()) {
    list.sort((a, b) => startOf(a) - startOf(b))
    list.forEach((r, i) => out.set(r.id, `${day(startOf(r))}, round ${i + 1}, ${clock(startOf(r))}`))
  }
  return out
}

function download(name: string, text: string) {
  const url = URL.createObjectURL(new Blob([text], { type: 'application/json' }))
  const a = document.createElement('a')
  a.href = url
  a.download = name
  a.click()
  URL.revokeObjectURL(url)
}

// datetime-local <-> unix ms, in the phone's time zone
const toLocalInput = (t?: number) => {
  if (t === undefined) return ''
  const d = new Date(t)
  d.setMinutes(d.getMinutes() - d.getTimezoneOffset())
  return d.toISOString().slice(0, 16)
}
const fromLocalInput = (v: string) => (v ? new Date(v).getTime() : undefined)

export default function ReviewApp() {
  const [rounds, setRounds] = useState<ReviewRound[]>(() => mergeRounds(loadSavedRounds(), [], loadLocalSetups()))
  const [status, setStatus] = useState<string>('Loading saved rounds…')
  const [openId, setOpenId] = useState<string | null>(null)
  const [liveEmpty, setLiveEmpty] = useState(() => isEmptyBoard(loadGame()))

  const refresh = useCallback(async () => {
    await flushUploads()
    const local = loadSavedRounds()
    try {
      const remote = await fetchRemoteRounds()
      setRounds(mergeRounds(local, remote, loadLocalSetups()))
      const waiting = pendingUploads().length
      setStatus(waiting ? `${waiting} round${waiting === 1 ? '' : 's'} waiting to upload.` : '')
    } catch {
      setRounds(mergeRounds(local, [], loadLocalSetups()))
      setStatus("Couldn't reach the review server: showing rounds saved on this phone.")
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const labels = useMemo(() => roundLabels(rounds), [rounds])
  const open = rounds.find((r) => r.id === openId) ?? null

  function saveLastRound() {
    if (!confirm('Save the board on this phone as a round and clear it?')) return
    saveRound(loadGame())
    saveGame({ ...emptyGame })
    setLiveEmpty(true)
    void refresh()
  }

  function onImport(file: File) {
    void file.text().then((text) => {
      const res = importRound(text)
      if (typeof res === 'string') alert(res)
      else void refresh()
    })
  }

  if (open) {
    return (
      <RoundView
        round={open}
        label={labels.get(open.id) ?? ''}
        onBack={() => setOpenId(null)}
        onSaved={(review) => setRounds((rs) => rs.map((r) => (r.id === open.id ? { ...r, review } : r)))}
      />
    )
  }

  return (
    <div className="review-home">
      <header className="review-head">
        <h1>{MAP_NAME} game review</h1>
        <label className="region-pick">
          map
          <select value={ACTIVE_REGION_ID} onChange={(e) => setActiveRegion(e.target.value)}>
            {REGIONS.map((r) => (
              <option key={r.id} value={r.id}>
                {r.name}
              </option>
            ))}
          </select>
        </label>
      </header>
      <p className="hint">
        Only saved rounds show here. Reset in the game saves a round; the last one of the day is saved with the button
        below.
      </p>
      <div className="review-actions">
        <button onClick={saveLastRound} disabled={liveEmpty}>
          Save last round
        </button>
        <label className="review-import">
          Import
          <input type="file" accept="application/json,.json" onChange={(e) => e.target.files?.[0] && onImport(e.target.files[0])} />
        </label>
        <button onClick={() => void refresh()}>Refresh</button>
      </div>
      {status && <p className="hint">{status}</p>}
      {rounds.length === 0 && <p className="hint">No saved rounds yet.</p>}
      <ul className="review-rounds">
        {rounds.map((r) => (
          <li key={r.id}>
            <button className="review-open" onClick={() => setOpenId(r.id)}>
              <strong>{labels.get(r.id)}</strong>
              <span className="hint">
                {r.game.questions.length} question{r.game.questions.length === 1 ? '' : 's'}
                {r.remote ? '' : ' · on this phone only'}
              </span>
            </button>
            <div className="qactions">
              <button onClick={() => download(`round-${r.id}.json`, exportRound(r))}>Export</button>
              <button
                onClick={() => {
                  if (!confirm(`Delete ${labels.get(r.id)} for everyone?`)) return
                  void deleteRound(r).then(() => refresh())
                }}
              >
                Delete
              </button>
            </div>
          </li>
        ))}
      </ul>
    </div>
  )
}

type Tab = 'timeline' | 'setup' | 'cleanup'

function RoundView({
  round,
  label,
  onBack,
  onSaved,
}: {
  round: ReviewRound
  label: string
  onBack: () => void
  onSaved: (r: ReviewSetup) => void
}) {
  const game = round.game
  const [tab, setTab] = useState<Tab>('timeline')
  const [setup, setSetup] = useState<ReviewSetup>(
    () =>
      round.review ?? {
        excluded: game.questions.filter((q) => !q.active || q.vetoed).map((q) => q.id),
      },
  )
  const [saveMsg, setSaveMsg] = useState('')
  const excluded = useMemo(() => new Set(setup.excluded ?? []), [setup.excluded])
  const base = useMemo(() => STATIONS.filter((s) => s.headwayMin[game.dayType] <= ELIGIBLE_HEADWAY_MIN), [game.dayType])
  const events = useMemo(() => buildTimeline(base, game, excluded, setup.hiderStation), [base, game, excluded, setup.hiderStation])
  const questions = useMemo(() => countedQuestions(game, excluded), [game, excluded])
  const net = useNetwork()
  const curses = useMemo(() => setup.curses ?? [], [setup.curses])
  const onTrain = useMemo(() => new Set(setup.onTrain ?? []), [setup.onTrain])
  const travel = useMemo(
    () => (net && net !== 'none' ? travelBetweenQuestions(net, questions, curses, onTrain, setup.endgameStartAt) : new Map<string, Travel>()),
    [net, questions, curses, onTrain, setup.endgameStartAt],
  )
  const cursed = useMemo(() => cursedQuestions(questions, curses, setup.startAt), [questions, curses, setup.startAt])
  const trips = useMemo(
    () => (net && net !== 'none' ? curseTrips(net, curses, questions, onTrain) : new Map<string, CurseTrips>()),
    [net, curses, questions],
  )
  const standIn = useMemo(() => {
    if (!net || net === 'none' || !questions.length) return null
    const { date } = pacificTime(questions[0].createdAt)
    const d = serviceDate(net, date)
    return d && d !== date ? d : null
  }, [net, questions])
  const rows = useMemo(
    () =>
      [
        ...events.map((ev, i) => ({ at: ev.at, ev, i })),
        ...curses.map((c) => ({ at: c.startAt, curse: c })),
      ].sort((a, b) => a.at - b.at),
    [events, curses],
  )

  const first = events[0]?.at ?? round.savedAt
  const last = events[events.length - 1]?.at ?? round.savedAt
  const [t, setT] = useState(last)
  const asked = useMemo(
    () => events.filter((e): e is Extract<TimelineEvent, { kind: 'question' }> => e.kind === 'question'),
    [events],
  )
  const step = asked.reduce((k, e, i) => (e.at <= t ? i : k), -1)
  const cur = step >= 0 ? asked[step] : null
  const go = (i: number) => setT(i < 0 ? first - 1 : asked[Math.min(i, asked.length - 1)].at)
  const remaining = useMemo(() => remainingAt(base, game, questions, t), [base, game, questions, t])
  const eliminated = useMemo(() => {
    const keep = new Set(remaining.map((s) => s.id))
    return base.filter((s) => !keep.has(s.id))
  }, [base, remaining])
  const records = useMemo(() => questions.filter((q) => q.createdAt <= t).map(asActive), [questions, t])
  const manualAt = useMemo(
    () =>
      new Set(
        game.eliminationLog.filter((m) => m.outAt <= t && (m.backAt === undefined || m.backAt > t)).map((m) => m.stationId),
      ),
    [game.eliminationLog, t],
  )
  const pickedPoints = useMemo(() => {
    const pts: { label: string; point: LatLng; color: string }[] = []
    if (setup.hiderStation) {
      const h = STATIONS.find((s) => s.id === setup.hiderStation)
      if (h) pts.push({ label: `Hider: ${h.name}`, point: { lat: h.lat, lon: h.lon }, color: '#d97706' })
    }
    return pts
  }, [setup.hiderStation])

  function edit(patch: Partial<ReviewSetup>) {
    setSetup((s) => ({ ...s, ...patch }))
    setSaveMsg('')
  }
  async function save() {
    const ok = await saveSetup(round, setup)
    onSaved(setup)
    setSaveMsg(ok ? 'Saved for everyone.' : round.remote ? "Saved on this phone; couldn't reach the server." : 'Saved on this phone.')
  }
  const cutoffDefault = REVIEW_CUTOFF_MIN[game.gameSize]
  const stationOptions = useMemo(() => [...base].sort((a, b) => a.name.localeCompare(b.name)), [base])

  return (
    <div className="app">
      <header className="topbar">
        <button className="review-back" onClick={onBack}>
          ← Rounds
        </button>
        <div className="brand">{label}</div>
        <div className="counts">
          <strong>{remaining.length}</strong> of {base.length} at {clock(t)}
        </div>
      </header>
      <div className="body">
        <div className="mapwrap">
          <MapView
            remaining={remaining}
            eliminated={eliminated}
            showEliminated
            satellite={false}
            starred={new Set()}
            manualEliminated={manualAt}
            units={game.units}
            onPickLocation={noop}
            onToggleStar={noop}
            onToggleEliminate={noop}
            records={records}
            preview={null}
            onClearPreview={noop}
            pickedPoints={pickedPoints}
            annotations={[]}
            onAddAnnotation={noop}
            onDeleteAnnotation={noop}
            onUpdateAnnotation={noop}
            onMovePoint={noop}
            onClearAnnotations={noop}
            endgameStation={null}
            hidingRadiusMi={hidingRadiusMi(game.gameSize, game.zoneCurses)}
            stripes
            focusTarget={null}
            poiFocus={null}
            onStartEndgame={noop}
            onExitEndgame={noop}
            pois={[]}
            stationView="normal"
            dayType={game.dayType}
            readOnly
          />
        </div>
        <aside className="sidebar review-side">
          <div className="review-step">
            <button onClick={() => go(step - 1)} disabled={step < 0}>
              ‹ Prev
            </button>
            <div className="review-now">
              {cur ? (
                <>
                  <span className="hint">
                    Q{step + 1} of {asked.length} · {clock(cur.at)} · {cur.before === cur.left ? `${cur.left} left` : `${cur.before} → ${cur.left} left`}
                  </span>
                  <div>{describeRecord(cur.record, game.units)}</div>
                </>
              ) : (
                <span className="hint">{asked.length ? 'Start, before the first question' : 'No questions logged'}</span>
              )}
            </div>
            <button onClick={() => go(step + 1)} disabled={step >= asked.length - 1}>
              Next ›
            </button>
          </div>
          <nav className="tabs">
            {(['timeline', 'setup', 'cleanup'] as Tab[]).map((k) => (
              <button key={k} className={tab === k ? 'on' : ''} onClick={() => setTab(k)}>
                {k === 'timeline' ? 'Timeline' : k === 'setup' ? 'Setup' : 'Cleanup'}
              </button>
            ))}
          </nav>
          {tab === 'timeline' && (
            <div className="panel">
              <p className="hint">
                Move ranks (#X of N, minutes slower than best) aren't in yet. Each question shows the fastest transit time
                from the previous question's spot. Tap a row to replay the map to that moment.
              </p>
              {standIn && (
                <p className="hint">
                  This game day isn't in the saved timetable, so times use the published schedule for {standIn} (same
                  weekday).
                </p>
              )}
              {events.length === 0 && <p className="hint">Nothing was logged in this round.</p>}
              <ul className="qlist review-timeline">
                {rows.map((r) =>
                  'curse' in r ? (
                    <CurseRow key={`c-${r.curse.id}`} curse={r.curse} trips={trips.get(r.curse.id)} on={r.curse.startAt <= t && r.curse.endAt > t} onPick={() => setT(Math.min(Math.max(r.curse.startAt, first), last))} />
                  ) : (
                    <TimelineRow
                      key={r.i}
                      ev={r.ev}
                      travel={r.ev.kind === 'question' ? travel.get(r.ev.record.id) : undefined}
                      curse={r.ev.kind === 'question' ? cursed.get(r.ev.record.id) : undefined}
                      endgame={r.ev.kind === 'question' && setup.endgameStartAt !== undefined && r.ev.record.createdAt >= setup.endgameStartAt}
                      units={game.units}
                      on={r.ev.at <= t && (events[r.i + 1]?.at ?? Infinity) > t}
                      onPick={() => setT(r.ev.at)}
                    />
                  ),
                )}
              </ul>
            </div>
          )}
          {tab === 'setup' && (
            <div className="panel qform">
              <div className="row">
                <label>Game date</label>
                <input type="date" value={setup.gameDate ?? new Date(round.savedAt).toLocaleDateString('en-CA')} onChange={(e) => edit({ gameDate: e.target.value })} />
              </div>
              <div className="row">
                <label>Seekers released</label>
                <input type="datetime-local" value={toLocalInput(setup.startAt)} onChange={(e) => edit({ startAt: fromLocalInput(e.target.value) })} />
              </div>
              <div className="row">
                <label>Start station</label>
                <StationSelect value={setup.startStation} options={stationOptions} onChange={(v) => edit({ startStation: v })} />
              </div>
              <div className="row">
                <label>Hider's station</label>
                <StationSelect value={setup.hiderStation} options={stationOptions} onChange={(v) => edit({ hiderStation: v })} />
              </div>
              <p className="hint">Only used to show which answers kept the hider's station; never in scoring.</p>
              <div className="row">
                <label>Hider cutoff (min)</label>
                <input
                  type="number"
                  min={1}
                  value={setup.cutoffMin ?? cutoffDefault}
                  onChange={(e) => edit({ cutoffMin: e.target.value ? Number(e.target.value) : undefined })}
                />
              </div>
              <div className="row">
                <label>Endgame started</label>
                <input type="datetime-local" value={toLocalInput(setup.endgameStartAt)} onChange={(e) => edit({ endgameStartAt: fromLocalInput(e.target.value) })} />
              </div>
              <p className="hint">Questions from this time on are endgame: their eliminations still count, but they aren't ranked.</p>
              <div className="row">
                <label>Hider found</label>
                <input type="datetime-local" value={toLocalInput(setup.foundAt)} onChange={(e) => edit({ foundAt: fromLocalInput(e.target.value) })} />
              </div>
              <CurseEditor curses={curses} options={stationOptions} defaultAt={first} onChange={(next) => edit({ curses: next })} />
              <button className="primary" onClick={() => void save()}>
                Save setup
              </button>
              {saveMsg && <p className="hint">{saveMsg}</p>}
            </div>
          )}
          {tab === 'cleanup' && (
            <div className="panel">
              <p className="hint">Untick records the review should skip. Tick "asked on a train" when the seekers asked while riding, so travel counts from the nearest station. This only changes the review, never the saved game.</p>
              <ul className="qlist">
                {game.questions.map((q, i) => {
                  const flags: string[] = []
                  if (setup.startAt !== undefined && q.createdAt < setup.startAt) flags.push('before release')
                  const prev = game.questions[i - 1]
                  if (prev && prev.kind === q.kind && q.createdAt - prev.createdAt < 120_000 && JSON.stringify(prev.params) === JSON.stringify(q.params))
                    flags.push('possible duplicate')
                  if (q.vetoed) flags.push('vetoed')
                  else if (!q.active) flags.push('disabled in game')
                  return (
                    <li key={q.id}>
                      <label className="chk">
                        <input
                          type="checkbox"
                          checked={!excluded.has(q.id)}
                          disabled={q.vetoed}
                          onChange={(e) => {
                            const next = new Set(excluded)
                            if (e.target.checked) next.delete(q.id)
                            else next.add(q.id)
                            edit({ excluded: [...next] })
                          }}
                        />
                        {clock(q.createdAt)} · {describeRecord(q, game.units)}
                      </label>
                      {spotOf(q) && (
                        <label className="chk review-train">
                          <input
                            type="checkbox"
                            checked={onTrain.has(q.id)}
                            onChange={(e) => {
                              const next = new Set(onTrain)
                              if (e.target.checked) next.add(q.id)
                              else next.delete(q.id)
                              edit({ onTrain: [...next] })
                            }}
                          />
                          asked on a train
                        </label>
                      )}
                      {flags.map((f) => (
                        <span key={f} className="tag">
                          {f}
                        </span>
                      ))}
                    </li>
                  )
                })}
              </ul>
              <button className="primary" onClick={() => void save()}>
                Save cleanup
              </button>
              {saveMsg && <p className="hint">{saveMsg}</p>}
            </div>
          )}
        </aside>
      </div>
    </div>
  )
}

function StationSelect({ value, options, onChange }: { value?: string; options: Station[]; onChange: (v?: string) => void }) {
  return (
    <select value={value ?? ''} onChange={(e) => onChange(e.target.value || undefined)}>
      <option value="">—</option>
      {options.map((s) => (
        <option key={s.id} value={s.id}>
          {s.name}
        </option>
      ))}
    </select>
  )
}

function TimelineRow({
  ev,
  travel,
  curse,
  endgame,
  units,
  on,
  onPick,
}: {
  ev: TimelineEvent
  travel?: Travel
  curse?: ReviewCurse
  endgame?: boolean
  units: 'imperial' | 'metric'
  on: boolean
  onPick: () => void
}) {
  const text =
    ev.kind === 'question'
      ? describeRecord(ev.record, units)
      : `${ev.kind === 'out' ? 'Crossed out' : 'Put back'} ${NAME.get(ev.stationId) ?? ev.stationId}`
  const photo = ev.kind === 'question' && ev.record.kind === 'photo'
  return (
    <li className={on ? 'review-on' : ''} onClick={onPick}>
      <div className="qtext">
        <span className="review-time">{clock(ev.at)}</span> {text}
        {photo && !endgame && <span className="tag">unranked</span>}
        {curse && !endgame && <span className="tag curse">curse time</span>}
        {endgame && <span className="tag">endgame, not ranked</span>}
        {ev.kind === 'question' && ev.record.curse && <span className="tag curse">curse info</span>}
      </div>
      <div className="qreward">
        {ev.before === ev.left ? `${ev.left} left` : `${ev.before} → ${ev.left} left`}
        {ev.keptHider === false && <span className="tag veto">ruled out hider's station</span>}
      </div>
      {travel && (
        <div className="hint">
          Fastest from last spot: {travel.fastest} min ({travel.via}) · took {travel.took} min
          {travel.onBoard.length > 0 && ` · asked on a train, counted from ${travel.onBoard.join(' and ')}`}
        </div>
      )}
    </li>
  )
}

function CurseRow({ curse, trips, on, onPick }: { curse: ReviewCurse; trips?: CurseTrips; on: boolean; onPick: () => void }) {
  const listed = trips?.listed
  const hind = trips?.hindsight
  const lost = listed ? Math.max(0, listed.took - listed.fastest) : null
  return (
    <li className={on ? 'review-on' : ''} onClick={onPick}>
      <div className="qtext">
        <span className="review-time">{clock(curse.startAt)}</span> Curse: {curse.name || 'unnamed'}
        <span className="tag curse">curse time</span>
      </div>
      <div className="qreward">
        {clock(curse.startAt)}–{clock(curse.endAt)} · {curseMinutes(curse)} min, not ranked
      </div>
      {listed && (
        <div className="hint">
          Fastest to clear: {listed.fastest} min to {NAME.get(listed.place) ?? listed.place} ({listed.via}) · took {listed.took} min
          {lost ? ` · ${lost} min lost` : ' · no time lost'}
        </div>
      )}
      {hind && (
        <div className="hint">
          Hindsight: {hind.fastest} min to {NAME.get(hind.place) ?? hind.place}
          {listed && hind.fastest < listed.fastest ? ` (${listed.fastest - hind.fastest} min faster, not counted)` : ' (not counted)'}
        </div>
      )}
    </li>
  )
}

function PlaceList({ ids, options, onChange }: { ids: string[]; options: Station[]; onChange: (ids: string[]) => void }) {
  return (
    <div className="review-places">
      {ids.map((id) => (
        <span key={id} className="tag">
          {NAME.get(id) ?? id}{' '}
          <button type="button" aria-label={`Remove ${NAME.get(id) ?? id}`} onClick={() => onChange(ids.filter((x) => x !== id))}>
            ×
          </button>
        </span>
      ))}
      <StationSelect value={undefined} options={options.filter((s) => !ids.includes(s.id))} onChange={(v) => v && onChange([...ids, v])} />
    </div>
  )
}

// Curses entered after the game: a window is all that's needed; places are optional.
function CurseEditor({
  curses,
  options,
  defaultAt,
  onChange,
}: {
  curses: ReviewCurse[]
  options: Station[]
  defaultAt: number
  onChange: (next: ReviewCurse[]) => void
}) {
  const set = (id: string, patch: Partial<ReviewCurse>) => onChange(curses.map((c) => (c.id === id ? { ...c, ...patch } : c)))
  return (
    <div className="review-curses">
      <h3>Curses</h3>
      <p className="hint">
        The window between cast and cleared is curse time: nothing in it is ranked. Places where it could be cleared are
        optional; with them, the trip is checked against the fastest one. Hindsight places are only a side note.
      </p>
      {curses.map((c) => (
        <div key={c.id} className="review-curse">
          <div className="row">
            <label>Curse</label>
            <input value={c.name} placeholder="e.g. Planespotter" onChange={(e) => set(c.id, { name: e.target.value })} />
          </div>
          <div className="row">
            <label>Cast</label>
            <input type="datetime-local" value={toLocalInput(c.startAt)} onChange={(e) => set(c.id, { startAt: fromLocalInput(e.target.value) ?? c.startAt })} />
          </div>
          <div className="row">
            <label>Cleared</label>
            <input type="datetime-local" value={toLocalInput(c.endAt)} onChange={(e) => set(c.id, { endAt: fromLocalInput(e.target.value) ?? c.endAt })} />
          </div>
          <div className="row">
            <label>Seekers were at</label>
            <StationSelect value={c.fromStation} options={options} onChange={(v) => set(c.id, { fromStation: v })} />
          </div>
          <p className="hint">Leave blank to use the last question's spot before the cast.</p>
          <div className="row">
            <label>Could clear at</label>
            <PlaceList ids={c.clearAt ?? []} options={options} onChange={(ids) => set(c.id, { clearAt: ids })} />
          </div>
          <div className="row">
            <label>Hindsight places</label>
            <PlaceList ids={c.hindsightAt ?? []} options={options} onChange={(ids) => set(c.id, { hindsightAt: ids })} />
          </div>
          <button type="button" onClick={() => onChange(curses.filter((x) => x.id !== c.id))}>
            Remove curse
          </button>
        </div>
      ))}
      <button
        type="button"
        onClick={() =>
          onChange([...curses, { id: `curse-${Date.now().toString(36)}`, name: '', startAt: defaultAt, endAt: defaultAt + 15 * 60_000 }])
        }
      >
        Add curse
      </button>
    </div>
  )
}
