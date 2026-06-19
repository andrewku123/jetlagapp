import { useState } from 'react'
import {
  MapContainer,
  TileLayer,
  CircleMarker,
  Circle,
  Polyline,
  Popup,
  Tooltip,
  GeoJSON,
  useMapEvents,
  Marker,
} from 'react-leaflet'
import L from 'leaflet'
import type { Feature, Geometry } from 'geojson'
import type { Annotation, LatLng, QuestionRecord, Station, DrawTool } from '../types'
import { stationColor, isMultiSystem } from '../lib/style'
import { bisectorEndpoints, haversineMiles, formatMiles } from '../lib/geo'
import { RADAR_OPTIONS } from '../data/questions'
import { IN_PLAY_COUNTIES } from '../lib/playArea'
import countiesData from '../data/counties.geojson.json'
import transitData from '../data/transit-lines.geojson.json'

const COUNTIES = countiesData as unknown as GeoJSON.FeatureCollection
function countyStyle(feature?: Feature<Geometry, { name: string }>) {
  const inPlay = feature ? IN_PLAY_COUNTIES.has(feature.properties.name) : false
  return inPlay
    ? { stroke: false, fill: false, interactive: false }
    : { stroke: true, color: '#6b7280', weight: 1, fillColor: '#6b7280', fillOpacity: 0.35, interactive: false }
}

const TRANSIT = transitData as unknown as GeoJSON.FeatureCollection
function transitStyle(feature?: Feature<Geometry, { color: string }>) {
  return { color: feature?.properties.color ?? '#666', weight: 3, opacity: 0.9, interactive: false }
}

interface Props {
  remaining: Station[]
  eliminated: Station[]
  showEliminated: boolean
  starred: Set<string>
  onPickLocation: (p: LatLng) => void
  onStationClick: (st: Station) => void
  records: QuestionRecord[]
  pickedPoints: { label: string; point: LatLng; color: string }[]
  annotations: Annotation[]
  onAddAnnotation: (a: Annotation) => void
  onDeleteAnnotation: (id: string) => void
  onClearAnnotations: () => void
}

// length each side of the midpoint that a drawn line / bisector is extended (mi)
const LINE_LENGTH_MI = 60

const DRAW_COLORS = ['#e8590c', '#1971c2', '#2f9e44', '#9c36b5', '#0c0c0c']

function MapClicks({ onClick }: { onClick: (p: LatLng) => void }) {
  useMapEvents({
    click(e) {
      onClick({ lat: e.latlng.lat, lon: e.latlng.lng })
    },
  })
  return null
}

const pin = (color: string) =>
  L.divIcon({
    className: 'seeker-pin',
    html: `<div style="background:${color}" class="seeker-pin-dot"></div>`,
    iconSize: [16, 16],
    iconAnchor: [8, 8],
  })

const rid = () => Math.random().toString(36).slice(2, 9)

export default function MapView({
  remaining,
  eliminated,
  showEliminated,
  starred,
  onPickLocation,
  onStationClick,
  records,
  pickedPoints,
  annotations,
  onAddAnnotation,
  onDeleteAnnotation,
  onClearAnnotations,
}: Props) {
  const [tool, setTool] = useState<DrawTool>('select')
  const [radiusMi, setRadiusMi] = useState(1)
  const [color, setColor] = useState(DRAW_COLORS[0])
  // rounding step for the measure label: 0 = exact (2 dp), else snap to this many mi
  const [measureStep, setMeasureStep] = useState(0)
  // first click of a two-point line / bisector
  const [pending, setPending] = useState<LatLng | null>(null)

  function handleClick(p: LatLng) {
    if (tool === 'select') {
      onPickLocation(p)
      return
    }
    if (tool === 'compass') {
      onAddAnnotation({ id: rid(), type: 'circle', lat: p.lat, lon: p.lon, radiusMiles: radiusMi, color })
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
  }

  const toolNoun = tool === 'bisector' ? 'bisector' : tool === 'measure' ? 'measurement' : 'line'
  const hint =
    tool === 'select'
      ? 'Select: click drops a seeker point.'
      : tool === 'compass'
        ? `Compass: click a center to draw a ${radiusMi} mi circle.`
        : pending
          ? `Click the 2nd point to finish the ${toolNoun}.`
          : tool === 'measure'
            ? 'Measure: click two points to read the distance.'
            : `${tool === 'bisector' ? 'Bisector' : 'Line'}: click the 1st point.`

  return (
    <>
      <div className="draw-toolbar">
        <div className="draw-tools">
          {(['select', 'compass', 'line', 'bisector', 'measure'] as DrawTool[]).map((t) => (
            <button key={t} className={tool === t ? 'on' : ''} onClick={() => selectTool(t)} title={t}>
              {t === 'select' ? '✋' : t === 'compass' ? '⊙' : t === 'line' ? '／' : t === 'bisector' ? '⊥' : '📏'}
              <span>{t === 'select' ? 'Select' : t === 'compass' ? 'Compass' : t === 'line' ? 'Line' : t === 'bisector' ? 'Bisector' : 'Measure'}</span>
            </button>
          ))}
        </div>
        {tool === 'compass' && (
          <label className="draw-radius">
            radius
            <select value={radiusMi} onChange={(e) => setRadiusMi(Number(e.target.value))}>
              {RADAR_OPTIONS.map((r) => (
                <option key={r} value={r}>{r} mi</option>
              ))}
            </select>
          </label>
        )}
        {tool === 'measure' && (
          <label className="draw-radius">
            round
            <select value={measureStep} onChange={(e) => setMeasureStep(Number(e.target.value))}>
              <option value={0}>exact</option>
              <option value={0.5}>½ mi</option>
              <option value={1}>1 mi</option>
              <option value={5}>5 mi</option>
              <option value={10}>10 mi</option>
            </select>
          </label>
        )}
        {tool !== 'select' && (
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
        <div className="draw-hint">{hint}</div>
        {(annotations.length > 0 || pending) && (
          <div className="draw-actions">
            <button
              className="draw-undo"
              onClick={() => {
                if (pending) {
                  setPending(null)
                } else if (annotations.length > 0) {
                  onDeleteAnnotation(annotations[annotations.length - 1].id)
                }
              }}
            >
              ↩ Undo
            </button>
            {annotations.length > 0 && (
              <button className="draw-clear" onClick={onClearAnnotations}>
                Clear ({annotations.length})
              </button>
            )}
          </div>
        )}
      </div>

      <MapContainer center={[37.6, -122.2]} zoom={10} className="map" preferCanvas>
        <TileLayer
          attribution='&copy; OpenStreetMap contributors &copy; CARTO'
          url="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png"
          subdomains="abcd"
          maxZoom={20}
        />
        <MapClicks onClick={handleClick} />

        <GeoJSON data={COUNTIES} style={countyStyle as never} interactive={false} />
        <GeoJSON data={TRANSIT} style={transitStyle as never} interactive={false} />

        {showEliminated &&
          eliminated.map((st) => (
            <CircleMarker
              key={st.id}
              center={[st.lat, st.lon]}
              radius={5}
              pathOptions={{ color: '#9aa0a6', weight: 1, fillColor: '#9aa0a6', fillOpacity: 0.55 }}
            >
              <Popup>
                <div className="popup">
                  <strong>{st.name}</strong>
                  <div className="muted">{st.systems.join(' · ')}</div>
                  <div className="muted">Eliminated — restore from the Suspects list.</div>
                </div>
              </Popup>
            </CircleMarker>
          ))}

        {remaining.map((st) => {
          const c = stationColor(st)
          const star = starred.has(st.id)
          return (
            <CircleMarker
              key={st.id}
              center={[st.lat, st.lon]}
              radius={star ? 11 : 6}
              pathOptions={{
                color: star ? '#b8860b' : c,
                weight: star ? 3 : 1.5,
                fillColor: star ? '#f5b301' : c,
                fillOpacity: 0.9,
              }}
              eventHandlers={{ click: () => onStationClick(st) }}
            >
              <Popup>
                <div className="popup">
                  <strong>{st.name}</strong>
                  <div>{st.systems.join(' · ')}{isMultiSystem(st) ? ' (shared)' : ''}</div>
                  {st.lines.length > 0 && <div className="muted">{st.lines.join(', ')}</div>}
                  <div className="muted">
                    {st.city ?? '?'}, {st.county ?? '?'} Co. · {st.nameLength} chars
                    {st.elevation != null ? ` · ${Math.round(st.elevation)} m` : ''}
                  </div>
                  <div className="muted">Nearest airport: {st.nearestAirport}</div>
                  <button onClick={() => onStationClick(st)}>Actions…</button>
                </div>
              </Popup>
            </CircleMarker>
          )
        })}

        {records
          .filter((r) => r.active && r.eliminates && r.kind === 'radar')
          .map((r) => (
            <Circle
              key={r.id}
              center={[Number(r.params.lat), Number(r.params.lon)]}
              radius={Number(r.params.radiusMiles) * 1609.344}
              pathOptions={{
                color: r.params.answer === 'yes' ? '#1a7f37' : '#cf222e',
                weight: 1,
                fillOpacity: r.params.answer === 'yes' ? 0.06 : 0.04,
                dashArray: r.params.answer === 'yes' ? undefined : '4',
              }}
            />
          ))}

        {/* manual compass / straightedge annotations */}
        {annotations.map((a) => {
          if (a.type === 'circle') {
            return (
              <Circle
                key={a.id}
                center={[a.lat, a.lon]}
                radius={a.radiusMiles * 1609.344}
                pathOptions={{ color: a.color, weight: 2, fillOpacity: 0.05 }}
                eventHandlers={{ click: () => onDeleteAnnotation(a.id) }}
              >
                <Popup>
                  <div className="popup">
                    Compass circle · {a.radiusMiles} mi
                    <button onClick={() => onDeleteAnnotation(a.id)}>Delete</button>
                  </div>
                </Popup>
              </Circle>
            )
          }
          const endpoints =
            a.type === 'bisector'
              ? bisectorEndpoints({ lat: a.aLat, lon: a.aLon }, { lat: a.bLat, lon: a.bLon }, LINE_LENGTH_MI)
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
                ? formatMiles(miles!, a.step ?? 0)
                : 'Straightedge line'
          return (
            <Polyline
              key={a.id}
              positions={endpoints.map((p) => [p.lat, p.lon]) as [number, number][]}
              pathOptions={{ color: a.color, weight: 2, dashArray: a.type === 'bisector' ? '6 4' : a.type === 'measure' ? '2 6' : undefined }}
              eventHandlers={{ click: () => onDeleteAnnotation(a.id) }}
            >
              {a.type === 'measure' && (
                <Tooltip permanent direction="center" className="measure-label">
                  {label}
                </Tooltip>
              )}
              <Popup>
                <div className="popup">
                  {label}
                  <button onClick={() => onDeleteAnnotation(a.id)}>Delete</button>
                </div>
              </Popup>
            </Polyline>
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
      </MapContainer>
    </>
  )
}
