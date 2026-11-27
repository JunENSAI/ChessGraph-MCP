import type { Arrow } from 'react-chessboard'
import type { CandidateLine, CandidateLines } from '../services/coach'
import { tryUci } from './chess'
import { formatWhiteEval, whiteEvalFromSide } from './eval'

/** Rank colors for the coach's candidate lines: best first. */
export const LINE_COLORS = ['#b8f05a', '#77a7ff', '#ffc46b'] as const

export function lineColor(rank: number): string {
  return LINE_COLORS[(rank - 1) % LINE_COLORS.length]
}

function withAlpha(hex: string, alpha: number): string {
  const value = parseInt(hex.slice(1), 16)
  return `rgba(${(value >> 16) & 255}, ${(value >> 8) & 255}, ${value & 255}, ${alpha})`
}

/** The first move of every candidate line, in its rank color. */
export function firstMoveArrows(lines: CandidateLines): Arrow[] {
  return lines.lines.flatMap(line => {
    const applied = tryUci(lines.fen, line.uci[0] ?? '')
    return applied ? [{ startSquare: applied.from, endSquare: applied.to, color: lineColor(line.rank) }] : []
  })
}

/** The whole path of one line, fading move by move, so the board shows where it leads. */
export function pathArrows(fen: string, line: CandidateLine, maxMoves = 6): Arrow[] {
  const arrows: Arrow[] = []
  let position = fen
  for (const [index, uci] of line.uci.slice(0, maxMoves).entries()) {
    const applied = tryUci(position, uci)
    if (!applied) break
    arrows.push({
      startSquare: applied.from,
      endSquare: applied.to,
      color: withAlpha(lineColor(line.rank), Math.max(0.3, 1 - index * 0.14)),
    })
    position = applied.fen
  }
  return arrows
}

/** The eval of a line from White's side, e.g. "+0.4" or "M3". */
export function lineEval(line: CandidateLine, rootPlayer: CandidateLines['root_player']): string {
  const side = rootPlayer === 'white' ? 'w' : 'b'
  const score = line.score
  return formatWhiteEval(
    whiteEvalFromSide(score.type === 'cp' ? score.value : null, score.type === 'mate' ? score.value : null, side),
  )
}

/** Short chip text: the first moves in SAN and the eval. */
export function lineLabel(line: CandidateLine, rootPlayer: CandidateLines['root_player'], moves = 3): string {
  return `${line.san.slice(0, moves).join(' ')} · ${lineEval(line, rootPlayer)}`
}

/** Why a line is tagged human, for the chip's tooltip. */
export function humanReason(line: CandidateLine): string | null {
  if (!line.human) return null
  return line.games > 0 ? `Played here in ${line.games} of your stored games` : 'Book move'
}
