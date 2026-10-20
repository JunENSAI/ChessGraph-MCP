import { useEffect, useState } from 'react'
import { analyzeFen } from '../services/engine'
import type { WhiteEval } from '../lib/eval'

const EMPTY: WhiteEval = { whiteCp: null, mate: null }

/**
 * Prefer a stored White evaluation. Otherwise search the current FEN.
 * `stored` null means this ply has no stored score, so the bar searches.
 */
export function usePositionEval(fen: string, stored?: WhiteEval | null) {
  const [live, setLive] = useState<{ fen: string; evaluation: WhiteEval } | null>(null)
  const [pending, setPending] = useState(false)
  const hasStored = stored != null && (stored.whiteCp !== null || stored.mate !== null)

  useEffect(() => {
    if (hasStored) return
    let active = true
    setPending(true)
    analyzeFen(fen)
      .then(result => {
        if (active) setLive({ fen, evaluation: result.white })
      })
      .catch(() => {
        if (active) setLive({ fen, evaluation: EMPTY })
      })
      .finally(() => {
        if (active) setPending(false)
      })
    return () => {
      active = false
    }
  }, [fen, hasStored])

  if (hasStored && stored) return { evaluation: stored, pending: false }
  if (live?.fen === fen) return { evaluation: live.evaluation, pending }
  return { evaluation: EMPTY, pending: true }
}
