import { useEffect, useMemo, useState } from 'react'
import dagre from '@dagrejs/dagre'
import {
  Background,
  BackgroundVariant,
  Controls,
  Handle,
  MarkerType,
  MiniMap,
  Position,
  ReactFlow,
  SelectionMode,
  type Edge,
  type Node,
  type NodeProps,
  type ReactFlowInstance,
} from '@xyflow/react'
import { Check, CircleDashed, Sparkles, Wrench } from 'lucide-react'
import type { CreatorProjection, CreatorRecipePreview } from '../../api.types.ts'

export type CreatorCanvasTool = 'inspect' | 'pointer' | 'lasso'

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
      <span className="creator-node-title"><strong title={data.label}>{data.label}</strong><small>{data.state === 'empty' ? '从想法开始' : '语义步骤'}</small></span>
      <span className="creator-node-state" title={stateLabel} aria-label={stateLabel}>{data.state === 'confirmed' ? <Check /> : data.state === 'empty' ? <Sparkles /> : data.state === 'unresolved' ? <Wrench /> : <CircleDashed />}</span>
    </header>
    <div className="creator-node-body">
      <span>这一步要完成</span>
      <p title={data.description}>{data.description}</p>
    </div>
    <footer className="creator-node-footer"><span>步骤 {data.order || '—'}</span><strong>{stateLabel}</strong></footer>
    <Handle type="source" position={data.direction === 'vertical' ? Position.Bottom : Position.Right} />
  </div>
}

const nodeTypes = { creator: CreatorNode }
const fitOptions = {
  padding: 0.12,
  minZoom: 0.55,
  maxZoom: 1,
} as const
const compactFitOptions = {
  padding: 0.1,
  minZoom: 0.48,
  maxZoom: 0.84,
} as const
const emptyFitOptions = {
  padding: 0.35,
  minZoom: 0.65,
  maxZoom: 0.9,
} as const

function layout(nodes: CanvasNode[], edges: Edge[], vertical: boolean) {
  if (!vertical && nodes.length > 1 && nodes.length <= 6) {
    return nodes.map((node, index) => ({
      ...node,
      position: { x: (index % 3) * 326, y: Math.floor(index / 3) * 252 },
    }))
  }
  const graph = new dagre.graphlib.Graph().setDefaultEdgeLabel(() => ({}))
  graph.setGraph({ rankdir: vertical ? 'TB' : 'LR', ranksep: vertical ? 42 : 56, nodesep: 44, marginx: 32, marginy: 36, acyclicer: 'greedy' })
  nodes.forEach((node) => graph.setNode(node.id, { width: 256, height: 178 }))
  edges.forEach((edge) => graph.setEdge(edge.source, edge.target))
  dagre.layout(graph)
  return nodes.map((node) => {
    const point = graph.node(node.id)
    return { ...node, position: { x: point.x - 128, y: point.y - 89 } }
  })
}

export function IntentCanvas({ creator, preview, draftGoal, selectedId, contextNodeIds, tool, onSelect, onContextChange }: {
  creator: CreatorProjection | null
  preview: CreatorRecipePreview | null
  draftGoal: string
  selectedId: string
  contextNodeIds: string[]
  tool: CreatorCanvasTool
  onSelect: (nodeId: string) => void
  onContextChange: (nodeIds: string[]) => void
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
        width: 256,
        height: 178,
        position: { x: 0, y: 0 },
        data: {
          order: 0,
          label: draftGoal.trim() ? '当前想法' : '从一句话开始',
          description: draftGoal.trim() || '告诉 AI 你想得到什么，大纲会立刻出现在这里。',
          state: 'empty',
          direction: vertical ? 'vertical' : 'horizontal',
        },
        selectable: false,
      }]
      return { nodes: layout(nodes, [], vertical), edges: [] as Edge[] }
    }
    const confirmed = new Set(preview ? [] : creator.frozen_steps)
    const recipeNodes = preview?.nodes || creator.trusted_recipe.nodes
    const recipeRelations = preview?.relations || creator.trusted_recipe.relations
    const nodes: CanvasNode[] = recipeNodes.map((node, index) => ({
      id: node.id,
      type: 'creator',
      width: 256,
      height: 178,
      position: { x: 0, y: 0 },
      selected: tool === 'inspect' ? node.id === selectedId : contextNodeIds.includes(node.id),
      data: {
        order: index + 1,
        label: node.label,
        description: node.description,
        state: (typeof node.resolution === 'string' ? node.resolution : node.resolution?.status) === 'unresolved' ? 'unresolved' : confirmed.has(node.id) ? 'confirmed' : 'review',
        direction: vertical ? 'vertical' : 'horizontal',
      },
    }))
    const edges: Edge[] = recipeRelations.map((relation) => ({
      id: relation.id,
      source: relation.relation === 'uses' ? relation.to_node_id : relation.from_node_id,
      target: relation.relation === 'uses' ? relation.from_node_id : relation.to_node_id,
      label: relation.relation === 'produces' ? '产出' : relation.relation === 'uses' ? '提供' : '提供信息',
      type: 'smoothstep',
      animated: true,
      markerEnd: { type: MarkerType.ArrowClosed, color: '#87949a', width: 18, height: 18 },
      className: 'creator-edge',
    }))
    return { nodes: layout(nodes, edges, vertical), edges }
  }, [contextNodeIds, creator, draftGoal, preview, selectedId, tool, vertical])

  const layoutSignature = `${elements.nodes.map((node) => node.id).join(':')}|${elements.edges.map((edge) => `${edge.source}>${edge.target}`).join(':')}`
  const activeFitOptions = !creator ? emptyFitOptions : vertical ? compactFitOptions : fitOptions
  useEffect(() => {
    if (!flow) return
    let frame = requestAnimationFrame(() => {
      frame = requestAnimationFrame(() => {
        void flow.fitView({ ...activeFitOptions, duration: 260 })
      })
    })
    return () => cancelAnimationFrame(frame)
  }, [activeFitOptions, flow, layoutSignature])

  useEffect(() => {
    if (!flow) return
    let frame = 0
    const refit = () => {
      cancelAnimationFrame(frame)
      frame = requestAnimationFrame(() => void flow.fitView({ ...activeFitOptions, duration: 180 }))
    }
    window.addEventListener('resize', refit)
    return () => {
      window.removeEventListener('resize', refit)
      cancelAnimationFrame(frame)
    }
  }, [activeFitOptions, flow])

  return <ReactFlow
    nodes={elements.nodes}
    edges={elements.edges}
    nodeTypes={nodeTypes}
    onInit={setFlow}
    onNodeClick={(event, node) => {
      if (node.id === 'empty') return
      if (tool === 'pointer') {
        event.preventDefault()
        onContextChange([node.id])
        return
      }
      if (tool === 'inspect') onSelect(node.id)
    }}
    onSelectionChange={({ nodes }) => {
      if (tool !== 'lasso') return
      const nextNodeIds = nodes.map((node) => node.id).sort()
      const currentNodeIds = [...contextNodeIds].sort()
      if (nextNodeIds.length === currentNodeIds.length && nextNodeIds.every((nodeId, index) => nodeId === currentNodeIds[index])) return
      onContextChange(nextNodeIds)
    }}
    onPaneClick={() => {
      if (tool === 'inspect') onSelect('')
    }}
    nodesDraggable={false}
    nodesConnectable={false}
    elementsSelectable={Boolean(creator)}
    selectionOnDrag={tool === 'lasso'}
    selectionMode={SelectionMode.Partial}
    panOnDrag={tool === 'lasso' ? [1, 2] : true}
    deleteKeyCode={null}
    fitView
    fitViewOptions={activeFitOptions}
    minZoom={0.5}
    maxZoom={1.35}
    proOptions={{ hideAttribution: true }}
  >
    <Background variant={BackgroundVariant.Lines} color="var(--intent-line)" gap={46} size={1} />
    <Controls showInteractive={false} position="bottom-left" />
    <MiniMap
      pannable
      zoomable
      position="bottom-left"
      nodeBorderRadius={2}
      nodeColor={(node) => node.selected ? 'var(--intent-accent)' : '#aeb5b0'}
      nodeStrokeColor="#8d9591"
      maskColor="rgba(240, 243, 244, .64)"
    />
  </ReactFlow>
}
