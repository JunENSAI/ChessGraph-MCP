import { Chess, type Square } from 'chess.js'
import type { WhiteEval } from './eval'

export type Promotion = 'q' | 'r' | 'b' | 'n'

export interface ReplayedPly {
  ply: number
  san: string
  from: Square
  to: Square
  fenBefore: string
  fenAfter: string
}

export interface AppliedMove {
  san: string
  from: Square
  to: Square
  fen: string
}

export function sideToMove(fen: string): 'w' | 'b' {
  return fen.split(' ')[1] === 'b' ? 'b' : 'w'
}

export function replaySan(sans: string[], startFen?: string): ReplayedPly[] {
  const chess = startFen ? new Chess(startFen) : new Chess()
  const plies: ReplayedPly[] = []
  for (const san of sans) {
    const fenBefore = chess.fen()
    const move = chess.move(san)
    plies.push({
      ply: plies.length + 1,
      san: move.san,
      from: move.from,
      to: move.to,
      fenBefore,
      fenAfter: chess.fen(),
    })
  }
  return plies
}

export function tryUci(fen: string, uci: string): AppliedMove | null {
  if (uci.length < 4) return null
  return tryMove(fen, uci.slice(0, 2) as Square, uci.slice(2, 4) as Square, uci.length > 4 ? (uci[4] as Promotion) : undefined)
}

export function tryMove(fen: string, from: Square, to: Square, promotion?: Promotion): AppliedMove | null {
  try {
    const chess = new Chess(fen)
    const move = chess.move({ from, to, promotion })
    return { san: move.san, from: move.from, to: move.to, fen: chess.fen() }
  } catch {
    return null
  }
}

export function legalTargets(fen: string, from: Square): Square[] {
  try {
    return new Chess(fen).moves({ square: from, verbose: true }).map(move => move.to)
  } catch {
    return []
  }
}

export function isPromotion(fen: string, from: Square, to: Square): boolean {
  try {
    const chess = new Chess(fen)
    const piece = chess.get(from)
    if (!piece || piece.type !== 'p') return false
    const rank = to[1]
    return (piece.color === 'w' && rank === '8') || (piece.color === 'b' && rank === '1')
  } catch {
    return false
  }
}

export function resultText(fen: string): string | null {
  let chess: Chess
  try {
    chess = new Chess(fen)
  } catch {
    return null
  }
  if (!chess.isGameOver()) return null
  if (chess.isCheckmate()) {
    const winner = chess.turn() === 'w' ? 'Black' : 'White'
    return `${winner} wins by checkmate`
  }
  if (chess.isStalemate()) return 'Stalemate'
  if (chess.isThreefoldRepetition()) return 'Draw by repetition'
  if (chess.isInsufficientMaterial()) return 'Draw by insufficient material'
  return 'Draw'
}

export function gameStatus(fen: string): string | null {
  const finished = resultText(fen)
  if (finished) return finished
  try {
    return new Chess(fen).isCheck() ? 'Check' : null
  } catch {
    return null
  }
}

/** Freeze the evaluation bar once the position is decided. */
export function resultEval(fen: string): WhiteEval | null {
  let chess: Chess
  try {
    chess = new Chess(fen)
  } catch {
    return null
  }
  if (!chess.isGameOver()) return null
  if (chess.isCheckmate()) {
    const whiteMated = chess.turn() === 'w'
    return { whiteCp: null, mate: whiteMated ? -1 : 1 }
  }
  return { whiteCp: 0, mate: null }
}
