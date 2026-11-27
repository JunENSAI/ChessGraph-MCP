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

/** One focus for seven days, from GET /api/coach/program. */
export interface ProgramPosition {
  fen: string
  best_uci: string
  played_san: string
  times: number
  average_cp_loss: number
}

export interface ProgramDay {
  day: number
  kind: 'learn' | 'drill' | 'mistakes' | 'play' | 'review'
  title: string
  goal: string
  start_fen: string
  uci_line: string
  user_color: 'white' | 'black'
  positions: ProgramPosition[]
  opponent_elo: number | null
}

export interface TrainingProgram {
  focus: string | null
  title: string
  reason: string
  user_color: 'white' | 'black'
  check_after_games: number
  days: ProgramDay[]
  notes: string[]
}

export async function loadTrainingProgram(fetchImpl: typeof fetch = fetch): Promise<TrainingProgram> {
  const response = await fetchImpl('/api/coach/program')
  if (!response.ok) throw new Error(`Training program failed (${response.status}).`)
  return (await response.json()) as TrainingProgram
}

/** Where this viewer's ticks live. Progress is per browser; the databases are written only by the ETL. */
export const PROGRAM_PROGRESS_KEY = 'chessgraph-program'

interface ProgressStore {
  getItem(key: string): string | null
  setItem(key: string, value: string): void
}

function defaultStore(): ProgressStore | null {
  try {
    return typeof localStorage === 'undefined' ? null : localStorage
  } catch {
    return null
  }
}

/** A new focus or line starts a new week. */
export function programId(program: TrainingProgram): string {
  return `${program.focus ?? ''}|${program.title}|${program.user_color}`
}

/** The days ticked for this program, or none when the stored ticks belong to another one. */
export function loadProgress(program: TrainingProgram, store: ProgressStore | null = defaultStore()): number[] {
  try {
    const raw = store?.getItem(PROGRAM_PROGRESS_KEY)
    if (!raw) return []
    const saved = JSON.parse(raw) as { id?: unknown; done?: unknown }
    if (saved.id !== programId(program) || !Array.isArray(saved.done)) return []
    const days = new Set(program.days.map(day => day.day))
    return [...new Set(saved.done.filter((day): day is number => typeof day === 'number' && days.has(day)))].sort((a, b) => a - b)
  } catch {
    return []
  }
}

export function saveProgress(program: TrainingProgram, done: number[], store: ProgressStore | null = defaultStore()): void {
  try {
    store?.setItem(PROGRAM_PROGRESS_KEY, JSON.stringify({ id: programId(program), done }))
  } catch {
    // Private windows and blocked storage: the ticks last for this page only.
  }
}

/** Today's day: the first one not ticked, or null when the week is done. */
export function nextDay(program: TrainingProgram, done: number[]): number | null {
  return program.days.find(day => !done.includes(day.day))?.day ?? null
}

export function toggleDay(done: number[], day: number): number[] {
  return done.includes(day) ? done.filter(item => item !== day) : [...done, day].sort((a, b) => a - b)
}
