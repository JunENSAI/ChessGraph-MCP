import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  askCoach,
  cachedAnswer,
  COACH_ENDPOINT,
  CoachUnavailableError,
  coachProse,
  createMessage,
  historyFrom,
  loadThread,
  parsePlayMoves,
  parseSse,
  rememberAnswer,
  saveThread,
  type CoachContext,
  type CoachEvent,
  type CoachPhase,
  type CoachTrace,
  type KeyValueStore,
} from './coach'

const context: CoachContext = {
  mode: 'review',
  fen: 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq -',
  summary: 'Italian Game, 5.d3',
}

/** A streamed response whose body arrives in the given chunks. */
function sseResponse(chunks: string[], status = 200): Response {
  const encoder = new TextEncoder()
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk))
      controller.close()
    },
  })
  return new Response(body, { status, headers: { 'Content-Type': 'text/event-stream' } })
}

function frame(event: CoachEvent): string {
  return `data: ${JSON.stringify(event)}\n\n`
}

const OFFLINE_ANSWER: CoachEvent[] = [
  { type: 'start', mode: 'offline', model: null },
  { type: 'tool_start', tool: 'analyze_position', source: 'stockfish' },
  { type: 'tool_end', tool: 'analyze_position', source: 'stockfish', ok: true },
  { type: 'tool_start', tool: 'get_position_moves', source: 'neo4j' },
  { type: 'tool_end', tool: 'get_position_moves', source: 'neo4j', ok: false },
  { type: 'text', text: 'EVAL: +0.57\nMOVE: e4\n' },
  { type: 'text', text: 'PLAY: e2e4 d7d5' },
  { type: 'done', mode: 'offline', stop_reason: 'end_turn' },
]

afterEach(() => {
  vi.unstubAllGlobals()
})

class MemoryStore implements KeyValueStore {
  value: string | null = null
  getItem(): string | null {
    return this.value
  }
  setItem(_key: string, value: string): void {
    this.value = value
  }
}

function memoryStore(): KeyValueStore {
  return new MemoryStore()
}

describe('loadThread', () => {
  it('ignores a stored intro that has no question', () => {
    const store = memoryStore()
    saveThread('training', [createMessage('coach', 'Choose an opening.')], store)
    expect(loadThread('training', store)).toBeNull()
    saveThread('training', [createMessage('user', 'Why this move?'), createMessage('coach', 'EVAL: +0.2')], store)
    expect(loadThread('training', store)?.map(message => message.role)).toEqual(['user', 'coach'])
  })

  it('never stores a half-streamed answer', () => {
    const store = memoryStore()
    saveThread('review', [createMessage('user', 'Why?'), createMessage('coach', 'EVAL', { pending: true })], store)
    expect(loadThread('review', store)?.map(message => message.role)).toEqual(['user'])
  })
})

describe('parsePlayMoves', () => {
  it('keeps at most six legal UCI moves', () => {
    const text = 'EVAL: +1.2\nMOVE: e4\nPLAY: e2e4 e7e5 g1f3 b8c6 f1c4 f8c5 d2d3 zz9'
    expect(parsePlayMoves(text)).toEqual(['e2e4', 'e7e5', 'g1f3', 'b8c6', 'f1c4', 'f8c5'])
    expect(coachProse(text)).not.toContain('PLAY:')
    expect(coachProse(text)).toContain('MOVE: e4')
  })
})

describe('parseSse', () => {
  it('returns complete events and keeps the unfinished tail', () => {
    const buffer = frame(OFFLINE_ANSWER[0]) + 'data: {"type":"te'
    const { events, rest } = parseSse(buffer)
    expect(events).toEqual([OFFLINE_ANSWER[0]])
    expect(rest).toBe('data: {"type":"te')
  })

  it('accepts CRLF line endings and skips malformed events', () => {
    const buffer = 'data: not json\r\n\r\n' + frame({ type: 'text', text: 'ok' }).replace(/\n/g, '\r\n')
    expect(parseSse(buffer).events).toEqual([{ type: 'text', text: 'ok' }])
  })
})

describe('historyFrom', () => {
  it('keeps the last text turns and drops pending ones', () => {
    const messages = [
      createMessage('user', 'one'),
      createMessage('coach', 'two'),
      createMessage('coach', '', { pending: true }),
    ]
    expect(historyFrom(messages, 1)).toEqual([{ role: 'coach', text: 'two' }])
  })
})

describe('askCoach', () => {
  it('posts the question and board context to the API coach route', async () => {
    const fetchMock = vi.fn(async (_url: string, _init?: RequestInit) => sseResponse(OFFLINE_ANSWER.map(frame)))
    vi.stubGlobal('fetch', fetchMock)

    await askCoach('Why was this a mistake?', {
      ...context,
      gameId: 42,
      profile: 'Weakest: Bird Opening',
      played: { san: 'Rc4', color: 'black', evalText: '+0.3' },
      history: [{ role: 'user', text: 'hi' }],
    })

    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe(COACH_ENDPOINT)
    const body = JSON.parse(String(init?.body))
    expect(body).toMatchObject({
      question: 'Why was this a mistake?',
      fen: context.fen,
      view: 'review',
      game_id: 42,
      profile: 'Weakest: Bird Opening',
      played: { san: 'Rc4', color: 'black', eval_text: '+0.3' },
      history: [{ role: 'user', text: 'hi' }],
    })
    // Nothing that looks like a model key leaves the browser.
    expect(JSON.stringify(init)).not.toMatch(/api[_-]?key|authorization/i)
  })

  it('streams text, reports the evidence trace and returns the final message', async () => {
    // Split one frame across two chunks to exercise buffering.
    const raw = OFFLINE_ANSWER.map(frame).join('')
    vi.stubGlobal('fetch', vi.fn(async () => sseResponse([raw.slice(0, 50), raw.slice(50)])))

    const phases: CoachPhase[] = []
    const traces: CoachTrace[] = []
    const texts: string[] = []
    const message = await askCoach('Best move?', context, {
      onPhase: phase => phases.push(phase),
      onTrace: trace => traces.push(trace),
      onText: text => texts.push(text),
    }, memoryStore())

    expect(message.mode).toBe('offline')
    expect(message.text).toBe('EVAL: +0.57\nMOVE: e4')
    expect(message.play).toEqual(['e2e4', 'd7d5'])
    expect(traces.at(-1)).toEqual({ stockfish: 'done', neo4j: 'failed' })
    expect(phases).toEqual(['composing', 'stockfish', 'composing', 'neo4j', 'composing', 'idle'])
    expect(texts[0]).toBe('EVAL: +0.57\nMOVE: e4')
    expect(texts.every(text => !text.includes('PLAY:'))).toBe(true)
  })

  it('caches the answer with its mode and replays it without a request', async () => {
    const store = memoryStore()
    vi.stubGlobal('fetch', vi.fn(async () => sseResponse(OFFLINE_ANSWER.map(frame))))
    await askCoach('plan?', context, {}, store)
    expect(cachedAnswer(context.mode, context.fen, 'plan?', store)?.mode).toBe('offline')

    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    const phases: CoachPhase[] = []
    const message = await askCoach('plan?', context, { onPhase: phase => phases.push(phase) }, store)
    expect(fetchMock).not.toHaveBeenCalled()
    expect(phases).toEqual([])
    expect(message.cached).toBe(true)
    expect(message.play).toEqual(['e2e4', 'd7d5'])
  })

  it('reads an older cached answer that has no mode', async () => {
    const store = memoryStore()
    rememberAnswer(context.mode, context.fen, 'q', 'MOVE: Nf3\nPLAY: g1f3', 'claude', store)
    const message = await askCoach('q', context, {}, store)
    expect(message.mode).toBe('claude')
  })

  it('turns an error event into a CoachUnavailableError', async () => {
    const events: CoachEvent[] = [
      { type: 'start', mode: 'claude', model: 'claude-opus-5-5' },
      { type: 'error', message: 'Claude Code is not logged in. Run `claude` once and use /login, then ask again.' },
    ]
    vi.stubGlobal('fetch', vi.fn(async () => sseResponse(events.map(frame))))
    await expect(askCoach('q', context, {}, memoryStore())).rejects.toThrow(/not logged in/)
  })

  it('reports a down store from the API error body', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response(JSON.stringify({ error: 'Neo4j is not accepting connections.' }), { status: 503 })),
    )
    await expect(askCoach('q', context, {}, memoryStore())).rejects.toThrow(/Neo4j is not accepting/)
  })

  it('reports an unreachable API with the command to start it', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        throw new TypeError('Failed to fetch')
      }),
    )
    await expect(askCoach('q', context, {}, memoryStore())).rejects.toThrow(CoachUnavailableError)
    await expect(askCoach('q', context, {}, memoryStore())).rejects.toThrow(/uvicorn backend\.main:app/)
  })

  it('reports an empty answer', async () => {
    const events: CoachEvent[] = [{ type: 'start', mode: 'offline', model: null }, { type: 'done', mode: 'offline', stop_reason: 'end_turn' }]
    vi.stubGlobal('fetch', vi.fn(async () => sseResponse(events.map(frame))))
    await expect(askCoach('q', context, {}, memoryStore())).rejects.toThrow(/empty answer/)
  })
})
