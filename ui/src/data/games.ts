import { tryUci, type ReplayedPly } from '../lib/chess'
import { whiteEvalFromStored } from '../lib/eval'
import type { Color, GameCategory, KeyMoment, Outcome } from './types'

export const GAMES_PAGE = 25

export interface ListedGame {
  id: number
  category: GameCategory
  timeControl: string
  playedOn: string
  opponent: string
  opponentElo: number | null
  userElo: number | null
  userColor: Color
  result: Outcome | 'unfinished'
  opening: string
  eco: string
}

export interface StoredMove {
  ply: number
  san: string
  uci: string
  mover: 'w' | 'b'
  cpAfter: number | null
  cpLoss: number | null
  bestUci: string | null
}

interface GameJson {
  game_id: number
  game_type: GameCategory
  played_date: string
  white_username: string
  black_username: string
  white_elo: number | null
  black_elo: number | null
  result: string
  time_control_raw: string
  eco_code: string | null
  opening_name: string | null
}

interface MoveJson {
  ply_number: number
  turn_color: 'w' | 'b'
  san_move: string
  uci_move: string
  eval_cp_after: number | null
  cp_loss: number | null
  best_move_uci: string | null
}

export function outcomeFor(result: string, userColor: Color): Outcome | 'unfinished' {
  if (result === '1/2-1/2') return 'draw'
  if (result === '*') return 'unfinished'
  const whiteWon = result === '1-0'
  if (userColor === 'white') return whiteWon ? 'win' : 'loss'
  return whiteWon ? 'loss' : 'win'
}

export function listedGame(row: GameJson, username: string): ListedGame | null {
  const name = username.trim().toLowerCase()
  const white = row.white_username.toLowerCase() === name
  const black = row.black_username.toLowerCase() === name
  if (!white && !black) return null
  const userColor: Color = white ? 'white' : 'black'
  return {
    id: row.game_id,
    category: row.game_type,
    timeControl: row.time_control_raw,
    playedOn: row.played_date,
    opponent: white ? row.black_username : row.white_username,
    opponentElo: white ? row.black_elo : row.white_elo,
    userElo: white ? row.white_elo : row.black_elo,
    userColor,
    result: outcomeFor(row.result, userColor),
    opening: row.opening_name?.trim() || 'Unclassified',
    eco: row.eco_code?.trim() || '—',
  }
}

export function keyMomentFromMoves(stored: StoredMove[], userColor: Color, plies: ReplayedPly[]): KeyMoment | null {
  const turn = userColor === 'white' ? 'w' : 'b'
  const ranked = stored.filter(move => move.mover === turn && move.cpLoss !== null)
  if (ranked.length === 0) return null
  ranked.sort((left, right) => (right.cpLoss ?? 0) - (left.cpLoss ?? 0) || left.ply - right.ply)
  const top = ranked[0]
  const ply = plies[top.ply - 1]
  if (!ply) return null
  const best = top.bestUci ? tryUci(ply.fenBefore, top.bestUci) : null
  const previous = stored.find(move => move.ply === top.ply - 1)
  const evalBefore =
    previous?.cpAfter === null || previous?.cpAfter === undefined
      ? 0
      : whiteEvalFromStored(previous.cpAfter, previous.mover).whiteCp ?? 0
  const evalAfter = top.cpAfter === null ? evalBefore : whiteEvalFromStored(top.cpAfter, top.mover).whiteCp ?? evalBefore
  return {
    ply: top.ply,
    played: ply.san,
    best: best?.san ?? ply.san,
    evalBefore,
    evalAfter,
    explanation: best ? 'Largest stored centipawn loss.' : 'The engine move was not stored.',
    bestUci: best ? top.bestUci ?? undefined : undefined,
    cpLoss: top.cpLoss ?? undefined,
    showEngine: Boolean(best),
  }
}

async function readError(response: Response, fallback: string): Promise<string> {
  try {
    const body = (await response.json()) as { error?: string }
    if (body.error) return body.error
  } catch {
    // Keep the fallback when the body is not JSON.
  }
  return fallback
}

export async function loadPlayerName(): Promise<string> {
  const response = await fetch('/api/player')
  if (!response.ok) throw new Error(await readError(response, `Player request failed (${response.status}).`))
  const body = (await response.json()) as { username?: string }
  if (!body.username) throw new Error('The player summary has no username.')
  return body.username
}

export async function loadGamesPage(
  username: string,
  category: GameCategory,
  offset: number,
): Promise<{ games: ListedGame[]; rawCount: number; hasMore: boolean }> {
  const params = new URLSearchParams({
    game_type: category,
    limit: String(GAMES_PAGE),
    offset: String(offset),
  })
  const response = await fetch(`/api/games?${params}`)
  if (!response.ok) throw new Error(await readError(response, `Game list failed (${response.status}).`))
  const body = (await response.json()) as { games?: GameJson[] }
  const games = (body.games ?? []).flatMap(row => {
    const game = listedGame(row, username)
    return game ? [game] : []
  })
  const rawCount = body.games?.length ?? 0
  return { games, rawCount, hasMore: rawCount === GAMES_PAGE }
}

export async function loadGameMoves(gameId: number): Promise<StoredMove[]> {
  const stored: StoredMove[] = []
  let start = 1
  for (;;) {
    const params = new URLSearchParams({ start_ply: String(start), limit: '100' })
    const response = await fetch(`/api/games/${gameId}/moves?${params}`)
    if (!response.ok) throw new Error(await readError(response, `Moves request failed (${response.status}).`))
    const body = (await response.json()) as { moves?: MoveJson[] }
    const page = body.moves ?? []
    for (const move of page) {
      stored.push({
        ply: move.ply_number,
        san: move.san_move,
        uci: move.uci_move,
        mover: move.turn_color,
        cpAfter: move.eval_cp_after,
        cpLoss: move.cp_loss,
        bestUci: move.best_move_uci,
      })
    }
    if (page.length < 100) break
    start += page.length
  }
  return stored
}

/** Presentation vocabulary, not evidence. */
export const CATEGORY_LABELS: Record<GameCategory, string> = {
  rapid: 'Rapid',
  blitz: 'Blitz',
  bullet: 'Bullet',
  daily: 'Daily',
  bot: 'Bot',
}
