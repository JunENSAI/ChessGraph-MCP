import { describe, expect, it } from 'vitest'
import { materialBalance } from './material'

describe('materialBalance', () => {
  it('is level at the start', () => {
    expect(materialBalance('rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1')).toEqual({
      capturedByWhite: [],
      capturedByBlack: [],
      diff: 0,
    })
  })

  it('lists captures by value and counts the difference in pawns', () => {
    // White is missing a knight; Black is missing the queen and a pawn.
    const fen = 'rnb1kbnr/ppp1pppp/8/8/8/8/PPPPPPPP/R1BQKBNR w KQkq - 0 5'
    expect(materialBalance(fen)).toEqual({ capturedByWhite: ['q', 'p'], capturedByBlack: ['n'], diff: 7 })
  })

  it('never shows a negative capture after a promotion', () => {
    // White has two queens and seven pawns.
    const fen = '4k3/8/8/8/8/8/PPPPPPP1/QQ2K3 w - - 0 50'
    const balance = materialBalance(fen)
    expect(balance.capturedByBlack).toEqual(['r', 'r', 'b', 'b', 'n', 'n', 'p'])
    expect(balance.diff).toBe(25)
  })
})
