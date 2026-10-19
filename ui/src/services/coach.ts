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

/** Same-origin path served by the Vite proxy, which injects the bearer key. */
const COACH_ENDPOINT = '/hermes-api/chat/completions'
const COACH_MODEL = 'hermes-agent'
const REQUEST_TIMEOUT_MS = 180_000

/** Raised when the coach call cannot produce an evidence-backed answer. */
export class CoachUnavailableError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'CoachUnavailableError'
  }
}

interface ChatCompletion {
  choices?: { message?: { content?: string | null } | null }[] | null
}

function buildPrompt(question: string, context: CoachContext): string {
  const subject = context.mode === 'training' ? 'training position' : 'position from my game'
  return [
    `Position (normalized FEN): ${context.fen}`,
    `Context: ${subject} — ${context.summary}`,
    '',
    question,
    '',
    'Gather evidence with the chess_postgres, chess_neo4j, and chess_stockfish MCP tools in that order,',
    'use chess_stockfish_validate_line for any continuation you cite, and state only what those tools returned.',
    'If a tool returned nothing, say the evidence is missing instead of filling the gap.',
  ].join('\n')
}

function failureFor(status: number): string {
  if (status === 401) {
    return 'Hermes rejected the key. Check that HERMES_API_KEY in the project .env matches API_SERVER_KEY in ~/.hermes/.env, then restart the gateway.'
  }
  if (status === 403) {
    return (
      'The Hermes gateway refused the request because it carried an Origin header. ' +
      'It accepts no cross-origin browser callers: the dev proxy must strip Origin and Referer ' +
      'before forwarding (see ui/vite.config.ts). This is not a key problem.'
    )
  }
  if (status === 404) {
    return `Hermes has no route at ${COACH_ENDPOINT}. The Vite proxy or the gateway API server is not enabled.`
  }
  if (status >= 500) {
    return `Hermes failed while answering (HTTP ${status}). Check ~/.hermes/logs/gateway.log.`
  }
  return `The coach request failed (HTTP ${status}).`
}

/**
 * Post the question and board context to the Hermes gateway, which answers with
 * the ChessGraph MCP tools. The bearer key is added by the local proxy, never
 * read from a VITE_ variable or sent from the browser.
 */
export async function askCoach(
  question: string,
  context: CoachContext,
  onPhase: (phase: CoachPhase) => void,
): Promise<CoachMessage> {
  onPhase('composing')
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS)

  try {
    const response = await fetch(COACH_ENDPOINT, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        model: COACH_MODEL,
        messages: [{ role: 'user', content: buildPrompt(question, context) }],
        stream: false,
      }),
      signal: controller.signal,
    })

    if (!response.ok) throw new CoachUnavailableError(failureFor(response.status))

    const payload = (await response.json()) as ChatCompletion
    const text = payload.choices?.[0]?.message?.content?.trim()
    if (!text) throw new CoachUnavailableError('Hermes returned an empty answer.')

    return createMessage('coach', text)
  } catch (error) {
    if (error instanceof CoachUnavailableError) throw error
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new CoachUnavailableError(
        `Hermes did not answer within ${Math.round(REQUEST_TIMEOUT_MS / 1000)}s.`,
      )
    }
    throw new CoachUnavailableError(
      `Could not reach Hermes at ${COACH_ENDPOINT}. Start the gateway (hermes gateway status) and retry.`,
    )
  } finally {
    clearTimeout(timer)
    onPhase('idle')
  }
}
