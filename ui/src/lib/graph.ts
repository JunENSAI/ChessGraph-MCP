import type { Color, KeyMoment } from '../data/types'
import { replaySan } from './chess'

export type GraphNodeKind = 'start' | 'user' | 'opponent' | 'mistake' | 'best'

export interface GraphNode {
  id: string
  label: string
  kind: GraphNodeKind
  /** Ply reached at this node; the engine alternative points at its root ply. */
  ply: number
  fen: string
  description: string
}

export interface GraphLink {
  source: string
  target: string
  kind: 'played' | 'alternative'
}

export interface GameGraph {
  nodes: GraphNode[]
  links: GraphLink[]
}

export const NODE_COLORS: Record<GraphNodeKind, string> = {
  start: '#f3f5f7',
  user: '#b8f05a',
  opponent: '#77a7ff',
  mistake: '#ff7b72',
  best: '#bb9af7',
}

/**
 * Builds the position path of one game plus the engine's preferred branch
 * at the key moment, mirroring Neo4j PLAYED_MOVE and THEORY_MOVE edges.
 */
export function buildGameGraph(game: {
  moves: string[]
  userColor: Color
  keyMoment: KeyMoment | null
}): GameGraph {
  const plies = replaySan(game.moves)
  const userSide = game.userColor === 'white' ? 1 : 0
  const nodes: GraphNode[] = [
    {
      id: 'ply-0',
      label: 'Start',
      kind: 'start',
      ply: 0,
      fen: plies[0]?.fenBefore ?? '',
      description: 'Initial position',
    },
  ]
  const links: GraphLink[] = []

  plies.forEach(({ ply, san, fenAfter }) => {
    const moveNumber = Math.ceil(ply / 2)
    const notation = ply % 2 === 1 ? `${moveNumber}.${san}` : `${moveNumber}…${san}`
    const isUser = ply % 2 === userSide
    const isMistake = game.keyMoment !== null && ply === game.keyMoment.ply
    nodes.push({
      id: `ply-${ply}`,
      label: notation,
      kind: isMistake ? 'mistake' : isUser ? 'user' : 'opponent',
      ply,
      fen: fenAfter,
      description: isMistake ? 'Key moment reviewed by Hermes' : isUser ? 'Your move' : 'Opponent move',
    })
    links.push({ source: `ply-${ply - 1}`, target: `ply-${ply}`, kind: 'played' })
  })

  const key = game.keyMoment
  const root = key && key.showEngine !== false ? plies[key.ply - 1] : undefined
  if (key && root) {
    try {
      const [best] = replaySan([key.best], root.fenBefore)
      const moveNumber = Math.ceil(key.ply / 2)
      nodes.push({
        id: 'best',
        label: key.ply % 2 === 1 ? `${moveNumber}.${best.san}` : `${moveNumber}…${best.san}`,
        kind: 'best',
        ply: key.ply - 1,
        fen: best.fenAfter,
        description: 'Stockfish preferred alternative',
      })
      links.push({ source: `ply-${key.ply - 1}`, target: 'best', kind: 'alternative' })
    } catch {
      // The stored engine move is not legal from this position.
    }
  }

  return { nodes, links }
}
