import { Fragment, useEffect, useRef, useState } from 'react'
import {
  MapContainer,
  TileLayer,
  CircleMarker,
  Circle,
  Polyline,
  Polygon,
  Popup,
  Tooltip,
  GeoJSON,
  useMapEvents,
  useMap,
  Marker,
} from 'react-leaflet'
import L from 'leaflet'
import type { Feature, Geometry } from 'geojson'
import type { Annotation, LatLng, QuestionRecord, Station, DrawTool, UnitSystem } from '../types'
import { stationColor, isMultiSystem } from '../lib/style'
import { bisectorPolyline, bisectorHalfPlane, circlePolygon, haversineMiles, formatDistance, formatElevation, parseLatLng } from '../lib/geo'
import { RADAR_OPTIONS } from '../data/questions'
import { IN_PLAY_COUNTIES } from '../lib/playArea'
import countiesData from '../data/counties.geojson.json'
import transitData from '../data/transit-lines.geojson.json'

const COUNTIES = countiesData as unknown as GeoJSON.FeatureCollection

// Bounding box of the in-play counties; used to restrict satellite imagery tile
// requests to the play area (out-of-play tiles never load → much faster).
const PLAY_BOUNDS = L.geoJSON({
  type: 'FeatureCollection',
  features: COUNTIES.features.filter((f) =>
    IN_PLAY_COUNTIES.has((f.properties as { name: string }).name),
  ),
} as GeoJSON.FeatureCollection).getBounds()
function countyStyle(feature?: Feature<Geometry, { name: string }>) {
  const inPlay = feature ? IN_PLAY_COUNTIES.has(feature.properties.name) : false
  return inPlay
    ? { stroke: false, fill: false, interactive: false }
    : { stroke: true, color: '#6b7280', weight: 1, fillColor: '#6b7280', fillOpacity: 0.35, interactive: false }
}

interface TransitWay {
  type: 'Feature'
  properties: { system: string; colors: string[] }
  geometry:
    | { type: 'LineString'; coordinates: number[][] }
    | { type: 'MultiLineString'; coordinates: number[][][] }
}
const TRANSIT_WAYS = (transitData as unknown as { features: TransitWay[] }).features

// one line per physical track, drawn in the first color that runs on it
const TRANSIT: GeoJSON.FeatureCollection = {
  type: 'FeatureCollection',
  features: TRANSIT_WAYS.map((w) => ({
    type: 'Feature',
    properties: { color: w.properties.colors[0] },
    geometry: w.geometry,
  })) as Feature[],
}

function transitStyle(feature?: Feature<Geometry, { color: string }>) {
  return { color: feature?.properties.color ?? '#666', weight: 2.5, opacity: 0.95, interactive: false }
}

// BART line labels carry a "(start–end)" suffix; drop it for the station popup
const fmtLine = (l: string) => (l.startsWith('BART ') ? l.replace(/\s*\(.*\)\s*$/, '') : l)

const abbrevName = (s: string) =>
  s
    .replace(/\bStreet\b/g, 'St')
    .replace(/\bAvenue\b/g, 'Ave')
    .replace(/\bBoulevard\b/g, 'Blvd')
    .replace(/\bDrive\b/g, 'Dr')

// Alternate stop names (other-direction pole / official name) worth showing in
// the popup so a stop you'd find under that name on a map isn't "missing".
// Skip the primary name and its spelled-out duplicate.
const altNames = (st: Station): string[] => {
  const seen = new Set([abbrevName(st.name).toLowerCase()])
  const out: string[] = []
  for (const a of st.aka) {
    const ab = abbrevName(a)
    const key = ab.toLowerCase()
    if (seen.has(key)) continue
    seen.add(key)
    out.push(ab)
  }
  return out
}

interface Props {
  remaining: Station[]
  eliminated: Station[]
  showEliminated: boolean
  satellite: boolean
  starred: Set<string>
  manualEliminated: Set<string>
  units: UnitSystem
  onPickLocation: (p: LatLng) => void
  onToggleStar: (id: string) => void
  onToggleEliminate: (id: string) => void
  records: QuestionRecord[]
  pickedPoints: { label: string; point: LatLng; color: string }[]
  annotations: Annotation[]
  onAddAnnotation: (a: Annotation) => void
  onDeleteAnnotation: (id: string) => void
  onUpdateAnnotation: (id: string, patch: Partial<Annotation>) => void
  onMovePoint: (from: LatLng, to: LatLng) => void
  onClearAnnotations: () => void
  endgameStation: Station | null
  hidingRadiusMi: number
  onStartEndgame: (id: string) => void
  onExitEndgame: () => void
}

// length each side of the midpoint that a drawn line / bisector is extended (mi)
const LINE_LENGTH_MI = 60

// translucent shading for the area a question has eliminated
const ELIM_FILL = {
  color: '#cf222e',
  weight: 0,
  fillColor: '#cf222e',
  fillOpacity: 0.12,
  interactive: false,
} as const

// a near-world outer ring; eliminated-outside-circle is this minus the circle hole
const WORLD_RING: [number, number][] = [
  [-85, -179.9],
  [-85, 179.9],
  [85, 179.9],
  [85, -179.9],
]

const DRAW_COLORS = ['#e8590c', '#1971c2', '#2f9e44', '#9c36b5', '#0c0c0c']

function inAnnotationControl(t: HTMLElement | null | undefined): boolean {
  return !!(t?.closest?.('.leaflet-popup') || t?.closest?.('.leaflet-marker-icon'))
}

// snap radius in screen pixels (zoom-aware): a click/pointer within this many
// pixels of an existing drawn point reuses that exact point.
const SNAP_PX = 14

function MapClicks({
  onClick,
  onHover,
  snapPoints,
}: {
  onClick: (p: LatLng) => void
  onHover: (idx: number | null) => void
  snapPoints: LatLng[]
}) {
  // A click on a popup control (e.g. the Delete button) can re-fire as a map
  // click; by then React may have already removed the popup from the DOM, so
  // checking the click target is unreliable. Record at mousedown/touchstart
  // (capture phase, before any React state update) whether the press began on
  // a popup or marker handle, and suppress the next map click if so.
  const suppressRef = useRef(false)
  useEffect(() => {
    const onDown = (e: Event) => {
      suppressRef.current = inAnnotationControl(e.target as HTMLElement | null)
    }
    document.addEventListener('mousedown', onDown, true)
    document.addEventListener('touchstart', onDown, true)
    return () => {
      document.removeEventListener('mousedown', onDown, true)
      document.removeEventListener('touchstart', onDown, true)
    }
  }, [])
  const map = useMap()
  // nearest snap point to a container-pixel position, or -1 if none within range
  const nearest = (cp: L.Point): number => {
    let best = -1
    let bestD = Infinity
    snapPoints.forEach((sp, i) => {
      const d = cp.distanceTo(map.latLngToContainerPoint([sp.lat, sp.lon]))
      if (d < bestD) {
        bestD = d
        best = i
      }
    })
    return bestD <= SNAP_PX ? best : -1
  }
  useMapEvents({
    click(e) {
      const target = e.originalEvent?.target as HTMLElement | null
      if (suppressRef.current || inAnnotationControl(target)) {
        suppressRef.current = false
        return
      }
      // snap to an existing drawn point if the click lands within ~14px of one,
      // so you can reuse points across tools instead of re-clicking them
      const idx = nearest(e.containerPoint)
      const p: LatLng = idx >= 0 ? snapPoints[idx] : { lat: e.latlng.lat, lon: e.latlng.lng }
      onHover(null)
      onClick(p)
    },
    // highlight the point the next click would snap onto as the pointer nears it.
    // Skip while a mouse button is held: a hover state change re-renders the map,
    // and a re-render mid-drag resets the dragged handle to its prop position and
    // cancels the drag (react-leaflet calls setLatLng on every render).
    mousemove(e) {
      if ((e.originalEvent as MouseEvent | undefined)?.buttons) return
      const idx = snapPoints.length ? nearest(e.containerPoint) : -1
      onHover(idx === -1 ? null : idx)
    },
    mouseout() {
      onHover(null)
    },
  })
  return null
}

// Fits the view to the live area: once on first load (to the remaining
// stations), and again whenever endgame locks onto a station (to its
// hiding-zone circle). Manual zoom/pan afterwards is left untouched.
function MapFit({
  remaining,
  endgame,
  radiusMi,
}: {
  remaining: Station[]
  endgame: Station | null
  radiusMi: number
}) {
  const map = useMap()
  const didInit = useRef(false)
  const lastEndgame = useRef<string | null>(null)
  useEffect(() => {
    if (didInit.current || remaining.length === 0) return
    didInit.current = true
    map.fitBounds(L.latLngBounds(remaining.map((s) => [s.lat, s.lon])).pad(0.12))
  }, [map, remaining])
  useEffect(() => {
    const id = endgame?.id ?? null
    if (id === lastEndgame.current) return
    lastEndgame.current = id
    if (!endgame) return
    const b = L.latLng(endgame.lat, endgame.lon).toBounds(radiusMi * 1609.344 * 2.6)
    map.fitBounds(b)
  }, [map, endgame, radiusMi])
  return null
}

const pin = (color: string) =>
  L.divIcon({
    className: 'seeker-pin',
    html: `<div style="background:${color}" class="seeker-pin-dot"></div>`,
    iconSize: [16, 16],
    iconAnchor: [8, 8],
  })

const handleIcon = (color: string, big = false) => {
  const s = big ? 18 : 14
  return L.divIcon({
    className: 'drag-handle',
    html: `<div style="background:${color}" class="drag-handle-dot"></div>`,
    iconSize: [s, s],
    iconAnchor: [s / 2, s / 2],
  })
}

const MEASURE_STEPS = [0, 0.5, 1, 5, 10]

function RadiusEditPopup({
  value,
  onChange,
  onDelete,
}: {
  value: number
  onChange: (v: number) => void
  onDelete: () => void
}) {
  const [custom, setCustom] = useState(!RADAR_OPTIONS.includes(value))
  return (
    <div className="popup">
      <label>
        radius
        <select
          value={custom ? 'custom' : String(value)}
          onChange={(e) => {
            if (e.target.value === 'custom') setCustom(true)
            else {
              setCustom(false)
              onChange(Number(e.target.value))
            }
          }}
        >
          {RADAR_OPTIONS.map((r) => (
            <option key={r} value={r}>{r} mi</option>
          ))}
          <option value="custom">Custom…</option>
        </select>
      </label>
      {custom && (
        <input
          className="popup-input"
          type="number"
          min={0}
          step="any"
          value={value}
          onChange={(e) => onChange(Number(e.target.value))}
        />
      )}
      <button onClick={onDelete}>Delete</button>
    </div>
  )
}

function MeasureEditPopup({
  step,
  units,
  onChange,
  onDelete,
}: {
  step: number
  units: UnitSystem
  onChange: (v: number) => void
  onDelete: () => void
}) {
  const [custom, setCustom] = useState(!MEASURE_STEPS.includes(step))
  const u = units === 'metric' ? 'km' : 'mi'
  return (
    <div className="popup">
      <label>
        round
        <select
          value={custom ? 'custom' : String(step)}
          onChange={(e) => {
            if (e.target.value === 'custom') setCustom(true)
            else {
              setCustom(false)
              onChange(Number(e.target.value))
            }
          }}
        >
          <option value={0}>exact</option>
          <option value={0.5}>½ {u}</option>
          <option value={1}>1 {u}</option>
          <option value={5}>5 {u}</option>
          <option value={10}>10 {u}</option>
          <option value="custom">Custom…</option>
        </select>
      </label>
      {custom && (
        <input
          className="popup-input"
          type="number"
          min={0}
          step="any"
          value={step}
          onChange={(e) => onChange(Number(e.target.value))}
        />
      )}
      <button onClick={onDelete}>Delete</button>
    </div>
  )
}

const rid = () => Math.random().toString(36).slice(2, 9)

export default function MapView({
  remaining,
  eliminated,
  showEliminated,
  satellite,
  starred,
  manualEliminated,
  units,
  onPickLocation,
  onToggleStar,
  onToggleEliminate,
  records,
  pickedPoints,
  annotations,
  onAddAnnotation,
  onDeleteAnnotation,
  onUpdateAnnotation,
  onMovePoint,
  onClearAnnotations,
  endgameStation,
  hidingRadiusMi,
  onStartEndgame,
  onExitEndgame,
}: Props) {
  const [tool, setTool] = useState<DrawTool>('select')
  // stations are only clickable in select mode; in draw modes clicks pass
  // through to the map so you can snap a point/endpoint onto a station
  const selectMode = tool === 'select'
  const [radiusMi, setRadiusMi] = useState(1)
  const [compassCustom, setCompassCustom] = useState(false)
  const [color, setColor] = useState(DRAW_COLORS[0])
  // rounding step for the measure label: 0 = exact (2 dp), else snap to this many mi
  const [measureStep, setMeasureStep] = useState(0)
  // first click of a two-point line / bisector
  const [pending, setPending] = useState<LatLng | null>(null)
  // collapsible "enter coordinates" box for placing points without clicking
  const [showCoordEntry, setShowCoordEntry] = useState(false)
  const [coordText, setCoordText] = useState('')
  // second coordinate field for two-point tools (line / bisector / measure), so
  // both endpoints can be entered at once instead of one-then-the-other
  const [coordTextB, setCoordTextB] = useState('')
  const [coordError, setCoordError] = useState(false)
  // coordinate read-out tool: a transient dot + copied coords, no annotation
  const [coordPin, setCoordPin] = useState<LatLng | null>(null)
  const [coordCopied, setCoordCopied] = useState(false)
  // index (into snapPoints) of the existing point the next click would snap onto,
  // enlarged so you can see what you're about to reuse; null when none in range
  const [snapHover, setSnapHover] = useState<number | null>(null)
  // a point that was just snapped onto, briefly enlarged so the snap reads on
  // touch (where there's no hover); cleared after a short pulse
  const [snapPulse, setSnapPulse] = useState<LatLng | null>(null)
  // thermometer A/B/answer labels show briefly when a thermometer overlay
  // appears or changes, then hide so they don't clutter the map
  const [thermoLabels, setThermoLabels] = useState(true)
  const thermoSig = records
    .filter((r) => r.active && r.eliminates && r.kind === 'thermometer')
    .map(
      (r) =>
        `${r.id}:${r.params.fromLat},${r.params.fromLon},${r.params.toLat},${r.params.toLon},${r.params.answer}`,
    )
    .join('|')
  useEffect(() => {
    if (!thermoSig) return
    setThermoLabels(true)
    const t = window.setTimeout(() => setThermoLabels(false), 5000)
    return () => window.clearTimeout(t)
  }, [thermoSig])
  // measure polylines by id, so the distance label can open the line's rounding
  // popup (the label tooltip isn't the popup's source by default)
  const measureLineRefs = useRef<Record<string, L.Polyline>>({})
  // true while a handle is being dragged: suppress snap-hover state updates so the
  // map's mousemove doesn't re-render mid-drag (a re-render resets the dragged
  // marker back to its prop position, fighting/cancelling the drag)
  const draggingRef = useRef(false)
  const setHover = (idx: number | null) => {
    if (!draggingRef.current) setSnapHover(idx)
  }

  function readCoord(p: LatLng) {
    setCoordPin(p)
    const text = `${p.lat.toFixed(6)}, ${p.lon.toFixed(6)}`
    navigator.clipboard?.writeText(text).then(
      () => {
        setCoordCopied(true)
        window.setTimeout(() => setCoordCopied(false), 1200)
      },
      () => setCoordCopied(false),
    )
  }

  function addCoordPoint() {
    const p = parseLatLng(coordText)
    if (!p) {
      setCoordError(true)
      return
    }
    setCoordError(false)
    setCoordText('')
    handleClick(p)
  }

  // two-point tools: place an endpoint from each filled field. With both filled,
  // build the line/bisector/measure directly (A→B); with one filled, fall back to
  // the click flow (sets/uses `pending`) so map-click + typed point still mix.
  function addCoordPair() {
    const a = coordText.trim() ? parseLatLng(coordText) : null
    const b = coordTextB.trim() ? parseLatLng(coordTextB) : null
    if ((coordText.trim() && !a) || (coordTextB.trim() && !b) || (!a && !b)) {
      setCoordError(true)
      return
    }
    setCoordError(false)
    if (a && b) {
      const type = tool === 'bisector' ? 'bisector' : tool === 'measure' ? 'measure' : 'line'
      onAddAnnotation({
        id: rid(),
        type,
        aLat: a.lat,
        aLon: a.lon,
        bLat: b.lat,
        bLon: b.lon,
        color,
        ...(type === 'measure' ? { step: measureStep } : {}),
      })
      setPending(null)
    } else {
      handleClick((a ?? b) as LatLng)
    }
    setCoordText('')
    setCoordTextB('')
  }

  function handleClick(p: LatLng) {
    if (tool === 'select') {
      onPickLocation(p)
      return
    }
    // if this click reused an existing point, briefly enlarge it so the snap is
    // visible even on touch (no hover); exact-coord match means it was snapped
    const snapped = snapPoints.find((sp) => sp.lat === p.lat && sp.lon === p.lon)
    if (snapped) {
      setSnapPulse(snapped)
      window.setTimeout(() => setSnapPulse((cur) => (cur === snapped ? null : cur)), 450)
    }
    if (tool === 'compass') {
      onAddAnnotation({ id: rid(), type: 'circle', lat: p.lat, lon: p.lon, radiusMiles: radiusMi, color })
      return
    }
    if (tool === 'coord') {
      readCoord(p)
      return
    }
    // line / bisector / measure: collect two points
    if (!pending) {
      setPending(p)
    } else {
      const type = tool === 'bisector' ? 'bisector' : tool === 'measure' ? 'measure' : 'line'
      onAddAnnotation({
        id: rid(),
        type,
        aLat: pending.lat,
        aLon: pending.lon,
        bLat: p.lat,
        bLon: p.lon,
        color,
        ...(type === 'measure' ? { step: measureStep } : {}),
      })
      setPending(null)
    }
  }

  function selectTool(t: DrawTool) {
    setTool(t)
    setPending(null)
    setCoordPin(null)
    setCoordCopied(false)
    setCoordText('')
    setCoordTextB('')
    setCoordError(false)
  }

  // points already drawn that a new click can snap onto (reuse across tools):
  // compass centers + every line/bisector/measure endpoint, plus the in-progress
  // first point. Only offered while a drawing tool is active.
  const snapPoints: LatLng[] = selectMode
    ? []
    : [
        ...annotations.flatMap((a) =>
          a.type === 'circle'
            ? // with the compass active, a click on a center opens its edit bar
              // rather than snap-adding a concentric ring (use the coordinate
              // box for that), so don't offer circle centers as snap targets
              tool === 'compass'
              ? []
              : [{ lat: a.lat, lon: a.lon }]
            : [
                { lat: a.aLat, lon: a.aLon },
                { lat: a.bLat, lon: a.bLon },
              ],
        ),
        ...(pending ? [pending] : []),
      ]

  return (
    <>
      <div className="draw-toolbar">
        <div className="draw-tools">
          {(['select', 'compass', 'line', 'bisector', 'measure', 'coord'] as DrawTool[]).map((t) => (
            <button
              key={t}
              className={tool === t ? 'on' : ''}
              onClick={() => selectTool(t)}
              data-tip={t === 'select' ? 'Select' : t === 'compass' ? 'Compass' : t === 'line' ? 'Line' : t === 'bisector' ? 'Perpendicular bisector' : t === 'measure' ? 'Measure' : 'Coordinates'}
              aria-label={t}
            >
              {t === 'select' ? '✋' : t === 'compass' ? '⊙' : t === 'line' ? '／' : t === 'bisector' ? '⊥' : t === 'measure' ? '📏' : '📍'}
            </button>
          ))}
        </div>
        {tool === 'compass' && (
          <label className="draw-radius">
            radius
            <select
              value={compassCustom ? 'custom' : String(radiusMi)}
              onChange={(e) => {
                if (e.target.value === 'custom') {
                  setCompassCustom(true)
                } else {
                  setCompassCustom(false)
                  setRadiusMi(Number(e.target.value))
                }
              }}
            >
              {RADAR_OPTIONS.map((r) => (
                <option key={r} value={r}>{r} mi</option>
              ))}
              <option value="custom">Custom…</option>
            </select>
            {compassCustom && (
              <input
                type="number"
                min={0}
                step="any"
                className="draw-radius-input"
                value={radiusMi}
                onChange={(e) => setRadiusMi(Number(e.target.value))}
              />
            )}
          </label>
        )}
        {tool === 'measure' && (
          <label className="draw-radius">
            round
            <select value={measureStep} onChange={(e) => setMeasureStep(Number(e.target.value))}>
              <option value={0}>exact</option>
              <option value={0.5}>½ {units === 'metric' ? 'km' : 'mi'}</option>
              <option value={1}>1 {units === 'metric' ? 'km' : 'mi'}</option>
              <option value={5}>5 {units === 'metric' ? 'km' : 'mi'}</option>
              <option value={10}>10 {units === 'metric' ? 'km' : 'mi'}</option>
            </select>
          </label>
        )}
        {tool !== 'select' && tool !== 'coord' && (
          <div className="draw-colors">
            {DRAW_COLORS.map((c) => (
              <button
                key={c}
                className={'swatch' + (color === c ? ' on' : '')}
                style={{ background: c }}
                onClick={() => setColor(c)}
                aria-label={`color ${c}`}
              />
            ))}
          </div>
        )}
        {tool === 'coord' && (
          <div className="draw-coord-readout">
            {coordPin ? (
              <>
                <span className="cr-val">{coordPin.lat.toFixed(6)}, {coordPin.lon.toFixed(6)}</span>
                <button
                  className="cr-copy"
                  onClick={() => readCoord(coordPin)}
                >
                  {coordCopied ? 'Copied ✓' : 'Copy'}
                </button>
              </>
            ) : (
              <span className="cr-hint">Click the map to read &amp; copy coordinates.</span>
            )}
          </div>
        )}
        {tool !== 'select' && tool !== 'coord' && (
          <div className="draw-coords">
            <button
              className="draw-coords-toggle"
              onClick={() => setShowCoordEntry((v) => !v)}
            >
              {showCoordEntry ? '▾' : '▸'} enter coordinates
            </button>
            {showCoordEntry &&
              (tool === 'line' || tool === 'bisector' || tool === 'measure' ? (
                <div className="draw-coords-body two">
                  <input
                    className={'draw-coords-input' + (coordError ? ' err' : '')}
                    placeholder="A: lat, lon"
                    value={coordText}
                    onChange={(e) => {
                      setCoordText(e.target.value)
                      setCoordError(false)
                    }}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') addCoordPair()
                    }}
                  />
                  <input
                    className={'draw-coords-input' + (coordError ? ' err' : '')}
                    placeholder="B: lat, lon"
                    value={coordTextB}
                    onChange={(e) => {
                      setCoordTextB(e.target.value)
                      setCoordError(false)
                    }}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') addCoordPair()
                    }}
                  />
                  <button onClick={addCoordPair}>Add</button>
                </div>
              ) : (
                <div className="draw-coords-body">
                  <input
                    className={'draw-coords-input' + (coordError ? ' err' : '')}
                    placeholder="lat, lon"
                    value={coordText}
                    onChange={(e) => {
                      setCoordText(e.target.value)
                      setCoordError(false)
                    }}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') addCoordPoint()
                    }}
                  />
                  <button onClick={addCoordPoint}>{tool === 'compass' ? 'Draw' : 'Add'}</button>
                </div>
              ))}
            {coordError && <div className="draw-coords-err">Couldn’t read those coordinates.</div>}
          </div>
        )}
        {(annotations.length > 0 || pending) && (
          <div className={'draw-actions' + (tool !== 'select' ? ' open' : '')}>
            <button
              className="draw-undo"
              data-tip="Undo"
              aria-label="Undo"
              onClick={() => {
                if (pending) {
                  setPending(null)
                } else if (annotations.length > 0) {
                  onDeleteAnnotation(annotations[annotations.length - 1].id)
                }
              }}
            >
              ↩
            </button>
            {annotations.length > 0 && (
              <button
                className="draw-clear"
                data-tip={`Clear all (${annotations.length})`}
                aria-label={`Clear all (${annotations.length})`}
                onClick={onClearAnnotations}
              >
                🗑️
              </button>
            )}
          </div>
        )}
      </div>

      {endgameStation && (
        <div className="endgame-banner">
          <span>
            <b>Endgame:</b> {endgameStation.name} — hider within{' '}
            {formatDistance(hidingRadiusMi, units)}
          </span>
          <button onClick={onExitEndgame}>Exit</button>
        </div>
      )}

      <MapContainer center={[37.6, -122.2]} zoom={10} className="map" preferCanvas>
        <TileLayer
          attribution='&copy; OpenStreetMap contributors &copy; CARTO'
          url="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png"
          subdomains="abcd"
          maxZoom={20}
        />
        {satellite && (
          <TileLayer
            attribution='Imagery &copy; Esri, Maxar, Earthstar Geographics'
            url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
            bounds={PLAY_BOUNDS}
            maxZoom={20}
          />
        )}
        <MapClicks onClick={handleClick} onHover={setHover} snapPoints={snapPoints} />
        <MapFit remaining={remaining} endgame={endgameStation} radiusMi={hidingRadiusMi} />

        <GeoJSON data={COUNTIES} style={countyStyle as never} interactive={false} />
        <GeoJSON data={TRANSIT} style={transitStyle as never} interactive={false} />

        {/* endgame: shade the ELIMINATED area outside the hiding zone (same as
            radar/thermometer); the circle outline marks the zone, left clear. */}
        {endgameStation && (
          <Fragment>
            <Polygon
              positions={[
                WORLD_RING,
                circlePolygon(
                  { lat: endgameStation.lat, lon: endgameStation.lon },
                  hidingRadiusMi,
                ).map((p) => [p.lat, p.lon] as [number, number]),
              ]}
              pathOptions={ELIM_FILL}
            />
            <Circle
              center={[endgameStation.lat, endgameStation.lon]}
              radius={hidingRadiusMi * 1609.344}
              interactive={false}
              pathOptions={{ color: '#16a34a', weight: 2, fill: false }}
            />
          </Fragment>
        )}

        {showEliminated &&
          eliminated.map((st) => (
            <CircleMarker
              key={st.id + (selectMode ? '-s' : '-d')}
              center={[st.lat, st.lon]}
              radius={5}
              interactive={selectMode}
              pathOptions={{ color: '#9aa0a6', weight: 1, fillColor: '#9aa0a6', fillOpacity: 0.55 }}
            >
              <Popup>
                <div className="popup">
                  <strong>{st.name}</strong>
                  <div className="muted">{st.systems.join(' · ')}</div>
                  <div className="muted">Eliminated.</div>
                  <div className="popup-actions">
                    <button onClick={() => onToggleStar(st.id)}>{starred.has(st.id) ? '★ Unstar' : '☆ Star'}</button>
                    {manualEliminated.has(st.id) && (
                      <button onClick={() => onToggleEliminate(st.id)}>↩ Restore</button>
                    )}
                  </div>
                </div>
              </Popup>
            </CircleMarker>
          ))}

        {remaining.map((st) => {
          const c = stationColor(st)
          const star = starred.has(st.id)
          return (
            <CircleMarker
              key={st.id + (selectMode ? '-s' : '-d')}
              center={[st.lat, st.lon]}
              radius={star ? 11 : 6}
              interactive={selectMode}
              pathOptions={{
                color: star ? '#b8860b' : c,
                weight: star ? 3 : 1.5,
                fillColor: star ? '#f5b301' : c,
                fillOpacity: 0.9,
              }}
            >
              <Popup>
                <div className="popup">
                  <strong>{st.name}</strong>
                  {altNames(st).length > 0 && (
                    <div className="muted">also: {altNames(st).join(' · ')}</div>
                  )}
                  <div>{st.systems.join(' · ')}{isMultiSystem(st) ? ' (shared)' : ''}</div>
                  {st.lines.length > 0 && <div className="muted">{st.lines.map(fmtLine).join(', ')}</div>}
                  <div className="muted">
                    {st.city ?? '?'}, {st.county ?? '?'} Co. · {st.nameLength} chars
                    {st.elevation != null ? ` · ${formatElevation(st.elevation, units)}` : ''}
                  </div>
                  <div className="muted">Nearest airport: {st.nearestAirport}</div>
                  <div className="popup-actions">
                    <button onClick={() => onToggleStar(st.id)}>{star ? '★ Unstar' : '☆ Star'}</button>
                    <button onClick={() => onToggleEliminate(st.id)}>✕ Eliminate</button>
                    {endgameStation?.id === st.id ? (
                      <button onClick={onExitEndgame}>↩ Exit endgame</button>
                    ) : (
                      <button onClick={() => onStartEndgame(st.id)}>🎯 Endgame here</button>
                    )}
                  </div>
                </div>
              </Popup>
            </CircleMarker>
          )
        })}

        {/* radar: shade the ELIMINATED area. YES (within X) eliminates outside
            the circle; NO eliminates inside it. The circle outline always shows
            the radius. */}
        {records
          .filter((r) => r.active && r.eliminates && r.kind === 'radar')
          .map((r) => {
            const center = { lat: Number(r.params.lat), lon: Number(r.params.lon) }
            const radiusMiles = Number(r.params.radiusMiles)
            const ring = circlePolygon(center, radiusMiles).map(
              (p) => [p.lat, p.lon] as [number, number],
            )
            const yes = r.params.answer === 'yes'
            return (
              <Fragment key={r.id}>
                <Polygon
                  positions={yes ? [WORLD_RING, ring] : [ring]}
                  pathOptions={ELIM_FILL}
                />
                <Circle
                  center={[center.lat, center.lon]}
                  radius={radiusMiles * 1609.344}
                  interactive={false}
                  pathOptions={{ color: '#3730a3', weight: 1, fill: false }}
                />
              </Fragment>
            )
          })}

        {/* thermometer boundary: perpendicular bisector of the from→to segment.
            The hotter half-plane is the side toward `to`. */}
        {records
          .filter((r) => r.active && r.eliminates && r.kind === 'thermometer')
          .map((r) => {
            const from = { lat: Number(r.params.fromLat), lon: Number(r.params.fromLon) }
            const to = { lat: Number(r.params.toLat), lon: Number(r.params.toLon) }
            const ends = bisectorPolyline(from, to, LINE_LENGTH_MI)
            const hotter = r.params.answer === 'hotter'
            const hotSide = hotter ? to : from
            // mark the hotter (kept) half-plane: a point between the boundary
            // midpoint and the hot endpoint, so it sits clear of the A/B pins
            const mid = { lat: (from.lat + to.lat) / 2, lon: (from.lon + to.lon) / 2 }
            const hotMark = {
              lat: mid.lat + 0.4 * (hotSide.lat - mid.lat),
              lon: mid.lon + 0.4 * (hotSide.lon - mid.lon),
            }
            // shade the colder (eliminated) half-plane: a wide band built from
            // the boundary edge extended far, then pushed toward the cold side.
            const coldSide = hotter ? from : to
            const coldBand = bisectorHalfPlane(from, to, coldSide, 300).map(
              (p) => [p.lat, p.lon] as [number, number],
            )
            return (
              <Fragment key={r.id}>
                <Polygon positions={coldBand} pathOptions={ELIM_FILL} />
                <Polyline
                  positions={ends.map((p) => [p.lat, p.lon]) as [number, number][]}
                  interactive={false}
                  pathOptions={{ color: '#7c3aed', weight: 2.5, dashArray: '6 4' }}
                />
                {/* the A→B move the seeker made, so the kept side is unambiguous */}
                <Polyline
                  positions={[[from.lat, from.lon], [to.lat, to.lon]]}
                  interactive={false}
                  pathOptions={{ color: '#6b7280', weight: 1.5, dashArray: '2 3' }}
                />
                <CircleMarker
                  center={[from.lat, from.lon]}
                  radius={5}
                  interactive={false}
                  pathOptions={{ color: '#1971c2', weight: 2, fillColor: '#fff', fillOpacity: 1 }}
                >
                  {thermoLabels && (
                    <Tooltip permanent direction="top" offset={[0, -6]}>
                      A (start)
                    </Tooltip>
                  )}
                </CircleMarker>
                <CircleMarker
                  center={[to.lat, to.lon]}
                  radius={5}
                  interactive={false}
                  pathOptions={{ color: '#1971c2', weight: 2, fillColor: '#1971c2', fillOpacity: 1 }}
                >
                  {thermoLabels && (
                    <Tooltip permanent direction="top" offset={[0, -6]}>
                      B (end)
                    </Tooltip>
                  )}
                </CircleMarker>
                <CircleMarker
                  center={[hotMark.lat, hotMark.lon]}
                  radius={6}
                  interactive={false}
                  pathOptions={{ color: '#cf222e', weight: 2, fillColor: '#cf222e', fillOpacity: 0.85 }}
                >
                  {thermoLabels && (
                    <Tooltip permanent direction="top" offset={[0, -6]}>
                      {hotter ? 'hotter (kept)' : 'colder → kept'}
                    </Tooltip>
                  )}
                </CircleMarker>
              </Fragment>
            )
          })}

        {/* manual compass / straightedge annotations */}
        {annotations.map((a) => {
          if (a.type === 'circle') {
            return (
              <Fragment key={a.id}>
                <Circle
                  center={[a.lat, a.lon]}
                  radius={a.radiusMiles * 1609.344}
                  interactive={false}
                  pathOptions={{ color: a.color, weight: 2, fillOpacity: 0.05 }}
                />
                {/* radius spoke: center → east edge, labelled at the spoke midpoint.
                    The label is anchored to a marker at the midpoint (not the
                    polyline) so it re-positions when the radius is edited. */}
                {(() => {
                  const edge = circlePolygon({ lat: a.lat, lon: a.lon }, a.radiusMiles)[0]
                  const mid = circlePolygon({ lat: a.lat, lon: a.lon }, a.radiusMiles / 2)[0]
                  return (
                    <>
                      <Polyline
                        positions={[
                          [a.lat, a.lon],
                          [edge.lat, edge.lon],
                        ]}
                        interactive={false}
                        pathOptions={{ color: a.color, weight: 1.5, dashArray: '4 4' }}
                      />
                      <CircleMarker
                        center={[mid.lat, mid.lon]}
                        radius={1}
                        interactive={false}
                        pathOptions={{ opacity: 0, fillOpacity: 0 }}
                      >
                        <Tooltip permanent direction="center" className="measure-label">
                          {formatDistance(a.radiusMiles, units)}
                        </Tooltip>
                      </CircleMarker>
                    </>
                  )
                })()}
                <Marker
                  key={`${a.id}-center-${selectMode}-${tool === 'compass'}`}
                  position={[a.lat, a.lon]}
                  draggable={selectMode}
                  interactive={selectMode || tool === 'compass'}
                  icon={handleIcon(a.color, true)}
                  eventHandlers={{
                    // set the no-rerender guard on press, BEFORE any movement: the
                    // map's mousemove (which updates snap-hover state) fires during
                    // the initial drag threshold, and a re-render then would reset
                    // the marker to its prop position and cancel the drag
                    mousedown: () => {
                      draggingRef.current = true
                    },
                    click: (e) => {
                      draggingRef.current = false
                      // select or compass tool: open this circle's edit bar.
                      // other tools: reuse the center as a point for that tool.
                      if (selectMode || tool === 'compass') {
                        const mk = e.target as L.Marker
                        mk.openPopup()
                        return
                      }
                      handleClick({ lat: a.lat, lon: a.lon })
                    },
                    dragend: (e) => {
                      draggingRef.current = false
                      setSnapHover(null)
                      const ll = (e.target as L.Marker).getLatLng()
                      onMovePoint({ lat: a.lat, lon: a.lon }, { lat: ll.lat, lon: ll.lng })
                    },
                  }}
                >
                  {(selectMode || tool === 'compass') && (
                    <Popup>
                      <RadiusEditPopup
                        value={a.radiusMiles}
                        onChange={(v) => onUpdateAnnotation(a.id, { radiusMiles: v })}
                        onDelete={() => onDeleteAnnotation(a.id)}
                      />
                    </Popup>
                  )}
                </Marker>
              </Fragment>
            )
          }
          const endpoints =
            a.type === 'bisector'
              ? bisectorPolyline({ lat: a.aLat, lon: a.aLon }, { lat: a.bLat, lon: a.bLon }, LINE_LENGTH_MI)
              : [
                  { lat: a.aLat, lon: a.aLon },
                  { lat: a.bLat, lon: a.bLon },
                ]
          const miles =
            a.type === 'measure'
              ? haversineMiles({ lat: a.aLat, lon: a.aLon }, { lat: a.bLat, lon: a.bLon })
              : null
          const label =
            a.type === 'bisector'
              ? 'Perpendicular bisector'
              : a.type === 'measure'
                ? formatDistance(miles!, units, a.step ?? 0)
                : 'Straightedge line'
          return (
            <Fragment key={a.id}>
              {a.type === 'bisector' && (
                <Polyline
                  key={`bcon-${a.id}-${a.aLat.toFixed(5)}-${a.aLon.toFixed(5)}-${a.bLat.toFixed(5)}-${a.bLon.toFixed(5)}`}
                  positions={[[a.aLat, a.aLon], [a.bLat, a.bLon]]}
                  interactive={false}
                  pathOptions={{ color: '#6b7280', weight: 1.5, dashArray: '2 4' }}
                >
                  <Tooltip permanent direction="center" className="measure-label">
                    {formatDistance(haversineMiles({ lat: a.aLat, lon: a.aLon }, { lat: a.bLat, lon: a.bLon }), units)}
                  </Tooltip>
                </Polyline>
              )}
              <Polyline
                key={`${a.id}-${a.aLat.toFixed(5)}-${a.aLon.toFixed(5)}-${a.bLat.toFixed(5)}-${a.bLon.toFixed(5)}`}
                ref={(el) => {
                  if (el) measureLineRefs.current[a.id] = el as unknown as L.Polyline
                  else delete measureLineRefs.current[a.id]
                }}
                positions={endpoints.map((p) => [p.lat, p.lon]) as [number, number][]}
                interactive={selectMode && a.type === 'measure'}
                pathOptions={{ color: a.color, weight: 2, dashArray: a.type === 'bisector' ? '6 4' : a.type === 'measure' ? '2 6' : undefined }}
              >
                {a.type === 'measure' && (
                  <Tooltip
                    key={`tip-${selectMode}`}
                    permanent
                    direction="center"
                    className={selectMode ? 'measure-label measure-label-click' : 'measure-label'}
                    interactive={selectMode}
                    eventHandlers={
                      selectMode
                        ? {
                            // clicking the distance label opens the same rounding
                            // popup as clicking the line body (deferred a tick so
                            // Leaflet's close-on-click doesn't swallow it)
                            click: () => {
                              const ln = measureLineRefs.current[a.id]
                              if (ln) setTimeout(() => ln.openPopup(), 0)
                            },
                          }
                        : undefined
                    }
                  >
                    {label}
                  </Tooltip>
                )}
                {selectMode && a.type === 'measure' && (
                  <Popup>
                    <MeasureEditPopup
                      step={a.step ?? 0}
                      units={units}
                      onChange={(v) => onUpdateAnnotation(a.id, { step: v })}
                      onDelete={() => onDeleteAnnotation(a.id)}
                    />
                  </Popup>
                )}
              </Polyline>
              {(['a', 'b'] as const).map((k) => (
                <Marker
                  key={`${a.id}${k}-${selectMode}`}
                  position={[k === 'a' ? a.aLat : a.bLat, k === 'a' ? a.aLon : a.bLon]}
                  draggable={selectMode}
                  interactive={selectMode}
                  icon={handleIcon(a.color)}
                  eventHandlers={{
                    mousedown: () => {
                      draggingRef.current = true
                    },
                    click: (e) => {
                      draggingRef.current = false
                      // in select mode a measure endpoint opens its rounding
                      // editor (same popup as clicking the line body); while a
                      // drawing tool is active the click reuses the point
                      if (selectMode) {
                        if (a.type === 'measure') {
                          const mk = e.target as L.Marker
                          setTimeout(() => mk.openPopup(), 0)
                        }
                        return
                      }
                      handleClick({
                        lat: k === 'a' ? a.aLat : a.bLat,
                        lon: k === 'a' ? a.aLon : a.bLon,
                      })
                    },
                    dragend: (e) => {
                      draggingRef.current = false
                      setSnapHover(null)
                      const ll = (e.target as L.Marker).getLatLng()
                      const old =
                        k === 'a' ? { lat: a.aLat, lon: a.aLon } : { lat: a.bLat, lon: a.bLon }
                      onMovePoint(old, { lat: ll.lat, lon: ll.lng })
                    },
                  }}
                >
                  {selectMode && a.type === 'measure' && (
                    <Popup>
                      <MeasureEditPopup
                        step={a.step ?? 0}
                        units={units}
                        onChange={(v) => onUpdateAnnotation(a.id, { step: v })}
                        onDelete={() => onDeleteAnnotation(a.id)}
                      />
                    </Popup>
                  )}
                </Marker>
              ))}
            </Fragment>
          )
        })}

        {/* reusable snap targets: existing drawn points, clickable to reuse. the
            one the next click would snap onto (hover) or that was just snapped
            onto (pulse) is enlarged + highlighted so the snap is obvious */}
        {!selectMode &&
          snapPoints.map((sp, i) => {
            const active = i === snapHover || (!!snapPulse && sp.lat === snapPulse.lat && sp.lon === snapPulse.lon)
            return (
              <CircleMarker
                key={`snap-${i}`}
                center={[sp.lat, sp.lon]}
                radius={active ? 11 : 6}
                interactive={false}
                pathOptions={
                  active
                    ? { color, weight: 2, opacity: 1, fillColor: color, fillOpacity: 0.45 }
                    : { color: '#111', weight: 1, opacity: 0.5, fillColor: '#fff', fillOpacity: 0.4 }
                }
              />
            )
          })}

        {/* endpoints clicked for line/bisector are shown via the pending marker */}
        {pending && (
          <CircleMarker
            center={[pending.lat, pending.lon]}
            radius={5}
            pathOptions={{ color, weight: 2, fillColor: '#fff', fillOpacity: 1 }}
          />
        )}

        {pickedPoints.map((pp, i) => (
          <Marker key={i} position={[pp.point.lat, pp.point.lon]} icon={pin(pp.color)}>
            <Popup>{pp.label}</Popup>
          </Marker>
        ))}

        {/* transient coordinate-tool dot: shows the lat/lon, no annotation kept */}
        {tool === 'coord' && coordPin && (
          <CircleMarker
            center={[coordPin.lat, coordPin.lon]}
            radius={5}
            pathOptions={{ color: '#111', weight: 2, fillColor: '#fff', fillOpacity: 1 }}
          >
            <Tooltip permanent direction="top" offset={[0, -6]}>
              {coordPin.lat.toFixed(6)}, {coordPin.lon.toFixed(6)}
              {coordCopied ? ' ✓' : ''}
            </Tooltip>
          </CircleMarker>
        )}
      </MapContainer>
    </>
  )
}
