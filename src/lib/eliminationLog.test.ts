import { describe, expect, it } from 'vitest'
import { logManualChange } from './eliminationLog'

describe('elimination time log', () => {
  it('opens a mark for each new cross-out', () => {
    expect(logManualChange([], [], ['a', 'b'], 100)).toEqual([
      { stationId: 'a', outAt: 100 },
      { stationId: 'b', outAt: 100 },
    ])
  })

  it('closes the open mark on restore and leaves others alone', () => {
    const log = logManualChange([], [], ['a', 'b'], 100)
    expect(logManualChange(log, ['a', 'b'], ['b'], 200)).toEqual([
      { stationId: 'a', outAt: 100, backAt: 200 },
      { stationId: 'b', outAt: 100 },
    ])
  })

  it('keeps the full history when a station is crossed out again', () => {
    let log = logManualChange([], [], ['a'], 100)
    log = logManualChange(log, ['a'], [], 200)
    log = logManualChange(log, [], ['a'], 300)
    log = logManualChange(log, ['a'], [], 400)
    expect(log).toEqual([
      { stationId: 'a', outAt: 100, backAt: 200 },
      { stationId: 'a', outAt: 300, backAt: 400 },
    ])
  })

  it('logs nothing when the list is unchanged', () => {
    const log = [{ stationId: 'a', outAt: 100 }]
    expect(logManualChange(log, ['a'], ['a'], 200)).toEqual(log)
  })
})
