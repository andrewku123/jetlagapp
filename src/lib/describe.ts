import type { QuestionRecord, UnitSystem } from '../types'
import { formatDistance, formatElevation } from './geo'
import { poiCategoryLabel } from './poi'
import { MEASURE_FEATURE_LABELS, type MeasureFeatureKey } from './measureFeatures'

export function describeRecord(r: QuestionRecord, units: UnitSystem = 'imperial'): string {
  const p = r.params
  // A vetoed question has no answer, so the "→ answer" suffix is dropped.
  const a = p.answer
  const arrow = (text: string) => (a == null ? '' : ` → ${text}`)
  switch (r.kind) {
    case 'radar':
      return `Radar ${formatDistance(Number(p.radiusMiles), units)}${arrow(String(a).toUpperCase())}`
    case 'thermometer': {
      const t = Number(p.thermometerMiles)
      const dist = Number.isFinite(t) && t > 0 ? ` ${formatDistance(t, units)}` : ''
      return `Thermometer${dist}${arrow(String(a))}`
    }
    case 'match-county':
      return `Same county as "${p.value}"?${arrow(String(a))}`
    case 'match-city':
      return `Same city as "${p.value}"?${arrow(String(a))}`
    case 'match-airport':
      return `Same nearest airport (${p.value})?${arrow(String(a))}`
    case 'match-line':
      return `On line "${p.value}"?${arrow(String(a))}`
    case 'match-namelength':
      return `Name length = ${p.value}?${arrow(String(a))}`
    case 'match-poi':
      return `Same nearest ${poiCategoryLabel(String(p.poiCat))}${p.poiName ? ` ("${String(p.poiName)}")` : ''}?${arrow(String(a))}`
    case 'measure-poi':
      return `Closer/further from nearest ${poiCategoryLabel(String(p.poiCat))}${arrow(String(a))}`
    case 'measure-feature':
      return `Closer/further from ${MEASURE_FEATURE_LABELS[String(p.feature) as MeasureFeatureKey] ?? 'a border'}${arrow(String(a))}`
    case 'measure-airport':
      return `Closer/further from airport${arrow(String(a))}`
    case 'measure-sealevel':
      return `Altitude vs ${formatElevation(Number(p.value), units)}${arrow(String(a))}`
    case 'inside-floor': {
      const ans: Record<string, string> = {
        higher: 'higher floor',
        lower: 'lower floor',
        same: 'same floor',
        cannot: "can't answer",
      }
      return `Inside "${p.building}"${p.floor ? ` (floor ${String(p.floor)})` : ''}${arrow(ans[String(a)] ?? String(a))}`
    }
    case 'photo':
      return `Photo: ${p.description || '(logged)'}`
    case 'match-street':
    case 'match-admin1':
    case 'match-admin4':
    case 'match-landmass': {
      const detail = p.description ? ` "${String(p.description)}"` : ''
      const subject = { 'match-street': 'street/path', 'match-admin1': 'state', 'match-admin4': 'neighborhood', 'match-landmass': 'landmass' }[r.kind]
      return `Same ${subject}?${detail}${arrow(String(a).toUpperCase())} (log only)`
    }
    case 'measure-hsr':
    case 'measure-railstation':
    case 'measure-water': {
      const detail = p.description ? ` "${String(p.description)}"` : ''
      const subject = { 'measure-hsr': 'high-speed rail', 'measure-railstation': 'rail station', 'measure-water': 'body of water' }[r.kind]
      return `Closer/further from ${subject}?${detail}${arrow(String(a))} (log only)`
    }
    default:
      return r.kind
  }
}
