export type Side = 'w' | 'b'

export interface TimeControl {
  id: string
  label: string
  baseMs: number
  incrementMs: number
}

export const TIME_CONTROLS: TimeControl[] = [
  { id: '1+0', label: '1 + 0', baseMs: 60_000, incrementMs: 0 },
  { id: '2+1', label: '2 + 1', baseMs: 120_000, incrementMs: 1_000 },
  { id: '3+0', label: '3 + 0', baseMs: 180_000, incrementMs: 0 },
  { id: '3+2', label: '3 + 2', baseMs: 180_000, incrementMs: 2_000 },
  { id: '5+0', label: '5 + 0', baseMs: 300_000, incrementMs: 0 },
  { id: '10+0', label: '10 + 0', baseMs: 600_000, incrementMs: 0 },
  { id: '15+10', label: '15 + 10', baseMs: 900_000, incrementMs: 10_000 },
  { id: '30+0', label: '30 + 0', baseMs: 1_800_000, incrementMs: 0 },
]

/**
 * Remaining time is stored only at turn boundaries. While a clock runs,
 * the live value is derived from `runningSince`, so timer drift or a
 * throttled background tab cannot change the result.
 */
export interface ClockState {
  remaining: Record<Side, number>
  active: Side
  runningSince: number | null
  incrementMs: number
  flagged: Side | null
}

export function createClock(control: TimeControl, active: Side = 'w'): ClockState {
  return {
    remaining: { w: control.baseMs, b: control.baseMs },
    active,
    runningSince: null,
    incrementMs: control.incrementMs,
    flagged: null,
  }
}

export function remainingAt(state: ClockState, now: number): Record<Side, number> {
  if (state.runningSince === null) return state.remaining
  const elapsed = Math.max(0, now - state.runningSince)
  return {
    ...state.remaining,
    [state.active]: Math.max(0, state.remaining[state.active] - elapsed),
  }
}

export function startClock(state: ClockState, now: number): ClockState {
  if (state.flagged || state.runningSince !== null) return state
  return { ...state, runningSince: now }
}

export function pauseClock(state: ClockState, now: number): ClockState {
  if (state.runningSince === null) return state
  return { ...state, remaining: remainingAt(state, now), runningSince: null }
}

/**
 * Called after the active side completes a move. The increment is granted
 * only for moves made on a running clock, so the first move of a game
 * starts the opponent's clock without crediting the mover.
 */
export function pressClock(state: ClockState, now: number): ClockState {
  if (state.flagged) return state
  const wasRunning = state.runningSince !== null
  const remaining = remainingAt(state, now)
  if (wasRunning && remaining[state.active] <= 0) {
    return { ...state, remaining, runningSince: null, flagged: state.active }
  }
  const mover = state.active
  return {
    ...state,
    remaining: wasRunning
      ? { ...remaining, [mover]: remaining[mover] + state.incrementMs }
      : remaining,
    active: mover === 'w' ? 'b' : 'w',
    runningSince: now,
  }
}

export function checkFlag(state: ClockState, now: number): ClockState {
  if (state.flagged || state.runningSince === null) return state
  const remaining = remainingAt(state, now)
  if (remaining[state.active] > 0) return state
  return { ...state, remaining, runningSince: null, flagged: state.active }
}

export function formatClock(ms: number): string {
  const clamped = Math.max(0, ms)
  const tenths = Math.ceil(clamped / 100)
  if (tenths < 100) {
    return `0:0${Math.floor(tenths / 10)}.${tenths % 10}`
  }
  const totalSeconds = Math.ceil(clamped / 1000)
  const hours = Math.floor(totalSeconds / 3600)
  const minutes = Math.floor((totalSeconds % 3600) / 60)
  const seconds = String(totalSeconds % 60).padStart(2, '0')
  if (hours > 0) return `${hours}:${String(minutes).padStart(2, '0')}:${seconds}`
  return `${minutes}:${seconds}`
}
