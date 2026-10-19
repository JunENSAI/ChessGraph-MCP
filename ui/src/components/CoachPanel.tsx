import { useEffect, useRef, useState, type FormEvent } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { SendHorizontal } from 'lucide-react'
import { ThinkingOrb } from 'thinking-orbs'
import {
  PHASE_LABEL,
  PHASE_ORB,
  PHASE_TRACE,
  type CoachMessage,
  type CoachPhase,
} from '../services/coach'

interface CoachPanelProps {
  title: string
  subtitle: string
  messages: CoachMessage[]
  phase: CoachPhase
  prompts: string[]
  onAsk: (question: string) => void
  className?: string
}

const SOURCE_LABELS = { postgres: 'Postgres', neo4j: 'Neo4j', stockfish: 'Stockfish', composing: 'Hermes' }

export function CoachPanel({ title, subtitle, messages, phase, prompts, onAsk, className = '' }: CoachPanelProps) {
  const [draft, setDraft] = useState('')
  const listRef = useRef<HTMLDivElement>(null)
  const busy = phase !== 'idle'

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages.length, phase])

  const submit = (event: FormEvent) => {
    event.preventDefault()
    const question = draft.trim()
    if (!question || busy) return
    setDraft('')
    onAsk(question)
  }

  return (
    <section className={`panel coach-panel ${className}`} aria-label={title}>
      <header className="panel-head">
        <div>
          <h2 className="panel-title">{title}</h2>
          <p className="panel-subtitle">{subtitle}</p>
        </div>
      </header>

      <div className="agent-state">
        <div className="agent-orb">
          <ThinkingOrb state={PHASE_ORB[phase]} size={20} theme="dark" color="#b8f05a" />
          <span>
            <strong>Hermes</strong> · {PHASE_LABEL[phase]}
          </span>
        </div>
        <ol className="trace" aria-label="Evidence sources">
          {PHASE_TRACE.map(step => (
            <li key={step} className={`trace-step${step === phase ? ' current' : ''}`}>
              {SOURCE_LABELS[step]}
            </li>
          ))}
        </ol>
      </div>

      <div className="messages" ref={listRef} aria-live="polite">
        <AnimatePresence initial={false} mode="popLayout">
          {messages.map(message => (
            <motion.article
              key={message.id}
              className={`message ${message.role}`}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, transition: { duration: 0.08 } }}
              transition={{ duration: 0.2 }}
            >
              {message.role === 'coach' && <div className="message-author">Hermes</div>}
              <p>{message.text}</p>
              {message.demo && <div className="demo-note">Demo reply · connect Hermes-Agent for MCP evidence</div>}
            </motion.article>
          ))}
        </AnimatePresence>
      </div>

      <div className="composer-area">
        <div className="prompt-row">
          {prompts.map(prompt => (
            <button key={prompt} type="button" className="chip" disabled={busy} onClick={() => onAsk(prompt)}>
              {prompt}
            </button>
          ))}
        </div>
        <form className="composer" onSubmit={submit}>
          <label className="sr-only" htmlFor={`${title}-input`}>
            Ask Hermes
          </label>
          <input
            id={`${title}-input`}
            value={draft}
            onChange={event => setDraft(event.target.value)}
            placeholder="Ask Hermes about this position…"
            autoComplete="off"
          />
          <button type="submit" className="send" disabled={busy || !draft.trim()} aria-label="Send">
            <SendHorizontal size={16} />
          </button>
        </form>
      </div>
    </section>
  )
}
