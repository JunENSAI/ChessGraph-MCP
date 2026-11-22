import { Chess } from 'chess.js'

/** One ply as the move table needs it. */
export interface NotationPly {
  san: string
  /** Stored centipawn loss of this move, when evaluated. */
  cpLoss?: number | null
}

export interface MoveRow {
  number: number
  /** Index into the ply list (0-based) of White's and Black's move, or null for an empty cell. */
  white: number | null
  black: number | null
}

export type Glyph = '?!' | '?' | '??'

/** Same thresholds as the graph ETL (`chess_mcp.chess.SEVERITY_MIN_CP`). */
export const SEVERITY_CP = { inaccuracy: 50, mistake: 100, blunder: 300 } as const

export function glyphFor(cpLoss: number | null | undefined): Glyph | null {
  if (cpLoss == null) return null
  if (cpLoss >= SEVERITY_CP.blunder) return '??'
  if (cpLoss >= SEVERITY_CP.mistake) return '?'
  if (cpLoss >= SEVERITY_CP.inaccuracy) return '?!'
  return null
}

function startInfo(startFen?: string): { number: number; blackFirst: boolean } {
  const fields = (startFen ?? '').trim().split(/\s+/)
  const blackFirst = fields[1] === 'b'
  const number = Number(fields[5])
  return { number: Number.isInteger(number) && number > 0 ? number : 1, blackFirst }
}

/** Pair plies into numbered rows. A game that starts with Black to move gets an empty White cell. */
export function pairMoves(plyCount: number, startFen?: string): MoveRow[] {
  const { number, blackFirst } = startInfo(startFen)
  const rows: MoveRow[] = []
  let index = 0
  let moveNumber = number
  if (blackFirst && plyCount > 0) {
    rows.push({ number: moveNumber, white: null, black: 0 })
    index = 1
    moveNumber += 1
  }
  for (; index < plyCount; index += 2) {
    rows.push({ number: moveNumber, white: index, black: index + 1 < plyCount ? index + 1 : null })
    moveNumber += 1
  }
  return rows
}

export interface PgnHeaders {
  white: string
  black: string
  result?: '1-0' | '0-1' | '1/2-1/2' | '*'
  date?: Date
  event?: string
}

/** A PGN for the clipboard. Moves are replayed so an illegal list fails loudly. */
export function buildPgn(sans: string[], headers: PgnHeaders, startFen?: string): string {
  const chess = startFen ? new Chess(startFen) : new Chess()
  for (const san of sans) chess.move(san)
  const date = headers.date ?? new Date()
  const pad = (value: number) => String(value).padStart(2, '0')
  chess.setHeader('Event', headers.event ?? 'ChessGraph training game')
  chess.setHeader('Site', 'ChessGraph')
  chess.setHeader('Date', `${date.getFullYear()}.${pad(date.getMonth() + 1)}.${pad(date.getDate())}`)
  chess.setHeader('White', headers.white)
  chess.setHeader('Black', headers.black)
  chess.setHeader('Result', headers.result ?? '*')
  return chess.pgn()
}
