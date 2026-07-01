import { useState } from 'react'
import type { LatLng, QuestionKind, QuestionRecord, UnitSystem } from '../types'
import { QUESTION_CATALOG, RADAR_OPTIONS, THERMOMETER_OPTIONS, questionGroupKey, scaleCards } from '../data/questions'
import type { QuestionMeta } from '../data/questions'
import { KM_PER_MILE, FEET_PER_METER, parseLatLng, formatDistance } from '../lib/geo'
import { QUESTION_POI_CATEGORIES, poiCategoryLabel, nearestPoi, nearestPoiMiles } from '../lib/poi'

interface Props {
  lastClick: LatLng | null
  units: UnitSystem
  counties: string[]
  cities: string[]
  lines: string[]
  airports: string[]
  onSubmit: (r: QuestionRecord) => void
  onPreview: (p: LatLng) => void
  // how many times each question group has already been asked, keyed by
  // questionGroupKey — used to preview the scaled cost of asking once more.
  askGroupCounts: Map<string, number>
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

function uid(): string {
  return 'q' + Date.now().toString(36) + Math.random().toString(36).slice(2, 6)
}

function fmt(p: LatLng | null): string {
  return p ? `${p.lat.toFixed(4)}, ${p.lon.toFixed(4)}` : '— click map —'
}

// A location picker: manual lat/lon entry (primary), with last map click as a fallback.
function CoordPicker({
  label,
  point,
  setPoint,
  lastClick,
  onPreview,
}: {
  label: string
  point: LatLng | null
  setPoint: (p: LatLng | null) => void
  lastClick: LatLng | null
  onPreview: (p: LatLng) => void
}) {
  const [text, setText] = useState('')
  const [err, setErr] = useState(false)
  function apply() {
    const p = parseLatLng(text)
    if (!p) {
      setErr(true)
      return
    }
    setErr(false)
    setText('')
    setPoint(p)
    onPreview(p)
  }
  return (
    <div className="coordpick">
      <div className="row">
        <label>{label}</label>
        <span className="coord">{fmt(point)}</span>
      </div>
      <div className="row coordin">
        <input
          className={err ? 'err' : ''}
          type="text"
          placeholder="paste lat, lon"
          value={text}
          onChange={(e) => {
            setText(e.target.value)
            setErr(false)
          }}
          onKeyDown={(e) => {
            if (e.key === 'Enter') apply()
          }}
        />
        <button onClick={apply}>Set</button>
      </div>
      <button
        className="uselast"
        disabled={!lastClick}
        onClick={() => lastClick && setPoint(lastClick)}
      >
        or use last map click
      </button>
    </div>
  )
}

export default function QuestionForm({
  lastClick,
  units,
  counties,
  cities,
  lines,
  airports,
  onSubmit,
  onPreview,
  askGroupCounts,
}: Props) {
  const metric = units === 'metric'
  const distUnit = metric ? 'km' : 'mi'
  const elevUnit = metric ? 'm' : 'ft'
  const [kind, setKind] = useState<QuestionKind>('radar')
  const meta = QUESTION_CATALOG.find((q) => q.kind === kind)!
  // category is step 1 (segmented buttons); the kind dropdown (step 2) only shows
  // for categories with more than one question.
  const categories = QUESTION_CATALOG.reduce<QuestionMeta['category'][]>(
    (acc, q) => (acc.includes(q.category) ? acc : [...acc, q.category]),
    [],
  )
  const [category, setCategory] = useState<QuestionMeta['category']>(meta.category)
  const kindsInCategory = QUESTION_CATALOG.filter((q) => q.category === category)
  function pickCategory(c: QuestionMeta['category']) {
    setCategory(c)
    const first = QUESTION_CATALOG.find((q) => q.category === c)!
    setKind(first.kind)
  }
  // strip the "Category — " prefix so the step-2 dropdown is just the specifics
  const subLabel = (label: string) => {
    const i = label.indexOf(' — ')
    return i >= 0 ? label.slice(i + 3) : label
  }

  // shared param state
  const [radius, setRadius] = useState<string>('0.5')
  const [customRadius, setCustomRadius] = useState<string>('')
  const [thermo, setThermo] = useState<string>('0.5')
  const [customThermo, setCustomThermo] = useState<string>('')
  const [yesno, setYesno] = useState<'yes' | 'no'>('yes')
  const [hotcold, setHotcold] = useState<'hotter' | 'colder'>('hotter')
  const [closefar, setClosefar] = useState<'closer' | 'further'>('closer')
  const [center, setCenter] = useState<LatLng | null>(null)
  const [ptA, setPtA] = useState<LatLng | null>(null)
  const [ptB, setPtB] = useState<LatLng | null>(null)
  const [value, setValue] = useState<string>('')
  const [poiCat, setPoiCat] = useState<string>(QUESTION_POI_CATEGORIES[0])
  const [num, setNum] = useState<string>('')
  const [building, setBuilding] = useState<string>('')
  const [floor, setFloor] = useState<string>('')
  const [floorAns, setFloorAns] = useState<'higher' | 'lower' | 'same' | 'cannot'>('higher')
  const [note, setNote] = useState<string>('')

  // The thermometer the seeker chose (converted to miles), or NaN if invalid.
  function thermoMiles(): number {
    if (thermo === 'custom') return metric ? Number(customThermo) / KM_PER_MILE : Number(customThermo)
    return Number(thermo)
  }

  function submit(vetoed = false) {
    let params: Record<string, unknown> = {}
    switch (kind) {
      case 'radar': {
        if (!center) return alert('Set the radar center (click the map or enter coordinates).')
        const radiusMiles =
          radius === 'custom'
            ? metric
              ? Number(customRadius) / KM_PER_MILE
              : Number(customRadius)
            : Number(radius)
        if (!Number.isFinite(radiusMiles) || radiusMiles <= 0)
          return alert('Enter a valid radar radius greater than 0.')
        params = { lat: center.lat, lon: center.lon, radiusMiles, answer: yesno }
        break
      }
      case 'thermometer': {
        if (!ptA || !ptB) return alert('Set both start (A) and end (B) points.')
        const tMiles = thermoMiles()
        if (!Number.isFinite(tMiles) || tMiles <= 0)
          return alert('Choose which thermometer you used (a travel distance greater than 0).')
        params = { fromLat: ptA.lat, fromLon: ptA.lon, toLat: ptB.lat, toLon: ptB.lon, thermometerMiles: tMiles, answer: hotcold }
        break
      }
      case 'measure-airport': {
        if (!center) return alert('Set your location by clicking the map.')
        params = { fromLat: center.lat, fromLon: center.lon, answer: closefar }
        break
      }
      case 'match-poi': {
        if (!center) return alert('Set your location (paste coordinates or click the map).')
        const np = nearestPoi(center, poiCat)
        if (!np) return alert('No places of that type are in the play area.')
        params = { poiCat, fromLat: center.lat, fromLon: center.lon, poiName: np.name, answer: yesno }
        break
      }
      case 'measure-poi': {
        if (!center) return alert('Set your location (paste coordinates or click the map).')
        if (!Number.isFinite(nearestPoiMiles(center, poiCat)))
          return alert('No places of that type are in the play area.')
        params = { poiCat, fromLat: center.lat, fromLon: center.lon, answer: closefar }
        break
      }
      case 'measure-sealevel': {
        if (num === '') return alert(`Enter your altitude in ${elevUnit}.`)
        const meters = metric ? Number(num) : Number(num) / FEET_PER_METER
        params = { value: meters, answer: closefar }
        break
      }
      case 'match-namelength': {
        if (num === '') return alert('Enter your station name length.')
        params = { value: Number(num), answer: yesno }
        break
      }
      case 'match-county':
      case 'match-city':
      case 'match-airport':
      case 'match-line': {
        if (!value) return alert('Choose a value.')
        params = { value, answer: yesno }
        break
      }
      case 'inside-floor': {
        if (!building.trim()) return alert('Enter the building you are inside.')
        if (!floor.trim()) return alert('Enter the floor you are on.')
        params = { building: building.trim(), floor: floor.trim(), answer: floorAns }
        break
      }
      case 'photo': {
        params = { description: value }
        break
      }
    }
    // A vetoed question carries no answer (the hider refused to answer), so it
    // eliminates nothing but is still logged.
    if (vetoed) delete params.answer
    onSubmit({
      id: uid(),
      kind,
      createdAt: Date.now(),
      params,
      note: note || undefined,
      eliminates: meta.eliminates,
      active: true,
      ...(vetoed ? { vetoed: true } : {}),
    })
    // reset point captures but keep kind
    setCenter(null); setPtA(null); setPtB(null); setValue(''); setNum(''); setBuilding(''); setFloor(''); setNote(''); setCustomRadius(''); setCustomThermo('')
  }

  // Preview of the hider's cost if this question were asked now: the nth ask of
  // the same group costs ×n. Radar/thermometer key on the chosen distance, so the
  // preview updates as you change the radius dropdown or set the A/B points.
  const previewMult = (() => {
    let params: Record<string, unknown> = {}
    if (kind === 'radar') {
      const r =
        radius === 'custom'
          ? metric
            ? Number(customRadius) / KM_PER_MILE
            : Number(customRadius)
          : Number(radius)
      if (!Number.isFinite(r) || r <= 0) return 1
      params = { radiusMiles: r }
    } else if (kind === 'thermometer') {
      const t = thermoMiles()
      if (!Number.isFinite(t) || t <= 0) return 1
      params = { thermometerMiles: t }
    } else if (kind === 'match-poi' || kind === 'measure-poi') {
      params = { poiCat }
    }
    const key = questionGroupKey(kind, params)
    return (askGroupCounts.get(key) ?? 0) + 1
  })()
  const previewCards = scaleCards(meta.cards, previewMult)

  const yesNo = (
    <div className="row">
      <label>Answer</label>
      <div className="seg">
        <button className={yesno === 'yes' ? 'on' : ''} onClick={() => setYesno('yes')}>Yes</button>
        <button className={yesno === 'no' ? 'on' : ''} onClick={() => setYesno('no')}>No</button>
      </div>
    </div>
  )

  const dropdown = (opts: string[]) => (
    <div className="row">
      <label>Your value</label>
      <select value={value} onChange={(e) => setValue(e.target.value)}>
        <option value="">— choose —</option>
        {opts.map((o) => (
          <option key={o} value={o}>{o}</option>
        ))}
      </select>
    </div>
  )

  return (
    <div className="qform">
      <div className="row qrow-cat">
        <label>Type</label>
        <div className="seg seg-wrap qcat">
          {categories.map((c) => (
            <button key={c} className={category === c ? 'on' : ''} onClick={() => pickCategory(c)}>{c}</button>
          ))}
        </div>
      </div>
      {kindsInCategory.length > 1 && (
        <div className="row">
          <label>Question</label>
          <select value={kind} onChange={(e) => setKind(e.target.value as QuestionKind)}>
            {kindsInCategory.map((q) => (
              <option key={q.kind} value={q.kind}>{subLabel(q.label)}</option>
            ))}
          </select>
        </div>
      )}
      <p className="blurb">
        {meta.blurb}{' '}
        <span className="cards">
          ({previewCards}
          {previewMult > 1 && (
            <span className="cards-mult">
              {' '}— ×{previewMult}, {previewMult}
              {ordinalSuffix(previewMult)} time asked
            </span>
          )}
          )
        </span>
      </p>

      {kind === 'radar' && (
        <>
          <div className="row">
            <label>Radius (mi)</label>
            <select value={radius} onChange={(e) => setRadius(e.target.value)}>
              {RADAR_OPTIONS.map((r) => (
                <option key={r} value={r}>{r}</option>
              ))}
              <option value="custom">Custom…</option>
            </select>
          </div>
          {radius === 'custom' && (
            <div className="row">
              <label>Custom ({distUnit})</label>
              <input type="number" step="any" min="0" value={customRadius} onChange={(e) => setCustomRadius(e.target.value)} placeholder="e.g. 2.5" />
            </div>
          )}
          <CoordPicker label="Center" point={center} setPoint={setCenter} lastClick={lastClick} onPreview={onPreview} />
          {yesNo}
        </>
      )}

      {kind === 'thermometer' && (
        <>
          <div className="row">
            <label>Thermometer ({distUnit})</label>
            <select value={thermo} onChange={(e) => setThermo(e.target.value)}>
              {THERMOMETER_OPTIONS.map((t) => (
                <option key={t} value={t}>{metric ? +(t * KM_PER_MILE).toFixed(2) : t}</option>
              ))}
              <option value="custom">Custom…</option>
            </select>
          </div>
          {thermo === 'custom' && (
            <div className="row">
              <label>Custom ({distUnit})</label>
              <input type="number" step="any" min="0" value={customThermo} onChange={(e) => setCustomThermo(e.target.value)} placeholder="e.g. 1" />
            </div>
          )}
          <CoordPicker label="Start A" point={ptA} setPoint={setPtA} lastClick={lastClick} onPreview={onPreview} />
          <CoordPicker label="End B" point={ptB} setPoint={setPtB} lastClick={lastClick} onPreview={onPreview} />
          <div className="row">
            <label>Result</label>
            <div className="seg">
              <button className={hotcold === 'hotter' ? 'on' : ''} onClick={() => setHotcold('hotter')}>Hotter</button>
              <button className={hotcold === 'colder' ? 'on' : ''} onClick={() => setHotcold('colder')}>Colder</button>
            </div>
          </div>
        </>
      )}

      {kind === 'measure-airport' && (
        <>
          <CoordPicker label="Your location" point={center} setPoint={setCenter} lastClick={lastClick} onPreview={onPreview} />
          <div className="row">
            <label>Answer</label>
            <div className="seg">
              <button className={closefar === 'closer' ? 'on' : ''} onClick={() => setClosefar('closer')}>Closer</button>
              <button className={closefar === 'further' ? 'on' : ''} onClick={() => setClosefar('further')}>Further</button>
            </div>
          </div>
        </>
      )}

      {(kind === 'match-poi' || kind === 'measure-poi') && (
        <>
          <div className="row">
            <label>Place type</label>
            <select value={poiCat} onChange={(e) => setPoiCat(e.target.value)}>
              {QUESTION_POI_CATEGORIES.map((c) => (
                <option key={c} value={c}>{poiCategoryLabel(c)}</option>
              ))}
            </select>
          </div>
          <CoordPicker label="Your location" point={center} setPoint={setCenter} lastClick={lastClick} onPreview={onPreview} />
          {center && (() => {
            const np = nearestPoi(center, poiCat)
            const d = nearestPoiMiles(center, poiCat)
            if (!np || !Number.isFinite(d))
              return <p className="blurb poi-readout">No {poiCategoryLabel(poiCat)} in the play area.</p>
            return (
              <p className="blurb poi-readout">
                {kind === 'match-poi' ? (
                  <>Your nearest {poiCategoryLabel(poiCat)}: <b>{np.name}</b> — {formatDistance(d, units)}</>
                ) : (
                  <>Distance to nearest {poiCategoryLabel(poiCat)} (<b>{np.name}</b>): <b>{formatDistance(d, units)}</b></>
                )}
              </p>
            )
          })()}
          {kind === 'match-poi' ? yesNo : (
            <div className="row">
              <label>Answer</label>
              <div className="seg">
                <button className={closefar === 'closer' ? 'on' : ''} onClick={() => setClosefar('closer')}>Closer</button>
                <button className={closefar === 'further' ? 'on' : ''} onClick={() => setClosefar('further')}>Further</button>
              </div>
            </div>
          )}
        </>
      )}

      {kind === 'measure-sealevel' && (
        <>
          <div className="row">
            <label>Your altitude ({elevUnit})</label>
            <input type="number" value={num} onChange={(e) => setNum(e.target.value)} />
          </div>
          <div className="row">
            <label>Answer</label>
            <div className="seg">
              <button className={closefar === 'closer' ? 'on' : ''} onClick={() => setClosefar('closer')}>Closer to sea level</button>
              <button className={closefar === 'further' ? 'on' : ''} onClick={() => setClosefar('further')}>Further</button>
            </div>
          </div>
        </>
      )}

      {kind === 'match-county' && dropdown(counties)}
      {kind === 'match-city' && dropdown(cities)}
      {kind === 'match-airport' && dropdown(airports)}
      {kind === 'match-line' && dropdown(lines)}
      {(kind === 'match-county' ||
        kind === 'match-city' ||
        kind === 'match-airport' ||
        kind === 'match-line') &&
        yesNo}

      {kind === 'match-namelength' && (
        <>
          <div className="row">
            <label>Your name length</label>
            <input type="number" value={num} onChange={(e) => setNum(e.target.value)} />
          </div>
          {yesNo}
        </>
      )}

      {kind === 'inside-floor' && (
        <>
          <div className="row">
            <label>Building</label>
            <input type="text" value={building} onChange={(e) => setBuilding(e.target.value)} placeholder="e.g. Salesforce Tower" />
          </div>
          <div className="row">
            <label>Your floor</label>
            <input type="text" value={floor} onChange={(e) => setFloor(e.target.value)} placeholder="e.g. 12 or Ground" />
          </div>
          <div className="row">
            <label>Answer</label>
            <div className="seg seg-wrap">
              <button className={floorAns === 'higher' ? 'on' : ''} onClick={() => setFloorAns('higher')}>Higher</button>
              <button className={floorAns === 'lower' ? 'on' : ''} onClick={() => setFloorAns('lower')}>Lower</button>
              <button className={floorAns === 'same' ? 'on' : ''} onClick={() => setFloorAns('same')}>Same</button>
              <button className={floorAns === 'cannot' ? 'on' : ''} onClick={() => setFloorAns('cannot')}>Can’t answer</button>
            </div>
          </div>
        </>
      )}

      {kind === 'photo' && (
        <div className="row">
          <label>Describe</label>
          <input type="text" value={value} onChange={(e) => setValue(e.target.value)} placeholder="e.g. tallest building from station" />
        </div>
      )}

      <div className="row">
        <label>Note</label>
        <input type="text" value={note} onChange={(e) => setNote(e.target.value)} placeholder="optional" />
      </div>

      <div className="qform-actions">
        <button className="primary" onClick={() => submit(false)}>{meta.eliminates ? 'Log question & eliminate' : 'Log question'}</button>
        {kind !== 'photo' && (
          <button
            className="veto"
            onClick={() => submit(true)}
            title="The hider refused to answer. Logs the question (no answer, no elimination) so you can ask it again later."
          >
            Hider vetoed
          </button>
        )}
      </div>
    </div>
  )
}
