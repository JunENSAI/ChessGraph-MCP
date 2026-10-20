import { describe, expect, it } from 'vitest'
import { replaySan } from '../lib/chess'
import { keyMomentFromMoves, listedGame, outcomeFor, type StoredMove } from './games'

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
