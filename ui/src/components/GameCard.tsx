import type { ReactNode } from 'react'
import type { GameStats, ListedGame } from '../data/games'

const RESULT_LABEL = { win: 'Win', loss: 'Loss', draw: 'Draw', unfinished: 'Unfinished' }

interface GameCardProps {
  game: ListedGame
  mine: GameStats
  theirs: GameStats
  /** The eval graph, under the numbers. */
  children?: ReactNode
}

/** What a game was, at a glance: result, ratings and your accuracy from the stored centipawn loss. */
export function GameCard({ game, mine, theirs, children }: GameCardProps) {
  const side = game.userColor === 'white' ? 'White' : 'Black'
  return (
    <section className="game-card" aria-label="Game summary">
      <div className="game-card-head">
        <span className={`result-pill ${game.result}`}>{RESULT_LABEL[game.result]}</span>
        <span className="muted small">
          as {side} · you {game.userElo ?? '—'} · opponent {game.opponentElo ?? '—'}
        </span>
      </div>
      {mine.evaluated > 0 ? (
        <dl className="game-card-stats">
          <div title={mine.mateSwings ? `Leaves out ${mine.mateSwings} swing(s) to or from mate.` : undefined}>
            <dt>Avg loss</dt>
            <dd>{mine.averageCpLoss ?? '—'} cp</dd>
          </div>
          <div title="Inaccuracies: 50 to 99 cp lost">
            <dt>Inaccur.</dt>
            <dd>{mine.inaccuracies}</dd>
          </div>
          <div title="Mistakes: 100 to 299 cp lost">
            <dt>Mistakes</dt>
            <dd>{mine.mistakes}</dd>
          </div>
          <div title="Blunders: 300 cp or more lost">
            <dt>Blunders</dt>
            <dd>{mine.blunders}</dd>
          </div>
        </dl>
      ) : (
        <p className="muted small">No stored centipawn loss for your moves.</p>
      )}
      {theirs.evaluated > 0 && (
        <p className="muted small game-card-note">
          Opponent: {theirs.mistakes} mistakes, {theirs.blunders} blunders
          {theirs.averageCpLoss !== null ? `, ${theirs.averageCpLoss} cp average loss` : ''}.
        </p>
      )}
      {children}
    </section>
  )
}
