import { useCallback, useEffect, useState } from 'react'
import {
  checkFlag,
  createClock,
  pauseClock,
  pressClock,
  remainingAt,
  startClock,
  type Side,
  type TimeControl,
} from '../lib/clock'

const TICK_MS = 100

export function useChessClock(control: TimeControl) {
  const [state, setState] = useState(() => createClock(control))
  const [now, setNow] = useState(() => performance.now())
  const running = state.runningSince !== null

  useEffect(() => {
    if (!running) return
    const tick = () => {
      const timestamp = performance.now()
      setNow(timestamp)
      setState(current => checkFlag(current, timestamp))
    }
    const interval = window.setInterval(tick, TICK_MS)
    document.addEventListener('visibilitychange', tick)
    return () => {
      window.clearInterval(interval)
      document.removeEventListener('visibilitychange', tick)
    }
  }, [running])

  const start = useCallback(() => setState(current => startClock(current, performance.now())), [])
  const pause = useCallback(() => setState(current => pauseClock(current, performance.now())), [])
  const press = useCallback(() => setState(current => pressClock(current, performance.now())), [])
  const reset = useCallback(
    (next: TimeControl = control, active: Side = 'w') => setState(createClock(next, active)),
    [control],
  )

  return {
    remaining: remainingAt(state, now),
    active: state.active,
    running,
    flagged: state.flagged,
    start,
    pause,
    press,
    reset,
  }
}

export type ChessClockController = ReturnType<typeof useChessClock>
