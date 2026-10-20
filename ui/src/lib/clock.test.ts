import { describe, expect, it } from 'vitest'
import { checkFlag, createClock, pauseClock, pressClock, remainingAt, startClock, TIME_CONTROLS } from './clock'

const blitz = TIME_CONTROLS.find(control => control.id === '3+2')!

describe('chess clock', () => {
  it('derives the live time without writing the stored remainder', () => {
    const started = startClock(createClock(blitz), 1_000)
    const live = remainingAt(started, 1_400)
    expect(live.w).toBe(blitz.baseMs - 400)
    expect(started.remaining.w).toBe(blitz.baseMs)
  })

  it('starts the opponent clock on the first move and withholds the increment', () => {
    const afterFirst = pressClock(startClock(createClock(blitz), 0), 500)
    expect(afterFirst.active).toBe('b')
    expect(afterFirst.remaining.w).toBe(blitz.baseMs - 500)
    expect(afterFirst.runningSince).toBe(500)
    const afterSecond = pressClock(afterFirst, 800)
    expect(afterSecond.active).toBe('w')
    expect(afterSecond.remaining.b).toBe(blitz.baseMs - 300 + blitz.incrementMs)
  })

  it('flags the side whose stored time reaches zero', () => {
    const running = startClock(createClock(blitz), 0)
    const flagged = checkFlag(running, blitz.baseMs + 1)
    expect(flagged.flagged).toBe('w')
    expect(flagged.runningSince).toBeNull()
    expect(flagged.remaining.w).toBe(0)
    expect(pressClock(flagged, blitz.baseMs + 50)).toBe(flagged)
  })

  it('pause stores the elapsed time and a later resume continues from there', () => {
    const paused = pauseClock(startClock(createClock(blitz), 0), 1_000)
    expect(paused.runningSince).toBeNull()
    expect(paused.remaining.w).toBe(blitz.baseMs - 1_000)
    const resumed = startClock(paused, 5_000)
    expect(remainingAt(resumed, 5_250).w).toBe(blitz.baseMs - 1_250)
  })
})
