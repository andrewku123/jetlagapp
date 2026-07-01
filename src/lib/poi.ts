import poiData from '../data/poi.json'
import type { LatLng } from '../types'
import { haversineMiles } from './geo'

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
  { key: 'stadium', label: 'Sports stadiums', color: '#00897b' },
  { key: 'mountain', label: 'Mountains', color: '#607d8b' },
  { key: 'consulate', label: 'Consulates', color: '#5e35b1' },
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

// Categories offered by the POI Matching / Measuring questions (every Medium-deck
// subject we have data for). Order = the dropdown order in the ask form, grouped
// natural → places of interest → public utilities. Sparser categories are the
// stronger map-cutters (a 2-aquarium map splits cleanly in half), so they are
// deliberately kept rather than hidden.
export const QUESTION_POI_CATEGORIES: string[] = [
  'park',
  'mountain',
  'museum',
  'movie_theater',
  'golf_course',
  'amusement_park',
  'zoo',
  'aquarium',
  'stadium',
  'hospital',
  'library',
  'consulate',
]

const CATEGORY_LABEL: Record<string, string> = Object.fromEntries(
  POI_CATEGORIES.map((c) => [c.key, c.label]),
)

// Singular label for a category, for question prompts ("your nearest museum").
// Handles the "-ies" plural (Libraries → library) before the plain "-s" strip.
export function poiCategoryLabel(key: string): string {
  const plural = CATEGORY_LABEL[key] ?? key
  const singular = plural.endsWith('ies')
    ? plural.slice(0, -3) + 'y'
    : plural.replace(/s$/, '')
  return singular.toLowerCase()
}

// A stable identity for a POI (name + rounded coords) so two independent
// "nearest" computations agree on whether they landed on the same place.
export function poiKey(p: { name: string; lat: number; lon: number }): string {
  return `${p.name}|${p.lat.toFixed(5)}|${p.lon.toFixed(5)}`
}

// The nearest POI (straight-line) of `categoryKey` to `p`, or null if none.
export function nearestPoi(p: LatLng, categoryKey: string): PoiPlace | null {
  const list = POI_BY_CATEGORY[categoryKey]
  if (!list || list.length === 0) return null
  let best = list[0]
  let bestD = haversineMiles(p, best)
  for (let i = 1; i < list.length; i++) {
    const d = haversineMiles(p, list[i])
    if (d < bestD) {
      bestD = d
      best = list[i]
    }
  }
  return best
}

// Straight-line miles from `p` to the nearest POI of `categoryKey` (NaN if none).
export function nearestPoiMiles(p: LatLng, categoryKey: string): number {
  const b = nearestPoi(p, categoryKey)
  return b ? haversineMiles(p, b) : NaN
}
