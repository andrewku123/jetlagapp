import { zoneElevData } from '../data/regions'

// Lowest / highest in-play ground within each preset hiding-zone radius around
// every station, from USGS-derived terrain (scripts/build_zone_elevation.py).
// A zone between presets uses the next larger one, so the range can only be
// too wide (keeps a station), never too narrow.

interface ZoneElevFile {
  bandsMi: number[]
  stations: Record<string, [number, number][]>
}

// Terrain tiles and the USGS point service the seeker reads from differ by a
// metre or two, and a pixel grid can step over the very top of a crest.
export const ZONE_ELEV_MARGIN_M = 3

const DATA = zoneElevData as ZoneElevFile

export function zoneElevationRange(stationId: string, zoneMi: number): { min: number; max: number } | null {
  const bands = DATA.stations[stationId]
  if (!bands) return null
  const i = DATA.bandsMi.findIndex((b) => b >= zoneMi - 1e-9)
  if (i < 0 || !bands[i]) return null
  const [min, max] = bands[i]
  return { min: min - ZONE_ELEV_MARGIN_M, max: max + ZONE_ELEV_MARGIN_M }
}
