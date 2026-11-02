import type { DayType, Station } from '../types'
import { WEEKDAY_EXCLUDED_LINES } from '../data/regions'

// Dot color for an agency with no entry below — which is every single-agency
// map, where one color reads better than a per-line dot under the per-line
// colored overlay. A new city needs no edit here.
export const DEFAULT_SYSTEM_COLOR = '#7b2d8b'

export const SYSTEM_COLORS: Record<string, string> = {
  BART: '#0066cc',
  Caltrain: '#d4001a',
  VTA: '#f5821f',
  Muni: DEFAULT_SYSTEM_COLOR,
  'SFO AirTrain': '#00897b',
  'Water Shuttle': '#c2185b',
  Metro: DEFAULT_SYSTEM_COLOR,
  Metrorail: DEFAULT_SYSTEM_COLOR,
}

export const SYSTEM_ORDER = ['BART', 'Caltrain', 'VTA', 'Muni', 'SFO AirTrain', 'Water Shuttle', 'Metro', 'Metrorail']

// Lines that don't run on weekends; hidden from the transit-line question in
// Weekend mode. Caltrain Express ("Baby Bullet") and Limited are weekday-only.
export const WEEKEND_EXCLUDED_LINES = ['Caltrain Express', 'Caltrain Limited']

// Lines that don't count on the given day type: the weekday-only lines on a
// weekend, the weekend-only lines (RegionData.weekdayExcludedLines) on a weekday.
export function linesExcludedOn(day: DayType): string[] {
  return day === 'we' ? WEEKEND_EXCLUDED_LINES : WEEKDAY_EXCLUDED_LINES
}

export function stationColor(st: Station): string {
  // primary color = first system in canonical order
  for (const sys of SYSTEM_ORDER) {
    if (st.systems.includes(sys)) return SYSTEM_COLORS[sys]
  }
  return DEFAULT_SYSTEM_COLOR
}

export function isMultiSystem(st: Station): boolean {
  return st.systems.length > 1
}
