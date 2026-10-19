import { useMemo, useRef, useState } from 'react'
import { Chess, type Square } from 'chess.js'
import { ArrowUpDown, Lightbulb, Pause, Play, RotateCcw } from 'lucide-react'
import { ChessBoard, type BoardMove } from '../components/ChessBoard'
import { CoachPanel } from '../components/CoachPanel'
import { PlayerBar } from '../components/PlayerBar'
import { TRAINING_TRACKS } from '../data/demo'
import type { TrainingTrack } from '../data/types'
import { useChessClock } from '../hooks/useChessClock'
import { useCoach } from '../hooks/useCoach'
import { gameStatus, replaySan, sideToMove, tryMove } from '../lib/chess'
import { TIME_CONTROLS } from '../lib/clock'
import { createMessage } from '../services/coach'

const START_FEN = new Chess().fen()
const FREE_PLAY = 'free-play'
const KIND_LABEL: Record<TrainingTrack['kind'], string> = {
  opening: 'Opening learning',
  defense: 'Defense learning',
  endgame: 'Endgame learning',
}
const OPPONENT_DELAY_MS = 550

function introFor(track: TrainingTrack | undefined) {
  if (!track) return 'Free play: move for both sides. The clock switches after every legal move.'
  const side = track.userColor === 'white' ? 'White' : 'Black'
  return `${track.title}: you play ${side}. Play the lesson move; I will reply and explain each step.`
}

export function TrainingView() {
  const [trackId, setTrackId] = useState(TRAINING_TRACKS[0].id)
  const track = TRAINING_TRACKS.find(item => item.id === trackId)
  const [fen, setFen] = useState(track?.startFen ?? START_FEN)
  const [step, setStep] = useState(0)
  const [lastMove, setLastMove] = useState<BoardMove | null>(null)
  const [showHint, setShowHint] = useState(false)
  const [mistakes, setMistakes] = useState(0)
  const [orientation, setOrientation] = useState<'white' | 'black'>(track?.userColor ?? 'white')
  const [opponentThinking, setOpponentThinking] = useState(false)
  const [controlId, setControlId] = useState('10+0')
  const control = TIME_CONTROLS.find(item => item.id === controlId)!
  const clock = useChessClock(control)
  const coach = useCoach([createMessage('coach', introFor(track))])
  const pending = useRef<number | null>(null)

  const cancelPending = () => {
    if (pending.current !== null) window.clearTimeout(pending.current)
    pending.current = null
    setOpponentThinking(false)
  }

  const playLessonReply = (lesson: TrainingTrack, fromFen: string, index: number) => {
    setOpponentThinking(true)
    pending.current = window.setTimeout(() => {
      pending.current = null
      const [reply] = replaySan([lesson.line[index].san], fromFen)
      setFen(reply.fenAfter)
      setLastMove({ from: reply.from, to: reply.to })
      clock.press()
      coach.say(lesson.line[index].explanation)
      setStep(index + 1)
      setOpponentThinking(false)
      if (index + 1 === lesson.line.length) coach.say('Lesson complete. Restart it to drill the line again.')
    }, OPPONENT_DELAY_MS)
  }

  const loadTrack = (id: string, nextControl = control) => {
    cancelPending()
    const next = TRAINING_TRACKS.find(item => item.id === id)
    const startFen = next?.startFen ?? START_FEN
    setTrackId(id)
    setFen(startFen)
    setStep(0)
    setLastMove(null)
    setShowHint(false)
    setMistakes(0)
    setOrientation(next?.userColor ?? 'white')
    clock.reset(nextControl, sideToMove(startFen))
    coach.reset([createMessage('coach', introFor(next))])
    if (next && next.userColor === 'black') playLessonReply(next, startFen, 0)
  }

  const expected = track?.line[step]
  const userSide = track ? (track.userColor === 'white' ? 'w' : 'b') : sideToMove(fen)
  const status = gameStatus(fen)
  const complete = track ? step >= track.line.length : status === 'Checkmate' || status?.startsWith('Draw')
  const interactive = !clock.flagged && !opponentThinking && !complete && sideToMove(fen) === userSide

  const hintArrow = useMemo(() => {
    if (!showHint || !expected || !interactive) return []
    const [move] = replaySan([expected.san], fen)
    return [{ startSquare: move.from, endSquare: move.to, color: '#bb9af7' }]
  }, [showHint, expected, interactive, fen])

  const handleMove = (from: Square, to: Square) => {
    if (!interactive) return false
    const applied = tryMove(fen, from, to)
    if (!applied) return false

    if (!track) {
      setFen(applied.fen)
      setLastMove({ from, to })
      clock.press()
      return true
    }

    if (!expected || applied.san !== expected.san) {
      setMistakes(count => count + 1)
      coach.say(`${applied.san} is legal, but this lesson continues differently. Use Hint to see the move.`)
      return false
    }

    setFen(applied.fen)
    setLastMove({ from, to })
    setShowHint(false)
    clock.press()
    coach.say(expected.explanation)
    const nextStep = step + 1
    setStep(nextStep)
    if (nextStep < track.line.length) playLessonReply(track, applied.fen, nextStep)
    else coach.say('Lesson complete. Restart it to drill the line again.')
    return true
  }

  const changeControl = (id: string) => {
    setControlId(id)
    loadTrack(trackId, TIME_CONTROLS.find(item => item.id === id)!)
  }

  const topColor = orientation === 'white' ? 'black' : 'white'
  const bottomColor = orientation
  const nameFor = (color: 'white' | 'black') => {
    if (!track) return color === 'white' ? 'White' : 'Black'
    return color === track.userColor ? 'Junior' : 'Lesson partner'
  }
  const flaggedSide = clock.flagged === 'w' ? 'White' : clock.flagged === 'b' ? 'Black' : null
  const progress = track ? `Move ${Math.min(step + 1, track.line.length)} of ${track.line.length}` : 'Free play'
  const statusText = flaggedSide
    ? `${flaggedSide} lost on time`
    : complete && track
      ? 'Lesson complete'
      : opponentThinking
        ? 'Partner is replying…'
        : status ?? `${sideToMove(fen) === 'w' ? 'White' : 'Black'} to move`

  return (
    <div className="view training-view">
      <section className="panel board-panel" aria-label="Training board">
        <header className="panel-head">
          <div>
            <h2 className="panel-title">{track ? track.title : 'Free play'}</h2>
            <p className="panel-subtitle">
              {progress} · {statusText}
              {track && mistakes > 0 ? ` · ${mistakes} retr${mistakes === 1 ? 'y' : 'ies'}` : ''}
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
          <PlayerBar
            name={nameFor(bottomColor)}
            rating={track && bottomColor === track.userColor ? 1518 : undefined}
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
            disabled={Boolean(clock.flagged) || Boolean(complete)}
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
          {track && (
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
          <button type="button" className="btn icon" aria-label="Restart" onClick={() => loadTrack(trackId)}>
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
        subtitle="Move-by-move Stockfish lesson"
        messages={coach.messages}
        phase={coach.phase}
        prompts={['Why this move?', 'What is the plan?', 'Common mistakes here']}
        onAsk={question =>
          coach.ask(question, {
            mode: 'training',
            fen,
            summary: track ? `${track.title}, ${progress.toLowerCase()}` : 'free play',
          })
        }
      />

      <section className="panel tracks-panel" aria-label="Personalized training tracks">
        <header className="panel-head">
          <div>
            <h2 className="panel-title">Personalized tracks</h2>
            <p className="panel-subtitle">Opening · defense · endgame</p>
          </div>
        </header>
        <div className="scroll-pane">
          {TRAINING_TRACKS.map(item => (
            <button
              key={item.id}
              type="button"
              className={`track-card${item.id === trackId ? ' active' : ''}`}
              onClick={() => loadTrack(item.id)}
            >
              <span className="eyebrow">{KIND_LABEL[item.kind]}</span>
              <strong>{item.title}</strong>
              <span>{item.subtitle}</span>
            </button>
          ))}
          <button
            type="button"
            className={`track-card${trackId === FREE_PLAY ? ' active' : ''}`}
            onClick={() => loadTrack(FREE_PLAY)}
          >
            <span className="eyebrow">Practice</span>
            <strong>Free play</strong>
            <span>Both sides · test time controls</span>
          </button>
        </div>
      </section>
    </div>
  )
}
