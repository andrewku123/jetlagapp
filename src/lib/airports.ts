import type { LatLng } from '../types'

// Commercial airports inside the play area (the three with scheduled passenger
// flights across SF / San Mateo / Alameda / Contra Costa / Santa Clara).
// Coordinates are each airport's Google Maps pin/icon (the point the official
// game rules measure from). Keep in sync with scripts/build_attributes.py.
export const AIRPORTS: Record<string, LatLng> = {
  SFO: { lat: 37.619083, lon: -122.381597 },
  OAK: { lat: 37.719016, lon: -122.219595 },
  SJC: { lat: 37.363510, lon: -121.928648 },
}
