import { useEffect, useRef, useState, type CSSProperties, type FormEvent } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { SendHorizontal } from 'lucide-react'
import { ThinkingOrb } from 'thinking-orbs'
import {
  PHASE_LABEL,
  PHASE_ORB,
  TRACE_SOURCES,
  type CandidateLine,
  type CoachMessage,
  type CoachMode,
  type CoachPhase,
  type CoachTrace,
} from '../services/coach'
import { humanReason, lineColor, lineLabel } from '../lib/lines'

interface CoachPanelProps {
  title: string
  subtitle: string
  messages: CoachMessage[]
  phase: CoachPhase
  trace?: CoachTrace
  mode?: CoachMode | null
  prompts: string[]
  onAsk: (question: string) => void
  className?: string
  /** Inside a side-panel tab: no card chrome of its own. */
  embedded?: boolean
  /** A candidate line chip was clicked: show that line on the board. */
  onLine?: (message: CoachMessage, line: CandidateLine) => void
  /** The line the board shows now, to mark its chip. */
  activeLine?: { messageId: string; rank: number } | null
}

const SOURCE_LABELS = { postgres: 'Games', neo4j: 'Graph', stockfish: 'Stockfish' }
const MODE_LABEL: Record<CoachMode, string> = { claude: 'Claude', offline: 'Offline evidence' }

function authorFor(message: CoachMessage): string {
  if (message.mode === 'claude') return 'Claude'
  if (message.mode === 'offline') return 'Coach · offline'
  return 'Coach'
}

export function CoachPanel({
  title,
  subtitle,
  messages,
  phase,
  trace = {},
  mode = null,
  prompts,
  onAsk,
  className = '',
  embedded = false,
  onLine,
  activeLine = null,
}: CoachPanelProps) {
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
    <section className={`${embedded ? 'coach-embedded' : 'panel'} coach-panel ${className}`} aria-label={title}>
      {!embedded && (
        <header className="panel-head">
          <div>
            <h2 className="panel-title">{title}</h2>
            <p className="panel-subtitle">{subtitle}</p>
          </div>
        </header>
      )}

      <div className="agent-state">
        <div className="agent-orb">
          <ThinkingOrb state={PHASE_ORB[phase]} size={20} theme="dark" color="#b8f05a" />
          <span>
            <strong>{mode ? MODE_LABEL[mode] : 'Coach'}</strong> · {PHASE_LABEL[phase]}
          </span>
        </div>
        <ol className="trace" aria-label="Evidence sources used for the last answer">
          {TRACE_SOURCES.map(step => {
            const state = trace[step]
            const current = step === phase ? ' current' : ''
            return (
              <li key={step} className={`trace-step${current}${state ? ` ${state}` : ''}`} title={state ?? 'not used'}>
                {SOURCE_LABELS[step]}
              </li>
            )
          })}
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
              {message.role === 'coach' && <div className="message-author">{authorFor(message)}</div>}
              <p>{message.pending && !message.text ? '…' : message.text}</p>
              {message.lines && message.lines.lines.length > 0 && (
                <div className="line-chips" role="group" aria-label="Candidate lines: show one on the board">
                  {message.lines.lines.map(line => {
                    const active = activeLine?.messageId === message.id && activeLine.rank === line.rank
                    return (
                      <button
                        key={line.rank}
                        type="button"
                        className={`line-chip${active ? ' active' : ''}`}
                        style={{ '--line-color': lineColor(line.rank) } as CSSProperties}
                        aria-pressed={active}
                        title={humanReason(line) ?? `Stockfish line ${line.rank}`}
                        onClick={() => onLine?.(message, line)}
                      >
                        <span className="line-rank">{line.rank}</span>
                        <span className="line-moves">{lineLabel(line, message.lines!.root_player)}</span>
                        {line.human && <span className="line-tag">human</span>}
                      </button>
                    )
                  })}
                </div>
              )}
              {message.cached && <div className="demo-note">Cached reply</div>}
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
            Ask the coach
          </label>
          <input
            id={`${title}-input`}
            value={draft}
            onChange={event => setDraft(event.target.value)}
            placeholder="Ask the coach about this position…"
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
