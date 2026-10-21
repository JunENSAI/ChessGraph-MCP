import type { OutcomeCounts } from '../data/types'

export function totalGames(counts: OutcomeCounts): number {
  return counts.wins + counts.draws + counts.losses
}

/** Win percentage, rounded to a whole number; draws count as non-wins. */
export function winRate(counts: OutcomeCounts): number {
  const total = totalGames(counts)
  return total === 0 ? 0 : Math.round((counts.wins / total) * 100)
}

/** Points per game as a percentage: a draw scores half a point. */
export function scoreRate(counts: OutcomeCounts): number {
  const total = totalGames(counts)
  return total === 0 ? 0 : Math.round(((counts.wins + counts.draws / 2) / total) * 100)
}

export function combine(...counts: OutcomeCounts[]): OutcomeCounts {
  return counts.reduce(
    (sum, item) => ({
      wins: sum.wins + item.wins,
      draws: sum.draws + item.draws,
      losses: sum.losses + item.losses,
    }),
    { wins: 0, draws: 0, losses: 0 },
  )
}

export function share(part: number, whole: number): number {
  return whole === 0 ? 0 : Math.round((part / whole) * 100)
}
