import { describe, expect, it } from 'vitest'
import { levelForRating, MAX_ENGINE_ELO, MIN_ENGINE_ELO, moveTimeMs, STRENGTH_LEVELS, strengthById } from './strength'

describe('strength levels', () => {
  it('stay inside the range Stockfish accepts', () => {
    for (const level of STRENGTH_LEVELS) {
      if (level.elo !== null) {
        expect(level.elo).toBeGreaterThanOrEqual(MIN_ENGINE_ELO)
        expect(level.elo).toBeLessThanOrEqual(MAX_ENGINE_ELO)
      }
    }
    expect(STRENGTH_LEVELS.at(-1)?.elo).toBeNull()
  })

  it('picks the closest limited level for a rating', () => {
    expect(levelForRating(1780).id).toBe('1800')
    expect(levelForRating(900).id).toBe('1400')
    expect(levelForRating(3000).id).toBe('2500')
    expect(levelForRating(null).id).toBe('1800')
  })

  it('falls back to the default for an unknown id', () => {
    expect(strengthById('nope').id).toBe('1800')
  })

  it('thinks longer at higher levels, within the API bounds', () => {
    const times = STRENGTH_LEVELS.map(moveTimeMs)
    expect(times.every(time => time >= 50 && time <= 3000)).toBe(true)
    expect(moveTimeMs(strengthById('2500'))).toBeGreaterThan(moveTimeMs(strengthById('1400')))
  })
})
