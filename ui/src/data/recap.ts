import type { OpeningStat, RecapBand, RecapPayload } from './types'

/** The stored line with the most games. Ties break by name, then ECO. */
export function mostPlayedLine(items: OpeningStat[]): OpeningStat | undefined {
  return [...items].sort((a, b) => {
    const byGames = gamesIn(b.results) - gamesIn(a.results)
    if (byGames !== 0) return byGames
    const byName = a.name.localeCompare(b.name)
    if (byName !== 0) return byName
    return a.eco.localeCompare(b.eco)
  })[0]
}

export function clockGameCounts(band: RecapBand): { label: string; games: number }[] {
  return band.timeControls
    .map(item => ({ label: item.label, games: gamesIn(item.results) }))
    .filter(item => item.games > 0)
}

export function mostPlayedClock(band: RecapBand) {
  return [...band.timeControls].sort((a, b) => {
    const byGames = gamesIn(b.results) - gamesIn(a.results)
    if (byGames !== 0) return byGames
    return a.label.localeCompare(b.label)
  })[0]
}

export function busiestBand(bands: RecapBand[]): RecapBand | undefined {
  return [...bands].sort((a, b) => bandGames(b) - bandGames(a) || a.label.localeCompare(b.label))[0]
}

export function bandGames(band: RecapBand): number {
  return gamesIn(band.white) + gamesIn(band.black)
}

export function gamesIn(counts: { wins: number; draws: number; losses: number }): number {
  return counts.wins + counts.draws + counts.losses
}

/** Axis label: the specific line after the family prefix, plus its ECO. */
export function chartLabel(name: string, eco: string): string {
  const parts = name.split(':')
  const specific = (parts.length > 1 ? parts.slice(1).join(':') : name).trim()
  const clipped = specific.length > 36 ? `${specific.slice(0, 35)}…` : specific
  return `${clipped} (${eco})`
}

/**
 * Whole-number shares of wins, draws and losses that add up to 100
 * (largest remainder), so a bar's segments and its labels always agree.
 */
export function resultShares(counts: { wins: number; draws: number; losses: number }): {
  wins: number
  draws: number
  losses: number
} {
  const total = gamesIn(counts)
  if (total === 0) return { wins: 0, draws: 0, losses: 0 }
  const keys = ['wins', 'draws', 'losses'] as const
  const exact = keys.map(key => (counts[key] * 100) / total)
  const floors = exact.map(Math.floor)
  let left = 100 - floors.reduce((sum, value) => sum + value, 0)
  const order = exact.map((value, index) => ({ index, rest: value - floors[index] })).sort((a, b) => b.rest - a.rest)
  for (const { index } of order) {
    if (left <= 0) break
    floors[index] += 1
    left -= 1
  }
  return { wins: floors[0], draws: floors[1], losses: floors[2] }
}

/** The most played lines first, at most ``limit``. */
export function topLines(items: OpeningStat[], limit = 6): OpeningStat[] {
  return [...items].sort((a, b) => gamesIn(b.results) - gamesIn(a.results) || a.name.localeCompare(b.name)).slice(0, limit)
}

export async function loadRecap(fetchImpl: typeof fetch = fetch): Promise<RecapPayload> {
  const response = await fetchImpl('/api/recap')
  if (!response.ok) {
    let detail = `Recap request failed (${response.status}).`
    try {
      const body = (await response.json()) as { error?: string }
      if (body.error) detail = body.error
    } catch {
      // The body was not JSON; keep the status message.
    }
    throw new Error(detail)
  }
  const body = (await response.json()) as RecapPayload
  if (!Array.isArray(body.bands)) throw new Error('Recap response has no rating bands.')
  return body
}
