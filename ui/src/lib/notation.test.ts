import { describe, expect, it } from 'vitest'
import { buildPgn, glyphFor, pairMoves } from './notation'

describe('glyphFor', () => {
  it('uses the graph severity thresholds', () => {
    expect([null, 49, 50, 99, 100, 299, 300, 9600].map(glyphFor)).toEqual([null, null, '?!', '?!', '?', '?', '??', '??'])
  })
})

describe('pairMoves', () => {
  it('numbers White and Black pairs from the start position', () => {
    expect(pairMoves(3)).toEqual([
      { number: 1, white: 0, black: 1 },
      { number: 2, white: 2, black: null },
    ])
  })

  it('leaves the White cell empty when Black moves first', () => {
    const fen = '8/8/8/8/8/8/4k3/R3K3 b - - 0 41'
    expect(pairMoves(3, fen)).toEqual([
      { number: 41, white: null, black: 0 },
      { number: 42, white: 1, black: 2 },
    ])
  })

  it('returns no rows for no moves', () => {
    expect(pairMoves(0, '8/8/8/8/8/8/4k3/R3K3 b - - 0 41')).toEqual([])
  })
})

describe('buildPgn', () => {
  it('writes headers and numbered moves', () => {
    const pgn = buildPgn(['e4', 'e5', 'Nf3'], { white: 'You', black: 'Stockfish 1800', result: '*', date: new Date(2026, 10, 22) })
    expect(pgn).toContain('[White "You"]')
    expect(pgn).toContain('[Black "Stockfish 1800"]')
    expect(pgn).toContain('[Date "2026.11.22"]')
    expect(pgn).toContain('1. e4 e5 2. Nf3')
  })

  it('rejects an illegal move list', () => {
    expect(() => buildPgn(['e5'], { white: 'a', black: 'b' })).toThrow()
  })
})
