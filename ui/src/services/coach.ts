import type { OrbState } from 'thinking-orbs'

/**
 * Coach transport. The browser posts the question and board context to the
 * retrieval API (`POST /api/coach/chat`), which runs Claude over the
 * ChessGraph repositories through the local Claude Code login — or the offline
 * evidence mode when COACH_MODE=offline — and streams server-sent events back.
 * No credential ever reaches the browser.
 */

export type EvidenceSource = 'postgres' | 'neo4j' | 'stockfish'
export type CoachPhase = 'idle' | EvidenceSource | 'composing'
export type CoachView = 'training' | 'review'
export type CoachMode = 'claude' | 'offline'
export type StepState = 'running' | 'done' | 'failed'
export type CoachTrace = Partial<Record<EvidenceSource, StepState>>

/** One Stockfish candidate from the current position, tagged with how people play its first move. */
export interface CandidateLine {
  rank: number
  uci: string[]
  san: string[]
  /** From the side to move at the root. */
  score: { type: 'cp' | 'mate'; value: number }
  /** Stored games (yours and your opponents') where the first move was played here. */
  games: number
  book: boolean
  /** The line people actually play here: most games, else the best-ranked book line. */
  human: boolean
}

export interface CandidateLines {
  /** The position the lines start from. */
  fen: string
  root_player: 'white' | 'black'
  depth: number | null
  lines: CandidateLine[]
}

export interface CoachMessage {
  id: string
  role: 'user' | 'coach'
  text: string
  mode?: CoachMode
  cached?: boolean
  pending?: boolean
  /** UCI moves the board should play. Not shown as prose. */
  play?: string[]
  /** Stockfish's candidate lines for a position question, drawn on the board. */
  lines?: CandidateLines
}

export interface PlayedMove {
  san: string
  color: 'white' | 'black'
  evalText: string
}

export interface HistoryTurn {
  role: 'user' | 'coach'
  text: string
}

export interface CoachContext {
  mode: CoachView
  fen: string
  summary: string
  /** Set when the board already played a move and the coach should only explain it. */
  played?: PlayedMove
  /** One-line profile from /api/coach/plan, so answers are framed by the player's own results. */
  profile?: string
  /** Stored game under review, so the coach can read its mistakes. */
  gameId?: number
  history?: HistoryTurn[]
}

export type CoachEvent =
  | { type: 'start'; mode: CoachMode; model: string | null }
  | { type: 'tool_start'; tool: string; source: EvidenceSource }
  | { type: 'tool_end'; tool: string; source: EvidenceSource; ok: boolean }
  | { type: 'text'; text: string }
  | ({ type: 'lines' } & Omit<CandidateLines, 'fen'>)
  | { type: 'done'; mode: CoachMode; stop_reason: string }
  | { type: 'error'; message: string }

export interface CoachHandlers {
  onPhase?: (phase: CoachPhase) => void
  onText?: (textSoFar: string) => void
  onTrace?: (trace: CoachTrace) => void
  onMode?: (mode: CoachMode) => void
  onLines?: (lines: CandidateLines) => void
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
  composing: 'Writing the answer',
}

export const TRACE_SOURCES: EvidenceSource[] = ['postgres', 'neo4j', 'stockfish']

const LOG_KEY = 'chessgraph-coach-log'
const LOG_LIMIT = 50
const HISTORY_TURNS = 6
const UCI_MOVE = /^[a-h][1-8][a-h][1-8][qrbn]?$/

export const COACH_ENDPOINT = '/api/coach/chat'
const REQUEST_TIMEOUT_MS = 180_000

let messageCounter = 0
export function createMessage(
  role: CoachMessage['role'],
  text: string,
  extra: Omit<Partial<CoachMessage>, 'id' | 'role' | 'text'> = {},
): CoachMessage {
  messageCounter += 1
  return { id: `m-${Date.now()}-${messageCounter}`, role, text, ...extra }
}

/** Raised when the coach call cannot produce an evidence-backed answer. */
export class CoachUnavailableError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'CoachUnavailableError'
  }
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
  mode?: CoachMode
  lines?: CandidateLines
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
  const stripped = text.replace(/^PLAY:\s*.*$/gim, '').trim()
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
  return thread.filter(message => !message.pending)
}

export function saveThread(
  view: CoachView,
  messages: CoachMessage[],
  store: KeyValueStore | null = browserStore(),
): void {
  const log = readLog(store)
  log.threads[view] = messages.filter(message => !message.pending).slice(-LOG_LIMIT)
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
): CacheEntry | null {
  const key = cacheKey(view, fen, question)
  return readLog(store).cache.find(entry => cacheKey(entry.view, entry.fen, entry.question) === key) ?? null
}

export function rememberAnswer(
  view: CoachView,
  fen: string,
  question: string,
  answer: string,
  mode: CoachMode,
  store: KeyValueStore | null = browserStore(),
  lines?: CandidateLines,
): void {
  const log = readLog(store)
  const key = cacheKey(view, fen, question)
  const next = log.cache.filter(entry => cacheKey(entry.view, entry.fen, entry.question) !== key)
  next.push({ view, fen: positionKey(fen), question: question.trim(), answer, mode, ...(lines ? { lines } : {}) })
  log.cache = next.slice(-LOG_LIMIT)
  writeLog(store, log)
}

/** Recent text turns, sent so follow-up questions keep their context. */
export function historyFrom(messages: CoachMessage[], limit = HISTORY_TURNS): HistoryTurn[] {
  return messages
    .filter(message => !message.pending && message.text.trim())
    .slice(-limit)
    .map(message => ({ role: message.role, text: message.text.slice(0, 4000) }))
}

/**
 * Split a server-sent-event buffer into complete events and the unfinished
 * rest. Only `data:` lines are used; each event is one JSON object.
 */
export function parseSse(buffer: string): { events: CoachEvent[]; rest: string } {
  const normalized = buffer.replace(/\r\n/g, '\n')
  const blocks = normalized.split('\n\n')
  const rest = blocks.pop() ?? ''
  const events: CoachEvent[] = []
  for (const block of blocks) {
    const data = block
      .split('\n')
      .filter(line => line.startsWith('data:'))
      .map(line => line.slice(5).trimStart())
      .join('\n')
    if (!data) continue
    try {
      events.push(JSON.parse(data) as CoachEvent)
    } catch {
      // A malformed event is skipped; the stream carries on.
    }
  }
  return { events, rest }
}

function requestBody(question: string, context: CoachContext) {
  return {
    question,
    fen: context.fen,
    view: context.mode,
    summary: context.summary.slice(0, 600),
    profile: (context.profile ?? '').slice(0, 600),
    game_id: context.gameId ?? null,
    played: context.played
      ? { san: context.played.san, color: context.played.color, eval_text: context.played.evalText }
      : null,
    history: context.history ?? [],
  }
}

async function failureFor(response: Response): Promise<string> {
  let detail = ''
  try {
    const body = (await response.json()) as { error?: string; detail?: unknown }
    detail = typeof body.error === 'string' ? body.error : ''
  } catch {
    // Not JSON: fall back to the status text below.
  }
  if (response.status === 404) return 'The API has no coach route. Restart it from this checkout.'
  if (response.status === 422) return 'The coach could not read this question (invalid request).'
  if (response.status === 503) return detail || 'A ChessGraph store is down. Run uv run chessgraph-status.'
  return detail || `The coach request failed (HTTP ${response.status}).`
}

function present(raw: string, mode: CoachMode, cached = false, lines?: CandidateLines): CoachMessage {
  return createMessage('coach', coachProse(raw), { mode, cached, play: parsePlayMoves(raw), ...(lines ? { lines } : {}) })
}

/**
 * Ask the coach. Streams progress through the handlers and resolves with the
 * final message. A repeated question on the same position returns the stored
 * answer without a request.
 */
export async function askCoach(
  question: string,
  context: CoachContext,
  handlers: CoachHandlers = {},
  store: KeyValueStore | null = browserStore(),
): Promise<CoachMessage> {
  const hit = cachedAnswer(context.mode, context.fen, question, store)
  if (hit) {
    // A cached answer draws its lines too, from the board as it is now.
    const lines = hit.lines ? { ...hit.lines, fen: context.fen } : undefined
    if (lines) handlers.onLines?.(lines)
    return present(hit.answer, hit.mode ?? 'offline', true, lines)
  }

  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS)
  const trace: CoachTrace = {}
  let mode: CoachMode = 'offline'
  let text = ''
  let lines: CandidateLines | undefined
  handlers.onPhase?.('composing')

  try {
    let response: Response
    try {
      response = await fetch(COACH_ENDPOINT, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
        body: JSON.stringify(requestBody(question, context)),
        signal: controller.signal,
      })
    } catch (error) {
      if (error instanceof DOMException && error.name === 'AbortError') throw error
      throw new CoachUnavailableError(
        'Could not reach the ChessGraph API. Start it with: uv run uvicorn backend.main:app --port 8000',
      )
    }
    if (!response.ok) throw new CoachUnavailableError(await failureFor(response))
    if (!response.body) throw new CoachUnavailableError('The coach returned an empty response.')

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    let finished = false
    while (!finished) {
      const { value, done } = await reader.read()
      buffer += decoder.decode(value ?? new Uint8Array(), { stream: !done })
      const parsed = parseSse(done ? `${buffer}\n\n` : buffer)
      buffer = parsed.rest
      for (const event of parsed.events) {
        switch (event.type) {
          case 'start':
            mode = event.mode
            handlers.onMode?.(mode)
            break
          case 'tool_start':
            trace[event.source] = 'running'
            handlers.onTrace?.({ ...trace })
            handlers.onPhase?.(event.source)
            break
          case 'tool_end':
            trace[event.source] = event.ok ? 'done' : 'failed'
            handlers.onTrace?.({ ...trace })
            handlers.onPhase?.('composing')
            break
          case 'lines': {
            const { type: _type, ...rest } = event
            lines = { ...rest, fen: context.fen }
            handlers.onLines?.(lines)
            break
          }
          case 'text':
            text += event.text
            handlers.onText?.(coachProse(text))
            break
          case 'error':
            throw new CoachUnavailableError(event.message)
          case 'done':
            finished = true
            break
        }
      }
      if (done) break
    }
    const answer = text.trim()
    if (!answer) throw new CoachUnavailableError('The coach returned an empty answer.')
    rememberAnswer(context.mode, context.fen, question, answer, mode, store, lines)
    return present(answer, mode, false, lines)
  } catch (error) {
    if (error instanceof CoachUnavailableError) throw error
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new CoachUnavailableError(`The coach did not answer within ${Math.round(REQUEST_TIMEOUT_MS / 1000)}s.`)
    }
    throw new CoachUnavailableError('The coach stream was interrupted. Ask again.')
  } finally {
    clearTimeout(timer)
    handlers.onPhase?.('idle')
  }
}
