import { Suspense, lazy, useEffect, useMemo, useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import {
  ArrowUpDown,
  Bot,
  CalendarDays,
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
  Folder,
  FolderOpen,
  Hourglass,
  Target,
  Timer,
  Zap,
  type LucideIcon,
} from 'lucide-react'
import { ChessBoard } from '../components/ChessBoard'
import { CoachPanel } from '../components/CoachPanel'
import { PlayerBar } from '../components/PlayerBar'
import { CATEGORY_LABELS, LIBRARY } from '../data/demo'
import type { GameCategory, LibraryGame } from '../data/types'
import { useCoach } from '../hooks/useCoach'
import { formatEval, replaySan } from '../lib/chess'
import { NODE_COLORS, buildGameGraph, type GraphNode } from '../lib/graph'
import { createMessage } from '../services/coach'

const PositionGraph = lazy(() => import('../components/PositionGraph'))

const CATEGORY_ORDER: GameCategory[] = ['rapid', 'blitz', 'bullet', 'daily', 'bot']
const CATEGORY_ICONS: Record<GameCategory, LucideIcon> = {
  rapid: Hourglass,
  blitz: Timer,
  bullet: Zap,
  daily: CalendarDays,
  bot: Bot,
}
const RESULT_LABEL = { win: 'Win', loss: 'Loss', draw: 'Draw' }

function reviewIntro(game: LibraryGame) {
  const { keyMoment } = game
  const loss = Math.max(0, keyMoment.evalBefore - keyMoment.evalAfter)
  return createMessage(
    'coach',
    `Key moment at move ${Math.ceil(keyMoment.ply / 2)}: you played ${keyMoment.played}; Stockfish preferred ` +
      `${keyMoment.best} (${loss} cp difference in this demo). ${keyMoment.explanation}`,
  )
}

export function GamesView({ active }: { active: boolean }) {
  const [openFolders, setOpenFolders] = useState<Set<GameCategory>>(() => new Set(['rapid']))
  const [gameId, setGameId] = useState(LIBRARY[0].id)
  const game = LIBRARY.find(item => item.id === gameId)!
  const plies = useMemo(() => replaySan(game.moves), [game])
  const graph = useMemo(() => buildGameGraph(game), [game])
  const [ply, setPly] = useState(game.keyMoment.ply - 1)
  const [showAlternative, setShowAlternative] = useState(true)
  const [orientation, setOrientation] = useState<'white' | 'black'>(game.userColor)
  const coach = useCoach([reviewIntro(game)])

  const atKeyRoot = ply === game.keyMoment.ply - 1
  const bestMove = useMemo(() => replaySan([game.keyMoment.best], plies[game.keyMoment.ply - 1].fenBefore)[0], [game, plies])
  const fen = ply === 0 ? plies[0].fenBefore : plies[ply - 1].fenAfter
  const lastMove = ply === 0 ? null : { from: plies[ply - 1].from, to: plies[ply - 1].to }
  const arrows =
    atKeyRoot && showAlternative
      ? [
          { startSquare: plies[ply].from, endSquare: plies[ply].to, color: NODE_COLORS.mistake },
          { startSquare: bestMove.from, endSquare: bestMove.to, color: NODE_COLORS.best },
        ]
      : []

  const selectGame = (next: LibraryGame) => {
    setGameId(next.id)
    setPly(next.keyMoment.ply - 1)
    setOrientation(next.userColor)
    setShowAlternative(true)
    coach.reset([reviewIntro(next)])
  }

  const goTo = (target: number) => setPly(Math.max(0, Math.min(plies.length, target)))

  useEffect(() => {
    if (!active) return
    const onKey = (event: KeyboardEvent) => {
      if (event.target instanceof HTMLInputElement) return
      if (event.key === 'ArrowLeft') setPly(value => Math.max(0, value - 1))
      if (event.key === 'ArrowRight') setPly(value => Math.min(plies.length, value + 1))
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [active, plies.length])

  const toggleFolder = (category: GameCategory) =>
    setOpenFolders(current => {
      const next = new Set(current)
      if (next.has(category)) next.delete(category)
      else next.add(category)
      return next
    })

  const selectNode = (node: GraphNode) => {
    goTo(node.ply)
    if (node.kind === 'best' || node.kind === 'mistake') {
      setPly(game.keyMoment.ply - 1)
      setShowAlternative(true)
    }
  }

  const selectedNodeId = `ply-${ply}`
  const selectedNode = graph.nodes.find(node => node.id === selectedNodeId)
  const userIsWhite = game.userColor === 'white'
  const topColor = orientation === 'white' ? 'black' : 'white'
  const playerFor = (color: 'white' | 'black') =>
    (color === 'white') === userIsWhite
      ? { name: 'Junior', rating: game.userElo }
      : { name: game.opponent, rating: game.opponentElo }
  const cpl = Math.max(0, game.keyMoment.evalBefore - game.keyMoment.evalAfter)

  return (
    <div className="view games-view">
      <section className="panel library-panel" aria-label="Game library">
        <header className="panel-head">
          <div>
            <h2 className="panel-title">My games</h2>
            <p className="panel-subtitle">Grouped by time control</p>
          </div>
        </header>
        <div className="scroll-pane">
          {CATEGORY_ORDER.map(category => {
            const games = LIBRARY.filter(item => item.category === category)
            const open = openFolders.has(category)
            const Icon = CATEGORY_ICONS[category]
            return (
              <div key={category} className="folder">
                <button
                  type="button"
                  className={`folder-toggle${open ? ' open' : ''}`}
                  aria-expanded={open}
                  onClick={() => toggleFolder(category)}
                >
                  {open ? <FolderOpen size={15} /> : <Folder size={15} />}
                  <Icon size={13} className="folder-kind" />
                  <span>{CATEGORY_LABELS[category]}</span>
                  <span className="count">{games.length}</span>
                </button>
                <AnimatePresence initial={false}>
                  {open && (
                    <motion.div
                      className="folder-body"
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: 'auto', opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      transition={{ duration: 0.18 }}
                    >
                      {category === 'bot' && <p className="folder-note">Bot games, labeled by time control.</p>}
                      {games.map(item => (
                        <button
                          key={item.id}
                          type="button"
                          className={`game-row${item.id === gameId ? ' active' : ''}`}
                          onClick={() => selectGame(item)}
                        >
                          <span className="game-meta">
                            {item.timeControl} · {item.playedOn}
                          </span>
                          <strong>{item.opening}</strong>
                          <span className="game-meta">
                            vs {item.opponent} · <span className={`result ${item.result}`}>{RESULT_LABEL[item.result]}</span>
                            {' '}as {item.userColor === 'white' ? 'White' : 'Black'}
                          </span>
                        </button>
                      ))}
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            )
          })}
        </div>
      </section>

      <section className="panel board-panel review-board" aria-label="Game review board">
        <header className="panel-head">
          <div>
            <h2 className="panel-title">
              {game.opening} <span className="eco">{game.eco}</span>
            </h2>
            <p className="panel-subtitle">
              {CATEGORY_LABELS[game.category]} · {game.timeControl} ·{' '}
              <span className={`result ${game.result}`}>{RESULT_LABEL[game.result]}</span>
            </p>
          </div>
          <button
            type="button"
            className="btn icon"
            aria-label="Flip board"
            onClick={() => setOrientation(value => (value === 'white' ? 'black' : 'white'))}
          >
            <ArrowUpDown size={14} />
          </button>
        </header>
        <div className="board-stack">
          <PlayerBar {...playerFor(topColor)} color={topColor} />
          <div className="board-frame">
            <ChessBoard
              id="review-board"
              fen={fen}
              orientation={orientation}
              interactive={false}
              lastMove={lastMove}
              arrows={arrows}
            />
          </div>
          <PlayerBar {...playerFor(orientation)} color={orientation} />
        </div>
        <div className="board-controls">
          <button type="button" className="btn icon" aria-label="First move" onClick={() => goTo(0)}>
            <ChevronsLeft size={15} />
          </button>
          <button type="button" className="btn icon" aria-label="Previous move" onClick={() => goTo(ply - 1)}>
            <ChevronLeft size={15} />
          </button>
          <span className="ply-label">{ply === 0 ? 'Start' : graph.nodes[ply].label}</span>
          <button type="button" className="btn icon" aria-label="Next move" onClick={() => goTo(ply + 1)}>
            <ChevronRight size={15} />
          </button>
          <button type="button" className="btn icon" aria-label="Last move" onClick={() => goTo(plies.length)}>
            <ChevronsRight size={15} />
          </button>
          <span className="spacer" />
          <button
            type="button"
            className={`btn${atKeyRoot ? ' active' : ''}`}
            onClick={() => {
              setPly(game.keyMoment.ply - 1)
              setShowAlternative(true)
            }}
          >
            <Target size={14} /> Key moment
          </button>
        </div>
        <ol className="move-list" aria-label="Moves">
          {plies.map(item => (
            <li key={item.ply}>
              {item.ply % 2 === 1 && <span className="move-number">{Math.ceil(item.ply / 2)}.</span>}
              <button
                type="button"
                className={`move${item.ply === ply ? ' current' : ''}${item.ply === game.keyMoment.ply ? ' key' : ''}`}
                onClick={() => goTo(item.ply)}
              >
                {item.san}
              </button>
            </li>
          ))}
        </ol>
      </section>

      <section className="panel graph-panel" aria-label="Position graph">
        <header className="panel-head">
          <div>
            <h2 className="panel-title">ChessGraph</h2>
            <p className="panel-subtitle">Played path and Stockfish alternative</p>
          </div>
        </header>
        {active ? (
          <Suspense fallback={<div className="graph-canvas graph-loading">Loading 3D graph…</div>}>
            <PositionGraph graph={graph} selectedId={selectedNodeId} onSelect={selectNode} />
          </Suspense>
        ) : (
          <div className="graph-canvas" />
        )}
        <div className="graph-info">
          <div className="legend">
            {(['user', 'opponent', 'mistake', 'best'] as const).map(kind => (
              <span key={kind}>
                <i style={{ background: NODE_COLORS[kind] }} />
                {{ user: 'Your move', opponent: 'Opponent', mistake: 'Key moment', best: 'Stockfish best' }[kind]}
              </span>
            ))}
          </div>
          <div className="key-card">
            <div>
              <span className="eyebrow">Key moment · demo evaluation</span>
              <strong>
                {game.keyMoment.played} <span className="vs">vs</span> {game.keyMoment.best}
              </strong>
              <span className="muted">
                {formatEval(game.keyMoment.evalBefore)} → {formatEval(game.keyMoment.evalAfter)} · {cpl} cp loss
              </span>
            </div>
            <span className="node-chip">{selectedNode?.label ?? 'Start'}</span>
          </div>
        </div>
      </section>

      <CoachPanel
        className="review-coach"
        title="Hermes review"
        subtitle="Graph move and engine explanation"
        messages={coach.messages}
        phase={coach.phase}
        prompts={['Why was this a mistake?', 'Show my usual plan', 'Similar positions']}
        onAsk={question =>
          coach.ask(question, {
            mode: 'review',
            fen,
            summary: `${game.opening}, ${ply === 0 ? 'start' : graph.nodes[ply].label}`,
          })
        }
      />
    </div>
  )
}
