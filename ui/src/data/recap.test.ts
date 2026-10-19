import { describe, expect, it, vi } from 'vitest'
import { busiestBand, chartLabel, loadRecap, mostPlayedLine } from './recap'
import type { OpeningStat, RecapBand } from './types'

const italian: OpeningStat = {
  name: 'Italian Game',
  eco: 'C50',
  results: { wins: 2, draws: 0, losses: 1 },
}
const london: OpeningStat = {
  name: "Queen's Pawn Game: London System",
  eco: 'D02',
  results: { wins: 30, draws: 4, losses: 16 },
}

function band(id: string, games: number): RecapBand {
  return {
    id,
    label: id,
    white: { wins: games, draws: 0, losses: 0 },
    black: { wins: 0, draws: 0, losses: 0 },
    openingsWhite: [],
    defensesBlack: [],
    timeControls: [],
  }
}

describe('mostPlayedLine', () => {
  it('ranks a larger London line ahead of a played Italian line', () => {
    expect(mostPlayedLine([italian, london])?.name).toBe(london.name)
  })

  it('keeps Italian when that stored line really has the most games', () => {
    expect(mostPlayedLine([italian])?.name).toBe('Italian Game')
  })

  it('returns nothing when the band has no stored lines', () => {
    expect(mostPlayedLine([])).toBeUndefined()
  })

  it('breaks a tie by name so the headline is stable', () => {
    const other: OpeningStat = { ...london, name: 'London System', eco: 'A48' }
    expect(mostPlayedLine([other, london])?.name).toBe('London System')
  })
})

describe('busiestBand', () => {
  it('selects the rating band that contains the most games', () => {
    expect(busiestBand([band('under-1700', 10), band('1900-1999', 40)])?.id).toBe('1900-1999')
  })
})

describe('chartLabel', () => {
  it('shows the specific line and ECO instead of the family prefix', () => {
    expect(chartLabel("Queen's Pawn Game: London System, with e6", 'D02')).toBe(
      'London System, with e6 (D02)',
    )
  })
})

describe('loadRecap', () => {
  it('returns the bands from the recap endpoint', async () => {
    const payload = { gameCount: 3, bands: [band('2000-plus', 3)] }
    const fetchImpl = vi.fn(async () => new Response(JSON.stringify(payload), { status: 200 }))
    await expect(loadRecap(fetchImpl)).resolves.toEqual(payload)
    expect(fetchImpl).toHaveBeenCalledWith('/api/recap')
  })

  it('surfaces a database error instead of falling back to demo openings', async () => {
    const fetchImpl = vi.fn(
      async () => new Response(JSON.stringify({ error: 'PostgreSQL is not accepting connections.' }), { status: 503 }),
    )
    await expect(loadRecap(fetchImpl)).rejects.toThrow('PostgreSQL is not accepting connections.')
  })
})
