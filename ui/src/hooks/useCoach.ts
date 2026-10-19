import { useCallback, useRef, useState } from 'react'
import { askCoach, createMessage, type CoachContext, type CoachMessage, type CoachPhase } from '../services/coach'

export function useCoach(initial: CoachMessage[] = []) {
  const [messages, setMessages] = useState<CoachMessage[]>(initial)
  const [phase, setPhase] = useState<CoachPhase>('idle')
  const generation = useRef(0)

  const say = useCallback((text: string) => {
    setMessages(current => [...current, createMessage('coach', text)])
  }, [])

  const reset = useCallback((next: CoachMessage[] = []) => {
    generation.current += 1
    setPhase('idle')
    setMessages(next)
  }, [])

  const ask = useCallback(async (question: string, context: CoachContext) => {
    const run = ++generation.current
    setMessages(current => [...current, createMessage('user', question)])
    const reply = await askCoach(question, context, next => {
      if (run === generation.current) setPhase(next)
    })
    if (run === generation.current) setMessages(current => [...current, reply])
  }, [])

  return { messages, phase, say, ask, reset }
}
