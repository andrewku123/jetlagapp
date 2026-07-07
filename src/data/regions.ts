import type { LatLng, QuestionKind, Station } from '../types'

// Region registry: the app is data-driven and region-agnostic — every question,
// the elimination engine, the map, the board code etc. read whatever the ACTIVE
// region supplies. A region is just a bundle of the same-shaped data files (see
// the add-transit-city skill). Adding a city = adding its data files + one entry
// here.
//
// The active region is chosen once per page load from localStorage (default =
// Bay Area). Switching regions persists the choice and reloads the page, so the
// module-level constants that many lib files derive from their region's data are
// simply recomputed on the fresh load — no giant reactive refactor needed, and
// switching maps can't leave stale cross-map state behind.

// --- Bay Area (the original map) -------------------------------------------
import baStations from './stations.json'
import baPoi from './poi.json'
import baPlayArea from './play-area.geojson.json'
import baMeasure from './measure-features.geojson.json'
import baPlaces from './places.geojson.json'
import baCounties from './counties.geojson.json'
import baZctas from './zctas.geojson.json'
import baTransit from './transit-lines.geojson.json'

// --- SF Muni (day-pass map: Muni rail lines J/K/L/M/N/T/F, SF county only) ---
import sfStations from './sfmuni.stations.json'
import sfPoi from './sfmuni.poi.json'
import sfPlayArea from './sfmuni.play-area.geojson.json'
import sfMeasure from './sfmuni.measure-features.geojson.json'
import sfPlaces from './sfmuni.places.geojson.json'
import sfCounties from './sfmuni.counties.geojson.json'
import sfZctas from './sfmuni.zctas.geojson.json'
import sfTransit from './sfmuni.transit-lines.geojson.json'

export interface RegionData {
  id: string
  /** Human-readable name; shown in the picker and baked into the board code. */
  name: string
  /** Initial map center [lat, lon]. */
  center: [number, number]
  /** Initial map zoom. */
  zoom: number
  /** 2nd-admin divisions that hold stations (used by county Matching + dim). */
  inPlayCounties: string[]
  stations: unknown
  poi: unknown
  playArea: unknown
  measureFeatures: unknown
  places: unknown
  counties: unknown
  zctas: unknown
  transitLines: unknown
}

export const REGIONS: RegionData[] = [
  {
    id: 'bayarea',
    name: 'Bay Area',
    center: [37.6, -122.2],
    zoom: 10,
    inPlayCounties: ['Alameda', 'Contra Costa', 'San Francisco', 'San Mateo', 'Santa Clara'],
    stations: baStations,
    poi: baPoi,
    playArea: baPlayArea,
    measureFeatures: baMeasure,
    places: baPlaces,
    counties: baCounties,
    zctas: baZctas,
    transitLines: baTransit,
  },
  {
    id: 'sfmuni',
    name: 'SF Muni',
    center: [37.76, -122.44],
    zoom: 12,
    inPlayCounties: ['San Francisco'],
    stations: sfStations,
    poi: sfPoi,
    playArea: sfPlayArea,
    measureFeatures: sfMeasure,
    places: sfPlaces,
    counties: sfCounties,
    zctas: sfZctas,
    transitLines: sfTransit,
  },
]

export const DEFAULT_REGION_ID = 'bayarea'
const STORAGE_KEY = 'bahs.region'

function readActiveId(): string {
  try {
    const v = localStorage.getItem(STORAGE_KEY)
    if (v && REGIONS.some((r) => r.id === v)) return v
  } catch {
    /* no localStorage (SSR / tests) → default */
  }
  return DEFAULT_REGION_ID
}

export const ACTIVE_REGION_ID = readActiveId()
export const ACTIVE_REGION: RegionData =
  REGIONS.find((r) => r.id === ACTIVE_REGION_ID) ?? REGIONS[0]

/** Persist the chosen region and reload so all region-derived data recomputes. */
export function setActiveRegion(id: string): void {
  if (id === ACTIVE_REGION_ID) return
  try {
    localStorage.setItem(STORAGE_KEY, id)
  } catch {
    /* ignore */
  }
  try {
    window.location.reload()
  } catch {
    /* ignore (tests) */
  }
}

// --- Convenience exports: the active region's data, consumed by the lib files ---
export const stationsData = ACTIVE_REGION.stations
export const poiData = ACTIVE_REGION.poi
export const playAreaData = ACTIVE_REGION.playArea
export const measureFeaturesData = ACTIVE_REGION.measureFeatures
export const placesData = ACTIVE_REGION.places
export const countiesData = ACTIVE_REGION.counties
export const zctasData = ACTIVE_REGION.zctas
export const transitLinesData = ACTIVE_REGION.transitLines
export const IN_PLAY_COUNTIES = new Set<string>(ACTIVE_REGION.inPlayCounties)
export const MAP_NAME = ACTIVE_REGION.name

// Transit agencies present on the active map. On a single-agency map (e.g. SF
// Muni, where every station is "Muni") per-station agency chips are just noise,
// so UI can suppress them; on a multi-agency map (Bay Area) they're useful.
export const AGENCIES: string[] = [
  ...new Set(
    (ACTIVE_REGION.stations as { systems?: string[] }[]).flatMap((s) => s.systems ?? []),
  ),
]
export const SINGLE_AGENCY = AGENCIES.length <= 1
export const MAP_CENTER = ACTIVE_REGION.center
export const MAP_ZOOM = ACTIVE_REGION.zoom

// Commercial airports the "nearest airport" questions measure from (each one's
// Google-Maps pin). The game rule "anything outside the play area is treated as
// if it doesn't exist" applies here: an airport off the active map is not a
// valid answer, so only airports INSIDE the play area count. Bay Area contains
// SFO/OAK/SJC; SF Muni (San Francisco only) contains none — so on SF Muni the
// airport questions are demoted to log-only below.
const AIRPORT_SITES: Record<string, LatLng> = {
  SFO: { lat: 37.619083, lon: -122.381597 },
  OAK: { lat: 37.719016, lon: -122.219595 },
  SJC: { lat: 37.36351, lon: -121.928648 },
}
function pointInPlayArea(p: LatLng): boolean {
  const fc = playAreaData as unknown as {
    features: { geometry: { type: string; coordinates: number[][][] | number[][][][] } }[]
  }
  const inRing = (x: number, y: number, ring: number[][]): boolean => {
    let inside = false
    for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
      const xi = ring[i][0]
      const yi = ring[i][1]
      const xj = ring[j][0]
      const yj = ring[j][1]
      if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = !inside
    }
    return inside
  }
  const inPoly = (x: number, y: number, poly: number[][][]): boolean => {
    if (poly.length === 0 || !inRing(x, y, poly[0])) return false
    for (let h = 1; h < poly.length; h++) if (inRing(x, y, poly[h])) return false
    return true
  }
  for (const f of fc.features) {
    const g = f.geometry
    if (g.type === 'Polygon') {
      if (inPoly(p.lon, p.lat, g.coordinates as number[][][])) return true
    } else if (g.type === 'MultiPolygon') {
      for (const poly of g.coordinates as number[][][][]) if (inPoly(p.lon, p.lat, poly)) return true
    }
  }
  return false
}
// Airports that actually exist on the active map (inside its play area).
export const AIRPORTS: Record<string, LatLng> = Object.fromEntries(
  Object.entries(AIRPORT_SITES).filter(([, p]) => pointInPlayArea(p)),
)
export const HAS_AIRPORTS = Object.keys(AIRPORTS).length > 0

// Normally-eliminating questions that are useless on the active map, demoted to
// log-only (still recorded for the seeker's notes, but they shade/eliminate
// nothing). Two reasons a question is useless here:
//  - every in-play station shares one value, so "same as mine?" can't split the
//    set (county/city/line Matching on a single-county / single-line map); or
//  - the feature it measures doesn't exist in the play area (no in-play airport
//    on SF Muni, so nearest-airport Matching and Measuring can't discriminate).
// Derived from the active region's own data so it stays correct for any future
// map with no hand-maintained list.
const logOnlyStations = ACTIVE_REGION.stations as Station[]
function distinctValueCount(vals: (string | number | null)[]): number {
  return new Set(vals.filter((v) => v != null && v !== '')).size
}
export const LOG_ONLY_KINDS: ReadonlySet<QuestionKind> = new Set<QuestionKind>(
  (
    [
      [distinctValueCount(logOnlyStations.map((s) => s.county)) <= 1, 'match-county'],
      [distinctValueCount(logOnlyStations.map((s) => s.city)) <= 1, 'match-city'],
      [distinctValueCount(logOnlyStations.flatMap((s) => s.lines)) <= 1, 'match-line'],
      // No airport exists in the play area → these can't discriminate at all.
      [!HAS_AIRPORTS, 'match-airport'],
      [!HAS_AIRPORTS, 'measure-airport'],
    ] as [boolean, QuestionKind][]
  )
    .filter(([useless]) => useless)
    .map(([, kind]) => kind),
)
