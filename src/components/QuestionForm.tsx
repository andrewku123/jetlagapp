import { useState, useEffect } from 'react'
import type { LatLng, QuestionKind, QuestionRecord, UnitSystem } from '../types'
import { QUESTION_CATALOG, RADAR_OPTIONS, THERMOMETER_OPTIONS, questionGroupKey, scaleCards } from '../data/questions'
import type { QuestionMeta } from '../data/questions'
import { KM_PER_MILE, FEET_PER_METER, parseLatLng, formatDistance, haversineMiles } from '../lib/geo'
import { QUESTION_POI_CATEGORIES, poiCategoryLabel, nearestPoi, nearestPoiMiles, TENTACLE_CATEGORIES, tentacleCategory, poisWithinRadius, poiKey } from '../lib/poi'
import { AVAILABLE_MEASURE_FEATURE_KEYS, MEASURE_FEATURE_LABELS, measureFeatureNoun, distanceToFeatureMiles } from '../lib/measureFeatures'
import { nearestAirport } from '../lib/airports'
import { countyAt } from '../lib/counties'
import { cityAt, inPlayArea } from '../lib/cities'
import { zipAt } from '../lib/zip'
import { PHOTO, type GameSize } from '../data/questionSets'

interface Props {
  lastClick: LatLng | null
  units: UnitSystem
  lines: string[]
  onSubmit: (r: QuestionRecord) => void
  onPreview: (p: LatLng) => void
  // how many times each question group has already been asked, keyed by
  // questionGroupKey — used to preview the scaled cost of asking once more.
  askGroupCounts: Map<string, number>
  // whether the seeker is currently in the endgame phase (a hiding zone is
  // locked). Used to default the "Endgame question" checkbox on.
  endgameActive: boolean
  // current game size — decides which photo cards are askable.
  gameSize: GameSize
}

// Optgroup each POI category falls under in the flattened subject dropdown, so
// the 12 categories read as one scannable list alongside airport/county/etc.
const POI_SUBJECT_GROUP: Record<string, string> = {
  park: 'Natural',
  mountain: 'Natural',
  museum: 'Places of Interest',
  movie_theater: 'Places of Interest',
  golf_course: 'Places of Interest',
  amusement_park: 'Places of Interest',
  zoo: 'Places of Interest',
  aquarium: 'Places of Interest',
  stadium: 'Places of Interest',
  hospital: 'Public Utilities',
  library: 'Public Utilities',
  consulate: 'Public Utilities',
}

// Optgroup a non-POI matching/measuring subject falls under.
const KIND_SUBJECT_GROUP: Partial<Record<QuestionKind, string>> = {
  'match-airport': 'Transit',
  'match-line': 'Transit',
  'match-namelength': 'Transit',
  'match-street': 'Transit',
  'match-admin1': 'Administrative divisions',
  'match-county': 'Administrative divisions',
  'match-city': 'Administrative divisions',
  'match-admin4': 'Administrative divisions',
  'match-landmass': 'Natural',
  'measure-airport': 'Transit',
  'measure-hsr': 'Transit',
  'measure-railstation': 'Transit',
  'measure-sealevel': 'Natural',
  'measure-water': 'Natural',
  'measure-zip': 'Administrative divisions',
  'temperature': 'Natural',
  'inside-floor': 'Indoors',
  'traffic': 'Indoors',
}

// Optgroup each coastline/border feature falls under when measure-feature is
// flattened into the single Question dropdown (same treatment as POI categories).
const FEATURE_SUBJECT_GROUP: Record<string, string> = {
  coastline: 'Natural',
  'county-border': 'Borders',
  'state-border': 'Borders',
  'intl-border': 'Borders',
}

// Dropdown label for a measure-feature: strip the leading article from the
// data label ("a coastline" → "Coastline") and capitalize.
function featureSubjectLabel(key: string): string {
  const raw = (MEASURE_FEATURE_LABELS[key as keyof typeof MEASURE_FEATURE_LABELS] ?? key).replace(/^an? /, '')
  return raw.charAt(0).toUpperCase() + raw.slice(1)
}

// Kinds that have no auto-eliminator — logged for the seeker's notes only.
const MATCH_LOGONLY: QuestionKind[] = ['match-street', 'match-admin1', 'match-admin4', 'match-landmass']
const MEASURE_LOGONLY: QuestionKind[] = ['measure-hsr', 'measure-railstation', 'measure-water']

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
  lines,
  onSubmit,
  onPreview,
  askGroupCounts,
  endgameActive,
  gameSize,
}: Props) {
  // photo cards askable in this game size
  const photoCards = PHOTO.filter((c) => c.sizes.includes(gameSize))
  // tentacle categories askable in this game size (Small = none, so the whole
  // Tentacles type is hidden below).
  const tentCats = TENTACLE_CATEGORIES.filter((c) => c.sizes.includes(gameSize))
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
  ).filter((c) => c !== 'Tentacles' || tentCats.length > 0)
  const [category, setCategory] = useState<QuestionMeta['category']>(meta.category)
  const kindsInCategory = QUESTION_CATALOG.filter((q) => q.category === category)
  function pickCategory(c: QuestionMeta['category']) {
    setCategory(c)
    const first = QUESTION_CATALOG.find((q) => q.category === c)!
    setKind(first.kind)
    // Entering Tentacles: make sure the chosen category is one askable at this
    // game size (the default museum could be gated out on some sizes).
    if (c === 'Tentacles' && tentCats.length > 0 && !tentCats.some((t) => t.key === tentCat)) {
      setTentCat(tentCats[0].key)
    }
  }
  // strip the "Category — " prefix so the step-2 dropdown is just the specifics
  const subLabel = (label: string) => {
    const i = label.indexOf(' — ')
    return i >= 0 ? label.slice(i + 3) : label
  }
  const capitalize = (s: string) => (s ? s.charAt(0).toUpperCase() + s.slice(1) : s)

  // shared param state
  const [radius, setRadius] = useState<string>('0.5')
  const [customRadius, setCustomRadius] = useState<string>('')
  const [thermo, setThermo] = useState<string>('0.5')
  const [customThermo, setCustomThermo] = useState<string>('')
  const [yesno, setYesno] = useState<'yes' | 'no'>('yes')
  const [hotcold, setHotcold] = useState<'hotter' | 'colder'>('hotter')
  const [closefar, setClosefar] = useState<'closer' | 'further'>('closer')
  const [smalllarge, setSmalllarge] = useState<'smaller' | 'larger'>('smaller')
  const [center, setCenter] = useState<LatLng | null>(null)
  const [ptA, setPtA] = useState<LatLng | null>(null)
  const [ptB, setPtB] = useState<LatLng | null>(null)
  const [value, setValue] = useState<string>('')
  const [poiCat, setPoiCat] = useState<string>(QUESTION_POI_CATEGORIES[0])
  // tentacle: selected category (a TENTACLE_CATEGORIES key) + chosen in-range POI
  const [tentCat, setTentCat] = useState<string>(TENTACLE_CATEGORIES[0].key)
  const [tentPoi, setTentPoi] = useState<string>('')
  const [feature, setFeature] = useState<string>(AVAILABLE_MEASURE_FEATURE_KEYS[0])
  const [num, setNum] = useState<string>('')
  const [photoTitle, setPhotoTitle] = useState<string>(photoCards[0]?.title ?? '')
  const [building, setBuilding] = useState<string>('')
  const [floor, setFloor] = useState<string>('')
  const [floorAns, setFloorAns] = useState<'higher' | 'lower' | 'same' | 'cannot'>('higher')
  const [hilo, setHilo] = useState<'higher' | 'lower'>('higher')
  const [note, setNote] = useState<string>('')
  // Mark this question as asked during the endgame phase. Defaults to whether a
  // hiding zone is currently locked; re-syncs when the seeker enters/exits
  // endgame, but the seeker can override per question before logging.
  const [endgameFlag, setEndgameFlag] = useState<boolean>(endgameActive)
  useEffect(() => setEndgameFlag(endgameActive), [endgameActive])

  // The thermometer the seeker chose (converted to miles), or NaN if invalid.
  function thermoMiles(): number {
    if (thermo === 'custom') return metric ? Number(customThermo) / KM_PER_MILE : Number(customThermo)
    return Number(thermo)
  }

  // The thermometer distance is a *minimum* travel: A→B must be at least the
  // chosen distance. This is how far the actual A↔B gap may fall *short* of the
  // chosen distance before it's flagged: 5% of it, floored at 0.1 mi so hand-
  // placed points right at the threshold aren't rejected.
  function thermoTolMiles(chosen: number): number {
    return Math.max(0.1, chosen * 0.05)
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
        const actualMiles = haversineMiles(ptA, ptB)
        if (actualMiles + thermoTolMiles(tMiles) < tMiles)
          return alert(
            `Start A and end B are only ${formatDistance(actualMiles, units)} apart, but a ${formatDistance(tMiles, units)} thermometer needs a travel of at least ${formatDistance(tMiles, units)}. ` +
            `Move A/B farther apart, or pick a shorter thermometer.`,
          )
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
      case 'measure-feature': {
        if (!center) return alert('Set your location (paste coordinates or click the map).')
        if (!Number.isFinite(distanceToFeatureMiles(center, feature)))
          return alert('That feature has no geometry in the play area.')
        params = { feature, fromLat: center.lat, fromLon: center.lon, answer: closefar }
        break
      }
      case 'measure-sealevel': {
        if (num === '') return alert(`Enter your altitude in ${elevUnit}.`)
        const meters = metric ? Number(num) : Number(num) / FEET_PER_METER
        params = { value: meters, answer: closefar }
        break
      }
      case 'measure-zip': {
        if (!center) return alert('Set your location (paste coordinates or click the map).')
        const z = zipAt(center)
        if (!z) return alert(inPlayArea(center)
          ? 'No ZIP code here.'
          : 'Outside the play area.')
        params = { value: z, fromLat: center.lat, fromLon: center.lon, answer: smalllarge }
        break
      }
      case 'tentacle': {
        if (!center) return alert('Set your location (paste coordinates or click the map).')
        const tc = tentacleCategory(tentCat)
        if (!tc) return alert('Pick a tentacle subject.')
        const inPlay = poisWithinRadius(center, tentCat, tc.radiusMi)
        if (inPlay.length === 0)
          return alert(`No ${poiCategoryLabel(tentCat)}s within ${formatDistance(tc.radiusMi, units)} of here — this question can't be asked from this spot.`)
        const chosen = inPlay.find((poi) => poiKey(poi) === tentPoi)
        if (!chosen) return alert('Pick which in-range place the hider is closest to.')
        params = {
          poiCat: tentCat,
          radiusMi: tc.radiusMi,
          fromLat: center.lat,
          fromLon: center.lon,
          value: poiKey(chosen),
          poiName: chosen.name,
        }
        break
      }
      case 'match-namelength': {
        if (num === '') return alert('Enter your station name length.')
        params = { value: Number(num), answer: yesno }
        break
      }
      case 'match-airport': {
        if (!center) return alert('Set your location (paste coordinates or click the map).')
        params = { value: nearestAirport(center).code, fromLat: center.lat, fromLon: center.lon, answer: yesno }
        break
      }
      case 'match-county': {
        if (!center) return alert('Set your location (paste coordinates or click the map).')
        const c = countyAt(center)
        if (!c) return alert('Outside the play area.')
        params = { value: c, fromLat: center.lat, fromLon: center.lon, answer: yesno }
        break
      }
      case 'match-city': {
        if (!center) return alert('Set your location (paste coordinates or click the map).')
        const c = cityAt(center)
        if (!c) return alert(inPlayArea(center)
          ? "Unincorporated — you're not in a city here, so there's no municipality to match."
          : 'Outside the play area.')
        params = { value: c, fromLat: center.lat, fromLon: center.lon, answer: yesno }
        break
      }
      case 'match-line': {
        if (!value) return alert('Choose a value.')
        params = { value, answer: yesno }
        break
      }
      case 'match-street':
      case 'match-admin1':
      case 'match-admin4':
      case 'match-landmass': {
        // Record-keeping only: log the answer (+ optional detail) but eliminate nothing.
        params = { description: value.trim() || undefined, answer: yesno }
        break
      }
      case 'measure-hsr':
      case 'measure-railstation':
      case 'measure-water': {
        params = { description: value.trim() || undefined, answer: closefar }
        break
      }
      case 'inside-floor': {
        if (!building.trim()) return alert('Enter the building you are inside.')
        if (!floor.trim()) return alert('Enter the floor you are on.')
        params = { building: building.trim(), floor: floor.trim(), answer: floorAns }
        break
      }
      case 'temperature': {
        // Log-only: record the hider's higher/lower answer for reference.
        params = { answer: hilo }
        break
      }
      case 'traffic': {
        // Log-only: record the hider's reported foot-traffic count.
        if (num === '') return alert("Enter the hider's reported count.")
        params = { value: Number(num) }
        break
      }
      case 'photo': {
        if (!photoTitle) return alert('Pick which photo you asked for.')
        params = { photoTitle }
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
      ...(endgameFlag ? { endgame: true } : {}),
    })
    // reset point captures but keep kind
    setCenter(null); setPtA(null); setPtB(null); setValue(''); setNum(''); setBuilding(''); setFloor(''); setNote(''); setCustomRadius(''); setCustomThermo(''); setTentPoi('')
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
    } else if (kind === 'measure-feature') {
      params = { feature }
    } else if (kind === 'tentacle') {
      params = { poiCat: tentCat }
    } else if (kind === 'photo') {
      params = { photoTitle }
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

  // Flattened subject dropdown: the two POI kinds (match-poi / measure-poi) and
  // measure-feature each expand into one entry per category/feature, so every
  // subject sits in the single Question dropdown rather than behind a second
  // select. An expanded option encodes its parameter as `${kind}::${value}`.
  interface SubjectOption { value: string; label: string; group: string }
  const subjectOptions: SubjectOption[] = kindsInCategory.flatMap((q) => {
    if (q.kind === 'match-poi' || q.kind === 'measure-poi') {
      return QUESTION_POI_CATEGORIES.map((c) => ({
        value: `${q.kind}::${c}`,
        label: capitalize(poiCategoryLabel(c)),
        group: POI_SUBJECT_GROUP[c] ?? 'Places of Interest',
      }))
    }
    if (q.kind === 'measure-feature') {
      return AVAILABLE_MEASURE_FEATURE_KEYS.map((k) => ({
        value: `${q.kind}::${k}`,
        label: featureSubjectLabel(k),
        group: FEATURE_SUBJECT_GROUP[k] ?? 'Borders',
      }))
    }
    if (q.kind === 'tentacle') {
      return tentCats.map((c) => ({
        value: `${q.kind}::${c.key}`,
        label: `${capitalize(poiCategoryLabel(c.key))}s within ${formatDistance(c.radiusMi, units)}`,
        group: `Within ${formatDistance(c.radiusMi, units)}`,
      }))
    }
    return [{ value: q.kind, label: subLabel(q.label), group: KIND_SUBJECT_GROUP[q.kind] ?? 'Other' }]
  })
  const subjectValue =
    kind === 'match-poi' || kind === 'measure-poi'
      ? `${kind}::${poiCat}`
      : kind === 'measure-feature'
        ? `${kind}::${feature}`
        : kind === 'tentacle'
          ? `${kind}::${tentCat}`
          : kind
  function pickSubject(v: string) {
    const [k, param] = v.split('::')
    setKind(k as QuestionKind)
    if (param) {
      if (k === 'measure-feature') setFeature(param)
      else if (k === 'tentacle') setTentCat(param)
      else setPoiCat(param)
    }
  }
  const subjectGroups: { group: string; opts: SubjectOption[] }[] = []
  for (const o of subjectOptions) {
    let g = subjectGroups.find((x) => x.group === o.group)
    if (!g) {
      g = { group: o.group, opts: [] }
      subjectGroups.push(g)
    }
    g.opts.push(o)
  }

  // The catalog blurb is generic ("…the chosen coastline / border", "…your
  // nearest place of the chosen type"); once a specific feature / POI subject is
  // picked, name it so the seeker reads exactly what they're measuring/matching.
  const tentRadius = tentacleCategory(tentCat)?.radiusMi ?? 1
  const blurbText =
    kind === 'measure-feature'
      ? `Compared to me, are you closer to or further from the nearest ${measureFeatureNoun(feature)}? Set your location; the app shows your distance to it.`
      : kind === 'measure-poi'
        ? `Compared to me, are you closer to or further from your nearest ${poiCategoryLabel(poiCat)}? Set your location; the app shows your distance to it.`
        : kind === 'match-poi'
          ? `Is your nearest ${poiCategoryLabel(poiCat)} the same as mine? Set your location; the app shows which one it treats as nearest.`
          : kind === 'tentacle'
            ? `Of all the ${poiCategoryLabel(tentCat)}s within ${formatDistance(tentRadius, units)} of me, which are you closest to? Set your location; the app lists the in-range ${poiCategoryLabel(tentCat)}s — pick the one I answer. ${capitalize(poiCategoryLabel(tentCat))}s outside the radius don't count even if they're closer to you.`
            : meta.blurb

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
      {subjectOptions.length > 1 && (
        <div className="row">
          <label>Question</label>
          <select value={subjectValue} onChange={(e) => pickSubject(e.target.value)}>
            {subjectGroups.map((g) => (
              <optgroup key={g.group} label={g.group}>
                {g.opts.map((o) => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </optgroup>
            ))}
          </select>
        </div>
      )}
      <p className="blurb">
        {blurbText}{' '}
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
          {ptA && ptB && (() => {
            const actual = haversineMiles(ptA, ptB)
            const chosen = thermoMiles()
            const ok = Number.isFinite(chosen) && chosen > 0 && actual + thermoTolMiles(chosen) >= chosen
            return (
              <p className={`blurb poi-readout${ok ? '' : ' warn'}`}>
                A↔B distance: <b>{formatDistance(actual, units)}</b>
                {Number.isFinite(chosen) && chosen > 0 && (
                  <> {ok ? `✓ meets the ${formatDistance(chosen, units)} thermometer` : `⚠ must be at least ${formatDistance(chosen, units)}`}</>
                )}
              </p>
            )
          })()}
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
          {center && (() => {
            const a = nearestAirport(center)
            return (
              <p className="blurb poi-readout">
                Distance to nearest airport (<b>{a.code}</b>): <b>{formatDistance(a.distMiles, units)}</b>
              </p>
            )
          })()}
          <div className="row">
            <label>Answer</label>
            <div className="seg">
              <button className={closefar === 'closer' ? 'on' : ''} onClick={() => setClosefar('closer')}>Closer</button>
              <button className={closefar === 'further' ? 'on' : ''} onClick={() => setClosefar('further')}>Further</button>
            </div>
          </div>
        </>
      )}

      {kind === 'match-airport' && (
        <>
          <CoordPicker label="Your location" point={center} setPoint={setCenter} lastClick={lastClick} onPreview={onPreview} />
          {center && (
            <p className="blurb poi-readout">
              Your nearest airport: <b>{nearestAirport(center).code}</b> — {formatDistance(nearestAirport(center).distMiles, units)}
            </p>
          )}
          {yesNo}
        </>
      )}

      {kind === 'match-county' && (
        <>
          <CoordPicker label="Your location" point={center} setPoint={setCenter} lastClick={lastClick} onPreview={onPreview} />
          {center && (() => {
            const c = countyAt(center)
            return (
              <p className="blurb poi-readout">
                {c ? <>Your county: <b>{c}</b></> : 'Outside the play area.'}
              </p>
            )
          })()}
          {yesNo}
        </>
      )}

      {(kind === 'match-poi' || kind === 'measure-poi') && (
        <>
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

      {kind === 'measure-feature' && (
        <>
          <CoordPicker label="Your location" point={center} setPoint={setCenter} lastClick={lastClick} onPreview={onPreview} />
          {center && (() => {
            const d = distanceToFeatureMiles(center, feature)
            if (!Number.isFinite(d))
              return <p className="blurb poi-readout">No geometry for {measureFeatureNoun(feature)}.</p>
            return (
              <p className="blurb poi-readout">
                Distance to nearest {measureFeatureNoun(feature)}: <b>{formatDistance(d, units)}</b>
              </p>
            )
          })()}
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

      {kind === 'measure-zip' && (
        <>
          <CoordPicker label="Your location" point={center} setPoint={setCenter} lastClick={lastClick} onPreview={onPreview} />
          {center && (() => {
            const z = zipAt(center)
            return (
              <p className="blurb poi-readout">
                {z
                  ? <>Your ZIP: <b>{z}</b></>
                  : inPlayArea(center)
                    ? <>No ZIP code here.</>
                    : 'Outside the play area.'}
              </p>
            )
          })()}
          <div className="row">
            <label>Answer</label>
            <div className="seg">
              <button className={smalllarge === 'smaller' ? 'on' : ''} onClick={() => setSmalllarge('smaller')}>Smaller</button>
              <button className={smalllarge === 'larger' ? 'on' : ''} onClick={() => setSmalllarge('larger')}>Larger</button>
            </div>
          </div>
        </>
      )}

      {kind === 'tentacle' && (
        <>
          <CoordPicker label="Your location" point={center} setPoint={setCenter} lastClick={lastClick} onPreview={onPreview} />
          {center && (() => {
            const tc = tentacleCategory(tentCat)
            if (!tc) return null
            const inPlay = poisWithinRadius(center, tentCat, tc.radiusMi)
              .map((poi) => ({ poi, key: poiKey(poi), d: haversineMiles(center, poi) }))
              .sort((a, b) => a.d - b.d)
            if (inPlay.length === 0)
              return (
                <p className="blurb poi-readout warn">
                  No {poiCategoryLabel(tentCat)}s within {formatDistance(tc.radiusMi, units)} of here — this question can't be asked from this spot.
                </p>
              )
            return (
              <>
                <div className="row">
                  <label>Which is the hider closest to?</label>
                  <select value={tentPoi} onChange={(e) => setTentPoi(e.target.value)}>
                    <option value="">— choose the in-range place —</option>
                    {inPlay.map(({ poi, key, d }) => (
                      <option key={key} value={key}>{poi.name} ({formatDistance(d, units)} from you)</option>
                    ))}
                  </select>
                </div>
                <p className="blurb poi-readout">
                  {inPlay.length} {poiCategoryLabel(tentCat)}{inPlay.length === 1 ? '' : 's'} in range.
                  {inPlay.length === 1 && ' Only one in range — this eliminates nothing.'}
                </p>
              </>
            )
          })()}
        </>
      )}

      {kind === 'match-city' && (
        <>
          <CoordPicker label="Your location" point={center} setPoint={setCenter} lastClick={lastClick} onPreview={onPreview} />
          {center && (() => {
            const c = cityAt(center)
            return (
              <p className="blurb poi-readout">
                {c
                  ? <>Your city: <b>{c}</b></>
                  : inPlayArea(center)
                    ? <>Your city: <b>Unincorporated</b> (no municipality to match here)</>
                    : 'Outside the play area.'}
              </p>
            )
          })()}
          {yesNo}
        </>
      )}

      {kind === 'match-line' && dropdown(lines)}
      {kind === 'match-line' && yesNo}

      {MATCH_LOGONLY.includes(kind) && (
        <>
          <div className="row">
            <label>Detail (optional)</label>
            <input type="text" value={value} onChange={(e) => setValue(e.target.value)} placeholder="your answer, for your notes" />
          </div>
          {yesNo}
        </>
      )}

      {MEASURE_LOGONLY.includes(kind) && (
        <>
          <div className="row">
            <label>Detail (optional)</label>
            <input type="text" value={value} onChange={(e) => setValue(e.target.value)} placeholder="your answer, for your notes" />
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

      {kind === 'temperature' && (
        <div className="row">
          <label>Answer</label>
          <div className="seg">
            <button className={hilo === 'higher' ? 'on' : ''} onClick={() => setHilo('higher')}>Higher</button>
            <button className={hilo === 'lower' ? 'on' : ''} onClick={() => setHilo('lower')}>Lower</button>
          </div>
        </div>
      )}

      {kind === 'traffic' && (
        <div className="row">
          <label>Hider's count</label>
          <input type="number" value={num} onChange={(e) => setNum(e.target.value)} placeholder="people in 5 min" />
        </div>
      )}

      {kind === 'photo' && (
        <>
          <div className="row">
            <label>Photo</label>
            <select value={photoTitle} onChange={(e) => setPhotoTitle(e.target.value)}>
              {photoCards.map((c) => (
                <option key={c.title} value={c.title}>{c.title}</option>
              ))}
            </select>
          </div>
          {(() => {
            const card = photoCards.find((c) => c.title === photoTitle)
            return card ? <p className="blurb poi-readout">{card.requirement}</p> : null
          })()}
        </>
      )}

      <div className="row">
        <label>Note</label>
        <input type="text" value={note} onChange={(e) => setNote(e.target.value)} placeholder="optional" />
      </div>

      {meta.eliminates && (
        <label className="endgame-check" title="Endgame questions still eliminate stations map-wide, but their shading is clipped to the hiding zone to help pinpoint the hider inside it.">
          <input type="checkbox" checked={endgameFlag} onChange={(e) => setEndgameFlag(e.target.checked)} />
          <span className="endgame-text">
            Endgame question
            <span className="muted">shading clips to the hiding zone</span>
          </span>
        </label>
      )}

      <div className="qform-actions">
        <button className="primary" onClick={() => submit(false)}>{meta.eliminates ? 'Log question & eliminate' : 'Log question'}</button>
        <button
          className="veto"
          onClick={() => submit(true)}
          title="The hider refused to answer. Logs the question (no answer, no elimination) so you can ask it again later."
        >
          Hider vetoed
        </button>
      </div>
    </div>
  )
}
