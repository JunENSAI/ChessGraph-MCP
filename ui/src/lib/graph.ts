export const NODE_COLORS = {
  start: '#8d96a5',
  user: '#b8f05a',
  opponent: '#77a7ff',
  mistake: '#ff7b72',
  best: '#bb9af7',
} as const

export type NodeKind = keyof typeof NODE_COLORS

export interface GraphNode {
  id: string
  label: string
  description: string
  kind: NodeKind
  ply: number
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

interface GraphGame {
  moves: string[]
  userColor: 'white' | 'black'
  keyMoment: { ply: number; best: string; showEngine?: boolean } | null
}

/** Played path plus the stored engine alternative at the key moment. */
export function buildGameGraph(game: GraphGame): GameGraph {
  const userStarts = game.userColor === 'white'
  const nodes: GraphNode[] = [
    { id: 'ply-0', label: 'Start', description: 'Starting position', kind: 'start', ply: 0 },
  ]
  const links: GraphLink[] = []
  game.moves.forEach((san, index) => {
    const ply = index + 1
    const userMove = userStarts ? ply % 2 === 1 : ply % 2 === 0
    const mistake = game.keyMoment?.ply === ply
    const id = `ply-${ply}`
    nodes.push({
      id,
      label: san,
      description: mistake ? 'Key moment' : userMove ? 'Your move' : 'Opponent',
      kind: mistake ? 'mistake' : userMove ? 'user' : 'opponent',
      ply,
    })
    links.push({ source: `ply-${index}`, target: id, kind: 'played' })
  })
  const key = game.keyMoment
  if (key && key.showEngine !== false && key.ply >= 1 && key.ply <= game.moves.length) {
    nodes.push({
      id: 'best',
      label: key.best,
      description: 'Stockfish best',
      kind: 'best',
      ply: key.ply,
    })
    links.push({ source: `ply-${key.ply - 1}`, target: 'best', kind: 'alternative' })
  }
  return { nodes, links }
}
