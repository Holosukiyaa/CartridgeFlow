import { useMemo } from 'react'
import dagre from '@dagrejs/dagre'
import {
  Background,
  Controls,
  MarkerType,
  ReactFlow,
  type Edge,
  type Node,
  type NodeProps,
} from '@xyflow/react'
import { Check, CircleDashed, Sparkles, Wrench } from 'lucide-react'
import type { CreatorProjection } from '../../api.types.ts'

type CanvasNodeData = {
  label: string
  description: string
  state: 'empty' | 'review' | 'confirmed' | 'unresolved'
}

type CanvasNode = Node<CanvasNodeData, 'creator'>

function CreatorNode({ data, selected }: NodeProps<CanvasNode>) {
  return <div className={`creator-node creator-node-${data.state} ${selected ? 'is-selected' : ''}`}>
    <span className="creator-node-state" aria-hidden="true">
      {data.state === 'confirmed' ? <Check /> : data.state === 'empty' ? <Sparkles /> : data.state === 'unresolved' ? <Wrench /> : <CircleDashed />}
    </span>
    <div>
      <strong>{data.label}</strong>
      <p>{data.description}</p>
      <small>{data.state === 'confirmed' ? '已确认' : data.state === 'review' ? '待审核' : data.state === 'unresolved' ? '待补齐能力' : '从这里开始'}</small>
    </div>
  </div>
}

const nodeTypes = { creator: CreatorNode }

function layout(nodes: CanvasNode[], edges: Edge[]) {
  const graph = new dagre.graphlib.Graph().setDefaultEdgeLabel(() => ({}))
  graph.setGraph({ rankdir: 'LR', ranksep: 88, nodesep: 48, marginx: 48, marginy: 48 })
  nodes.forEach((node) => graph.setNode(node.id, { width: 240, height: 116 }))
  edges.forEach((edge) => graph.setEdge(edge.source, edge.target))
  dagre.layout(graph)
  return nodes.map((node) => {
    const point = graph.node(node.id)
    return { ...node, position: { x: point.x - 120, y: point.y - 58 } }
  })
}

export function CreatorCanvas({ creator, selectedId, onSelect }: {
  creator: CreatorProjection | null
  selectedId: string
  onSelect: (nodeId: string) => void
}) {
  const elements = useMemo(() => {
    if (!creator) {
      const nodes: CanvasNode[] = [{
        id: 'empty',
        type: 'creator',
        position: { x: 0, y: 0 },
        data: { label: '开始创作', description: '告诉 AI 你想得到什么', state: 'empty' },
        selectable: false,
      }]
      return { nodes: layout(nodes, []), edges: [] as Edge[] }
    }
    const confirmed = new Set(creator.frozen_steps)
    const nodes: CanvasNode[] = creator.trusted_recipe.nodes.map((node) => ({
      id: node.id,
      type: 'creator',
      position: { x: 0, y: 0 },
      selected: node.id === selectedId,
      data: {
        label: node.label,
        description: node.description,
        state: node.resolution?.status === 'unresolved' ? 'unresolved' : confirmed.has(node.id) ? 'confirmed' : 'review',
      },
    }))
    const edges: Edge[] = creator.trusted_recipe.relations.map((relation) => ({
      id: relation.id,
      source: relation.from_node_id,
      target: relation.to_node_id,
      label: relation.relation === 'produces' ? '产出' : relation.relation === 'uses' ? '使用' : '提供信息',
      markerEnd: { type: MarkerType.ArrowClosed },
      className: 'creator-edge',
    }))
    return { nodes: layout(nodes, edges), edges }
  }, [creator, selectedId])

  return <ReactFlow
    nodes={elements.nodes}
    edges={elements.edges}
    nodeTypes={nodeTypes}
    onNodeClick={(_, node) => node.id !== 'empty' && onSelect(node.id)}
    nodesDraggable={false}
    nodesConnectable={false}
    elementsSelectable={Boolean(creator)}
    deleteKeyCode={null}
    fitView
    fitViewOptions={{ padding: 0.28, maxZoom: 1.1 }}
    minZoom={0.35}
    maxZoom={1.5}
    proOptions={{ hideAttribution: true }}
  >
    <Background color="#d8dde3" gap={22} size={1} />
    <Controls showInteractive={false} position="bottom-left" />
  </ReactFlow>
}
