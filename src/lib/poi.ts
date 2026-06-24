import poiData from '../data/poi.json'

// One entry per gathered POI category. `key` matches the keys in poi.json
// (the Google primaryType family); `color` is the dot color on the map.
export interface PoiCategory {
  key: string
  label: string
  color: string
}

// Display/legend order. Tentacle radius categories first, then the
// matching/measuring-only ones (park, golf).
export const POI_CATEGORIES: PoiCategory[] = [
  { key: 'museum', label: 'Museums', color: '#9c27b0' },
  { key: 'library', label: 'Libraries', color: '#1e88e5' },
  { key: 'movie_theater', label: 'Movie theaters', color: '#fb8c00' },
  { key: 'hospital', label: 'Hospitals', color: '#e53935' },
  { key: 'zoo', label: 'Zoos', color: '#6d4c41' },
  { key: 'aquarium', label: 'Aquariums', color: '#00acc1' },
  { key: 'amusement_park', label: 'Amusement parks', color: '#d81b60' },
  { key: 'park', label: 'Parks', color: '#43a047' },
  { key: 'golf_course', label: 'Golf courses', color: '#c0ca33' },
]

export interface PoiPlace {
  name: string
  lat: number
  lon: number
  type: string
  reviews: number
}

interface RawPoi {
  n: string
  lat: number
  lon: number
  t: string
  r: number
}

const RAW = poiData as unknown as Record<string, RawPoi[]>

export const POI_BY_CATEGORY: Record<string, PoiPlace[]> = Object.fromEntries(
  POI_CATEGORIES.map((c) => [
    c.key,
    (RAW[c.key] ?? []).map((p) => ({ name: p.n, lat: p.lat, lon: p.lon, type: p.t, reviews: p.r })),
  ]),
)

export const POI_COUNTS: Record<string, number> = Object.fromEntries(
  POI_CATEGORIES.map((c) => [c.key, POI_BY_CATEGORY[c.key].length]),
)

// A single POI ready to draw: its category color/label folded in.
export interface RenderPoi extends PoiPlace {
  categoryKey: string
  label: string
  color: string
}
