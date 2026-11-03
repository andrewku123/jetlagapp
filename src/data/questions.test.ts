import { describe, it, expect } from 'vitest'
import { scaleCards, rewardForKind, questionGroupKey, askOrdinals, askGroupCounts, thermometerTravelOk, curseUnmarkBlocked } from './questions'
import type { QuestionRecord } from '../types'

describe('scaleCards — repeat-question reward scaling', () => {
  it('leaves the reward unchanged for the 1st ask (×1)', () => {
    expect(scaleCards('draw 2, keep 1', 1)).toBe('draw 2, keep 1')
    expect(scaleCards('draw 2, keep 1', 0)).toBe('draw 2, keep 1')
  })
  it('multiplies both draw and keep by n', () => {
    expect(scaleCards('draw 2, keep 1', 2)).toBe('draw 4, keep 2')
    expect(scaleCards('draw 3, keep 1', 3)).toBe('draw 9, keep 3')
  })
})

describe('questionGroupKey — thermometer keys on the chosen thermometer', () => {
  it('groups by the explicitly chosen thermometer distance', () => {
    const a = questionGroupKey('thermometer', { thermometerMiles: 0.5, fromLat: 37.8, fromLon: -122.3, toLat: 37.9, toLon: -122.2 })
    const b = questionGroupKey('thermometer', { thermometerMiles: 0.5, fromLat: 37.7, fromLon: -122.4, toLat: 37.6, toLon: -122.5 })
    const c = questionGroupKey('thermometer', { thermometerMiles: 3, fromLat: 37.8, fromLon: -122.3, toLat: 37.9, toLon: -122.2 })
    expect(a).toBe(b) // same chosen thermometer = same question
    expect(a).not.toBe(c) // different thermometer = different question
  })
  it('falls back to inferring from A→B travel when no thermometer chosen', () => {
    const k = questionGroupKey('thermometer', { fromLat: 37.8, fromLon: -122.3, toLat: 37.805, toLon: -122.3 })
    expect(k).toBe('thermometer:0.5')
  })
})

describe('questionGroupKey — each photo card is its own question', () => {
  it('two different photos do not share a group (no stacked penalty)', () => {
    const tree = questionGroupKey('photo', { photoTitle: 'A Tree' })
    const sky = questionGroupKey('photo', { photoTitle: 'The Sky' })
    expect(tree).not.toBe(sky)
  })
  it('re-asking the same photo shares a group', () => {
    const a = questionGroupKey('photo', { photoTitle: 'A Tree', description: 'oak' })
    const b = questionGroupKey('photo', { photoTitle: 'A Tree' })
    expect(a).toBe(b)
  })
})

describe('rewardForKind', () => {
  it('returns the base reward, scaled by the ask multiplier', () => {
    expect(rewardForKind('radar')).toBe('draw 2, keep 1')
    expect(rewardForKind('radar', 2)).toBe('draw 4, keep 2')
    expect(rewardForKind('match-county', 3)).toBe('draw 9, keep 3')
  })
})

describe('curse info — not a question for rewards or repeats', () => {
  const rec = (id: string, createdAt: number, extra: Partial<QuestionRecord> = {}): QuestionRecord => ({
    id,
    kind: 'radar',
    createdAt,
    params: { lat: 40.7, lon: -74, radiusMiles: 3, answer: 'no' },
    eliminates: true,
    active: true,
    ...extra,
  })
  it('gives curse info no ask ordinal and keeps the next real ask at x1', () => {
    const qs = [rec('curse', 1, { curse: true }), rec('ask', 2)]
    const ord = askOrdinals(qs)
    expect(ord.has('curse')).toBe(false)
    expect(ord.get('ask')).toBe(1)
  })
  it('still counts a second real ask as x2', () => {
    const ord = askOrdinals([rec('a', 1), rec('curse', 2, { curse: true }), rec('b', 3)])
    expect(ord.get('b')).toBe(2)
  })
  it('leaves curse info out of the Ask-form preview counts', () => {
    const counts = askGroupCounts([rec('curse', 1, { curse: true })])
    expect(counts.get(questionGroupKey('radar', { radiusMiles: 3 }))).toBeUndefined()
  })
})

describe('thermometerTravelOk — minimum A→B travel', () => {
  it('requires the chosen distance, less a small tolerance', () => {
    expect(thermometerTravelOk(0.5, 0.5)).toBe(true)
    expect(thermometerTravelOk(0.41, 0.5)).toBe(true)
    expect(thermometerTravelOk(0.3, 0.5)).toBe(false)
    expect(thermometerTravelOk(2.8, 3)).toBe(false)
    expect(thermometerTravelOk(2.86, 3)).toBe(true)
  })
  it('has no minimum for curse info (a curse move shorter than 0.5 mi still counts)', () => {
    expect(thermometerTravelOk(0.2, 0.5, true)).toBe(true)
    expect(thermometerTravelOk(0.05, 3, true)).toBe(true)
  })
})

describe('curseUnmarkBlocked — a too-short curse thermometer stays curse info', () => {
  // ~0.21 mi apart along a meridian
  const short = { fromLat: 37.77, fromLon: -122.42, toLat: 37.773, toLon: -122.42, thermometerMiles: 0.5, answer: 'hotter' }
  const long = { ...short, toLat: 37.78 }
  it('blocks unmarking a curse thermometer under its minimum travel', () => {
    expect(curseUnmarkBlocked({ kind: 'thermometer', params: short, curse: true })).toBe(true)
  })
  it('allows unmarking when the move meets the minimum, or the row is not curse info', () => {
    expect(curseUnmarkBlocked({ kind: 'thermometer', params: long, curse: true })).toBe(false)
    expect(curseUnmarkBlocked({ kind: 'thermometer', params: short })).toBe(false)
    expect(curseUnmarkBlocked({ kind: 'radar', params: { radiusMiles: 3 }, curse: true })).toBe(false)
  })
})
