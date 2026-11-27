import { useRef, useState } from 'react'
import { EVAL_CLAMP_PAWNS, MATE_SWING_CP, type EvalPoint } from '../data/games'
import { SEVERITY_CP } from '../lib/notation'

interface EvalGraphProps {
  points: EvalPoint[]
  /** SAN of each ply, index = ply - 1. */
  sans: string[]
  /** The ply shown on the board (0 = start). */
  current: number
  keyPly: number | null
  onSelect: (ply: number) => void
}

const WIDTH = 320
const HEIGHT = 92
const PAD_X = 6
const PAD_Y = 6
const MID = HEIGHT / 2

function moveName(ply: number, san: string | undefined): string {
  return `${Math.ceil(ply / 2)}${ply % 2 === 1 ? '.' : '…'} ${san ?? ''}`.trim()
}

function evalLabel(point: EvalPoint): string {
  if (point.pawns === null) return 'not evaluated'
  if (point.mate) return point.pawns > 0 ? 'mate for White' : 'mate for Black'
  return `${point.pawns > 0 ? '+' : ''}${point.pawns.toFixed(1)}`
}

/**
 * The stored evaluation after every ply, from White's side, clamped at five pawns.
 * Above the middle line White is better. Dots mark your mistakes and blunders, the ring the key moment.
 * Click (or hover, then click) to jump to that ply.
 */
export function EvalGraph({ points, sans, current, keyPly, onSelect }: EvalGraphProps) {
  const ref = useRef<SVGSVGElement>(null)
  const [hover, setHover] = useState<EvalPoint | null>(null)
  const last = points.at(-1)?.ply ?? 0
  if (points.length < 2 || points.every(point => point.pawns === null)) {
    return <p className="muted small eval-graph-empty">No stored evaluation for this game.</p>
  }
  const first = points[0].ply
  const span = Math.max(1, last - first)
  const x = (ply: number) => PAD_X + ((ply - first) / span) * (WIDTH - PAD_X * 2)
  const y = (pawns: number) => MID - (pawns / EVAL_CLAMP_PAWNS) * (MID - PAD_Y)

  // One path per run of evaluated plies, so a gap stays a gap.
  const runs: EvalPoint[][] = []
  for (const point of points) {
    if (point.pawns === null) runs.push([])
    else if (runs.length === 0) runs.push([point])
    else runs[runs.length - 1].push(point)
  }
  const segments = runs.filter(run => run.length > 0)
  const line = segments.map(run => run.map((point, index) => `${index ? 'L' : 'M'}${x(point.ply).toFixed(1)},${y(point.pawns!).toFixed(1)}`).join('')).join('')
  const area = segments
    .map(run => {
      const top = run.map(point => `L${x(point.ply).toFixed(1)},${y(point.pawns!).toFixed(1)}`).join('')
      return `M${x(run[0].ply).toFixed(1)},${MID}${top}L${x(run[run.length - 1].ply).toFixed(1)},${MID}Z`
    })
    .join('')

  const errors = points.filter(point => point.mine && point.pawns !== null && (point.cpLoss ?? 0) >= SEVERITY_CP.mistake)
  const keyPoint = keyPly === null ? null : points.find(point => point.ply === keyPly && point.pawns !== null) ?? null

  const plyAt = (event: { clientX: number }): EvalPoint | null => {
    const box = ref.current?.getBoundingClientRect()
    if (!box || box.width === 0) return null
    const local = ((event.clientX - box.left) / box.width) * WIDTH
    const ply = Math.round(first + ((local - PAD_X) / (WIDTH - PAD_X * 2)) * span)
    const clamped = Math.max(first, Math.min(last, ply))
    return points.find(point => point.ply === clamped) ?? null
  }

  const mine = errors.length
  const summary = `Stored evaluation from White's side over ${last} plies, clamped at ${EVAL_CLAMP_PAWNS} pawns. ${mine} of your moves lost ${SEVERITY_CP.mistake} centipawns or more.`

  return (
    <figure className="eval-graph">
      <div className="eval-graph-plot">
        <svg
          ref={ref}
          viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
          preserveAspectRatio="none"
          role="img"
          aria-label={summary}
          onPointerMove={event => setHover(plyAt(event))}
          onPointerLeave={() => setHover(null)}
          onClick={event => {
            const point = plyAt(event)
            if (point) onSelect(point.ply)
          }}
        >
          <defs>
            <clipPath id="eval-white">
              <rect x="0" y="0" width={WIDTH} height={MID} />
            </clipPath>
            <clipPath id="eval-black">
              <rect x="0" y={MID} width={WIDTH} height={MID} />
            </clipPath>
          </defs>
          <path d={area} className="eval-area white" clipPath="url(#eval-white)" />
          <path d={area} className="eval-area black" clipPath="url(#eval-black)" />
          <line x1={0} x2={WIDTH} y1={MID} y2={MID} className="eval-zero" />
          <path d={line} className="eval-line" vectorEffect="non-scaling-stroke" />
          {current >= first && current <= last && (
            <line x1={x(current)} x2={x(current)} y1={0} y2={HEIGHT} className="eval-current" vectorEffect="non-scaling-stroke" />
          )}
          {hover && <line x1={x(hover.ply)} x2={x(hover.ply)} y1={0} y2={HEIGHT} className="eval-cursor" vectorEffect="non-scaling-stroke" />}
        </svg>
        {/* Markers are HTML so they stay round when the plot stretches. */}
        {errors.map(point => (
          <span
            key={point.ply}
            className={`eval-dot${(point.cpLoss ?? 0) >= SEVERITY_CP.blunder ? ' blunder' : ''}`}
            style={{ left: `${(x(point.ply) / WIDTH) * 100}%`, top: `${(y(point.pawns!) / HEIGHT) * 100}%` }}
          />
        ))}
        {keyPoint && (
          <span
            className="eval-key"
            style={{ left: `${(x(keyPoint.ply) / WIDTH) * 100}%`, top: `${(y(keyPoint.pawns!) / HEIGHT) * 100}%` }}
          />
        )}
        {hover && (
          <span className={`eval-tip${x(hover.ply) > WIDTH / 2 ? ' left' : ''}`} style={{ left: `${(x(hover.ply) / WIDTH) * 100}%` }}>
            <strong>{moveName(hover.ply, sans[hover.ply - 1])}</strong> {evalLabel(hover)}
            {hover.cpLoss !== null && hover.cpLoss > 0 && (
              <span> · {hover.cpLoss >= MATE_SWING_CP ? 'swing to mate' : `${hover.cpLoss} cp loss`}</span>
            )}
          </span>
        )}
      </div>
      <figcaption className="eval-legend">
        <span>White better above the line</span>
        <span>
          <i className="eval-dot static" /> your mistake · <i className="eval-dot static blunder" /> blunder
        </span>
        {keyPoint && (
          <span>
            <i className="eval-key static" /> key moment
          </span>
        )}
      </figcaption>
    </figure>
  )
}
