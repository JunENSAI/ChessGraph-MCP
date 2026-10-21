export interface PlanItem {
  kind: 'opening' | 'defense' | 'endgame' | 'puzzle'
  title: string
  reason: string
  weight: number
  ready: boolean
  goal: string
  check_after_games: number
  start_fen: string
  uci_line: string
  pgn_line: string
  user_color: 'white' | 'black'
  puzzle_fens: string[]
}

export interface TrainingPlan {
  items: PlanItem[]
  strengths: string[]
  notes: string[]
}

/** Ranked first, then unready items last, then alphabetical. Deterministic. */
export function orderPlan(items: PlanItem[]): PlanItem[] {
  return [...items].sort((a, b) => {
    if (a.ready !== b.ready) return a.ready ? -1 : 1
    const byWeight = b.weight - a.weight
    if (byWeight !== 0) return byWeight
    return a.title.localeCompare(b.title)
  })
}

export function planSummary(plan: TrainingPlan): string {
  if (plan.items.length === 0) return 'No family has enough finished games for a plan yet.'
  const top = orderPlan(plan.items)[0]
  return `Start with ${top.title}: ${top.goal}`
}

export async function loadTrainingPlan(fetchImpl: typeof fetch = fetch): Promise<TrainingPlan> {
  const response = await fetchImpl('/api/coach/plan')
  if (!response.ok) {
    throw new Error(`Training plan failed (${response.status}).`)
  }
  return (await response.json()) as TrainingPlan
}
