import { describe, expect, it } from 'vitest'
import { replaySan } from '../lib/chess'
import { buildGameGraph } from '../lib/graph'
import { totalGames } from '../lib/stats'
import { LIBRARY, RATING_BANDS, TRAINING_TRACKS } from './demo'

describe('demo training tracks', () => {
  it.each(TRAINING_TRACKS.map(track => [track.title, track] as const))(
    '%s replays as a legal line',
    (_, track) => {
      expect(() => replaySan(track.line.map(step => step.san), track.startFen)).not.toThrow()
    },
  )
})

describe('demo game library', () => {
  it.each(LIBRARY.map(game => [game.id, game] as const))('%s is legal and consistent', (_, game) => {
    const plies = replaySan(game.moves)
    expect(plies[game.keyMoment.ply - 1].san).toBe(game.keyMoment.played)

    const userMovesOnOddPlies = game.userColor === 'white'
    expect(game.keyMoment.ply % 2 === 1).toBe(userMovesOnOddPlies)

    const graph = buildGameGraph(game)
    expect(graph.nodes).toHaveLength(game.moves.length + 2)
    expect(graph.nodes.find(node => node.id === 'best')).toBeDefined()
  })
})

describe('demo rating bands', () => {
  it.each(RATING_BANDS.map(band => [band.label, band] as const))(
    '%s stays within each color total',
    (_, band) => {
      const whiteOpenings = band.openingsWhite.reduce((sum, item) => sum + totalGames(item.results), 0)
      const blackDefenses = band.defensesBlack.reduce((sum, item) => sum + totalGames(item.results), 0)
      expect(whiteOpenings).toBeLessThanOrEqual(totalGames(band.white))
      expect(blackDefenses).toBeLessThanOrEqual(totalGames(band.black))

      const whiteEndgames = band.endgames.reduce((sum, item) => sum + totalGames(item.white), 0)
      const blackEndgames = band.endgames.reduce((sum, item) => sum + totalGames(item.black), 0)
      expect(whiteEndgames).toBeLessThanOrEqual(totalGames(band.white))
      expect(blackEndgames).toBeLessThanOrEqual(totalGames(band.black))
    },
  )
})
