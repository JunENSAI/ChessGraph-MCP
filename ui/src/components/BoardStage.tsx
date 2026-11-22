import type { ReactNode } from 'react'
import type { Arrow } from 'react-chessboard'
import type { Square } from 'chess.js'
import { ChessBoard, type BoardMove } from './ChessBoard'
import { EvalBar } from './EvalBar'
import { PlayerBar } from './PlayerBar'
import { materialBalance } from '../lib/material'
import type { Promotion } from '../lib/chess'
import type { WhiteEval } from '../lib/eval'

export interface SeatInfo {
  name: string
  rating?: number
  timeMs?: number
  active?: boolean
  flagged?: boolean
  thinking?: boolean
}

interface BoardStageProps {
  id: string
  fen: string
  orientation: 'white' | 'black'
  white: SeatInfo
  black: SeatInfo
  evaluation: { evaluation: WhiteEval; pending: boolean }
  interactive: boolean
  onMove?: (from: Square, to: Square, promotion?: Promotion) => boolean
  lastMove?: BoardMove | null
  arrows?: Arrow[]
  /** Shown centered over the board, e.g. the result and a rematch button. */
  overlay?: ReactNode
  /** Shown under the board, e.g. move navigation. */
  controls?: ReactNode
  /** Title and status line above the board. */
  header?: ReactNode
}

/** Player bars, evaluation bar and board, sized to the viewport height. */
export function BoardStage({
  id,
  fen,
  orientation,
  white,
  black,
  evaluation,
  interactive,
  onMove,
  lastMove,
  arrows,
  overlay,
  controls,
  header,
}: BoardStageProps) {
  const balance = materialBalance(fen)
  const seat = (color: 'white' | 'black') => {
    const info = color === 'white' ? white : black
    return (
      <PlayerBar
        {...info}
        color={color}
        captured={color === 'white' ? balance.capturedByWhite : balance.capturedByBlack}
        advantage={color === 'white' ? balance.diff : -balance.diff}
      />
    )
  }
  const top = orientation === 'white' ? 'black' : 'white'
  return (
    <section className="board-stage" aria-label="Board">
      <div className="stage-column">
        {header && <header className="stage-head">{header}</header>}
        {seat(top)}
        <div className="board-and-eval">
          <EvalBar orientation={orientation} evaluation={evaluation.evaluation} pending={evaluation.pending} />
          <div className="board-frame">
            {overlay && <div className="board-result">{overlay}</div>}
            <ChessBoard
              id={id}
              fen={fen}
              orientation={orientation}
              interactive={interactive}
              onMove={onMove}
              lastMove={lastMove}
              arrows={arrows}
            />
          </div>
        </div>
        {seat(orientation)}
        {controls && <div className="board-controls">{controls}</div>}
      </div>
    </section>
  )
}
