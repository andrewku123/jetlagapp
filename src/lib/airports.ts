import type { LatLng } from '../types'

// Commercial airports inside the play area (the three with scheduled passenger
// flights across SF / San Mateo / Alameda / Contra Costa / Santa Clara).
export const AIRPORTS: Record<string, LatLng> = {
  SFO: { lat: 37.6213, lon: -122.379 },
  OAK: { lat: 37.7126, lon: -122.2197 },
  SJC: { lat: 37.3639, lon: -121.9289 },
}
