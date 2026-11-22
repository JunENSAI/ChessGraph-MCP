import { describe, expect, it } from 'vitest'
import { explorerRows, formatScore, type ExplorerJson } from './explorer'

const payload: ExplorerJson = {
  fen_norm: 'start',
  context: { engine_best: { uci: 'e2e4', san: 'e4' } },
  moves: [
    { relationship: 'PLAYED_MOVE', uci_move: 'd2d4', san_move: 'd4', by: 'owner', games: 1843, score_pct: 57.8, avg_cp_loss: 9, mistakes: 3, blunders: 1 },
    { relationship: 'PLAYED_MOVE', uci_move: 'e2e4', san_move: 'e4', by: 'opponent', games: 1256, score_pct: 48 },
    { relationship: 'PLAYED_MOVE', uci_move: 'd2d4', san_move: 'd4', by: 'opponent', games: 615, score_pct: 51 },
    { relationship: 'THEORY_MOVE', uci_move: 'd2d4', san_move: 'd4', eco_codes: ['A40', 'D00'] },
    { relationship: 'THEORY_MOVE', uci_move: 'c2c4', san_move: 'c4', eco_codes: ['A10'] },
    { relationship: 'THEORY_MOVE', uci_move: 'b2b4', san_move: 'b4', eco_codes: ['A00', 'A00b'] },
  ],
  games: { total_games: 0, owner_wins: 0, owner_draws: 0, owner_losses: 0, games: [] },
}

describe('explorerRows', () => {
  it('merges book, your and opponents moves into one row per move', () => {
    const rows = explorerRows(payload)
    expect(rows.map(row => row.san)).toEqual(['d4', 'e4', 'b4', 'c4'])
    const d4 = rows[0]
    expect(d4.book).toBe(true)
    expect(d4.ecoCount).toBe(2)
    expect(d4.you).toEqual({ games: 1843, scorePct: 57.8, avgCpLoss: 9, errors: 4 })
    expect(d4.opponents?.games).toBe(615)
    expect(rows[1].engineBest).toBe(true)
    expect(rows[1].book).toBe(false)
  })

  it('handles an unknown position', () => {
    expect(explorerRows({ ...payload, context: null, moves: [] })).toEqual([])
  })
})

describe('formatScore', () => {
  it('rounds and marks a missing sample', () => {
    expect(formatScore(57.8)).toBe('58%')
    expect(formatScore(null)).toBe('–')
  })
})
