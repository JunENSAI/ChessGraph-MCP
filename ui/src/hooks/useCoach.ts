import { useCallback, useEffect, useRef, useState } from 'react'
import {
  askCoach,
  CoachUnavailableError,
  createMessage,
  loadThread,
  saveThread,
  type CoachContext,
  type CoachMessage,
  type CoachPhase,
  type CoachView,
} from '../services/coach'

export function useCoach(view: CoachView, initial: CoachMessage[] = []) {
  const [messages, setMessages] = useState<CoachMessage[]>(() => loadThread(view) ?? initial)
  const [phase, setPhase] = useState<CoachPhase>('idle')
  const generation = useRef(0)

  useEffect(() => {
    saveThread(view, messages)
  }, [view, messages])

  const say = useCallback((text: string) => {
    setMessages(current => [...current, createMessage('coach', text)])
  }, [])

  const reset = useCallback((next: CoachMessage[] = []) => {
    generation.current += 1
    setPhase('idle')
    setMessages(next)
  }, [])

  const ask = useCallback(async (question: string, context: CoachContext, options?: { silent?: boolean }) => {
    const run = ++generation.current
    if (!options?.silent) setMessages(current => [...current, createMessage('user', question)])
    try {
      const reply = await askCoach(question, context, next => {
        if (run === generation.current) setPhase(next)
      })
      if (run === generation.current) setMessages(current => [...current, reply])
      return reply
    } catch (error) {
      if (run !== generation.current) return undefined
      const text =
        error instanceof CoachUnavailableError
          ? error.message
          : 'The coach request failed for an unexpected reason.'
      const reply = createMessage('coach', text)
      setMessages(current => [...current, reply])
      return reply
    }
  }, [])

  return { messages, phase, say, ask, reset }
}
