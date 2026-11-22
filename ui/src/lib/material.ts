export type PieceLetter = 'p' | 'n' | 'b' | 'r' | 'q'

const START_COUNT: Record<PieceLetter, number> = { p: 8, n: 2, b: 2, r: 2, q: 1 }
export const PIECE_VALUE: Record<PieceLetter, number> = { p: 1, n: 3, b: 3, r: 5, q: 9 }
const ORDER: PieceLetter[] = ['q', 'r', 'b', 'n', 'p']

export interface MaterialBalance {
  /** Black pieces that White has captured, most valuable first. */
  capturedByWhite: PieceLetter[]
  /** White pieces that Black has captured. */
  capturedByBlack: PieceLetter[]
  /** White material minus Black material, in pawns (1/3/3/5/9). */
  diff: number
}

/**
 * Captured pieces are the start set minus what is on the board. A promoted
 * piece can make a count exceed the start set; that never shows as negative.
 */
export function materialBalance(fen: string): MaterialBalance {
  const placement = fen.trim().split(/\s+/)[0] ?? ''
  const white: Record<PieceLetter, number> = { p: 0, n: 0, b: 0, r: 0, q: 0 }
  const black: Record<PieceLetter, number> = { p: 0, n: 0, b: 0, r: 0, q: 0 }
  for (const char of placement) {
    const letter = char.toLowerCase() as PieceLetter
    if (!(letter in START_COUNT)) continue
    if (char === letter) black[letter] += 1
    else white[letter] += 1
  }
  const captured = (side: Record<PieceLetter, number>) =>
    ORDER.flatMap(letter => Array<PieceLetter>(Math.max(0, START_COUNT[letter] - side[letter])).fill(letter))
  const total = (side: Record<PieceLetter, number>) =>
    ORDER.reduce((sum, letter) => sum + side[letter] * PIECE_VALUE[letter], 0)
  return {
    capturedByWhite: captured(black),
    capturedByBlack: captured(white),
    diff: total(white) - total(black),
  }
}
