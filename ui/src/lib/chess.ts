import { Chess, type Square } from 'chess.js'

export interface ReplayedPly {
  ply: number
  san: string
  from: Square
  to: Square
  fenBefore: string
  fenAfter: string
}

export function replaySan(moves: string[], startFen?: string): ReplayedPly[] {
  const chess = startFen ? new Chess(startFen) : new Chess()
  return moves.map((san, index) => {
    const fenBefore = chess.fen()
    const move = chess.move(san)
    return {
      ply: index + 1,
      san: move.san,
      from: move.from,
      to: move.to,
      fenBefore,
      fenAfter: chess.fen(),
    }
  })
}

export function legalTargets(fen: string, square: Square): Square[] {
  return new Chess(fen).moves({ square, verbose: true }).map(move => move.to)
}

export interface AppliedMove {
  san: string
  from: Square
  to: Square
  fen: string
}

export type Promotion = 'q' | 'r' | 'b' | 'n'

/** True when this pawn move can only be completed by choosing a promotion piece. */
export function isPromotion(fen: string, from: Square, to: Square): boolean {
  const chess = new Chess(fen)
  return chess.moves({ square: from, verbose: true }).some(move => move.to === to && move.promotion)
}

/** Returns null for illegal moves. A promoting move requires the chosen piece. */
export function tryMove(fen: string, from: Square, to: Square, promotion?: Promotion): AppliedMove | null {
  const chess = new Chess(fen)
  try {
    const move = chess.move({ from, to, promotion: promotion ?? 'q' })
    return { san: move.san, from: move.from, to: move.to, fen: chess.fen() }
  } catch {
    return null
  }
}

const UCI_MOVE = /^[a-h][1-8][a-h][1-8][qrbn]?$/

/** Returns null when the UCI move is illegal in this position. */
export function tryUci(fen: string, uci: string): AppliedMove | null {
  const token = uci.trim().toLowerCase()
  if (!UCI_MOVE.test(token)) return null
  const chess = new Chess(fen)
  try {
    const move = chess.move({
      from: token.slice(0, 2),
      to: token.slice(2, 4),
      promotion: token[4] as 'q' | 'r' | 'b' | 'n' | undefined,
    })
    return { san: move.san, from: move.from, to: move.to, fen: chess.fen() }
  } catch {
    return null
  }
}

export function sideToMove(fen: string): 'w' | 'b' {
  return fen.split(' ')[1] === 'b' ? 'b' : 'w'
}

export function gameStatus(fen: string): string | null {
  const chess = new Chess(fen)
  if (chess.isCheckmate()) return 'Checkmate'
  if (chess.isStalemate()) return 'Stalemate'
  if (chess.isInsufficientMaterial()) return 'Draw by insufficient material'
  if (chess.isThreefoldRepetition()) return 'Draw by repetition'
  if (chess.isDraw()) return 'Draw'
  if (chess.inCheck()) return 'Check'
  return null
}

/** Immediate bar score when the game is already over, so the UI does not wait on a search. */
export function resultEval(fen: string): { whiteCp: number | null; mate: number | null } | null {
  let chess: Chess
  try {
    chess = new Chess(fen)
  } catch {
    return null
  }
  if (chess.isCheckmate()) {
    const whiteWins = chess.turn() === 'b'
    return { whiteCp: null, mate: whiteWins ? 1 : -1 }
  }
  if (chess.isDraw()) return { whiteCp: 0, mate: null }
  return null
}

/** Who won, or the draw reason. Checkmate names the side that delivered it. */
export function resultText(fen: string): string | null {
  let chess: Chess
  try {
    chess = new Chess(fen)
  } catch {
    return null
  }
  if (chess.isCheckmate()) {
    const winner = chess.turn() === 'w' ? 'Black' : 'White'
    return `${winner} wins by checkmate`
  }
  if (chess.isStalemate()) return 'Draw by stalemate'
  if (chess.isInsufficientMaterial()) return 'Draw by insufficient material'
  if (chess.isThreefoldRepetition()) return 'Draw by repetition'
  if (chess.isDraw()) return 'Draw'
  return null
}

export function formatEval(centipawns: number): string {
  const pawns = centipawns / 100
  return `${pawns > 0 ? '+' : ''}${pawns.toFixed(2)}`
}
