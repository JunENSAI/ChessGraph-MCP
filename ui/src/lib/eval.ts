/** Centipawns from White's point of view. Mate is a signed ply count, also from White. */
export interface WhiteEval {
  whiteCp: number | null
  mate: number | null
}

const MATE_SENTINEL = 9000
const BAR_PAWNS = 5
const BAR_CP = BAR_PAWNS * 100

/**
 * Stored `eval_cp_after` is from the side that just moved.
 * White's centipawns are that value after a white move, and its negation after a black move.
 */
export function whiteEvalFromStored(cp: number, mover: 'w' | 'b'): WhiteEval {
  const whiteCp = mover === 'w' ? cp : -cp
  if (Math.abs(whiteCp) >= MATE_SENTINEL) {
    return { whiteCp, mate: whiteCp > 0 ? 1 : -1 }
  }
  return { whiteCp, mate: null }
}

/** Live Stockfish scores are from the side to move. */
export function whiteEvalFromSide(cp: number | null, mate: number | null, side: 'w' | 'b'): WhiteEval {
  const sign = side === 'w' ? 1 : -1
  return {
    whiteCp: cp === null ? null : cp * sign,
    mate: mate === null || mate === 0 ? null : mate * sign,
  }
}

/** Share of the bar that belongs to White, clamped at five pawns. Mate fills the bar. */
export function whiteShare(evaluation: WhiteEval): number {
  if (evaluation.mate !== null && evaluation.mate !== 0) return evaluation.mate > 0 ? 1 : 0
  if (evaluation.whiteCp === null) return 0.5
  const clamped = Math.max(-BAR_CP, Math.min(BAR_CP, evaluation.whiteCp))
  return (clamped + BAR_CP) / (BAR_CP * 2)
}

export function formatWhiteEval(evaluation: WhiteEval): string {
  if (evaluation.mate !== null && evaluation.mate !== 0) {
    return evaluation.mate > 0 ? `M${evaluation.mate}` : `-M${Math.abs(evaluation.mate)}`
  }
  if (evaluation.whiteCp === null) return '—'
  const pawns = evaluation.whiteCp / 100
  return `${pawns > 0 ? '+' : ''}${pawns.toFixed(1)}`
}

export function describeSideScore(type: 'cp' | 'mate', value: number, side: 'white' | 'black'): string {
  if (type === 'mate') {
    const moves = Math.abs(value)
    return value >= 0 ? `mate in ${moves} for ${side}` : `mate in ${moves} against ${side}`
  }
  const pawns = value / 100
  return `${pawns > 0 ? '+' : ''}${pawns.toFixed(2)} for ${side}`
}
