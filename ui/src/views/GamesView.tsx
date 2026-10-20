import { Suspense, lazy, useEffect, useMemo, useRef, useState } from 'react'
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
import { Chess } from 'chess.js'
import { ChessBoard } from '../components/ChessBoard'
import { CoachPanel } from '../components/CoachPanel'
import { EvalBar } from '../components/EvalBar'
import { PlayerBar } from '../components/PlayerBar'
import { CATEGORY_LABELS } from '../data/demo'
import {
  keyMomentFromMoves,
  loadGameMoves,
  loadGamesPage,
  loadPlayerName,
  type ListedGame,
  type StoredMove,
} from '../data/games'
import type { GameCategory, KeyMoment } from '../data/types'
import { useCoach } from '../hooks/useCoach'
import { usePositionEval } from '../hooks/usePositionEval'
import { replaySan } from '../lib/chess'
import { whiteEvalFromStored } from '../lib/eval'
import { NODE_COLORS, buildGameGraph, type GraphNode } from '../lib/graph'
import { createMessage, loadThread } from '../services/coach'

const PositionGraph = lazy(() => import('../components/PositionGraph'))

const START_FEN = new Chess().fen()
const CATEGORY_ORDER: GameCategory[] = ['rapid', 'blitz', 'bullet', 'daily', 'bot']
const CATEGORY_ICONS: Record<GameCategory, LucideIcon> = {
  rapid: Hourglass,
  blitz: Timer,
  bullet: Zap,
  daily: CalendarDays,
  bot: Bot,
}
const RESULT_LABEL = { win: 'Win', loss: 'Loss', draw: 'Draw', unfinished: 'Unfinished' }

interface FolderPage {
  games: ListedGame[]
  nextOffset: number
  hasMore: boolean
  loading: boolean
  settled: boolean
  error: string | null
}

interface ReviewedGame extends ListedGame {
  moves: string[]
  stored: StoredMove[]
  keyMoment: KeyMoment | null
}

const emptyFolder = (): FolderPage => ({
  games: [],
  nextOffset: 0,
  hasMore: false,
  loading: false,
  settled: false,
  error: null,
})

function reviewIntro(game: ReviewedGame) {
  const key = game.keyMoment
  if (!key) {
    return createMessage('coach', 'No stored evaluation for this game, so there is no key moment to highlight.')
  }
  const engine =
    key.showEngine === false ? 'The engine move was not stored.' : `Stockfish preferred ${key.best}.`
  const loss =
    key.cpLoss == null ? '' : key.cpLoss >= 9000 ? ' The stored score is a mate.' : ` ${key.cpLoss} cp loss.`
  return createMessage(
    'coach',
    `Key moment at move ${Math.ceil(key.ply / 2)}: you played ${key.played}. ${engine}${loss}`,
  )
}

export function GamesView({ active }: { active: boolean }) {
  const keepThread = useRef(loadThread('review') !== null)
  const [username, setUsername] = useState<string | null>(null)
  const [libraryError, setLibraryError] = useState<string | null>(null)
  const [openFolders, setOpenFolders] = useState<Set<GameCategory>>(() => new Set(['rapid']))
  const [folders, setFolders] = useState<Record<GameCategory, FolderPage>>(() => ({
    rapid: emptyFolder(),
    blitz: emptyFolder(),
    bullet: emptyFolder(),
    daily: emptyFolder(),
    bot: emptyFolder(),
  }))
  const [gameId, setGameId] = useState<number | null>(null)
  const [detail, setDetail] = useState<ReviewedGame | null>(null)
  const [detailError, setDetailError] = useState<string | null>(null)
  const [ply, setPly] = useState(0)
  const [showAlternative, setShowAlternative] = useState(true)
  const [orientation, setOrientation] = useState<'white' | 'black'>('white')
  const coach = useCoach('review', [])

  const listed = useMemo(() => {
    for (const category of CATEGORY_ORDER) {
      const found = folders[category].games.find(item => item.id === gameId)
      if (found) return found
    }
    return null
  }, [folders, gameId])

  const plies = useMemo(() => (detail ? replaySan(detail.moves) : []), [detail])
  const graph = useMemo(
    () => (detail ? buildGameGraph({ moves: detail.moves, userColor: detail.userColor, keyMoment: detail.keyMoment }) : null),
    [detail],
  )
  const fen = detail && ply > 0 && plies[ply - 1] ? plies[ply - 1].fenAfter : plies[0]?.fenBefore ?? START_FEN
  const storedMove = detail && ply > 0 ? detail.stored[ply - 1] : undefined
  const storedEval =
    storedMove && storedMove.cpAfter !== null ? whiteEvalFromStored(storedMove.cpAfter, storedMove.mover) : null
  const evaluation = usePositionEval(fen, detail ? storedEval : { whiteCp: 0, mate: null })

  useEffect(() => {
    let activeLoad = true
    loadPlayerName()
      .then(name => {
        if (activeLoad) setUsername(name)
      })
      .catch((reason: unknown) => {
        if (activeLoad) setLibraryError(reason instanceof Error ? reason.message : 'Games could not be loaded.')
      })
    return () => {
      activeLoad = false
    }
  }, [])

  const fetchPage = (category: GameCategory, offset: number) => {
    if (!username) return
    setFolders(current => ({
      ...current,
      [category]: { ...current[category], loading: true, error: null },
    }))
    loadGamesPage(username, category, offset)
      .then(page => {
        setFolders(current => {
          const previous = offset === 0 ? [] : current[category].games
          return {
            ...current,
            [category]: {
              games: [...previous, ...page.games],
              nextOffset: offset + page.rawCount,
              hasMore: page.hasMore,
              loading: false,
              settled: true,
              error: null,
            },
          }
        })
        if (offset === 0 && category === 'rapid') {
          setGameId(current => current ?? page.games[0]?.id ?? null)
        }
      })
      .catch((reason: unknown) => {
        setFolders(current => ({
          ...current,
            [category]: {
              ...current[category],
              loading: false,
              settled: true,
              error: reason instanceof Error ? reason.message : 'This time control could not be loaded.',
            },
        }))
      })
  }

  useEffect(() => {
    if (!username) return
    fetchPage('rapid', 0)
    // Reload only when the account name arrives.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [username])

  useEffect(() => {
    if (!listed) return
    let activeLoad = true
    setDetailError(null)
    loadGameMoves(listed.id)
      .then(stored => {
        if (!activeLoad) return
        const moves = stored.map(move => move.san)
        const replay = replaySan(moves)
        const review: ReviewedGame = {
          ...listed,
          moves,
          stored,
          keyMoment: keyMomentFromMoves(stored, listed.userColor, replay),
        }
        setDetail(review)
        setPly(review.keyMoment ? Math.max(0, review.keyMoment.ply - 1) : 0)
        setOrientation(review.userColor)
        setShowAlternative(true)
        if (keepThread.current) {
          keepThread.current = false
          return
        }
        coach.reset([reviewIntro(review)])
      })
      .catch((reason: unknown) => {
        if (activeLoad) setDetailError(reason instanceof Error ? reason.message : 'This game could not be loaded.')
      })
    return () => {
      activeLoad = false
    }
    // coach.reset is stable. Reloading follows the selected game.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [listed?.id])

  const atKeyRoot = Boolean(detail?.keyMoment && ply === detail.keyMoment.ply - 1 && detail.keyMoment.showEngine !== false)
  const bestMove = useMemo(() => {
    if (!detail?.keyMoment || detail.keyMoment.showEngine === false) return null
    const root = plies[detail.keyMoment.ply - 1]
    if (!root) return null
    try {
      return replaySan([detail.keyMoment.best], root.fenBefore)[0]
    } catch {
      return null
    }
  }, [detail, plies])
  const lastMove = ply === 0 || !plies[ply - 1] ? null : { from: plies[ply - 1].from, to: plies[ply - 1].to }
  const arrows =
    atKeyRoot && showAlternative && bestMove && plies[ply]
      ? [
          { startSquare: plies[ply].from, endSquare: plies[ply].to, color: NODE_COLORS.mistake },
          { startSquare: bestMove.from, endSquare: bestMove.to, color: NODE_COLORS.best },
        ]
      : []

  const goTo = (target: number) => setPly(Math.max(0, Math.min(plies.length, target)))

  useEffect(() => {
    if (!active) return
    const onKey = (event: KeyboardEvent) => {
      if (event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement) return
      if (event.target instanceof HTMLSelectElement) return
      if (event.key === 'ArrowLeft') setPly(value => Math.max(0, value - 1))
      if (event.key === 'ArrowRight') setPly(value => Math.min(plies.length, value + 1))
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [active, plies.length])

  const toggleFolder = (category: GameCategory) => {
    setOpenFolders(current => {
      const next = new Set(current)
      if (next.has(category)) next.delete(category)
      else next.add(category)
      return next
    })
    const folder = folders[category]
    if (!folder.loading && folder.games.length === 0) fetchPage(category, 0)
  }

  const selectNode = (node: GraphNode) => {
    goTo(node.ply)
    if (detail?.keyMoment && (node.kind === 'best' || node.kind === 'mistake')) {
      setPly(detail.keyMoment.ply - 1)
      setShowAlternative(true)
    }
  }

  const game = detail
  const selectedNodeId = `ply-${ply}`
  const selectedNode = graph?.nodes.find(node => node.id === selectedNodeId)
  const userIsWhite = game?.userColor === 'white'
  const topColor = orientation === 'white' ? 'black' : 'white'
  const playerFor = (color: 'white' | 'black') => {
    if (!game) return { name: color === 'white' ? 'White' : 'Black' }
    return (color === 'white') === userIsWhite
      ? { name: 'Junior', rating: game.userElo ?? undefined }
      : { name: game.opponent, rating: game.opponentElo ?? undefined }
  }
  const moveLabel = ply === 0 ? 'Start' : graph?.nodes[ply]?.label ?? `Move ${ply}`

  return (
    <div className="view games-view">
      <section className="panel library-panel" aria-label="Game library">
        <header className="panel-head">
          <div>
            <h2 className="panel-title">My games</h2>
            <p className="panel-subtitle">
              {libraryError ?? 'Your games, grouped by time control'}
            </p>
          </div>
        </header>
        <div className="scroll-pane">
          {CATEGORY_ORDER.map(category => {
            const folder = folders[category]
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
                  <span className="count">
                    {folder.settled ? `${folder.games.length}${folder.hasMore ? '+' : ''}` : '…'}
                  </span>
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
                      {!folder.settled && <p className="folder-note">Loading games…</p>}
                      {folder.error && <p className="folder-note">{folder.error}</p>}
                      {folder.settled && !folder.error && folder.games.length === 0 && (
                        <p className="folder-note">No games stored.</p>
                      )}
                      {folder.games.map(item => (
                        <button
                          key={item.id}
                          type="button"
                          className={`game-row${item.id === gameId ? ' active' : ''}`}
                          onClick={() => setGameId(item.id)}
                        >
                          <span className="game-meta">
                            {item.timeControl} · {item.playedOn}
                          </span>
                          <strong>{item.opening}</strong>
                          <span className="game-meta">
                            vs {item.opponent} ·{' '}
                            <span className={`result ${item.result}`}>{RESULT_LABEL[item.result]}</span> as{' '}
                            {item.userColor === 'white' ? 'White' : 'Black'}
                          </span>
                        </button>
                      ))}
                      {folder.hasMore && (
                        <button
                          type="button"
                          className="folder-more"
                          disabled={folder.loading}
                          onClick={() => fetchPage(category, folder.nextOffset)}
                        >
                          {folder.loading ? 'Loading…' : 'Load more'}
                        </button>
                      )}
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
              {game?.opening ?? 'Game'} {game && <span className="eco">{game.eco}</span>}
            </h2>
            <p className="panel-subtitle">
              {detailError
                ? detailError
                : game
                  ? `${CATEGORY_LABELS[game.category]} · ${game.timeControl} · ${RESULT_LABEL[game.result]}`
                  : 'Choose a game'}
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
          <div className="board-and-eval">
            <EvalBar orientation={orientation} evaluation={evaluation.evaluation} pending={evaluation.pending} />
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
          <span className="ply-label">{moveLabel}</span>
          <button type="button" className="btn icon" aria-label="Next move" onClick={() => goTo(ply + 1)}>
            <ChevronRight size={15} />
          </button>
          <button type="button" className="btn icon" aria-label="Last move" onClick={() => goTo(plies.length)}>
            <ChevronsRight size={15} />
          </button>
          <span className="spacer" />
          {game?.keyMoment && (
            <button
              type="button"
              className={`btn${atKeyRoot ? ' active' : ''}`}
              onClick={() => {
                setPly(game.keyMoment!.ply - 1)
                setShowAlternative(true)
              }}
            >
              <Target size={14} /> Key moment
            </button>
          )}
        </div>
        <ol className="move-list" aria-label="Moves">
          {plies.map(item => (
            <li key={item.ply}>
              {item.ply % 2 === 1 && <span className="move-number">{Math.ceil(item.ply / 2)}.</span>}
              <button
                type="button"
                className={`move${item.ply === ply ? ' current' : ''}${item.ply === game?.keyMoment?.ply ? ' key' : ''}`}
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
        {active && graph ? (
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
              <span className="eyebrow">Key moment</span>
              {game?.keyMoment ? (
                <>
                  <strong>
                    {game.keyMoment.played}
                    {game.keyMoment.showEngine !== false && (
                      <>
                        {' '}
                        <span className="vs">vs</span> {game.keyMoment.best}
                      </>
                    )}
                  </strong>
                  <span className="muted">
                    {game.keyMoment.cpLoss == null
                      ? game.keyMoment.explanation
                      : game.keyMoment.cpLoss >= 9000
                        ? 'Stored score is a mate'
                        : `${game.keyMoment.cpLoss} cp loss`}
                  </span>
                </>
              ) : (
                <strong>No stored evaluation for this game.</strong>
              )}
            </div>
            <span className="node-chip">{selectedNode?.label ?? 'Start'}</span>
          </div>
        </div>
      </section>

      <CoachPanel
        className="review-coach"
        title="Hermes review"
        subtitle="Evaluation, the move, and a short reason"
        messages={coach.messages}
        phase={coach.phase}
        prompts={['Why was this a mistake?', 'Show my usual plan', 'Similar positions']}
        onAsk={question =>
          coach.ask(question, {
            mode: 'review',
            fen,
            summary: game ? `${game.opening}, ${moveLabel}` : 'game',
          })
        }
      />
    </div>
  )
}
