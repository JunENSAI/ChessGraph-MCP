import { describe, expect, it } from 'vitest'
import {
  loadProgress,
  loadTrainingPlan,
  nextDay,
  orderPlan,
  planSummary,
  PROGRAM_PROGRESS_KEY,
  saveProgress,
  toggleDay,
  type PlanItem,
  type ProgramDay,
  type TrainingPlan,
  type TrainingProgram,
} from './plan'

function item(over: Partial<PlanItem>): PlanItem {
  return {
    kind: 'opening',
    title: 'London System',
    reason: 'r',
    weight: 0.5,
    ready: true,
    goal: 'g',
    check_after_games: 20,
    start_fen: '',
    uci_line: '',
    pgn_line: '',
    user_color: 'white',
    puzzle_fens: [],
    ...over,
  }
}

describe('orderPlan', () => {
  it('puts ready items first, then weight, then name', () => {
    const ordered = orderPlan([
      item({ title: 'Zeta', weight: 0.9, ready: false }),
      item({ title: 'Beta', weight: 0.2 }),
      item({ title: 'Alpha', weight: 0.8 }),
    ])
    expect(ordered.map(entry => entry.title)).toEqual(['Alpha', 'Beta', 'Zeta'])
  })

  it('is stable for equal weights', () => {
    const ordered = orderPlan([item({ title: 'B' }), item({ title: 'A' })])
    expect(ordered.map(entry => entry.title)).toEqual(['A', 'B'])
  })
})

describe('planSummary', () => {
  it('names the top item and its goal', () => {
    const plan: TrainingPlan = { items: [item({ title: 'Caro-Kann', goal: 'Play 20 games.' })], strengths: [], notes: [] }
    expect(planSummary(plan)).toBe('Start with Caro-Kann: Play 20 games.')
  })

  it('says the evidence is missing rather than inventing a drill', () => {
    expect(planSummary({ items: [], strengths: [], notes: [] })).toMatch(/No family/)
  })
})

describe('loadTrainingPlan', () => {
  it('reads the plan route', async () => {
    const fetchImpl = (async () => new Response(JSON.stringify({ items: [], strengths: [], notes: [] }))) as unknown as typeof fetch
    await expect(loadTrainingPlan(fetchImpl)).resolves.toEqual({ items: [], strengths: [], notes: [] })
  })

  it('reports a failing route', async () => {
    const fetchImpl = (async () => new Response('', { status: 503 })) as unknown as typeof fetch
    await expect(loadTrainingPlan(fetchImpl)).rejects.toThrow('Training plan failed (503).')
  })
})

function program(over: Partial<TrainingProgram> = {}): TrainingProgram {
  const kinds: ProgramDay['kind'][] = ['learn', 'drill', 'mistakes', 'play', 'mistakes', 'play', 'review']
  return {
    focus: 'Caro-Kann Defense',
    title: 'Caro-Kann Defense: Main Line',
    reason: 'r',
    user_color: 'black',
    check_after_games: 20,
    days: kinds.map((kind, index) => ({
      day: index + 1,
      kind,
      title: kind,
      goal: 'g',
      start_fen: '',
      uci_line: 'e2e4 c7c6',
      user_color: 'black',
      positions: [],
      opponent_elo: kind === 'play' ? 1836 : null,
    })),
    notes: [],
    ...over,
  }
}

class Store {
  items = new Map<string, string>()
  getItem(key: string) {
    return this.items.get(key) ?? null
  }
  setItem(key: string, value: string) {
    this.items.set(key, value)
  }
}

describe('program progress', () => {
  it('starts on day 1 and moves to the first unticked day', () => {
    const week = program()
    expect(nextDay(week, [])).toBe(1)
    expect(nextDay(week, [1, 2, 4])).toBe(3)
    expect(nextDay(week, [1, 2, 3, 4, 5, 6, 7])).toBeNull()
  })

  it('saves ticks per program and drops them when the focus changes', () => {
    const store = new Store()
    saveProgress(program(), toggleDay(toggleDay([], 2), 1), store)
    expect(loadProgress(program(), store)).toEqual([1, 2])
    expect(loadProgress(program({ focus: 'French Defense' }), store)).toEqual([])
    expect(toggleDay([1, 2], 2)).toEqual([1])
  })

  it('ignores broken or foreign storage', () => {
    const store = new Store()
    store.setItem(PROGRAM_PROGRESS_KEY, '{not json')
    expect(loadProgress(program(), store)).toEqual([])
    store.setItem(PROGRAM_PROGRESS_KEY, JSON.stringify({ id: 'Caro-Kann Defense|Caro-Kann Defense: Main Line|black', done: [1, 9, 'x', 1] }))
    expect(loadProgress(program(), store)).toEqual([1])
    const throwing = { getItem: () => { throw new Error('blocked') }, setItem: () => { throw new Error('blocked') } }
    expect(loadProgress(program(), throwing)).toEqual([])
    expect(() => saveProgress(program(), [1], throwing)).not.toThrow()
  })
})
