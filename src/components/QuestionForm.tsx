import { useState } from 'react'
import type { LatLng, QuestionKind, QuestionRecord, UnitSystem } from '../types'
import { QUESTION_CATALOG, RADAR_OPTIONS } from '../data/questions'
import { KM_PER_MILE, FEET_PER_METER, parseLatLng } from '../lib/geo'

interface Props {
  lastClick: LatLng | null
  units: UnitSystem
  counties: string[]
  cities: string[]
  lines: string[]
  airports: string[]
  onSubmit: (r: QuestionRecord) => void
}

function uid(): string {
  return 'q' + Date.now().toString(36) + Math.random().toString(36).slice(2, 6)
}

function fmt(p: LatLng | null): string {
  return p ? `${p.lat.toFixed(4)}, ${p.lon.toFixed(4)}` : '— click map —'
}

// A location picker: "Use last click" plus manual lat/lon entry.
function CoordPicker({
  label,
  point,
  setPoint,
  lastClick,
}: {
  label: string
  point: LatLng | null
  setPoint: (p: LatLng | null) => void
  lastClick: LatLng | null
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
  }
  return (
    <div className="coordpick">
      <div className="row">
        <label>{label}</label>
        <span className="coord">{fmt(point)}</span>
        <button disabled={!lastClick} onClick={() => setPoint(lastClick)}>Use last click</button>
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
}: Props) {
  const metric = units === 'metric'
  const distUnit = metric ? 'km' : 'mi'
  const elevUnit = metric ? 'm' : 'ft'
  const [kind, setKind] = useState<QuestionKind>('radar')
  const meta = QUESTION_CATALOG.find((q) => q.kind === kind)!

  // shared param state
  const [radius, setRadius] = useState<string>('0.5')
  const [customRadius, setCustomRadius] = useState<string>('')
  const [yesno, setYesno] = useState<'yes' | 'no'>('yes')
  const [hotcold, setHotcold] = useState<'hotter' | 'colder'>('hotter')
  const [closefar, setClosefar] = useState<'closer' | 'further'>('closer')
  const [center, setCenter] = useState<LatLng | null>(null)
  const [ptA, setPtA] = useState<LatLng | null>(null)
  const [ptB, setPtB] = useState<LatLng | null>(null)
  const [value, setValue] = useState<string>('')
  const [num, setNum] = useState<string>('')
  const [building, setBuilding] = useState<string>('')
  const [floorAns, setFloorAns] = useState<'higher' | 'lower' | 'same' | 'cannot'>('higher')
  const [note, setNote] = useState<string>('')

  function submit() {
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
        params = { fromLat: ptA.lat, fromLon: ptA.lon, toLat: ptB.lat, toLon: ptB.lon, answer: hotcold }
        break
      }
      case 'measure-airport': {
        if (!center) return alert('Set your location by clicking the map.')
        params = { fromLat: center.lat, fromLon: center.lon, answer: closefar }
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
        params = { building: building.trim(), answer: floorAns }
        break
      }
      case 'photo': {
        params = { description: value }
        break
      }
    }
    onSubmit({
      id: uid(),
      kind,
      createdAt: Date.now(),
      params,
      note: note || undefined,
      eliminates: meta.eliminates,
      active: true,
    })
    // reset point captures but keep kind
    setCenter(null); setPtA(null); setPtB(null); setValue(''); setNum(''); setBuilding(''); setNote(''); setCustomRadius('')
  }

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
      <div className="row">
        <label>Question</label>
        <select value={kind} onChange={(e) => setKind(e.target.value as QuestionKind)}>
          {QUESTION_CATALOG.map((q) => (
            <option key={q.kind} value={q.kind}>{q.label}</option>
          ))}
        </select>
      </div>
      <p className="blurb">{meta.blurb} <span className="cards">({meta.cards})</span></p>

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
          <CoordPicker label="Center" point={center} setPoint={setCenter} lastClick={lastClick} />
          {yesNo}
        </>
      )}

      {kind === 'thermometer' && (
        <>
          <CoordPicker label="Start A" point={ptA} setPoint={setPtA} lastClick={lastClick} />
          <CoordPicker label="End B" point={ptB} setPoint={setPtB} lastClick={lastClick} />
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
          <CoordPicker label="Your location" point={center} setPoint={setCenter} lastClick={lastClick} />
          <div className="row">
            <label>Answer</label>
            <div className="seg">
              <button className={closefar === 'closer' ? 'on' : ''} onClick={() => setClosefar('closer')}>Closer</button>
              <button className={closefar === 'further' ? 'on' : ''} onClick={() => setClosefar('further')}>Further</button>
            </div>
          </div>
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

      <button className="primary" onClick={submit}>{meta.eliminates ? 'Log question & eliminate' : 'Log question'}</button>
    </div>
  )
}
