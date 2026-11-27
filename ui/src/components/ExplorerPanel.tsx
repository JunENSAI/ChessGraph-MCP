import { useEffect, useState } from 'react'
import { BookOpen, Cpu } from 'lucide-react'
import { explorerRows, formatScore, type ExplorerJson } from '../lib/explorer'
import { loadExplorer } from '../services/explorer'
import { ScoreBar } from './ScoreBar'

interface ExplorerPanelProps {
  fen: string
  /** Only fetch while the tab is visible. */
  active: boolean
  /** Hovering a row previews its move as an arrow on the board. */
  onPreview?: (uci: string | null) => void
  onOpenGame?: (gameId: number) => void
}

const PHASE: Record<string, string> = { opening: 'Opening', middlegame: 'Middlegame', endgame: 'Endgame' }

/** Book moves, your moves and your opponents' moves from this position, read from the Neo4j graph. */
export function ExplorerPanel({ fen, active, onPreview, onOpenGame }: ExplorerPanelProps) {
  const [state, setState] = useState<{ fen: string; data: ExplorerJson | null; error: string | null } | null>(null)

  useEffect(() => {
    if (!active) return
    let live = true
    // A short wait keeps fast arrow-key browsing from sending one request per ply.
    const timer = window.setTimeout(() => {
      loadExplorer(fen)
        .then(data => live && setState({ fen, data, error: null }))
        .catch((error: unknown) =>
          live && setState({ fen, data: null, error: error instanceof Error ? error.message : 'The graph did not answer.' }),
        )
    }, 120)
    return () => {
      live = false
      window.clearTimeout(timer)
    }
  }, [fen, active])

  const current = state?.fen === fen ? state : null
  if (!current) return <p className="muted small explorer-note">Reading the graph…</p>
  if (current.error) return <p className="muted small explorer-note">Graph evidence is missing: {current.error}</p>
  const data = current.data!
  const rows = explorerRows(data)
  const context = data.context
  const opening = context?.openings?.[0]
  const games = data.games

  return (
    <div className="explorer">
      <div className="explorer-summary">
        <div>
          <span className="eyebrow">Position</span>
          <strong>
            {opening?.opening_name ?? context?.opening_families?.[0] ?? (context ? 'Unnamed position' : 'Not in your games or the book')}
          </strong>
          <span className="muted small">
            {context?.position?.phase ? PHASE[context.position.phase] : '—'}
            {opening?.eco_code ? ` · ${opening.eco_code}` : ''}
            {context?.position?.eval_cp != null
              ? ` · stored eval ${context.position.eval_cp > 0 ? '+' : ''}${(context.position.eval_cp / 100).toFixed(2)} (side to move, ${context.position.eval_samples} sample${context.position.eval_samples === 1 ? '' : 's'})`
              : ''}
          </span>
        </div>
        <div className="explorer-record">
          <span className="eyebrow">Your games here</span>
          <strong>{games.total_games}</strong>
          {games.total_games > 0 && (
            <>
              <span className="small">
                {games.owner_wins}W {games.owner_draws}D {games.owner_losses}L
              </span>
              <ScoreBar wins={games.owner_wins} draws={games.owner_draws} losses={games.owner_losses} label="Your games here" />
            </>
          )}
        </div>
      </div>

      {rows.length === 0 ? (
        <p className="muted small explorer-note">No book move and no stored game continues from here.</p>
      ) : (
        <table className="explorer-table">
          <thead>
            <tr>
              <th scope="col">Move</th>
              <th scope="col" title="You: games and your score">You</th>
              <th scope="col" title="Opponents: games and their score">Opponents</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(row => (
              <tr key={row.uci} onMouseEnter={() => onPreview?.(row.uci)} onMouseLeave={() => onPreview?.(null)}>
                <th scope="row">
                  <span className="explorer-move">{row.san}</span>
                  {row.book && (
                    <span className="tag book" title={`Book move in ${row.ecoCount} ECO line${row.ecoCount === 1 ? '' : 's'}`}>
                      <BookOpen size={11} /> book
                    </span>
                  )}
                  {row.engineBest && (
                    <span className="tag engine" title="Most frequent stored Stockfish best move">
                      <Cpu size={11} /> best
                    </span>
                  )}
                </th>
                <td>
                  {row.you ? (
                    <>
                      <strong>{row.you.games}</strong> · {formatScore(row.you.scorePct)}
                      {row.you.avgCpLoss != null && <span className="muted"> · {row.you.avgCpLoss} cp</span>}
                    </>
                  ) : (
                    <span className="muted">—</span>
                  )}
                </td>
                <td>
                  {row.opponents ? (
                    <>
                      <strong>{row.opponents.games}</strong> · {formatScore(row.opponents.scorePct)}
                    </>
                  ) : (
                    <span className="muted">—</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {games.games.length > 0 && (
        <div className="explorer-games">
          <span className="eyebrow">Recent games through this position</span>
          {games.games.map(visit => (
            <button
              key={visit.game.game_id}
              type="button"
              className="explorer-game"
              disabled={!onOpenGame}
              onClick={() => onOpenGame?.(visit.game.game_id)}
            >
              <span>{visit.game.played_date ?? ''}</span>
              <span className="explorer-game-name">{visit.game.opening_name ?? 'Game'}</span>
              <span className={`result ${visit.game.user_outcome ?? ''}`}>{visit.game.user_outcome ?? ''}</span>
            </button>
          ))}
        </div>
      )}
      <p className="muted small explorer-note">Scores are from the side that played the move. Source: Neo4j graph.</p>
    </div>
  )
}
