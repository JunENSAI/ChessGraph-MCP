import { describe, expect, it } from 'vitest'
import { Chess } from 'chess.js'
import { LESSON_PLIES, lineFromPgn, lineFromUci, sessionFromEndgame, sessionFromOpening } from './lessons'

describe('lineFromUci', () => {
  it('stops at 12 plies', () => {
    const uci = 'e2e4 e7e5 g1f3 b8c6 f1c4 g8f6 d2d3 f8c5 c2c3 d7d6 e1g1 e8g8 a2a3'
    const line = lineFromUci(uci)
    expect(line).toHaveLength(LESSON_PLIES)
    expect(line[0].san).toBe('e4')
    expect(line[11].san).toBe('O-O')
  })

  it('stops when a token is illegal', () => {
    expect(lineFromUci('e2e4 e7e5 e2e4')).toHaveLength(2)
  })
})

describe('lineFromPgn', () => {
  it('drops move numbers and keeps the SAN line', () => {
    expect(lineFromPgn('1. e4 e5 2. Nf3').map(step => step.san)).toEqual(['e4', 'e5', 'Nf3'])
  })
})

describe('sessionFromOpening', () => {
  it('builds a white drill from the theory line', () => {
    const session = sessionFromOpening(
      { openingName: 'Italian Game', ecoCode: 'C50', games: 8, uciLine: 'e2e4 e7e5', pgnLine: null },
      'white',
    )
    expect(session.userColor).toBe('white')
    expect(session.line.map(step => step.san)).toEqual(['e4', 'e5'])
    expect(session.missingLine).toBe(false)
  })

  it('reports a missing theory line', () => {
    const session = sessionFromOpening(
      { openingName: 'Unlisted', ecoCode: null, games: 3, uciLine: null, pgnLine: null },
      'black',
    )
    expect(session.missingLine).toBe(true)
    expect(session.line).toEqual([])
    expect(session.detail).toMatch(/No stored theory line/)
  })
})

describe('sessionFromEndgame', () => {
  it('expects the stored move and then hands the position to Stockfish', () => {
    const fen = new Chess('4k3/8/8/8/8/8/4P3/4K3 w - - 0 1').fen()
    const session = sessionFromEndgame({
      endgameType: 'king_pawn',
      fenFull: fen,
      humanMoveUci: 'e2e4',
      eloTier: '1600-1800',
      pieceCount: 3,
    })
    expect(session?.line[0].san).toBe('e4')
    expect(session?.engineAfter).toBe(true)
    expect(session?.userColor).toBe('white')
  })
})
