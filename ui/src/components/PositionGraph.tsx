import { useEffect, useMemo, useRef } from 'react'
import ForceGraph3D, { type ForceGraphMethods } from 'react-force-graph-3d'
import SpriteText from 'three-spritetext'
import { useElementSize } from '../hooks/useElementSize'
import { NODE_COLORS, type GameGraph, type GraphNode } from '../lib/graph'

interface PositionGraphProps {
  graph: GameGraph
  selectedId: string
  onSelect: (node: GraphNode) => void
}

type RenderNode = GraphNode & { x?: number; y?: number; z?: number }

export default function PositionGraph({ graph, selectedId, onSelect }: PositionGraphProps) {
  const [containerRef, size] = useElementSize<HTMLDivElement>()
  const graphRef = useRef<ForceGraphMethods | undefined>(undefined)

  // The force engine mutates node objects, so each game gets fresh copies.
  const data = useMemo(
    () => ({
      nodes: graph.nodes.map(node => ({ ...node })),
      links: graph.links.map(link => ({ ...link })),
    }),
    [graph],
  )

  useEffect(() => {
    const instance = graphRef.current
    if (!instance) return
    const node = data.nodes.find(item => item.id === selectedId) as RenderNode | undefined
    if (!node || node.x === undefined) return
    const distance = 90
    instance.cameraPosition(
      { x: (node.x ?? 0) + distance * 0.35, y: (node.y ?? 0) + distance * 0.25, z: (node.z ?? 0) + distance },
      { x: node.x ?? 0, y: node.y ?? 0, z: node.z ?? 0 },
      700,
    )
  }, [selectedId, data])

  return (
    <div className="graph-canvas" ref={containerRef}>
      {size.width > 0 && size.height > 0 && (
        <ForceGraph3D
          ref={graphRef}
          width={size.width}
          height={size.height}
          graphData={data}
          backgroundColor="#0b0e12"
          dagMode="lr"
          dagLevelDistance={26}
          showNavInfo={false}
          cooldownTicks={120}
          nodeRelSize={4}
          nodeVal={node => ((node as RenderNode).id === selectedId ? 5 : (node as RenderNode).kind === 'start' ? 3 : 1.6)}
          nodeColor={node => NODE_COLORS[(node as RenderNode).kind]}
          nodeLabel={node => `${(node as RenderNode).label} · ${(node as RenderNode).description}`}
          nodeThreeObjectExtend
          nodeThreeObject={node => {
            const item = node as RenderNode
            const label = new SpriteText(item.label, item.id === selectedId ? 4.2 : 3, '#e6ebf2')
            label.fontFace = 'Inter, system-ui, sans-serif'
            label.fontWeight = item.id === selectedId ? '700' : '500'
            label.position.set(0, 7, 0)
            return label
          }}
          linkColor={link => ((link as { kind: string }).kind === 'alternative' ? '#bb9af7' : '#4a5566')}
          linkWidth={link => ((link as { kind: string }).kind === 'alternative' ? 1.2 : 0.6)}
          linkDirectionalParticles={link => ((link as { kind: string }).kind === 'alternative' ? 3 : 1)}
          linkDirectionalParticleWidth={1.6}
          linkDirectionalParticleColor={link =>
            (link as { kind: string }).kind === 'alternative' ? '#bb9af7' : '#b8f05a'
          }
          onNodeClick={node => onSelect(node as RenderNode)}
          onEngineStop={() => {
            const node = data.nodes.find(item => item.id === selectedId) as RenderNode | undefined
            if (node?.x !== undefined) {
              graphRef.current?.cameraPosition(
                { x: node.x + 30, y: (node.y ?? 0) + 25, z: (node.z ?? 0) + 110 },
                { x: node.x, y: node.y ?? 0, z: node.z ?? 0 },
                600,
              )
            }
          }}
        />
      )}
    </div>
  )
}
