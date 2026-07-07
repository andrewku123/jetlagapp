import { describe, it, expect, vi, afterEach } from 'vitest'

// Loads POI_COUNTS fresh for a given active region so we can assert per-category
// POI demotion (a Matching/Measuring subject with no in-play POI is useless).
async function poiCountsFor(id: string) {
  vi.resetModules()
  const store: Record<string, string> = { 'bahs.region': id }
  vi.stubGlobal('localStorage', {
    getItem: (k: string) => store[k] ?? null,
    setItem: () => {},
  })
  const m = await import('./poi')
  return m.POI_COUNTS
}

afterEach(() => {
  vi.unstubAllGlobals()
  vi.resetModules()
})

describe('per-category POI question demotion', () => {
  it('Bay Area has amusement parks in play (both POI questions ask normally)', async () => {
    const counts = await poiCountsFor('bayarea')
    expect(counts.amusement_park).toBeGreaterThan(1)
  })

  it('SF Muni has zero in-play amusement parks (both POI questions log-only)', async () => {
    const counts = await poiCountsFor('sfmuni')
    // No amusement park inside San Francisco → "nearest amusement park" has no
    // answer, so both match-poi and measure-poi on that subject are log-only.
    expect(counts.amusement_park).toBe(0)
    // Sparse-but-present categories (2 each) still split cleanly and stay.
    expect(counts.zoo).toBeGreaterThanOrEqual(2)
    expect(counts.aquarium).toBeGreaterThanOrEqual(2)
  })
})
