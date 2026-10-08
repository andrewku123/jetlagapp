import type { LatLng } from '../types'

// Ground elevation (m) at a point from the USGS Elevation Point Query Service —
// the same 3DEP terrain the station elevations and zone ranges are built from,
// so the seeker's number and the hider's zone are on one scale. US only; null
// when the point has no data or the service is unreachable.
export async function usgsGroundElevationM(p: LatLng, signal?: AbortSignal): Promise<number | null> {
  const url = `https://epqs.nationalmap.gov/v1/json?x=${p.lon}&y=${p.lat}&units=Meters&wkid=4326&includeDate=false`
  try {
    const res = await fetch(url, { signal })
    if (!res.ok) return null
    const body = (await res.json()) as { value?: unknown }
    const v = Number(body.value)
    // EPQS reports -1000000 for "no data"
    return Number.isFinite(v) && v > -1000 ? v : null
  } catch {
    return null
  }
}
