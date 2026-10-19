import { afterEach, describe, expect, it, vi } from 'vitest'
import { askCoach, CoachUnavailableError, type CoachContext, type CoachPhase } from './coach'

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
    expect(body.messages[0].content).toContain('chess_stockfish_validate_line')
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
