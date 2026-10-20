import { describeSideScore, whiteEvalFromSide, type WhiteEval } from '../lib/eval'

export interface EngineAnalysis {
  uci: string
  san: string
  /** Score from the side to move, before the move is played. */
  scoreType: 'cp' | 'mate'
  scoreValue: number
  side: 'white' | 'black'
  evalText: string
  white: WhiteEval
}

interface AnalysisResponse {
  root_player?: 'white' | 'black'
  lines?: {
    move_uci?: string | null
    move_san?: string | null
    score?: { type?: 'cp' | 'mate'; value?: number }
  }[]
}

const inflight = new Map<string, Promise<EngineAnalysis>>()

export class EngineError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'EngineError'
  }
}

async function requestAnalysis(fen: string): Promise<EngineAnalysis> {
  let response: Response
  try {
    response = await fetch('/api/engine/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ fen, multipv: 1 }),
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
  return {
    uci: line.move_uci,
    san: line.move_san,
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

/** One search per position while a request is already running. */
export function analyzeFen(fen: string): Promise<EngineAnalysis> {
  const existing = inflight.get(fen)
  if (existing) return existing
  const promise = requestAnalysis(fen).finally(() => {
    if (inflight.get(fen) === promise) inflight.delete(fen)
  })
  inflight.set(fen, promise)
  return promise
}
