export type Side = 'w' | 'b'

export interface TimeControl {
  id: string
  label: string
  baseMs: number
  incrementMs: number
}

export interface ClockState {
  control: TimeControl
  /** Remaining time captured at the last turn boundary. The live value is derived. */
  remaining: Record<Side, number>
  active: Side
  runningSince: number | null
  flagged: Side | null
  /** True after the first move. That move does not receive an increment. */
  started: boolean
}

export const TIME_CONTROLS: TimeControl[] = [
  { id: '1+0', label: '1 + 0', baseMs: 60_000, incrementMs: 0 },
  { id: '2+1', label: '2 + 1', baseMs: 120_000, incrementMs: 1_000 },
  { id: '3+0', label: '3 + 0', baseMs: 180_000, incrementMs: 0 },
  { id: '3+2', label: '3 + 2', baseMs: 180_000, incrementMs: 2_000 },
  { id: '5+0', label: '5 + 0', baseMs: 300_000, incrementMs: 0 },
  { id: '10+0', label: '10 + 0', baseMs: 600_000, incrementMs: 0 },
  { id: '15+10', label: '15 + 10', baseMs: 900_000, incrementMs: 10_000 },
]

const other = (side: Side): Side => (side === 'w' ? 'b' : 'w')

export function createClock(control: TimeControl, active: Side = 'w'): ClockState {
  return {
    control,
    remaining: { w: control.baseMs, b: control.baseMs },
    active,
    runningSince: null,
    flagged: null,
    started: false,
  }
}

export function remainingAt(state: ClockState, now: number): Record<Side, number> {
  if (state.runningSince === null || state.flagged) return { ...state.remaining }
  const elapsed = Math.max(0, now - state.runningSince)
  return {
    ...state.remaining,
    [state.active]: Math.max(0, state.remaining[state.active] - elapsed),
  }
}

export function checkFlag(state: ClockState, now: number): ClockState {
  if (state.runningSince === null || state.flagged) return state
  if (state.remaining[state.active] - (now - state.runningSince) > 0) return state
  return {
    ...state,
    remaining: { ...state.remaining, [state.active]: 0 },
    runningSince: null,
    flagged: state.active,
  }
}

export function startClock(state: ClockState, now: number): ClockState {
  if (state.flagged || state.runningSince !== null) return state
  return { ...state, runningSince: now }
}

export function pauseClock(state: ClockState, now: number): ClockState {
  if (state.runningSince === null || state.flagged) return state
  return { ...state, remaining: remainingAt(state, now), runningSince: null }
}

/**
 * A move was played. Settle the mover's clock, give the increment only after
 * the first move, and start the opponent's clock.
 */
export function pressClock(state: ClockState, now: number): ClockState {
  if (state.flagged) return state
  const live = remainingAt(state, now)
  const mover = state.active
  const awarded = state.started ? state.control.incrementMs : 0
  return {
    ...state,
    remaining: { ...live, [mover]: live[mover] + awarded },
    active: other(mover),
    runningSince: now,
    started: true,
  }
}

export function formatClock(ms: number): string {
  const clamped = Math.max(0, Math.ceil(ms))
  const totalSeconds = Math.floor(clamped / 1000)
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  const clock = `${minutes}:${seconds.toString().padStart(2, '0')}`
  if (clamped >= 20_000) return clock
  const tenths = Math.floor((clamped % 1000) / 100)
  return `${clock}.${tenths}`
}
