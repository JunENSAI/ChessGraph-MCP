/** Shapes the /api/explorer response (graph schema v2) into one row per move. */

export interface ExplorerMoveJson {
  relationship: 'PLAYED_MOVE' | 'THEORY_MOVE'
  uci_move: string
  san_move?: string | null
  by?: 'owner' | 'opponent' | null
  games?: number | null
  wins?: number | null
  draws?: number | null
  losses?: number | null
  score_pct?: number | null
  avg_cp_loss?: number | null
  blunders?: number | null
  mistakes?: number | null
  eco_codes?: string[] | null
  is_engine_best?: boolean | null
}

export interface ExplorerJson {
  fen_norm: string
  context: {
    position?: { phase?: string | null; eval_cp?: number | null; eval_samples?: number | null; visit_games?: number }
    openings?: { opening_name?: string | null; eco_code?: string | null }[]
    opening_families?: string[]
    engine_best?: { uci: string; san?: string | null } | null
  } | null
  moves: ExplorerMoveJson[]
  games: {
    total_games: number
    owner_wins: number
    owner_draws: number
    owner_losses: number
    games: { game: { game_id: number; played_date?: string | null; opening_name?: string | null; user_outcome?: string | null }; ply: number }[]
  }
}

export interface SideStats {
  games: number
  /** Score of the side that played the move, 0-100. */
  scorePct: number | null
  avgCpLoss: number | null
  errors: number
}

export interface ExplorerRow {
  uci: string
  san: string
  book: boolean
  ecoCount: number
  engineBest: boolean
  you: SideStats | null
  opponents: SideStats | null
}

function stats(move: ExplorerMoveJson): SideStats {
  return {
    games: move.games ?? 0,
    scorePct: move.score_pct ?? null,
    avgCpLoss: move.avg_cp_loss ?? null,
    errors: (move.mistakes ?? 0) + (move.blunders ?? 0),
  }
}

/** One row per UCI move: book flag plus your and your opponents' statistics. Most-played first, then book moves. */
export function explorerRows(payload: ExplorerJson): ExplorerRow[] {
  const rows = new Map<string, ExplorerRow>()
  const bestUci = payload.context?.engine_best?.uci ?? null
  for (const move of payload.moves) {
    const row =
      rows.get(move.uci_move) ??
      ({
        uci: move.uci_move,
        san: move.san_move ?? move.uci_move,
        book: false,
        ecoCount: 0,
        engineBest: move.uci_move === bestUci,
        you: null,
        opponents: null,
      } satisfies ExplorerRow)
    if (move.relationship === 'THEORY_MOVE') {
      row.book = true
      row.ecoCount = move.eco_codes?.length ?? 0
    } else if (move.by === 'owner') row.you = stats(move)
    else if (move.by === 'opponent') row.opponents = stats(move)
    if (move.is_engine_best) row.engineBest = true
    rows.set(move.uci_move, row)
  }
  const played = (row: ExplorerRow) => (row.you?.games ?? 0) + (row.opponents?.games ?? 0)
  return [...rows.values()].sort(
    (a, b) => played(b) - played(a) || Number(b.book) - Number(a.book) || b.ecoCount - a.ecoCount || a.san.localeCompare(b.san),
  )
}

/** "62%" or "–" when there is no sample. */
export function formatScore(value: number | null | undefined): string {
  return value == null ? '–' : `${Math.round(value)}%`
}
