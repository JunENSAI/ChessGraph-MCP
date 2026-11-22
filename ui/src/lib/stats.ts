import type { OutcomeCounts } from '../data/types'

export function totalGames(counts: OutcomeCounts): number {
  return counts.wins + counts.draws + counts.losses
}

/** Win percentage, rounded to a whole number; draws count as non-wins. */
export function winRate(counts: OutcomeCounts): number {
  const total = totalGames(counts)
  return total === 0 ? 0 : Math.round((counts.wins / total) * 100)
}

export function share(part: number, whole: number): number {
  return whole === 0 ? 0 : Math.round((part / whole) * 100)
}
