import { useEffect, useMemo, useState } from 'react'
import MapView from './components/MapView'
import QuestionForm from './components/QuestionForm'
import { applyFilters } from './lib/elimination'
import { describeRecord } from './lib/describe'
import { loadGame, saveGame, emptyGame } from './lib/storage'
import { SYSTEM_COLORS, SYSTEM_ORDER, WEEKEND_EXCLUDED_LINES } from './lib/style'
import { ELIGIBLE_HEADWAY_MIN } from './data/questionSets'
import type { Annotation, DayType, GameState, LatLng, QuestionRecord, Station, UnitSystem } from './types'
import rawStations from './data/stations.json'

const STATIONS = rawStations as unknown as Station[]

type Tab = 'ask' | 'history' | 'suspects' | 'legend'

export default function App() {
  const [game, setGame] = useState<GameState>(() => loadGame())
  const [lastClick, setLastClick] = useState<LatLng | null>(null)
  const [tab, setTab] = useState<Tab>('ask')
  const [showEliminated, setShowEliminated] = useState(true)
  const [sheetOpen, setSheetOpen] = useState(false)

  useEffect(() => saveGame(game), [game])

  const update = (patch: Partial<GameState>) => setGame((g) => ({ ...g, ...patch }))

  // A station is a valid hiding spot only if it's served at least hourly (the
  // canonical Jet Lag rule, flat across all sizes).
  const base = useMemo(
    () => STATIONS.filter((s) => s.headwayMin[game.dayType] <= ELIGIBLE_HEADWAY_MIN),
    [game.dayType],
  )

  const { remaining, eliminated } = useMemo(() => {
    const res = applyFilters(base, game.questions)
    const manual = new Set(game.manualEliminated)
    const remain = res.remaining.filter((s) => !manual.has(s.id))
    const remainIds = new Set(remain.map((s) => s.id))
    const elim = base.filter((s) => !remainIds.has(s.id))
    return { remaining: remain, eliminated: elim }
  }, [base, game.questions, game.manualEliminated])

  const counties = useMemo(
    () => uniqSorted(STATIONS.map((s) => s.county).filter(Boolean) as string[]),
    [],
  )
  const cities = useMemo(
    () => uniqSorted(STATIONS.map((s) => s.city).filter(Boolean) as string[]),
    [],
  )
  const lines = useMemo(() => {
    const all = uniqSorted(STATIONS.flatMap((s) => s.lines))
    return game.dayType === 'we'
      ? all.filter((l) => !WEEKEND_EXCLUDED_LINES.includes(l))
      : all
  }, [game.dayType])
  const airports = useMemo(
    () => uniqSorted(STATIONS.map((s) => s.nearestAirport)),
    [],
  )

  const starredSet = useMemo(() => new Set(game.starred), [game.starred])
  const manualSet = useMemo(() => new Set(game.manualEliminated), [game.manualEliminated])

  const pickedPoints = useMemo(() => {
    const pts: { label: string; point: LatLng; color: string }[] = []
    for (const r of game.questions) {
      if (!r.active) continue
      if (r.kind === 'thermometer') {
        pts.push({ label: 'Thermo start', point: { lat: Number(r.params.fromLat), lon: Number(r.params.fromLon) }, color: '#2563eb' })
        pts.push({ label: 'Thermo end', point: { lat: Number(r.params.toLat), lon: Number(r.params.toLon) }, color: '#7c3aed' })
      }
      if (r.kind === 'measure-airport') {
        pts.push({ label: 'Measure (airport)', point: { lat: Number(r.params.fromLat), lon: Number(r.params.fromLon) }, color: '#0891b2' })
      }
    }
    if (lastClick) pts.push({ label: 'Last click', point: lastClick, color: '#111' })
    return pts
  }, [game.questions, lastClick])

  function addQuestion(r: QuestionRecord) {
    update({ questions: [r, ...game.questions] })
    setTab('history')
    setSheetOpen(true)
  }
  function toggleActive(id: string) {
    update({ questions: game.questions.map((q) => (q.id === id ? { ...q, active: !q.active } : q)) })
  }
  function deleteQuestion(id: string) {
    update({ questions: game.questions.filter((q) => q.id !== id) })
  }
  function toggleStar(id: string) {
    update({ starred: starredSet.has(id) ? game.starred.filter((x) => x !== id) : [...game.starred, id] })
  }
  function toggleManual(id: string) {
    const set = new Set(game.manualEliminated)
    if (set.has(id)) set.delete(id)
    else set.add(id)
    update({ manualEliminated: [...set] })
  }
  function resetGame() {
    if (confirm('Clear all questions, eliminations and notes?')) setGame({ ...emptyGame })
  }
  function addAnnotation(a: Annotation) {
    update({ annotations: [...game.annotations, a] })
  }
  function deleteAnnotation(id: string) {
    update({ annotations: game.annotations.filter((a) => a.id !== id) })
  }
  function updateAnnotation(id: string, patch: Partial<Annotation>) {
    update({
      annotations: game.annotations.map((a) => (a.id === id ? ({ ...a, ...patch } as Annotation) : a)),
    })
  }
  function clearAnnotations() {
    update({ annotations: [] })
  }

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">🕵️ Bay Area Hide &amp; Seek</div>
        <div className="counts">
          <strong>{remaining.length}</strong> of {base.length} possible
        </div>
        <div className="toggles">
          <DayToggle value={game.dayType} onChange={(d) => update({ dayType: d })} />
          <UnitsToggle value={game.units} onChange={(u) => update({ units: u })} />
          <span
            className="size-badge"
            title={`Game size is auto-set from the map (${STATIONS.length} stations). Only stations served at least once an hour (≤${ELIGIBLE_HEADWAY_MIN} min) count as valid hiding spots.`}
          >
            {game.gameSize} · ≥hourly
          </span>
          <label className="chk">
            <input type="checkbox" checked={showEliminated} onChange={(e) => setShowEliminated(e.target.checked)} />
            show eliminated
          </label>
          <button onClick={resetGame}>Reset</button>
        </div>
      </header>

      <div className={`body${sheetOpen ? ' sheet-open' : ''}`}>
        <div className="mapwrap">
          <MapView
            remaining={remaining}
            eliminated={eliminated}
            showEliminated={showEliminated}
            starred={starredSet}
            manualEliminated={manualSet}
            units={game.units}
            onPickLocation={setLastClick}
            onToggleStar={toggleStar}
            onToggleEliminate={toggleManual}
            records={game.questions}
            pickedPoints={pickedPoints}
            annotations={game.annotations}
            onAddAnnotation={addAnnotation}
            onDeleteAnnotation={deleteAnnotation}
            onUpdateAnnotation={updateAnnotation}
            onClearAnnotations={clearAnnotations}
          />
        </div>

        <button
          className="sheet-toggle"
          onClick={() => setSheetOpen((v) => !v)}
          aria-label={sheetOpen ? 'Hide controls' : 'Show controls'}
        >
          {sheetOpen ? '▾ Map' : `▴ Controls · ${remaining.length}`}
        </button>

        <aside className="sidebar">
          <button className="sheet-grab" onClick={() => setSheetOpen((v) => !v)} aria-label="Toggle controls" />
          <nav className="tabs">
            {(['ask', 'history', 'suspects', 'legend'] as Tab[]).map((t) => (
              <button key={t} className={tab === t ? 'on' : ''} onClick={() => setTab(t)}>
                {t === 'ask' ? 'Ask' : t === 'history' ? `History (${game.questions.length})` : t === 'suspects' ? `Suspects (${remaining.length})` : 'Legend'}
              </button>
            ))}
          </nav>

          {tab === 'ask' && (
            <div className="panel">
              <p className="hint">Click the map to drop a point, then use it as a seeker location.</p>
              <QuestionForm
                lastClick={lastClick}
                units={game.units}
                counties={counties}
                cities={cities}
                lines={lines}
                airports={airports}
                onSubmit={addQuestion}
              />
            </div>
          )}

          {tab === 'history' && (
            <div className="panel">
              {game.questions.length === 0 && <p className="hint">No questions logged yet.</p>}
              <ul className="qlist">
                {game.questions.map((q) => (
                  <li key={q.id} className={q.active ? '' : 'off'}>
                    <div className="qtext">
                      {describeRecord(q, game.units)}
                      {!q.eliminates && <span className="tag">info</span>}
                    </div>
                    {q.note && <div className="qnote">{q.note}</div>}
                    <div className="qactions">
                      {q.eliminates && (
                        <button onClick={() => toggleActive(q.id)}>{q.active ? 'Disable' : 'Enable'}</button>
                      )}
                      <button onClick={() => deleteQuestion(q.id)}>Delete</button>
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {tab === 'suspects' && (
            <div className="panel">
              <p className="hint">
                {remaining.length} of {base.length} still possible. Click ★ to flag (pins to top), ✕ to eliminate by hand.
              </p>
              <ul className="slist">
                {remaining
                  .slice()
                  .sort((a, b) => Number(starredSet.has(b.id)) - Number(starredSet.has(a.id)) || a.name.localeCompare(b.name))
                  .map((s) => (
                    <li key={s.id} className={starredSet.has(s.id) ? 'starred' : ''}>
                      <button className={'star ' + (starredSet.has(s.id) ? 'on' : '')} onClick={() => toggleStar(s.id)}>★</button>
                      <span className="dot" style={{ background: SYSTEM_COLORS[s.systems[0]] ?? '#444' }} />
                      <span className="sname">{s.name}</span>
                      <span className="ssys">{s.systems.join('·')}</span>
                      <button className="x" onClick={() => toggleManual(s.id)} title="eliminate">✕</button>
                    </li>
                  ))}
                {eliminated
                  .slice()
                  .sort((a, b) => a.name.localeCompare(b.name))
                  .map((s) => {
                    const manual = manualSet.has(s.id)
                    return (
                      <li key={s.id} className="elim">
                        <span className="star-spacer" />
                        <span className="dot" style={{ background: '#9aa0a6' }} />
                        <span className="sname">{s.name}</span>
                        <span className="ssys">{s.systems.join('·')}</span>
                        {manual ? (
                          <button className="restore" onClick={() => toggleManual(s.id)} title="restore">↩</button>
                        ) : (
                          <span className="x-spacer" title="eliminated by a question" />
                        )}
                      </li>
                    )
                  })}
              </ul>
            </div>
          )}

          {tab === 'legend' && (
            <div className="panel legend">
              <h3>Systems</h3>
              {SYSTEM_ORDER.map((sys) => (
                <div key={sys} className="legrow">
                  <span className="dot" style={{ background: SYSTEM_COLORS[sys] }} />
                  {sys} ({STATIONS.filter((s) => s.systems.includes(sys)).length})
                </div>
              ))}
              <p className="hint">
                Total dataset: {STATIONS.length} stations. Weekday eligible:{' '}
                {STATIONS.filter((s) => s.service.wd.served && s.service.wd.hourly).length}; weekend:{' '}
                {STATIONS.filter((s) => s.service.we.served && s.service.we.hourly).length}.
              </p>
              <p className="hint">
                Auto-elimination supports Radar, Thermometer, Matching (county / city / airport / line / name length)
                and Measuring (airport / sea level). POI-based questions (parks, hospitals, museums, etc.) and
                Tentacles are coming next.
              </p>
            </div>
          )}
        </aside>
      </div>
    </div>
  )
}

function DayToggle({ value, onChange }: { value: DayType; onChange: (d: DayType) => void }) {
  return (
    <div className="seg">
      <button className={value === 'wd' ? 'on' : ''} onClick={() => onChange('wd')}>Weekday</button>
      <button className={value === 'we' ? 'on' : ''} onClick={() => onChange('we')}>Weekend</button>
    </div>
  )
}

function UnitsToggle({ value, onChange }: { value: UnitSystem; onChange: (u: UnitSystem) => void }) {
  return (
    <div className="seg">
      <button className={value === 'imperial' ? 'on' : ''} onClick={() => onChange('imperial')}>mi/ft</button>
      <button className={value === 'metric' ? 'on' : ''} onClick={() => onChange('metric')}>km/m</button>
    </div>
  )
}

function uniqSorted(arr: string[]): string[] {
  return [...new Set(arr)].sort((a, b) => a.localeCompare(b))
}
