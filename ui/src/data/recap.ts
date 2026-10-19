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
