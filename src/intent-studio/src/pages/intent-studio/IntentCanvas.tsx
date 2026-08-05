import { useEffect, useMemo, useState } from 'react'
import dagre from '@dagrejs/dagre'
import {
  Background,
  BackgroundVariant,
  Controls,
  Handle,
  MarkerType,
  Position,
  ReactFlow,
  type Edge,
  type Node,
  type NodeProps,
  type ReactFlowInstance,
} from '@xyflow/react'
import { Check, CircleDashed, Sparkles, Wrench } from 'lucide-react'
import type { CreatorProjection } from '../../api.types.ts'

type CanvasNodeData = {
  order: number
  label: string
  description: string
  state: 'empty' | 'review' | 'confirmed' | 'unresolved'
  direction: 'horizontal' | 'vertical'
}

type CanvasNode = Node<CanvasNodeData, 'creator'>

function CreatorNode({ data, selected }: NodeProps<CanvasNode>) {
  const stateLabel = data.state === 'confirmed' ? '已确认' : data.state === 'review' ? '待审核' : data.state === 'unresolved' ? '待补齐能力' : '空白画布'
  return <div className={`creator-node creator-node-${data.state} ${selected ? 'is-selected' : ''}`}>
    <Handle type="target" position={data.direction === 'vertical' ? Position.Top : Position.Left} />
    <header className="creator-node-header">
      <span className="creator-node-order">{data.order ? String(data.order).padStart(2, '0') : 'AI'}</span>
      <span className="creator-node-state">
        {data.state === 'confirmed' ? <Check /> : data.state === 'empty' ? <Sparkles /> : data.state === 'unresolved' ? <Wrench /> : <CircleDashed />}
        {stateLabel}
      </span>
    </header>
    <div className="creator-node-body">
      <strong title={data.label}>{data.label}</strong>
      <p title={data.description}>{data.description}</p>
    </div>
    <Handle type="source" position={data.direction === 'vertical' ? Position.Bottom : Position.Right} />
  </div>
}

const nodeTypes = { creator: CreatorNode }
const fitOptions = {
  padding: { top: '10%', right: '7%', bottom: '10%', left: '7%' },
  minZoom: 0.55,
  maxZoom: 1,
} as const
const compactFitOptions = {
  padding: '5%',
  minZoom: 0.78,
  maxZoom: 1,
} as const

function layout(nodes: CanvasNode[], edges: Edge[], vertical: boolean) {
  if (!vertical && nodes.length > 1 && nodes.length <= 6) {
    return nodes.map((node, index) => ({
      ...node,
      position: { x: (index % 3) * 286, y: Math.floor(index / 3) * 238 },
    }))
  }
  const graph = new dagre.graphlib.Graph().setDefaultEdgeLabel(() => ({}))
  graph.setGraph({ rankdir: vertical ? 'TB' : 'LR', ranksep: vertical ? 42 : 56, nodesep: 44, marginx: 32, marginy: 36, acyclicer: 'greedy' })
  nodes.forEach((node) => graph.setNode(node.id, { width: 214, height: 146 }))
  edges.forEach((edge) => graph.setEdge(edge.source, edge.target))
  dagre.layout(graph)
  return nodes.map((node) => {
    const point = graph.node(node.id)
    return { ...node, position: { x: point.x - 107, y: point.y - 73 } }
  })
}

export function IntentCanvas({ creator, selectedId, onSelect }: {
  creator: CreatorProjection | null
  selectedId: string
  onSelect: (nodeId: string) => void
}) {
  const [flow, setFlow] = useState<ReactFlowInstance<CanvasNode, Edge> | null>(null)
  const [vertical, setVertical] = useState(() => window.matchMedia('(max-width: 760px)').matches)
  useEffect(() => {
    const query = window.matchMedia('(max-width: 760px)')
    const update = () => setVertical(query.matches)
    query.addEventListener('change', update)
    return () => query.removeEventListener('change', update)
  }, [])
  const elements = useMemo(() => {
    if (!creator) {
      const nodes: CanvasNode[] = [{
        id: 'empty',
        type: 'creator',
        width: 214,
        height: 146,
        position: { x: 0, y: 0 },
        data: { order: 0, label: '开始创作', description: '告诉 AI 你想得到什么', state: 'empty', direction: vertical ? 'vertical' : 'horizontal' },
        selectable: false,
      }]
      return { nodes: layout(nodes, [], vertical), edges: [] as Edge[] }
    }
    const confirmed = new Set(creator.frozen_steps)
    const nodes: CanvasNode[] = creator.trusted_recipe.nodes.map((node, index) => ({
      id: node.id,
      type: 'creator',
      width: 214,
      height: 146,
      position: { x: 0, y: 0 },
      selected: node.id === selectedId,
      data: {
        order: index + 1,
        label: node.label,
        description: node.description,
        state: node.resolution?.status === 'unresolved' ? 'unresolved' : confirmed.has(node.id) ? 'confirmed' : 'review',
        direction: vertical ? 'vertical' : 'horizontal',
      },
    }))
    const edges: Edge[] = creator.trusted_recipe.relations.map((relation) => ({
      id: relation.id,
      source: relation.relation === 'uses' ? relation.to_node_id : relation.from_node_id,
      target: relation.relation === 'uses' ? relation.from_node_id : relation.to_node_id,
      label: relation.relation === 'produces' ? '产出' : relation.relation === 'uses' ? '提供' : '提供信息',
      type: 'smoothstep',
      animated: true,
      markerEnd: { type: MarkerType.ArrowClosed, color: '#447675', width: 18, height: 18 },
      className: 'creator-edge',
    }))
    return { nodes: layout(nodes, edges, vertical), edges }
  }, [creator, selectedId, vertical])

  const layoutSignature = `${elements.nodes.map((node) => node.id).join(':')}|${elements.edges.map((edge) => `${edge.source}>${edge.target}`).join(':')}`
  useEffect(() => {
    if (!flow) return
    let frame = requestAnimationFrame(() => {
      frame = requestAnimationFrame(() => {
        void flow.fitView({ ...(vertical ? compactFitOptions : fitOptions), duration: 260 })
      })
    })
    return () => cancelAnimationFrame(frame)
  }, [flow, layoutSignature, vertical])

  return <ReactFlow
    nodes={elements.nodes}
    edges={elements.edges}
    nodeTypes={nodeTypes}
    onInit={setFlow}
    onNodeClick={(_, node) => node.id !== 'empty' && onSelect(node.id)}
    nodesDraggable={false}
    nodesConnectable={false}
    elementsSelectable={Boolean(creator)}
    deleteKeyCode={null}
    fitView
    fitViewOptions={vertical ? compactFitOptions : fitOptions}
    minZoom={0.5}
    maxZoom={1.35}
    proOptions={{ hideAttribution: true }}
  >
    <Background variant={BackgroundVariant.Dots} color="#c7d5d4" gap={22} size={1} />
    <Controls showInteractive={false} position="top-left" />
  </ReactFlow>
}
