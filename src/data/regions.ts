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

// --- LA Metro (Metro Rail A/B/C/D/E/K + Busway G/J, Los Angeles County) -------
// POI is not gathered yet, so la.poi.json ships every category empty: the POI
// Matching/Measuring/Tentacle questions auto-demote to log-only (POI_COUNTS===0)
// until the POI dataset lands in a follow-up.
import laStations from './la.stations.json'
import laPoi from './la.poi.json'
import laPlayArea from './la.play-area.geojson.json'
import laMeasure from './la.measure-features.geojson.json'
import laPlaces from './la.places.geojson.json'
import laCounties from './la.counties.geojson.json'
import laZctas from './la.zctas.geojson.json'
import laTransit from './la.transit-lines.geojson.json'
import laWater from './la.water.geojson.json'

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
  /** Optional cosmetic water overlay (ocean/lakes/rivers); no game logic. */
  water?: unknown
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
  {
    id: 'la',
    name: 'LA Metro',
    center: [34.05, -118.25],
    zoom: 10,
    inPlayCounties: ['Los Angeles'],
    stations: laStations,
    poi: laPoi,
    playArea: laPlayArea,
    measureFeatures: laMeasure,
    places: laPlaces,
    counties: laCounties,
    zctas: laZctas,
    transitLines: laTransit,
    water: laWater,
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
export const waterData = ACTIVE_REGION.water
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
  LAX: { lat: 33.94256, lon: -118.40853 },
  LGB: { lat: 33.81765, lon: -118.15227 },
}
interface NamedFeature {
  properties?: { name?: string }
  geometry: { type: string; coordinates: number[][][] | number[][][][] }
}
function inRing(x: number, y: number, ring: number[][]): boolean {
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
function inPoly(x: number, y: number, poly: number[][][]): boolean {
  if (poly.length === 0 || !inRing(x, y, poly[0])) return false
  for (let h = 1; h < poly.length; h++) if (inRing(x, y, poly[h])) return false
  return true
}
function featureContains(f: NamedFeature, p: LatLng): boolean {
  const g = f.geometry
  if (g.type === 'Polygon') return inPoly(p.lon, p.lat, g.coordinates as number[][][])
  if (g.type === 'MultiPolygon')
    for (const poly of g.coordinates as number[][][][]) if (inPoly(p.lon, p.lat, poly)) return true
  return false
}
function pointInPlayArea(p: LatLng): boolean {
  const fc = playAreaData as unknown as { features: NamedFeature[] }
  for (const f of fc.features) if (featureContains(f, p)) return true
  return false
}
// Airports that actually exist on the active map (inside its play area).
export const AIRPORTS: Record<string, LatLng> = Object.fromEntries(
  Object.entries(AIRPORT_SITES).filter(([, p]) => pointInPlayArea(p)),
)
export const HAS_AIRPORTS = Object.keys(AIRPORTS).length > 0

// A lon/lat frame that comfortably wraps the active play area, used to bound
// half-plane shading (e.g. the airport-match Voronoi cell) so it renders as a
// sane polygon instead of a world-spanning bowtie. Derived from the region's own
// station spread (+ padding) so it follows whatever map is active — a hardcoded
// box would misplace the shading on any other region.
const REGION_LATS = (ACTIVE_REGION.stations as LatLng[]).map((s) => s.lat)
const REGION_LONS = (ACTIVE_REGION.stations as LatLng[]).map((s) => s.lon)
const FRAME_PAD = 1.5 // degrees (~100 mi) of slack past the outermost station
export const REGION_FRAME = {
  minLat: Math.min(...REGION_LATS) - FRAME_PAD,
  maxLat: Math.max(...REGION_LATS) + FRAME_PAD,
  minLon: Math.min(...REGION_LONS) - FRAME_PAD,
  maxLon: Math.max(...REGION_LONS) + FRAME_PAD,
}

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
const singleCounty = distinctValueCount(logOnlyStations.map((s) => s.county)) <= 1
const singleCity = distinctValueCount(logOnlyStations.map((s) => s.city)) <= 1
const singleLine = distinctValueCount(logOnlyStations.flatMap((s) => s.lines)) <= 1

// Geometry-derived: does ANY station's endgame hiding disk straddle a
// county/city boundary into a DIFFERENT named area? A single-county (or
// single-city) map still lets "same county/city?" carve the endgame zone IF a
// border station's disk crosses the line (e.g. SF Muni's Bayshore disk reaching
// into San Mateo / Brisbane). But if every disk sits wholly inside one area
// (e.g. LA Metro — nearest station is ~3 km from the LA County line, far beyond
// the 0.25 mi disk), the boundary can never carve, so the question is useless in
// BOTH phases → full log-only, not endgame-only. Derived from each region's own
// polygons + station coords, so no hand-maintained per-map list.
const ENDGAME_RADIUS_MI = 0.25
function nameAt(fc: { features: NamedFeature[] }, p: LatLng): string | null {
  for (const f of fc.features) if (featureContains(f, p)) return f.properties?.name ?? null
  return null
}
function boundaryCarves(
  fc: { features: NamedFeature[] },
  ownNameOf: (s: Station) => string | null,
): boolean {
  const N = 24
  for (const s of logOnlyStations) {
    const own = ownNameOf(s)
    if (own == null) continue
    const dLat = ENDGAME_RADIUS_MI / 69.0
    const dLon = ENDGAME_RADIUS_MI / (69.0 * Math.cos((s.lat * Math.PI) / 180))
    for (let i = 0; i < N; i++) {
      const a = (2 * Math.PI * i) / N
      const p = { lat: s.lat + dLat * Math.sin(a), lon: s.lon + dLon * Math.cos(a) }
      const other = nameAt(fc, p)
      if (other != null && other !== own) return true
    }
  }
  return false
}
const countiesFc = countiesData as unknown as { features: NamedFeature[] }
const placesFc = placesData as unknown as { features: NamedFeature[] }
// Place polygons carry a "<name> city"/"…CDP" suffix while Station.city stores
// the same suffixed value, so compare against the polygon name directly.
const countyCarves = singleCounty && boundaryCarves(countiesFc, (s) => s.county ?? null)
const cityCarves = singleCity && boundaryCarves(placesFc, (s) => s.city ?? null)

// Always log-only: the question can't help in the regular game OR the endgame.
//  - single-line: every station is on the same line (a non-spatial attribute, so
//    it can't carve the endgame hiding zone either).
//  - airport: no airport exists anywhere in play, so there's nothing to match or
//    measure in either phase.
//  - single-county / single-city whose boundary no disk can reach: the value is
//    uniform AND spatially unreachable, so it's dead in both phases (LA Metro's
//    county Matching — every station sits deep inside LA County).
export const LOG_ONLY_KINDS: ReadonlySet<QuestionKind> = new Set<QuestionKind>(
  (
    [
      [singleLine, 'match-line'],
      [!HAS_AIRPORTS, 'match-airport'],
      [!HAS_AIRPORTS, 'measure-airport'],
      [singleCounty && !countyCarves, 'match-county'],
      [singleCity && !cityCarves, 'match-city'],
    ] as [boolean, QuestionKind][]
  )
    .filter(([useless]) => useless)
    .map(([, kind]) => kind),
)

// Log-only in the *regular* game but still fully eliminating in the *endgame*.
// County/city Matching can't split a single-county / single-city station list,
// but the county/city boundary is spatial: a border station's 0.25 mi hiding
// zone can straddle it (e.g. Sunnydale/Bayshore across the SF↔San Mateo line),
// so "same county/city?" carves the endgame zone. We only demote these to
// endgame-only (not full log-only) when a disk actually crosses the boundary
// (countyCarves / cityCarves); otherwise they fall to full log-only above.
export const ENDGAME_ELIMINATES_KINDS: ReadonlySet<QuestionKind> = new Set<QuestionKind>(
  (
    [
      [singleCounty && countyCarves, 'match-county'],
      [singleCity && cityCarves, 'match-city'],
    ] as [boolean, QuestionKind][]
  )
    .filter(([endgameOnly]) => endgameOnly)
    .map(([, kind]) => kind),
)
