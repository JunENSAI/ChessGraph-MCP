import { describe, expect, it } from 'vitest'
import { replaySan } from '../lib/chess'
import {
  evalSeries,
  gameStats,
  keyMomentFromMoves,
  listedGame,
  openingFamilyOf,
  outcomeFor,
  type StoredMove,
} from './games'

describe('outcomeFor', () => {
  it('reads the result from the user color', () => {
    expect(outcomeFor('1-0', 'white')).toBe('win')
    expect(outcomeFor('1-0', 'black')).toBe('loss')
    expect(outcomeFor('1/2-1/2', 'black')).toBe('draw')
    expect(outcomeFor('*', 'white')).toBe('unfinished')
  })
})

describe('listedGame', () => {
  it('names the opponent and keeps the user color', () => {
    const game = listedGame(
      {
        game_id: 4,
        game_type: 'blitz',
        played_date: '2026-01-02',
        white_username: 'junior',
        black_username: 'opponent',
        white_elo: 1700,
        black_elo: 1680,
        result: '0-1',
        time_control_raw: '180',
        eco_code: 'C50',
        opening_name: 'Italian Game',
      },
      'Junior',
    )
    expect(game?.userColor).toBe('white')
    expect(game?.opponent).toBe('opponent')
    expect(game?.result).toBe('loss')
    expect(game?.userElo).toBe(1700)
  })
})

describe('keyMomentFromMoves', () => {
  it('picks the user move with the largest centipawn loss', () => {
    const sans = ['e4', 'e5', 'Qh5']
    const plies = replaySan(sans)
    const stored: StoredMove[] = [
      { ply: 1, san: 'e4', uci: 'e2e4', mover: 'w', cpAfter: 30, cpLoss: 0, bestUci: 'e2e4' },
      { ply: 2, san: 'e5', uci: 'e7e5', mover: 'b', cpAfter: 20, cpLoss: 10, bestUci: 'e7e5' },
      { ply: 3, san: 'Qh5', uci: 'd1h5', mover: 'w', cpAfter: -80, cpLoss: 240, bestUci: 'g1f3' },
    ]
    const key = keyMomentFromMoves(stored, 'white', plies)
    expect(key?.ply).toBe(3)
    expect(key?.played).toBe('Qh5')
    expect(key?.best).toBe('Nf3')
    expect(key?.cpLoss).toBe(240)
    expect(key?.showEngine).toBe(true)
  })

  it('returns nothing when no user move has a stored loss', () => {
    const plies = replaySan(['e4'])
    const stored: StoredMove[] = [
      { ply: 1, san: 'e4', uci: 'e2e4', mover: 'w', cpAfter: null, cpLoss: null, bestUci: null },
    ]
    expect(keyMomentFromMoves(stored, 'white', plies)).toBeNull()
  })
})

function move(ply: number, cpAfter: number | null, cpLoss: number | null): StoredMove {
  return { ply, san: 'x', uci: 'a1a2', mover: ply % 2 === 1 ? 'w' : 'b', cpAfter, cpLoss, bestUci: null }
}

describe('evalSeries', () => {
  it('reads every stored eval from White, clamps at five pawns and flags mate', () => {
    const series = evalSeries([move(2, 120, 0), move(1, 30, 5), move(3, 800, 0), move(4, 10000, 900), move(5, null, null)], 'white')
    expect(series.map(point => point.ply)).toEqual([1, 2, 3, 4, 5])
    // Ply 2 is Black's move: +120 for Black is -1.2 for White.
    expect(series.map(point => point.pawns)).toEqual([0.3, -1.2, 5, -5, null])
    expect(series.map(point => point.mate)).toEqual([false, false, false, true, false])
    expect(series.map(point => point.mine)).toEqual([true, false, true, false, true])
  })
})

describe('gameStats', () => {
  it('counts the user moves by severity and leaves mate swings out of the average', () => {
    const stored = [move(1, 0, 20), move(3, 0, 60), move(5, 0, 150), move(7, 0, 400), move(9, 0, 9000), move(2, 0, 500), move(11, 0, null)]
    expect(gameStats(stored, 'white')).toEqual({
      evaluated: 5,
      averageCpLoss: Math.round((20 + 60 + 150 + 400) / 4),
      mateSwings: 1,
      inaccuracies: 1,
      mistakes: 1,
      blunders: 2,
    })
  })

  it('has no average without evaluated moves', () => {
    expect(gameStats([move(1, null, null)], 'white').averageCpLoss).toBeNull()
  })
})

describe('openingFamilyOf', () => {
  it('keeps the part before the colon', () => {
    expect(openingFamilyOf('Sicilian Defense: Najdorf Variation')).toBe('Sicilian Defense')
    expect(openingFamilyOf('Bird Opening')).toBe('Bird Opening')
  })
})
