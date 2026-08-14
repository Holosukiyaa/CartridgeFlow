import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import dagre from '@dagrejs/dagre'
import {
  Handle,
  MarkerType,
  Panel,
  Position,
  ReactFlow,
  SelectionMode,
  type Edge,
  type Node,
  type NodeProps,
  type ReactFlowInstance,
  useNodesState,
} from '@xyflow/react'
import { CheckCircle2, Circle, FilePlus2, FileText, Filter, Globe2, Maximize2, Minus, Plus, Send, UserRound } from 'lucide-react'
import type { CreatorProjection, CreatorRecipePreview } from '../../api.types.ts'

export type CreatorCanvasTool = 'inspect' | 'pointer' | 'lasso'

type CanvasNodeData = {
  order: number
  label: string
  description: string
  state: 'empty' | 'review' | 'confirmed' | 'unresolved'
  targetPosition: Position
  sourcePosition: Position
}

type CanvasNode = Node<CanvasNodeData, 'creator'>

function CreatorNode({ data, selected }: NodeProps<CanvasNode>) {
  const stateLabel = data.state === 'confirmed' ? '已确认' : data.state === 'review' ? '待审核' : data.state === 'unresolved' ? '待补齐能力' : '空白画布'
  const icons = [Globe2, Filter, FilePlus2, FileText, UserRound, Send]
  const NodeIcon = icons[Math.max(0, data.order - 1) % icons.length] || FileText
  return <div className={`creator-node creator-node-${data.state} creator-node-order-${data.order} ${selected ? 'is-selected' : ''}`}>
    <Handle type="target" position={data.targetPosition} />
    <header className="creator-node-header">
      <span className="creator-node-order">{data.order ? String(data.order).padStart(2, '0') : 'AI'}</span>
      {data.order > 0 && <NodeIcon className="creator-node-kind" />}
      <span className="creator-node-title"><strong title={data.label}>{data.label}</strong></span>
    </header>
    <div className="creator-node-body">
      <p title={data.description}>{data.description}</p>
    </div>
    <footer className="creator-node-footer"><strong>{data.state === 'confirmed' ? <CheckCircle2 /> : <Circle />}{stateLabel}</strong></footer>
    <Handle type="source" position={data.sourcePosition} />
  </div>
}

const nodeTypes = { creator: CreatorNode }
const NODE_WIDTH = 204
const NODE_HEIGHT = 174
const CREATOR_LAYOUT_KEY = 'cartridgeflow.creator-layout.v2'
const fitOptions = {
  padding: { x: 0.04, top: '7%', bottom: '7%' },
  minZoom: 0.7,
  maxZoom: 1,
} as const
const compactFitOptions = {
  padding: 0.1,
  minZoom: 0.58,
  maxZoom: 0.9,
} as const
const multiRowFitOptions = {
  padding: { x: 0.025, top: '7%', bottom: '5%' },
  minZoom: 0.64,
  maxZoom: 1,
} as const
const emptyFitOptions = {
  padding: 0.35,
  minZoom: 0.65,
  maxZoom: 0.9,
} as const

function readSavedPositions(projectId: string) {
  if (!projectId) return {} as Record<string, { x: number; y: number }>
  try {
    const saved = JSON.parse(localStorage.getItem(`${CREATOR_LAYOUT_KEY}.${projectId}`) || '{}')
    if (!saved || typeof saved !== 'object' || Array.isArray(saved)) return {}
    return Object.fromEntries(Object.entries(saved).filter(([, value]) => {
      if (!value || typeof value !== 'object' || Array.isArray(value)) return false
      const point = value as { x?: unknown; y?: unknown }
      return Number.isFinite(point.x) && Number.isFinite(point.y)
    })) as Record<string, { x: number; y: number }>
  } catch {
    return {}
  }
}

function savePositions(projectId: string, nodes: CanvasNode[]) {
  if (!projectId) return
  const positions = Object.fromEntries(nodes.filter((node) => node.id !== 'empty').map((node) => [node.id, node.position]))
  localStorage.setItem(`${CREATOR_LAYOUT_KEY}.${projectId}`, JSON.stringify(positions))
}

function layout(nodes: CanvasNode[], edges: Edge[], vertical: boolean) {
  if (!vertical && nodes.length > 1 && nodes.length <= 8) {
    const columns = nodes.length > 6 ? 4 : 3
    const columnGap = nodes.length <= 3 ? 90 : nodes.length <= 6 ? 90 : 38
    return nodes.map((node, index) => ({
      ...node,
      position: {
        x: index < columns
          ? index * (NODE_WIDTH + columnGap)
          : index === columns && columns === 3
            ? 557
            : index === columns + 1 && columns === 3
              ? 280
              : (columns - 1 - ((index - columns) % columns)) * (NODE_WIDTH + columnGap),
        y: index < columns ? 0 : index === columns ? 294 : 460,
      },
    }))
  }
  const graph = new dagre.graphlib.Graph().setDefaultEdgeLabel(() => ({}))
  graph.setGraph({ rankdir: vertical ? 'TB' : 'LR', ranksep: vertical ? 54 : 66, nodesep: 48, marginx: 32, marginy: 36, acyclicer: 'greedy' })
  nodes.forEach((node) => graph.setNode(node.id, { width: NODE_WIDTH, height: NODE_HEIGHT }))
  edges.forEach((edge) => graph.setEdge(edge.source, edge.target))
  dagre.layout(graph)
  return nodes.map((node) => {
    const point = graph.node(node.id)
    return { ...node, position: { x: point.x - NODE_WIDTH / 2, y: point.y - NODE_HEIGHT / 2 } }
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
  const [zoom, setZoom] = useState(1)
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
        width: NODE_WIDTH,
        height: NODE_HEIGHT,
        position: { x: 0, y: 0 },
        data: {
          order: 0,
          label: draftGoal.trim() ? '当前想法' : '从一句话开始',
          description: draftGoal.trim() || '告诉 AI 你想得到什么，大纲会立刻出现在这里。',
          state: 'empty',
          targetPosition: vertical ? Position.Top : Position.Left,
          sourcePosition: vertical ? Position.Bottom : Position.Right,
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
      width: NODE_WIDTH,
      height: NODE_HEIGHT,
      position: { x: 0, y: 0 },
      selected: tool === 'inspect' ? node.id === selectedId : contextNodeIds.includes(node.id),
      data: {
        order: index + 1,
        label: node.label,
        description: node.description,
        state: (typeof node.resolution === 'string' ? node.resolution : node.resolution?.status) === 'unresolved' ? 'unresolved' : confirmed.has(node.id) ? 'confirmed' : 'review',
        targetPosition: vertical ? Position.Top : recipeNodes.length <= 3 || index < 3 ? Position.Left : index === 3 ? Position.Top : Position.Right,
        sourcePosition: vertical ? Position.Bottom : recipeNodes.length <= 3 || index < 2 ? Position.Right : index === 2 || index === 3 ? Position.Bottom : Position.Left,
      },
    }))
    const edges: Edge[] = recipeRelations.map((relation) => ({
      id: relation.id,
      source: relation.relation === 'uses' ? relation.to_node_id : relation.from_node_id,
      target: relation.relation === 'uses' ? relation.from_node_id : relation.to_node_id,
      label: relation.relation === 'produces' ? '产出' : relation.relation === 'uses' ? '提供' : '提供信息',
      type: 'smoothstep',
      animated: false,
      markerEnd: { type: MarkerType.ArrowClosed, color: '#9aa5af', width: 14, height: 14 },
      className: 'creator-edge',
    }))
    return { nodes: layout(nodes, edges, vertical), edges }
  }, [contextNodeIds, creator, draftGoal, preview, selectedId, tool, vertical])

  const layoutScope = creator?.project_id ? `${creator.project_id}.${vertical ? 'vertical' : 'horizontal'}` : ''
  const layoutScopeRef = useRef(layoutScope)
  const [nodes, setNodes, onNodesChange] = useNodesState<CanvasNode>(elements.nodes)
  const layoutSignature = `${elements.nodes.map((node) => node.id).join(':')}|${elements.edges.map((edge) => `${edge.source}>${edge.target}`).join(':')}`
  const activeFitOptions = !creator ? emptyFitOptions : vertical ? compactFitOptions : elements.nodes.length > 3 ? multiRowFitOptions : fitOptions
  const fitCanvas = useCallback(async (duration: number) => {
    if (!flow) return
    await flow.fitView({ ...activeFitOptions, duration })
    if (!vertical) {
      const viewport = flow.getViewport()
      await flow.setViewport({ ...viewport, x: viewport.x - 9, y: viewport.y - 9 })
    }
  }, [activeFitOptions, flow, vertical])
  useEffect(() => {
    const sameScope = layoutScopeRef.current === layoutScope
    const saved = readSavedPositions(layoutScope)
    setNodes((current) => {
      const currentById = new Map(current.map((node) => [node.id, node]))
      return elements.nodes.map((node) => ({
        ...node,
        position: sameScope ? currentById.get(node.id)?.position || saved[node.id] || node.position : saved[node.id] || node.position,
      }))
    })
    layoutScopeRef.current = layoutScope
  }, [elements.nodes, layoutScope, setNodes])

  useEffect(() => {
    if (!flow) return
    let frame = requestAnimationFrame(() => {
      frame = requestAnimationFrame(() => {
        const firstNode = flow.getNodes().find((node) => node.id !== 'empty')
        if (vertical && creator && firstNode) {
          void flow.setCenter(firstNode.position.x + NODE_WIDTH / 2, firstNode.position.y + NODE_HEIGHT / 2, { zoom: 0.82, duration: 260 })
        } else void fitCanvas(260)
      })
    })
    return () => cancelAnimationFrame(frame)
  }, [creator, fitCanvas, flow, layoutSignature, vertical])

  useEffect(() => {
    if (!flow) return
    let frame = 0
    let timer = 0
    const refit = () => {
      cancelAnimationFrame(frame)
      window.clearTimeout(timer)
      frame = requestAnimationFrame(() => {
        timer = window.setTimeout(() => {
          const firstNode = flow.getNodes().find((node) => node.id !== 'empty')
          if (vertical && creator && firstNode) {
            void flow.setCenter(firstNode.position.x + NODE_WIDTH / 2, firstNode.position.y + NODE_HEIGHT / 2, { zoom: 0.82, duration: 180 })
          } else void fitCanvas(180)
        }, 120)
      })
    }
    window.addEventListener('resize', refit)
    return () => {
      window.removeEventListener('resize', refit)
      cancelAnimationFrame(frame)
      window.clearTimeout(timer)
    }
  }, [creator, fitCanvas, flow, vertical])

  return <ReactFlow
    nodes={nodes}
    edges={elements.edges}
    nodeTypes={nodeTypes}
    onInit={setFlow}
    onNodesChange={onNodesChange}
    onNodeDragStop={(_, movedNode) => {
      if (!layoutScope || movedNode.id === 'empty') return
      savePositions(layoutScope, nodes.map((node) => node.id === movedNode.id ? { ...node, position: movedNode.position } : node))
    }}
    onNodeClick={(event, node) => {
      if (node.id === 'empty') return
      if (tool === 'pointer') {
        event.preventDefault()
        onContextChange([node.id])
        return
      }
      if (tool === 'inspect') onSelect(node.id)
    }}
    onSelectionEnd={() => {
      if (tool !== 'lasso' || !flow) return
      const nextNodeIds = flow.getNodes().filter((node) => node.selected).map((node) => node.id).sort()
      const currentNodeIds = [...contextNodeIds].sort()
      if (nextNodeIds.length === currentNodeIds.length && nextNodeIds.every((nodeId, index) => nodeId === currentNodeIds[index])) return
      onContextChange(nextNodeIds)
    }}
    onPaneClick={() => {
      if (tool === 'inspect') onSelect('')
    }}
    onMoveEnd={(_, viewport) => setZoom(viewport.zoom)}
    nodesDraggable={Boolean(creator) && tool === 'inspect'}
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
    <Panel className="creator-zoom-controls" position="bottom-left">
      <button type="button" title="缩小" aria-label="缩小" onClick={() => void flow?.zoomOut({ duration: 150 })}><Minus /></button>
      <span>{Math.round(zoom * 100)}%</span>
      <button type="button" title="放大" aria-label="放大" onClick={() => void flow?.zoomIn({ duration: 150 })}><Plus /></button>
      <button type="button" title="适应画布" aria-label="适应画布" onClick={() => void fitCanvas(180)}><Maximize2 /></button>
    </Panel>
  </ReactFlow>
}
