import { useEffect, useRef } from 'react'
import { glyphFor, pairMoves, type NotationPly } from '../lib/notation'

interface MoveTableProps {
  plies: NotationPly[]
  /** Number of plies shown on the board (0 = start position). */
  current: number
  startFen?: string
  onSelect: (index: number) => void
  /** 1-based ply to mark as the key moment. */
  keyPly?: number | null
  empty?: string
}

/** Two-column numbered notation with ?!, ? and ?? from stored centipawn loss. */
export function MoveTable({ plies, current, startFen, onSelect, keyPly = null, empty = 'No moves yet.' }: MoveTableProps) {
  const listRef = useRef<HTMLDivElement>(null)
  const rows = pairMoves(plies.length, startFen)

  useEffect(() => {
    const node = listRef.current?.querySelector<HTMLElement>('.mt-move.current')
    node?.scrollIntoView({ block: 'nearest' })
  }, [current, plies.length])

  if (plies.length === 0) return <p className="muted small move-table-empty">{empty}</p>

  const cell = (index: number | null) => {
    if (index === null) return <span className="mt-move empty">…</span>
    const ply = plies[index]
    const glyph = glyphFor(ply.cpLoss)
    const classes = ['mt-move']
    if (index + 1 === current) classes.push('current')
    if (index + 1 === keyPly) classes.push('key')
    if (glyph) classes.push(glyph === '??' ? 'blunder' : glyph === '?' ? 'mistake' : 'inaccuracy')
    return (
      <button type="button" className={classes.join(' ')} onClick={() => onSelect(index + 1)}>
        {ply.san}
        {glyph && <span className="glyph">{glyph}</span>}
      </button>
    )
  }

  return (
    <div className="move-table" ref={listRef} role="list" aria-label="Moves">
      {rows.map(row => (
        <div key={row.number} className="mt-row" role="listitem">
          <span className="mt-number">{row.number}.</span>
          {cell(row.white)}
          {cell(row.black)}
        </div>
      ))}
    </div>
  )
}
