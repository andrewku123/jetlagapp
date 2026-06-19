import { useState } from 'react'
import type { LatLng, QuestionKind, QuestionRecord } from '../types'
import { QUESTION_CATALOG, RADAR_OPTIONS } from '../data/questions'

interface Props {
  lastClick: LatLng | null
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

export default function QuestionForm({
  lastClick,
  counties,
  cities,
  lines,
  airports,
  onSubmit,
}: Props) {
  const [kind, setKind] = useState<QuestionKind>('radar')
  const meta = QUESTION_CATALOG.find((q) => q.kind === kind)!

  // shared param state
  const [radius, setRadius] = useState<string>('0.5')
  const [yesno, setYesno] = useState<'yes' | 'no'>('yes')
  const [hotcold, setHotcold] = useState<'hotter' | 'colder'>('hotter')
  const [closefar, setClosefar] = useState<'closer' | 'further'>('closer')
  const [center, setCenter] = useState<LatLng | null>(null)
  const [ptA, setPtA] = useState<LatLng | null>(null)
  const [ptB, setPtB] = useState<LatLng | null>(null)
  const [value, setValue] = useState<string>('')
  const [num, setNum] = useState<string>('')
  const [note, setNote] = useState<string>('')

  function submit() {
    let params: Record<string, unknown> = {}
    switch (kind) {
      case 'radar': {
        if (!center) return alert('Set the radar center by clicking the map.')
        params = { lat: center.lat, lon: center.lon, radiusMiles: Number(radius), answer: yesno }
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
        if (num === '') return alert('Enter your altitude in meters.')
        params = { value: Number(num), answer: closefar }
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
    setCenter(null); setPtA(null); setPtB(null); setValue(''); setNum(''); setNote('')
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
            </select>
          </div>
          <div className="row">
            <label>Center</label>
            <span className="coord">{fmt(center)}</span>
            <button disabled={!lastClick} onClick={() => setCenter(lastClick)}>Use last click</button>
          </div>
          {yesNo}
        </>
      )}

      {kind === 'thermometer' && (
        <>
          <div className="row">
            <label>Start A</label>
            <span className="coord">{fmt(ptA)}</span>
            <button disabled={!lastClick} onClick={() => setPtA(lastClick)}>Use last click</button>
          </div>
          <div className="row">
            <label>End B</label>
            <span className="coord">{fmt(ptB)}</span>
            <button disabled={!lastClick} onClick={() => setPtB(lastClick)}>Use last click</button>
          </div>
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
          <div className="row">
            <label>Your location</label>
            <span className="coord">{fmt(center)}</span>
            <button disabled={!lastClick} onClick={() => setCenter(lastClick)}>Use last click</button>
          </div>
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
            <label>Your altitude (m)</label>
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

      <button className="primary" onClick={submit}>Log question &amp; eliminate</button>
    </div>
  )
}
