export interface WhiteEval {
  whiteCp: number | null
  mate: number | null
}

type Side = 'w' | 'b'
type ColorName = 'white' | 'black'

/** Stored centipawns are from the mover. Return the same score for White. */
export function whiteEvalFromStored(cp: number, mover: Side): WhiteEval {
  return { whiteCp: mover === 'b' ? -cp : cp, mate: null }
}

/** Engine scores are from the side to move. Return them for White. */
export function whiteEvalFromSide(cp: number | null, mate: number | null, side: Side): WhiteEval {
  if (side === 'w') return { whiteCp: cp, mate }
  return {
    whiteCp: cp === null ? null : -cp,
    mate: mate === null ? null : -mate,
  }
}

export function describeSideScore(scoreType: 'cp' | 'mate', scoreValue: number, side: ColorName): string {
  if (scoreType === 'mate') {
    const winner = scoreValue >= 0 ? side : side === 'white' ? 'black' : 'white'
    return `mate in ${Math.abs(scoreValue)} for ${winner}`
  }
  const pawns = (scoreValue / 100).toFixed(2)
  const signed = scoreValue > 0 ? `+${pawns}` : pawns
  return `${signed} for ${side}`
}

export function formatWhiteEval(evaluation: WhiteEval): string {
  if (evaluation.mate !== null && evaluation.mate !== 0) {
    const sign = evaluation.mate > 0 ? '+' : '-'
    return `${sign}M${Math.abs(evaluation.mate)}`
  }
  if (evaluation.whiteCp === null) return '0.0'
  const pawns = Math.abs(evaluation.whiteCp) / 100
  const text = pawns.toFixed(1)
  if (evaluation.whiteCp > 0) return `+${text}`
  if (evaluation.whiteCp < 0) return `-${text}`
  return '0.0'
}

/** White's share of the bar, from a capped centipawn score. */
export function whiteShare(evaluation: WhiteEval): number {
  if (evaluation.mate !== null && evaluation.mate !== 0) return evaluation.mate > 0 ? 0.96 : 0.04
  if (evaluation.whiteCp === null) return 0.5
  const capped = Math.max(-1000, Math.min(1000, evaluation.whiteCp))
  return 1 / (1 + 10 ** (-capped / 400))
}
