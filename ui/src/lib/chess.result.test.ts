import { describe, expect, it } from 'vitest'
import { isPromotion, resultText, tryMove } from './chess'

describe('resultText', () => {
  it('names the side that delivered checkmate', () => {
    expect(resultText('7k/5QK1/8/8/8/8/8/8 b - - 0 1')).toBe('White wins by checkmate')
    expect(resultText('8/8/8/8/8/8/5qk1/7K w - - 0 1')).toBe('Black wins by checkmate')
  })
})

describe('promotion', () => {
  const fen = '7k/4P3/8/8/8/8/8/4K3 w - - 0 1'

  it('recognizes a pawn move to the last rank', () => {
    expect(isPromotion(fen, 'e7', 'e8')).toBe(true)
    expect(isPromotion(fen, 'e7', 'e6')).toBe(false)
  })

  it('promotes to the chosen piece', () => {
    expect(tryMove(fen, 'e7', 'e8', 'q')?.san).toContain('=Q')
    expect(tryMove(fen, 'e7', 'e8', 'r')?.san).toContain('=R')
    expect(tryMove(fen, 'e7', 'e8', 'b')?.san).toContain('=B')
    expect(tryMove(fen, 'e7', 'e8', 'n')?.san).toContain('=N')
  })
})
