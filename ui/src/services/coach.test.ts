import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  askCoach,
  buildPrompt,
  isCourseQuestion,
  cachedAnswer,
  CoachUnavailableError,
  coachProse,
  createMessage,
  loadThread,
  parsePlayMoves,
  rememberAnswer,
  saveThread,
  type CoachContext,
  type CoachPhase,
  type KeyValueStore,
} from './coach'

const context: CoachContext = {
  mode: 'review',
  fen: 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq -',
  summary: 'Italian Game, 5.d3',
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

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
})

describe('parsePlayMoves', () => {
  it('keeps at most six legal UCI moves', () => {
    const text = 'EVAL: +1.2\nMOVE: e4\nPLAY: e2e4 e7e5 g1f3 b8c6 f1c4 f8c5 d2d3 zz9'
    expect(parsePlayMoves(text)).toEqual(['e2e4', 'e7e5', 'g1f3', 'b8c6', 'f1c4', 'f8c5'])
    expect(coachProse(text)).not.toContain('PLAY:')
    expect(coachProse(text)).toContain('MOVE: e4')
  })
})

describe('askCoach', () => {
  it('sends the question and board context as an OpenAI chat request', async () => {
    const fetchMock = vi.fn(async () => jsonResponse({ choices: [{ message: { content: 'Answer.' } }] }))
    vi.stubGlobal('fetch', fetchMock)

    const message = await askCoach('Why was this a mistake?', context, () => {})
    expect(message.role).toBe('coach')
    expect(message.text).toBe('Answer.')

    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toBe('/hermes-api/chat/completions')
    expect(init.method).toBe('POST')

    // The browser must never send the bearer key: the Vite proxy adds it.
    const headers = init.headers as Record<string, string>
    expect(Object.keys(headers).map(key => key.toLowerCase())).toEqual(['content-type'])

    const body = JSON.parse(String(init.body))
    expect(body.stream).toBe(false)
    expect(body.messages).toHaveLength(1)
    expect(body.messages[0].content).toContain(context.fen)
    expect(body.messages[0].content).toContain('Why was this a mistake?')
    expect(body.messages[0].content).toContain('multipv=1')
    expect(body.messages[0].content).toContain('limit.value')
    expect(body.messages[0].content).toContain('PLAY:')
    expect(body.messages[0].content).not.toContain('validate_line')
    expect(body.messages[0].content).not.toContain('get_coaching_brief')
    expect(isCourseQuestion('Why this move?')).toBe(false)
  })

  it('sends a course question to the coaching brief before the engine', async () => {
    const fetchMock = vi.fn(async () => jsonResponse({ choices: [{ message: { content: 'STRENGTH: Italian Game' } }] }))
    vi.stubGlobal('fetch', fetchMock)

    await askCoach('What should I work on in the London?', context, () => {})

    const body = JSON.parse(String((fetchMock.mock.calls[0] as unknown as [string, RequestInit])[1].body))
    const prompt = body.messages[0].content as string
    expect(prompt).toContain('get_coaching_brief')
    expect(prompt).toContain('four training tasks')
    expect(prompt).toContain('reason field')
    expect(prompt).toContain('analyze_position')
    expect(prompt).toContain('STRENGTH:')
    expect(prompt).toContain('TARGET:')
    expect(prompt).toContain('endgame type is not stored on games')
    expect(prompt.indexOf('get_coaching_brief')).toBeLessThan(prompt.indexOf('analyze_position'))
  })

  it('asks for two sentences and no tools when the move is already played', async () => {
    const fetchMock = vi.fn(async () => jsonResponse({ choices: [{ message: { content: 'The rook cuts the king off.' } }] }))
    vi.stubGlobal('fetch', fetchMock)
    const store = memoryStore()

    await askCoach(
      'Explain Rc4',
      { ...context, played: { san: 'Rc4', color: 'white', evalText: 'mate in 25 for white' } },
      () => {},
      store,
    )

    const body = JSON.parse(String((fetchMock.mock.calls[0] as unknown as [string, RequestInit])[1].body))
    expect(body.messages[0].content).toContain('already played Rc4')
    expect(body.messages[0].content).toContain('Do not call tools')
    expect(body.messages[0].content).not.toContain('analyze_position')
  })

  it('returns a cached answer without calling Hermes', async () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    const store = memoryStore()
    rememberAnswer(context.mode, context.fen, 'plan?', 'EVAL: +0.4\nMOVE: Nf3\nPLAY: g1f3', store)

    const seen: CoachPhase[] = []
    const message = await askCoach('plan?', context, phase => seen.push(phase), store)
    expect(fetchMock).not.toHaveBeenCalled()
    expect(seen).toEqual([])
    expect(message.cached).toBe(true)
    expect(message.text).not.toContain('PLAY:')
    expect(message.play).toEqual(['g1f3'])
    expect(cachedAnswer(context.mode, context.fen, 'plan?', store)).toContain('Nf3')
  })

  it('cycles the phase from composing back to idle', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({ choices: [{ message: { content: 'ok' } }] })))

    const seen: CoachPhase[] = []
    await askCoach('plan?', context, phase => seen.push(phase))
    expect(seen).toEqual(['composing', 'idle'])
  })

  it('does not blame the key when the gateway refuses a browser Origin', async () => {
    // The gateway answers 403 to any request carrying an Origin header; the
    // proxy must strip it. A 403 is not an auth failure.
    vi.stubGlobal('fetch', vi.fn(async () => new Response('', { status: 403 })))

    await expect(askCoach('plan?', context, () => {})).rejects.toThrow(/Origin header/)
    await expect(askCoach('plan?', context, () => {})).rejects.not.toThrow(/HERMES_API_KEY/)
  })

  it('reports a rejected key instead of inventing an answer', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('unauthorized', { status: 401 })))

    await expect(askCoach('plan?', context, () => {})).rejects.toThrow(CoachUnavailableError)
    await expect(askCoach('plan?', context, () => {})).rejects.toThrow(/HERMES_API_KEY/)
  })

  it('reports an unreachable gateway', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        throw new TypeError('Failed to fetch')
      }),
    )

    await expect(askCoach('plan?', context, () => {})).rejects.toThrow(/Could not reach Hermes/)
  })

  it('reports an empty answer', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({ choices: [] })))

    await expect(askCoach('plan?', context, () => {})).rejects.toThrow(/empty answer/)
  })
})

describe('buildPrompt', () => {
  it('carries the player profile into the question', () => {
    const prompt = buildPrompt('What is the plan?', { ...context, profile: 'Start with Caro-Kann: Play 20 games.' })
    expect(prompt).toContain('Your profile: Start with Caro-Kann: Play 20 games.')
  })

  it('omits the profile line when there is none', () => {
    expect(buildPrompt('What is the plan?', context)).not.toContain('Your profile:')
  })
})
