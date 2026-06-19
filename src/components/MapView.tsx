import { MapContainer, TileLayer, CircleMarker, Circle, Popup, useMapEvents, Marker } from 'react-leaflet'
import L from 'leaflet'
import type { LatLng, QuestionRecord, Station } from '../types'
import { stationColor, isMultiSystem } from '../lib/style'

interface Props {
  remaining: Station[]
  eliminated: Station[]
  showEliminated: boolean
  starred: Set<string>
  onPickLocation: (p: LatLng) => void
  onStationClick: (st: Station) => void
  records: QuestionRecord[]
  pickedPoints: { label: string; point: LatLng; color: string }[]
}

function ClickHandler({ onPick }: { onPick: (p: LatLng) => void }) {
  useMapEvents({
    click(e) {
      onPick({ lat: e.latlng.lat, lon: e.latlng.lng })
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

export default function MapView({
  remaining,
  eliminated,
  showEliminated,
  starred,
  onPickLocation,
  onStationClick,
  records,
  pickedPoints,
}: Props) {
  return (
    <MapContainer center={[37.6, -122.2]} zoom={10} className="map" preferCanvas>
      <TileLayer
        attribution='&copy; OpenStreetMap contributors'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      <ClickHandler onPick={onPickLocation} />

      {showEliminated &&
        eliminated.map((st) => (
          <CircleMarker
            key={st.id}
            center={[st.lat, st.lon]}
            radius={3}
            pathOptions={{ color: '#bbb', weight: 1, fillColor: '#ddd', fillOpacity: 0.4 }}
          />
        ))}

      {remaining.map((st) => {
        const color = stationColor(st)
        const star = starred.has(st.id)
        return (
          <CircleMarker
            key={st.id}
            center={[st.lat, st.lon]}
            radius={star ? 8 : 6}
            pathOptions={{
              color: star ? '#000' : color,
              weight: star ? 3 : 1.5,
              fillColor: color,
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

      {pickedPoints.map((pp, i) => (
        <Marker key={i} position={[pp.point.lat, pp.point.lon]} icon={pin(pp.color)}>
          <Popup>{pp.label}</Popup>
        </Marker>
      ))}
    </MapContainer>
  )
}
