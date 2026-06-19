export type DayType = 'wd' | 'we'

export interface ServiceFlags {
  served: boolean
  hourly: boolean
}

export interface Station {
  id: string
  name: string
  lat: number
  lon: number
  systems: string[]
  lines: string[]
  aka: string[]
  nameLength: number
  county: string | null
  city: string | null
  elevation: number | null
  airportDist: Record<string, number>
  nearestAirport: string
  service: { wd: ServiceFlags; we: ServiceFlags }
}

export interface LatLng {
  lat: number
  lon: number
}

// A logged question + answer. `kind` selects the predicate used to filter stations.
export type QuestionKind =
  | 'radar'
  | 'thermometer'
  | 'match-county'
  | 'match-city'
  | 'match-airport'
  | 'match-namelength'
  | 'match-line'
  | 'measure-airport'
  | 'measure-sealevel'
  | 'photo'

export interface QuestionRecord {
  id: string
  kind: QuestionKind
  createdAt: number
  // generic params bag; interpreted per kind
  params: Record<string, unknown>
  note?: string
  // photo questions don't auto-eliminate
  eliminates: boolean
  // whether this record is active in the filter
  active: boolean
}

// Manual compass / straightedge annotations the seeker draws on the map.
export type DrawTool = 'select' | 'compass' | 'line' | 'bisector' | 'measure'

export interface CircleAnnotation {
  id: string
  type: 'circle'
  lat: number
  lon: number
  radiusMiles: number
  color: string
}

export interface LineAnnotation {
  id: string
  type: 'line' | 'bisector' | 'measure'
  aLat: number
  aLon: number
  bLat: number
  bLon: number
  color: string
  // measure only: rounding step in miles (0 = exact). e.g. 1 snaps to whole miles
  step?: number
}

export type Annotation = CircleAnnotation | LineAnnotation

export type UnitSystem = 'imperial' | 'metric'

export interface GameState {
  dayType: DayType
  hourlyOnly: boolean
  units: UnitSystem
  questions: QuestionRecord[]
  manualEliminated: string[] // station ids eliminated by hand
  starred: string[] // station ids flagged as suspects
  notes: Record<string, string> // station id -> note
  annotations: Annotation[] // compass / straightedge drawings
}
