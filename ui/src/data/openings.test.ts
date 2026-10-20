import { describe, expect, it } from 'vitest'
import type { OpeningLesson } from './lessons'
import { endgameTitle, groupOpenings, openingFamilyName } from './openings'

function lesson(name: string, games: number): OpeningLesson {
  return { openingName: name, ecoCode: null, games, uciLine: 'e2e4', pgnLine: null }
}

describe('openingFamilyName', () => {
  it('groups London spellings under one opening', () => {
    expect(openingFamilyName("Queen's Pawn Game: London System, with e6")).toEqual({
      family: 'London System',
      variant: 'with e6',
    })
    expect(openingFamilyName("Queen's Pawn Game: London System").family).toBe('London System')
    expect(openingFamilyName('London System').variant).toBe('Main line')
  })

  it('keeps the defense name and puts the line in the variant', () => {
    expect(openingFamilyName('Scandinavian Defense: Main Line')).toEqual({
      family: 'Scandinavian Defense',
      variant: 'Main Line',
    })
  })
})

describe('groupOpenings', () => {
  it('returns the families with the most games and lists their variants', () => {
    const families = groupOpenings(
      [
        lesson("Queen's Pawn Game: London System, with e6", 10),
        lesson('London System', 4),
        lesson('Caro-Kann Defense: Exchange', 3),
        lesson('Caro-Kann Defense', 8),
      ],
      5,
    )
    expect(families.map(item => item.name)).toEqual(['London System', 'Caro-Kann Defense'])
    expect(families[0].games).toBe(14)
    expect(families[0].variants.map(item => item.label)).toEqual(['with e6', 'Main line'])
  })
})

describe('endgameTitle', () => {
  it('reads material codes as piece names', () => {
    expect(endgameTitle('KPPvKPP')).toBe('King and two pawns vs king and two pawns')
    expect(endgameTitle('KQvK')).toBe('King and queen vs king')
    expect(endgameTitle('KvKP')).toBe('King vs king and pawn')
  })
})
