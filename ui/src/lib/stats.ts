interface OutcomeCounts {
  wins: number
  draws: number
  losses: number
}

export function totalGames(counts: OutcomeCounts): number {
  return counts.wins + counts.draws + counts.losses
}

export function winRate(counts: OutcomeCounts): number {
  const total = totalGames(counts)
  if (total === 0) return 0
  return Math.round((counts.wins / total) * 100)
}

/** Integer percent. A zero total stays at zero. */
export function share(part: number, total: number): number {
  if (total <= 0) return 0
  return Math.round((part / total) * 100)
}
