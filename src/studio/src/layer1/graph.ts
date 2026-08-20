import dagre from '@dagrejs/dagre'
import type { CreatorProjection, CreatorRecipeNode } from '../api/types.ts'
import { copy } from '../copy.ts'
import { nodeReviewState } from './model.ts'

export const RELATION_KINDS = ['control', 'data', 'uses'] as const
export type RelationKind = (typeof RELATION_KINDS)[number]
export type PortSide = 'left' | 'right' | 'top' | 'bottom'
export type PortCounts = Record<PortSide, { incoming: number; outgoing: number }>
export type EdgePort = { sourceSide: PortSide; targetSide: PortSide; sourceIndex: number; targetIndex: number }

export type SemanticEdge = {
  id: string
  source: string
  target: string
  relation: string
  kind: RelationKind
  label: string
}

export type Neighbor = {
  nodeId: string
  label: string
  kind: RelationKind
  relation: string
  direction: 'in' | 'out'
}

export type StepContract = {
  need: string
  role: string
  resolved: boolean
  capabilityLabel?: string
  inputs: Neighbor[]
  outputs: Neighbor[]
  uses: Neighbor[]
}

export type GraphNodeSize = { width: number; height: number }

const PORT_SIDES: PortSide[] = ['left', 'right', 'top', 'bottom']
const KIND_SIDES: Record<RelationKind, { source: PortSide; target: PortSide }> = {
  control: { source: 'right', target: 'left' },
  data: { source: 'bottom', target: 'top' },
  uses: { source: 'top', target: 'bottom' },
}
const VERTICAL_KIND_SIDES: Record<RelationKind, { source: PortSide; target: PortSide }> = {
  control: { source: 'bottom', target: 'top' },
  data: { source: 'right', target: 'left' },
  uses: { source: 'left', target: 'right' },
}

const NODE_WIDTH = 160
const MIN_NODE_HEIGHT = 132
const MAX_NODE_HEIGHT = 132
const MAX_NODE_WIDTH = 160

export function relationKind(relation: string): RelationKind {
  if (relation === 'uses') return 'uses'
  if (relation === 'produces') return 'data'
  return 'control'
}

export function relationLabel(relation: string) {
  if (relation === 'uses') return copy.relationUses
  if (relation === 'produces') return copy.relationProduces
  return copy.relationInforms
}

export function kindLabel(kind: RelationKind) {
  if (kind === 'uses') return copy.kindUses
  if (kind === 'data') return copy.kindData
  return copy.kindControl
}

export function relationEndpoints(relation: { from_node_id: string; to_node_id: string; relation: string }) {
  if (relation.relation === 'uses') return { source: relation.to_node_id, target: relation.from_node_id }
  return { source: relation.from_node_id, target: relation.to_node_id }
}

export function semanticEdges(creator: CreatorProjection): SemanticEdge[] {
  const known = new Set(creator.trusted_recipe.nodes.map((node) => node.id))
  return creator.trusted_recipe.relations.flatMap((relation) => {
    const ends = relationEndpoints(relation)
    if (!known.has(ends.source) || !known.has(ends.target) || ends.source === ends.target) return []
    return [{
      id: relation.id,
      source: ends.source,
      target: ends.target,
      relation: relation.relation,
      kind: relationKind(relation.relation),
      label: relationLabel(relation.relation),
    }]
  })
}

export function emptyPortCounts(): PortCounts {
  return {
    left: { incoming: 0, outgoing: 0 },
    right: { incoming: 0, outgoing: 0 },
    top: { incoming: 0, outgoing: 0 },
    bottom: { incoming: 0, outgoing: 0 },
  }
}

export function getPortHandleId(type: 'target' | 'source', side: PortSide, index: number) {
  return `${type}-${side}-${index}`
}

export function assignEdgePorts(edges: SemanticEdge[], vertical: boolean): {
  counts: Map<string, PortCounts>
  ports: Map<string, EdgePort>
} {
  const sides = vertical ? VERTICAL_KIND_SIDES : KIND_SIDES
  const counts = new Map<string, PortCounts>()
  const ports = new Map<string, EdgePort>()
  const bump = (nodeId: string, side: PortSide, direction: 'incoming' | 'outgoing') => {
    const current = counts.get(nodeId) || emptyPortCounts()
    const index = current[side][direction]
    current[side][direction] = index + 1
    counts.set(nodeId, current)
    return index
  }
  for (const edge of edges) {
    const pair = sides[edge.kind]
    const sourceIndex = bump(edge.source, pair.source, 'outgoing')
    const targetIndex = bump(edge.target, pair.target, 'incoming')
    ports.set(edge.id, { sourceSide: pair.source, targetSide: pair.target, sourceIndex, targetIndex })
  }
  return { counts, ports }
}

export function visiblePortCount(count: number) {
  return Math.max(1, Math.min(5, count || 1))
}

export function portOffset(type: 'target' | 'source', index: number, count: number) {
  const groups = type === 'target'
    ? [[44], [34, 50], [26, 42, 58], [18, 34, 50, 66], [14, 28, 42, 56, 70]]
    : [[56], [50, 66], [42, 58, 74], [34, 50, 66, 82], [30, 44, 58, 72, 86]]
  const offsets = groups[visiblePortCount(count) - 1]
  return `${offsets[index % offsets.length]}%`
}

export function nodeNeighbors(creator: CreatorProjection, nodeId: string): Neighbor[] {
  const labels = new Map(creator.trusted_recipe.nodes.map((node) => [node.id, node.label]))
  const neighbors: Neighbor[] = []
  for (const edge of semanticEdges(creator)) {
    if (edge.target === nodeId) {
      neighbors.push({ nodeId: edge.source, label: labels.get(edge.source) || edge.source, kind: edge.kind, relation: edge.relation, direction: 'in' })
    } else if (edge.source === nodeId) {
      neighbors.push({ nodeId: edge.target, label: labels.get(edge.target) || edge.target, kind: edge.kind, relation: edge.relation, direction: 'out' })
    }
  }
  return neighbors
}

export function stepContract(creator: CreatorProjection, node: CreatorRecipeNode): StepContract {
  const neighbors = nodeNeighbors(creator, node.id)
  const need = node.resolution?.needed_capability || node.description
  return {
    need,
    role: need,
    resolved: node.resolution?.status === 'resolved',
    capabilityLabel: node.resolution?.capability?.label,
    inputs: neighbors.filter((item) => item.direction === 'in' && item.kind !== 'uses'),
    outputs: neighbors.filter((item) => item.direction === 'out' && item.kind !== 'uses'),
    uses: neighbors.filter((item) => item.kind === 'uses'),
  }
}

export function packRoles(creator: CreatorProjection) {
  return creator.trusted_recipe.nodes.map((node) => ({
    nodeId: node.id,
    label: node.label,
    role: node.resolution?.needed_capability || node.description,
    bound: node.resolution?.status === 'resolved',
    state: nodeReviewState(creator, node),
  }))
}

function visualLength(value: string) {
  return Array.from(value).reduce((length, character) => length + (/\p{Script=Han}/u.test(character) ? 1 : 0.56), 0)
}

export function stepNodeSize(node: CreatorRecipeNode, _unresolved: boolean): GraphNodeSize {
  const width = Math.min(MAX_NODE_WIDTH, Math.max(NODE_WIDTH, 58 + visualLength(node.label) * 9))
  const titleLines = Math.min(2, Math.max(1, Math.ceil(visualLength(node.label) / Math.max(8, (width - 120) / 11))))
  const bodyLines = Math.min(3, Math.max(2, Math.ceil(visualLength(node.description) / Math.max(12, (width - 32) / 11))))
  const extras = 36
  const height = Math.min(MAX_NODE_HEIGHT, MIN_NODE_HEIGHT + (titleLines - 1) * 22 + (bodyLines - 2) * 16 + extras)
  return { width, height }
}

export function layoutGraph<T extends { id: string; width?: number | null; height?: number | null }>(
  nodes: T[],
  edges: Array<{ source: string; target: string }>,
  vertical: boolean,
) {
  const graph = new dagre.graphlib.Graph().setDefaultEdgeLabel(() => ({}))
  graph.setGraph({
    rankdir: vertical ? 'TB' : 'LR',
    align: 'UL',
    acyclicer: 'greedy',
    ranker: 'network-simplex',
    nodesep: 48,
    ranksep: vertical ? 72 : 88,
    edgesep: 36,
    marginx: 28,
    marginy: 28,
  })
  nodes.forEach((node) => graph.setNode(node.id, { width: node.width || NODE_WIDTH, height: node.height || MIN_NODE_HEIGHT }))
  edges.forEach((edge) => graph.setEdge(edge.source, edge.target))
  dagre.layout(graph)
  return nodes.map((node) => {
    const point = graph.node(node.id)
    const width = node.width || NODE_WIDTH
    const height = node.height || MIN_NODE_HEIGHT
    return { ...node, position: { x: point.x - width / 2, y: point.y - height / 2 } }
  })
}

export { PORT_SIDES }
