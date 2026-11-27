import { useCallback, useEffect, useRef, useState } from 'react'
import {
  askCoach,
  CoachUnavailableError,
  createMessage,
  historyFrom,
  loadThread,
  saveThread,
  type CoachContext,
  type CandidateLines,
  type CoachMessage,
  type CoachMode,
  type CoachPhase,
  type CoachTrace,
  type CoachView,
} from '../services/coach'

export function useCoach(view: CoachView, initial: CoachMessage[] = []) {
  const [messages, setMessages] = useState<CoachMessage[]>(() => loadThread(view) ?? initial)
  const [phase, setPhase] = useState<CoachPhase>('idle')
  const [trace, setTrace] = useState<CoachTrace>({})
  const [mode, setMode] = useState<CoachMode | null>(null)
  const generation = useRef(0)
  const latest = useRef(messages)

  useEffect(() => {
    latest.current = messages
    saveThread(view, messages)
  }, [view, messages])

  const say = useCallback((text: string) => {
    setMessages(current => [...current, createMessage('coach', text)])
  }, [])

  const reset = useCallback((next: CoachMessage[] = []) => {
    generation.current += 1
    setPhase('idle')
    setTrace({})
    setMessages(next)
  }, [])

  const ask = useCallback(async (
    question: string,
    context: CoachContext,
    options?: { silent?: boolean; onLines?: (lines: CandidateLines, messageId: string) => void },
  ) => {
    const run = ++generation.current
    const live = () => run === generation.current
    const history = context.history ?? historyFrom(latest.current)
    const pending = createMessage('coach', '', { pending: true })
    setTrace({})
    setMessages(current => [
      ...current,
      ...(options?.silent ? [] : [createMessage('user', question)]),
      pending,
    ])
    const replacePending = (next: CoachMessage | null) =>
      setMessages(current =>
        next
          ? current.map(message => (message.id === pending.id ? next : message))
          : current.filter(message => message.id !== pending.id),
      )

    let streamed: CoachMessage = pending
    try {
      const reply = await askCoach(question, { ...context, history }, {
        onPhase: next => live() && setPhase(next),
        onTrace: next => live() && setTrace(next),
        onMode: next => live() && setMode(next),
        onText: text => {
          streamed = { ...streamed, text }
          if (live()) replacePending(streamed)
        },
        onLines: lines => {
          streamed = { ...streamed, lines }
          if (!live()) return
          replacePending(streamed)
          options?.onLines?.(lines, pending.id)
        },
      })
      if (live()) {
        if (reply.mode) setMode(reply.mode)
        // Keep the pending id, so a line the board already shows stays tied to its chips.
        replacePending({ ...reply, id: pending.id })
      }
      return { ...reply, id: pending.id }
    } catch (error) {
      if (!live()) return undefined
      const text =
        error instanceof CoachUnavailableError ? error.message : 'The coach request failed for an unexpected reason.'
      const reply = createMessage('coach', text)
      replacePending(reply)
      return reply
    }
  }, [])

  return { messages, phase, trace, mode, say, ask, reset }
}
