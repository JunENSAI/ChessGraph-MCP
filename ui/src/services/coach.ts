import type { OrbState } from 'thinking-orbs'

export type CoachPhase = 'idle' | 'postgres' | 'neo4j' | 'stockfish' | 'composing'

export interface CoachMessage {
  id: string
  role: 'user' | 'coach'
  text: string
  demo?: boolean
}

export interface CoachContext {
  mode: 'training' | 'review'
  fen: string
  summary: string
}

export const PHASE_ORB: Record<CoachPhase, OrbState> = {
  idle: 'breathing',
  postgres: 'searching',
  neo4j: 'connecting',
  stockfish: 'solving',
  composing: 'composing',
}

export const PHASE_LABEL: Record<CoachPhase, string> = {
  idle: 'Ready',
  postgres: 'Reading your games',
  neo4j: 'Traversing ChessGraph',
  stockfish: 'Checking with Stockfish',
  composing: 'Writing the explanation',
}

export const PHASE_TRACE: Exclude<CoachPhase, 'idle'>[] = ['postgres', 'neo4j', 'stockfish', 'composing']

let messageCounter = 0
export function createMessage(role: CoachMessage['role'], text: string, demo = false): CoachMessage {
  messageCounter += 1
  return { id: `m-${messageCounter}`, role, text, demo }
}

const wait = (ms: number) => new Promise(resolve => window.setTimeout(resolve, ms))

/**
 * Demo transport. A later version posts the question and board context to
 * HERMES_API_URL with HERMES_API_KEY (see .env.template). Hermes answers
 * using the ChessGraph MCP servers. Do not read the key from a VITE_ variable.
 */
export async function askCoach(
  question: string,
  context: CoachContext,
  onPhase: (phase: CoachPhase) => void,
): Promise<CoachMessage> {
  for (const phase of PHASE_TRACE) {
    onPhase(phase)
    await wait(phase === 'stockfish' ? 650 : 380)
  }
  onPhase('idle')
  const subject = context.mode === 'training' ? 'this training position' : 'this position from your game'
  return createMessage(
    'coach',
    `You asked: “${question}” For ${subject} (${context.summary}), I would compare your personal games, ` +
      'the graph continuations, and a same-root Stockfish search before stating a reason.',
    true,
  )
}
