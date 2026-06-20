import type { Station } from '../types'

export const SYSTEM_COLORS: Record<string, string> = {
  BART: '#0066cc',
  Caltrain: '#d4001a',
  VTA: '#f5821f',
  Muni: '#7b2d8b',
  'SFO AirTrain': '#00897b',
}

export const SYSTEM_ORDER = ['BART', 'Caltrain', 'VTA', 'Muni', 'SFO AirTrain']

// Lines that don't run on weekends; hidden from the transit-line question in
// Weekend mode. Caltrain Express ("Baby Bullet") and Limited are weekday-only.
export const WEEKEND_EXCLUDED_LINES = ['Caltrain Express', 'Caltrain Limited']

export function stationColor(st: Station): string {
  // primary color = first system in canonical order
  for (const sys of SYSTEM_ORDER) {
    if (st.systems.includes(sys)) return SYSTEM_COLORS[sys]
  }
  return '#444'
}

export function isMultiSystem(st: Station): boolean {
  return st.systems.length > 1
}
