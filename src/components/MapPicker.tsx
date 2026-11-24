import { useState, type ReactNode } from 'react'
import { ACTIVE_REGION_ID, NEEDS_MAP_PICK, REGIONS, rememberRegion, setActiveRegion } from '../data/regions'

// First-visit home screen: choose a map before the app opens. Later loads go
// straight to the last map used (see resolveActiveRegion).
export function MapPicker({ children }: { children: ReactNode }) {
  const [picked, setPicked] = useState(!NEEDS_MAP_PICK)

  if (picked) return <>{children}</>

  function pick(id: string) {
    if (id === ACTIVE_REGION_ID) {
      rememberRegion(id)
      setPicked(true)
    } else {
      setActiveRegion(id)
    }
  }

  return (
    <div className="map-picker">
      <h1>Hide &amp; Seek</h1>
      <p>Pick a map. You can switch anytime under ⚙ in the top bar (on a computer, use the map menu there).</p>
      <div className="map-picker-list">
        {REGIONS.map((r) => (
          <button key={r.id} type="button" onClick={() => pick(r.id)}>
            <span className="map-picker-name">{r.name}</span>
            <span className="map-picker-meta">{(r.stations as unknown[]).length} stations</span>
          </button>
        ))}
      </div>
    </div>
  )
}
