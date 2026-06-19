import type { QuestionRecord, UnitSystem } from '../types'
import { formatDistance, formatElevation } from './geo'

export function describeRecord(r: QuestionRecord, units: UnitSystem = 'imperial'): string {
  const p = r.params
  switch (r.kind) {
    case 'radar':
      return `Radar ${formatDistance(Number(p.radiusMiles), units)} → ${String(p.answer).toUpperCase()}`
    case 'thermometer':
      return `Thermometer → ${String(p.answer)}`
    case 'match-county':
      return `Same county as "${p.value}"? → ${String(p.answer)}`
    case 'match-city':
      return `Same city as "${p.value}"? → ${String(p.answer)}`
    case 'match-airport':
      return `Same nearest airport (${p.value})? → ${String(p.answer)}`
    case 'match-line':
      return `On line "${p.value}"? → ${String(p.answer)}`
    case 'match-namelength':
      return `Name length = ${p.value}? → ${String(p.answer)}`
    case 'measure-airport':
      return `Closer/further from airport → ${String(p.answer)}`
    case 'measure-sealevel':
      return `Altitude vs ${formatElevation(Number(p.value), units)} → ${String(p.answer)}`
    case 'photo':
      return `Photo: ${p.description || '(logged)'}`
    default:
      return r.kind
  }
}
