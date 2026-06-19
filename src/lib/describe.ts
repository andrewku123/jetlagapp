import type { QuestionRecord } from '../types'

export function describeRecord(r: QuestionRecord): string {
  const p = r.params
  switch (r.kind) {
    case 'radar':
      return `Radar ${p.radiusMiles} mi → ${String(p.answer).toUpperCase()}`
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
      return `Altitude vs ${p.value} m → ${String(p.answer)}`
    case 'photo':
      return `Photo: ${p.description || '(logged)'}`
    default:
      return r.kind
  }
}
