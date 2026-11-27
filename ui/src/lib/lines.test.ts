import { describe, expect, it } from 'vitest'
import type { CandidateLine, CandidateLines } from '../services/coach'
import { firstMoveArrows, humanReason, LINE_COLORS, lineColor, lineEval, lineLabel, pathArrows } from './lines'

const START = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1'

function line(rank: number, uci: string[], san: string[], value = 30, extra: Partial<CandidateLine> = {}): CandidateLine {
  return { rank, uci, san, score: { type: 'cp', value }, games: 0, book: false, human: false, ...extra }
}

const lines: CandidateLines = {
  fen: START,
  root_player: 'white',
  depth: 18,
  lines: [
    line(1, ['e2e4', 'e7e5', 'g1f3'], ['e4', 'e5', 'Nf3'], 35, { games: 9, human: true }),
    line(2, ['d2d4', 'd7d5'], ['d4', 'd5'], 30, { book: true }),
    line(3, ['x9x9'], ['??'], 20),
  ],
}

describe('candidate lines on the board', () => {
  it('colors each rank and cycles past three', () => {
    expect(lineColor(1)).toBe(LINE_COLORS[0])
    expect(lineColor(3)).toBe(LINE_COLORS[2])
    expect(lineColor(4)).toBe(LINE_COLORS[0])
  })

  it('draws the first move of each legal line in its rank color', () => {
    expect(firstMoveArrows(lines)).toEqual([
      { startSquare: 'e2', endSquare: 'e4', color: LINE_COLORS[0] },
      { startSquare: 'd2', endSquare: 'd4', color: LINE_COLORS[1] },
    ])
  })

  it('draws a whole line, fading move by move, and stops at an illegal move', () => {
    const arrows = pathArrows(START, line(2, ['d2d4', 'd7d5', 'a1a8', 'c2c4'], []))
    expect(arrows.map(arrow => `${arrow.startSquare}${arrow.endSquare}`)).toEqual(['d2d4', 'd7d5'])
    expect(arrows[0].color).toBe('rgba(119, 167, 255, 1)')
    expect(arrows[1].color).toBe('rgba(119, 167, 255, 0.86)')
  })

  it('shows the eval from White and labels the chip', () => {
    expect(lineEval(lines.lines[0], 'white')).toBe('+0.3')
    expect(lineEval(line(1, ['a'], [], 120), 'black')).toBe('-1.2')
    expect(lineEval({ ...line(1, ['a'], []), score: { type: 'mate', value: 3 } }, 'black')).toBe('-M3')
    expect(lineLabel(lines.lines[0], 'white')).toBe('e4 e5 Nf3 · +0.3')
  })

  it('explains the human tag', () => {
    expect(humanReason(lines.lines[0])).toBe('Played here in 9 of your stored games')
    expect(humanReason({ ...lines.lines[1], human: true })).toBe('Book move')
    expect(humanReason(lines.lines[1])).toBeNull()
  })
})
