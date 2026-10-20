import { describe, expect, it, vi } from 'vitest'
import { replaySan } from '../lib/chess'
import { GAMES_PAGE, keyMomentFromMoves, listedGame, loadGameMoves, loadGamesPage, loadPlayerName, outcomeFor, type StoredMove } from './games'

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

function gameRow(id: number) {
  return {
    game_id: id,
    game_type: 'rapid',
    played_date: '2026-04-02',
    white_username: 'white',
    black_username: 'black',
    white_elo: 1500,
    black_elo: 1480,
    result: '1-0',
    time_control_raw: '600',
    eco_code: 'C50',
    opening_name: 'Italian Game',
  }
}

describe('loadGamesPage', () => {
  it('maps the account games and asks for another page only when the page is full', async () => {
    const fetchImpl = vi.fn(async () => new Response(JSON.stringify({ games: [gameRow(4)] }), { status: 200 }))
    const page = await loadGamesPage('white', 'rapid', 0, fetchImpl)
    expect(page.games).toHaveLength(1)
    expect(page.games[0].opponent).toBe('black')
    expect(page.games[0].userColor).toBe('white')
    expect(page.hasMore).toBe(false)
    expect(fetchImpl).toHaveBeenCalledWith(`/api/games?game_type=rapid&limit=${GAMES_PAGE}&offset=0`)
  })

  it('surfaces a database error instead of sample games', async () => {
    const fetchImpl = vi.fn(
      async () => new Response(JSON.stringify({ error: 'PostgreSQL is not accepting connections.' }), { status: 503 }),
    )
    await expect(loadGamesPage('white', 'blitz', 0, fetchImpl)).rejects.toThrow(
      'PostgreSQL is not accepting connections.',
    )
  })

  it('reports when the retrieval API is not responding', async () => {
    const fetchImpl = vi.fn(async () => Promise.reject(new TypeError('Failed to fetch')))
    await expect(loadPlayerName(fetchImpl)).rejects.toThrow('The retrieval API is not responding.')
  })
})

describe('loadGameMoves', () => {
  it('follows the next page until a short page arrives', async () => {
    const calls: string[] = []
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url
      calls.push(url)
      const start = Number(new URL(url, 'http://local').searchParams.get('start_ply'))
      const count = start === 1 ? 100 : 1
      const moves = Array.from({ length: count }, (_, index) => ({
        ply_number: start + index,
        turn_color: 'w',
        san_move: 'e4',
        uci_move: 'e2e4',
        eval_cp_after: 12,
        cp_loss: index === 0 && start > 1 ? 40 : 0,
        best_move_uci: 'e2e4',
      }))
      return new Response(JSON.stringify({ moves }), { status: 200 })
    })
    const stored = await loadGameMoves(4, fetchImpl)
    expect(stored).toHaveLength(101)
    expect(stored[100].cpLoss).toBe(40)
    expect(calls[1]).toContain('start_ply=101')
  })
})
