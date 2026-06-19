import { Fragment, useState } from 'react'
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
  Marker,
} from 'react-leaflet'
import L from 'leaflet'
import type { Feature, Geometry } from 'geojson'
import type { Annotation, LatLng, QuestionRecord, Station, DrawTool, UnitSystem } from '../types'
import { stationColor, isMultiSystem } from '../lib/style'
import { bisectorEndpoints, circlePolygon, haversineMiles, formatDistance, formatElevation } from '../lib/geo'
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

interface TransitWay {
  type: 'Feature'
  properties: { system: string; colors: string[] }
  geometry: { type: 'LineString'; coordinates: number[][] }
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

interface Props {
  remaining: Station[]
  eliminated: Station[]
  showEliminated: boolean
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
  onClearAnnotations: () => void
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
  onClearAnnotations,
}: Props) {
  const [tool, setTool] = useState<DrawTool>('select')
  // stations are only clickable in select mode; in draw modes clicks pass
  // through to the map so you can snap a point/endpoint onto a station
  const selectMode = tool === 'select'
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
              <option value={0.5}>½ {units === 'metric' ? 'km' : 'mi'}</option>
              <option value={1}>1 {units === 'metric' ? 'km' : 'mi'}</option>
              <option value={5}>5 {units === 'metric' ? 'km' : 'mi'}</option>
              <option value={10}>10 {units === 'metric' ? 'km' : 'mi'}</option>
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
            const ends = bisectorEndpoints(from, to, LINE_LENGTH_MI)
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
            const longEdge = bisectorEndpoints(from, to, 300)
            const dLat = coldSide.lat - mid.lat
            const dLon = coldSide.lon - mid.lon
            const dLen = Math.hypot(dLat, dLon) || 1
            const off = { lat: (dLat / dLen) * 8, lon: (dLon / dLen) * 8 }
            const coldBand: [number, number][] = [
              [longEdge[0].lat, longEdge[0].lon],
              [longEdge[1].lat, longEdge[1].lon],
              [longEdge[1].lat + off.lat, longEdge[1].lon + off.lon],
              [longEdge[0].lat + off.lat, longEdge[0].lon + off.lon],
            ]
            return (
              <Fragment key={r.id}>
                <Polygon positions={coldBand} pathOptions={ELIM_FILL} />
                <Polyline
                  positions={ends.map((p) => [p.lat, p.lon]) as [number, number][]}
                  interactive={false}
                  pathOptions={{ color: '#7c3aed', weight: 2.5, dashArray: '6 4' }}
                />
                <CircleMarker
                  center={[hotMark.lat, hotMark.lon]}
                  radius={6}
                  interactive={false}
                  pathOptions={{ color: '#cf222e', weight: 2, fillColor: '#cf222e', fillOpacity: 0.85 }}
                >
                  <Tooltip permanent direction="top" offset={[0, -6]}>
                    hotter
                  </Tooltip>
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
                <CircleMarker
                  center={[a.lat, a.lon]}
                  radius={4}
                  pathOptions={{ color: a.color, weight: 2, fillColor: a.color, fillOpacity: 1 }}
                  eventHandlers={{ click: () => onDeleteAnnotation(a.id) }}
                />
                <CircleMarker
                  center={[a.lat, a.lon]}
                  radius={9}
                  pathOptions={{ stroke: false, fillOpacity: 0 }}
                  eventHandlers={{ click: () => onDeleteAnnotation(a.id) }}
                />
              </Fragment>
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
                ? formatDistance(miles!, units, a.step ?? 0)
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
