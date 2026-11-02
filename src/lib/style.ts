import type { Station } from '../types'

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
  Metro: DEFAULT_SYSTEM_COLOR,
  Metrorail: DEFAULT_SYSTEM_COLOR,
  Subway: '#0039a6',
  SIR: '#1d2f6f',
  LIRR: '#00985f',
  'NYC Ferry': '#ff6b00',
  'Staten Island Ferry': '#f58220',
  'Roosevelt Island Tram': '#c60c30',
}

export const SYSTEM_ORDER = ['BART', 'Caltrain', 'VTA', 'Muni', 'SFO AirTrain', 'Metro', 'Metrorail', 'Subway', 'SIR', 'LIRR', 'NYC Ferry', 'Staten Island Ferry', 'Roosevelt Island Tram']

// Lines that don't run on weekends, per map (RegionData.weekendExcludedLines).
export { WEEKEND_EXCLUDED_LINES } from '../data/regions'

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
