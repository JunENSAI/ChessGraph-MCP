/** Opponent strength for play mode. Stockfish accepts UCI_Elo from 1320 to 3190. */
export interface StrengthLevel {
  id: string
  label: string
  /** null = full strength. */
  elo: number | null
}

export const MIN_ENGINE_ELO = 1320
export const MAX_ENGINE_ELO = 3190

export const STRENGTH_LEVELS: StrengthLevel[] = [
  { id: '1400', label: 'Club · 1400', elo: 1400 },
  { id: '1600', label: 'Club · 1600', elo: 1600 },
  { id: '1800', label: 'Strong club · 1800', elo: 1800 },
  { id: '2000', label: 'Expert · 2000', elo: 2000 },
  { id: '2200', label: 'Master · 2200', elo: 2200 },
  { id: '2500', label: 'Grandmaster · 2500', elo: 2500 },
  { id: 'max', label: 'Stockfish · full strength', elo: null },
]

export const DEFAULT_STRENGTH = '1800'

export function strengthById(id: string): StrengthLevel {
  return STRENGTH_LEVELS.find(level => level.id === id) ?? STRENGTH_LEVELS.find(level => level.id === DEFAULT_STRENGTH)!
}

/** The limited level closest to a rating, for a fair first game. */
export function levelForRating(rating: number | null | undefined): StrengthLevel {
  const limited = STRENGTH_LEVELS.filter(level => level.elo !== null)
  if (rating == null || !Number.isFinite(rating)) return strengthById(DEFAULT_STRENGTH)
  return limited.reduce((best, level) =>
    Math.abs(level.elo! - rating) < Math.abs(best.elo! - rating) ? level : best,
  )
}

/** Think time per move: a little longer at higher levels, never long enough to stall the game. */
export function moveTimeMs(level: StrengthLevel): number {
  if (level.elo === null) return 800
  return Math.round(150 + ((level.elo - MIN_ENGINE_ELO) / (MAX_ENGINE_ELO - MIN_ENGINE_ELO)) * 500)
}
