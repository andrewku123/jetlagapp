import { useCallback, useEffect, useMemo, useState } from 'react'
import MapView from '../components/MapView'
import { describeRecord } from '../lib/describe'
import { emptyGame, loadGame, saveGame } from '../lib/storage'
import { hidingRadiusMi } from '../lib/hidingZone'
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
import { buildTimeline, countedQuestions, remainingAt, REVIEW_CUTOFF_MIN, type TimelineEvent } from '../lib/reviewTimeline'
import type { LatLng, Station } from '../types'

const STATIONS = stationsData as Station[]
const NAME = new Map(STATIONS.map((s) => [s.id, s.name]))
const noop = () => {}

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

  const first = events[0]?.at ?? round.savedAt
  const last = events[events.length - 1]?.at ?? round.savedAt
  const [t, setT] = useState(last)
  const remaining = useMemo(() => remainingAt(base, game, questions, t), [base, game, questions, t])
  const eliminated = useMemo(() => {
    const keep = new Set(remaining.map((s) => s.id))
    return base.filter((s) => !keep.has(s.id))
  }, [base, remaining])
  const records = useMemo(() => questions.filter((q) => q.createdAt <= t).map((q) => ({ ...q, active: true })), [questions, t])
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
          <div className="review-slider">
            <input
              type="range"
              min={first}
              max={last}
              step={1000}
              value={t}
              onChange={(e) => setT(Number(e.target.value))}
              aria-label="Replay time"
              disabled={events.length === 0}
            />
            <span className="hint">{clock(t)}</span>
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
                Move ranks (#X of N, minutes slower than best) come once game-day travel times are added. Tap a row to
                replay the map to that moment.
              </p>
              {events.length === 0 && <p className="hint">Nothing was logged in this round.</p>}
              <ul className="qlist review-timeline">
                {events.map((ev, i) => (
                  <TimelineRow key={i} ev={ev} units={game.units} on={ev.at <= t && (events[i + 1]?.at ?? Infinity) > t} onPick={() => setT(ev.at)} />
                ))}
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
              <div className="row">
                <label>Hider found</label>
                <input type="datetime-local" value={toLocalInput(setup.foundAt)} onChange={(e) => edit({ foundAt: fromLocalInput(e.target.value) })} />
              </div>
              <button className="primary" onClick={() => void save()}>
                Save setup
              </button>
              {saveMsg && <p className="hint">{saveMsg}</p>}
            </div>
          )}
          {tab === 'cleanup' && (
            <div className="panel">
              <p className="hint">Untick records the review should skip. This only changes the review, never the saved game.</p>
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

function TimelineRow({ ev, units, on, onPick }: { ev: TimelineEvent; units: 'imperial' | 'metric'; on: boolean; onPick: () => void }) {
  const text =
    ev.kind === 'question'
      ? describeRecord(ev.record, units)
      : `${ev.kind === 'out' ? 'Crossed out' : 'Put back'} ${NAME.get(ev.stationId) ?? ev.stationId}`
  const photo = ev.kind === 'question' && ev.record.kind === 'photo'
  return (
    <li className={on ? 'review-on' : ''} onClick={onPick}>
      <div className="qtext">
        <span className="review-time">{clock(ev.at)}</span> {text}
        {photo && <span className="tag">unranked</span>}
        {ev.kind === 'question' && ev.record.curse && <span className="tag curse">curse info</span>}
      </div>
      <div className="qreward">
        {ev.before === ev.left ? `${ev.left} left` : `${ev.before} → ${ev.left} left`}
        {ev.keptHider === false && <span className="tag veto">ruled out hider's station</span>}
      </div>
    </li>
  )
}
