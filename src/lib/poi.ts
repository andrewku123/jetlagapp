import { poiData } from '../data/regions'
import type { LatLng } from '../types'
import type { GameSize } from '../data/questionSets'
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
  { key: 'consulate', label: 'Foreign consulates', color: '#5e35b1' },
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

// Tentacle categories: "of all the ___ within R of me, which are you closest to?"
// Radius is fixed per category and the card is size-gated (never in small games):
// the 1-mile set is Medium+, the 15-mile set is Large only. (Metro Lines — a
// line-based 15-mile Large tentacle — is handled separately, not here.)
export interface TentacleCategory {
  key: string
  radiusMi: number
  sizes: GameSize[]
}

const MED_PLUS: GameSize[] = ['medium', 'large']
const LARGE_ONLY: GameSize[] = ['large']

export const TENTACLE_CATEGORIES: TentacleCategory[] = [
  { key: 'museum', radiusMi: 1, sizes: MED_PLUS },
  { key: 'library', radiusMi: 1, sizes: MED_PLUS },
  { key: 'movie_theater', radiusMi: 1, sizes: MED_PLUS },
  { key: 'hospital', radiusMi: 1, sizes: MED_PLUS },
  { key: 'zoo', radiusMi: 15, sizes: LARGE_ONLY },
  { key: 'aquarium', radiusMi: 15, sizes: LARGE_ONLY },
  { key: 'amusement_park', radiusMi: 15, sizes: LARGE_ONLY },
]

export function tentacleCategory(key: string): TentacleCategory | null {
  return TENTACLE_CATEGORIES.find((c) => c.key === key) ?? null
}

// Sentinel tentacle answers used in place of an in-range POI/line name when the
// hider reveals only whether they are within the radius of the seeker. These
// make a tentacle behave exactly like a radar centred on the seeker:
//   OUTSIDE ("not within R") = radar "no"  → the disk of radius R is eliminated.
//   INSIDE  ("within R")     = radar "yes" → everything outside the disk is.
// The seeker uses INSIDE/OUTSIDE when only one POI is in the circle (the
// closest-POI answer is then useless), and OUTSIDE is always offered as an
// alternative answer. Stored as params.value on a tentacle / tentacle-line
// record so elimination and shading recognise it.
export const TENTACLE_OUTSIDE = '__outside__'
export const TENTACLE_INSIDE = '__inside__'
export function isTentacleRadarAnswer(v: string): boolean {
  return v === TENTACLE_OUTSIDE || v === TENTACLE_INSIDE
}

// Every POI of `categoryKey` whose straight-line distance to `p` is <= radiusMi.
// These are the only POIs "in play" for a Tentacle from `p`; anything outside the
// radius does not count even if it is closer to the hider.
export function poisWithinRadius(p: LatLng, categoryKey: string, radiusMi: number): PoiPlace[] {
  const list = POI_BY_CATEGORY[categoryKey]
  if (!list) return []
  return list.filter((poi) => haversineMiles(p, poi) <= radiusMi)
}

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

// Plural label for a category, lowercased for mid-sentence use ("libraries",
// "movie theaters"). Uses the stored plural so "library" doesn't become the
// naive "librarys"; capitalize at call sites that need a leading capital.
export function poiCategoryLabelPlural(key: string): string {
  return (CATEGORY_LABEL[key] ?? `${key}s`).toLowerCase()
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
