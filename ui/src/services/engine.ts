import { describeSideScore, whiteEvalFromSide, type WhiteEval } from '../lib/eval'

export interface EngineAnalysis {
  uci: string
  san: string
  /** Principal variation, starting with the chosen move. */
  pv: string[]
  /** Score from the side to move, before the move is played. */
  scoreType: 'cp' | 'mate'
  scoreValue: number
  side: 'white' | 'black'
  evalText: string
  white: WhiteEval
}

export interface SearchBudget {
  limitType?: 'depth' | 'nodes' | 'time'
  limitValue?: number
}

interface AnalysisResponse {
  root_player?: 'white' | 'black'
  lines?: {
    move_uci?: string | null
    move_san?: string | null
    score?: { type?: 'cp' | 'mate'; value?: number }
    pv?: { uci?: string[] }
  }[]
}

const inflight = new Map<string, Promise<EngineAnalysis>>()

export class EngineError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'EngineError'
  }
}

async function requestAnalysis(fen: string, budget: SearchBudget = {}): Promise<EngineAnalysis> {
  let response: Response
  try {
    response = await fetch('/api/engine/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        fen,
        multipv: 1,
        ...(budget.limitType ? { limit_type: budget.limitType, limit_value: budget.limitValue } : {}),
      }),
    })
  } catch {
    throw new EngineError('Stockfish is not reachable.')
  }
  if (!response.ok) {
    let detail = `Stockfish request failed (${response.status}).`
    try {
      const body = (await response.json()) as { error?: string }
      if (body.error) detail = body.error
    } catch {
      // Keep the status message when the body is not JSON.
    }
    throw new EngineError(detail)
  }
  const payload = (await response.json()) as AnalysisResponse
  const line = payload.lines?.[0]
  const side = payload.root_player === 'black' ? 'black' : 'white'
  if (!line?.move_uci || !line.move_san || !line.score || line.score.value === undefined || !line.score.type) {
    throw new EngineError('Stockfish returned no move.')
  }
  const scoreType = line.score.type
  const scoreValue = line.score.value
  const pv = (line.pv?.uci ?? []).filter(move => move.length > 0)
  return {
    uci: line.move_uci,
    san: line.move_san,
    pv: pv.length > 0 ? pv : [line.move_uci],
    scoreType,
    scoreValue,
    side,
    evalText: describeSideScore(scoreType, scoreValue, side),
    white: whiteEvalFromSide(
      scoreType === 'cp' ? scoreValue : null,
      scoreType === 'mate' ? scoreValue : null,
      side === 'white' ? 'w' : 'b',
    ),
  }
}

/** One search per position and budget while a request is already running. */
export function analyzeFen(fen: string, budget: SearchBudget = {}): Promise<EngineAnalysis> {
  const key = `${fen}|${budget.limitType ?? 'default'}|${budget.limitValue ?? ''}`
  const existing = inflight.get(key)
  if (existing) return existing
  const promise = requestAnalysis(fen, budget).finally(() => {
    if (inflight.get(key) === promise) inflight.delete(key)
  })
  inflight.set(key, promise)
  return promise
}

/** Short search used by the evaluation bar so the number tracks the position. */
export const BAR_BUDGET: SearchBudget = { limitType: 'time', limitValue: 250 }
