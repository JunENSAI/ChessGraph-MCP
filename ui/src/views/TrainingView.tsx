import { useEffect, useMemo, useRef, useState } from 'react'
import { Chess, type Square } from 'chess.js'
import {
  ArrowUpDown,
  BookOpen,
  ChevronLeft,
  ChevronRight,
  ClipboardCopy,
  Compass,
  Flag,
  Lightbulb,
  ListOrdered,
  MessageSquare,
  Pause,
  Play,
  RotateCcw,
  Swords,
  Undo2,
  Volume2,
  VolumeX,
} from 'lucide-react'
import type { Arrow } from 'react-chessboard'
import type { BoardMove } from '../components/ChessBoard'
import { BoardStage } from '../components/BoardStage'
import { CoachPanel } from '../components/CoachPanel'
import { ExplorerPanel } from '../components/ExplorerPanel'
import { MoveTable } from '../components/MoveTable'
import { SidePanel } from '../components/SidePanel'
import {
  drillNote,
  loadEndgameLessons,
  loadOpeningLessons,
  playableFen,
  playSession,
  sessionFromEndgame,
  sessionFromOpening,
  sessionFromTask,
  type EndgameLesson,
  type LessonSession,
  type OpeningLesson,
  type TrainingTask,
} from '../data/lessons'
import { endgameTitle, groupOpenings, openingFamilyName } from '../data/openings'
import { loadTrainingPlan, orderPlan, planSummary, type PlanItem, type TrainingPlan } from '../data/plan'
import type { Color } from '../data/types'
import { useBoardKeys } from '../hooks/useBoardKeys'
import { useChessClock } from '../hooks/useChessClock'
import { useCoach } from '../hooks/useCoach'
import { usePlayerProfile } from '../hooks/usePlayerProfile'
import { usePositionEval } from '../hooks/usePositionEval'
import { gameStatus, resultText, sideToMove, tryMove, tryUci, type AppliedMove, type Promotion } from '../lib/chess'
import { describeSideScore, whiteEvalFromSide, type WhiteEval } from '../lib/eval'
import { TIME_CONTROLS } from '../lib/clock'
import { buildPgn } from '../lib/notation'
import { isMuted, playSound, setMuted, soundFor } from '../lib/sound'
import { DEFAULT_STRENGTH, levelForRating, moveTimeMs, STRENGTH_LEVELS, strengthById } from '../lib/strength'
import { createMessage, loadThread, type CandidateLines } from '../services/coach'
import { firstMoveArrows, pathArrows } from '../lib/lines'
import { analyzeFen, EngineError, playEngineMove } from '../services/engine'

const START_FEN = new Chess().fen()
const MOVE_DELAY_MS = 420
/** A move that arrives instantly feels wrong; the opponent waits at least this long. */
const ENGINE_MIN_THINK_MS = 350

type TrainingTab = 'play' | 'moves' | 'coach' | 'explorer'

interface HistoryPly {
  san: string
  from: Square
  to: Square
  fenBefore: string
  fen: string
}

function engineShouldResign(scoreType: 'cp' | 'mate' | null, scoreValue: number | null, fen: string): boolean {
  if (scoreType === null || scoreValue === null) return false
  const moveNumber = Number(fen.split(' ')[5] ?? '1')
  if (!Number.isFinite(moveNumber) || moveNumber < 6) return false
  if (scoreType === 'mate' && scoreValue < 0) return true
  return scoreType === 'cp' && scoreValue <= -1500
}

function introFor(session: LessonSession | null) {
  if (!session) return 'Choose an opening, a defense, an endgame, or start a game.'
  if (session.missingLine) return `${session.title}. ${session.detail}`
  if (session.id.startsWith('task:')) return session.detail
  if (session.enginePlay) {
    const side = session.userColor === 'white' ? 'White' : 'Black'
    return `You play ${side}. Stockfish answers at once at the strength you chose. Ask me about any position; Explain reviews the last move.`
  }
  const side = session.userColor === 'white' ? 'White' : 'Black'
  return `${session.title}: you play ${side}. Play the lesson move; the reply follows on the board.`
}

export function TrainingView({ active = true }: { active?: boolean }) {
  const keepThread = useRef(loadThread('training') !== null)
  const profile = usePlayerProfile()
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
  const [strengthId, setStrengthId] = useState<string | null>(null)
  const [activeKind, setActiveKind] = useState<'opening' | 'defense' | 'endgame' | 'play' | 'course'>('opening')
  const [plan, setPlan] = useState<TrainingPlan | null>(null)
  const [planStatus, setPlanStatus] = useState<'loading' | 'ready' | 'error'>('loading')
  const [watching, setWatching] = useState(false)
  const [session, setSession] = useState<LessonSession | null>(null)
  const [fen, setFen] = useState(START_FEN)
  const [history, setHistory] = useState<HistoryPly[]>([])
  const [viewIndex, setViewIndex] = useState<number | null>(null)
  const [step, setStep] = useState(0)
  const [againstEngine, setAgainstEngine] = useState(false)
  const [lastMove, setLastMove] = useState<BoardMove | null>(null)
  const [showHint, setShowHint] = useState(false)
  const [engineHint, setEngineHint] = useState<{ from: Square; to: Square } | null>(null)
  const [resigned, setResigned] = useState<'w' | 'b' | null>(null)
  const [engineResigned, setEngineResigned] = useState(false)
  const [preview, setPreview] = useState<{ fen: string; evaluation: WhiteEval } | null>(null)
  const [lastEngine, setLastEngine] = useState<{ fen: string; san: string; evalText: string | null } | null>(null)
  const [coachLine, setCoachLine] = useState<{ fen: string; moves: string[] } | null>(null)
  // The coach's candidate lines for one answer, and the one picked to show its whole path.
  const [coachLines, setCoachLines] = useState<{ messageId: string; lines: CandidateLines } | null>(null)
  const [activeLine, setActiveLine] = useState<{ messageId: string; rank: number } | null>(null)
  const [explorerArrow, setExplorerArrow] = useState<string | null>(null)
  const [mistakes, setMistakes] = useState(0)
  const [orientation, setOrientation] = useState<'white' | 'black'>('white')
  const [opponentThinking, setOpponentThinking] = useState(false)
  const [pausedByHide, setPausedByHide] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  const [muted, setMutedState] = useState(isMuted)
  const [tab, setTab] = useState<TrainingTab>('play')
  const [controlId, setControlId] = useState('10+0')
  const control = TIME_CONTROLS.find(item => item.id === controlId)!
  const clock = useChessClock(control)
  const coach = useCoach('training', [createMessage('coach', introFor(null))])
  // Until the player picks a level, match the stored average rating.
  const strength = strengthId ? strengthById(strengthId) : profile.loaded ? levelForRating(profile.averageRating) : strengthById(DEFAULT_STRENGTH)
  const strengthRef = useRef(strength)
  strengthRef.current = strength
  const fenRef = useRef(fen)
  fenRef.current = fen
  const clockRef = useRef(clock)
  clockRef.current = clock
  const sessionRef = useRef(session)
  sessionRef.current = session
  const pending = useRef<number | null>(null)
  const engineToken = useRef(0)

  const displayFen = viewIndex === null ? fen : viewIndex === 0 ? (session?.startFen ?? START_FEN) : history[viewIndex - 1].fen
  const evaluation = usePositionEval(displayFen, preview?.fen === displayFen ? preview.evaluation : null)

  // Leaving the view pauses a running game; nothing ticks out of sight.
  useEffect(() => {
    if (!active && clockRef.current.running) {
      clockRef.current.pause()
      setPausedByHide(true)
    }
  }, [active])

  useEffect(() => {
    if (!notice) return
    const timer = window.setTimeout(() => setNotice(null), 2200)
    return () => window.clearTimeout(timer)
  }, [notice])

  const cancelPending = () => {
    if (pending.current !== null) window.clearTimeout(pending.current)
    pending.current = null
    engineToken.current += 1
    setOpponentThinking(false)
  }

  /** Every move on the live board goes through here: board, history, sound. */
  const commitMove = (applied: AppliedMove, fenBefore: string) => {
    setFen(applied.fen)
    fenRef.current = applied.fen
    setLastMove({ from: applied.from, to: applied.to })
    setHistory(current => [...current, { san: applied.san, from: applied.from, to: applied.to, fenBefore, fen: applied.fen }])
    setViewIndex(null)
    setCoachLine(null)
    playSound(soundFor(applied.san, resultText(applied.fen) !== null))
  }

  const stopForResult = (position: string) => {
    const text = resultText(position)
    if (!text) return false
    clockRef.current.pause()
    coach.say(text)
    return true
  }

  const engineReply = (fromFen: string) => {
    const token = ++engineToken.current
    const thinkingSide = sideToMove(fromFen)
    const level = strengthRef.current
    setOpponentThinking(true)
    setShowHint(false)
    const startedAt = performance.now()
    void (async () => {
      try {
        const played = await playEngineMove(fromFen, level.elo, moveTimeMs(level))
        const elapsed = performance.now() - startedAt
        if (elapsed < ENGINE_MIN_THINK_MS) await wait(ENGINE_MIN_THINK_MS - elapsed)
        if (token !== engineToken.current || fenRef.current !== fromFen) return
        if (clockRef.current.flagged === thinkingSide) {
          coach.say(`${thinkingSide === 'w' ? 'White' : 'Black'} lost on time`)
          return
        }
        if (sessionRef.current?.enginePlay && engineShouldResign(played.scoreType, played.scoreValue, fromFen)) {
          clockRef.current.pause()
          setEngineResigned(true)
          coach.say(`${thinkingSide === 'w' ? 'White' : 'Black'} resigns.`)
          return
        }
        const applied = tryUci(fromFen, played.uci)
        if (!applied) {
          coach.say('Stockfish returned a move that is not legal in this position.')
          return
        }
        commitMove(applied, fromFen)
        const side = thinkingSide === 'w' ? 'w' : 'b'
        if (played.scoreType && played.scoreValue !== null) {
          setPreview({
            fen: applied.fen,
            // The score is from the mover before its move; as an estimate it stands for the new position too.
            evaluation: whiteEvalFromSide(
              played.scoreType === 'cp' ? played.scoreValue : null,
              played.scoreType === 'mate' ? played.scoreValue : null,
              side,
            ),
          })
        }
        setLastEngine({
          fen: applied.fen,
          san: applied.san,
          evalText:
            played.scoreType && played.scoreValue !== null
              ? describeSideScore(played.scoreType, played.scoreValue, side === 'w' ? 'white' : 'black')
              : null,
        })
        if (stopForResult(applied.fen)) return
        clockRef.current.press()
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
      commitMove(applied, fromFen)
      if (stopForResult(applied.fen)) {
        setStep(index + 1)
        setOpponentThinking(false)
        return
      }
      clockRef.current.press()
      coach.say(lesson.line[index].explanation)
      const next = index + 1
      setStep(next)
      setOpponentThinking(false)
      if (next === lesson.line.length && lesson.engineAfter) {
        setAgainstEngine(true)
        engineReply(applied.fen)
      } else if (next === lesson.line.length) {
        coach.say('Lesson complete. Choose it again to drill the line.')
      }
    }, MOVE_DELAY_MS)
  }

  const resetBoard = (startFen: string) => {
    setFen(startFen)
    fenRef.current = startFen
    setHistory([])
    setViewIndex(null)
    setLastMove(null)
    setCoachLine(null)
  }

  const demonstrate = (lesson: LessonSession) => {
    setWatching(true)
    clockRef.current.pause()
    let fenNow = lesson.startFen
    let index = 0
    const tick = () => {
      if (index >= lesson.line.length) {
        setWatching(false)
        resetBoard(lesson.startFen)
        setStep(0)
        coach.say('Your turn. Play the same moves.')
        const userSideNow = lesson.userColor === 'white' ? 'w' : 'b'
        if (sideToMove(lesson.startFen) !== userSideNow && lesson.line.length > 0) {
          playScripted(lesson, lesson.startFen, 0)
        }
        return
      }
      const applied = tryMoveSan(fenNow, lesson.line[index].san)
      if (!applied) {
        setWatching(false)
        coach.say('The stored line is not legal from this position.')
        return
      }
      commitMove(applied, fenNow)
      fenNow = applied.fen
      setStep(index + 1)
      index += 1
      pending.current = window.setTimeout(tick, MOVE_DELAY_MS)
    }
    pending.current = window.setTimeout(tick, MOVE_DELAY_MS)
  }

  const loadSession = (next: LessonSession, resetCoach: boolean) => {
    cancelPending()
    setSession(next)
    resetBoard(next.startFen)
    setStep(0)
    setAgainstEngine(next.enginePlay)
    setShowHint(false)
    setEngineHint(null)
    setResigned(null)
    setEngineResigned(false)
    setWatching(false)
    setPreview(null)
    setLastEngine(null)
    setMistakes(0)
    setPausedByHide(false)
    setOrientation(next.userColor)
    clock.reset(control, sideToMove(next.startFen))
    if (resetCoach) coach.reset([createMessage('coach', introFor(next))])
    if (next.watch && next.line.length > 0) {
      demonstrate(next)
      return
    }
    const opponentStarts = sideToMove(next.startFen) !== (next.userColor === 'white' ? 'w' : 'b')
    if (opponentStarts && next.enginePlay) engineReply(next.startFen)
    else if (opponentStarts && !next.missingLine && next.line.length > 0) playScripted(next, next.startFen, 0)
  }

  useEffect(() => {
    let live = true
    loadTrainingPlan()
      .then(next => {
        if (!live) return
        setPlan(next)
        setPlanStatus('ready')
      })
      .catch(() => {
        if (!live) return
        setPlan(null)
        setPlanStatus('error')
      })
    Promise.all([loadOpeningLessons('white'), loadOpeningLessons('black'), loadEndgameLessons()])
      .then(([white, black, endgame]) => {
        if (!live) return
        setOpenings(white)
        setDefenses(black)
        setEndgames(endgame.lessons)
        setCatalogError(null)
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
          loadSession(sessionFromOpening(first, 'white'), !keepThread.current)
          keepThread.current = false
        }
      })
      .catch((reason: unknown) => {
        if (live) setCatalogError(reason instanceof Error ? reason.message : 'Lessons could not be loaded.')
      })
    return () => {
      live = false
    }
    // The catalog is loaded once. Later choices call loadSession directly.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const playing = Boolean(session?.enginePlay || againstEngine)
  const scripted = Boolean(session && !session.enginePlay && !againstEngine && !session.missingLine)
  const expected = scripted ? session?.line[step] : undefined
  const userSide = session ? (session.userColor === 'white' ? 'w' : 'b') : 'w'
  const outcome = resultText(fen)
  const terminal = outcome !== null
  const scriptDone = Boolean(session && scripted && step >= session.line.length && !session.engineAfter)
  const complete = terminal || scriptDone || resigned !== null || engineResigned || Boolean(playing && clock.flagged)
  const browsing = viewIndex !== null
  const interactive =
    Boolean(session) &&
    !session?.missingLine &&
    !clock.flagged &&
    !opponentThinking &&
    !watching &&
    !complete &&
    !browsing &&
    sideToMove(fen) === userSide

  const arrows = useMemo<Arrow[]>(() => {
    const list: Arrow[] = []
    if (explorerArrow) {
      list.push({ startSquare: explorerArrow.slice(0, 2), endSquare: explorerArrow.slice(2, 4), color: '#77a7ff' })
    }
    if (coachLines && coachLines.lines.fen === displayFen) {
      const picked = activeLine?.messageId === coachLines.messageId
        ? coachLines.lines.lines.find(line => line.rank === activeLine.rank)
        : undefined
      list.push(...(picked ? pathArrows(coachLines.lines.fen, picked) : firstMoveArrows(coachLines.lines)))
    } else if (coachLine && coachLine.fen === displayFen) {
      let position = coachLine.fen
      coachLine.moves.slice(0, 2).forEach((uci, index) => {
        const applied = tryUci(position, uci)
        if (!applied) return
        list.push({ startSquare: applied.from, endSquare: applied.to, color: index === 0 ? '#b8f05a' : 'rgba(184, 240, 90, 0.45)' })
        position = applied.fen
      })
    }
    if (!showHint || browsing) return list
    if (engineHint) return [...list, { startSquare: engineHint.from, endSquare: engineHint.to, color: '#bb9af7' }]
    if (!expected || !interactive) return list
    const applied = tryMoveSan(fen, expected.san)
    if (applied) list.push({ startSquare: applied.from, endSquare: applied.to, color: '#bb9af7' })
    return list
  }, [explorerArrow, coachLines, activeLine, coachLine, displayFen, showHint, browsing, engineHint, expected, interactive, fen])

  const requestEngineHint = async () => {
    if (showHint) {
      setShowHint(false)
      return
    }
    try {
      const analysis = await analyzeFen(fen, { limitType: 'time', limitValue: 400 })
      setEngineHint({ from: analysis.uci.slice(0, 2) as Square, to: analysis.uci.slice(2, 4) as Square })
      setShowHint(true)
      coach.say(`Hint: ${analysis.san}.`)
    } catch (error) {
      coach.say(error instanceof EngineError ? error.message : 'Stockfish could not offer a hint.')
    }
  }

  const resign = () => {
    if (!playing || complete) return
    cancelPending()
    clock.pause()
    setResigned(userSide)
    playSound('end')
    coach.say(`You resigned. ${userSide === 'w' ? 'Black' : 'White'} wins.`)
  }

  const userMovesPlayed = history.some(ply => sideToMove(ply.fenBefore) === userSide)
  const canTakeBack = playing && userMovesPlayed && !opponentThinking && resigned === null && !engineResigned && !clock.flagged

  /** Take back your last move and the reply to it, so it is your move again. */
  const takeBack = () => {
    if (!canTakeBack || !session) return
    cancelPending()
    const next = history.slice(0, -1)
    const fenOf = (plies: HistoryPly[]) => (plies.length ? plies[plies.length - 1].fen : session.startFen)
    while (next.length > 0 && sideToMove(fenOf(next)) !== userSide) next.pop()
    const target = fenOf(next)
    setHistory(next)
    setViewIndex(null)
    setFen(target)
    fenRef.current = target
    const last = next[next.length - 1]
    setLastMove(last ? { from: last.from, to: last.to } : null)
    setPreview(null)
    setLastEngine(null)
    setShowHint(false)
    setEngineHint(null)
    setCoachLine(null)
    if (clock.active !== sideToMove(target)) clock.press()
    if (sideToMove(target) !== userSide) engineReply(target)
    setNotice('Move taken back')
  }

  const handleMove = (from: Square, to: Square, promotion?: Promotion) => {
    if (!interactive || !session) return false
    const applied = tryMove(fen, from, to, promotion)
    if (!applied) return false

    if (playing) {
      commitMove(applied, fen)
      setShowHint(false)
      setEngineHint(null)
      setPreview(null)
      setPausedByHide(false)
      if (stopForResult(applied.fen)) return true
      clock.press()
      engineReply(applied.fen)
      return true
    }

    if (!expected || applied.san !== expected.san) {
      setMistakes(count => count + 1)
      coach.say(`${applied.san} is legal, but this lesson continues differently. Use Hint to see the move.`)
      return false
    }

    commitMove(applied, fen)
    setShowHint(false)
    clock.press()
    coach.say(expected.explanation)
    const nextStep = step + 1
    setStep(nextStep)
    if (nextStep < session.line.length) playScripted(session, applied.fen, nextStep)
    else if (session.engineAfter) {
      setAgainstEngine(true)
      engineReply(applied.fen)
    } else coach.say('Lesson complete. Choose it again to drill the line.')
    return true
  }

  const openingFamilies = useMemo(() => groupOpenings(openings), [openings])
  const defenseFamilies = useMemo(() => groupOpenings(defenses), [defenses])
  const openingVariants = openingFamilies.find(item => item.name === openingFamily)?.variants ?? []
  const defenseVariants = defenseFamilies.find(item => item.name === defenseFamily)?.variants ?? []

  const startEndgame = async (task: TrainingTask) => {
    const base = sessionFromTask(task)
    let uci = task.uci_line
    const first = uci.split(/\s+/)[0]
    const applied = first ? tryUci(base.startFen, first) : null
    if (applied) {
      try {
        const analysis = await analyzeFen(applied.fen)
        uci = [first, ...analysis.pv].join(' ')
      } catch {
        uci = task.uci_line
      }
    }
    loadSession(sessionFromTask(task, uci), true)
    coach.say('The first move is the stored technique move. The following moves are a Stockfish search.')
  }

  const startPuzzle = async (task: TrainingTask) => {
    coach.say('Searching the candidate positions for a short mate.')
    for (const candidate of task.puzzle_fens) {
      try {
        const analysis = await analyzeFen(playableFen(candidate))
        const mate = analysis.scoreType === 'mate' && analysis.scoreValue >= 1 && analysis.scoreValue <= 5
        if (!mate) continue
        loadSession(
          sessionFromTask({ ...task, start_fen: playableFen(candidate), user_color: analysis.side, uci_line: analysis.pv.join(' ') }),
          true,
        )
        coach.say(`Mate in ${analysis.scoreValue}. Find the continuation.`)
        return
      } catch {
        continue
      }
    }
    coach.say('No mate was found in those positions.')
  }

  const taskFromPlanItem = (entry: PlanItem): TrainingTask => ({
    kind: entry.kind,
    title: entry.title,
    reason: entry.reason,
    start_fen: entry.start_fen,
    uci_line: entry.uci_line,
    pgn_line: entry.pgn_line,
    user_color: entry.user_color,
    ready: entry.ready,
    puzzle_fens: entry.puzzle_fens,
  })

  /** The plan item's reason starts with its family, so the family is the text before the first colon. */
  const planFamily = (entry: PlanItem) => entry.reason.split(':')[0].trim()

  const startPlanItem = (entry: PlanItem) => {
    setActiveKind('course')
    if (entry.kind === 'puzzle') {
      void startPuzzle(taskFromPlanItem(entry))
      return
    }
    if (entry.kind === 'endgame') {
      const lesson = endgames.find(item => endgameTitle(item.endgameType) === entry.title || item.endgameType === entry.title)
      if (!lesson) {
        coach.say(`No stored endgame position for ${entry.title}.`)
        return
      }
      void startEndgame({ ...taskFromPlanItem(entry), start_fen: lesson.fenFull, uci_line: lesson.humanMoveUci })
      return
    }
    const family = planFamily(entry).toLowerCase()
    const lesson = [...openings, ...defenses].find(item => openingFamilyName(item.openingName).family.toLowerCase() === family)
    if (lesson) {
      loadSession(sessionFromOpening(lesson, entry.user_color), true)
      return
    }
    if (!entry.uci_line && !entry.pgn_line) {
      coach.say(`No stored line for ${planFamily(entry)} yet, so there is nothing to drill there.`)
      return
    }
    loadSession(sessionFromTask(taskFromPlanItem(entry)), true)
  }

  const chooseOpening = (name: string) => {
    const lesson = openings.find(item => item.openingName === name)
    if (!lesson) return
    setActiveKind('opening')
    setOpeningName(name)
    loadSession(sessionFromOpening(lesson, 'white'), true)
  }

  const chooseOpeningFamily = (name: string) => {
    const lesson = openingFamilies.find(item => item.name === name)?.variants[0]?.lesson
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
    const lesson = defenseFamilies.find(item => item.name === name)?.variants[0]?.lesson
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

  const startGame = (color: Color = playColor) => {
    setActiveKind('play')
    setPlayColor(color)
    loadSession(playSession(color), true)
    setTab('moves')
  }

  const changeControl = (id: string) => {
    const next = TIME_CONTROLS.find(item => item.id === id)
    if (!next) return
    setControlId(id)
    clock.reset(next, sideToMove(fenRef.current))
  }

  const toggleMute = () => {
    setMuted(!muted)
    setMutedState(!muted)
  }

  const flip = () => setOrientation(value => (value === 'white' ? 'black' : 'white'))

  const pgnResult = (): '1-0' | '0-1' | '1/2-1/2' | '*' => {
    const whiteWins = (loser: 'w' | 'b') => (loser === 'b' ? '1-0' : '0-1')
    if (resigned) return whiteWins(resigned)
    if (engineResigned) return whiteWins(userSide === 'w' ? 'b' : 'w')
    if (clock.flagged) return whiteWins(clock.flagged)
    if (outcome?.includes('checkmate')) return outcome.startsWith('White') ? '1-0' : '0-1'
    if (outcome) return '1/2-1/2'
    return '*'
  }

  const copyPgn = async () => {
    if (!session) return
    try {
      const startFen = session.startFen === START_FEN ? undefined : session.startFen
      const pgn = buildPgn(history.map(ply => ply.san), { white: nameFor('white'), black: nameFor('black'), result: pgnResult() }, startFen)
      await navigator.clipboard.writeText(pgn)
      setNotice('PGN copied')
    } catch {
      setNotice('The browser refused the clipboard')
    }
  }

  const explainLast = () => {
    const last = history[history.length - 1]
    if (!last) return
    setTab('coach')
    const mover: Color = sideToMove(last.fenBefore) === 'w' ? 'white' : 'black'
    const evalText = lastEngine?.fen === last.fen ? lastEngine.evalText ?? '' : ''
    void coach.ask(`Explain ${last.san}`, {
      mode: 'training',
      fen: last.fen,
      summary: session?.title ?? 'game',
      played: { san: last.san, color: mover, evalText },
      profile: plan ? planSummary(plan) : undefined,
    })
  }

  useBoardKeys(active, {
    index: viewIndex ?? history.length,
    last: history.length,
    go: index => setViewIndex(index >= history.length ? null : index),
    flip,
  })

  // The level shows as the rating next to the name.
  const partner = playing ? 'Stockfish' : 'Book'
  function nameFor(color: Color) {
    if (!session) return color === 'white' ? 'White' : 'Black'
    return color === session.userColor ? profile.username : partner
  }
  const seat = (color: Color) => {
    const side = color === 'white' ? 'w' : 'b'
    const mine = session ? color === session.userColor : false
    return {
      name: nameFor(color),
      rating: mine ? (profile.averageRating ? Math.round(profile.averageRating) : undefined) : playing ? (strength.elo ?? undefined) : undefined,
      timeMs: clock.remaining[side],
      active: clock.running && clock.active === side,
      flagged: clock.flagged === side,
      thinking: !mine && opponentThinking,
    }
  }

  const flaggedSide = clock.flagged === 'w' ? 'White' : clock.flagged === 'b' ? 'Black' : null
  const progress = playing && session?.enginePlay
    ? 'Game'
    : session && !session.missingLine
      ? `Move ${Math.min(step + 1, Math.max(session.line.length, 1))} of ${session.line.length}`
      : 'Lesson'
  const engineResignation = engineResigned ? `${session?.userColor === 'white' ? 'Black' : 'White'} resigned · You win` : null
  const resignation = resigned === null ? null : `${resigned === 'w' ? 'White' : 'Black'} resigned · ${resigned === 'w' ? 'Black' : 'White'} wins`
  const statusText =
    notice ??
    engineResignation ??
    resignation ??
    (flaggedSide
      ? `${flaggedSide} lost on time`
      : outcome
        ? outcome
        : scriptDone
          ? 'Lesson complete'
          : browsing
            ? `Viewing move ${viewIndex} of ${history.length} · → or End returns to the game`
            : opponentThinking
              ? playing
                ? 'Stockfish is thinking…'
                : 'Book is replying…'
              : pausedByHide
                ? 'Paused while you were away · press Resume'
                : (gameStatus(fen) ?? `${sideToMove(fen) === 'w' ? 'White' : 'Black'} to move`))
  const finished = playing ? complete : Boolean(outcome || resignation)

  const overlay = finished ? (
    <>
      <p>{engineResignation ?? resignation ?? (flaggedSide ? `${flaggedSide} lost on time` : outcome ?? 'Lesson complete')}</p>
      {session?.enginePlay && (
        <div className="overlay-actions">
          <button type="button" className="btn primary" onClick={() => startGame(session.userColor)}>
            <RotateCcw size={14} /> Rematch
          </button>
          <button type="button" className="btn" onClick={() => startGame(session.userColor === 'white' ? 'black' : 'white')}>
            Switch sides
          </button>
        </div>
      )}
    </>
  ) : null

  const controls = (
    <>
      <button
        type="button"
        className="btn primary"
        disabled={Boolean(clock.flagged) || complete}
        onClick={() => {
          if (clock.running) clock.pause()
          else {
            setPausedByHide(false)
            clock.start()
          }
        }}
      >
        {clock.running ? <Pause size={14} /> : <Play size={14} />}
        {clock.running ? 'Pause' : pausedByHide || history.length > 0 ? 'Resume' : 'Start clock'}
      </button>
      {(scripted || playing) && (
        <button
          type="button"
          className={`btn${showHint ? ' active' : ''}`}
          disabled={!interactive && !showHint}
          onClick={() => {
            if (playing) void requestEngineHint()
            else setShowHint(value => !value)
          }}
        >
          <Lightbulb size={14} /> Hint
        </button>
      )}
      {playing && (
        <>
          <button type="button" className="btn" disabled={!canTakeBack} onClick={takeBack}>
            <Undo2 size={14} /> Takeback
          </button>
          <button type="button" className="btn" disabled={complete} onClick={resign}>
            <Flag size={14} /> Resign
          </button>
        </>
      )}
      <span className="spacer" />
      <button type="button" className="btn icon" aria-label="Previous move" disabled={(viewIndex ?? history.length) === 0} onClick={() => setViewIndex((viewIndex ?? history.length) - 1)}>
        <ChevronLeft size={15} />
      </button>
      <button type="button" className="btn icon" aria-label="Next move" disabled={!browsing} onClick={() => setViewIndex(viewIndex! + 1 >= history.length ? null : viewIndex! + 1)}>
        <ChevronRight size={15} />
      </button>
      <button type="button" className="btn icon" aria-label="Copy PGN" disabled={history.length === 0} onClick={() => void copyPgn()}>
        <ClipboardCopy size={14} />
      </button>
      <button type="button" className="btn icon" aria-label={muted ? 'Turn sound on' : 'Mute sound'} onClick={toggleMute}>
        {muted ? <VolumeX size={14} /> : <Volume2 size={14} />}
      </button>
      <button type="button" className="btn icon" aria-label="Restart" onClick={() => session && loadSession(session, true)}>
        <RotateCcw size={14} />
      </button>
      <button type="button" className="btn icon" aria-label="Flip board (F)" onClick={flip}>
        <ArrowUpDown size={14} />
      </button>
    </>
  )

  const playTab = (
    <div className="scroll-pane">
      <article className={`track-card play-card${activeKind === 'play' ? ' active' : ''}`}>
        <span className="eyebrow">New game against Stockfish</span>
        <div className="segmented" role="group" aria-label="Your color">
          {(['white', 'black'] as const).map(color => (
            <button key={color} type="button" className={playColor === color ? 'active' : ''} onClick={() => setPlayColor(color)}>
              <span className={`player-swatch ${color}`} aria-hidden="true" /> {color === 'white' ? 'White' : 'Black'}
            </button>
          ))}
        </div>
        <label className="field">
          <span>Strength</span>
          <select value={strength.id} onChange={event => setStrengthId(event.target.value)}>
            {STRENGTH_LEVELS.map(level => (
              <option key={level.id} value={level.id}>
                {level.label}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>Time control</span>
          <select value={controlId} onChange={event => changeControl(event.target.value)}>
            {TIME_CONTROLS.map(item => (
              <option key={item.id} value={item.id}>
                {item.label}
              </option>
            ))}
          </select>
        </label>
        <button type="button" className="btn primary play-button" onClick={() => startGame()}>
          <Swords size={15} /> Play
        </button>
        <span className="muted small">
          {strengthId ? 'Stockfish limits its strength with UCI_Elo.' : 'Level matched to your average rating. Change it any time; the next move uses it.'}
        </span>
      </article>

      <article className={`track-card${activeKind === 'course' ? ' active' : ''}`}>
        <span className="eyebrow">Your training plan</span>
        {planStatus === 'ready' && plan ? (
          <>
            <p className="muted small">{planSummary(plan)}</p>
            {orderPlan(plan.items).map(entry => (
              <button
                key={`${entry.kind}:${entry.title}`}
                type="button"
                className="btn task-choice"
                disabled={!entry.ready}
                onClick={() => startPlanItem(entry)}
              >
                {entry.title}
                <span>{entry.reason}</span>
                <span className="muted small">Goal: {entry.goal}</span>
              </button>
            ))}
          </>
        ) : (
          <span>{planStatus === 'error' ? 'The training plan could not be loaded.' : 'Reading your games…'}</span>
        )}
      </article>

      {catalogError && <p className="muted small">{catalogError}</p>}
      <LessonCard
        title="Opening"
        note="Your most played openings. Pick a variant to drill it."
        active={activeKind === 'opening'}
        family={openingFamily}
        families={openingFamilies}
        variant={openingName}
        variants={openingVariants}
        onFamily={chooseOpeningFamily}
        onVariant={chooseOpening}
        onOpen={() => openingName && chooseOpening(openingName)}
        empty="No openings stored"
      />
      <LessonCard
        title="Defense"
        note="Your most played defenses. Pick a variant to drill it."
        active={activeKind === 'defense'}
        family={defenseFamily}
        families={defenseFamilies}
        variant={defenseName}
        variants={defenseVariants}
        onFamily={chooseDefenseFamily}
        onVariant={chooseDefense}
        onOpen={() => defenseName && chooseDefense(defenseName)}
        empty="No defenses stored"
      />
      <article
        className={`track-card${activeKind === 'endgame' ? ' active' : ''}`}
        onClick={event => {
          if ((event.target as HTMLElement).closest('select, option')) return
          if (endgameId) chooseEndgame(endgameId)
        }}
      >
        <span className="eyebrow">Endgame technique</span>
        <label>
          <span className="sr-only">Endgame technique</span>
          <select value={endgameId} onChange={event => chooseEndgame(event.target.value)} disabled={endgames.length === 0}>
            {endgames.length === 0 && <option value="">No techniques stored</option>}
            {endgames.map(item => (
              <option key={endgameKey(item)} value={endgameKey(item)}>
                {endgameTitle(item.endgameType)}
              </option>
            ))}
          </select>
        </label>
      </article>
    </div>
  )

  const movesTab = (
    <div className="moves-tab">
      <MoveTable
        plies={history}
        current={viewIndex ?? history.length}
        startFen={session?.startFen}
        onSelect={index => setViewIndex(index >= history.length ? null : index)}
        empty={playing ? 'Make your first move.' : 'The moves you play appear here.'}
      />
      <div className="moves-actions">
        <button type="button" className="btn" disabled={history.length === 0 || coach.phase !== 'idle'} onClick={explainLast}>
          <MessageSquare size={14} /> Explain last move
        </button>
        <button type="button" className="btn" disabled={history.length === 0} onClick={() => void copyPgn()}>
          <ClipboardCopy size={14} /> Copy PGN
        </button>
      </div>
      <p className="muted small keys-note">← → browse · Home/End jump · F flips</p>
    </div>
  )

  const coachTab = (
    <CoachPanel
      embedded
      title="Coach"
      subtitle="Evaluation, the move, and a short reason"
      messages={coach.messages}
      phase={coach.phase}
      trace={coach.trace}
      mode={coach.mode}
      prompts={['Why this move?', 'What is the plan?', 'What should I train?']}
      activeLine={activeLine}
      onLine={(message, line) => {
        if (!message.lines) return
        setCoachLines({ messageId: message.id, lines: message.lines })
        setActiveLine(current =>
          current?.messageId === message.id && current.rank === line.rank ? null : { messageId: message.id, rank: line.rank },
        )
      }}
      onAsk={question => {
        const fromFen = displayFen
        if (playing && !complete && sideToMove(fen) === userSide && clock.running) clock.pause()
        void coach
          .ask(
            question,
            {
              mode: 'training',
              fen: fromFen,
              summary: session ? `${session.title}, ${progress.toLowerCase()}` : 'lesson',
              profile: plan ? planSummary(plan) : undefined,
            },
            {
              onLines: (lines, messageId) => {
                setCoachLines({ messageId, lines })
                setActiveLine(null)
              },
            },
          )
          .then(reply => {
            if (!reply?.lines && reply?.play?.length) {
              setCoachLines(null)
              setCoachLine({ fen: fromFen, moves: reply.play })
            }
          })
      }}
    />
  )

  return (
    <div className="view play-layout">
      <BoardStage
        id="training-board"
        fen={displayFen}
        orientation={orientation}
        white={seat('white')}
        black={seat('black')}
        evaluation={evaluation}
        interactive={interactive}
        onMove={handleMove}
        lastMove={browsing ? (viewIndex! > 0 ? { from: history[viewIndex! - 1].from, to: history[viewIndex! - 1].to } : null) : lastMove}
        arrows={arrows}
        overlay={browsing ? null : overlay}
        controls={controls}
        header={
          <>
            <h2 className="panel-title">{session ? session.title : 'Lessons'}</h2>
            <p className="panel-subtitle" aria-live="polite">
              {progress} · {statusText}
              {session && !playing ? ` · ${drillNote(session)}` : ''}
              {playing ? ` · ${strength.label} · ${control.label}` : ''}
              {mistakes > 0 ? ` · ${mistakes} retr${mistakes === 1 ? 'y' : 'ies'}` : ''}
            </p>
          </>
        }
      />
      <SidePanel<TrainingTab>
        label="Training"
        active={tab}
        onChange={setTab}
        tabs={[
          { id: 'play', label: 'Play', icon: Swords, content: playTab },
          { id: 'moves', label: 'Moves', icon: ListOrdered, badge: history.length ? Math.ceil(history.length / 2) : undefined, content: movesTab },
          { id: 'coach', label: 'Coach', icon: BookOpen, content: coachTab },
          {
            id: 'explorer',
            label: 'Explorer',
            icon: Compass,
            content: <ExplorerPanel fen={displayFen} active={active && tab === 'explorer'} onPreview={setExplorerArrow} />,
          },
        ]}
      />
    </div>
  )
}

interface LessonCardProps {
  title: string
  note: string
  active: boolean
  family: string
  families: { name: string; games: number }[]
  variant: string
  variants: { label: string; lesson: { openingName: string; games: number } }[]
  onFamily: (name: string) => void
  onVariant: (name: string) => void
  onOpen: () => void
  empty: string
}

function LessonCard({ title, note, active, family, families, variant, variants, onFamily, onVariant, onOpen, empty }: LessonCardProps) {
  return (
    <article
      className={`track-card${active ? ' active' : ''}`}
      onClick={event => {
        if ((event.target as HTMLElement).closest('select, option')) return
        onOpen()
      }}
    >
      <span className="eyebrow">{title}</span>
      <label>
        <span className="sr-only">{title}</span>
        <select value={family} onChange={event => onFamily(event.target.value)} disabled={families.length === 0}>
          {families.length === 0 && <option value="">{empty}</option>}
          {families.map(item => (
            <option key={item.name} value={item.name}>
              {item.name} · {item.games}
            </option>
          ))}
        </select>
      </label>
      {variants.length > 1 && (
        <label>
          <span className="sr-only">{title} variant</span>
          <select value={variant} onChange={event => onVariant(event.target.value)}>
            {variants.map(item => (
              <option key={item.lesson.openingName} value={item.lesson.openingName}>
                {item.label} · {item.lesson.games}
              </option>
            ))}
          </select>
        </label>
      )}
      <span>{note}</span>
    </article>
  )
}

function endgameKey(lesson: EndgameLesson): string {
  return `${lesson.endgameType}:${lesson.fenFull}`
}

function tryMoveSan(fen: string, san: string): AppliedMove | null {
  const chess = new Chess(fen)
  try {
    const move = chess.move(san)
    return { san: move.san, from: move.from, to: move.to, fen: chess.fen() }
  } catch {
    return null
  }
}

function wait(ms: number): Promise<void> {
  return new Promise(resolve => {
    window.setTimeout(resolve, ms)
  })
}
