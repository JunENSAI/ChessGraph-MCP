import type { OrbState } from 'thinking-orbs'

export type CoachPhase = 'idle' | 'postgres' | 'neo4j' | 'stockfish' | 'composing'
export type CoachView = 'training' | 'review'

export interface CoachMessage {
  id: string
  role: 'user' | 'coach'
  text: string
  demo?: boolean
  cached?: boolean
  /** UCI moves the training board should play. Not shown as prose. */
  play?: string[]
}

export interface PlayedMove {
  san: string
  color: 'white' | 'black'
  evalText: string
}

export interface CoachContext {
  mode: CoachView
  fen: string
  summary: string
  /** Set when the board already played a Stockfish move and Hermes should only explain it. */
  played?: PlayedMove
  /** One-line profile from /api/coach/plan, so answers are framed by the player's own results. */
  profile?: string
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

const LOG_KEY = 'chessgraph-coach-log'
const LOG_LIMIT = 50
const UCI_MOVE = /^[a-h][1-8][a-h][1-8][qrbn]?$/

let messageCounter = 0
export function createMessage(
  role: CoachMessage['role'],
  text: string,
  demo = false,
  extra: { cached?: boolean; play?: string[] } = {},
): CoachMessage {
  messageCounter += 1
  return { id: `m-${Date.now()}-${messageCounter}`, role, text, demo, ...extra }
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

export interface KeyValueStore {
  getItem(key: string): string | null
  setItem(key: string, value: string): void
}

interface CacheEntry {
  view: CoachView
  fen: string
  question: string
  answer: string
}

interface CoachLog {
  threads: Partial<Record<CoachView, CoachMessage[]>>
  cache: CacheEntry[]
}

function emptyLog(): CoachLog {
  return { threads: {}, cache: [] }
}

export function positionKey(fen: string): string {
  return fen.trim().split(/\s+/).slice(0, 4).join(' ')
}

export function parsePlayMoves(text: string): string[] {
  const match = text.match(/^PLAY:\s*(.+)$/im)
  if (!match) return []
  return match[1]
    .trim()
    .split(/\s+/)
    .map(token => token.toLowerCase())
    .filter(token => UCI_MOVE.test(token))
    .slice(0, 6)
}

export function coachProse(text: string): string {
  const stripped = text.replace(/^PLAY:\s*.+$/gim, '').trim()
  return stripped || text.trim()
}

export function browserStore(): KeyValueStore | null {
  try {
    return typeof localStorage === 'undefined' ? null : localStorage
  } catch {
    return null
  }
}

function readLog(store: KeyValueStore | null): CoachLog {
  if (!store) return emptyLog()
  try {
    const raw = store.getItem(LOG_KEY)
    if (!raw) return emptyLog()
    const parsed = JSON.parse(raw) as Partial<CoachLog>
    return {
      threads: parsed.threads ?? {},
      cache: Array.isArray(parsed.cache) ? parsed.cache : [],
    }
  } catch {
    return emptyLog()
  }
}

function writeLog(store: KeyValueStore | null, log: CoachLog): void {
  if (!store) return
  try {
    store.setItem(LOG_KEY, JSON.stringify(log))
  } catch {
    // A full or blocked store should not stop the coach from answering.
  }
}

export function loadThread(view: CoachView, store: KeyValueStore | null = browserStore()): CoachMessage[] | null {
  const thread = readLog(store).threads[view]
  // A lesson intro saved before the catalog loads is not a conversation to restore.
  if (!thread?.some(message => message.role === 'user')) return null
  return thread
}

export function saveThread(
  view: CoachView,
  messages: CoachMessage[],
  store: KeyValueStore | null = browserStore(),
): void {
  const log = readLog(store)
  log.threads[view] = messages.slice(-LOG_LIMIT)
  writeLog(store, log)
}

function cacheKey(view: CoachView, fen: string, question: string): string {
  return `${view}\n${positionKey(fen)}\n${question.trim()}`
}

export function cachedAnswer(
  view: CoachView,
  fen: string,
  question: string,
  store: KeyValueStore | null = browserStore(),
): string | null {
  const key = cacheKey(view, fen, question)
  const hit = readLog(store).cache.find(entry => cacheKey(entry.view, entry.fen, entry.question) === key)
  return hit?.answer ?? null
}

export function rememberAnswer(
  view: CoachView,
  fen: string,
  question: string,
  answer: string,
  store: KeyValueStore | null = browserStore(),
): void {
  const log = readLog(store)
  const key = cacheKey(view, fen, question)
  const next = log.cache.filter(entry => cacheKey(entry.view, entry.fen, entry.question) !== key)
  next.push({ view, fen: positionKey(fen), question: question.trim(), answer })
  log.cache = next.slice(-LOG_LIMIT)
  writeLog(store, log)
}

const COURSE_QUESTION =
  /\b(train|weakness|strengths?|openings?|defen[cs]e|london|work on|what should i|(?:common|repeated|my) mistakes?)\b/i

export function isCourseQuestion(question: string): boolean {
  return COURSE_QUESTION.test(question)
}

export function buildPrompt(question: string, context: CoachContext): string {
  if (context.played) {
    return [
      `Position (normalized FEN): ${context.fen}`,
      `The interface already played ${context.played.san} for ${context.played.color}.`,
      `Stockfish evaluation, from the side to move before that move: ${context.played.evalText}.`,
      'Explain only this move in two sentences.',
      'Do not call tools. Do not print a FEN, a variation, or any other move.',
    ].join('\n')
  }
  const subject = context.mode === 'training' ? 'training position' : 'position from my game'
  if (isCourseQuestion(question)) {
    return [
      `Position (normalized FEN): ${context.fen}`,
      `Context: ${subject} — ${context.summary}`,
      ...(context.profile ? [`Your profile: ${context.profile}`] : []),
      '',
      question,
      '',
      'Call get_coaching_brief first. Cite only fields it returned.',
      'Name the four training tasks and the reason field of each.',
      'Then call analyze_position on the task the question is about, with multipv=1.',
      'Cite depth only from the tool result field limit.value.',
      'Do not claim an endgame weakness. The brief says endgame type is not stored on games.',
      'If the brief has no target split, say that evidence is missing and do not invent a move.',
      '',
      'Answer in this shape and nothing longer:',
      'STRENGTH: <one family from the brief>',
      'TARGET: <the played move and the stored move>',
      'MOVE: <one SAN move>',
      '<at most two sentences>',
      'PLAY: <that one UCI move>',
    ].join('\n')
  }
  return [
    `Position (normalized FEN): ${context.fen}`,
    `Context: ${subject} — ${context.summary}`,
    ...(context.profile ? [`Your profile: ${context.profile}`] : []),
    '',
    question,
    '',
    'Answer in this shape and nothing longer:',
    'EVAL: <score from the tool>',
    'MOVE: <one SAN move>',
    '<at most two sentences>',
    'PLAY: <up to 6 UCI moves, space separated>',
    '',
    'Call analyze_position with multipv=1. Cite depth only from the tool result field limit.value.',
    'Do not list other engine ranks. Do not print a final FEN.',
    'Do not narrate empty Postgres or Neo4j results unless the question is about my games or the graph.',
    'If a tool returned nothing for a question that needed it, say that evidence is missing in one clause.',
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

function present(raw: string, cached = false): CoachMessage {
  return createMessage('coach', coachProse(raw), false, { cached, play: parsePlayMoves(raw) })
}

/**
 * Post the question and board context to the Hermes gateway, which answers with
 * the ChessGraph MCP tools. The bearer key is added by the local proxy, never
 * read from a VITE_ variable or sent from the browser.
 *
 * A repeated question on the same position returns the stored answer.
 */
export async function askCoach(
  question: string,
  context: CoachContext,
  onPhase: (phase: CoachPhase) => void,
  store: KeyValueStore | null = browserStore(),
): Promise<CoachMessage> {
  const cached = cachedAnswer(context.mode, context.fen, question, store)
  if (cached) return present(cached, true)

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
    rememberAnswer(context.mode, context.fen, question, text, store)
    return present(text)
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
