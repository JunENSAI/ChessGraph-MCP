import { formatWhiteEval, whiteShare, type WhiteEval } from '../lib/eval'

interface EvalBarProps {
  orientation: 'white' | 'black'
  evaluation: WhiteEval
  pending?: boolean
}

export function EvalBar({ orientation, evaluation, pending = false }: EvalBarProps) {
  const label = pending && evaluation.whiteCp === null && evaluation.mate === null ? '…' : formatWhiteEval(evaluation)
  const share = whiteShare(evaluation)
  const bottomShare = orientation === 'white' ? share : 1 - share
  const bottom = orientation === 'white' ? '#f0d9b5' : '#2b241c'
  const top = orientation === 'white' ? '#2b241c' : '#f0d9b5'

  return (
    <div className="eval-bar" role="img" aria-label={`Evaluation ${label}`}>
      <div className="eval-fill top" style={{ flex: Math.max(0, 1 - bottomShare), background: top }} />
      <div className="eval-fill bottom" style={{ flex: Math.max(0.001, bottomShare), background: bottom }} />
      <span className="eval-label">{label}</span>
    </div>
  )
}
