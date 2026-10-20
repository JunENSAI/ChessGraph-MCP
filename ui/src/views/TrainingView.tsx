import { useEffect, useMemo, useRef, useState } from 'react'
import { Chess, type Square } from 'chess.js'
import { ArrowUpDown, Lightbulb, Pause, Play, RotateCcw } from 'lucide-react'
import { ChessBoard, type BoardMove } from '../components/ChessBoard'
import { CoachPanel } from '../components/CoachPanel'
import { EvalBar } from '../components/EvalBar'
import { PlayerBar } from '../components/PlayerBar'
import {
  loadEndgameLessons,
  loadOpeningLessons,
  playSession,
  sessionFromEndgame,
  sessionFromOpening,
  type EndgameLesson,
  type LessonSession,
  type OpeningLesson,
} from '../data/lessons'
import type { Color } from '../data/types'
import { useChessClock } from '../hooks/useChessClock'
import { useCoach } from '../hooks/useCoach'
import { usePositionEval } from '../hooks/usePositionEval'
import { gameStatus, sideToMove, tryMove, tryUci } from '../lib/chess'
import { TIME_CONTROLS } from '../lib/clock'
import { createMessage, loadThread } from '../services/coach'
import { analyzeFen, EngineError } from '../services/engine'

const START_FEN = new Chess().fen()
const MOVE_DELAY_MS = 420

function introFor(session: LessonSession | null) {
  if (!session) return 'Choose an opening, a defense, an endgame, or a color to play.'
  if (session.missingLine) return `${session.title}. ${session.detail}`
  if (session.enginePlay) {
    const side = session.userColor === 'white' ? 'White' : 'Black'
    return `You play ${side}. Stockfish plays the other side and I explain the move after it is on the board. Pause the clock if you want to read.`
  }
  const side = session.userColor === 'white' ? 'White' : 'Black'
  return `${session.title}: you play ${side}. Play the lesson move; the reply follows on the board.`
}

export function TrainingView() {
  const keepThread = useRef(loadThread('training') !== null)
  const [openings, setOpenings] = useState<OpeningLesson[]>([])
  const [defenses, setDefenses] = useState<OpeningLesson[]>([])
  const [endgames, setEndgames] = useState<EndgameLesson[]>([])
  const [catalogError, setCatalogError] = useState<string | null>(null)
  const [openingName, setOpeningName] = useState('')
  const [defenseName, setDefenseName] = useState('')
  const [endgameId, setEndgameId] = useState('')
  const [playColor, setPlayColor] = useState<Color>('white')
  const [activeKind, setActiveKind] = useState<'opening' | 'defense' | 'endgame' | 'play'>('opening')
  const [session, setSession] = useState<LessonSession | null>(null)
  const [fen, setFen] = useState(START_FEN)
  const [step, setStep] = useState(0)
  const [againstEngine, setAgainstEngine] = useState(false)
  const [lastMove, setLastMove] = useState<BoardMove | null>(null)
  const [showHint, setShowHint] = useState(false)
  const [mistakes, setMistakes] = useState(0)
  const [orientation, setOrientation] = useState<'white' | 'black'>('white')
  const [opponentThinking, setOpponentThinking] = useState(false)
  const [controlId, setControlId] = useState('10+0')
  const control = TIME_CONTROLS.find(item => item.id === controlId)!
  const clock = useChessClock(control)
  const coach = useCoach('training', [createMessage('coach', introFor(null))])
  const evaluation = usePositionEval(fen)
  const fenRef = useRef(fen)
  const pending = useRef<number | null>(null)
  const engineToken = useRef(0)
  fenRef.current = fen

  const cancelPending = () => {
    if (pending.current !== null) window.clearTimeout(pending.current)
    pending.current = null
    engineToken.current += 1
    setOpponentThinking(false)
  }

  const explainMove = (san: string, color: Color, evalText: string, position: string, title: string) => {
    void coach.ask(
      `Explain ${san}`,
      {
        mode: 'training',
        fen: position,
        summary: title,
        played: { san, color, evalText },
      },
      { silent: true },
    )
  }

  const engineReply = (fromFen: string, title: string) => {
    const token = ++engineToken.current
    setOpponentThinking(true)
    clock.pause()
    void (async () => {
      try {
        const analysis = await analyzeFen(fromFen)
        if (token !== engineToken.current || fenRef.current !== fromFen) return
        const applied = tryUci(fromFen, analysis.uci)
        if (!applied) {
          coach.say('Stockfish returned a move that is not legal in this position.')
          return
        }
        setFen(applied.fen)
        fenRef.current = applied.fen
        setLastMove({ from: applied.from, to: applied.to })
        clock.press()
        explainMove(applied.san, analysis.side, analysis.evalText, applied.fen, title)
      } catch (error) {
        if (token !== engineToken.current) return
        coach.say(error instanceof EngineError ? error.message : 'Stockfish could not move.')
      } finally {
        if (token === engineToken.current) setOpponentThinking(false)
      }
    })()
  }

  const playScripted = (lesson: LessonSession, fromFen: string, index: number) => {
    setOpponentThinking(true)
    pending.current = window.setTimeout(() => {
      pending.current = null
      const applied = tryMoveSan(fromFen, lesson.line[index].san)
      if (!applied) {
        setOpponentThinking(false)
        coach.say('The stored reply is not legal from this position.')
        return
      }
      setFen(applied.fen)
      fenRef.current = applied.fen
      setLastMove({ from: applied.from, to: applied.to })
      clock.press()
      coach.say(lesson.line[index].explanation)
      const next = index + 1
      setStep(next)
      setOpponentThinking(false)
      if (next === lesson.line.length && lesson.engineAfter) {
        setAgainstEngine(true)
        engineReply(applied.fen, lesson.title)
      } else if (next === lesson.line.length) {
        coach.say('Lesson complete. Choose it again to drill the line.')
      }
    }, MOVE_DELAY_MS)
  }

  const loadSession = (next: LessonSession, resetCoach: boolean) => {
    cancelPending()
    setSession(next)
    setFen(next.startFen)
    fenRef.current = next.startFen
    setStep(0)
    setAgainstEngine(next.enginePlay)
    setLastMove(null)
    setShowHint(false)
    setMistakes(0)
    setOrientation(next.userColor)
    clock.reset(control, sideToMove(next.startFen))
    if (resetCoach) coach.reset([createMessage('coach', introFor(next))])
    const opponentStarts = sideToMove(next.startFen) !== (next.userColor === 'white' ? 'w' : 'b')
    if (opponentStarts && next.enginePlay) engineReply(next.startFen, next.title)
    else if (opponentStarts && !next.missingLine && next.line.length > 0) playScripted(next, next.startFen, 0)
  }

  useEffect(() => {
    let active = true
    Promise.all([loadOpeningLessons('white'), loadOpeningLessons('black'), loadEndgameLessons()])
      .then(([white, black, endgame]) => {
        if (!active) return
        setOpenings(white)
        setDefenses(black)
        setEndgames(endgame.lessons)
        setCatalogError(null)
        if (black[0]) setDefenseName(black[0].openingName)
        if (endgame.lessons[0]) setEndgameId(endgameKey(endgame.lessons[0]))
        if (white[0]) {
          setOpeningName(white[0].openingName)
          loadSession(sessionFromOpening(white[0], 'white'), !keepThread.current)
          keepThread.current = false
        }
      })
      .catch((reason: unknown) => {
        if (active) setCatalogError(reason instanceof Error ? reason.message : 'Lessons could not be loaded.')
      })
    return () => {
      active = false
    }
    // The catalog is loaded once. Later choices call loadSession directly.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const scripted = Boolean(session && !session.enginePlay && !againstEngine && !session.missingLine)
  const expected = scripted ? session?.line[step] : undefined
  const userSide = session ? (session.userColor === 'white' ? 'w' : 'b') : 'w'
  const status = gameStatus(fen)
  const terminal = status === 'Checkmate' || Boolean(status?.startsWith('Draw'))
  const scriptDone = Boolean(session && scripted && step >= session.line.length && !session.engineAfter)
  const complete = terminal || scriptDone
  const interactive =
    Boolean(session) &&
    !session?.missingLine &&
    !clock.flagged &&
    !opponentThinking &&
    !complete &&
    sideToMove(fen) === userSide

  const hintArrow = useMemo(() => {
    if (!showHint || !expected || !interactive) return []
    const applied = tryMoveSan(fen, expected.san)
    if (!applied) return []
    return [{ startSquare: applied.from, endSquare: applied.to, color: '#bb9af7' }]
  }, [showHint, expected, interactive, fen])

  const handleMove = (from: Square, to: Square) => {
    if (!interactive || !session) return false
    const applied = tryMove(fen, from, to)
    if (!applied) return false

    if (againstEngine || session.enginePlay) {
      setFen(applied.fen)
      fenRef.current = applied.fen
      setLastMove({ from, to })
      clock.press()
      if (gameStatus(applied.fen)) return true
      engineReply(applied.fen, session.title)
      return true
    }

    if (!expected || applied.san !== expected.san) {
      setMistakes(count => count + 1)
      coach.say(`${applied.san} is legal, but this lesson continues differently. Use Hint to see the move.`)
      return false
    }

    setFen(applied.fen)
    fenRef.current = applied.fen
    setLastMove({ from, to })
    setShowHint(false)
    clock.press()
    coach.say(expected.explanation)
    const nextStep = step + 1
    setStep(nextStep)
    if (nextStep < session.line.length) playScripted(session, applied.fen, nextStep)
    else if (session.engineAfter) {
      setAgainstEngine(true)
      engineReply(applied.fen, session.title)
    } else coach.say('Lesson complete. Choose it again to drill the line.')
    return true
  }

  const chooseOpening = (name: string) => {
    const lesson = openings.find(item => item.openingName === name)
    if (!lesson) return
    setActiveKind('opening')
    setOpeningName(name)
    loadSession(sessionFromOpening(lesson, 'white'), true)
  }

  const chooseDefense = (name: string) => {
    const lesson = defenses.find(item => item.openingName === name)
    if (!lesson) return
    setActiveKind('defense')
    setDefenseName(name)
    loadSession(sessionFromOpening(lesson, 'black'), true)
  }

  const chooseEndgame = (id: string) => {
    const lesson = endgames.find(item => endgameKey(item) === id)
    if (!lesson) return
    const next = sessionFromEndgame(lesson)
    if (!next) {
      coach.say('That endgame position is not a legal board.')
      return
    }
    setActiveKind('endgame')
    setEndgameId(id)
    loadSession(next, true)
  }

  const choosePlay = (color: Color) => {
    setActiveKind('play')
    setPlayColor(color)
    loadSession(playSession(color), true)
  }

  const animatePlay = async (moves: string[], fromFen: string) => {
    if (fenRef.current !== fromFen) return
    cancelPending()
    setOpponentThinking(true)
    let current = fromFen
    for (const uci of moves) {
      if (fenRef.current !== current) break
      const applied = tryUci(current, uci)
      if (!applied) break
      setFen(applied.fen)
      fenRef.current = applied.fen
      setLastMove({ from: applied.from, to: applied.to })
      current = applied.fen
      await wait(MOVE_DELAY_MS)
    }
    setOpponentThinking(false)
  }

  const changeControl = (id: string) => {
    const next = TIME_CONTROLS.find(item => item.id === id)
    if (!next) return
    setControlId(id)
    clock.reset(next, sideToMove(fenRef.current))
  }

  const topColor = orientation === 'white' ? 'black' : 'white'
  const bottomColor = orientation
  const partner = session?.enginePlay || againstEngine ? 'Stockfish' : 'Book'
  const nameFor = (color: Color) => {
    if (!session) return color === 'white' ? 'White' : 'Black'
    return color === session.userColor ? 'Junior' : partner
  }
  const flaggedSide = clock.flagged === 'w' ? 'White' : clock.flagged === 'b' ? 'Black' : null
  const progress = session?.enginePlay
    ? 'Play'
    : session && !session.missingLine
      ? `Move ${Math.min(step + 1, Math.max(session.line.length, 1))} of ${session.line.length}`
      : 'Lesson'
  const statusText = flaggedSide
    ? `${flaggedSide} lost on time`
    : scriptDone
      ? 'Lesson complete'
        : opponentThinking
        ? againstEngine || session?.enginePlay
          ? 'Stockfish is moving…'
          : 'Book is replying…'
        : status ?? `${sideToMove(fen) === 'w' ? 'White' : 'Black'} to move`

  return (
    <div className="view training-view">
      <section className="panel board-panel" aria-label="Training board">
        <header className="panel-head">
          <div>
            <h2 className="panel-title">{session ? session.title : 'Lessons'}</h2>
            <p className="panel-subtitle">
              {progress} · {statusText}
              {mistakes > 0 ? ` · ${mistakes} retr${mistakes === 1 ? 'y' : 'ies'}` : ''}
            </p>
          </div>
        </header>
        <div className="board-stack">
          <PlayerBar
            name={nameFor(topColor)}
            color={topColor}
            timeMs={clock.remaining[topColor[0] as 'w' | 'b']}
            active={clock.running && clock.active === topColor[0]}
            flagged={clock.flagged === topColor[0]}
          />
          <div className="board-and-eval">
            <EvalBar orientation={orientation} evaluation={evaluation.evaluation} pending={evaluation.pending} />
            <div className="board-frame">
              <ChessBoard
                id="training-board"
                fen={fen}
                orientation={orientation}
                interactive={interactive}
                onMove={handleMove}
                lastMove={lastMove}
                arrows={hintArrow}
              />
            </div>
          </div>
          <PlayerBar
            name={nameFor(bottomColor)}
            color={bottomColor}
            timeMs={clock.remaining[bottomColor[0] as 'w' | 'b']}
            active={clock.running && clock.active === bottomColor[0]}
            flagged={clock.flagged === bottomColor[0]}
          />
        </div>
        <div className="board-controls">
          <button
            type="button"
            className="btn primary"
            disabled={Boolean(clock.flagged) || complete}
            onClick={clock.running ? clock.pause : clock.start}
          >
            {clock.running ? <Pause size={14} /> : <Play size={14} />}
            {clock.running ? 'Pause' : 'Start'}
          </button>
          <label className="select-wrap">
            <span className="sr-only">Time control</span>
            <select value={controlId} onChange={event => changeControl(event.target.value)}>
              {TIME_CONTROLS.map(item => (
                <option key={item.id} value={item.id}>
                  {item.label}
                </option>
              ))}
            </select>
          </label>
          {scripted && (
            <button
              type="button"
              className={`btn${showHint ? ' active' : ''}`}
              disabled={!interactive}
              onClick={() => setShowHint(value => !value)}
            >
              <Lightbulb size={14} /> Hint
            </button>
          )}
          <span className="spacer" />
          <button
            type="button"
            className="btn icon"
            aria-label="Restart"
            onClick={() => session && loadSession(session, true)}
          >
            <RotateCcw size={14} />
          </button>
          <button
            type="button"
            className="btn icon"
            aria-label="Flip board"
            onClick={() => setOrientation(value => (value === 'white' ? 'black' : 'white'))}
          >
            <ArrowUpDown size={14} />
          </button>
        </div>
      </section>

      <CoachPanel
        title="Hermes trainer"
        subtitle="Evaluation, the move, and a short reason"
        messages={coach.messages}
        phase={coach.phase}
        prompts={['Why this move?', 'What is the plan?', 'Common mistakes here']}
        onAsk={question => {
          const fromFen = fenRef.current
          void coach
            .ask(question, {
              mode: 'training',
              fen: fromFen,
              summary: session ? `${session.title}, ${progress.toLowerCase()}` : 'lesson',
            })
            .then(reply => {
              if (reply?.play?.length) void animatePlay(reply.play, fromFen)
            })
        }}
      />

      <section className="panel tracks-panel" aria-label="Lessons">
        <header className="panel-head">
          <div>
            <h2 className="panel-title">Lessons</h2>
            {catalogError && <p className="panel-subtitle">{catalogError}</p>}
          </div>
        </header>
        <div className="scroll-pane">
          <article
            className={`track-card${activeKind === 'opening' ? ' active' : ''}`}
            onClick={event => {
              if ((event.target as HTMLElement).closest('select, option')) return
              if (openingName) chooseOpening(openingName)
            }}
          >
            <span className="eyebrow">Opening</span>
            <label>
              <span className="sr-only">Opening</span>
              <select
                value={openingName}
                onChange={event => chooseOpening(event.target.value)}
                disabled={openings.length === 0}
              >
                {openings.length === 0 && <option value="">No openings stored</option>}
                {openings.map(item => (
                  <option key={item.openingName} value={item.openingName}>
                    {item.openingName} · {item.games}
                  </option>
                ))}
              </select>
            </label>
            <span>Top 5 lines you have played as White</span>
          </article>

          <article
            className={`track-card${activeKind === 'defense' ? ' active' : ''}`}
            onClick={event => {
              if ((event.target as HTMLElement).closest('select, option')) return
              if (defenseName) chooseDefense(defenseName)
            }}
          >
            <span className="eyebrow">Defense</span>
            <label>
              <span className="sr-only">Defense</span>
              <select
                value={defenseName}
                onChange={event => chooseDefense(event.target.value)}
                disabled={defenses.length === 0}
              >
                {defenses.length === 0 && <option value="">No defenses stored</option>}
                {defenses.map(item => (
                  <option key={item.openingName} value={item.openingName}>
                    {item.openingName} · {item.games}
                  </option>
                ))}
              </select>
            </label>
            <span>Top 5 lines you have played as Black</span>
          </article>

          <article
            className={`track-card${activeKind === 'endgame' ? ' active' : ''}`}
            onClick={event => {
              if ((event.target as HTMLElement).closest('select, option')) return
              if (endgameId) chooseEndgame(endgameId)
            }}
          >
            <span className="eyebrow">Endgame Technique</span>
            <label>
              <span className="sr-only">Endgame technique</span>
              <select
                value={endgameId}
                onChange={event => chooseEndgame(event.target.value)}
                disabled={endgames.length === 0}
              >
                {endgames.length === 0 && <option value="">No techniques stored</option>}
                {endgames.map(item => (
                  <option key={endgameKey(item)} value={endgameKey(item)}>
                    {item.endgameType.replaceAll('_', ' ')} · {item.pieceCount} pieces
                  </option>
                ))}
              </select>
            </label>
            <span>Positions near your rating. Stockfish continues after the technique move.</span>
          </article>

          <article
            className={`track-card${activeKind === 'play' ? ' active' : ''}`}
            onClick={event => {
              if ((event.target as HTMLElement).closest('select, option')) return
              choosePlay(playColor)
            }}
          >
            <span className="eyebrow">Play</span>
            <label>
              <span className="sr-only">Color to play</span>
              <select value={playColor} onChange={event => choosePlay(event.target.value as Color)}>
                <option value="white">Play as White</option>
                <option value="black">Play as Black</option>
              </select>
            </label>
            <span>Stockfish moves the other color. If you play Black, White moves first. Pause to read: the clock keeps running.</span>
          </article>
        </div>
      </section>
    </div>
  )
}

function endgameKey(lesson: EndgameLesson): string {
  return `${lesson.endgameType}:${lesson.fenFull}`
}

function tryMoveSan(fen: string, san: string): { from: Square; to: Square; fen: string } | null {
  const chess = new Chess(fen)
  try {
    const move = chess.move(san)
    return { from: move.from, to: move.to, fen: chess.fen() }
  } catch {
    return null
  }
}

function wait(ms: number): Promise<void> {
  return new Promise(resolve => {
    window.setTimeout(resolve, ms)
  })
}
