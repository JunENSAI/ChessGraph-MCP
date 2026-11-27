import { useEffect, useMemo, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import {
  ArrowUpDown,
  Bot,
  CalendarDays,
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
  Compass,
  Folder,
  FolderOpen,
  Hourglass,
  ListOrdered,
  MessageSquare,
  Sparkles,
  Target,
  Timer,
  Volume2,
  VolumeX,
  Zap,
  type LucideIcon,
} from 'lucide-react'
import { Chess } from 'chess.js'
import type { Arrow } from 'react-chessboard'
import { BoardStage } from '../components/BoardStage'
import { CoachPanel } from '../components/CoachPanel'
import { EvalGraph } from '../components/EvalGraph'
import { ExplorerPanel } from '../components/ExplorerPanel'
import { GameCard } from '../components/GameCard'
import { MoveTable } from '../components/MoveTable'
import { SidePanel } from '../components/SidePanel'
import {
  CATEGORY_LABELS,
  evalSeries,
  gameStats,
  keyMomentFromMoves,
  MATE_SWING_CP,
  openingFamilyOf,
  loadGameMoves,
  loadGamesPage,
  loadListedGame,
  type ListedGame,
  type StoredMove,
} from '../data/games'
import type { GameCategory, KeyMoment } from '../data/types'
import { useBoardKeys } from '../hooks/useBoardKeys'
import { useCoach } from '../hooks/useCoach'
import { usePlayerProfile } from '../hooks/usePlayerProfile'
import { usePositionEval } from '../hooks/usePositionEval'
import { replaySan, resultText, tryUci, type ReplayedPly } from '../lib/chess'
import { whiteEvalFromStored } from '../lib/eval'
import { glyphFor } from '../lib/notation'
import { isMuted, playSound, setMuted, soundFor } from '../lib/sound'
import { createMessage, loadThread, type CandidateLines } from '../services/coach'
import { firstMoveArrows } from '../lib/lines'
import { analyzeFen } from '../services/engine'

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
const ARROW = { played: '#ff7b72', best: '#b8f05a', preview: '#77a7ff' }

type ReviewTab = 'games' | 'moves' | 'coach' | 'explorer'

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

function wantsBoardLine(question: string): boolean {
  return /\b(play|replay|continu|line|mate|follow)\b/i.test(question)
}

function wait(ms: number): Promise<void> {
  return new Promise(resolve => {
    window.setTimeout(resolve, ms)
  })
}

function reviewIntro(game: ReviewedGame) {
  const key = game.keyMoment
  if (!key) {
    return createMessage('coach', 'No stored evaluation for this game, so there is no key moment to highlight.')
  }
  const engine = key.showEngine === false ? 'The engine move was not stored.' : `Stockfish preferred ${key.best}.`
  const loss = key.cpLoss == null ? '' : key.cpLoss >= MATE_SWING_CP ? ' The stored score swings to a mate.' : ` ${key.cpLoss} cp loss.`
  return createMessage('coach', `Key moment at move ${Math.ceil(key.ply / 2)}: you played ${key.played}. ${engine}${loss}`)
}

export function GamesView({ active }: { active: boolean }) {
  const keepThread = useRef(loadThread('review') !== null)
  const profile = usePlayerProfile()
  const username = profile.loaded ? profile.username : null
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
  const [extraGame, setExtraGame] = useState<ListedGame | null>(null)
  const [detail, setDetail] = useState<ReviewedGame | null>(null)
  const [detailError, setDetailError] = useState<string | null>(null)
  const [ply, setPly] = useState(0)
  const [line, setLine] = useState<{ startFen: string; moves: ReplayedPly[]; index: number } | null>(null)
  // The coach's candidate lines for the last answer, and the one being replayed.
  const [coachLines, setCoachLines] = useState<{ messageId: string; lines: CandidateLines } | null>(null)
  const [activeLine, setActiveLine] = useState<{ messageId: string; rank: number } | null>(null)
  const lineToken = useRef(0)
  const [showAlternative, setShowAlternative] = useState(true)
  const [orientation, setOrientation] = useState<'white' | 'black'>('white')
  const [tab, setTab] = useState<ReviewTab>('games')
  const [explorerArrow, setExplorerArrow] = useState<string | null>(null)
  const [muted, setMutedState] = useState(isMuted)
  const coach = useCoach('review', [])

  const listed = useMemo(() => {
    for (const category of CATEGORY_ORDER) {
      const found = folders[category].games.find(item => item.id === gameId)
      if (found) return found
    }
    return extraGame?.id === gameId ? extraGame : null
  }, [folders, gameId, extraGame])

  const plies = useMemo(() => (detail ? replaySan(detail.moves) : []), [detail])
  const gameFen = detail && ply > 0 && plies[ply - 1] ? plies[ply - 1].fenAfter : (plies[0]?.fenBefore ?? START_FEN)
  const fen = line ? (line.index === 0 ? line.startFen : (line.moves[line.index - 1]?.fenAfter ?? line.startFen)) : gameFen
  const storedMove = !line && detail && ply > 0 ? detail.stored[ply - 1] : undefined
  const storedEval = storedMove && storedMove.cpAfter !== null ? whiteEvalFromStored(storedMove.cpAfter, storedMove.mover) : null
  const evaluation = usePositionEval(fen, line ? null : detail ? storedEval : { whiteCp: 0, mate: null })

  useEffect(() => {
    if (profile.loaded) setLibraryError(null)
  }, [profile.loaded])

  const fetchPage = (category: GameCategory, offset: number) => {
    if (!username) return
    setFolders(current => ({ ...current, [category]: { ...current[category], loading: true, error: null } }))
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
        if (offset === 0 && category === 'rapid') setGameId(current => current ?? page.games[0]?.id ?? null)
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
    let live = true
    setDetailError(null)
    loadGameMoves(listed.id)
      .then(stored => {
        if (!live) return
        const moves = stored.map(move => move.san)
        const review: ReviewedGame = { ...listed, moves, stored, keyMoment: keyMomentFromMoves(stored, listed.userColor, replaySan(moves)) }
        setDetail(review)
        setLine(null)
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
        if (live) setDetailError(reason instanceof Error ? reason.message : 'This game could not be loaded.')
      })
    return () => {
      live = false
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
  const lastMove = line
    ? line.index === 0
      ? null
      : { from: line.moves[line.index - 1].from, to: line.moves[line.index - 1].to }
    : ply === 0 || !plies[ply - 1]
      ? null
      : { from: plies[ply - 1].from, to: plies[ply - 1].to }
  const arrows: Arrow[] = []
  if (!line && atKeyRoot && showAlternative && bestMove && plies[ply]) {
    arrows.push({ startSquare: plies[ply].from, endSquare: plies[ply].to, color: ARROW.played })
    arrows.push({ startSquare: bestMove.from, endSquare: bestMove.to, color: ARROW.best })
  }
  if (!line && coachLines && coachLines.lines.fen === fen) arrows.push(...firstMoveArrows(coachLines.lines))
  if (explorerArrow) arrows.push({ startSquare: explorerArrow.slice(0, 2), endSquare: explorerArrow.slice(2, 4), color: ARROW.preview })

  // Navigation works on whatever is shown: the game, or the better line.
  const current = line ? line.index : ply
  const last = line ? line.moves.length : plies.length
  const goTo = (target: number) => {
    const next = Math.max(0, Math.min(last, target))
    if (next === current) return
    const shown = line ? line.moves : plies
    if (next === current + 1 && shown[next - 1]) playSound(soundFor(shown[next - 1].san, resultText(shown[next - 1].fenAfter) !== null))
    if (line) setLine(value => (value ? { ...value, index: next } : value))
    else setPly(next)
  }
  const flip = () => setOrientation(value => (value === 'white' ? 'black' : 'white'))
  useBoardKeys(active, { index: current, last, go: goTo, flip })

  const toggleFolder = (category: GameCategory) => {
    setOpenFolders(value => {
      const next = new Set(value)
      if (next.has(category)) next.delete(category)
      else next.add(category)
      return next
    })
    const folder = folders[category]
    if (!folder.loading && folder.games.length === 0) fetchPage(category, 0)
  }

  const selectGame = (id: number) => {
    setGameId(id)
    setTab('moves')
  }

  const openGameById = (id: number) => {
    if (!username) return
    const known = CATEGORY_ORDER.some(category => folders[category].games.some(item => item.id === id))
    if (known) {
      selectGame(id)
      return
    }
    loadListedGame(id, username)
      .then(game => {
        setExtraGame(game)
        selectGame(game.id)
      })
      .catch((reason: unknown) => setDetailError(reason instanceof Error ? reason.message : 'This game could not be loaded.'))
  }

  const showLine = async (startFen: string, moves: string[]) => {
    const token = ++lineToken.current
    const played: ReplayedPly[] = []
    let position = startFen
    setLine({ startFen, moves: [], index: 0 })
    for (const uci of moves) {
      if (token !== lineToken.current) return
      const applied = tryUci(position, uci)
      if (!applied) break
      played.push({ ply: played.length + 1, san: applied.san, from: applied.from, to: applied.to, fenBefore: position, fenAfter: applied.fen })
      position = applied.fen
      setLine({ startFen, moves: [...played], index: played.length })
      playSound(soundFor(applied.san))
      await wait(360)
      if (resultText(position)) return
    }
  }

  const correction = () => {
    const key = detail?.keyMoment
    if (!key?.bestUci || !key.showEngine) return null
    const root = plies[key.ply - 1]
    const played = detail?.stored.find(move => move.ply === key.ply)
    if (!root || !played || played.uci === key.bestUci) return null
    return { fen: root.fenBefore, uci: key.bestUci, played: key.played, best: key.best }
  }

  const playContinuation = async (startFen: string, seed: string[]) => {
    const token = ++lineToken.current
    const played: ReplayedPly[] = []
    let position = startFen
    setLine({ startFen, moves: [], index: 0 })
    const push = async (uci: string) => {
      if (token !== lineToken.current) return false
      const applied = tryUci(position, uci)
      if (!applied) return false
      played.push({ ply: played.length + 1, san: applied.san, from: applied.from, to: applied.to, fenBefore: position, fenAfter: applied.fen })
      position = applied.fen
      setLine({ startFen, moves: [...played], index: played.length })
      playSound(soundFor(applied.san))
      await wait(280)
      return token === lineToken.current
    }
    for (const uci of seed) {
      if (!(await push(uci))) return
      if (resultText(position)) break
    }
    while (played.length < 20 && !resultText(position)) {
      try {
        const analysis = await analyzeFen(position, { limitType: 'time', limitValue: 400 })
        if (!(await push(analysis.uci))) return
      } catch {
        break
      }
    }
    const text = resultText(position)
    if (token === lineToken.current && text) coach.say(`${text} on the recommended line.`)
  }

  const playBetter = () => {
    const fix = correction()
    if (!fix) {
      coach.say('No different Stockfish move is stored for this mistake.')
      return
    }
    setPly(detail!.keyMoment!.ply - 1)
    setShowAlternative(true)
    coach.say(`You played ${fix.played}. Stockfish preferred ${fix.best}. Playing that line, not the game.`)
    void playContinuation(fix.fen, [fix.uci])
  }

  const toggleMute = () => {
    setMuted(!muted)
    setMutedState(!muted)
  }

  const game = detail
  const userIsWhite = game?.userColor === 'white'
  const seat = (color: 'white' | 'black') => {
    if (!game) return { name: color === 'white' ? 'White' : 'Black' }
    return (color === 'white') === userIsWhite
      ? { name: profile.username, rating: game.userElo ?? undefined }
      : { name: game.opponent, rating: game.opponentElo ?? undefined }
  }
  const moveLabel = line
    ? line.index === 0
      ? 'Line start'
      : `${line.index}. ${line.moves[line.index - 1]?.san ?? ''}`
    : ply === 0
      ? 'Start'
      : `${Math.ceil(ply / 2)}${ply % 2 === 1 ? '.' : '…'} ${plies[ply - 1]?.san ?? ''}${glyphFor(detail?.stored[ply - 1]?.cpLoss) ?? ''}`
  const lineResult = line ? resultText(fen) : null
  const review = useMemo(() => {
    if (!detail) return null
    const other = detail.userColor === 'white' ? 'black' : 'white'
    return {
      mine: gameStats(detail.stored, detail.userColor),
      theirs: gameStats(detail.stored, other),
      series: evalSeries(detail.stored, detail.userColor),
    }
  }, [detail])

  const controls = (
    <>
      <button type="button" className="btn icon" aria-label="First move" onClick={() => goTo(0)} disabled={current === 0}>
        <ChevronsLeft size={15} />
      </button>
      <button type="button" className="btn icon" aria-label="Previous move" onClick={() => goTo(current - 1)} disabled={current === 0}>
        <ChevronLeft size={15} />
      </button>
      <span className="ply-label">{moveLabel}</span>
      <button type="button" className="btn icon" aria-label="Next move" onClick={() => goTo(current + 1)} disabled={current >= last}>
        <ChevronRight size={15} />
      </button>
      <button type="button" className="btn icon" aria-label="Last move" onClick={() => goTo(last)} disabled={current >= last}>
        <ChevronsRight size={15} />
      </button>
      {line && (
        <button type="button" className="btn" onClick={() => setLine(null)}>
          Back to game
        </button>
      )}
      <span className="spacer" />
      <button type="button" className="btn icon" aria-label={muted ? 'Turn sound on' : 'Mute sound'} onClick={toggleMute}>
        {muted ? <VolumeX size={14} /> : <Volume2 size={14} />}
      </button>
      <button type="button" className="btn icon" aria-label="Flip board (F)" onClick={flip}>
        <ArrowUpDown size={14} />
      </button>
    </>
  )

  const gamesTab = (
    <div className="scroll-pane">
      {libraryError && <p className="folder-note">{libraryError}</p>}
      {!profile.loaded && <p className="folder-note">Reading your account…</p>}
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
              <span className="count">{folder.settled ? `${folder.games.length}${folder.hasMore ? '+' : ''}` : '…'}</span>
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
                  {folder.settled && !folder.error && folder.games.length === 0 && <p className="folder-note">No games stored.</p>}
                  {folder.games.map(item => (
                    <button
                      key={item.id}
                      type="button"
                      className={`game-row ${item.result}${item.id === gameId ? ' active' : ''}`}
                      onClick={() => selectGame(item.id)}
                    >
                      <span className="game-meta">
                        {item.timeControl} · {item.playedOn}
                      </span>
                      <strong>{openingFamilyOf(item.opening)}</strong>
                      {item.opening.includes(':') && <span className="game-meta variation">{item.opening.slice(item.opening.indexOf(':') + 1).trim()}</span>}
                      <span className="game-meta">
                        vs {item.opponent} · <span className={`result ${item.result}`}>{RESULT_LABEL[item.result]}</span> as{' '}
                        {item.userColor === 'white' ? 'White' : 'Black'}
                      </span>
                    </button>
                  ))}
                  {folder.hasMore && (
                    <button type="button" className="folder-more" disabled={folder.loading} onClick={() => fetchPage(category, folder.nextOffset)}>
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
  )

  const movesTab = (
    <div className="moves-tab">
      {game && review && (
        <GameCard game={game} mine={review.mine} theirs={review.theirs}>
          <EvalGraph
            points={review.series}
            sans={plies.map(item => item.san)}
            current={line ? -1 : ply}
            keyPly={game.keyMoment?.ply ?? null}
            onSelect={next => {
              setLine(null)
              setPly(next)
            }}
          />
        </GameCard>
      )}
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
                  : game.keyMoment.cpLoss >= MATE_SWING_CP
                    ? 'Stored score swings to a mate'
                    : `${game.keyMoment.cpLoss} cp loss`}
              </span>
            </>
          ) : (
            <strong>{game ? 'No stored evaluation for this game.' : 'Choose a game.'}</strong>
          )}
        </div>
        <div className="key-actions">
          {game?.keyMoment && (
            <button
              type="button"
              className={`btn${atKeyRoot && !line ? ' active' : ''}`}
              onClick={() => {
                setLine(null)
                setPly(game.keyMoment!.ply - 1)
                setShowAlternative(true)
              }}
            >
              <Target size={14} /> Go there
            </button>
          )}
          <button type="button" className="btn" disabled={!game || coach.phase !== 'idle'} onClick={playBetter}>
            <Sparkles size={14} /> Better move
          </button>
        </div>
      </div>
      {line ? (
        <>
          <p className="line-note">
            Stockfish line from move {Math.ceil((game?.keyMoment?.ply ?? 1) / 2)} · not the game{lineResult ? ` · ${lineResult}` : ''}
          </p>
          <MoveTable
            plies={line.moves}
            current={line.index}
            startFen={line.startFen}
            onSelect={index => setLine(value => (value ? { ...value, index } : value))}
          />
        </>
      ) : (
        <MoveTable
          plies={plies.map((item, index) => ({ san: item.san, cpLoss: detail?.stored[index]?.cpLoss }))}
          current={ply}
          onSelect={setPly}
          keyPly={game?.keyMoment?.ply ?? null}
          empty={detailError ?? 'Choose a game in the Games tab.'}
        />
      )}
      <p className="muted small keys-note">← → browse · Home/End jump · F flips · ?! ? ?? from stored centipawn loss</p>
    </div>
  )

  const coachTab = (
    <CoachPanel
      embedded
      className="review-coach"
      title="Game review"
      subtitle="Evaluation, the move, and a short reason"
      messages={coach.messages}
      phase={coach.phase}
      trace={coach.trace}
      mode={coach.mode}
      prompts={['Why was this a mistake?', 'Why did I lose?', 'What should I play here?']}
      activeLine={line ? activeLine : null}
      onLine={(message, picked) => {
        if (!message.lines) return
        setCoachLines({ messageId: message.id, lines: message.lines })
        setActiveLine({ messageId: message.id, rank: picked.rank })
        void showLine(message.lines.fen, picked.uci)
      }}
      onAsk={question => {
        const fromFen = fen
        void coach
          .ask(
            question,
            {
              mode: 'review',
              fen: fromFen,
              summary: game ? `${game.opening}, ${moveLabel}` : 'game',
              gameId: game?.id,
            },
            {
              onLines: (lines, messageId) => {
                setCoachLines({ messageId, lines })
                setActiveLine(null)
              },
            },
          )
          .then(reply => {
            const fix = correction()
            if (wantsBoardLine(question) && fix) {
              setPly(detail!.keyMoment!.ply - 1)
              void playContinuation(fix.fen, [fix.uci])
              return
            }
            if (reply?.lines) return // the chips replay a line on demand
            const seed = reply?.play ?? []
            if (seed.length > 0) void showLine(fromFen, seed)
          })
      }}
    />
  )

  return (
    <div className="view play-layout">
      <BoardStage
        id="review-board"
        fen={fen}
        orientation={orientation}
        white={seat('white')}
        black={seat('black')}
        evaluation={evaluation}
        interactive={false}
        lastMove={lastMove}
        arrows={arrows}
        overlay={lineResult ? <p>{lineResult}</p> : null}
        controls={controls}
        header={
          <>
            <h2 className="panel-title">
              {game?.opening ?? 'Game'} {game && <span className="eco">{game.eco}</span>}
            </h2>
            <p className="panel-subtitle">
              {detailError
                ? detailError
                : line
                  ? `Better line · ${line.moves[0]?.san ?? '…'} instead of your move · ${line.index} of ${line.moves.length}`
                  : game
                    ? `${CATEGORY_LABELS[game.category]} · ${game.timeControl} · ${game.playedOn} · ${RESULT_LABEL[game.result]} as ${game.userColor === 'white' ? 'White' : 'Black'}`
                    : 'Choose a game'}
            </p>
          </>
        }
      />
      <SidePanel<ReviewTab>
        label="Review"
        active={tab}
        onChange={setTab}
        tabs={[
          { id: 'games', label: 'Games', icon: FolderOpen, content: gamesTab },
          { id: 'moves', label: 'Moves', icon: ListOrdered, content: movesTab },
          { id: 'coach', label: 'Coach', icon: MessageSquare, content: coachTab },
          {
            id: 'explorer',
            label: 'Explorer',
            icon: Compass,
            content: (
              <ExplorerPanel fen={fen} active={active && tab === 'explorer'} onPreview={setExplorerArrow} onOpenGame={openGameById} />
            ),
          },
        ]}
      />
    </div>
  )
}
