import type { Station } from '../types'

export const SYSTEM_COLORS: Record<string, string> = {
  BART: '#0066cc',
  Caltrain: '#d4001a',
  VTA: '#f5821f',
  Muni: '#7b2d8b',
}

export const SYSTEM_ORDER = ['BART', 'Caltrain', 'VTA', 'Muni']

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
