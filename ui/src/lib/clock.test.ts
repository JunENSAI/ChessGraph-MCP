import { describe, expect, it } from 'vitest'
import {
  TIME_CONTROLS,
  checkFlag,
  createClock,
  formatClock,
  pauseClock,
  pressClock,
  remainingAt,
  startClock,
} from './clock'

const blitz = TIME_CONTROLS.find(control => control.id === '3+2')!

describe('chess clock', () => {
  it('does not run until started or until the first move', () => {
    const clock = createClock(blitz)
    expect(remainingAt(clock, 50_000)).toEqual({ w: 180_000, b: 180_000 })
  })

  it('deducts elapsed time only from the side to move', () => {
    const clock = startClock(createClock(blitz), 1_000)
    expect(remainingAt(clock, 4_500)).toEqual({ w: 176_500, b: 180_000 })
  })

  it('starts the opponent clock on the first move without an increment', () => {
    const clock = pressClock(createClock(blitz), 1_000)
    expect(clock.active).toBe('b')
    expect(clock.remaining).toEqual({ w: 180_000, b: 180_000 })
    expect(remainingAt(clock, 3_000)).toEqual({ w: 180_000, b: 178_000 })
  })

  it('credits the increment after a move on a running clock', () => {
    let clock = pressClock(createClock(blitz), 0)
    clock = pressClock(clock, 5_000)
    expect(clock.remaining.b).toBe(177_000)
    expect(clock.active).toBe('w')
  })

  it('freezes both sides while paused', () => {
    let clock = startClock(createClock(blitz), 0)
    clock = pauseClock(clock, 2_000)
    expect(remainingAt(clock, 60_000)).toEqual({ w: 178_000, b: 180_000 })
  })

  it('flags the side whose time reaches zero', () => {
    const bullet = TIME_CONTROLS.find(control => control.id === '1+0')!
    let clock = startClock(createClock(bullet), 0)
    clock = checkFlag(clock, 59_999)
    expect(clock.flagged).toBeNull()
    clock = checkFlag(clock, 60_000)
    expect(clock.flagged).toBe('w')
    expect(clock.runningSince).toBeNull()
    expect(remainingAt(clock, 90_000).w).toBe(0)
  })

  it('rejects a move made after the flag fell', () => {
    const bullet = TIME_CONTROLS.find(control => control.id === '1+0')!
    let clock = startClock(createClock(bullet), 0)
    clock = pressClock(clock, 61_000)
    expect(clock.flagged).toBe('w')
    expect(clock.active).toBe('w')
  })
})

describe('formatClock', () => {
  it.each([
    [600_000, '10:00'],
    [59_001, '1:00'],
    [10_000, '0:10'],
    [9_999, '0:10'],
    [9_401, '0:09.5'],
    [500, '0:00.5'],
    [0, '0:00.0'],
    [3_723_000, '1:02:03'],
  ])('formats %i ms as %s', (ms, expected) => {
    expect(formatClock(ms)).toBe(expected)
  })
})
