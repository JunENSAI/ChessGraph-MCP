import { formatClock } from '../lib/clock'
import type { PieceLetter } from '../lib/material'

interface PlayerBarProps {
  name: string
  rating?: number
  color: 'white' | 'black'
  timeMs?: number
  active?: boolean
  flagged?: boolean
  /** Opponent pieces this player has captured. */
  captured?: PieceLetter[]
  /** Material lead in pawns, shown only when positive. */
  advantage?: number
  thinking?: boolean
}

const GLYPHS: Record<'white' | 'black', Record<PieceLetter, string>> = {
  // A player who is White captures black pieces, and the reverse.
  white: { q: '♛', r: '♜', b: '♝', n: '♞', p: '♟' },
  black: { q: '♕', r: '♖', b: '♗', n: '♘', p: '♙' },
}

export function PlayerBar({
  name,
  rating,
  color,
  timeMs,
  active = false,
  flagged = false,
  captured = [],
  advantage = 0,
  thinking = false,
}: PlayerBarProps) {
  const low = timeMs !== undefined && timeMs <= 20_000
  return (
    <div className={`player-bar${active ? ' to-move' : ''}`}>
      <div className="player-id">
        <span className={`player-swatch ${color}`} aria-hidden="true" />
        <div className="player-text">
          <div className="player-name">
            {name}
            {rating ? <span className="player-rating">{rating}</span> : null}
            {thinking && <span className="thinking-dots" aria-label="thinking" />}
          </div>
          <div className="captured" aria-label={`${color === 'white' ? 'White' : 'Black'} has captured ${captured.length} pieces`}>
            {captured.map((piece, index) => (
              <span key={`${piece}${index}`} className="captured-piece">
                {GLYPHS[color][piece]}
              </span>
            ))}
            {advantage > 0 && <span className="advantage">+{advantage}</span>}
          </div>
        </div>
      </div>
      {timeMs !== undefined && (
        <div
          className={`clock${active ? ' active' : ''}${low ? ' low' : ''}${flagged ? ' flagged' : ''}`}
          role="timer"
          aria-label={`${color === 'white' ? 'White' : 'Black'} clock`}
        >
          {flagged ? 'Time' : formatClock(timeMs)}
        </div>
      )}
    </div>
  )
}
