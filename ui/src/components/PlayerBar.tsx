import { formatClock } from '../lib/clock'

interface PlayerBarProps {
  name: string
  rating?: number
  color: 'white' | 'black'
  timeMs?: number
  active?: boolean
  flagged?: boolean
}

export function PlayerBar({ name, rating, color, timeMs, active = false, flagged = false }: PlayerBarProps) {
  const low = timeMs !== undefined && timeMs <= 20_000
  return (
    <div className="player-bar">
      <div className="player-id">
        <span className={`player-swatch ${color}`} aria-hidden="true" />
        <div>
          <div className="player-name">{name}</div>
          <div className="player-meta">
            {rating ? `${rating} · ` : ''}
            {color === 'white' ? 'White' : 'Black'}
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
