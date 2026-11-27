import { resultShares } from '../data/recap'

interface ScoreBarProps {
  wins: number
  draws: number
  losses: number
  /** Whose results these are, for the screen-reader label. */
  label?: string
}

const SEGMENTS = [
  { key: 'wins', name: 'Wins', className: 'win' },
  { key: 'draws', name: 'Draws', className: 'draw' },
  { key: 'losses', name: 'Losses', className: 'loss' },
] as const

/** Wins, draws and losses as one 100% bar. Hover a segment for its count. */
export function ScoreBar({ wins, draws, losses, label }: ScoreBarProps) {
  const counts = { wins, draws, losses }
  const shares = resultShares(counts)
  const total = wins + draws + losses
  const summary = `${label ? `${label}: ` : ''}${wins} wins, ${draws} draws, ${losses} losses`
  if (total === 0) return <div className="score-bar empty" role="img" aria-label={`${summary}: no games`} />
  return (
    <div className="score-bar" role="img" aria-label={summary}>
      {SEGMENTS.filter(segment => counts[segment.key] > 0).map(segment => (
        <span
          key={segment.key}
          className={`score-segment ${segment.className}`}
          style={{ flexGrow: counts[segment.key] }}
          title={`${segment.name}: ${counts[segment.key]} (${shares[segment.key]}%)`}
        />
      ))}
    </div>
  )
}

/** The legend for every score bar on a page. */
export function ScoreLegend() {
  return (
    <ul className="score-legend" aria-label="Legend">
      {SEGMENTS.map(segment => (
        <li key={segment.key}>
          <span className={`score-swatch ${segment.className}`} />
          {segment.name}
        </li>
      ))}
    </ul>
  )
}
