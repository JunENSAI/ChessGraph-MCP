import { useMemo, useState, type CSSProperties } from 'react'
import { Chessboard, type Arrow } from 'react-chessboard'
import type { Square } from 'chess.js'
import { isPromotion, legalTargets, sideToMove, type Promotion } from '../lib/chess'

export interface BoardMove {
  from: Square
  to: Square
}

interface ChessBoardProps {
  id: string
  fen: string
  orientation: 'white' | 'black'
  interactive: boolean
  onMove?: (from: Square, to: Square, promotion?: Promotion) => boolean
  lastMove?: BoardMove | null
  arrows?: Arrow[]
}

const LAST_MOVE: CSSProperties = { background: 'rgba(184, 240, 90, 0.42)' }
const SELECTED: CSSProperties = { background: 'rgba(184, 240, 90, 0.62)' }
const TARGET: CSSProperties = {
  background: 'radial-gradient(circle, rgba(17, 21, 13, 0.32) 22%, transparent 24%)',
}
const CAPTURE: CSSProperties = {
  background: 'radial-gradient(circle, transparent 58%, rgba(17, 21, 13, 0.32) 60%)',
}

export function ChessBoard({ id, fen, orientation, interactive, onMove, lastMove, arrows = [] }: ChessBoardProps) {
  // Selection is tied to the position it was made in, so it clears itself
  // whenever the board receives a new FEN.
  const [selection, setSelection] = useState<{ fen: string; square: Square } | null>(null)
  const [promotion, setPromotion] = useState<{ from: Square; to: Square } | null>(null)
  const selected = selection?.fen === fen ? selection.square : null
  const turn = sideToMove(fen)
  const targets = useMemo(() => (selected ? legalTargets(fen, selected) : []), [fen, selected])

  const occupied = useMemo(() => {
    const placement = fen.split(' ')[0]
    const squares = new Set<string>()
    placement.split('/').forEach((row, rankIndex) => {
      let file = 0
      for (const char of row) {
        if (/\d/.test(char)) file += Number(char)
        else {
          squares.add(`${'abcdefgh'[file]}${8 - rankIndex}`)
          file += 1
        }
      }
    })
    return squares
  }, [fen])

  const squareStyles = useMemo(() => {
    const styles: Record<string, CSSProperties> = {}
    if (lastMove) {
      styles[lastMove.from] = LAST_MOVE
      styles[lastMove.to] = LAST_MOVE
    }
    if (selected) styles[selected] = SELECTED
    targets.forEach(square => {
      styles[square] = occupied.has(square) ? CAPTURE : TARGET
    })
    return styles
  }, [lastMove, selected, targets, occupied])

  const attempt = (from: Square, to: Square, piece?: Promotion) => {
    setSelection(null)
    if (!piece && isPromotion(fen, from, to)) {
      setPromotion({ from, to })
      return false
    }
    setPromotion(null)
    return onMove ? onMove(from, to, piece) : false
  }

  const promoting = sideToMove(fen) === 'w'
  const pieces: { id: Promotion; glyph: string; label: string }[] = [
    { id: 'q', glyph: promoting ? '♕' : '♛', label: 'Queen' },
    { id: 'r', glyph: promoting ? '♖' : '♜', label: 'Rook' },
    { id: 'b', glyph: promoting ? '♗' : '♝', label: 'Bishop' },
    { id: 'n', glyph: promoting ? '♘' : '♞', label: 'Knight' },
  ]

  return (
    <div className="chess-board-wrap">
    <Chessboard
      options={{
        id,
        position: fen,
        boardOrientation: orientation,
        allowDragging: interactive,
        animationDurationInMs: 180,
        arrows,
        squareStyles,
        boardStyle: { borderRadius: 8, overflow: 'hidden', boxShadow: '0 14px 34px rgba(0,0,0,.35)' },
        darkSquareStyle: { backgroundColor: '#b58863' },
        lightSquareStyle: { backgroundColor: '#f0d9b5' },
        darkSquareNotationStyle: { color: '#f0d9b5' },
        lightSquareNotationStyle: { color: '#b58863' },
        canDragPiece: ({ piece }) => interactive && piece.pieceType[0] === turn,
        onPieceDrop: ({ sourceSquare, targetSquare }) => {
          if (!targetSquare) return false
          // A click on a draggable piece can register as a zero-distance drop.
          if (targetSquare === sourceSquare) {
            setSelection({ fen, square: sourceSquare as Square })
            return false
          }
          return attempt(sourceSquare as Square, targetSquare as Square)
        },
        onSquareClick: ({ square, piece }) => {
          if (!interactive) return
          if (selected && targets.includes(square as Square)) {
            attempt(selected, square as Square)
            return
          }
          if (piece && piece.pieceType[0] === turn) setSelection({ fen, square: square as Square })
          else setSelection(null)
        },
      }}
    />
      {promotion && (
        <div className="promo-dialog" role="dialog" aria-label="Choose the promotion piece">
          {pieces.map(piece => (
            <button
              key={piece.id}
              type="button"
              className={promoting ? '' : 'black-piece'}
              aria-label={piece.label}
              onClick={() => attempt(promotion.from, promotion.to, piece.id)}
            >
              {piece.glyph}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
