import { useEffect, useMemo, useRef, useState } from 'react'
import { Chess, type Square } from 'chess.js'
import { ArrowUpDown, Flag, Lightbulb, Pause, Play, RotateCcw } from 'lucide-react'
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
import { endgameTitle, groupOpenings } from '../data/openings'
import type { Color } from '../data/types'
import { useChessClock } from '../hooks/useChessClock'
import { useCoach } from '../hooks/useCoach'
import { usePositionEval } from '../hooks/usePositionEval'
import { gameStatus, resultText, sideToMove, tryMove, tryUci, type Promotion } from '../lib/chess'
import type { WhiteEval } from '../lib/eval'
import { TIME_CONTROLS } from '../lib/clock'
import { createMessage, loadThread } from '../services/coach'
import { analyzeFen, EngineError } from '../services/engine'

const START_FEN = new Chess().fen()
const MOVE_DELAY_MS = 420
/** Stockfish often answers in a few milliseconds. Spend at least this long so the clock actually changes. */
const ENGINE_REFLECTION_MS = 1000

function engineShouldResign(scoreType: 'cp' | 'mate', scoreValue: number, fen: string): boolean {
  const moveNumber = Number(fen.split(' ')[5] ?? '1')
  if (!Number.isFinite(moveNumber) || moveNumber < 6) return false
  if (scoreType === 'mate' && scoreValue < 0) return true
  return scoreType === 'cp' && scoreValue <= -1500
}

function catalogSubtitle(
  status: 'loading' | 'ready' | 'error',
  error: string | null,
  lessonCount: number,
): string {
  if (status === 'loading') return 'Reading stored lessons…'
  if (error) return error
  if (lessonCount === 0) return 'No lessons are stored for this account.'
  return 'Stored lines from your games.'
}

function introFor(session: LessonSession | null) {
  if (!session) return 'Choose an opening, a defense, an endgame, or a color to play.'
  if (session.missingLine) return `${session.title}. ${session.detail}`
  if (session.enginePlay) {
    const side = session.userColor === 'white' ? 'White' : 'Black'
    return `You play ${side}. Stockfish plays the other side. After each of its moves the clock stays paused until you press Continue, so you can read the explanation.`
  }
  const side = session.userColor === 'white' ? 'White' : 'Black'
  return `${session.title}: you play ${side}. Play the lesson move; the reply follows on the board.`
}

export function TrainingView() {
  const keepThread = useRef(loadThread('training') !== null)
  const [catalogAttempt, setCatalogAttempt] = useState(0)
  const [catalogStatus, setCatalogStatus] = useState<'loading' | 'ready' | 'error'>('loading')
  const [openings, setOpenings] = useState<OpeningLesson[]>([])
  const [defenses, setDefenses] = useState<OpeningLesson[]>([])
  const [endgames, setEndgames] = useState<EndgameLesson[]>([])
  const [catalogError, setCatalogError] = useState<string | null>(null)
  const [openingFamily, setOpeningFamily] = useState('')
  const [openingName, setOpeningName] = useState('')
  const [defenseFamily, setDefenseFamily] = useState('')
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
  const [engineHint, setEngineHint] = useState<{ from: Square; to: Square } | null>(null)
  const [resigned, setResigned] = useState<'w' | 'b' | null>(null)
  const [engineResigned, setEngineResigned] = useState(false)
  const [reading, setReading] = useState(false)
  const [preview, setPreview] = useState<{ fen: string; evaluation: WhiteEval } | null>(null)
  const [mistakes, setMistakes] = useState(0)
  const [orientation, setOrientation] = useState<'white' | 'black'>('white')
  const [opponentThinking, setOpponentThinking] = useState(false)
  const [controlId, setControlId] = useState('10+0')
  const control = TIME_CONTROLS.find(item => item.id === controlId)!
  const clock = useChessClock(control)
  const coach = useCoach('training', [createMessage('coach', introFor(null))])
  const evaluation = usePositionEval(fen, preview?.fen === fen ? preview.evaluation : null)
  const fenRef = useRef(fen)
  const clockRef = useRef(clock)
  clockRef.current = clock
  const sessionRef = useRef(session)
  sessionRef.current = session
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

  const stopForResult = (position: string) => {
    const text = resultText(position)
    if (!text) return false
    clockRef.current.pause()
    coach.say(text)
    return true
  }

  const engineReply = (fromFen: string, title: string) => {
    const token = ++engineToken.current
    const thinkingSide = sideToMove(fromFen)
    setOpponentThinking(true)
    setReading(false)
    setShowHint(false)
    const startedAt = performance.now()
    clockRef.current.start()
    void (async () => {
      try {
        const analysis = await analyzeFen(fromFen)
        const elapsed = performance.now() - startedAt
        if (elapsed < ENGINE_REFLECTION_MS) await wait(ENGINE_REFLECTION_MS - elapsed)
        if (token !== engineToken.current || fenRef.current !== fromFen) return
        if (clockRef.current.flagged === thinkingSide) {
          coach.say(`${thinkingSide === 'w' ? 'White' : 'Black'} lost on time`)
          return
        }
        if (
          sessionRef.current?.enginePlay &&
          engineShouldResign(analysis.scoreType, analysis.scoreValue, fromFen)
        ) {
          clockRef.current.pause()
          setEngineResigned(true)
          const side = thinkingSide === 'w' ? 'White' : 'Black'
          coach.say(`${side} resigns.`)
          return
        }
        const applied = tryUci(fromFen, analysis.uci)
        if (!applied) {
          coach.say('Stockfish returned a move that is not legal in this position.')
          return
        }
        setFen(applied.fen)
        fenRef.current = applied.fen
        setLastMove({ from: applied.from, to: applied.to })
        setPreview({ fen: applied.fen, evaluation: analysis.white })
        if (stopForResult(applied.fen)) return
        clockRef.current.press()
        clockRef.current.pause()
        setReading(true)
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
      if (stopForResult(applied.fen)) {
        setStep(index + 1)
        setOpponentThinking(false)
        return
      }
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
    setEngineHint(null)
    setResigned(null)
    setEngineResigned(false)
    setReading(false)
    setPreview(null)
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
    setCatalogStatus('loading')
    setCatalogError(null)
    Promise.all([loadOpeningLessons('white'), loadOpeningLessons('black'), loadEndgameLessons()])
      .then(([white, black, endgame]) => {
        if (!active) return
        setOpenings(white)
        setDefenses(black)
        setEndgames(endgame.lessons)
        setCatalogError(null)
        setCatalogStatus('ready')
        const whiteFamilies = groupOpenings(white)
        const blackFamilies = groupOpenings(black)
        if (blackFamilies[0]) {
          setDefenseFamily(blackFamilies[0].name)
          setDefenseName(blackFamilies[0].variants[0].lesson.openingName)
        }
        if (endgame.lessons[0]) setEndgameId(endgameKey(endgame.lessons[0]))
        if (whiteFamilies[0]) {
          const first = whiteFamilies[0].variants[0].lesson
          setOpeningFamily(whiteFamilies[0].name)
          setOpeningName(first.openingName)
          if (!sessionRef.current) {
            loadSession(sessionFromOpening(first, 'white'), !keepThread.current)
            keepThread.current = false
          }
        }
      })
      .catch((reason: unknown) => {
        if (!active) return
        setCatalogStatus('error')
        setCatalogError(reason instanceof Error && reason.message ? reason.message : 'Lessons could not be loaded.')
      })
    return () => {
      active = false
    }
    // Later choices call loadSession directly. Retry increments catalogAttempt.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [catalogAttempt])

  const scripted = Boolean(session && !session.enginePlay && !againstEngine && !session.missingLine)
  const expected = scripted ? session?.line[step] : undefined
  const userSide = session ? (session.userColor === 'white' ? 'w' : 'b') : 'w'
  const outcome = resultText(fen)
  const terminal = outcome !== null
  const scriptDone = Boolean(session && scripted && step >= session.line.length && !session.engineAfter)
  const complete = terminal || scriptDone || resigned !== null || engineResigned || Boolean(session?.enginePlay && clock.flagged)
  const interactive =
    Boolean(session) &&
    !session?.missingLine &&
    !clock.flagged &&
    !opponentThinking &&
    !reading &&
    !complete &&
    sideToMove(fen) === userSide

  const hintArrow = useMemo(() => {
    if (!showHint) return []
    if (engineHint) return [{ startSquare: engineHint.from, endSquare: engineHint.to, color: '#bb9af7' }]
    if (!expected || !interactive) return []
    const applied = tryMoveSan(fen, expected.san)
    if (!applied) return []
    return [{ startSquare: applied.from, endSquare: applied.to, color: '#bb9af7' }]
  }, [showHint, engineHint, expected, interactive, fen])

  const requestEngineHint = async () => {
    if (showHint) {
      setShowHint(false)
      return
    }
    try {
      const analysis = await analyzeFen(fen, { limitType: 'time', limitValue: 400 })
      const from = analysis.uci.slice(0, 2) as Square
      const to = analysis.uci.slice(2, 4) as Square
      setEngineHint({ from, to })
      setShowHint(true)
      coach.say(`Hint: ${analysis.san}.`)
    } catch (error) {
      coach.say(error instanceof EngineError ? error.message : 'Stockfish could not offer a hint.')
    }
  }

  const rematch = () => {
    if (!session?.enginePlay) return
    loadSession(playSession(session.userColor), true)
  }

  const resign = () => {
    if (!session?.enginePlay || complete) return
    cancelPending()
    clock.pause()
    setResigned(userSide)
    const winner = userSide === 'w' ? 'Black' : 'White'
    coach.say(`You resigned. ${winner} wins.`)
  }

  const handleMove = (from: Square, to: Square, promotion?: Promotion) => {
    if (!interactive || !session) return false
    const applied = tryMove(fen, from, to, promotion)
    if (!applied) return false

    if (againstEngine || session.enginePlay) {
      setReading(false)
      setFen(applied.fen)
      fenRef.current = applied.fen
      setLastMove({ from, to })
      setShowHint(false)
      setEngineHint(null)
      setPreview(null)
      if (stopForResult(applied.fen)) return true
      clock.press()
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

  const openingFamilies = useMemo(() => groupOpenings(openings), [openings])
  const defenseFamilies = useMemo(() => groupOpenings(defenses), [defenses])
  const openingVariants = openingFamilies.find(item => item.name === openingFamily)?.variants ?? []
  const defenseVariants = defenseFamilies.find(item => item.name === defenseFamily)?.variants ?? []

  const chooseOpening = (name: string) => {
    const lesson = openings.find(item => item.openingName === name)
    if (!lesson) return
    setActiveKind('opening')
    setOpeningName(name)
    loadSession(sessionFromOpening(lesson, 'white'), true)
  }

  const chooseOpeningFamily = (name: string) => {
    const family = openingFamilies.find(item => item.name === name)
    const lesson = family?.variants[0]?.lesson
    if (!lesson) return
    setOpeningFamily(name)
    chooseOpening(lesson.openingName)
  }

  const chooseDefense = (name: string) => {
    const lesson = defenses.find(item => item.openingName === name)
    if (!lesson) return
    setActiveKind('defense')
    setDefenseName(name)
    loadSession(sessionFromOpening(lesson, 'black'), true)
  }

  const chooseDefenseFamily = (name: string) => {
    const family = defenseFamilies.find(item => item.name === name)
    const lesson = family?.variants[0]?.lesson
    if (!lesson) return
    setDefenseFamily(name)
    chooseDefense(lesson.openingName)
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
  const engineResignation = engineResigned
    ? `${session?.userColor === 'white' ? 'Black' : 'White'} resigned · You win`
    : null
  const resignation =
    resigned === null ? null : `${resigned === 'w' ? 'White' : 'Black'} resigned · ${resigned === 'w' ? 'Black' : 'White'} wins`
  const statusText = engineResignation
    ? engineResignation
    : resignation
    ? resignation
    : flaggedSide
      ? `${flaggedSide} lost on time`
      : outcome
        ? outcome
        : scriptDone
          ? 'Lesson complete'
            : opponentThinking
            ? againstEngine || session?.enginePlay
              ? 'Stockfish is moving…'
              : 'Book is replying…'
            : reading
              ? coach.phase === 'idle'
                ? 'Clock paused — press Continue when you have read it'
                : 'Clock paused while Hermes explains'
              : gameStatus(fen) ?? `${sideToMove(fen) === 'w' ? 'White' : 'Black'} to move`

  return (
    <div className="view training-view">
      <section className="panel board-panel" aria-label="Training board">
        <header className="panel-head">
          <div>
            <h2 className="panel-title">{session ? session.title : 'Lessons'}</h2>
            <p className="panel-subtitle">
              {!session && catalogStatus === 'loading'
                ? 'Reading stored lessons…'
                : `${progress} · ${statusText}`}
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
              {(session?.enginePlay ? complete : Boolean(outcome || resignation)) && (
                <div className="board-result">
                  <p>{statusText}</p>
                  {session?.enginePlay && (
                    <button type="button" className="btn primary" onClick={rematch}>
                      <RotateCcw size={14} /> Rematch
                    </button>
                  )}
                </div>
              )}
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
            disabled={Boolean(clock.flagged) || complete || (reading && coach.phase !== 'idle')}
            onClick={() => {
              if (clock.running) {
                clock.pause()
                return
              }
              setReading(false)
              clock.start()
            }}
          >
            {clock.running ? <Pause size={14} /> : <Play size={14} />}
            {clock.running ? 'Pause' : reading ? 'Continue' : 'Start'}
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
          {(scripted || session?.enginePlay) && (
            <button
              type="button"
              className={`btn${showHint ? ' active' : ''}`}
              disabled={!interactive && !showHint}
              onClick={() => {
                if (session?.enginePlay) void requestEngineHint()
                else setShowHint(value => !value)
              }}
            >
              <Lightbulb size={14} /> Hint
            </button>
          )}
          {session?.enginePlay && (
            <button type="button" className="btn" disabled={complete} onClick={resign}>
              <Flag size={14} /> Resign
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
          const playing = Boolean(session?.enginePlay || againstEngine)
          const usersTurn = sideToMove(fromFen) === userSide
          if (playing && usersTurn && !complete && !clock.flagged) {
            clock.pause()
            setReading(true)
          }
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
            <p className="panel-subtitle">
              {catalogSubtitle(catalogStatus, catalogError, openings.length + defenses.length + endgames.length)}
            </p>
          </div>
          {catalogStatus === 'error' && (
            <button type="button" className="btn" onClick={() => setCatalogAttempt(count => count + 1)}>
              Try again
            </button>
          )}
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
                value={openingFamily}
                onChange={event => chooseOpeningFamily(event.target.value)}
                disabled={catalogStatus !== 'ready' || openingFamilies.length === 0}
              >
                {catalogStatus === 'loading' && <option value="">Loading lessons…</option>}
                {catalogStatus === 'error' && <option value="">Lessons unavailable</option>}
                {catalogStatus === 'ready' && openingFamilies.length === 0 && <option value="">No openings stored</option>}
                {openingFamilies.map(item => (
                  <option key={item.name} value={item.name}>
                    {item.name} · {item.games}
                  </option>
                ))}
              </select>
            </label>
            {openingVariants.length > 1 && (
              <label>
                <span className="sr-only">Opening variant</span>
                <select value={openingName} onChange={event => chooseOpening(event.target.value)}>
                  {openingVariants.map(item => (
                    <option key={item.lesson.openingName} value={item.lesson.openingName}>
                      {item.label} · {item.lesson.games}
                    </option>
                  ))}
                </select>
              </label>
            )}
            <span>Your most played openings. Pick a variant to drill it.</span>
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
                value={defenseFamily}
                onChange={event => chooseDefenseFamily(event.target.value)}
                disabled={catalogStatus !== 'ready' || defenseFamilies.length === 0}
              >
                {catalogStatus === 'loading' && <option value="">Loading lessons…</option>}
                {catalogStatus === 'error' && <option value="">Lessons unavailable</option>}
                {catalogStatus === 'ready' && defenseFamilies.length === 0 && <option value="">No defenses stored</option>}
                {defenseFamilies.map(item => (
                  <option key={item.name} value={item.name}>
                    {item.name} · {item.games}
                  </option>
                ))}
              </select>
            </label>
            {defenseVariants.length > 1 && (
              <label>
                <span className="sr-only">Defense variant</span>
                <select value={defenseName} onChange={event => chooseDefense(event.target.value)}>
                  {defenseVariants.map(item => (
                    <option key={item.lesson.openingName} value={item.lesson.openingName}>
                      {item.label} · {item.lesson.games}
                    </option>
                  ))}
                </select>
              </label>
            )}
            <span>Your most played defenses. Pick a variant to drill it.</span>
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
                disabled={catalogStatus !== 'ready' || endgames.length === 0}
              >
                {catalogStatus === 'loading' && <option value="">Loading lessons…</option>}
                {catalogStatus === 'error' && <option value="">Lessons unavailable</option>}
                {catalogStatus === 'ready' && endgames.length === 0 && <option value="">No techniques stored</option>}
                {endgames.map(item => (
                  <option key={endgameKey(item)} value={endgameKey(item)}>
                    {endgameTitle(item.endgameType)}
                  </option>
                ))}
              </select>
            </label>
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
