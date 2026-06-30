import { Fragment, useEffect, useMemo, useState } from 'react'
import MapView from './components/MapView'
import QuestionForm from './components/QuestionForm'
import { applyFilters } from './lib/elimination'
import { describeRecord } from './lib/describe'
import { loadGame, saveGame, emptyGame } from './lib/storage'
import { SYSTEM_COLORS, SYSTEM_ORDER, WEEKEND_EXCLUDED_LINES } from './lib/style'
import { ELIGIBLE_HEADWAY_MIN, SIZE_PARAMS } from './data/questionSets'
import { rewardForKind, questionGroupKey } from './data/questions'
import { POI_CATEGORIES, POI_BY_CATEGORY } from './lib/poi'
import type { RenderPoi } from './lib/poi'
import type { Annotation, DayType, GameState, LatLng, QuestionRecord, Station, UnitSystem } from './types'
import rawStations from './data/stations.json'

const STATIONS = rawStations as unknown as Station[]

type Tab = 'ask' | 'history' | 'suspects' | 'poi' | 'legend'
type StationView = 'normal' | 'faded' | 'hidden'

// the agency a station is filed under = the first system in canonical order
const primarySystem = (s: Station) =>
  SYSTEM_ORDER.find((sys) => s.systems.includes(sys)) ?? s.systems[0] ?? '—'

// which agency a line belongs to (line labels are prefixed by their agency)
const agencyOfLine = (line: string) =>
  SYSTEM_ORDER.find((sys) => line.startsWith(sys)) ?? '—'

interface LineGroup {
  line: string
  stations: Station[]
}
interface AgencyGroup {
  agency: string
  count: number // unique stations served by the agency
  lines: LineGroup[]
}

// Group a station list by agency then by line. Interlined stations serve more
// than one line, so a station is listed under EVERY line it serves (it can
// appear in several line groups). The agency count is the number of UNIQUE
// stations on that agency, so it can be smaller than the sum of its lines.
function groupByAgencyLine(list: Station[]): AgencyGroup[] {
  const byAgency = new Map<string, { unique: Set<string>; lines: Map<string, Station[]> }>()
  const ensure = (ag: string) => {
    if (!byAgency.has(ag)) byAgency.set(ag, { unique: new Set(), lines: new Map() })
    return byAgency.get(ag)!
  }
  for (const s of list) {
    if (s.lines.length === 0) {
      const ag = primarySystem(s)
      const e = ensure(ag)
      e.unique.add(s.id)
      if (!e.lines.has('—')) e.lines.set('—', [])
      e.lines.get('—')!.push(s)
      continue
    }
    for (const line of s.lines) {
      const ag = agencyOfLine(line)
      const e = ensure(ag)
      e.unique.add(s.id)
      if (!e.lines.has(line)) e.lines.set(line, [])
      e.lines.get(line)!.push(s)
    }
  }
  const agencyRank = (a: string) => {
    const i = SYSTEM_ORDER.indexOf(a)
    return i < 0 ? SYSTEM_ORDER.length : i
  }
  return [...byAgency.keys()]
    .sort((a, b) => agencyRank(a) - agencyRank(b) || a.localeCompare(b))
    .map((agency) => {
      const { unique, lines: byLine } = byAgency.get(agency)!
      const lines = [...byLine.keys()]
        .sort((a, b) => a.localeCompare(b))
        .map((line) => ({
          line,
          stations: byLine.get(line)!.slice().sort((a, b) => a.name.localeCompare(b.name)),
        }))
      return { agency, count: unique.size, lines }
    })
}

export default function App() {
  const [game, setGame] = useState<GameState>(() => loadGame())
  const [lastClick, setLastClick] = useState<LatLng | null>(null)
  const [tab, setTab] = useState<Tab>('ask')
  const [showEliminated, setShowEliminated] = useState(true)
  const [satellite, setSatellite] = useState(false)
  const [sheetOpen, setSheetOpen] = useState(false)
  const [suspectSort, setSuspectSort] = useState<'name' | 'agency'>('name')
  const [suspectQuery, setSuspectQuery] = useState('')
  const [poiEnabled, setPoiEnabled] = useState<Set<string>>(
    () => new Set(POI_CATEGORIES.map((c) => c.key)),
  )
  // how stations are shown while the POI tab is open, so POI dots can stand out
  const [stationView, setStationView] = useState<StationView>('normal')
  const [poiQuery, setPoiQuery] = useState('')
  // bump nonce so the map re-centers even when the same station is clicked twice
  const [focusTarget, setFocusTarget] = useState<{ station: Station; nonce: number } | null>(null)
  const focusStation = (s: Station) => {
    setFocusTarget({ station: s, nonce: Date.now() })
    setSheetOpen(false) // reveal the map on mobile (bottom sheet)
  }

  useEffect(() => saveGame(game), [game])

  const update = (patch: Partial<GameState>) => setGame((g) => ({ ...g, ...patch }))

  // A station is a valid hiding spot only if it's served at least hourly (the
  // canonical Jet Lag rule, flat across all sizes).
  const base = useMemo(
    () => STATIONS.filter((s) => s.headwayMin[game.dayType] <= ELIGIBLE_HEADWAY_MIN),
    [game.dayType],
  )

  // the single station the seeker has locked endgame onto (if any)
  const endgameStation = useMemo(
    () => (game.endgame ? base.find((s) => s.id === game.endgame) ?? null : null),
    [game.endgame, base],
  )
  const hidingRadiusMi = SIZE_PARAMS[game.gameSize].hidingZoneRadiusMi

  const { remaining, eliminated } = useMemo(() => {
    if (endgameStation) {
      return {
        remaining: [endgameStation],
        eliminated: base.filter((s) => s.id !== endgameStation.id),
      }
    }
    const res = applyFilters(base, game.questions)
    const manual = new Set(game.manualEliminated)
    const remain = res.remaining.filter((s) => !manual.has(s.id))
    const remainIds = new Set(remain.map((s) => s.id))
    const elim = base.filter((s) => !remainIds.has(s.id))
    return { remaining: remain, eliminated: elim }
  }, [base, game.questions, game.manualEliminated, endgameStation])

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

  // Repeat-question reward: the nth time the SAME question is asked, the hider's
  // reward is multiplied by n. "Same question" = same kind, except radar and
  // thermometer also depend on their distance (a 5mi radar and a 10mi radar are
  // different questions; two 5mi radars are the same). Map each record id -> its
  // 1-based ask ordinal within its group (in ask order).
  const askOrdinal = useMemo(() => {
    const m = new Map<string, number>()
    const counts = new Map<string, number>()
    game.questions
      .slice()
      .sort((a, b) => a.createdAt - b.createdAt)
      .forEach((q) => {
        const key = questionGroupKey(q.kind, q.params)
        const n = (counts.get(key) ?? 0) + 1
        counts.set(key, n)
        m.set(q.id, n)
      })
    return m
  }, [game.questions])

  // Per-group counts of questions already asked, so the Ask form can preview the
  // scaled cost of asking a given question one more time (n = count + 1).
  const askGroupCounts = useMemo(() => {
    const m = new Map<string, number>()
    for (const q of game.questions) {
      const key = questionGroupKey(q.kind, q.params)
      m.set(key, (m.get(key) ?? 0) + 1)
    }
    return m
  }, [game.questions])

  const pickedPoints = useMemo(() => {
    const pts: { label: string; point: LatLng; color: string }[] = []
    for (const r of game.questions) {
      if (!r.active || r.vetoed) continue
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

  // POIs to draw: every enabled category, name-filtered by the POI search box.
  const pois = useMemo<RenderPoi[]>(() => {
    const q = poiQuery.trim().toLowerCase()
    const out: RenderPoi[] = []
    for (const cat of POI_CATEGORIES) {
      if (!poiEnabled.has(cat.key)) continue
      for (const p of POI_BY_CATEGORY[cat.key]) {
        if (q && !p.name.toLowerCase().includes(q)) continue
        out.push({ ...p, categoryKey: cat.key, label: cat.label, color: cat.color })
      }
    }
    return out
  }, [poiEnabled, poiQuery])

  // Per-category counts after the search filter (shown next to each toggle).
  const poiFilteredCounts = useMemo<Record<string, number>>(() => {
    const q = poiQuery.trim().toLowerCase()
    const m: Record<string, number> = {}
    for (const cat of POI_CATEGORIES) {
      m[cat.key] = q
        ? POI_BY_CATEGORY[cat.key].filter((p) => p.name.toLowerCase().includes(q)).length
        : POI_BY_CATEGORY[cat.key].length
    }
    return m
  }, [poiQuery])

  // Only overlay POIs while the POI tab is open, so the elimination view stays clean.
  const visiblePois = tab === 'poi' ? pois : []

  function togglePoi(key: string) {
    setPoiEnabled((s) => {
      const n = new Set(s)
      if (n.has(key)) n.delete(key)
      else n.add(key)
      return n
    })
  }

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

  const remainingLi = (s: Station) => (
    <li key={s.id} className={starredSet.has(s.id) ? 'starred' : ''}>
      <button className={'star ' + (starredSet.has(s.id) ? 'on' : '')} onClick={() => toggleStar(s.id)}>★</button>
      <span className="dot" style={{ background: SYSTEM_COLORS[s.systems[0]] ?? '#444' }} />
      <button className="sname" onClick={() => focusStation(s)} title="Show on map">{s.name}</button>
      <span className="ssys">{s.systems.join('·')}</span>
      <button className="x" onClick={() => toggleManual(s.id)} title="eliminate">✕</button>
    </li>
  )
  const eliminatedLi = (s: Station) => (
    <li key={s.id} className="elim">
      <span className="star-spacer" />
      <span className="dot" style={{ background: '#9aa0a6' }} />
      <button className="sname" onClick={() => focusStation(s)} title="Show on map">{s.name}</button>
      <span className="ssys">{s.systems.join('·')}</span>
      {manualSet.has(s.id) ? (
        <button className="restore" onClick={() => toggleManual(s.id)} title="restore">↩</button>
      ) : (
        <span className="x-spacer" title="eliminated by a question" />
      )}
    </li>
  )
  const groupedLis = (list: Station[], row: (s: Station) => JSX.Element) =>
    groupByAgencyLine(list).map((g) => (
      <Fragment key={g.agency}>
        <li className="sgroup agency">
          <span className="dot" style={{ background: SYSTEM_COLORS[g.agency] ?? '#444' }} />
          {g.agency} ({g.count})
        </li>
        {g.lines.map((l) => (
          <Fragment key={l.line}>
            <li className="sgroup line">{l.line} ({l.stations.length})</li>
            {l.stations.map(row)}
          </Fragment>
        ))}
      </Fragment>
    ))
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
  // Move every annotation point sitting at exactly `from` to `to`. Snapping
  // copies coords verbatim, so points dropped on the same spot are bit-identical
  // and drag together — a shared point stays shared.
  function movePoint(from: LatLng, to: LatLng) {
    if (from.lat === to.lat && from.lon === to.lon) return
    setGame((g) => ({
      ...g,
      annotations: g.annotations.map((a): Annotation => {
        if (a.type === 'circle') {
          return a.lat === from.lat && a.lon === from.lon ? { ...a, lat: to.lat, lon: to.lon } : a
        }
        let na = a
        if (na.aLat === from.lat && na.aLon === from.lon) na = { ...na, aLat: to.lat, aLon: to.lon }
        if (na.bLat === from.lat && na.bLon === from.lon) na = { ...na, bLat: to.lat, bLon: to.lon }
        return na
      }),
    }))
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
          <label className="chk">
            <input type="checkbox" checked={showEliminated} onChange={(e) => setShowEliminated(e.target.checked)} />
            show eliminated
          </label>
          <label className="chk">
            <input type="checkbox" checked={satellite} onChange={(e) => setSatellite(e.target.checked)} />
            satellite
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
            satellite={satellite}
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
            onMovePoint={movePoint}
            onClearAnnotations={clearAnnotations}
            endgameStation={endgameStation}
            hidingRadiusMi={hidingRadiusMi}
            focusTarget={focusTarget}
            onStartEndgame={(id) => update({ endgame: id })}
            onExitEndgame={() => update({ endgame: null })}
            pois={visiblePois}
            stationView={tab === 'poi' ? stationView : 'normal'}
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
            {(['ask', 'history', 'suspects', 'poi', 'legend'] as Tab[]).map((t) => (
              <button key={t} className={tab === t ? 'on' : ''} onClick={() => setTab(t)}>
                {t === 'ask'
                  ? 'Ask'
                  : t === 'history'
                    ? `History (${game.questions.length})`
                    : t === 'suspects'
                      ? `Suspects (${remaining.length})`
                      : t === 'poi'
                        ? 'POI'
                        : 'Legend'}
              </button>
            ))}
          </nav>

          {tab === 'ask' && (
            <div className="panel">
              <p className="hint">Paste coordinates (lat, lon) for each seeker location — most accurate. Clicking the map drops a point you can fall back on.</p>
              <QuestionForm
                lastClick={lastClick}
                units={game.units}
                counties={counties}
                cities={cities}
                lines={lines}
                airports={airports}
                onSubmit={addQuestion}
                onPreview={setLastClick}
                askGroupCounts={askGroupCounts}
              />
            </div>
          )}

          {tab === 'history' && (
            <div className="panel">
              {game.questions.length === 0 && <p className="hint">No questions logged yet.</p>}
              <ul className="qlist">
                {game.questions.map((q) => (
                  <li key={q.id} className={`${q.active ? '' : 'off'}${q.vetoed ? ' vetoed' : ''}`}>
                    <div className="qtext">
                      {describeRecord(q, game.units)}
                      {!q.eliminates && <span className="tag">info</span>}
                      {q.vetoed && <span className="tag veto">vetoed</span>}
                    </div>
                    {!q.vetoed &&
                      (() => {
                        const n = askOrdinal.get(q.id) ?? 1
                        return (
                          <div className="qreward">
                            Hider reward: {rewardForKind(q.kind, n)}
                            {n > 1 && (
                              <span className="qreward-mult">
                                {' '}(×{n} — {n}
                                {ordinalSuffix(n)} time asked)
                              </span>
                            )}
                          </div>
                        )
                      })()}
                    {q.note && <div className="qnote">{q.note}</div>}
                    <div className="qactions">
                      {q.eliminates && !q.vetoed && (
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
              <div className="sortbar">
                <label htmlFor="suspect-sort">Sort</label>
                <select
                  id="suspect-sort"
                  value={suspectSort}
                  onChange={(e) => setSuspectSort(e.target.value as 'name' | 'agency')}
                >
                  <option value="name">by name</option>
                  <option value="agency">by agency → line</option>
                </select>
              </div>
              <div className="searchbar">
                <input
                  type="search"
                  className="suspect-search"
                  placeholder="Search name, line, agency…"
                  value={suspectQuery}
                  onChange={(e) => setSuspectQuery(e.target.value)}
                />
                {suspectQuery && (
                  <button className="search-clear" aria-label="Clear search" onClick={() => setSuspectQuery('')}>
                    ✕
                  </button>
                )}
              </div>
              {(() => {
                const q = suspectQuery.trim().toLowerCase()
                const matches = (s: Station) =>
                  !q ||
                  [s.name, ...s.aka, ...s.systems, ...s.lines.map((l) => l.replace(/\s*\([^)]*\)/g, '')), s.city ?? '', s.county ?? '']
                    .join(' ')
                    .toLowerCase()
                    .includes(q)
                const fRemaining = remaining.filter(matches)
                const fEliminated = eliminated.filter(matches)
                if (q && fRemaining.length + fEliminated.length === 0) {
                  return <p className="hint">No stations match “{suspectQuery}”.</p>
                }
                return (
                  <ul className="slist">
                    {suspectSort === 'name' ? (
                      <>
                        {fRemaining
                          .slice()
                          .sort((a, b) => Number(starredSet.has(b.id)) - Number(starredSet.has(a.id)) || a.name.localeCompare(b.name))
                          .map(remainingLi)}
                        {fEliminated.slice().sort((a, b) => a.name.localeCompare(b.name)).map(eliminatedLi)}
                      </>
                    ) : (
                      <>
                        {groupedLis(fRemaining, remainingLi)}
                        {fEliminated.length > 0 && (
                          <li className="sgroup elimhdr">Eliminated ({fEliminated.length})</li>
                        )}
                        {groupedLis(fEliminated, eliminatedLi)}
                      </>
                    )}
                  </ul>
                )
              })()}
            </div>
          )}

          {tab === 'poi' && (
            <div className="panel">
              <p className="hint">
                Reference layer for composing Tentacles / Matching / Measuring questions. Toggle
                categories and search by name; dots show on the map while this tab is open. A place
                counts if it has the Google Maps category icon and ≥5 reviews.
              </p>
              <div className="searchbar">
                <input
                  type="search"
                  className="suspect-search"
                  placeholder="Search POI name…"
                  value={poiQuery}
                  onChange={(e) => setPoiQuery(e.target.value)}
                />
                {poiQuery && (
                  <button className="search-clear" aria-label="Clear search" onClick={() => setPoiQuery('')}>
                    ✕
                  </button>
                )}
              </div>
              <div className="poi-actions">
                <button onClick={() => setPoiEnabled(new Set(POI_CATEGORIES.map((c) => c.key)))}>
                  Show all
                </button>
                <button onClick={() => setPoiEnabled(new Set())}>Hide all</button>
                <span className="poi-total">{pois.length} shown</span>
              </div>
              <div className="poi-stations">
                <span className="poi-stations-label">Stations</span>
                <div className="seg">
                  {(['normal', 'faded', 'hidden'] as StationView[]).map((v) => (
                    <button
                      key={v}
                      className={stationView === v ? 'on' : ''}
                      onClick={() => setStationView(v)}
                    >
                      {v === 'normal' ? 'Normal' : v === 'faded' ? 'Faded' : 'Hidden'}
                    </button>
                  ))}
                </div>
              </div>
              <ul className="poi-list">
                {POI_CATEGORIES.map((cat) => (
                  <li key={cat.key}>
                    <label className="poi-row">
                      <input
                        type="checkbox"
                        checked={poiEnabled.has(cat.key)}
                        onChange={() => togglePoi(cat.key)}
                      />
                      <span className="dot" style={{ background: cat.color }} />
                      <span className="poi-name">{cat.label}</span>
                      <span className="poi-count">{poiFilteredCounts[cat.key]}</span>
                    </label>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {tab === 'legend' && (
            <div className="panel legend">
              <h3>About this map</h3>
              <p className="info">
                <span className="info-tag">{game.gameSize}</span> game ({STATIONS.length} stations,
                auto-set from station count).
              </p>
              <p className="info">
                <strong>Eligibility:</strong> hiders' stations must be served at least once an hour
                (≤{ELIGIBLE_HEADWAY_MIN} min between trains). Eligible —{' '}
                weekday {STATIONS.filter((s) => s.headwayMin.wd <= ELIGIBLE_HEADWAY_MIN).length},{' '}
                weekend {STATIONS.filter((s) => s.headwayMin.we <= ELIGIBLE_HEADWAY_MIN).length}{' '}
                of {STATIONS.length}.
              </p>
              <h3>Satellite imagery</h3>
              <p className="info">
                The <strong>satellite</strong> layer is{' '}
                <a
                  href="https://www.arcgis.com/home/item.html?id=10df2279f9684e4a9f6a7f08febac2a9"
                  target="_blank"
                  rel="noreferrer"
                >
                  Esri World Imagery
                </a>{' '}
                (Maxar / aerial), clipped to the play-area counties. It's a mosaic,
                so the capture date varies by location — in the Bay Area it's
                generally late 2024–2025 (e.g. San Francisco Aug 2025, Oakland Jun
                2025, San Jose Nov 2024). Check the exact date anywhere with{' '}
                <a href="https://livingatlas.arcgis.com/wayback/" target="_blank" rel="noreferrer">
                  Esri Wayback
                </a>
                .
              </p>
              <h3>Systems</h3>
              {SYSTEM_ORDER.map((sys) => (
                <div key={sys} className="legrow">
                  <span className="dot" style={{ background: SYSTEM_COLORS[sys] }} />
                  {sys} ({STATIONS.filter((s) => s.systems.includes(sys)).length})
                </div>
              ))}
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

function ordinalSuffix(n: number): string {
  const t = n % 100
  if (t >= 11 && t <= 13) return 'th'
  switch (n % 10) {
    case 1:
      return 'st'
    case 2:
      return 'nd'
    case 3:
      return 'rd'
    default:
      return 'th'
  }
}


