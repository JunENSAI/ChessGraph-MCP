import { describe, expect, it } from 'vitest'
import { loadTrainingPlan, orderPlan, planSummary, type PlanItem, type TrainingPlan } from './plan'

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
