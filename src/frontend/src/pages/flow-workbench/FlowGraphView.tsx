import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import {
  ReactFlow,
  Background,
  BackgroundVariant,
  ConnectionLineType,
  MarkerType,
  MiniMap,
  Panel,
  ViewportPortal,
  addEdge,
  applyEdgeChanges,
  applyNodeChanges,
  getViewportForBounds,
  type Connection,
  type Edge,
  type EdgeChange,
  type Node,
  type NodeChange,
  type ReactFlowInstance,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { AlignHorizontalSpaceAround, Box, Braces, BrainCircuit, GitBranch, GripVertical, Lock, Maximize, Maximize2, MessageSquare, MousePointer2, Settings, Unlock, Wrench, ZoomIn, ZoomOut } from 'lucide-react'
import type { FlowEdge, FlowEvent, FlowGraph, FlowNode } from '../../api.ts'
import { showToast } from '../../toast.tsx'
import type { CreateNodeHandler, NodeCategoryId } from './types.ts'
import { FLOW_NODE_DIMENSIONS, NODE_CATEGORIES, buildAutoAlignLayout, buildBalancedLayout, getNodeCategory, getPreset, getPresets, isStartNode, type FlowNodeViewMode } from './nodeModel.ts'
import { getAvailableNodeDetailSections, type NodeDetailSection } from './nodeDetails.ts'
import type { NodeRunState } from './TestBenchView.tsx'
import { FlowNodeCard, type FlowNodeProbeState } from './FlowNodeCard.tsx'
import { createPortCounts, getPortHandleId, type EdgePortAssignment, type PortCounts, type PortSide } from './FlowNodePorts.tsx'

type FlowGraphNode = Node<Record<string, unknown>>
type FlowGraphEdge = Edge<Record<string, unknown>>
type RunEdgeStatus = 'visited' | 'active'
type CanvasTool = 'select' | 'connect'
type CanvasPanel = 'nodes' | 'notes' | 'models' | 'variables' | 'settings' | 'tools' | null
type CanvasNodeEditor = {
  editorId: string
  nodeId: string
  section: NodeDetailSection
  width: number
  height: number
  connectorFraction: number
  position?: NodeEditorPosition
  content: ReactNode
}
type NodeEditorSide = 'top' | 'right' | 'bottom' | 'left'
type NodeEditorPosition = { x: number; y: number }
type NodeEditorPlacement = CanvasNodeEditor & NodeEditorPosition & { side: NodeEditorSide }
type NodeEditorDragState = NodeEditorPosition & {
  editorId: string
  nodeId: string
  pointerId: number
  clientX: number
  clientY: number
  zoom: number
}
type DetailConnector = {
  path: string
  source: { x: number; y: number }
  target: { x: number; y: number }
}

const PORT_LIMIT = 5
const EMPTY_FLOW_EVENTS: FlowEvent[] = []
const NODE_TEMPLATE_MIME = 'application/x-cf-node-template'
const NODE_EDITOR_GAP = 140
const NODE_EDITOR_SLOT_WIDTH = 410
const NODE_EDITOR_SLOT_HEIGHT = 340

function getGraphNodeSize(node: FlowGraphNode) {
  const styleWidth = typeof node.style?.width === 'number' ? node.style.width : 0
  const styleHeight = typeof node.style?.height === 'number' ? node.style.height : 0
  return {
    width: node.width || node.measured?.width || styleWidth || FLOW_NODE_DIMENSIONS.detailed.width,
    height: node.height || node.measured?.height || styleHeight || FLOW_NODE_DIMENSIONS.detailed.height,
  }
}

function resolveEditorSide(node: FlowGraphNode, position: NodeEditorPosition, width: number, height: number): NodeEditorSide {
  const nodeSize = getGraphNodeSize(node)
  const nodeCenterX = node.position.x + nodeSize.width / 2
  const nodeCenterY = node.position.y + nodeSize.height / 2
  const editorCenterX = position.x + width / 2
  const editorCenterY = position.y + height / 2
  const dx = editorCenterX - nodeCenterX
  const dy = editorCenterY - nodeCenterY
  if (Math.abs(dx) >= Math.abs(dy)) return dx >= 0 ? 'right' : 'left'
  return dy >= 0 ? 'bottom' : 'top'
}

function buildDetailConnector(node: FlowGraphNode, editor: NodeEditorPlacement): DetailConnector {
  const { width: nodeWidth, height: nodeHeight } = getGraphNodeSize(node)
  const horizontal = editor.side === 'left' || editor.side === 'right'

  const fraction = editor.connectorFraction
  let source: DetailConnector['source']
  let target: DetailConnector['target']
  let path = ''
  if (horizontal) {
    const direction = editor.side === 'right' ? 1 : -1
    source = {
      x: node.position.x + (direction > 0 ? nodeWidth : 0),
      y: node.position.y + nodeHeight * fraction,
    }
    target = {
      x: editor.x + (direction > 0 ? 0 : editor.width),
      y: editor.y + editor.height / 2,
    }
    const bend = Math.max(72, Math.abs(target.x - source.x) * 0.42)
    path = `M ${source.x} ${source.y} C ${source.x + bend * direction} ${source.y}, ${target.x - bend * direction} ${target.y}, ${target.x} ${target.y}`
  } else {
    const direction = editor.side === 'bottom' ? 1 : -1
    source = {
      x: node.position.x + nodeWidth * fraction,
      y: node.position.y + (direction > 0 ? nodeHeight : 0),
    }
    target = {
      x: editor.x + editor.width / 2,
      y: editor.y + (direction > 0 ? 0 : editor.height),
    }
    const bend = Math.max(72, Math.abs(target.y - source.y) * 0.42)
    path = `M ${source.x} ${source.y} C ${source.x} ${source.y + bend * direction}, ${target.x} ${target.y - bend * direction}, ${target.x} ${target.y}`
  }
  return { path, source, target }
}

function chooseEdgeSides(sourcePoint?: { x: number; y: number }, targetPoint?: { x: number; y: number }): { sourceSide: PortSide; targetSide: PortSide } {
  if (!sourcePoint || !targetPoint) return { sourceSide: 'right', targetSide: 'left' }
  const dx = targetPoint.x - sourcePoint.x
  const dy = targetPoint.y - sourcePoint.y
  const absX = Math.abs(dx)
  const absY = Math.abs(dy)
  if (absY > absX * 0.7) {
    return dy >= 0
      ? { sourceSide: 'bottom', targetSide: 'top' }
      : { sourceSide: 'top', targetSide: 'bottom' }
  }
  return dx >= 0
    ? { sourceSide: 'right', targetSide: 'left' }
    : { sourceSide: 'left', targetSide: 'right' }
}

function chooseHorizontalEdgeSides(sourcePoint?: { x: number; y: number }, targetPoint?: { x: number; y: number }): { sourceSide: PortSide; targetSide: PortSide } {
  if (!sourcePoint || !targetPoint) return { sourceSide: 'right', targetSide: 'left' }
  return targetPoint.x >= sourcePoint.x
    ? { sourceSide: 'right', targetSide: 'left' }
    : { sourceSide: 'left', targetSide: 'right' }
}

function normalizeGraphEdges(edges: FlowEdge[] = []) {
  const seen = new Set<string>()
  return edges.reduce<FlowEdge[]>((result, edge) => {
    if (!edge?.from || !edge?.to || edge.from === edge.to) return result
    const scope = String(edge.scope || 'root')
    const label = String(edge.label || '').trim()
    const key = `${scope}:${edge.from}->${edge.to}:${scope === 'branch' ? label : ''}`
    if (seen.has(key)) return result
    seen.add(key)
    result.push({ ...edge, scope, ...(label ? { label } : {}) })
    return result
  }, [])
}

async function copyNodeText(node: FlowNode, mode: 'id' | 'config') {
  const value = mode === 'id' ? node.id : JSON.stringify(node, null, 2)
  try {
    await navigator.clipboard.writeText(value)
    showToast({ title: mode === 'id' ? '节点 ID 已复制' : '节点配置已复制', type: 'success' })
  } catch (error: any) {
    showToast({ title: '复制失败', description: error?.message || String(error), type: 'error' })
  }
}

function buildRunEdgeStates(graphEdges: FlowEdge[], runEvents: FlowEvent[] = EMPTY_FLOW_EVENTS) {
  const edgePairs = new Set(graphEdges.map((edge) => `${edge.from}->${edge.to}`))
  const explicitEdges = runEvents.reduce<Array<{ key: string; index: number }>>((result, event, index) => {
    if (event.type !== 'flow_edge_traversed') return result
    const source = String((event.data as any)?.from || '').trim()
    const target = String((event.data as any)?.to || '').trim()
    const key = `${source}->${target}`
    if (source && target && edgePairs.has(key)) result.push({ key, index })
    return result
  }, [])
  const enteredStates = runEvents.reduce<Array<{ state: string; index: number }>>((result, event, index) => {
    if (event.type === 'state_entered' && event.state) result.push({ state: event.state, index })
    return result
  }, [])
  const edgeStates = new Map<string, RunEdgeStatus>()

  if (explicitEdges.length) {
    explicitEdges.forEach(({ key }) => edgeStates.set(key, 'visited'))
  } else {
    graphEdges.forEach((edge) => {
      const sourceIndexes = enteredStates.flatMap((entry) => entry.state === edge.from ? [entry.index] : [])
      const targetIndexes = enteredStates.flatMap((entry) => entry.state === edge.to ? [entry.index] : [])
      const traversed = sourceIndexes.some((sourceIndex) => targetIndexes.some((targetIndex) => targetIndex > sourceIndex))
      if (traversed) edgeStates.set(`${edge.from}->${edge.to}`, 'visited')
    })
  }

  const latestEntered = enteredStates[enteredStates.length - 1]
  const latestExplicit = explicitEdges[explicitEdges.length - 1]
  if (latestExplicit && (!latestEntered || latestExplicit.index > latestEntered.index)) {
    edgeStates.set(latestExplicit.key, 'active')
    return edgeStates
  }

  const latestNodeFailed = latestEntered && runEvents.slice(latestEntered.index + 1).some((event) => {
    return event.state === latestEntered.state && event.type === 'lab_node_failed'
  })
  if (latestEntered && !latestNodeFailed) {
    const outgoing = graphEdges.filter((edge) => edge.from === latestEntered.state)
    const mainOutgoing = outgoing.filter((edge) => edge.scope !== 'branch')
    ;(mainOutgoing.length ? mainOutgoing : outgoing).forEach((edge) => {
      edgeStates.set(`${edge.from}->${edge.to}`, 'active')
    })
  }
  return edgeStates
}

export function FlowGraphView({ graph, selectedNode, focusNodeId, onSelectNode, onOpenNodeEditor, onNodeEditorPositionChange, onLayoutSave, onEdgesSave, onCreateNode, onDeleteNode, modelPanel, toolPanel, nodeEditors = [], activeNodeEditorId, onCloseNodeEditor, compactStatic = false, readOnlyGraph = false, nodeRunStates, runEvents, testProbeState }: {
  graph: FlowGraph
  selectedNode: FlowNode | null
  focusNodeId: string | null
  onSelectNode: (node: FlowNode) => void
  onOpenNodeEditor?: (node: FlowNode, section: NodeDetailSection) => void
  onNodeEditorPositionChange?: (editorId: string, position: NodeEditorPosition) => void
  onLayoutSave?: (layout: Record<string, { x: number; y: number }>) => Promise<void>
  onEdgesSave?: (edges: FlowEdge[]) => Promise<void>
  onCreateNode?: CreateNodeHandler
  onDeleteNode?: (node: FlowNode) => Promise<void>
  modelPanel?: ReactNode
  toolPanel?: ReactNode
  nodeEditors?: CanvasNodeEditor[]
  activeNodeEditorId?: string | null
  onCloseNodeEditor?: () => void
  compactStatic?: boolean
  readOnlyGraph?: boolean
  nodeRunStates?: Map<string, NodeRunState>
  runEvents?: FlowEvent[]
  testProbeState?: FlowNodeProbeState
}) {
  const [fullscreen, setFullscreen] = useState(false)
  const [activeCanvasTool, setActiveCanvasTool] = useState<CanvasTool>('select')
  const [canvasPanel, setCanvasPanel] = useState<CanvasPanel>(null)
  const [selectedLibraryCategoryId, setSelectedLibraryCategoryId] = useState<NodeCategoryId | null>(null)
  const [selectedLibraryPresetId, setSelectedLibraryPresetId] = useState('')
  const [libraryPresetConfig, setLibraryPresetConfig] = useState<Record<string, string>>({})
  const [canvasLocked, setCanvasLocked] = useState(false)
  const gridSize = 10
  const [gridSnap, setGridSnap] = useState(true)
  const [contextMenu, setContextMenu] = useState<{ x: number; y: number; node: FlowNode | null; edge?: FlowGraphEdge | null } | null>(null)
  const [flowInstance, setFlowInstance] = useState<ReactFlowInstance | null>(null)
  const [nodeEditorPositions, setNodeEditorPositions] = useState<Record<string, NodeEditorPosition>>({})
  const [draggingEditorId, setDraggingEditorId] = useState<string | null>(null)
  const wrapperRef = useRef<HTMLDivElement | null>(null)
  const deletingNodeRef = useRef(false)
  const lastFittedGraphIdRef = useRef('')
  const openEditorIdsRef = useRef<Set<string>>(new Set())
  const nodeEditorDragRef = useRef<NodeEditorDragState | null>(null)
  const rightGestureRef = useRef<{ x: number; y: number; moved: boolean } | null>(null)
  const suppressContextMenuUntilRef = useRef(0)
  const nodeOrder = useMemo(() => new Map(graph.nodes.map((node, index) => [node.id, index + 1])), [graph.nodes])
  const nodeById = useMemo(() => new Map(graph.nodes.map((node) => [node.id, node])), [graph.nodes])
  const probeSelectedNodeIds = useMemo(() => new Set(testProbeState?.selectedNodeIds || []), [testProbeState?.selectedNodeIds])
  const graphEdges = useMemo(() => normalizeGraphEdges(graph.edges), [graph.edges])
  const stableRunEvents = runEvents ?? EMPTY_FLOW_EVENTS
  const runEdgeStates = useMemo(() => buildRunEdgeStates(graphEdges, stableRunEvents), [graphEdges, stableRunEvents])
  const renderGraph = useMemo(() => ({ ...graph, edges: graphEdges }), [graph, graphEdges])
  const selectedLibraryCategory = useMemo(
    () => NODE_CATEGORIES.find((category) => category.id === selectedLibraryCategoryId) || null,
    [selectedLibraryCategoryId],
  )
  const selectedLibraryPreset = useMemo(
    () => selectedLibraryCategory ? getPreset(selectedLibraryCategory.id, selectedLibraryPresetId) : null,
    [selectedLibraryCategory, selectedLibraryPresetId],
  )
  const canvasVariables = useMemo(() => {
    const variables = new Map<string, { name: string; source: string; kind: string }>()
    graph.nodes.forEach((node) => {
      const params = node.params || {}
      const candidates = [
        { value: params.input, kind: '输入' },
        { value: params.output, kind: '输出' },
        { value: params.save_to, kind: '存储' },
        { value: node.primary_output, kind: '主输出' },
      ]
      candidates.forEach(({ value, kind }) => {
        const name = String(value || '').trim()
        if (name && !variables.has(name)) variables.set(name, { name, source: node.display_name || node.title || node.id, kind })
      })
    })
    return [...variables.values()]
  }, [graph.nodes])
  const canvasNotes = useMemo(() => graph.nodes.flatMap((node) => {
    const note = String(node.params?.description || node.data?.params?.description || '').trim()
    return note ? [{ node, note }] : []
  }), [graph.nodes])
  const nodeViewMode: FlowNodeViewMode = compactStatic ? 'compact' : 'detailed'
  const expandedMainNodeIds = useMemo(() => new Set(nodeEditors.map((editor) => editor.nodeId)), [nodeEditors])
  const layoutViewMode = nodeViewMode
  const layout = useMemo(() => buildBalancedLayout(renderGraph, { viewMode: layoutViewMode }), [layoutViewMode, renderGraph])
  const edgePortPlan = useMemo(() => {
    const counts = new Map<string, PortCounts>()
    const cursor = new Map<string, number>()
    const edgePorts = new Map<string, EdgePortAssignment>()
    const outgoingCount = new Map<string, number>()
    const incomingCount = new Map<string, number>()
    graphEdges.forEach((edge) => {
      outgoingCount.set(edge.from, (outgoingCount.get(edge.from) || 0) + 1)
      incomingCount.set(edge.to, (incomingCount.get(edge.to) || 0) + 1)
    })
    graph.nodes.forEach((node) => counts.set(node.id, createPortCounts()))
    graphEdges.forEach((edge, index) => {
      const sourcePoint = layout[edge.from]
      const targetPoint = layout[edge.to]
      const targetNode = nodeById.get(edge.to)
      const isHorizontalBundle = sourcePoint && targetPoint
        && Math.abs(targetPoint.x - sourcePoint.x) > 140
        && ((outgoingCount.get(edge.from) || 0) >= 3 || (incomingCount.get(edge.to) || 0) >= 3)
      const sides = isStartNode(targetNode, edge.to) || isHorizontalBundle
        ? chooseHorizontalEdgeSides(sourcePoint, targetPoint)
        : chooseEdgeSides(sourcePoint, targetPoint)
      const source = counts.get(edge.from)
      const target = counts.get(edge.to)
      const sourceKey = `${edge.from}:source:${sides.sourceSide}`
      const targetKey = `${edge.to}:target:${sides.targetSide}`
      const sourceIndex = (cursor.get(sourceKey) || 0) % PORT_LIMIT
      const targetIndex = (cursor.get(targetKey) || 0) % PORT_LIMIT
      cursor.set(sourceKey, (cursor.get(sourceKey) || 0) + 1)
      cursor.set(targetKey, (cursor.get(targetKey) || 0) + 1)
      if (source) source.outgoing[sides.sourceSide] += 1
      if (target) target.incoming[sides.targetSide] += 1
      edgePorts.set(`${index}:${edge.from}->${edge.to}`, { ...sides, sourceIndex, targetIndex })
    })
    return { counts, edgePorts }
  }, [graphEdges, graph.nodes, layout, nodeById])
  const initialFocusId = focusNodeId || graph.nodes.find((node) => node.scope !== 'root')?.id || graph.nodes[0]?.id || null

  const CustomNode = useCallback(({ data }: { data: Record<string, unknown> }) => {
    const node = data as unknown as FlowNode
    const resolvedNodeViewMode = nodeViewMode
    const runState = nodeRunStates?.get(node.id)
    const counts = edgePortPlan.counts.get(node.id) || createPortCounts()
    const outgoingNodes = graphEdges
      .filter((edge) => edge.from === node.id)
      .map((edge) => nodeById.get(edge.to))
      .filter((item): item is FlowNode => Boolean(item))
    const incomingNodes = graphEdges
      .filter((edge) => edge.to === node.id)
      .map((edge) => nodeById.get(edge.from))
      .filter((item): item is FlowNode => Boolean(item))
    return (
      <FlowNodeCard
        node={node}
        viewMode={resolvedNodeViewMode}
        order={nodeOrder.get(node.id) || 0}
        selected={selectedNode?.id === node.id}
        detailOwner={expandedMainNodeIds.has(node.id)}
        compactStatic={compactStatic}
        counts={counts}
        incomingNodes={incomingNodes}
        outgoingNodes={outgoingNodes}
        runState={runState}
        probeState={testProbeState}
        probeSelected={probeSelectedNodeIds.has(node.id)}
        onSelect={onSelectNode}
      />
    )
  }, [compactStatic, edgePortPlan, expandedMainNodeIds, graphEdges, nodeById, nodeOrder, nodeRunStates, nodeViewMode, onSelectNode, probeSelectedNodeIds, readOnlyGraph, selectedNode, testProbeState])

  const nodeTypes = useMemo(() => ({ custom: CustomNode }), [CustomNode])
  const initialNodes: FlowGraphNode[] = useMemo(() => graph.nodes.map((node) => {
    const dimensions = FLOW_NODE_DIMENSIONS[nodeViewMode]
    return {
      id: node.id,
      type: 'custom',
      position: layout[node.id] || { x: node.x, y: node.y },
      data: node as unknown as Record<string, unknown>,
      deletable: !node.locked && !isStartNode(node, node.id),
      style: { width: dimensions.width, height: dimensions.height },
    }
  }), [expandedMainNodeIds, graph.nodes, layout, nodeViewMode])
  const initialEdges: FlowGraphEdge[] = useMemo(() => {
    const branchLaneBySource = new Map<string, number>()
    return graphEdges.map((edge, index) => {
      const branch = edge.scope === 'branch'
      const runEdgeStatus = runEdgeStates.get(`${edge.from}->${edge.to}`)
      const isRunActive = runEdgeStatus === 'active'
      const isRunVisited = runEdgeStatus === 'visited'
      const sourceNode = nodeById.get(edge.from)
      const sourceAccent = sourceNode ? getNodeCategory(sourceNode).color : '#ba6440'
      const normalStroke = branch ? '#5e8bd8' : sourceAccent
      const lane = branch ? (branchLaneBySource.get(edge.from) || 0) : 0
      if (branch) branchLaneBySource.set(edge.from, lane + 1)
      const ports = edgePortPlan.edgePorts.get(`${index}:${edge.from}->${edge.to}`) || { sourceSide: 'right', targetSide: 'left', sourceIndex: 0, targetIndex: 0 }
      const sourcePoint = layout[edge.from]
      const targetPoint = layout[edge.to]
      const loopY = sourcePoint && targetPoint ? Math.min(sourcePoint.y, targetPoint.y) - 72 - lane * 42 : undefined
      return {
        id: `edge-${index}-${edge.from}-${edge.to}`,
        source: edge.from,
        target: edge.to,
        sourceHandle: getPortHandleId('source', ports.sourceSide, ports.sourceIndex),
        targetHandle: getPortHandleId('target', ports.targetSide, ports.targetIndex),
        animated: false,
        type: 'default',
        label: branch ? edge.label || '分支' : undefined,
        data: { scope: edge.scope || 'root', label: edge.label || '', lane, loopY, runEdgeStatus: runEdgeStatus || '' },
        zIndex: isRunActive ? 3 : isRunVisited ? 2 : 0,
        style: {
          stroke: isRunActive ? '#d05b2f' : isRunVisited ? '#2f9e63' : normalStroke,
          strokeWidth: isRunActive ? 5 : isRunVisited ? 3.4 : branch ? 2.4 : 2.8,
          strokeDasharray: isRunActive ? 'none' : branch ? '6 5' : undefined,
          filter: isRunActive ? 'drop-shadow(0 0 4px rgba(208, 91, 47, .72))' : undefined,
        },
        markerEnd: { type: MarkerType.ArrowClosed, color: isRunActive ? '#d05b2f' : isRunVisited ? '#2f9e63' : normalStroke },
      }
    })
  }, [edgePortPlan, graphEdges, layout, nodeById, runEdgeStates])

  const [nodes, setNodes] = useState<FlowGraphNode[]>(initialNodes)
  const [edges, setEdges] = useState<FlowGraphEdge[]>(initialEdges)
  const focusCanvasNode = useCallback((nodeId: string) => {
    if (!flowInstance) return
    const target = flowInstance.getNode(nodeId)
    if (!target) return
    const viewport = flowInstance.getViewport()
    const targetSize = getGraphNodeSize(target as FlowGraphNode)
    flowInstance.setCenter(
      target.position.x + targetSize.width / 2,
      target.position.y + targetSize.height / 2,
      { zoom: Math.max(viewport.zoom, 1), duration: 240 },
    )
  }, [flowInstance])
  const nodeEditorPlacements = useMemo(() => {
    const occupied: Array<{ x: number; y: number; width: number; height: number }> = []
    const overlaps = (candidate: { x: number; y: number; width: number; height: number }) => occupied.some((item) => !(
      candidate.x + candidate.width + 18 <= item.x
      || item.x + item.width + 18 <= candidate.x
      || candidate.y + candidate.height + 18 <= item.y
      || item.y + item.height + 18 <= candidate.y
    ))

    return nodeEditors.reduce<NodeEditorPlacement[]>((result, editor) => {
      const graphNode = nodes.find((node) => node.id === editor.nodeId)
      if (!graphNode) return result
      const savedPosition = nodeEditorPositions[editor.editorId] || editor.position
      const nodeSize = getGraphNodeSize(graphNode)
      const savedOverlapsExpandedMain = savedPosition && expandedMainNodeIds.has(editor.nodeId) && !(
        savedPosition.x + editor.width + 20 <= graphNode.position.x
        || graphNode.position.x + nodeSize.width + 20 <= savedPosition.x
        || savedPosition.y + editor.height + 20 <= graphNode.position.y
        || graphNode.position.y + nodeSize.height + 20 <= savedPosition.y
      )
      if (savedPosition && !savedOverlapsExpandedMain) {
        const placement = { ...editor, ...savedPosition, side: resolveEditorSide(graphNode, savedPosition, editor.width, editor.height) }
        occupied.push({ ...savedPosition, width: editor.width, height: editor.height })
        result.push(placement)
        return result
      }
      const { width: nodeWidth, height: nodeHeight } = getGraphNodeSize(graphNode)
      const centerX = graphNode.position.x + nodeWidth / 2
      const centerY = graphNode.position.y + nodeHeight / 2
      const satelliteGap = 48
      const topY = graphNode.position.y - editor.height - satelliteGap
      const bottomY = graphNode.position.y + nodeHeight + 34
      const leftX = graphNode.position.x - editor.width - satelliteGap
      const rightX = graphNode.position.x + nodeWidth + satelliteGap
      const preferredBySection: Record<NodeDetailSection, Omit<NodeEditorPlacement, keyof CanvasNodeEditor>> = {
        contract: { x: leftX, y: graphNode.position.y - 150, side: 'left' },
        inputs: { x: leftX, y: centerY - editor.height / 2, side: 'left' },
        outputs: { x: centerX - editor.width / 2, y: bottomY, side: 'bottom' },
        component: { x: rightX, y: graphNode.position.y - 180, side: 'right' },
        model: { x: rightX, y: graphNode.position.y - 180, side: 'right' },
        resources: { x: rightX, y: centerY - editor.height / 2, side: 'right' },
        routing: { x: leftX, y: centerY - editor.height / 2, side: 'left' },
        safety: { x: rightX, y: bottomY, side: 'bottom' },
        runtime: { x: rightX, y: centerY - editor.height / 2, side: 'right' },
        artifacts: { x: centerX - editor.width / 2, y: bottomY, side: 'bottom' },
        config: { x: rightX + 36, y: graphNode.position.y - 130, side: 'right' },
      }
      const baseX = rightX
      const baseY = graphNode.position.y - 180
      const rightSlots = Array.from({ length: 12 }, (_, slot) => ({
        x: baseX + (slot % 2) * NODE_EDITOR_SLOT_WIDTH,
        y: baseY + Math.floor(slot / 2) * NODE_EDITOR_SLOT_HEIGHT,
        side: 'right' as const,
      }))
      const leftSlots = Array.from({ length: 6 }, (_, slot) => ({
        x: graphNode.position.x - editor.width - NODE_EDITOR_GAP - (slot % 2) * NODE_EDITOR_SLOT_WIDTH,
        y: baseY + Math.floor(slot / 2) * NODE_EDITOR_SLOT_HEIGHT,
        side: 'left' as const,
      }))
      const candidates: Array<Omit<NodeEditorPlacement, keyof CanvasNodeEditor>> = [
        preferredBySection[editor.section],
        { x: centerX - editor.width / 2, y: topY, side: 'top' },
        { x: centerX - editor.width / 2, y: bottomY, side: 'bottom' },
        { x: leftX, y: centerY - editor.height / 2, side: 'left' },
        { x: rightX, y: centerY - editor.height / 2, side: 'right' },
        ...rightSlots,
        ...leftSlots,
      ]
      const chosen = candidates.find((candidate) => !overlaps({ ...candidate, width: editor.width, height: editor.height })) || candidates[0]
      occupied.push({ ...chosen, width: editor.width, height: editor.height })
      result.push({ ...editor, ...chosen })
      return result
    }, [])
  }, [expandedMainNodeIds, nodeEditorPositions, nodeEditors, nodes])
  const nodeEditorPlacementSignature = nodeEditorPlacements.map((editor) => `${editor.editorId}:${editor.x}:${editor.y}:${editor.side}:${editor.width}:${editor.height}`).join('|')
  const hasNodeEditors = nodeEditorPlacements.length > 0

  useEffect(() => {
    if (!onNodeEditorPositionChange) return
    nodeEditorPlacements.forEach((editor) => {
      if (editor.position || nodeEditorPositions[editor.editorId]) return
      onNodeEditorPositionChange(editor.editorId, { x: editor.x, y: editor.y })
    })
  }, [nodeEditorPlacements, nodeEditorPositions, onNodeEditorPositionChange])

  useEffect(() => setNodes(initialNodes), [initialNodes])
  useEffect(() => setEdges(initialEdges), [initialEdges])
  useEffect(() => {
    setNodeEditorPositions({})
    setDraggingEditorId(null)
    nodeEditorDragRef.current = null
  }, [graph.id])
  useEffect(() => {
    if (!flowInstance || compactStatic || initialNodes.length === 0) return
    const graphId = `${graph.id || '__anonymous_graph__'}:${nodeViewMode}`
    if (lastFittedGraphIdRef.current === graphId) return
    lastFittedGraphIdRef.current = graphId
    if (hasNodeEditors) return
    const frame = window.requestAnimationFrame(() => {
      const target = flowInstance.getNode(initialFocusId || initialNodes[0]?.id) || initialNodes[0]
      if (!target) return
      const targetSize = getGraphNodeSize(target as FlowGraphNode)
      flowInstance.setCenter(
        target.position.x + targetSize.width / 2,
        target.position.y + targetSize.height / 2,
        { zoom: nodeViewMode === 'detailed' ? 1 : 1.02, duration: 260 },
      )
    })
    return () => window.cancelAnimationFrame(frame)
  }, [compactStatic, flowInstance, graph.id, hasNodeEditors, initialFocusId, initialNodes, nodeViewMode])

  const buildLayoutFromNodes = useCallback((items: FlowGraphNode[]) => {
    const nextLayout: Record<string, { x: number; y: number }> = {}
    items.forEach((node) => {
      nextLayout[node.id] = {
        x: Math.round(node.position.x / gridSize) * gridSize,
        y: Math.round(node.position.y / gridSize) * gridSize,
      }
    })
    return nextLayout
  }, [gridSize])

  const buildFlowEdges = useCallback((items: FlowGraphEdge[]): FlowEdge[] => {
    const seen = new Set<string>()
    return items.reduce<FlowEdge[]>((result, edge) => {
      if (!edge.source || !edge.target || edge.source === edge.target) return result
      const scope = String(edge.data?.scope || 'root')
      const label = String(edge.data?.label || edge.label || '').trim()
      const key = `${scope}:${edge.source}->${edge.target}`
      if (seen.has(key)) return result
      seen.add(key)
      result.push({ from: edge.source, to: edge.target, scope, ...(label ? { label } : {}) })
      return result
    }, [])
  }, [])

  const saveEdgesQuietly = useCallback(async (items: FlowGraphEdge[]) => {
    if (compactStatic || readOnlyGraph || !onEdgesSave) return
    await onEdgesSave(buildFlowEdges(items))
  }, [buildFlowEdges, compactStatic, onEdgesSave, readOnlyGraph])

  const validateConnection = useCallback((sourceId: string, targetId: string) => {
    const source = nodeById.get(sourceId)
    const target = nodeById.get(targetId)
    if (!source || !target) return '节点不存在，无法连接'
    if (sourceId === targetId) return '不能连接到自身'
    if (isStartNode(target, targetId)) return '开始节点不能作为链路目标'
    if (source.type === 'terminal' && !isStartNode(source, sourceId)) return '结尾节点不能再接出链路'
    return ''
  }, [nodeById])

  const focusGraph = useCallback((duration = 260) => {
    if (!flowInstance || initialNodes.length === 0) return
    const runFit = () => {
      flowInstance.fitView({ padding: 0.22, duration, maxZoom: compactStatic ? 0.82 : 1.05 })
      const firstNode = flowInstance.getNode(initialFocusId || initialNodes[0]?.id) || initialNodes[0]
      const wrapper = wrapperRef.current
      if (!firstNode || !wrapper) return
      window.setTimeout(() => {
        const zoom = compactStatic ? 0.72 : nodeViewMode === 'detailed' ? 0.9 : 0.98
        const { width, height } = getGraphNodeSize(firstNode as FlowGraphNode)
        flowInstance.setViewport({
          x: wrapper.clientWidth / 2 - (firstNode.position.x + width / 2) * zoom,
          y: wrapper.clientHeight / 2 - (firstNode.position.y + height / 2) * zoom,
          zoom,
        }, { duration })
      }, 120)
    }
    window.requestAnimationFrame(() => {
      runFit()
      window.requestAnimationFrame(runFit)
    })
  }, [compactStatic, flowInstance, initialFocusId, initialNodes, nodeViewMode])

  const handleFlowInit = useCallback((instance: ReactFlowInstance) => {
    setFlowInstance(instance)
  }, [])

  const beginNodeEditorDrag = useCallback((event: React.PointerEvent<HTMLDivElement>, editor: NodeEditorPlacement) => {
    const target = event.target as HTMLElement
    if (!target.closest('.cf-node-drawer-header, .cf-node-satellite-head')) return false
    if (target.closest('button, input, textarea, select, a, [contenteditable="true"]')) return false
    const node = nodeById.get(editor.nodeId)
    if (node) onSelectNode(node)
    const zoom = flowInstance?.getViewport().zoom || 1
    nodeEditorDragRef.current = {
      editorId: editor.editorId,
      nodeId: editor.nodeId,
      pointerId: event.pointerId,
      clientX: event.clientX,
      clientY: event.clientY,
      x: editor.x,
      y: editor.y,
      zoom,
    }
    setNodeEditorPositions((current) => ({ ...current, [editor.editorId]: { x: editor.x, y: editor.y } }))
    setDraggingEditorId(editor.editorId)
    event.currentTarget.setPointerCapture(event.pointerId)
    event.preventDefault()
    event.stopPropagation()
    return true
  }, [flowInstance, nodeById, onSelectNode])

  const moveNodeEditor = useCallback((event: React.PointerEvent<HTMLDivElement>) => {
    const drag = nodeEditorDragRef.current
    if (!drag || drag.pointerId !== event.pointerId) return
    const x = drag.x + (event.clientX - drag.clientX) / drag.zoom
    const y = drag.y + (event.clientY - drag.clientY) / drag.zoom
    nodeEditorDragRef.current = { ...drag, x, y, clientX: event.clientX, clientY: event.clientY }
    setNodeEditorPositions((current) => ({ ...current, [drag.editorId]: { x, y } }))
    event.preventDefault()
    event.stopPropagation()
  }, [])

  const endNodeEditorDrag = useCallback((event: React.PointerEvent<HTMLDivElement>) => {
    const drag = nodeEditorDragRef.current
    if (!drag || drag.pointerId !== event.pointerId) return
    onNodeEditorPositionChange?.(drag.editorId, { x: drag.x, y: drag.y })
    nodeEditorDragRef.current = null
    setDraggingEditorId(null)
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId)
    event.preventDefault()
    event.stopPropagation()
  }, [onNodeEditorPositionChange])

  const handleAutoAlign = useCallback(async () => {
    if (!onLayoutSave) return
    const currentNodes = (flowInstance?.getNodes() as FlowGraphNode[] | undefined) || nodes
    const alignedLayout = buildAutoAlignLayout(renderGraph, { viewMode: layoutViewMode })
    const aligned = currentNodes.map((node) => ({ ...node, position: alignedLayout[node.id] || node.position }))
    setNodes(aligned)
    await onLayoutSave(buildLayoutFromNodes(aligned))
    window.requestAnimationFrame(() => focusGraph(240))
  }, [buildLayoutFromNodes, flowInstance, focusGraph, layoutViewMode, renderGraph, nodes, onLayoutSave])

  const toggleCanvasPanel = useCallback((panel: Exclude<CanvasPanel, null>) => {
    setCanvasPanel((current) => {
      const next = current === panel ? null : panel
      if (next !== 'nodes') setSelectedLibraryCategoryId(null)
      return next
    })
  }, [])

  const activateConnectMode = useCallback(() => {
    setActiveCanvasTool('connect')
    setCanvasPanel(null)
    onCloseNodeEditor?.()
  }, [onCloseNodeEditor])

  const selectLibraryCategory = useCallback((categoryId: NodeCategoryId) => {
    const preset = getPreset(categoryId)
    onCloseNodeEditor?.()
    setSelectedLibraryCategoryId(categoryId)
    setSelectedLibraryPresetId(preset.id)
    setLibraryPresetConfig({})
  }, [onCloseNodeEditor])

  const startNodeTemplateDrag = useCallback((event: React.DragEvent<HTMLButtonElement>, categoryId: NodeCategoryId) => {
    const preset = getPreset(categoryId, categoryId === selectedLibraryCategoryId ? selectedLibraryPresetId : undefined)
    const config = categoryId === selectedLibraryCategoryId ? libraryPresetConfig : {}
    event.dataTransfer.setData(NODE_TEMPLATE_MIME, JSON.stringify({ categoryId, presetId: preset.id, presetConfig: config }))
    event.dataTransfer.effectAllowed = 'copy'
    if (categoryId !== selectedLibraryCategoryId) selectLibraryCategory(categoryId)
  }, [libraryPresetConfig, selectLibraryCategory, selectedLibraryCategoryId, selectedLibraryPresetId])

  const handleNodeTemplateDragOver = useCallback((event: React.DragEvent) => {
    if (!Array.from(event.dataTransfer.types || []).includes(NODE_TEMPLATE_MIME)) return
    event.preventDefault()
    event.dataTransfer.dropEffect = 'copy'
  }, [])

  const handleNodeTemplateDrop = useCallback(async (event: React.DragEvent) => {
    const raw = event.dataTransfer.getData(NODE_TEMPLATE_MIME)
    if (!raw || !flowInstance || !onCreateNode) return
    event.preventDefault()
    try {
      const template = JSON.parse(raw) as { categoryId: NodeCategoryId; presetId?: string; presetConfig?: Record<string, string> }
      const position = flowInstance.screenToFlowPosition({ x: event.clientX, y: event.clientY }, { snapToGrid: gridSnap })
      await onCreateNode(selectedNode, template.categoryId, 'insert', {
        presetId: template.presetId,
        presetConfig: template.presetConfig || {},
        position,
      })
      setSelectedLibraryCategoryId(null)
    } catch (error: any) {
      showToast({ title: '节点拖放失败', description: error?.message || '节点模板数据无效', type: 'error' })
    }
  }, [flowInstance, gridSnap, onCreateNode, selectedNode])

  useEffect(() => {
    if (!hasNodeEditors || compactStatic) return
    setCanvasPanel(null)
    setSelectedLibraryCategoryId(null)
  }, [compactStatic, hasNodeEditors])

  useEffect(() => {
    const currentIds = new Set(nodeEditorPlacements.map((editor) => editor.editorId))
    const addedIds = [...currentIds].filter((editorId) => !openEditorIdsRef.current.has(editorId))
    if (!flowInstance) return
    openEditorIdsRef.current = currentIds
    if (!addedIds.length || !hasNodeEditors || compactStatic) return
    const focusOpenEditors = () => {
      const bounds = nodeEditorPlacements.flatMap((editor) => {
        const graphNode = flowInstance.getNode(editor.nodeId)
        const nodeBounds = graphNode ? [{
          x: graphNode.position.x,
          y: graphNode.position.y,
          width: getGraphNodeSize(graphNode as FlowGraphNode).width,
          height: getGraphNodeSize(graphNode as FlowGraphNode).height,
        }] : []
        return [
          { x: editor.x, y: editor.y, width: editor.width, height: editor.height },
          ...nodeBounds,
        ]
      })
      if (!bounds.length) return
      const minX = Math.min(...bounds.map((item) => item.x))
      const minY = Math.min(...bounds.map((item) => item.y))
      const maxX = Math.max(...bounds.map((item) => item.x + item.width))
      const maxY = Math.max(...bounds.map((item) => item.y + item.height))
      const wrapper = wrapperRef.current
      if (!wrapper) return
      const currentZoom = Math.max(.18, Math.min(flowInstance.getViewport().zoom, 1.6))
      const viewport = getViewportForBounds(
        { x: minX, y: minY, width: maxX - minX, height: maxY - minY },
        wrapper.clientWidth,
        wrapper.clientHeight,
        currentZoom,
        currentZoom,
        nodeEditorPlacements.length > 1 ? .04 : .08,
      )
      flowInstance.setViewport(viewport, { duration: 280 })
    }
    const frame = window.requestAnimationFrame(focusOpenEditors)
    return () => {
      window.cancelAnimationFrame(frame)
    }
  }, [compactStatic, flowInstance, hasNodeEditors, nodeEditorPlacementSignature, nodeViewMode])

  const deleteEdges = useCallback(async (deletedEdges: FlowGraphEdge[]) => {
    if (compactStatic || readOnlyGraph || !onEdgesSave || deletedEdges.length === 0) return
    const deletedIds = new Set(deletedEdges.map((edge) => edge.id))
    const sourceEdges = (flowInstance?.getEdges() as FlowGraphEdge[] | undefined) || edges
    const nextEdges = sourceEdges.filter((edge) => !deletedIds.has(edge.id))
    setEdges(nextEdges)
    await saveEdgesQuietly(nextEdges)
    setContextMenu(null)
  }, [compactStatic, edges, flowInstance, onEdgesSave, readOnlyGraph, saveEdgesQuietly])

  const renameBranchEdge = useCallback(async (edge: FlowGraphEdge) => {
    if (readOnlyGraph || edge.data?.scope !== 'branch') return
    const currentLabel = String(edge.data?.label || edge.label || '分支')
    const nextLabel = window.prompt('请输入分支名称', currentLabel)?.trim()
    if (!nextLabel || nextLabel === currentLabel) return
    const sourceEdges = (flowInstance?.getEdges() as FlowGraphEdge[] | undefined) || edges
    const nextEdges = sourceEdges.map((item) => item.id === edge.id ? { ...item, label: nextLabel, data: { ...(item.data || {}), scope: 'branch', label: nextLabel } } : item)
    setEdges(nextEdges)
    await saveEdgesQuietly(nextEdges)
    setContextMenu(null)
  }, [edges, flowInstance, readOnlyGraph, saveEdgesQuietly])

  const updateEdgeScope = useCallback(async (edge: FlowGraphEdge, scope: 'root' | 'branch') => {
    if (readOnlyGraph) return
    const sourceEdges = (flowInstance?.getEdges() as FlowGraphEdge[] | undefined) || edges
    let label = scope === 'branch' ? String(edge.data?.label || edge.label || '').trim() : ''
    if (scope === 'branch' && !label) label = window.prompt('请输入分支名称', '条件分支')?.trim() || '条件分支'
    const nextEdges = sourceEdges.map((item) => item.id === edge.id ? {
      ...item,
      label: label || undefined,
      data: { ...(item.data || {}), scope, label },
    } : item)
    setEdges(nextEdges)
    await saveEdgesQuietly(nextEdges)
    setContextMenu(null)
  }, [edges, flowInstance, readOnlyGraph, saveEdgesQuietly])

  const trackRightPointerDown = useCallback((event: React.PointerEvent<HTMLDivElement>) => {
    if (event.button !== 2) return
    rightGestureRef.current = { x: event.clientX, y: event.clientY, moved: false }
  }, [])

  const trackRightPointerMove = useCallback((event: React.PointerEvent<HTMLDivElement>) => {
    const gesture = rightGestureRef.current
    if (!gesture || (event.buttons & 2) === 0) return
    if (Math.hypot(event.clientX - gesture.x, event.clientY - gesture.y) >= 5) gesture.moved = true
  }, [])

  const trackRightPointerUp = useCallback((event: React.PointerEvent<HTMLDivElement>) => {
    if (event.button !== 2 || !rightGestureRef.current) return
    if (rightGestureRef.current.moved) suppressContextMenuUntilRef.current = Date.now() + 350
    rightGestureRef.current = null
  }, [])

  useEffect(() => {
    if (compactStatic || readOnlyGraph || !onDeleteNode) return
    const handleKeyDown = async (event: KeyboardEvent) => {
      if (event.key !== 'Delete' && event.key !== 'Backspace') return
      const target = event.target as HTMLElement | null
      const tagName = target?.tagName?.toLowerCase()
      if (target?.isContentEditable || tagName === 'input' || tagName === 'textarea' || tagName === 'select') return
      if (!selectedNode || selectedNode.locked || isStartNode(selectedNode, selectedNode.id) || deletingNodeRef.current) return
      event.preventDefault()
      deletingNodeRef.current = true
      try {
        await onDeleteNode(selectedNode)
      } finally {
        deletingNodeRef.current = false
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [compactStatic, onDeleteNode, readOnlyGraph, selectedNode])

  useEffect(() => {
    if (!flowInstance || !initialFocusId || !compactStatic) return
    const frame = window.requestAnimationFrame(() => {
      const node = flowInstance.getNode(initialFocusId) || nodes.find((item) => item.id === initialFocusId)
      if (!node) return
      const zoom = compactStatic ? 0.72 : fullscreen ? 1.15 : 1.05
      const { width, height } = getGraphNodeSize(node as FlowGraphNode)
      const wrapper = wrapperRef.current
      flowInstance.setViewport({
        x: (wrapper?.clientWidth || 960) / 2 - (node.position.x + width / 2) * zoom,
        y: (wrapper?.clientHeight || 230) / 2 - (node.position.y + height / 2) * zoom,
        zoom,
      }, { duration: 450 })
    })
    return () => window.cancelAnimationFrame(frame)
  }, [compactStatic, flowInstance, fullscreen, initialFocusId, nodes])

  if (initialNodes.length === 0) {
    return (
      <div ref={wrapperRef} className={`cf-flow-graph-shell ${fullscreen ? 'fullscreen' : ''}`}>
        <div className="cf-flow-empty-state">
          <strong>当前画布没有节点</strong>
          <span>使用左侧“节点”工具创建第一个流程节点。</span>
        </div>
      </div>
    )
  }

  return (
    <div
      ref={wrapperRef}
      className={`cf-flow-graph-shell canvas-tool-${activeCanvasTool} ${fullscreen ? 'fullscreen' : ''}`}
      onPointerDownCapture={trackRightPointerDown}
      onPointerMoveCapture={trackRightPointerMove}
      onPointerUpCapture={trackRightPointerUp}
    >
      <ReactFlow<FlowGraphNode, FlowGraphEdge>
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        onInit={handleFlowInit}
        defaultViewport={{ x: 0, y: 0, zoom: compactStatic ? 0.72 : 1.05 }}
        minZoom={0.18}
        maxZoom={1.8}
        nodesDraggable={!compactStatic && !readOnlyGraph && !canvasLocked && activeCanvasTool === 'select'}
        nodesConnectable={!compactStatic && !readOnlyGraph && !canvasLocked && activeCanvasTool === 'connect'}
        elementsSelectable={!compactStatic && activeCanvasTool === 'select'}
        panOnDrag={!compactStatic && [1, 2]}
        selectionOnDrag={!compactStatic && activeCanvasTool === 'select'}
        zoomOnScroll={!compactStatic}
        panOnScroll={false}
        zoomOnPinch={!compactStatic}
        zoomOnDoubleClick={false}
        zoomActivationKeyCode={null}
        preventScrolling={!compactStatic}
        snapToGrid={!compactStatic && gridSnap}
        snapGrid={[gridSize, gridSize]}
        onDragOver={handleNodeTemplateDragOver}
        onDrop={handleNodeTemplateDrop}
        onNodesChange={(changes: NodeChange[]) => {
          setNodes((current) => applyNodeChanges(changes, current) as FlowGraphNode[])
        }}
        onSelectionChange={({ nodes: selectedNodes }) => {
          if (activeCanvasTool !== 'select' || selectedNodes.length !== 1) return
          const node = selectedNodes[0]?.data as unknown as FlowNode
          if (node) onSelectNode(node)
        }}
        onNodeDoubleClick={(event, graphNode) => {
          if (compactStatic || activeCanvasTool !== 'select') return
          event.preventDefault()
          const node = graphNode.data as unknown as FlowNode
          onSelectNode(node)
          focusCanvasNode(node.id)
          setContextMenu(null)
        }}
        onNodeContextMenu={(event, graphNode) => {
          if (compactStatic || readOnlyGraph) return
          event.preventDefault()
          event.stopPropagation()
          if (Date.now() < suppressContextMenuUntilRef.current) return
          const node = graphNode.data as unknown as FlowNode
          onSelectNode(node)
          focusCanvasNode(node.id)
          const canvas = wrapperRef.current?.getBoundingClientRect()
          setContextMenu({
            x: canvas ? Math.min(canvas.right - 188, canvas.left + canvas.width / 2 + 158) : event.clientX,
            y: canvas ? Math.max(canvas.top + 12, canvas.top + canvas.height / 2 - 72) : event.clientY,
            node,
          })
        }}
        onNodeDragStop={async () => {
          if (compactStatic || readOnlyGraph || !onLayoutSave) return
          await onLayoutSave(buildLayoutFromNodes((flowInstance?.getNodes() as FlowGraphNode[] | undefined) || nodes))
        }}
        onNodesDelete={async (deletedNodes: FlowGraphNode[]) => {
          if (compactStatic || readOnlyGraph || !onDeleteNode || deletedNodes.length === 0) return
          const node = deletedNodes[0].data as unknown as FlowNode
          if (!node || node.locked || isStartNode(node, node.id) || deletingNodeRef.current) return
          deletingNodeRef.current = true
          try { await onDeleteNode(node) } finally { deletingNodeRef.current = false }
        }}
        onEdgesChange={(changes: EdgeChange[]) => setEdges((current) => applyEdgeChanges(changes, current))}
        onConnect={async (connection: Connection) => {
          if (compactStatic || readOnlyGraph || !onEdgesSave || !connection.source || !connection.target) return
          const reason = validateConnection(connection.source, connection.target)
          if (reason) {
            showToast({ title: reason, type: 'error' })
            return
          }
          if (edges.some((edge) => edge.source === connection.source && edge.target === connection.target)) return
          const nextEdges = addEdge({
            ...connection,
            id: `edge-${Date.now()}-${connection.source}-${connection.target}`,
            sourceHandle: connection.sourceHandle || getPortHandleId('source', 'right', 0),
            targetHandle: connection.targetHandle || getPortHandleId('target', 'left', 0),
            animated: false,
            type: 'default',
            data: { scope: 'root' },
            zIndex: 0,
            style: { stroke: '#ba6440', strokeWidth: 2.8 },
            markerEnd: { type: MarkerType.ArrowClosed, color: '#ba6440' },
          }, edges)
          setEdges(nextEdges)
          await saveEdgesQuietly(nextEdges)
        }}
        onEdgesDelete={deleteEdges}
        onEdgeContextMenu={(event: React.MouseEvent, edge: FlowGraphEdge) => {
          if (compactStatic || readOnlyGraph || activeCanvasTool !== 'connect') return
          event.preventDefault()
          event.stopPropagation()
          if (Date.now() < suppressContextMenuUntilRef.current) return
          setContextMenu({ x: event.clientX, y: event.clientY, node: null, edge })
        }}
        deleteKeyCode={['Delete', 'Backspace']}
        connectionLineType={ConnectionLineType.Bezier}
        connectionLineStyle={{ stroke: '#ba6440', strokeWidth: 2.8 }}
        onPaneClick={() => setContextMenu(null)}
        onPaneContextMenu={(event) => {
          if (compactStatic || readOnlyGraph) return
          event.preventDefault()
          if ((event.target as Element | null)?.closest?.('.react-flow__node, .react-flow__edge')) return
          if (Date.now() >= suppressContextMenuUntilRef.current) setContextMenu(null)
        }}
        proOptions={{ hideAttribution: true }}
      >
        <Background id="canvas-grid" variant={BackgroundVariant.Lines} color="#e1e5e9" gap={gridSize * 4} lineWidth={1} />
        {!compactStatic && nodeEditorPlacements.map((editor, index) => {
          const active = editor.nodeId === activeNodeEditorId
          const dragging = draggingEditorId === editor.editorId
          const graphNode = nodes.find((node) => node.id === editor.nodeId)
          const connector = graphNode ? buildDetailConnector(graphNode, editor) : null
          const markerId = `cf-detail-arrow-${editor.editorId.replace(/[^a-zA-Z0-9_-]/g, '-')}`
          return (
            <ViewportPortal key={editor.editorId}>
              <>
                {connector && (
                  <svg className="cf-node-detail-connectors" data-editor-id={editor.editorId} data-node-id={editor.nodeId} data-connector-count="1" style={{ zIndex: active ? 1018 : 998 + index }} aria-hidden="true">
                    <defs>
                      <marker id={markerId} viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                        <path d="M 0 0 L 10 5 L 0 10 z" />
                      </marker>
                    </defs>
                    <path className="cf-node-detail-connector-path" d={connector.path} markerEnd={`url(#${markerId})`} />
                    <circle className="cf-node-detail-connector-port source" cx={connector.source.x} cy={connector.source.y} r="5" />
                    <circle className="cf-node-detail-connector-port target" cx={connector.target.x} cy={connector.target.y} r="4.5" />
                  </svg>
                )}
                <div
                  className={`cf-node-editor-viewport detail-section-${editor.section} placement-${editor.side} nodrag nopan nowheel ${active ? 'active' : ''} ${dragging ? 'dragging' : ''}`}
                  data-editor-id={editor.editorId}
                  data-node-id={editor.nodeId}
                  data-section={editor.section}
                  style={{ left: editor.x, top: editor.y, width: editor.width, height: editor.height, zIndex: active ? 1020 : 1000 + index }}
                  onPointerDown={(event) => {
                    if (beginNodeEditorDrag(event, editor)) return
                    const node = nodeById.get(editor.nodeId)
                    if (node) onSelectNode(node)
                  }}
                  onPointerMove={moveNodeEditor}
                  onPointerUp={endNodeEditorDrag}
                  onPointerCancel={endNodeEditorDrag}
                >
                  {editor.content}
                </div>
              </>
            </ViewportPortal>
          )
        })}
        {!compactStatic && (
          <Panel position="top-left" className="cf-canvas-tool-rail">
            <nav aria-label="画布工具">
              <button type="button" className={activeCanvasTool === 'select' && !canvasPanel ? 'active' : ''} onClick={() => { setActiveCanvasTool('select'); setCanvasPanel(null); onCloseNodeEditor?.() }} title="选择与移动"><MousePointer2 /><span>选择</span></button>
              <button type="button" className={activeCanvasTool === 'connect' && !canvasPanel ? 'active' : ''} onClick={activateConnectMode} title="连接节点"><GitBranch /><span>连线</span></button>
              <button type="button" className={canvasPanel === 'nodes' ? 'active' : ''} onClick={() => toggleCanvasPanel('nodes')} title="节点库"><Box /><span>节点</span></button>
              <button type="button" className={canvasPanel === 'notes' ? 'active' : ''} onClick={() => { onCloseNodeEditor?.(); toggleCanvasPanel('notes') }} title="节点说明"><MessageSquare /><span>注释</span></button>
              {modelPanel && <button type="button" className={canvasPanel === 'models' ? 'active' : ''} onClick={() => { onCloseNodeEditor?.(); toggleCanvasPanel('models') }} title="模型管理"><BrainCircuit /><span>模型</span></button>}
              <button type="button" className={canvasPanel === 'variables' ? 'active' : ''} onClick={() => { onCloseNodeEditor?.(); toggleCanvasPanel('variables') }} title="流程变量"><Braces /><span>变量</span></button>
              <button type="button" className={canvasPanel === 'settings' ? 'active' : ''} onClick={() => { onCloseNodeEditor?.(); toggleCanvasPanel('settings') }} title="画布配置"><Settings /><span>配置</span></button>
              {toolPanel && <button type="button" className={canvasPanel === 'tools' ? 'active' : ''} onClick={() => { onCloseNodeEditor?.(); toggleCanvasPanel('tools') }} title="MCP 工具库"><Wrench /><span>工具</span></button>}
            </nav>
            <div className="cf-canvas-zoom-tools">
              <button type="button" onClick={() => flowInstance?.zoomIn({ duration: 180 })} title="放大"><ZoomIn /></button>
              <button type="button" onClick={() => flowInstance?.zoomOut({ duration: 180 })} title="缩小"><ZoomOut /></button>
              <button type="button" onClick={() => flowInstance?.fitView({ padding: 0.18, duration: 240 })} title="适应画布"><Maximize2 /></button>
              <button type="button" onClick={() => setFullscreen((value) => !value)} title={fullscreen ? '退出全屏' : '全屏查看'}><Maximize /></button>
              <button type="button" className={canvasLocked ? 'active' : ''} onClick={() => setCanvasLocked((value) => !value)} title={canvasLocked ? '解锁画布' : '锁定画布'}>{canvasLocked ? <Lock /> : <Unlock />}</button>
            </div>
          </Panel>
        )}
        {!compactStatic && canvasPanel && (
          <Panel position="top-left" className={`cf-canvas-tool-panel ${canvasPanel === 'tools' || canvasPanel === 'models' ? 'resource-panel' : ''}`}>
            <header><strong>{canvasPanel === 'nodes' ? '节点库' : canvasPanel === 'notes' ? '节点注释' : canvasPanel === 'models' ? '模型管理' : canvasPanel === 'variables' ? '流程变量' : canvasPanel === 'tools' ? '工具管理' : '画布配置'}</strong><button type="button" onClick={() => { setCanvasPanel(null); setSelectedLibraryCategoryId(null) }}>×</button></header>
            {canvasPanel === 'nodes' && (
              <div className="cf-canvas-node-library">
                <p>拖到画布创建节点；右键打开新节点预配置。</p>
                {NODE_CATEGORIES.map((category) => (
                  <button
                    type="button"
                    key={category.id}
                    className={selectedLibraryCategoryId === category.id ? 'active' : ''}
                    disabled={!onCreateNode}
                    draggable={Boolean(onCreateNode)}
                    onDragStart={(event) => startNodeTemplateDrag(event, category.id)}
                    onContextMenu={(event) => { event.preventDefault(); selectLibraryCategory(category.id) }}
                    title="拖动创建；右键配置"
                  >
                    <GripVertical className="cf-node-library-grip" aria-hidden="true" />
                    <i style={{ background: category.color }} />
                    <span><b>{category.label}</b><small>{category.description}</small></span>
                    <Settings className="cf-node-library-arrow" aria-hidden="true" />
                  </button>
                ))}
              </div>
            )}
            {canvasPanel === 'notes' && <div className="cf-canvas-data-list">{canvasNotes.length ? canvasNotes.map(({ node, note }) => <button type="button" key={node.id} onClick={() => onSelectNode(node)}><b>{node.display_name || node.title}</b><span>{note}</span></button>) : <p>当前节点还没有说明文字。</p>}</div>}
            {canvasPanel === 'variables' && <div className="cf-canvas-data-list variables">{canvasVariables.length ? canvasVariables.map((item) => <div key={`${item.kind}-${item.name}`}><b>{item.name}</b><span>{item.kind} · {item.source}</span></div>) : <p>当前流程还没有声明输入或输出变量。</p>}</div>}
            {canvasPanel === 'settings' && (
              <div className="cf-canvas-settings">
                <label><span>10px 网格对齐</span><input type="checkbox" checked={gridSnap} onChange={(event) => setGridSnap(event.target.checked)} /></label>
                <div><span>主节点视图</span><b>完整信息卡</b></div>
                <div><span>网格尺寸</span><b>固定 10px</b></div>
                {onLayoutSave && <button type="button" onClick={handleAutoAlign}><AlignHorizontalSpaceAround />按当前节点尺寸自动整理</button>}
              </div>
            )}
            {canvasPanel === 'models' && <div className="cf-canvas-resource-content">{modelPanel}</div>}
            {canvasPanel === 'tools' && <div className="cf-canvas-tool-content">{toolPanel}</div>}
          </Panel>
        )}
        {!compactStatic && canvasPanel === 'nodes' && selectedLibraryCategory && selectedLibraryPreset && (
          <Panel position="top-left" className="cf-node-template-config">
            <header>
              <div><span>新节点预配置</span><strong>{selectedLibraryCategory.label}</strong></div>
              <button type="button" onClick={() => setSelectedLibraryCategoryId(null)}>×</button>
            </header>
            <div className="cf-node-template-config-body">
              <section className="cf-node-template-summary" style={{ '--node-accent': selectedLibraryCategory.color } as React.CSSProperties}>
                <i />
                <div><strong>{selectedLibraryCategory.label}</strong><p>{selectedLibraryCategory.description}</p></div>
              </section>
              <section className="cf-node-template-presets">
                <label>节点用途</label>
                <div>
                  {getPresets(selectedLibraryCategory.id).map((preset) => (
                    <button
                      type="button"
                      key={preset.id}
                      className={selectedLibraryPreset.id === preset.id ? 'active' : ''}
                      onClick={() => { setSelectedLibraryPresetId(preset.id); setLibraryPresetConfig({}) }}
                    >
                      <strong>{preset.label}</strong>
                      <span>{preset.description}</span>
                    </button>
                  ))}
                </div>
              </section>
              <section className="cf-node-template-fields">
                <label>预设参数</label>
                {selectedLibraryPreset.fields.length ? selectedLibraryPreset.fields.map((field) => (
                  <label key={field.key}>
                    <span>{field.label}</span>
                    {field.multiline ? (
                      <textarea
                        value={libraryPresetConfig[field.key] || ''}
                        placeholder={field.placeholder}
                        onChange={(event) => setLibraryPresetConfig((current) => ({ ...current, [field.key]: event.target.value }))}
                      />
                    ) : (
                      <input
                        value={libraryPresetConfig[field.key] || ''}
                        placeholder={field.placeholder}
                        onChange={(event) => setLibraryPresetConfig((current) => ({ ...current, [field.key]: event.target.value }))}
                      />
                    )}
                  </label>
                )) : <p>这个预设不需要额外参数。</p>}
              </section>
            </div>
            <footer><GripVertical aria-hidden="true" /><span>配置会随节点条目一起拖入画布，松开后创建</span></footer>
          </Panel>
        )}
        {!compactStatic && <Panel position="bottom-left" className="cf-canvas-status"><span className={gridSnap ? 'active' : ''}><i />{gridSnap ? '网格对齐' : '自由移动'}</span><b>{gridSize}px</b><span className={activeCanvasTool === 'connect' ? 'active' : ''}><i />{activeCanvasTool === 'connect' ? '连线模式' : '选择模式'}</span></Panel>}
        {!compactStatic && <MiniMap pannable zoomable nodeColor={(node) => (node.data as unknown as FlowNode).locked ? '#b7bbb4' : getNodeCategory(node.data as unknown as FlowNode).bg} nodeStrokeColor={(node) => (node.data as unknown as FlowNode).locked ? '#898f87' : getNodeCategory(node.data as unknown as FlowNode).color} nodeBorderRadius={3} maskColor="rgba(90, 68, 55, 0.12)" />}
        {contextMenu && !compactStatic && !readOnlyGraph && (
          <div className="cf-graph-context-menu" style={{ left: contextMenu.x, top: contextMenu.y }}>
            <strong>{contextMenu.edge ? `${contextMenu.edge.source} → ${contextMenu.edge.target}` : contextMenu.node ? contextMenu.node.title : '画布操作'}</strong>
            {contextMenu.edge ? (
              <>
                <span className="cf-graph-menu-label">连线操作</span>
                {contextMenu.edge.data?.scope !== 'root' && <button onClick={() => updateEdgeScope(contextMenu.edge!, 'root')}>设为主流程连线</button>}
                {contextMenu.edge.data?.scope !== 'branch' && <button onClick={() => updateEdgeScope(contextMenu.edge!, 'branch')}>设为条件分支</button>}
                {contextMenu.edge.data?.scope === 'branch' && <button onClick={() => renameBranchEdge(contextMenu.edge!)}>命名分支</button>}
                <button className="danger" onClick={() => deleteEdges([contextMenu.edge!])}>删除这条连线</button>
              </>
            ) : (
              <>
                {contextMenu.node && <div className="cf-graph-submenu-item">
                  <button type="button">打开节点详情 ›</button>
                  <div className="cf-graph-submenu cf-node-detail-submenu">
                    {getAvailableNodeDetailSections(contextMenu.node, {
                      edges: graphEdges,
                      hasRunData: Boolean(nodeRunStates?.has(contextMenu.node.id) || stableRunEvents.some((event) => event.state === contextMenu.node!.id)),
                      editable: !readOnlyGraph,
                    }).map((section) => (
                      <button
                        key={section.id}
                        type="button"
                        data-section={section.id}
                        onClick={() => {
                          onOpenNodeEditor?.(contextMenu.node!, section.id)
                          setContextMenu(null)
                        }}
                      >
                        <span><b>{section.label}</b><small>{section.description}</small></span>
                      </button>
                    ))}
                  </div>
                </div>}
                <div className="cf-graph-submenu-item">
                  <button disabled={!contextMenu.node || !onCreateNode}>新增 Flow ›</button>
                  <div className="cf-graph-submenu">
                    {NODE_CATEGORIES.map((category) => (
                      <button key={`flow-${category.id}`} onClick={() => contextMenu.node && onCreateNode?.(contextMenu.node, category.id, 'insert')} disabled={!contextMenu.node || !onCreateNode}>
                        {category.shortLabel} Flow
                      </button>
                    ))}
                  </div>
                </div>
                <div className="cf-graph-submenu-item">
                  <button disabled={!contextMenu.node || !onCreateNode}>新增分支 ›</button>
                  <div className="cf-graph-submenu">
                    {NODE_CATEGORIES.map((category) => (
                      <button key={`branch-${category.id}`} onClick={() => contextMenu.node && onCreateNode?.(contextMenu.node, category.id, 'branch')} disabled={!contextMenu.node || !onCreateNode}>
                        {category.shortLabel}分支
                      </button>
                    ))}
                  </div>
                </div>
                <button onClick={() => {
                  if (contextMenu.node) void copyNodeText(contextMenu.node, 'id')
                  setContextMenu(null)
                }} disabled={!contextMenu.node}>复制节点 ID</button>
                <button onClick={() => {
                  if (contextMenu.node) void copyNodeText(contextMenu.node, 'config')
                  setContextMenu(null)
                }} disabled={!contextMenu.node}>复制节点配置</button>
                <button className="danger" onClick={() => contextMenu.node && onDeleteNode?.(contextMenu.node)} disabled={!contextMenu.node || contextMenu.node.locked || !onDeleteNode}>删除节点</button>
              </>
            )}
          </div>
        )}
      </ReactFlow>
    </div>
  )
}
