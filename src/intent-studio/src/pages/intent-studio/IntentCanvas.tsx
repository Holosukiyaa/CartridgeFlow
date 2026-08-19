import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
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
import { AlertCircle, CheckCircle2, CircleDot, Eye, FilePlus2, FileText, Filter, Globe2, Maximize2, Minus, Plus, Puzzle, Send, UserRound } from 'lucide-react'
import type { CreatorProjection, CreatorRecipePreview } from '../../api.types.ts'
import { IconButton } from '../../ui/index.ts'

export type CreatorCanvasTool = 'inspect' | 'pointer' | 'lasso'
export type CreatorRelationKind = 'control' | 'data' | 'dependency'

type CanvasNodeData = {
  nodeId: string
  order: number
  label: string
  description: string
  state: 'empty' | 'review' | 'confirmed' | 'unresolved'
  kind: 'start' | 'end' | 'step'
  hasNestedCartridge: boolean
  targetPosition: Position
  sourcePosition: Position
  onOpenLayer: (nodeId: string) => void
  onPreviewLayer: (nodeId: string) => void
}

type CanvasNode = Node<CanvasNodeData, 'creator'>

function CreatorNode({ data, selected }: NodeProps<CanvasNode>) {
  const stateLabel = data.state === 'confirmed' ? '已确认' : data.state === 'unresolved' ? '待补齐' : data.state === 'empty' ? '等待编排' : '待审核'
  const StateIcon = data.state === 'confirmed' ? CheckCircle2 : data.state === 'unresolved' ? AlertCircle : CircleDot
  const icons = [Globe2, Filter, FilePlus2, FileText, UserRound, Send]
  const NodeIcon = icons[Math.max(0, data.order - 1) % icons.length] || FileText
  return <div className={`creator-node creator-node-${data.state} creator-node-order-${data.order} ${selected ? 'is-selected' : ''}`}>
    <Handle type="target" position={data.targetPosition} />
    <header className="creator-node-header">
      <span className="creator-node-order">{data.order ? String(data.order).padStart(2, '0') : 'AI'}</span>
      {data.order > 0 && <NodeIcon className="creator-node-kind" />}
      <span className="creator-node-title"><strong title={data.label}>{data.label}</strong></span>
      {data.kind === 'step' && <span className="creator-node-layer-actions">
        <IconButton label="进入第二层语义" variant="subtle" size="sm" onClick={(event) => { event.stopPropagation(); data.onOpenLayer(data.nodeId) }}><Puzzle /></IconButton>
        {data.hasNestedCartridge && <IconButton label="查看内部逻辑" variant="subtle" size="sm" onClick={(event) => { event.stopPropagation(); data.onPreviewLayer(data.nodeId) }}><Eye /></IconButton>}
      </span>}
    </header>
    <div className="creator-node-body">
      <p title={data.description}>{data.description}</p>
    </div>
    <footer className="creator-node-footer"><strong><StateIcon />{stateLabel}</strong></footer>
    <Handle type="source" position={data.sourcePosition} />
  </div>
}

const nodeTypes = { creator: CreatorNode }
const NODE_WIDTH = 280
const STEP_NODE_WIDTH = 300
const NESTED_NODE_WIDTH = 320
const MAX_STEP_NODE_WIDTH = 440
const NODE_HEIGHT = 168
const MAX_NODE_HEIGHT = 252
const CREATOR_LAYOUT_KEY = 'cartridgeflow.creator-layout.v3'
const fitOptions = {
  padding: { x: 0.08, top: '6%', bottom: '6%' },
  minZoom: 0.52,
  maxZoom: 1.12,
} as const
const compactFitOptions = {
  padding: 0.1,
  minZoom: 0.58,
  maxZoom: 0.9,
} as const
const multiRowFitOptions = {
  padding: { x: 0.08, top: '6%', bottom: '5%' },
  minZoom: 0.52,
  maxZoom: 1.08,
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

function nodeWidth(node: CanvasNode) {
  return typeof node.width === 'number' ? node.width : NODE_WIDTH
}

function stepNodeWidth(label: string, hasNestedCartridge: boolean) {
  const baseWidth = hasNestedCartridge ? NESTED_NODE_WIDTH : STEP_NODE_WIDTH
  const actionReserve = hasNestedCartridge ? 92 : 58
  const estimatedTitleWidth = Math.max(112, visualLength(label) * 9)
  return Math.min(MAX_STEP_NODE_WIDTH, Math.max(baseWidth, actionReserve + estimatedTitleWidth))
}

function visualLength(value: string) {
  return Array.from(value).reduce((length, character) => length + (/\p{Script=Han}/u.test(character) ? 1 : 0.56), 0)
}

function contentNodeHeight(label: string, description: string, width: number) {
  const titleLines = Math.min(2, Math.max(1, Math.ceil(visualLength(label) / Math.max(8, (width - 120) / 11))))
  const bodyLines = Math.min(4, Math.max(2, Math.ceil(visualLength(description) / Math.max(12, (width - 32) / 11))))
  return Math.min(MAX_NODE_HEIGHT, NODE_HEIGHT + (titleLines - 1) * 24 + (bodyLines - 2) * 18)
}

function layout(nodes: CanvasNode[], edges: Edge[], vertical: boolean) {
  if (!vertical && nodes.length > 1 && nodes.length <= 8) {
    const referencePositions = nodes.length === 2
      ? [{ x: 260, y: 220 }, { x: 760, y: 190 }]
      : [{ x: 80, y: 340 }, { x: 520, y: 170 }, { x: 1000, y: 20 }, { x: 690, y: 470 }, { x: 1160, y: 440 }, { x: 1510, y: 210 }, { x: 1840, y: 470 }, { x: 2170, y: 150 }]
    const columns = nodes.length > 6 ? 4 : 3
    const columnGap = nodes.length <= 3 ? 72 : nodes.length <= 6 ? 64 : 38
    const columnWidth = Math.max(...nodes.map(nodeWidth))
    const rowHeight = Math.max(...nodes.map((node) => node.height || NODE_HEIGHT))
    return nodes.map((node, index) => ({
      ...node,
      position: {
        x: referencePositions[index]?.x ?? (index < columns
          ? index * (columnWidth + columnGap)
          : (columns - 1 - ((index - columns) % columns)) * (columnWidth + columnGap)),
        y: referencePositions[index]?.y ?? (index < columns ? 0 : rowHeight + 120),
      },
    }))
  }
  const graph = new dagre.graphlib.Graph().setDefaultEdgeLabel(() => ({}))
  graph.setGraph({ rankdir: vertical ? 'TB' : 'LR', ranksep: vertical ? 54 : 66, nodesep: 48, marginx: 32, marginy: 36, acyclicer: 'greedy' })
  nodes.forEach((node) => graph.setNode(node.id, { width: nodeWidth(node), height: node.height || NODE_HEIGHT }))
  edges.forEach((edge) => graph.setEdge(edge.source, edge.target))
  dagre.layout(graph)
  return nodes.map((node) => {
    const point = graph.node(node.id)
    return { ...node, position: { x: point.x - nodeWidth(node) / 2, y: point.y - (node.height || NODE_HEIGHT) / 2 } }
  })
}

export function IntentCanvas({ creator, preview, draftGoal, selectedId, contextNodeIds, tool, visibleRelations, toolbar, onSelect, onContextChange, onOpenLayer, onPreviewLayer }: {
  creator: CreatorProjection | null
  preview: CreatorRecipePreview | null
  draftGoal: string
  selectedId: string
  contextNodeIds: string[]
  tool: CreatorCanvasTool
  visibleRelations: CreatorRelationKind[]
  toolbar?: ReactNode
  onSelect: (nodeId: string) => void
  onContextChange: (nodeIds: string[]) => void
  onOpenLayer: (nodeId: string) => void
  onPreviewLayer: (nodeId: string) => void
}) {
  const [flow, setFlow] = useState<ReactFlowInstance<CanvasNode, Edge> | null>(null)
  const [zoom, setZoom] = useState(1)
  const canvasHostRef = useRef<HTMLDivElement>(null)
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
        id: 'placeholder-start',
        type: 'creator',
        width: NODE_WIDTH,
        height: contentNodeHeight(draftGoal.trim() || '开始', draftGoal.trim() || '等待目标描述和语义编排。', NODE_WIDTH),
        position: { x: 0, y: 0 },
        data: {
          nodeId: 'placeholder-start',
          order: 1,
          label: '开始',
          description: draftGoal.trim() || '等待目标描述和语义编排。',
          state: 'unresolved',
          kind: 'start',
          hasNestedCartridge: false,
          targetPosition: vertical ? Position.Top : Position.Left,
          sourcePosition: vertical ? Position.Bottom : Position.Right,
          onOpenLayer,
          onPreviewLayer,
        },
        selectable: false,
      }, {
        id: 'placeholder-end',
        type: 'creator',
        width: NODE_WIDTH,
        height: contentNodeHeight('结束', '最终结果会在语义方案确认后落到这里。', NODE_WIDTH),
        position: { x: 0, y: 0 },
        data: {
          nodeId: 'placeholder-end',
          order: 2,
          label: '结束',
          description: '最终结果会在语义方案确认后落到这里。',
          state: 'unresolved',
          kind: 'end',
          hasNestedCartridge: false,
          targetPosition: vertical ? Position.Top : Position.Left,
          sourcePosition: vertical ? Position.Bottom : Position.Right,
          onOpenLayer,
          onPreviewLayer,
        },
        selectable: false,
      }]
      const edges: Edge[] = visibleRelations.includes('control') ? [{ id: 'placeholder-flow', source: 'placeholder-start', target: 'placeholder-end', type: 'bezier', className: 'creator-edge is-control' }] : []
      return { nodes: layout(nodes, edges, vertical), edges }
    }
    const confirmed = new Set(preview ? [] : creator.frozen_steps)
    const recipeNodes = preview?.nodes || creator.trusted_recipe.nodes
    const recipeRelations = preview?.relations || creator.trusted_recipe.relations
    const nodes: CanvasNode[] = recipeNodes.map((node, index) => {
      const hasNestedCartridge = typeof node.resolution === 'object' && Boolean(node.resolution?.capability)
      const width = stepNodeWidth(node.label, hasNestedCartridge)
      return {
        id: node.id,
        type: 'creator',
        width,
        height: contentNodeHeight(node.label, node.description, width),
        position: { x: 0, y: 0 },
        selected: tool === 'inspect' ? node.id === selectedId : contextNodeIds.includes(node.id),
        data: {
          nodeId: node.id,
          order: index + 1,
          label: node.label,
          description: node.description,
          state: (typeof node.resolution === 'string' ? node.resolution : node.resolution?.status) === 'unresolved' ? 'unresolved' : confirmed.has(node.id) ? 'confirmed' : 'review',
          kind: 'step',
          hasNestedCartridge,
          targetPosition: vertical ? Position.Top : recipeNodes.length <= 3 || index < 3 ? Position.Left : index === 3 ? Position.Top : Position.Right,
          sourcePosition: vertical ? Position.Bottom : recipeNodes.length <= 3 || index < 2 ? Position.Right : index === 2 || index === 3 ? Position.Bottom : Position.Left,
          onOpenLayer,
          onPreviewLayer,
        },
      }
    })
    const edges: Edge[] = recipeRelations.flatMap((relation) => {
      const kind: CreatorRelationKind = relation.relation === 'uses' ? 'dependency' : relation.relation === 'produces' ? 'data' : 'control'
      if (!visibleRelations.includes(kind)) return []
      return [{
      id: relation.id,
      source: relation.relation === 'uses' ? relation.to_node_id : relation.from_node_id,
      target: relation.relation === 'uses' ? relation.from_node_id : relation.to_node_id,
      /*
      label: relation.relation === 'produces' ? '产出' : relation.relation === 'uses' ? '提供' : '提供信息',
      */
      type: 'bezier',
      label: '\u4EA7\u51FA',
      animated: false,
      markerEnd: { type: MarkerType.ArrowClosed, color: '#9aa5af', width: 14, height: 14 },
      className: `creator-edge is-${kind}`,
      data: { kind },
    }]
    })
    return { nodes: layout(nodes, edges, vertical), edges }
  }, [contextNodeIds, creator, draftGoal, onOpenLayer, onPreviewLayer, preview, selectedId, tool, vertical, visibleRelations])

  const layoutScope = creator?.project_id ? `${creator.project_id}.${vertical ? 'vertical' : 'horizontal'}` : ''
  const layoutScopeRef = useRef(layoutScope)
  const [nodes, setNodes, onNodesChange] = useNodesState<CanvasNode>(elements.nodes)
  const layoutSignature = `${elements.nodes.map((node) => node.id).join(':')}|${elements.edges.map((edge) => `${edge.source}>${edge.target}`).join(':')}`
  const activeFitOptions = !creator ? emptyFitOptions : vertical ? compactFitOptions : elements.nodes.length > 3 ? multiRowFitOptions : fitOptions
  const correctHorizontalBounds = useCallback(async () => {
    if (!flow || vertical) return
    await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()))
    const host = canvasHostRef.current
    const frame = host?.closest('.vip-canvas-surface')?.getBoundingClientRect() || host?.getBoundingClientRect()
    if (!frame) return
    const toolstack = host?.querySelector('.semantic-canvas-toolstack')?.getBoundingClientRect()
    const nodeRects = [...(host?.querySelectorAll('.react-flow__node') || [])]
      .map((node) => node.getBoundingClientRect())
      .filter((rect) => rect.width > 0 && rect.height > 0)
    if (!nodeRects.length) return
    const left = Math.max(frame.left + 16, (toolstack?.right || frame.left) + 12)
    const right = frame.right - 16
    const currentLeft = Math.min(...nodeRects.map((rect) => rect.left))
    const currentRight = Math.max(...nodeRects.map((rect) => rect.right))
    const available = right - left
    const span = currentRight - currentLeft
    const viewport = flow.getViewport()
    const zoom = span > available && available > 0 ? Math.max(0.35, viewport.zoom * (available / span) * 0.98) : viewport.zoom
    const currentCenter = (currentLeft + currentRight) / 2
    const targetCenter = (left + right) / 2
    const flowCenter = (currentCenter - viewport.x) / viewport.zoom
    const nextX = targetCenter - flowCenter * zoom
    if (Math.abs(nextX - viewport.x) > 0.5 || Math.abs(zoom - viewport.zoom) > 0.005) {
      await flow.setViewport({ x: nextX, y: viewport.y, zoom }, { duration: 0 })
    }
  }, [flow, vertical])
  const fitCanvas = useCallback(async (duration: number) => {
    if (!flow) return
    await flow.fitView({ ...activeFitOptions, duration })
    if (!vertical) {
      const viewport = flow.getViewport()
      await flow.setViewport({ ...viewport, y: viewport.y - 9 }, { duration: 0 })
    }
    await correctHorizontalBounds()
  }, [activeFitOptions, correctHorizontalBounds, flow, vertical])
  const reframeCanvas = useCallback((duration: number) => {
    if (!flow) return
    const firstNode = flow.getNodes().find((node) => node.id !== 'empty')
    if (vertical && creator && firstNode) {
      void flow.setCenter(firstNode.position.x + nodeWidth(firstNode) / 2, firstNode.position.y + (firstNode.height || NODE_HEIGHT) / 2, { zoom: 0.82, duration })
    } else void fitCanvas(duration)
  }, [creator, fitCanvas, flow, vertical])
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
        reframeCanvas(260)
      })
    })
    return () => cancelAnimationFrame(frame)
  }, [flow, layoutSignature, reframeCanvas])

  useEffect(() => {
    if (!flow || !selectedId) return
    const selected = flow.getNode(selectedId)
    if (selected) void flow.setCenter(selected.position.x + nodeWidth(selected) / 2, selected.position.y + (selected.height || NODE_HEIGHT) / 2, { zoom: Math.max(flow.getZoom(), 0.85), duration: 220 })
  }, [flow, selectedId])

  useEffect(() => {
    const host = canvasHostRef.current
    if (!flow || !host) return
    let timer = 0
    let previousSize = ''
    const observer = new ResizeObserver(([entry]) => {
      const { width, height } = entry.contentRect
      if (width < 1 || height < 1) return
      const nextSize = `${Math.round(width)}x${Math.round(height)}`
      if (nextSize === previousSize) return
      previousSize = nextSize
      window.clearTimeout(timer)
      timer = window.setTimeout(() => reframeCanvas(180), 120)
    })
    observer.observe(host)
    return () => {
      observer.disconnect()
      window.clearTimeout(timer)
    }
  }, [flow, reframeCanvas])

  return <div className="vip-flow-host" ref={canvasHostRef}>
    {toolbar && <div className="semantic-canvas-tools">{toolbar}</div>}
    <ReactFlow
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
    minZoom={0.35}
    maxZoom={1.35}
    proOptions={{ hideAttribution: true }}
  >
    <Panel className="creator-zoom-controls" position="bottom-left">
      <IconButton label="缩小" variant="subtle" onClick={() => void flow?.zoomOut({ duration: 150 })}><Minus /></IconButton>
      <span>{Math.round(zoom * 100)}%</span>
      <IconButton label="放大" variant="subtle" onClick={() => void flow?.zoomIn({ duration: 150 })}><Plus /></IconButton>
      <IconButton label="适应画布" variant="subtle" onClick={() => void fitCanvas(180)}><Maximize2 /></IconButton>
    </Panel>
  </ReactFlow></div>
}
