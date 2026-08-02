import { createContext, memo, useCallback, useContext, useEffect, useMemo, useRef, useState, type CSSProperties, type ReactNode } from 'react'
import {
  ReactFlow,
  Background,
  BackgroundVariant,
  ConnectionLineType,
  MarkerType,
  MiniMap,
  Panel,
  SelectionMode,
  ViewportPortal,
  addEdge,
  getViewportForBounds,
  useUpdateNodeInternals,
  type Connection,
  type Edge,
  type Node,
  type NodeProps,
  type ReactFlowInstance,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { AlertTriangle, AlignHorizontalSpaceAround, Box, Braces, BrainCircuit, CheckCircle2, ChevronDown, ChevronUp, CirclePause, FileText, FolderOpen, GitBranch, GripVertical, Info, Lock, Maximize, Maximize2, MessageSquare, MessageSquarePlus, MousePointer2, PackageCheck, Plus, Settings, Trash2, Unlock, Wrench, X, ZoomIn, ZoomOut } from 'lucide-react'
import { uploadWorkspaceFile, type AIFlowSelection, type FlowAnnotation, type FlowEdge, type FlowEvent, type FlowFiles, type FlowGraph, type FlowNode, type RunResult } from '../../api.ts'
import { DEFAULT_WORKSPACE_THEME, loadWorkspaceTheme, saveWorkspaceTheme, WORKSPACE_THEME_PRESETS, type WorkspaceTheme } from '../../appearance.ts'
import { showToast } from '../../toast.tsx'
import type { CreateNodeHandler, DesignDisplayMode, NodeCategoryId } from './types.ts'
import { FLOW_NODE_DIMENSIONS, NODE_CATEGORIES, buildBalancedLayout, getFlowNodeDimensions, getNodeCategory, getNodePalette, getPreset, getPresets, isStartNode, type FlowNodeViewMode } from './nodeModel.ts'
import type { NodeDetailSection } from './nodeDetails.ts'
import type { NodeRunState } from './runState.ts'
import { FlowNodeCard, type FlowNodeProbeState } from './FlowNodeCard.tsx'
import { createPortCounts, getPortHandleId, type EdgePortAssignment, type PortCounts, type PortSide } from './FlowNodePorts.tsx'
import { CanvasAnnotationCard } from './CanvasAnnotationCard.tsx'
import { buildClusterAwareLayout } from './clusterLayout.ts'
import { EngineeringNodeCard } from './EngineeringNodeCard.tsx'
import { buildEngineeringDataRelations, buildEngineeringNodeModels, engineeringControlHandleId, engineeringHandleId, isEngineeringResourceNode, type EngineeringDataRelation, type EngineeringEdgeVisibility, type EngineeringNodeRenderModel } from './engineeringNode.ts'
import { buildOutcomeNodeModels, plainOutcomeFieldLabel, type OutcomeNodeRenderModel } from './flowNodeView.ts'

/** 资源节点连线到 Root Flow 控制流的拒绝提示（供 UI 与静态断言共用，防止文案漂移） */
export const RESOURCE_EDGE_REJECT_MESSAGE = '资源依赖不能写入 Root Flow 控制流'

type FlowGraphNode = Node<Record<string, unknown>>
type FlowGraphEdge = Edge<Record<string, unknown>>
type DataRelation = { from: string; to: string; key: string; kind?: 'data' | 'dependency'; label?: string; fromField?: string; toField?: string; expression?: string; source?: string }
type RunEdgeStatus = 'visited' | 'active'
export type CanvasTool = 'select' | 'connect' | 'steward-pointer' | 'steward-lasso'
export type ProtocolDisplayInfo = {
  baseContractLabel: string
  targetProtocolLabel: string
  currentProtocolLabel: string
  currentProtocolStatus: string
}

function FlowNodeInternalsSync({ nodeIds }: { nodeIds: string[] }) {
  const updateNodeInternals = useUpdateNodeInternals()
  useEffect(() => {
    const frame = window.requestAnimationFrame(() => updateNodeInternals(nodeIds))
    return () => window.cancelAnimationFrame(frame)
  }, [nodeIds, updateNodeInternals])
  return null
}

function graphNodesMatch(current: FlowGraphNode[], next: FlowGraphNode[]) {
  if (current.length !== next.length) return false
  return current.every((node, index) => {
    const candidate = next[index]
    return node.id === candidate.id
      && node.type === candidate.type
      && node.position.x === candidate.position.x
      && node.position.y === candidate.position.y
      && node.className === candidate.className
      && JSON.stringify(node.data) === JSON.stringify(candidate.data)
      && JSON.stringify(node.style) === JSON.stringify(candidate.style)
  })
}

function graphEdgesMatch(current: FlowGraphEdge[], next: FlowGraphEdge[]) {
  if (current.length !== next.length) return false
  const nextById = new Map(next.map((edge) => [edge.id, edge]))
  return current.every((edge) => JSON.stringify(edge) === JSON.stringify(nextById.get(edge.id)))
}
const DEFAULT_PROTOCOL_DISPLAY: ProtocolDisplayInfo = {
  baseContractLabel: 'Base Contract 未读取',
  targetProtocolLabel: '协议发布清单未读取',
  currentProtocolLabel: 'CF-FARP@unknown',
  currentProtocolStatus: '当前卡带协议未读取',
}
export type CanvasPanel = 'nodes' | 'notes' | 'models' | 'variables' | 'settings' | 'tools' | 'package' | 'base-info' | null

type LibraryInputFieldDraft = {
  key: string
  id: string
  label: string
  type: 'text' | 'textarea' | 'number' | 'date' | 'email' | 'url' | 'file'
  required: boolean
  default: string
}

function defaultLibraryInputFields(): LibraryInputFieldDraft[] {
  return [
    { key: 'field_requirement', id: 'input_1', label: '需求描述', type: 'textarea', required: true, default: '' },
    { key: 'field_goal', id: 'input_2', label: '目标', type: 'text', required: true, default: '' },
    { key: 'field_constraints', id: 'input_3', label: '限制条件', type: 'textarea', required: false, default: '' },
  ]
}

type EngineeringNodeRenderContextValue = {
  models: Map<string, EngineeringNodeRenderModel>
  nodeOrder: Map<string, number>
  counts: Map<string, PortCounts>
  runStates?: Map<string, NodeRunState>
  onSelect: (node: FlowNode) => void
}

const EngineeringNodeRenderContext = createContext<EngineeringNodeRenderContextValue | null>(null)

const EngineeringCanvasNode = memo(function EngineeringCanvasNode({ data, selected }: NodeProps<FlowGraphNode>) {
  const context = useContext(EngineeringNodeRenderContext)
  const node = data as unknown as FlowNode
  const model = context?.models.get(node.id)
  if (!context || !model) return null
  return (
    <EngineeringNodeCard
      node={node}
      model={model}
      order={context.nodeOrder.get(node.id) || 0}
      selected={selected}
      counts={context.counts.get(node.id) || createPortCounts()}
      runState={context.runStates?.get(node.id)}
      onSelect={context.onSelect}
    />
  )
})

const ENGINEERING_NODE_TYPES = { custom: EngineeringCanvasNode }

type OutcomeNodeRenderContextValue = {
  models: Map<string, OutcomeNodeRenderModel>
  nodeOrder: Map<string, number>
  counts: Map<string, PortCounts>
  expandedNodeIds: ReadonlySet<string>
  runStates?: Map<string, NodeRunState>
  probeState?: FlowNodeProbeState
  probeSelectedNodeIds: ReadonlySet<string>
  onSelect: (node: FlowNode) => void
}

const OutcomeNodeRenderContext = createContext<OutcomeNodeRenderContextValue | null>(null)

const OutcomeCanvasNode = memo(function OutcomeCanvasNode({ data, selected }: NodeProps<FlowGraphNode>) {
  const context = useContext(OutcomeNodeRenderContext)
  const node = data as unknown as FlowNode
  const model = context?.models.get(node.id)
  if (!context || !model) return null
  return (
    <FlowNodeCard
      node={node}
      viewMode="detailed"
      order={context.nodeOrder.get(node.id) || 0}
      selected={selected}
      detailOwner={context.expandedNodeIds.has(node.id)}
      compactStatic={false}
      counts={context.counts.get(node.id) || createPortCounts()}
      incomingNodes={[]}
      outgoingNodes={[]}
      presentation={model.view}
      runState={context.runStates?.get(node.id)}
      probeState={context.probeState}
      probeSelected={context.probeSelectedNodeIds.has(node.id)}
      onSelect={context.onSelect}
    />
  )
})

const OUTCOME_NODE_TYPES = { custom: OutcomeCanvasNode }

function completionSummary(run: RunResult | undefined, events: FlowEvent[]) {
  if (!run) return '本次运行已经结束。'
  if (['failed', 'interrupted', 'cancelled'].includes(run.status)) {
    const failedEvent = events.slice().reverse().find((event) => /failed|error|cancelled/i.test(String(event.type || '')))
    return run.error?.message || run.errors?.at(-1)?.message || failedEvent?.message
      || `运行在 ${run.current_state || '未知节点'} 结束，请查看详细日志。`
  }
  if (['paused', 'paused_waiting_user'].includes(run.status)) {
    return run.pending_interaction?.question?.prompt
      || `运行停在 ${run.current_state || '当前节点'}，等待用户继续。`
  }
  const delivery = String(run.delivery?.summary || '').trim()
  if (delivery) return delivery
  const outputEvent = events.slice().reverse().find((event) => {
    const data = event.data as Record<string, unknown> | undefined
    return data && (data.output_value !== undefined || data.output !== undefined)
  })
  const data = outputEvent?.data as Record<string, unknown> | undefined
  const output = data?.output_value ?? data?.output
  if (output !== undefined && output !== null && String(output).trim()) {
    const text = typeof output === 'string' ? output : JSON.stringify(output)
    return text.length > 150 ? `${text.slice(0, 150)}...` : text
  }
  const artifactCount = run.delivery?.artifacts?.length || run.artifacts?.length || 0
  return artifactCount ? `本次流程完成，已生成 ${artifactCount} 个交付产物。` : '本次流程已完成，所有节点已执行结束。'
}
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
type ConnectorPlacement = NodeEditorPosition & {
  width: number
  height: number
  side: NodeEditorSide
  connectorFraction: number
}
type AnnotationPointerState = {
  kind: 'move' | 'resize'
  annotationId: string
  pointerId: number
  clientX: number
  clientY: number
  x: number
  y: number
  width: number
  height: number
  zoom: number
  captureElement: HTMLElement
}

const PORT_LIMIT = 5
const EMPTY_FLOW_EVENTS: FlowEvent[] = []
const NODE_TEMPLATE_MIME = 'application/x-cf-node-template'
const NODE_EDITOR_GAP = 140
const NODE_EDITOR_SLOT_WIDTH = 410
const NODE_EDITOR_SLOT_HEIGHT = 340
const NODE_DROP_GAP = 48

function getGraphNodeSize(node: FlowGraphNode) {
  const styleWidth = typeof node.style?.width === 'number' ? node.style.width : 0
  const styleHeight = typeof node.style?.height === 'number' ? node.style.height : 0
  return {
    width: node.width || node.measured?.width || styleWidth || FLOW_NODE_DIMENSIONS.detailed.width,
    height: node.height || node.measured?.height || styleHeight || FLOW_NODE_DIMENSIONS.detailed.height,
  }
}

function findAvailableNodeDropPosition(
  requested: { x: number; y: number },
  nodes: FlowGraphNode[],
  viewMode: FlowNodeViewMode,
) {
  const targetSize = FLOW_NODE_DIMENSIONS[viewMode]
  const collides = (position: { x: number; y: number }) => nodes.some((node) => {
    const size = getGraphNodeSize(node)
    return position.x < node.position.x + size.width + NODE_DROP_GAP
      && position.x + targetSize.width + NODE_DROP_GAP > node.position.x
      && position.y < node.position.y + size.height + NODE_DROP_GAP
      && position.y + targetSize.height + NODE_DROP_GAP > node.position.y
  })

  if (!collides(requested)) return requested

  const xStep = targetSize.width + NODE_DROP_GAP
  const yStep = targetSize.height + NODE_DROP_GAP
  for (let ring = 1; ring <= 24; ring += 1) {
    const candidates = [
      { x: requested.x, y: requested.y + ring * yStep },
      { x: requested.x + ring * xStep, y: requested.y },
      { x: requested.x - ring * xStep, y: requested.y },
      { x: requested.x, y: requested.y - ring * yStep },
      { x: requested.x + ring * xStep, y: requested.y + ring * yStep },
      { x: requested.x - ring * xStep, y: requested.y + ring * yStep },
    ]
    const available = candidates.find((candidate) => candidate.x >= 0 && candidate.y >= 0 && !collides(candidate))
    if (available) return available
  }

  const bottom = nodes.reduce((value, node) => {
    const size = getGraphNodeSize(node)
    return Math.max(value, node.position.y + size.height)
  }, requested.y)
  return { x: Math.max(0, requested.x), y: bottom + NODE_DROP_GAP }
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

function buildDetailConnector(node: FlowGraphNode, editor: ConnectorPlacement): DetailConnector {
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

function variableNames(value: unknown): string[] {
  if (Array.isArray(value)) return value.flatMap(variableNames)
  if (typeof value !== 'string') return []
  const normalized = value.trim().replace(/^\$\{(.+)\}$/, '$1')
  if (!normalized || normalized.startsWith('{') || normalized.startsWith('[')) return []
  return normalized.split(/[,\n]/).map((item) => item.trim()).filter(Boolean)
}

function nodeOutputNames(node: FlowNode) {
  const params = node.params || {}
  return new Set([
    ...variableNames(node.output),
    ...variableNames(node.primary_output),
    ...variableNames(params.output),
    ...variableNames(params.save_to),
  ])
}

function nodeInputNames(node: FlowNode) {
  const params = node.params || {}
  const bindingInputs = Object.values(node.input_binding || {}).flatMap((value) => {
    const reference = String(value || '').trim()
    if (!reference.startsWith('store:')) return []
    return [reference.slice('store:'.length).split('.')[0]].filter(Boolean)
  })
  return new Set([
    ...variableNames(node.source),
    ...variableNames(params.input),
    ...variableNames(params.source),
    ...bindingInputs,
  ])
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

  return edgeStates
}

export function FlowGraphView({ graph, files = {}, displayMode = 'outcome', engineeringEdgeVisibility = { control: true, data: true, dependency: true, branch: true, failure: true }, engineeringDataRelations: providedEngineeringDataRelations, engineeringNodeModels: providedEngineeringNodeModels, selectedNode, focusNodeId, onSelectNode, onNodeEditorPositionChange, onLayoutSave, autoLayoutOnMount = false, onAutoLayoutComplete, onEdgesSave, onAnnotationsSave, onCreateNode, onDeleteNode, modelPanel, toolPanel, packagePanel, cartridgePanel, protocolInfo = DEFAULT_PROTOCOL_DISPLAY, nodeEditors = [], activeNodeEditorId, onCloseNodeEditor, onCanvasToolChange, requestedCanvasTool, requestedCanvasPanel, onStewardSelectionChange, compactStatic = false, readOnlyGraph = false, runStatus, nodeRunStates, runEvents, runCompletionVisible = false, runCompletion, onDismissRunCompletion, onOpenRunLog, onOpenRunResult, onOpenPendingInteraction, testProbeState }: {
  graph: FlowGraph
  files?: FlowFiles
  displayMode?: DesignDisplayMode
  engineeringEdgeVisibility?: EngineeringEdgeVisibility
  engineeringDataRelations?: EngineeringDataRelation[]
  engineeringNodeModels?: Map<string, EngineeringNodeRenderModel>
  selectedNode: FlowNode | null
  focusNodeId: string | null
  onSelectNode: (node: FlowNode) => void
  onNodeEditorPositionChange?: (editorId: string, position: NodeEditorPosition) => void
  onLayoutSave?: (layout: Record<string, { x: number; y: number }>) => Promise<void>
  autoLayoutOnMount?: boolean
  onAutoLayoutComplete?: () => void
  onEdgesSave?: (edges: FlowEdge[]) => Promise<void>
  onAnnotationsSave?: (annotations: FlowAnnotation[]) => Promise<void>
  onCreateNode?: CreateNodeHandler
  onDeleteNode?: (node: FlowNode) => Promise<void>
  modelPanel?: ReactNode
  toolPanel?: ReactNode
  packagePanel?: ReactNode
  cartridgePanel?: ReactNode
  protocolInfo?: ProtocolDisplayInfo
  nodeEditors?: CanvasNodeEditor[]
  activeNodeEditorId?: string | null
  onCloseNodeEditor?: () => void
  onCanvasToolChange?: (tool: CanvasTool) => void
  requestedCanvasTool?: CanvasTool
  requestedCanvasPanel?: { panel: Exclude<CanvasPanel, null>; requestId: number } | null
  onStewardSelectionChange?: (selection: AIFlowSelection) => void
  compactStatic?: boolean
  readOnlyGraph?: boolean
  runStatus?: string
  nodeRunStates?: Map<string, NodeRunState>
  runEvents?: FlowEvent[]
  runCompletionVisible?: boolean
  runCompletion?: RunResult
  onDismissRunCompletion?: () => void
  onOpenRunLog?: (run: RunResult) => void
  onOpenRunResult?: (run: RunResult) => void
  onOpenPendingInteraction?: () => void
  testProbeState?: FlowNodeProbeState
}) {
  const [fullscreen, setFullscreen] = useState(false)
  const [activeCanvasTool, setActiveCanvasTool] = useState<CanvasTool>('select')
  const [canvasPanel, setCanvasPanel] = useState<CanvasPanel>(null)
  const [selectedLibraryCategoryId, setSelectedLibraryCategoryId] = useState<NodeCategoryId | null>(null)
  const [selectedLibraryPresetId, setSelectedLibraryPresetId] = useState('')
  const [libraryPresetConfig, setLibraryPresetConfig] = useState<Record<string, string>>({})
  const [libraryInputFields, setLibraryInputFields] = useState<LibraryInputFieldDraft[]>(defaultLibraryInputFields)
  const [creatingLibraryNode, setCreatingLibraryNode] = useState(false)
  const [uploadingLibraryFile, setUploadingLibraryFile] = useState(false)
  const libraryFileInputRef = useRef<HTMLInputElement>(null)
  const [canvasLocked, setCanvasLocked] = useState(false)
  const canvasGridGap = 40
  const [workspaceTheme, setWorkspaceTheme] = useState<WorkspaceTheme>(() => loadWorkspaceTheme())
  const [annotations, setAnnotations] = useState<FlowAnnotation[]>(() => graph.annotations || [])
  const [activeAnnotationId, setActiveAnnotationId] = useState<string | null>(null)
  const requestedCanvasToolRef = useRef<CanvasTool | undefined>(requestedCanvasTool)
  const [contextMenu, setContextMenu] = useState<{
    x: number
    y: number
    node: FlowNode | null
    edge?: FlowGraphEdge | null
    side?: 'left' | 'right'
    verticalSide?: 'up' | 'down'
  } | null>(null)
  useEffect(() => onCanvasToolChange?.(activeCanvasTool), [activeCanvasTool, onCanvasToolChange])
  useEffect(() => {
    if (requestedCanvasTool && requestedCanvasTool !== requestedCanvasToolRef.current) {
      requestedCanvasToolRef.current = requestedCanvasTool
      setActiveCanvasTool(requestedCanvasTool)
      setCanvasPanel(null)
    }
  }, [requestedCanvasTool])
  useEffect(() => {
    if (!onEdgesSave && activeCanvasTool === 'connect') setActiveCanvasTool('select')
    if (!onCreateNode && canvasPanel === 'nodes') setCanvasPanel(null)
  }, [activeCanvasTool, canvasPanel, onCreateNode, onEdgesSave])
  useEffect(() => {
    if (!requestedCanvasPanel || readOnlyGraph) return
    onCloseNodeEditor?.()
    setCanvasPanel(requestedCanvasPanel.panel)
    if (requestedCanvasPanel.panel !== 'nodes') setSelectedLibraryCategoryId(null)
  }, [onCloseNodeEditor, readOnlyGraph, requestedCanvasPanel])
  useEffect(() => {
    if (readOnlyGraph && canvasPanel && canvasPanel !== 'base-info') setCanvasPanel(null)
  }, [canvasPanel, readOnlyGraph])
  const [flowInstance, setFlowInstance] = useState<ReactFlowInstance | null>(null)
  const resourcePositionsRef = useRef<Record<string, { x: number; y: number }>>({})
  const [nodeEditorPositions, setNodeEditorPositions] = useState<Record<string, NodeEditorPosition>>({})
  const [draggingEditorId, setDraggingEditorId] = useState<string | null>(null)
  const wrapperRef = useRef<HTMLDivElement | null>(null)
  const deletingNodeRef = useRef(false)
  const lastFittedGraphIdRef = useRef('')
  const autoLayoutGraphIdRef = useRef('')
  const nodeEditorDragRef = useRef<NodeEditorDragState | null>(null)
  const annotationPointerRef = useRef<AnnotationPointerState | null>(null)
  const annotationsRef = useRef<FlowAnnotation[]>(graph.annotations || [])
  const persistedAnnotationsRef = useRef<FlowAnnotation[]>(graph.annotations || [])
  const annotationSavePendingRef = useRef(0)
  const annotationSaveQueueRef = useRef<Promise<void>>(Promise.resolve())
  const nodeDragSnapshotRef = useRef<FlowGraphNode[] | null>(null)
  const resourcePositionDragSnapshotRef = useRef<Record<string, { x: number; y: number }> | null>(null)
  const rightGestureRef = useRef<{ x: number; y: number; moved: boolean } | null>(null)
  const suppressContextMenuUntilRef = useRef(0)
  const updateWorkspaceTheme = useCallback((nextTheme: WorkspaceTheme) => {
    setWorkspaceTheme(saveWorkspaceTheme(nextTheme))
  }, [])
  const runInProgress = ['created', 'running', 'retrying', 'recovering', 'rolling_back'].includes(runStatus || '')
  const runPaused = ['paused', 'paused_waiting_user'].includes(runStatus || '')
  const runActive = runInProgress || runPaused
  const runFinished = ['completed', 'failed', 'cancelled', 'interrupted'].includes(runStatus || '')
  const runFrameVisible = runActive || runFinished
  const runOutcomeClass = runStatus === 'completed'
    ? 'run-outcome-success'
    : ['failed', 'interrupted'].includes(runStatus || '')
      ? 'run-outcome-failure'
      : runStatus === 'cancelled'
        ? 'run-outcome-cancelled'
        : ''
  const nodeOrder = useMemo(() => new Map(graph.nodes.map((node, index) => [node.id, index + 1])), [graph.nodes])
  const nodeById = useMemo(() => new Map(graph.nodes.map((node) => [node.id, node])), [graph.nodes])
  const probeSelectedNodeIds = useMemo(() => new Set(testProbeState?.selectedNodeIds || []), [testProbeState?.selectedNodeIds])
  const graphEdges = useMemo(() => normalizeGraphEdges(graph.edges), [graph.edges])
  const inferredDataRelations = useMemo(() => {
    const producers = new Map<string, string[]>()
    graph.nodes.forEach((node) => nodeOutputNames(node).forEach((key) => {
      producers.set(key, [...(producers.get(key) || []), node.id])
    }))
    const seen = new Set<string>()
    return graph.nodes.reduce<DataRelation[]>((relations, target) => {
      nodeInputNames(target).forEach((key) => {
        const sourceIds = producers.get(key) || []
        sourceIds.forEach((sourceId) => {
          const relationId = `${sourceId}->${target.id}:${key}`
          if (sourceId === target.id || seen.has(relationId)) return
          seen.add(relationId)
          relations.push({ from: sourceId, to: target.id, key, label: plainOutcomeFieldLabel(key) })
        })
      })
      return relations
    }, [])
  }, [graph.nodes])
  const engineeringDataRelations = useMemo(() => (providedEngineeringDataRelations || buildEngineeringDataRelations(graph)).map((relation) => ({
    ...relation,
    key: `${relation.fromField}->${relation.toField}`,
  })), [graph, providedEngineeringDataRelations])
  const visibleGraphEdges = useMemo(() => displayMode !== 'engineering' ? graphEdges : graphEdges.filter((edge) => {
    const label = String(edge.label || '')
    const failure = edge.scope === 'failure' || /fail|error|异常|失败/i.test(label)
    if (failure) return engineeringEdgeVisibility.failure
    if (edge.scope === 'branch') return engineeringEdgeVisibility.branch
    return engineeringEdgeVisibility.control
  }), [displayMode, engineeringEdgeVisibility, graphEdges])
  const visibleEngineeringRelations = useMemo(() => engineeringDataRelations.filter((relation) => (
    relation.kind === 'dependency' ? engineeringEdgeVisibility.dependency : engineeringEdgeVisibility.data
  )), [engineeringDataRelations, engineeringEdgeVisibility])
  const engineeringNodeModels = useMemo(
    () => providedEngineeringNodeModels || buildEngineeringNodeModels(graph, files, nodeRunStates, visibleEngineeringRelations),
    [files, graph, nodeRunStates, providedEngineeringNodeModels, visibleEngineeringRelations],
  )
  const dataRelations = displayMode === 'engineering' ? visibleEngineeringRelations : inferredDataRelations
  const visualEdges = useMemo(() => [
    ...visibleGraphEdges,
    ...dataRelations.map((relation) => ({ from: relation.from, to: relation.to, scope: 'data', label: relation.key })),
  ], [dataRelations, visibleGraphEdges])
  const stableRunEvents = runEvents ?? EMPTY_FLOW_EVENTS
  const runEdgeStates = useMemo(() => buildRunEdgeStates(graphEdges, stableRunEvents), [graphEdges, stableRunEvents])
  const renderGraph = useMemo(() => ({ ...graph, edges: graphEdges }), [graph, graphEdges])
  const authoringNodeCategories = useMemo(() => displayMode === 'engineering'
    ? NODE_CATEGORIES
    : NODE_CATEGORIES.filter((category) => ['input', 'process', 'tool', 'transfer', 'store', 'control'].includes(category.id)), [displayMode])
  const selectedLibraryCategory = useMemo(
    () => authoringNodeCategories.find((category) => category.id === selectedLibraryCategoryId) || null,
    [authoringNodeCategories, selectedLibraryCategoryId],
  )
  const selectedLibraryPreset = useMemo(
    () => selectedLibraryCategory ? getPreset(selectedLibraryCategory.id, selectedLibraryPresetId) : null,
    [selectedLibraryCategory, selectedLibraryPresetId],
  )
  const structuredInputSelected = selectedLibraryCategory?.id === 'input' && selectedLibraryPreset?.id === 'user_form'
  const fileReadPresetSelected = selectedLibraryCategory?.id === 'input' && selectedLibraryPreset?.id === 'read_file'
  const validLibraryInputFields = useMemo(
    () => libraryInputFields.filter((field) => field.label.trim()),
    [libraryInputFields],
  )
  const effectiveLibraryPresetConfig = useMemo(() => {
    if (!structuredInputSelected) return libraryPresetConfig
    const definitions = validLibraryInputFields.map(({ id, label, type, required, default: defaultValue }) => ({
      id,
      label: label.trim(),
      type,
      required,
      ...(defaultValue.trim() ? { default: defaultValue } : {}),
    }))
    return {
      ...libraryPresetConfig,
      fields: definitions.map((field) => field.label).join('、'),
      fields_json: JSON.stringify(definitions),
      output_name: libraryPresetConfig.output_name || 'user_input',
    }
  }, [libraryPresetConfig, structuredInputSelected, validLibraryInputFields])
  const uploadLibraryFile = useCallback(async (file: File | null) => {
    if (!file || uploadingLibraryFile) return
    setUploadingLibraryFile(true)
    try {
      const result = await uploadWorkspaceFile(file)
      setLibraryPresetConfig((current) => ({ ...current, path: result.path }))
      showToast({ title: '文件已就绪', description: result.filename, type: 'success' })
    } catch (error: any) {
      showToast({ title: '文件导入失败', description: error?.message || '请检查文件后重试', type: 'error' })
    } finally {
      setUploadingLibraryFile(false)
    }
  }, [uploadingLibraryFile])
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
  const nodeViewMode: FlowNodeViewMode = compactStatic ? 'compact' : displayMode === 'engineering' ? 'engineering' : 'detailed'
  const expandedMainNodeIds = useMemo(() => new Set(nodeEditors.map((editor) => editor.nodeId)), [nodeEditors])
  const layoutViewMode = nodeViewMode
  const nodeDimensions = useMemo(() => {
    const incoming = new Map<string, number>()
    const outgoing = new Map<string, number>()
    graph.edges.forEach((edge) => {
      incoming.set(edge.to, (incoming.get(edge.to) || 0) + 1)
      outgoing.set(edge.from, (outgoing.get(edge.from) || 0) + 1)
    })
    return Object.fromEntries(graph.nodes.map((node) => [node.id, getFlowNodeDimensions(node, nodeViewMode, {
      incoming: incoming.get(node.id) || 0,
      outgoing: outgoing.get(node.id) || 0,
    })]))
  }, [graph.edges, graph.nodes, nodeViewMode])
  const layoutGraph = useMemo(() => displayMode === 'engineering'
    ? {
        ...renderGraph,
        edges: [
          ...renderGraph.edges,
          ...visibleEngineeringRelations
            .filter((relation) => relation.kind === 'dependency')
            .map((relation) => ({ from: relation.from, to: relation.to, scope: 'engineering_layout' })),
        ],
      }
    : renderGraph, [displayMode, renderGraph, visibleEngineeringRelations])
  const layout = useMemo(() => buildBalancedLayout(layoutGraph, { viewMode: layoutViewMode, nodeDimensions }), [layoutGraph, layoutViewMode, nodeDimensions])
  const edgePortPlan = useMemo(() => {
    const counts = new Map<string, PortCounts>()
    const cursor = new Map<string, number>()
    const edgePorts = new Map<string, EdgePortAssignment>()
    const outgoingCount = new Map<string, number>()
    const incomingCount = new Map<string, number>()
    const portPlanningEdges = displayMode === 'engineering' ? visibleGraphEdges : visualEdges
    portPlanningEdges.forEach((edge) => {
      outgoingCount.set(edge.from, (outgoingCount.get(edge.from) || 0) + 1)
      incomingCount.set(edge.to, (incomingCount.get(edge.to) || 0) + 1)
    })
    graph.nodes.forEach((node) => counts.set(node.id, createPortCounts()))
    portPlanningEdges.forEach((edge, index) => {
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
  }, [displayMode, graph.nodes, layout, nodeById, visibleGraphEdges, visualEdges])
  const engineeringNodeRenderContext = useMemo<EngineeringNodeRenderContextValue>(() => ({
    models: engineeringNodeModels,
    nodeOrder,
    counts: edgePortPlan.counts,
    runStates: nodeRunStates,
    onSelect: onSelectNode,
  }), [edgePortPlan.counts, engineeringNodeModels, nodeOrder, nodeRunStates, onSelectNode])
  const outcomeNodeModels = useMemo(() => buildOutcomeNodeModels(renderGraph, nodeRunStates), [nodeRunStates, renderGraph])
  const outcomeNodeRenderContext = useMemo<OutcomeNodeRenderContextValue>(() => ({
    models: outcomeNodeModels,
    nodeOrder,
    counts: edgePortPlan.counts,
    expandedNodeIds: expandedMainNodeIds,
    runStates: nodeRunStates,
    probeState: testProbeState,
    probeSelectedNodeIds,
    onSelect: onSelectNode,
  }), [edgePortPlan.counts, expandedMainNodeIds, nodeOrder, nodeRunStates, onSelectNode, outcomeNodeModels, probeSelectedNodeIds, testProbeState])
  // Live material carriers were removed: the running-node highlight plus the
  // runtime inspector (input/output/artifacts) cover what they showed, without
  // the translucent ghosting they occasionally left behind.
  const initialFocusId = focusNodeId || graph.nodes.find((node) => node.scope !== 'root')?.id || graph.nodes[0]?.id || null

  const CompactCanvasNode = useCallback(({ data }: { data: Record<string, unknown> }) => {
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
  }, [compactStatic, edgePortPlan, expandedMainNodeIds, graphEdges, nodeById, nodeOrder, nodeRunStates, nodeViewMode, onSelectNode, probeSelectedNodeIds, selectedNode, testProbeState])

  const compactNodeTypes = useMemo(() => ({ custom: CompactCanvasNode }), [CompactCanvasNode])
  const nodeTypes = compactStatic ? compactNodeTypes : displayMode === 'engineering' ? ENGINEERING_NODE_TYPES : OUTCOME_NODE_TYPES
  const initialNodes: FlowGraphNode[] = useMemo(() => graph.nodes.map((node) => {
    const dimensions = nodeDimensions[node.id] || FLOW_NODE_DIMENSIONS[nodeViewMode]
    const runState = nodeRunStates?.get(node.id)
    const resource = isEngineeringResourceNode(node)
    return {
      id: node.id,
      type: 'custom',
      position: resourcePositionsRef.current[node.id] || layout[node.id] || { x: node.x, y: node.y },
      data: {
        ...node,
        __runtimeRenderKey: `${displayMode}:${runState?.status || 'normal'}`,
      } as unknown as Record<string, unknown>,
      className: runState ? `cf-runtime-node run-node-${runState.status}` : '',
      deletable: !resource && !node.locked && !isStartNode(node, node.id),
      // width anchors the layout; height is left to content ("auto") so the node
      // hugs its recipe/sections data instead of clipping it to an estimate
      style: { width: dimensions.width, height: 'auto' as const },
    }
  }), [displayMode, graph.nodes, layout, nodeDimensions, nodeRunStates, nodeViewMode])
  const initialEdges: FlowGraphEdge[] = useMemo(() => {
    const branchLaneBySource = new Map<string, number>()
    const controlEdges = visibleGraphEdges.map((edge, index) => {
      const branch = edge.scope === 'branch'
      const edgeLabel = String(edge.label || '').trim()
      const planEdge = edge as FlowEdge & { plan_edge_id?: string; plan_edge_kind?: string; plan_transition?: string }
      const planEdgeId = String(planEdge.plan_edge_id || '').trim()
      const planEdgeKind = String(planEdge.plan_edge_kind || '').trim()
      const planTransition = String(planEdge.plan_transition || '').trim()
      const failureRoute = edge.scope === 'failure' || /fail|error|异常|失败/i.test(edgeLabel)
      const runEdgeStatus = runEdgeStates.get(`${edge.from}->${edge.to}`)
      const isRunActive = runEdgeStatus === 'active'
      const isRunVisited = runEdgeStatus === 'visited'
      const sourceNode = nodeById.get(edge.from)
      const sourceAccent = isStartNode(sourceNode, edge.from)
        ? '#7d8791'
        : sourceNode ? getNodeCategory(sourceNode).color : 'var(--accent)'
      const normalStroke = displayMode === 'engineering'
        ? failureRoute ? '#d26764' : branch ? '#2f7fbe' : '#6d7c85'
        : branch ? '#5e8bd8' : sourceAccent
      const lane = branch ? (branchLaneBySource.get(edge.from) || 0) : 0
      if (branch) branchLaneBySource.set(edge.from, lane + 1)
      const ports = edgePortPlan.edgePorts.get(`${index}:${edge.from}->${edge.to}`) || { sourceSide: 'right', targetSide: 'left', sourceIndex: 0, targetIndex: 0 }
      const sourcePoint = layout[edge.from]
      const targetPoint = layout[edge.to]
      const loopY = sourcePoint && targetPoint ? Math.min(sourcePoint.y, targetPoint.y) - 72 - lane * 42 : undefined
      return {
        id: planEdgeId ? `plan-edge-${planEdgeId}-${planTransition || 'transition'}-${edge.from}-${edge.to}` : `edge-${index}-${edge.from}-${edge.to}`,
        source: edge.from,
        target: edge.to,
        sourceHandle: displayMode === 'engineering' ? engineeringControlHandleId('source', ports.sourceSide) : getPortHandleId('source', ports.sourceSide, ports.sourceIndex),
        targetHandle: displayMode === 'engineering' ? engineeringControlHandleId('target', ports.targetSide) : getPortHandleId('target', ports.targetSide, ports.targetIndex),
        className: `${displayMode === 'engineering' ? `cf-engineering-control-edge${failureRoute ? ' failure' : branch ? ' branch' : ''}` : ''} ${runActive
          ? isRunActive ? 'cf-run-edge-active' : isRunVisited ? 'cf-run-edge-visited' : 'cf-run-edge-pending'
          : ''}`,
        animated: isRunActive,
        type: 'default',
        label: displayMode === 'engineering' ? edgeLabel || (failureRoute ? '失败处理' : branch ? '条件分支' : undefined) : branch ? edgeLabel || '分支' : undefined,
        data: {
          scope: edge.scope || 'root',
          label: edge.label || '',
          lane,
          loopY,
          runEdgeStatus: runEdgeStatus || '',
          planEdgeId,
          planEdgeKind,
          planTransition,
        },
        zIndex: isRunActive ? 3 : isRunVisited ? 2 : 0,
        style: {
          stroke: isRunActive ? '#d05b2f' : normalStroke,
          strokeWidth: isRunActive ? 5 : isRunVisited ? 3.4 : branch ? 2.4 : 2.8,
          strokeDasharray: isRunActive ? '9 7' : branch ? '6 5' : undefined,
          filter: isRunActive ? 'drop-shadow(0 0 4px rgba(208, 91, 47, .72))' : undefined,
        },
        markerEnd: { type: MarkerType.ArrowClosed, color: isRunActive ? '#d05b2f' : normalStroke },
      }
    })
    const relationEdges = dataRelations.map((relation, relationIndex) => {
      const index = visibleGraphEdges.length + relationIndex
      const ports = edgePortPlan.edgePorts.get(`${index}:${relation.from}->${relation.to}`) || { sourceSide: 'right', targetSide: 'left', sourceIndex: 0, targetIndex: 0 }
      const engineeringRelation = displayMode === 'engineering' && relation.fromField && relation.toField
      return {
        id: `data-${relation.from}-${relation.to}-${relation.key}`,
        source: relation.from,
        target: relation.to,
        sourceHandle: engineeringRelation ? engineeringHandleId('source', relation.fromField!) : getPortHandleId('source', ports.sourceSide, ports.sourceIndex),
        targetHandle: engineeringRelation ? engineeringHandleId('target', relation.toField!) : getPortHandleId('target', ports.targetSide, ports.targetIndex),
        className: `cf-data-edge${relation.kind === 'dependency' ? ' dependency' : ''}`,
        type: 'default',
        label: relation.label || relation.key,
        selectable: false,
        deletable: false,
        focusable: false,
        data: { scope: 'data', label: relation.label || relation.key, expression: relation.expression || relation.key, source: relation.source || '' },
        zIndex: engineeringRelation ? 2 : -1,
        style: engineeringRelation
          ? relation.kind === 'dependency'
            ? { stroke: '#8664bd', strokeWidth: 2.2, strokeDasharray: '6 4' }
            : { stroke: '#3479df', strokeWidth: 2.4 }
          : { stroke: '#6f968b', strokeWidth: 1.8, strokeDasharray: '3 6' },
        markerEnd: { type: MarkerType.ArrowClosed, color: engineeringRelation ? relation.kind === 'dependency' ? '#8664bd' : '#3479df' : '#6f968b' },
      } satisfies FlowGraphEdge
    })
    return [...controlEdges, ...relationEdges]
  }, [dataRelations, displayMode, edgePortPlan, layout, nodeById, runActive, runEdgeStates, visibleGraphEdges])

  const [nodes, setNodes] = useState<FlowGraphNode[]>(initialNodes)
  const [edges, setEdges] = useState<FlowGraphEdge[]>(initialEdges)
  const canvasNodeIds = useMemo(() => initialNodes.map((node) => node.id), [initialNodes])
  const persistedEdgesRef = useRef<FlowGraphEdge[]>(initialEdges)
  const edgeSavePendingRef = useRef(0)
  const edgeSaveQueueRef = useRef<Promise<void>>(Promise.resolve())
  const pendingCreatedNodeFocusRef = useRef<string | null>(null)
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
    const overlapsMainNode = (candidate: { x: number; y: number; width: number; height: number }) => nodes.some((item) => {
      const size = getGraphNodeSize(item)
      return !(
        candidate.x + candidate.width + 12 <= item.position.x
        || item.position.x + size.width + 12 <= candidate.x
        || candidate.y + candidate.height + 12 <= item.position.y
        || item.position.y + size.height + 12 <= candidate.y
      )
    })

    return nodeEditors.reduce<NodeEditorPlacement[]>((result, editor) => {
      const graphNode = nodes.find((node) => node.id === editor.nodeId)
      if (!graphNode) return result
      const savedPosition = nodeEditorPositions[editor.editorId] || editor.position
      if (savedPosition) {
        const placement = { ...editor, ...savedPosition, side: resolveEditorSide(graphNode, savedPosition, editor.width, editor.height) }
        occupied.push({ ...savedPosition, width: editor.width, height: editor.height })
        result.push(placement)
        return result
      }
      const { width: nodeWidth, height: nodeHeight } = getGraphNodeSize(graphNode)
      const centerX = graphNode.position.x + nodeWidth / 2
      const centerY = graphNode.position.y + nodeHeight / 2
      const satelliteGap = 48
      const topY = Math.max(24, graphNode.position.y - editor.height - satelliteGap)
      const bottomY = graphNode.position.y + nodeHeight + 34
      const leftX = graphNode.position.x - editor.width - satelliteGap
      const rightX = graphNode.position.x + nodeWidth + satelliteGap
      const preferredBySection: Record<NodeDetailSection, Omit<NodeEditorPlacement, keyof CanvasNodeEditor>> = {
        contract: { x: leftX, y: Math.max(24, graphNode.position.y - 150), side: 'left' },
        inputs: { x: leftX, y: centerY - editor.height / 2, side: 'left' },
        outputs: { x: centerX - editor.width / 2, y: bottomY, side: 'bottom' },
        component: { x: rightX, y: Math.max(24, graphNode.position.y - 180), side: 'right' },
        model: { x: rightX, y: Math.max(24, graphNode.position.y - 180), side: 'right' },
        resources: { x: rightX, y: centerY - editor.height / 2, side: 'right' },
        routing: { x: leftX, y: centerY - editor.height / 2, side: 'left' },
        safety: { x: rightX, y: bottomY, side: 'bottom' },
        runtime: { x: rightX, y: centerY - editor.height / 2, side: 'right' },
        artifacts: { x: centerX - editor.width / 2, y: bottomY, side: 'bottom' },
      }
      const baseX = rightX
      const baseY = Math.max(24, graphNode.position.y - 180)
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
      const wrapper = wrapperRef.current
      const viewport = flowInstance?.getViewport()
      const visiblePadding = 24
      const visibleLeft = wrapper && viewport ? (visiblePadding - viewport.x) / viewport.zoom : Number.NEGATIVE_INFINITY
      const visibleTop = wrapper && viewport ? (visiblePadding - viewport.y) / viewport.zoom : Number.NEGATIVE_INFINITY
      const visibleRight = wrapper && viewport ? (wrapper.clientWidth - visiblePadding - viewport.x) / viewport.zoom : Number.POSITIVE_INFINITY
      const visibleBottom = wrapper && viewport ? (wrapper.clientHeight - visiblePadding - viewport.y) / viewport.zoom : Number.POSITIVE_INFINITY
      const keepVisible = (candidate: Omit<NodeEditorPlacement, keyof CanvasNodeEditor>) => ({
        ...candidate,
        x: Math.min(Math.max(candidate.x, visibleLeft), Math.max(visibleLeft, visibleRight - editor.width)),
        y: Math.min(Math.max(candidate.y, visibleTop), Math.max(visibleTop, visibleBottom - editor.height)),
      })
      const visibleCandidates = candidates.map(keepVisible)
      const chosen = visibleCandidates.find((candidate) => {
        const bounds = { ...candidate, width: editor.width, height: editor.height }
        return !overlaps(bounds) && !overlapsMainNode(bounds)
      }) || visibleCandidates.find((candidate) => !overlaps({ ...candidate, width: editor.width, height: editor.height })) || visibleCandidates[0]
      occupied.push({ ...chosen, width: editor.width, height: editor.height })
      result.push({ ...editor, ...chosen })
      return result
    }, [])
  }, [flowInstance, nodeEditorPositions, nodeEditors, nodes])
  const hasNodeEditors = nodeEditorPlacements.length > 0

  useEffect(() => {
    if (!onNodeEditorPositionChange) return
    nodeEditorPlacements.forEach((editor) => {
      if (editor.position || nodeEditorPositions[editor.editorId]) return
      onNodeEditorPositionChange(editor.editorId, { x: editor.x, y: editor.y })
    })
  }, [nodeEditorPlacements, nodeEditorPositions, onNodeEditorPositionChange])

  useEffect(() => {
    setNodes((current) => graphNodesMatch(current, initialNodes) ? current : initialNodes)
    if (flowInstance && !graphNodesMatch(flowInstance.getNodes() as FlowGraphNode[], initialNodes)) {
      flowInstance.setNodes(initialNodes)
    }
  }, [flowInstance, initialNodes])
  useEffect(() => {
    if (edgeSavePendingRef.current > 0) return
    persistedEdgesRef.current = initialEdges
    setEdges((current) => graphEdgesMatch(current, initialEdges) ? current : initialEdges)
    if (flowInstance && !graphEdgesMatch(flowInstance.getEdges() as FlowGraphEdge[], initialEdges)) {
      flowInstance.setEdges(initialEdges)
    }
  }, [flowInstance, initialEdges])
  useEffect(() => {
    resourcePositionsRef.current = {}
  }, [graph.id])
  useEffect(() => {
    if (!flowInstance || compactStatic) return
    const selectedId = selectedNode?.id || null
    const currentNodes = flowInstance.getNodes() as FlowGraphNode[]
    const selectionMatches = currentNodes.every((node) => Boolean(node.selected) === (node.id === selectedId))
    if (selectionMatches) return
    flowInstance.setNodes(currentNodes.map((node) => (
      Boolean(node.selected) === (node.id === selectedId)
        ? node
        : { ...node, selected: node.id === selectedId }
    )))
  }, [compactStatic, displayMode, flowInstance, selectedNode?.id])
  useEffect(() => {
    if (annotationSavePendingRef.current > 0) return
    const next = graph.annotations || []
    annotationsRef.current = next
    persistedAnnotationsRef.current = next
    setAnnotations(next)
    setActiveAnnotationId(null)
    annotationPointerRef.current = null
  }, [graph.annotations, graph.id])
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
        { zoom: displayMode === 'engineering' ? 1.02 : 0.78, duration: 260 },
      )
    })
    return () => window.cancelAnimationFrame(frame)
  }, [compactStatic, displayMode, flowInstance, graph.id, hasNodeEditors, initialFocusId, initialNodes, nodeViewMode])

  const buildLayoutFromNodes = useCallback((items: FlowGraphNode[]) => {
    const nextLayout: Record<string, { x: number; y: number }> = {}
    items.forEach((node) => {
      const flowNode = node.data as unknown as FlowNode
      if (isEngineeringResourceNode(flowNode)) return
      nextLayout[node.id] = {
        x: Math.round(node.position.x),
        y: Math.round(node.position.y),
      }
    })
    return nextLayout
  }, [])

  const buildFlowEdges = useCallback((items: FlowGraphEdge[]): FlowEdge[] => {
    const seen = new Set<string>()
    return items.reduce<FlowEdge[]>((result, edge) => {
      if (!edge.source || !edge.target || edge.source === edge.target) return result
      const scope = String(edge.data?.scope || 'root')
      const source = nodeById.get(edge.source)
      const target = nodeById.get(edge.target)
      if (scope === 'data' || scope === 'engineering_dependency' || (source && isEngineeringResourceNode(source)) || (target && isEngineeringResourceNode(target))) return result
      const label = String(edge.data?.label || edge.label || '').trim()
      const key = `${scope}:${edge.source}->${edge.target}`
      if (seen.has(key)) return result
      seen.add(key)
      result.push({ from: edge.source, to: edge.target, scope, ...(label ? { label } : {}) })
      return result
    }, [])
  }, [nodeById])

  const saveEdgesQuietly = useCallback(async (items: FlowGraphEdge[]) => {
    if (compactStatic || readOnlyGraph || !onEdgesSave) return false
    edgeSavePendingRef.current += 1
    const save = edgeSaveQueueRef.current.then(() => onEdgesSave(buildFlowEdges(items)))
    edgeSaveQueueRef.current = save.catch(() => undefined)
    try {
      await save
      persistedEdgesRef.current = items
      return true
    } catch (error: any) {
      if (edgeSavePendingRef.current === 1) {
        const persisted = persistedEdgesRef.current
        setEdges(persisted)
        flowInstance?.setEdges(persisted)
      }
      showToast({ title: '保存连线失败', description: error?.message || String(error), type: 'error' })
      return false
    } finally {
      edgeSavePendingRef.current -= 1
    }
  }, [buildFlowEdges, compactStatic, flowInstance, onEdgesSave, readOnlyGraph])

  const validateConnection = useCallback((sourceId: string, targetId: string) => {
    const source = nodeById.get(sourceId)
    const target = nodeById.get(targetId)
    if (!source || !target) return '节点不存在，无法连接'
    if (isEngineeringResourceNode(source) || isEngineeringResourceNode(target)) return RESOURCE_EDGE_REJECT_MESSAGE
    if (sourceId === targetId) return '不能连接到自身'
    if (isStartNode(target, targetId)) return '开始节点不能作为链路目标'
    if (source.type === 'terminal' && !isStartNode(source, sourceId)) return '结尾节点不能再接出链路'
    return ''
  }, [nodeById])

  const fitBoundsIntoCanvas = useCallback((bounds: { x: number; y: number; width: number; height: number }, duration = 240) => {
    const wrapper = wrapperRef.current
    if (!flowInstance || !wrapper) return
    const maxZoom = compactStatic ? 0.82 : displayMode === 'engineering' ? 0.82 : 0.92
    const viewport = getViewportForBounds(bounds, wrapper.clientWidth, wrapper.clientHeight, 0.18, maxZoom, displayMode === 'engineering' ? 0.13 : 0.08)
    void flowInstance.setViewport(viewport, { duration })
  }, [compactStatic, displayMode, flowInstance])

  const fitCanvasContents = useCallback((duration = 240) => {
    if (nodes.length === 0) return
    const rectangles = [
      ...nodes.map((node) => ({ ...node.position, ...getGraphNodeSize(node) })),
      ...nodeEditorPlacements.map((editor) => ({ x: editor.x, y: editor.y, width: editor.width, height: editor.height })),
    ]
    const minX = Math.min(...rectangles.map((rect) => rect.x))
    const minY = Math.min(...rectangles.map((rect) => rect.y))
    const maxX = Math.max(...rectangles.map((rect) => rect.x + rect.width))
    const maxY = Math.max(...rectangles.map((rect) => rect.y + rect.height))
    fitBoundsIntoCanvas({ x: minX, y: minY, width: maxX - minX, height: maxY - minY }, duration)
  }, [fitBoundsIntoCanvas, nodeEditorPlacements, nodes])

  useEffect(() => {
    const nodeId = pendingCreatedNodeFocusRef.current
    if (!nodeId) return
    const target = nodes.find((node) => node.id === nodeId)
    if (!target) return
    pendingCreatedNodeFocusRef.current = null
    const frame = window.requestAnimationFrame(() => {
      const size = getGraphNodeSize(target)
      fitBoundsIntoCanvas({ ...target.position, ...size }, 250)
    })
    return () => window.cancelAnimationFrame(frame)
  }, [fitBoundsIntoCanvas, nodes])

  const handleFlowInit = useCallback((instance: ReactFlowInstance) => {
    setFlowInstance(instance)
    lastFittedGraphIdRef.current = ''
    instance.setNodes(initialNodes)
    instance.setEdges(initialEdges)
    if (compactStatic) return
    window.requestAnimationFrame(() => {
      const target = instance.getNode(initialFocusId || initialNodes[0]?.id) || initialNodes[0]
      if (!target) return
      const targetSize = getGraphNodeSize(target as FlowGraphNode)
      instance.setCenter(
        target.position.x + targetSize.width / 2,
        target.position.y + targetSize.height / 2,
        { zoom: displayMode === 'engineering' ? 1.02 : 0.78, duration: 0 },
      )
    })
  }, [compactStatic, displayMode, initialEdges, initialFocusId, initialNodes])

  const beginNodeEditorDrag = useCallback((event: React.PointerEvent<HTMLDivElement>, editor: NodeEditorPlacement) => {
    const target = event.target as HTMLElement
    if (!target.closest('.cf-node-satellite-head')) return false
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

  const replaceAnnotations = useCallback((next: FlowAnnotation[]) => {
    annotationsRef.current = next
    setAnnotations(next)
  }, [])

  const patchAnnotation = useCallback((annotationId: string, patch: Partial<FlowAnnotation>) => {
    replaceAnnotations(annotationsRef.current.map((annotation) => (
      annotation.id === annotationId ? { ...annotation, ...patch } : annotation
    )))
  }, [replaceAnnotations])

  const commitAnnotations = useCallback(async (next = annotationsRef.current) => {
    if (!onAnnotationsSave) return
    annotationSavePendingRef.current += 1
    const save = annotationSaveQueueRef.current.then(() => onAnnotationsSave(next))
    annotationSaveQueueRef.current = save.catch(() => undefined)
    try {
      await save
      persistedAnnotationsRef.current = next
    } catch (error: any) {
      if (annotationSavePendingRef.current === 1) replaceAnnotations(persistedAnnotationsRef.current)
      showToast({ title: '注释保存失败', description: error?.message || String(error), type: 'error' })
    } finally {
      annotationSavePendingRef.current -= 1
    }
  }, [onAnnotationsSave, replaceAnnotations])

  const createAnnotation = useCallback((anchorNode: FlowNode | null = null) => {
    if (!onAnnotationsSave || !flowInstance) return
    const width = 320
    const height = 180
    const graphNode = anchorNode ? flowInstance.getNode(anchorNode.id) as FlowGraphNode | undefined : undefined
    const occupied = [
      ...(flowInstance.getNodes() as FlowGraphNode[]).map((node) => ({ ...node.position, ...getGraphNodeSize(node) })),
      ...annotationsRef.current.map((annotation) => ({ x: annotation.x, y: annotation.y, width: annotation.width, height: annotation.collapsed ? 54 : annotation.height })),
    ]
    const isAvailable = (candidate: { x: number; y: number }) => occupied.every((item) => (
      candidate.x + width + 28 <= item.x
      || item.x + item.width + 28 <= candidate.x
      || candidate.y + height + 28 <= item.y
      || item.y + item.height + 28 <= candidate.y
    ))
    const wrapper = wrapperRef.current
    const wrapperBounds = wrapper?.getBoundingClientRect()
    const visibleTopLeft = flowInstance.screenToFlowPosition({ x: wrapperBounds?.left || 0, y: wrapperBounds?.top || 0 })
    const visibleBottomRight = flowInstance.screenToFlowPosition({
      x: wrapperBounds?.right || window.innerWidth,
      y: wrapperBounds?.bottom || window.innerHeight,
    })
    const isVisible = (candidate: { x: number; y: number }) => (
      candidate.x >= visibleTopLeft.x + 18
      && candidate.y >= visibleTopLeft.y + 18
      && candidate.x + width <= visibleBottomRight.x - 18
      && candidate.y + height <= visibleBottomRight.y - 18
    )
    const isUiClear = (candidate: { x: number; y: number }) => {
      if (!wrapper) return true
      const topLeft = flowInstance.flowToScreenPosition(candidate)
      const bottomRight = flowInstance.flowToScreenPosition({ x: candidate.x + width, y: candidate.y + height })
      const candidateRect = {
        left: Math.min(topLeft.x, bottomRight.x) - 14,
        right: Math.max(topLeft.x, bottomRight.x) + 14,
        top: Math.min(topLeft.y, bottomRight.y) - 14,
        bottom: Math.max(topLeft.y, bottomRight.y) + 14,
      }
      const overlays = wrapper.querySelectorAll<HTMLElement>(
        '.react-flow__minimap, .cf-canvas-status, .cf-canvas-tool-panel, .cf-canvas-tool-rail',
      )
      return [...overlays].every((overlay) => {
        const rect = overlay.getBoundingClientRect()
        return candidateRect.right <= rect.left
          || rect.right <= candidateRect.left
          || candidateRect.bottom <= rect.top
          || rect.bottom <= candidateRect.top
      })
    }
    let candidates: Array<{ x: number; y: number }> = []
    if (graphNode) {
      const nodeSize = getGraphNodeSize(graphNode)
      const centerX = graphNode.position.x + nodeSize.width / 2
      const centerY = graphNode.position.y + nodeSize.height / 2
      const belowY = graphNode.position.y + nodeSize.height + 72
      const aboveY = graphNode.position.y - height - 72
      candidates = [
        { x: graphNode.position.x + nodeSize.width + 72, y: centerY - height / 2 },
        { x: centerX - width / 2, y: belowY },
        { x: centerX - width - 80, y: belowY },
        { x: centerX + 80, y: belowY },
        { x: graphNode.position.x - width - 72, y: centerY - height / 2 },
        { x: centerX - width / 2, y: aboveY },
        { x: centerX - width - 80, y: aboveY },
        { x: centerX + 80, y: aboveY },
      ]
    } else {
      const center = flowInstance.screenToFlowPosition({
        x: (wrapper?.getBoundingClientRect().left || 0) + (wrapper?.clientWidth || window.innerWidth) / 2,
        y: (wrapper?.getBoundingClientRect().top || 0) + (wrapper?.clientHeight || window.innerHeight) / 2,
      })
      const base = { x: center.x - width / 2, y: center.y - height / 2 }
      candidates = [
        base,
        { x: base.x, y: base.y - height - 56 },
        { x: base.x, y: base.y + height + 56 },
        { x: base.x - width - 56, y: base.y },
        { x: base.x + width + 56, y: base.y },
        { x: base.x - width - 56, y: base.y - height - 56 },
        { x: base.x + width + 56, y: base.y - height - 56 },
      ]
    }
    const position = candidates.find((candidate) => isAvailable(candidate) && isVisible(candidate) && isUiClear(candidate))
      || candidates.find((candidate) => isAvailable(candidate) && isUiClear(candidate))
      || candidates.find((candidate) => isVisible(candidate) && isUiClear(candidate))
      || candidates.find((candidate) => isAvailable(candidate) && isVisible(candidate))
      || candidates.find(isAvailable)
      || candidates.find(isVisible)
      || candidates[0]
      || { x: 0, y: 0 }
    const annotation: FlowAnnotation = {
      id: `annotation_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 7)}`,
      title: anchorNode ? `${anchorNode.display_name || anchorNode.title} 注释` : '新注释',
      body: '',
      x: Math.round(position.x),
      y: Math.round(position.y),
      width,
      height,
      tone: 'neutral',
      ...(anchorNode ? { anchor: { type: 'node' as const, id: anchorNode.id } } : {}),
    }
    const next = [...annotationsRef.current, annotation]
    replaceAnnotations(next)
    setActiveAnnotationId(annotation.id)
    setCanvasPanel('notes')
    setContextMenu(null)
    void commitAnnotations(next)
  }, [commitAnnotations, flowInstance, onAnnotationsSave, replaceAnnotations])

  const deleteAnnotation = useCallback((annotationId: string) => {
    const annotation = annotationsRef.current.find((item) => item.id === annotationId)
    if (!annotation || !window.confirm(`删除注释“${annotation.title || '未命名注释'}”？`)) return
    const next = annotationsRef.current.filter((item) => item.id !== annotationId)
    replaceAnnotations(next)
    setActiveAnnotationId((current) => current === annotationId ? null : current)
    void commitAnnotations(next)
  }, [commitAnnotations, replaceAnnotations])

  const focusAnnotation = useCallback((annotation: FlowAnnotation) => {
    setActiveAnnotationId(annotation.id)
    if (!flowInstance) return
    const viewport = flowInstance.getViewport()
    const height = annotation.collapsed ? 54 : annotation.height
    flowInstance.setCenter(annotation.x + annotation.width / 2, annotation.y + height / 2, { zoom: viewport.zoom, duration: 180 })
  }, [flowInstance])

  const beginAnnotationMove = useCallback((event: React.PointerEvent<HTMLDivElement>, annotation: FlowAnnotation) => {
    const target = event.target as HTMLElement
    if (!onAnnotationsSave || !target.closest('.cf-canvas-annotation-head')) return
    if (target.closest('button, input, textarea, select, a, [contenteditable="true"]')) return
    const zoom = flowInstance?.getViewport().zoom || 1
    annotationPointerRef.current = {
      kind: 'move',
      annotationId: annotation.id,
      pointerId: event.pointerId,
      clientX: event.clientX,
      clientY: event.clientY,
      x: annotation.x,
      y: annotation.y,
      width: annotation.width,
      height: annotation.height,
      zoom,
      captureElement: event.currentTarget,
    }
    setActiveAnnotationId(annotation.id)
    event.currentTarget.setPointerCapture(event.pointerId)
    event.preventDefault()
    event.stopPropagation()
  }, [flowInstance, onAnnotationsSave])

  const beginAnnotationResize = useCallback((event: React.PointerEvent<HTMLButtonElement>, annotation: FlowAnnotation) => {
    if (!onAnnotationsSave) return
    const zoom = flowInstance?.getViewport().zoom || 1
    annotationPointerRef.current = {
      kind: 'resize',
      annotationId: annotation.id,
      pointerId: event.pointerId,
      clientX: event.clientX,
      clientY: event.clientY,
      x: annotation.x,
      y: annotation.y,
      width: annotation.width,
      height: annotation.height,
      zoom,
      captureElement: event.currentTarget,
    }
    setActiveAnnotationId(annotation.id)
    event.currentTarget.setPointerCapture(event.pointerId)
    event.preventDefault()
    event.stopPropagation()
  }, [flowInstance, onAnnotationsSave])

  const moveAnnotationPointer = useCallback((event: React.PointerEvent<HTMLDivElement>) => {
    const pointer = annotationPointerRef.current
    if (!pointer || pointer.pointerId !== event.pointerId) return
    const dx = (event.clientX - pointer.clientX) / pointer.zoom
    const dy = (event.clientY - pointer.clientY) / pointer.zoom
    patchAnnotation(pointer.annotationId, pointer.kind === 'move'
      ? { x: Math.round(pointer.x + dx), y: Math.round(pointer.y + dy) }
      : { width: Math.max(240, Math.min(640, Math.round(pointer.width + dx))), height: Math.max(120, Math.min(520, Math.round(pointer.height + dy))) })
    event.preventDefault()
    event.stopPropagation()
  }, [patchAnnotation])

  const endAnnotationPointer = useCallback((event: React.PointerEvent<HTMLDivElement>) => {
    const pointer = annotationPointerRef.current
    if (!pointer || pointer.pointerId !== event.pointerId) return
    annotationPointerRef.current = null
    if (pointer.captureElement.hasPointerCapture(event.pointerId)) pointer.captureElement.releasePointerCapture(event.pointerId)
    void commitAnnotations()
    event.preventDefault()
    event.stopPropagation()
  }, [commitAnnotations])

  const handleAutoAlign = useCallback(async () => {
    if (!onLayoutSave) return
    const currentNodes = (flowInstance?.getNodes() as FlowGraphNode[] | undefined) || nodes
    const wrapperWidth = wrapperRef.current?.clientWidth || 1600
    const wrapperHeight = wrapperRef.current?.clientHeight || 800
    const result = buildClusterAwareLayout({
      nodes: currentNodes.map((node) => ({ id: node.id, ...node.position, ...getGraphNodeSize(node) })),
      satellites: nodeEditorPlacements.map((editor) => ({
        editorId: editor.editorId,
        nodeId: editor.nodeId,
        x: editor.x,
        y: editor.y,
        width: editor.width,
        height: editor.height,
      })),
      edges: renderGraph.edges || [],
      targetAspect: wrapperWidth / wrapperHeight,
    })
    const aligned = currentNodes.map((node) => ({ ...node, position: result.nodeLayout[node.id] || node.position }))
    setNodes(aligned)
    flowInstance?.setNodes(aligned)
    try {
      await onLayoutSave(buildLayoutFromNodes(aligned))
    } catch (error: any) {
      setNodes(currentNodes)
      flowInstance?.setNodes(currentNodes)
      showToast({ title: '自动整理失败', description: error?.message || String(error), type: 'error' })
      return false
    }
    setNodeEditorPositions((current) => ({ ...current, ...result.satelliteLayout }))
    Object.entries(result.satelliteLayout).forEach(([editorId, position]) => {
      onNodeEditorPositionChange?.(editorId, position)
    })
    setCanvasPanel(null)
    window.requestAnimationFrame(() => {
      fitBoundsIntoCanvas(result.bounds, 260)
    })
    return true
  }, [buildLayoutFromNodes, fitBoundsIntoCanvas, flowInstance, nodeEditorPlacements, nodes, onLayoutSave, onNodeEditorPositionChange, renderGraph.edges])

  useEffect(() => {
    if (!autoLayoutOnMount || !flowInstance || !onLayoutSave || initialNodes.length === 0) return
    const graphId = graph.id || '__anonymous_graph__'
    if (autoLayoutGraphIdRef.current === graphId) return
    autoLayoutGraphIdRef.current = graphId
    let started = false
    const frame = window.requestAnimationFrame(() => {
      started = true
      void handleAutoAlign()
        .then((saved) => {
          if (saved) onAutoLayoutComplete?.()
          else autoLayoutGraphIdRef.current = ''
        })
        .catch((error: any) => {
          autoLayoutGraphIdRef.current = ''
          showToast({ title: '自动整理失败', description: error?.message || String(error), type: 'error' })
        })
    })
    return () => {
      if (started) return
      window.cancelAnimationFrame(frame)
      if (autoLayoutGraphIdRef.current === graphId) autoLayoutGraphIdRef.current = ''
    }
  }, [autoLayoutOnMount, flowInstance, graph.id, handleAutoAlign, initialNodes.length, onAutoLayoutComplete, onLayoutSave])

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
    setLibraryInputFields(defaultLibraryInputFields())
  }, [onCloseNodeEditor])

  const startNodeTemplateDrag = useCallback((event: React.DragEvent<HTMLButtonElement>, categoryId: NodeCategoryId) => {
    const preset = getPreset(categoryId, categoryId === selectedLibraryCategoryId ? selectedLibraryPresetId : undefined)
    const config = categoryId === selectedLibraryCategoryId ? effectiveLibraryPresetConfig : {}
    event.dataTransfer.setData(NODE_TEMPLATE_MIME, JSON.stringify({ categoryId, presetId: preset.id, presetConfig: config }))
    event.dataTransfer.effectAllowed = 'copy'
    if (categoryId !== selectedLibraryCategoryId) selectLibraryCategory(categoryId)
  }, [effectiveLibraryPresetConfig, selectLibraryCategory, selectedLibraryCategoryId, selectedLibraryPresetId])

  const handleNodeTemplateDragOver = useCallback((event: React.DragEvent) => {
    const types = Array.from(event.dataTransfer.types || [])
    if (!types.includes(NODE_TEMPLATE_MIME) && !types.includes('application/x-cf-steward-tool')) return
    event.preventDefault()
    event.dataTransfer.dropEffect = 'copy'
  }, [])

  const handleNodeTemplateDrop = useCallback(async (event: React.DragEvent) => {
    const raw = event.dataTransfer.getData(NODE_TEMPLATE_MIME)
    if (!raw || !flowInstance || !onCreateNode) return
    event.preventDefault()
    try {
      const template = JSON.parse(raw) as { categoryId: NodeCategoryId; presetId?: string; presetConfig?: Record<string, string> }
      const position = flowInstance.screenToFlowPosition({ x: event.clientX, y: event.clientY })
      const safePosition = findAvailableNodeDropPosition(position, flowInstance.getNodes() as FlowGraphNode[], nodeViewMode)
      const createdNode = await onCreateNode(selectedNode, template.categoryId, 'insert', {
        presetId: template.presetId,
        presetConfig: template.presetConfig || {},
        position: safePosition,
      })
      if (createdNode && (safePosition.x !== position.x || safePosition.y !== position.y)) {
        pendingCreatedNodeFocusRef.current = createdNode.id
      }
      setSelectedLibraryCategoryId(null)
    } catch (error: any) {
      showToast({ title: '节点拖放失败', description: error?.message || '节点模板数据无效', type: 'error' })
    }
  }, [flowInstance, nodeViewMode, onCreateNode, selectedNode])

  const createSelectedLibraryNode = useCallback(async () => {
    if (!onCreateNode || !selectedLibraryCategory || !selectedLibraryPreset || creatingLibraryNode) return
    setCreatingLibraryNode(true)
    try {
      const node = await onCreateNode(selectedNode, selectedLibraryCategory.id, 'insert', {
        presetId: selectedLibraryPreset.id,
        presetConfig: effectiveLibraryPresetConfig,
      })
      if (node) setSelectedLibraryCategoryId(null)
    } finally {
      setCreatingLibraryNode(false)
    }
  }, [creatingLibraryNode, effectiveLibraryPresetConfig, onCreateNode, selectedLibraryCategory, selectedLibraryPreset, selectedNode])

  const handleCanvasDrop = useCallback(async (event: React.DragEvent) => {
    if (event.dataTransfer.getData('application/x-cf-steward-tool') === 'pointer') {
      event.preventDefault()
      setActiveCanvasTool('steward-pointer')
      const target = document.elementFromPoint(event.clientX, event.clientY) as Element | null
      const nodeElement = target?.closest('.react-flow__node') as HTMLElement | null
      const edgeElement = target?.closest('.react-flow__edge') as HTMLElement | null
      if (nodeElement?.dataset.id) {
        const node = nodeById.get(nodeElement.dataset.id)
        if (node) onSelectNode(node)
        onStewardSelectionChange?.({ node_ids: [nodeElement.dataset.id], edge_ids: [], field_paths: [] })
        return
      }
      if (edgeElement?.dataset.id) {
        const edge = ((flowInstance?.getEdges() as FlowGraphEdge[] | undefined) || edges).find((item) => item.id === edgeElement.dataset.id)
        if (edge) onStewardSelectionChange?.({ node_ids: [edge.source, edge.target], edge_ids: [`${edge.source}->${edge.target}`], field_paths: [] })
        return
      }
      showToast({ title: '没有指向工程对象', description: '请把指针放到节点或连线上。', type: 'info' })
      return
    }
    await handleNodeTemplateDrop(event)
  }, [edges, flowInstance, handleNodeTemplateDrop, nodeById, onSelectNode, onStewardSelectionChange])

  useEffect(() => {
    if (!hasNodeEditors || compactStatic) return
    setCanvasPanel(null)
    setSelectedLibraryCategoryId(null)
  }, [compactStatic, hasNodeEditors])

  const deleteEdges = useCallback(async (deletedEdges: FlowGraphEdge[]) => {
    if (compactStatic || readOnlyGraph || !onEdgesSave || deletedEdges.length === 0) return
    const deletedIds = new Set(deletedEdges.map((edge) => edge.id))
    const sourceEdges = (flowInstance?.getEdges() as FlowGraphEdge[] | undefined) || edges
    const nextEdges = sourceEdges.filter((edge) => !deletedIds.has(edge.id))
    setEdges(nextEdges)
    flowInstance?.setEdges(nextEdges)
    await saveEdgesQuietly(nextEdges)
    setContextMenu(null)
  }, [compactStatic, edges, flowInstance, onEdgesSave, readOnlyGraph, saveEdgesQuietly])

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

  const getContextMenuPlacement = useCallback((clientX: number, clientY: number) => {
    const bounds = wrapperRef.current?.getBoundingClientRect()
    const width = bounds?.width || window.innerWidth
    const height = bounds?.height || window.innerHeight
    const localX = clientX - (bounds?.left || 0)
    const localY = clientY - (bounds?.top || 0)
    return {
      x: Math.min(Math.max(localX + 12, 12), Math.max(12, width - 276)),
      y: Math.min(Math.max(localY + 12, 12), Math.max(12, height - 340)),
      side: localX > width - 540 ? 'left' as const : 'right' as const,
      verticalSide: localY > height / 2 ? 'up' as const : 'down' as const,
    }
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
      className={`cf-flow-graph-shell notranslate display-${displayMode} canvas-tool-${activeCanvasTool} ${fullscreen ? 'fullscreen' : ''} ${runActive ? 'run-active' : ''} ${runInProgress ? 'run-in-progress' : ''} ${runPaused ? 'run-paused' : ''} ${runFinished ? 'run-finished' : ''} ${runOutcomeClass}`}
      translate="no"
      onPointerDownCapture={trackRightPointerDown}
      onPointerMoveCapture={trackRightPointerMove}
      onPointerUpCapture={trackRightPointerUp}
    >
      {runFrameVisible && (
        <svg className="cf-canvas-run-frame" aria-hidden="true">
          <rect />
        </svg>
      )}
      {runCompletionVisible && (
        <section className={`cf-canvas-run-completion ${['failed', 'interrupted', 'cancelled'].includes(runCompletion?.status || '') ? 'failed' : ['paused', 'paused_waiting_user'].includes(runCompletion?.status || '') ? 'paused' : ''}`} role="status" aria-live="polite">
          {['failed', 'interrupted', 'cancelled'].includes(runCompletion?.status || '') ? <AlertTriangle aria-hidden="true" /> : ['paused', 'paused_waiting_user'].includes(runCompletion?.status || '') ? <CirclePause aria-hidden="true" /> : <CheckCircle2 aria-hidden="true" />}
          <div>
            <strong>{['failed', 'interrupted', 'cancelled'].includes(runCompletion?.status || '') ? '运行未完成' : ['paused', 'paused_waiting_user'].includes(runCompletion?.status || '') ? '等待用户确认' : '运行完成'}</strong>
            <span title={completionSummary(runCompletion, stableRunEvents)}>{completionSummary(runCompletion, stableRunEvents)}</span>
          </div>
          {runCompletion && ['paused', 'paused_waiting_user'].includes(runCompletion.status) && onOpenPendingInteraction && <button className="cf-canvas-run-completion-log" type="button" onClick={onOpenPendingInteraction} title="重新打开当前交互"><CirclePause aria-hidden="true" /><span>打开交互</span></button>}
          {runCompletion && <button className="cf-canvas-run-completion-log" type="button" onClick={() => onOpenRunLog?.(runCompletion)} title="查看运行详细日志"><FileText aria-hidden="true" /><span>查看日志</span></button>}
          {runCompletion && (runCompletion.artifacts?.length || runCompletion.delivery?.artifacts?.length) && onOpenRunResult && (
            <button className="cf-canvas-run-completion-result" type="button" onClick={() => onOpenRunResult(runCompletion)} title="在系统文件管理器中打开本次产物文件夹"><FolderOpen aria-hidden="true" /><span>打开文件夹</span></button>
          )}
          <button type="button" onClick={onDismissRunCompletion} title="关闭运行结果" aria-label="关闭运行结果">
            <X aria-hidden="true" />
          </button>
        </section>
      )}
      <OutcomeNodeRenderContext.Provider value={outcomeNodeRenderContext}>
      <EngineeringNodeRenderContext.Provider value={engineeringNodeRenderContext}>
      <ReactFlow<FlowGraphNode, FlowGraphEdge>
        key={`${graph.id}:${compactStatic ? 'compact' : 'canvas'}:${displayMode}`}
        defaultNodes={initialNodes}
        defaultEdges={initialEdges}
        nodeTypes={nodeTypes}
        onInit={handleFlowInit}
        defaultViewport={{ x: 0, y: 0, zoom: compactStatic ? 0.72 : 1.05 }}
        minZoom={0.18}
        maxZoom={1.8}
        nodesDraggable={!compactStatic && !readOnlyGraph && !canvasLocked && activeCanvasTool === 'select'}
        nodesConnectable={!compactStatic && !readOnlyGraph && Boolean(onEdgesSave) && !canvasLocked && activeCanvasTool === 'connect'}
        elementsSelectable={!compactStatic && ['select', 'steward-pointer', 'steward-lasso'].includes(activeCanvasTool)}
        panOnDrag={!compactStatic && [1, 2]}
        selectionOnDrag={!compactStatic && ['select', 'steward-lasso'].includes(activeCanvasTool)}
        selectionMode={SelectionMode.Partial}
        zoomOnScroll={!compactStatic}
        panOnScroll={false}
        zoomOnPinch={!compactStatic}
        zoomOnDoubleClick={false}
        zoomActivationKeyCode={null}
        preventScrolling={!compactStatic}
        onDragOver={handleNodeTemplateDragOver}
        onDrop={handleCanvasDrop}
        onMoveStart={() => setContextMenu(null)}
        onSelectionChange={({ nodes: selectedNodes }) => {
          if (activeCanvasTool === 'steward-lasso') {
            const nodeIds = selectedNodes.map((item) => item.id)
            const selectedSet = new Set(nodeIds)
            const edgeIds = graphEdges
              .filter((edge) => selectedSet.has(edge.from) && selectedSet.has(edge.to))
              .map((edge) => `${edge.from}->${edge.to}`)
            onStewardSelectionChange?.({ node_ids: nodeIds, edge_ids: edgeIds, field_paths: [] })
            return
          }
          if (activeCanvasTool !== 'select' || selectedNodes.length !== 1) return
          const node = selectedNodes[0]?.data as unknown as FlowNode
          if (node && selectedNode?.id !== node.id) onSelectNode(node)
        }}
        onNodeClick={(event, graphNode) => {
          if (activeCanvasTool !== 'steward-pointer') return
          event.preventDefault()
          const node = graphNode.data as unknown as FlowNode
          onSelectNode(node)
          onStewardSelectionChange?.({ node_ids: [node.id], edge_ids: [], field_paths: [] })
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
          setContextMenu({
            ...getContextMenuPlacement(event.clientX, event.clientY),
            node,
          })
        }}
        onNodeDragStart={() => {
          setContextMenu(null)
          nodeDragSnapshotRef.current = ((flowInstance?.getNodes() as FlowGraphNode[] | undefined) || nodes).map((node) => ({
            ...node,
            position: { ...node.position },
          }))
          resourcePositionDragSnapshotRef.current = { ...resourcePositionsRef.current }
        }}
        onNodeDragStop={async () => {
          if (compactStatic || readOnlyGraph) return
          const currentNodes = (flowInstance?.getNodes() as FlowGraphNode[] | undefined) || nodes
          setNodes(currentNodes)
          const resourceLayout = currentNodes.reduce<Record<string, { x: number; y: number }>>((positions, currentNode) => {
            const flowNode = currentNode.data as unknown as FlowNode
            if (isEngineeringResourceNode(flowNode)) {
              positions[currentNode.id] = { x: Math.round(currentNode.position.x), y: Math.round(currentNode.position.y) }
            }
            return positions
          }, {})
          if (Object.keys(resourceLayout).length) {
            resourcePositionsRef.current = { ...resourcePositionsRef.current, ...resourceLayout }
          }
          if (!onLayoutSave) {
            nodeDragSnapshotRef.current = null
            resourcePositionDragSnapshotRef.current = null
            return
          }
          try {
            await onLayoutSave(buildLayoutFromNodes(currentNodes))
          } catch (error: any) {
            const previousNodes = nodeDragSnapshotRef.current
            if (previousNodes) {
              setNodes(previousNodes)
              flowInstance?.setNodes(previousNodes)
            }
            resourcePositionsRef.current = resourcePositionDragSnapshotRef.current || {}
            showToast({ title: '布局保存失败', description: error?.message || String(error), type: 'error' })
          } finally {
            nodeDragSnapshotRef.current = null
            resourcePositionDragSnapshotRef.current = null
          }
        }}
        onNodesDelete={async (deletedNodes: FlowGraphNode[]) => {
          if (compactStatic || readOnlyGraph || !onDeleteNode || deletedNodes.length === 0) return
          deletingNodeRef.current = true
          const errors: string[] = []
          try {
            for (const graphNode of deletedNodes) {
              const node = graphNode.data as unknown as FlowNode
              if (!node || isEngineeringResourceNode(node) || node.locked || isStartNode(node, node.id)) continue
              try {
                await onDeleteNode(node)
              } catch (deleteError: any) {
                errors.push(deleteError?.message || String(deleteError))
              }
            }
          } finally {
            deletingNodeRef.current = false
            if (errors.length) showToast({ title: `删除 ${errors.length} 个节点失败`, description: errors.join('; '), type: 'error' })
          }
        }}
        onConnect={async (connection: Connection) => {
          if (compactStatic || readOnlyGraph || !onEdgesSave || !connection.source || !connection.target) return
          const reason = validateConnection(connection.source, connection.target)
          if (reason) {
            showToast({ title: reason, type: 'error' })
            return
          }
          if (edges.some((edge) => edge.source === connection.source && edge.target === connection.target)) return
          const sourceNode = nodeById.get(connection.source)
          const sourceAccent = isStartNode(sourceNode, connection.source)
            ? '#7d8791'
            : sourceNode ? getNodeCategory(sourceNode).color : 'var(--accent)'
          const nextEdges = addEdge({
            ...connection,
            id: `edge-${Date.now()}-${connection.source}-${connection.target}`,
            sourceHandle: connection.sourceHandle || getPortHandleId('source', 'right', 0),
            targetHandle: connection.targetHandle || getPortHandleId('target', 'left', 0),
            animated: false,
            type: 'default',
            data: { scope: 'root' },
            zIndex: 0,
            style: { stroke: sourceAccent, strokeWidth: 2.8 },
            markerEnd: { type: MarkerType.ArrowClosed, color: sourceAccent },
          }, edges)
          setEdges(nextEdges)
          flowInstance?.setEdges(nextEdges)
          await saveEdgesQuietly(nextEdges)
        }}
        onEdgesDelete={deleteEdges}
        onEdgeContextMenu={(event: React.MouseEvent, edge: FlowGraphEdge) => {
          if (compactStatic || readOnlyGraph || activeCanvasTool !== 'connect') return
          event.preventDefault()
          event.stopPropagation()
          if (Date.now() < suppressContextMenuUntilRef.current) return
          setContextMenu({ ...getContextMenuPlacement(event.clientX, event.clientY), node: null, edge })
        }}
        onEdgeClick={(event, edge) => {
          if (activeCanvasTool !== 'steward-pointer') return
          event.preventDefault()
          onStewardSelectionChange?.({ node_ids: [edge.source, edge.target], edge_ids: [`${edge.source}->${edge.target}`], field_paths: [] })
        }}
        deleteKeyCode={activeCanvasTool === 'select' ? ['Delete', 'Backspace'] : null}
        connectionLineType={ConnectionLineType.Bezier}
        connectionLineStyle={{ stroke: 'var(--accent)', strokeWidth: 2.8 }}
        onPaneClick={() => setContextMenu(null)}
        onPaneContextMenu={(event) => {
          if (compactStatic || readOnlyGraph) return
          event.preventDefault()
          if ((event.target as Element | null)?.closest?.('.react-flow__node, .react-flow__edge')) return
          if (Date.now() >= suppressContextMenuUntilRef.current) setContextMenu(null)
        }}
        proOptions={{ hideAttribution: true }}
      >
        <Background id="canvas-grid" variant={BackgroundVariant.Lines} color="#e1e5e9" gap={canvasGridGap} lineWidth={1} />
        {!compactStatic && annotations.map((annotation, index) => {
          const graphNode = annotation.anchor?.type === 'node'
            ? nodes.find((node) => node.id === annotation.anchor?.id)
            : undefined
          const renderedHeight = annotation.collapsed ? 54 : annotation.height
          const side = graphNode ? resolveEditorSide(graphNode, annotation, annotation.width, renderedHeight) : 'right'
          const connector = graphNode ? buildDetailConnector(graphNode, {
            x: annotation.x,
            y: annotation.y,
            width: annotation.width,
            height: renderedHeight,
            side,
            connectorFraction: .5,
          }) : null
          const markerId = `cf-annotation-arrow-${annotation.id.replace(/[^a-zA-Z0-9_-]/g, '-')}`
          const active = annotation.id === activeAnnotationId
          const anchorNode = annotation.anchor ? nodeById.get(annotation.anchor.id) : undefined
          return (
            <ViewportPortal key={annotation.id}>
              <>
                {connector && (
                  <svg className={`cf-node-detail-connectors cf-canvas-annotation-connectors tone-${annotation.tone}`} style={{ zIndex: active ? 984 : 964 + index }} aria-hidden="true">
                    <defs>
                      <marker id={markerId} viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                        <path d="M 0 0 L 10 5 L 0 10 z" />
                      </marker>
                    </defs>
                    <path className="cf-node-detail-connector-path" d={connector.path} markerEnd={`url(#${markerId})`} />
                    <circle className="cf-node-detail-connector-port source" cx={connector.source.x} cy={connector.source.y} r="4.5" />
                    <circle className="cf-node-detail-connector-port target" cx={connector.target.x} cy={connector.target.y} r="4" />
                  </svg>
                )}
                <div style={{ position: 'absolute', left: annotation.x, top: annotation.y, width: annotation.width, height: renderedHeight, zIndex: active ? 990 : 970 + index }}>
                  <CanvasAnnotationCard
                    annotation={annotation}
                    active={active}
                    editable={Boolean(onAnnotationsSave)}
                    anchorLabel={anchorNode?.display_name || anchorNode?.title}
                    onSelect={() => setActiveAnnotationId(annotation.id)}
                    onPatch={(patch) => patchAnnotation(annotation.id, patch)}
                    onCommit={() => { void commitAnnotations() }}
                    onDelete={() => deleteAnnotation(annotation.id)}
                    onToggleCollapsed={() => {
                      patchAnnotation(annotation.id, { collapsed: !annotation.collapsed })
                      window.setTimeout(() => { void commitAnnotations() }, 0)
                    }}
                    onPointerDown={(event) => beginAnnotationMove(event, annotation)}
                    onPointerMove={moveAnnotationPointer}
                    onPointerUp={endAnnotationPointer}
                    onResizePointerDown={(event) => beginAnnotationResize(event, annotation)}
                  />
                </div>
              </>
            </ViewportPortal>
          )
        })}
        {!compactStatic && nodeEditorPlacements.map((editor, index) => {
          const active = editor.nodeId === activeNodeEditorId
          const dragging = draggingEditorId === editor.editorId
          const graphNode = nodes.find((node) => node.id === editor.nodeId)
          const connector = graphNode ? buildDetailConnector(graphNode, editor) : null
          const editorNode = graphNode?.data as unknown as FlowNode | undefined
          const editorRunStatus = nodeRunStates?.get(editor.nodeId)?.status || 'idle'
          const editorRunClass = runActive ? `run-node-${editorRunStatus}` : ''
          const palette = graphNode ? getNodePalette(editorNode) : null
          const satelliteStyle = {
            '--satellite-accent': palette?.color ?? 'var(--accent)',
            '--satellite-tint': palette?.bg ?? 'var(--accent-soft)',
          } as CSSProperties
          const markerId = `cf-detail-arrow-${editor.editorId.replace(/[^a-zA-Z0-9_-]/g, '-')}`
          return (
            <ViewportPortal key={editor.editorId}>
              <>
                {connector && (
                  <svg
                    className={`cf-node-detail-connectors ${editorRunClass}`}
                    data-editor-id={editor.editorId}
                    data-node-id={editor.nodeId}
                    data-connector-count="1"
                    style={{
                      zIndex: active ? 1018 : 998 + index,
                      ...satelliteStyle,
                    } as CSSProperties}
                    aria-hidden="true"
                  >
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
                  className={`cf-node-editor-viewport detail-section-${editor.section} placement-${editor.side} nodrag nopan nowheel ${active ? 'active' : ''} ${dragging ? 'dragging' : ''} ${editorRunClass}`}
                  data-editor-id={editor.editorId}
                  data-node-id={editor.nodeId}
                  data-section={editor.section}
                  style={{ left: editor.x, top: editor.y, width: editor.width, height: editor.height, zIndex: active ? 1020 : 1000 + index, ...satelliteStyle }}
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
              <button type="button" className={activeCanvasTool === 'select' && !canvasPanel ? 'active' : ''} onClick={() => { setActiveCanvasTool('select'); setCanvasPanel(null); onCloseNodeEditor?.() }} title={readOnlyGraph ? '选择节点查看详情' : '选择与移动'}><MousePointer2 /><span>选择</span></button>
              <button type="button" className={activeCanvasTool === 'connect' && !canvasPanel ? 'active' : ''} onClick={activateConnectMode} title={onEdgesSave && !readOnlyGraph ? '连接节点' : '当前流程暂不允许修改连线'} disabled={readOnlyGraph || !onEdgesSave}><GitBranch /><span>连线</span></button>
              <button type="button" className={canvasPanel === 'nodes' ? 'active' : ''} onClick={() => toggleCanvasPanel('nodes')} title={onCreateNode && !readOnlyGraph ? '节点库' : '当前流程暂不允许增删节点'} disabled={readOnlyGraph || !onCreateNode}><Box /><span>节点</span></button>
              <button type="button" className={canvasPanel === 'notes' ? 'active' : ''} onClick={() => { onCloseNodeEditor?.(); toggleCanvasPanel('notes') }} title={readOnlyGraph ? '当前流程暂不允许编辑注释' : '画布注释'} disabled={readOnlyGraph}><MessageSquare /><span>注释</span></button>
              <button type="button" className={canvasPanel === 'models' ? 'active' : ''} onClick={() => { onCloseNodeEditor?.(); toggleCanvasPanel('models') }} title={modelPanel && !readOnlyGraph ? '模型管理' : '当前流程暂不允许修改模型绑定'} disabled={readOnlyGraph || !modelPanel}><BrainCircuit /><span>模型</span></button>
              <button type="button" className={canvasPanel === 'variables' ? 'active' : ''} onClick={() => { onCloseNodeEditor?.(); toggleCanvasPanel('variables') }} title={readOnlyGraph ? '当前流程暂不允许编辑变量' : '流程变量'} disabled={readOnlyGraph}><Braces /><span>变量</span></button>
              <button type="button" className={canvasPanel === 'settings' ? 'active' : ''} onClick={() => { onCloseNodeEditor?.(); toggleCanvasPanel('settings') }} title={readOnlyGraph ? '当前流程暂不允许编辑配置' : '画布配置'} disabled={readOnlyGraph}><Settings /><span>配置</span></button>
              <button type="button" className={canvasPanel === 'tools' ? 'active' : ''} onClick={() => { onCloseNodeEditor?.(); toggleCanvasPanel('tools') }} title={toolPanel && !readOnlyGraph ? (displayMode === 'engineering' ? 'MCP 工具库' : '工具库') : '当前流程暂不允许修改工具绑定'} disabled={readOnlyGraph || !toolPanel}><Wrench /><span>工具</span></button>
              <button type="button" className={canvasPanel === 'package' ? 'active' : ''} onClick={() => { onCloseNodeEditor?.(); toggleCanvasPanel('package') }} title={packagePanel && !readOnlyGraph ? '打包当前卡带' : '当前流程暂不允许生成开发包'} disabled={readOnlyGraph || !packagePanel}><PackageCheck /><span>打包</span></button>
              <button type="button" className={canvasPanel === 'base-info' ? 'active' : ''} onClick={() => { onCloseNodeEditor?.(); toggleCanvasPanel('base-info') }} title="基座信息"><Info /><span>基座</span></button>
            </nav>
            <div className="cf-canvas-zoom-tools">
              <button type="button" onClick={() => flowInstance?.zoomIn({ duration: 180 })} title="放大"><ZoomIn /></button>
              <button type="button" onClick={() => flowInstance?.zoomOut({ duration: 180 })} title="缩小"><ZoomOut /></button>
              <button type="button" onClick={() => fitCanvasContents()} title="适应画布"><Maximize2 /></button>
              <button type="button" onClick={() => setFullscreen((value) => !value)} title={fullscreen ? '退出全屏' : '全屏查看'}><Maximize /></button>
              <button type="button" className={canvasLocked ? 'active' : ''} onClick={() => setCanvasLocked((value) => !value)} title={canvasLocked ? '解锁画布' : '锁定画布'}>{canvasLocked ? <Lock /> : <Unlock />}</button>
            </div>
          </Panel>
        )}
        {!compactStatic && canvasPanel && (
          <Panel position="top-left" className={`cf-canvas-tool-panel ${canvasPanel === 'tools' || canvasPanel === 'models' || canvasPanel === 'package' ? 'resource-panel' : ''}`}>
            <header><strong>{canvasPanel === 'nodes' ? '节点库' : canvasPanel === 'notes' ? '画布注释' : canvasPanel === 'models' ? '模型管理' : canvasPanel === 'variables' ? '流程变量' : canvasPanel === 'tools' ? '工具管理' : canvasPanel === 'package' ? '卡带打包' : canvasPanel === 'base-info' ? '基座信息' : '卡带与画布配置'}</strong><button type="button" onClick={() => { setCanvasPanel(null); setSelectedLibraryCategoryId(null) }}>×</button></header>
            {canvasPanel === 'nodes' && (
              <div className="cf-canvas-node-library">
                <p>点击选择并配置节点；也可以直接拖到画布。</p>
                {authoringNodeCategories.map((category) => (
                  <button
                    type="button"
                    key={category.id}
                    className={selectedLibraryCategoryId === category.id ? 'active' : ''}
                    disabled={!onCreateNode}
                    draggable={Boolean(onCreateNode)}
                    onClick={() => selectLibraryCategory(category.id)}
                    onDragStart={(event) => startNodeTemplateDrag(event, category.id)}
                    onContextMenu={(event) => { event.preventDefault(); selectLibraryCategory(category.id) }}
                    title="点击配置；拖动创建"
                  >
                    <GripVertical className="cf-node-library-grip" aria-hidden="true" />
                    <i style={{ background: category.color }} />
                    <span><b>{category.label}</b><small>{category.description}</small></span>
                    <Settings className="cf-node-library-arrow" aria-hidden="true" />
                  </button>
                ))}
              </div>
            )}
            {canvasPanel === 'notes' && (
              <div className="cf-canvas-notes-panel">
                <button type="button" className="cf-canvas-notes-create" onClick={() => createAnnotation()} disabled={!onAnnotationsSave}><Plus />新建注释</button>
                <div className="cf-canvas-notes-list">
                  {annotations.length ? annotations.map((annotation) => {
                    const anchor = annotation.anchor ? nodeById.get(annotation.anchor.id) : undefined
                    return (
                      <article key={annotation.id} className={annotation.id === activeAnnotationId ? 'active' : ''}>
                        <button type="button" onClick={() => focusAnnotation(annotation)}>
                          <b>{annotation.title || '未命名注释'}</b>
                          <span>{annotation.body || (anchor ? `关联：${anchor.display_name || anchor.title}` : '空注释')}</span>
                        </button>
                        {onAnnotationsSave && <button type="button" className="danger" onClick={() => deleteAnnotation(annotation.id)} title="删除注释"><Trash2 /></button>}
                      </article>
                    )
                  }) : <div className="cf-canvas-notes-empty"><MessageSquare /><b>还没有画布注释</b><span>记录设计原因、约束或待处理事项。</span></div>}
                </div>
              </div>
            )}
            {canvasPanel === 'variables' && <div className="cf-canvas-data-list variables">{canvasVariables.length ? canvasVariables.map((item) => <div key={`${item.kind}-${item.name}`}><b>{item.name}</b><span>{item.kind} · {item.source}</span></div>) : <p>当前流程还没有声明输入或输出变量。</p>}</div>}
            {canvasPanel === 'settings' && (
              <div className="cf-canvas-settings">
                {cartridgePanel}
                <section className="cf-canvas-theme-settings" aria-label="工作台主题">
                  <div className="cf-canvas-theme-heading"><span>工作台主题</span><small>仅调整界面强调色</small></div>
                  <div className="cf-canvas-theme-presets" role="group" aria-label="选择工作台主题色">
                    {WORKSPACE_THEME_PRESETS.map((theme) => (
                      <button
                        key={theme.id}
                        type="button"
                        className={workspaceTheme.id === theme.id ? 'active' : ''}
                        onClick={() => updateWorkspaceTheme({ id: theme.id, color: theme.color })}
                        title={`使用${theme.label}主题`}
                      >
                        <i style={{ background: theme.color }} aria-hidden="true" />
                        <span>{theme.label}</span>
                      </button>
                    ))}
                  </div>
                  <label className="cf-canvas-theme-custom">
                    <span>自定义颜色</span>
                    <input
                      type="color"
                      value={workspaceTheme.color}
                      onChange={(event) => updateWorkspaceTheme({ id: 'custom', color: event.target.value })}
                      aria-label="自定义工作台主题色"
                    />
                    <code>{workspaceTheme.color.toUpperCase()}</code>
                  </label>
                  <button type="button" className="cf-canvas-theme-reset" onClick={() => updateWorkspaceTheme(DEFAULT_WORKSPACE_THEME)}>恢复默认青绿</button>
                </section>
                <div><span>主节点视图</span><b>完整信息卡</b></div>
                {onLayoutSave && <button type="button" onClick={handleAutoAlign}><AlignHorizontalSpaceAround />按节点簇自动整理</button>}
              </div>
            )}
            {canvasPanel === 'models' && <div className="cf-canvas-resource-content">{modelPanel}</div>}
            {canvasPanel === 'tools' && <div className="cf-canvas-tool-content">{toolPanel}</div>}
            {canvasPanel === 'package' && <div className="cf-canvas-resource-content">{packagePanel}</div>}
            {canvasPanel === 'base-info' && <div className="cf-base-info-panel"><p>当前基座目标协议：{protocolInfo.baseContractLabel} + {protocolInfo.targetProtocolLabel}</p><div><b>当前卡带</b><span>{protocolInfo.currentProtocolLabel} · {protocolInfo.currentProtocolStatus}</span></div><div><b>流程结构（Flow Graph）</b><span>结构化输入/输出、显式绑定、类型化控制连线</span></div><div><b>流程分析器（Flow Analyzer）</b><span>源码指纹、规范化拓扑与分析结果</span></div><div><b>模型绑定（LLM Binding）</b><span>Flow 资源目录与节点级模型绑定</span></div><div><b>MCP 工具绑定</b><span>Flow 资源目录、来源追踪与运行前检查</span></div><div><b>运行时（Runtime）</b><span>交互暂停、恢复、产物交付与备用路径可见性</span></div></div>}
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
                      onClick={() => { setSelectedLibraryPresetId(preset.id); setLibraryPresetConfig({}); setLibraryInputFields(defaultLibraryInputFields()) }}
                    >
                      <strong>{preset.label}</strong>
                      <span>{preset.description}</span>
                    </button>
                  ))}
                </div>
              </section>
              <section className="cf-node-template-fields">
                <label>预设参数</label>
                {structuredInputSelected && (
                  <div className="cf-structured-input-editor">
                    {libraryInputFields.map((inputField, index) => (
                      <div className="cf-structured-input-row" key={inputField.key}>
                        <input
                          aria-label={`字段 ${index + 1} 名称`}
                          value={inputField.label}
                          placeholder="字段名称"
                          onChange={(event) => setLibraryInputFields((current) => current.map((item) => item.key === inputField.key ? { ...item, label: event.target.value } : item))}
                        />
                        <div className="cf-structured-input-options">
                          <select aria-label={`${inputField.label || `字段 ${index + 1}`} 类型`} value={inputField.type} onChange={(event) => setLibraryInputFields((current) => current.map((item) => item.key === inputField.key ? { ...item, type: event.target.value as LibraryInputFieldDraft['type'] } : item))}>
                            <option value="text">单行文本</option>
                            <option value="textarea">多行文本</option>
                            <option value="number">数字</option>
                            <option value="date">日期</option>
                            <option value="email">邮箱</option>
                            <option value="url">网址</option>
                            <option value="file">文件</option>
                          </select>
                          <input aria-label={`${inputField.label || `字段 ${index + 1}`} 默认值`} value={inputField.default} placeholder="默认值（可选）" onChange={(event) => setLibraryInputFields((current) => current.map((item) => item.key === inputField.key ? { ...item, default: event.target.value } : item))} />
                          <label className="cf-structured-input-required"><input type="checkbox" checked={inputField.required} onChange={(event) => setLibraryInputFields((current) => current.map((item) => item.key === inputField.key ? { ...item, required: event.target.checked } : item))} />必填</label>
                          <span className="cf-structured-input-actions">
                            <button type="button" title="上移字段" aria-label={`上移${inputField.label || `字段 ${index + 1}`}`} disabled={index === 0} onClick={() => setLibraryInputFields((current) => { const next = [...current]; [next[index - 1], next[index]] = [next[index], next[index - 1]]; return next })}><ChevronUp /></button>
                            <button type="button" title="下移字段" aria-label={`下移${inputField.label || `字段 ${index + 1}`}`} disabled={index === libraryInputFields.length - 1} onClick={() => setLibraryInputFields((current) => { const next = [...current]; [next[index], next[index + 1]] = [next[index + 1], next[index]]; return next })}><ChevronDown /></button>
                            <button type="button" title="删除字段" aria-label={`删除${inputField.label || `字段 ${index + 1}`}`} disabled={libraryInputFields.length === 1} onClick={() => setLibraryInputFields((current) => current.filter((item) => item.key !== inputField.key))}><Trash2 /></button>
                          </span>
                        </div>
                      </div>
                    ))}
                    <button className="cf-structured-input-add" type="button" onClick={() => { const suffix = Date.now().toString(36); setLibraryInputFields((current) => [...current, { key: `field_${suffix}`, id: `input_${suffix}`, label: '', type: 'text', required: false, default: '' }]) }}><Plus />添加字段</button>
                  </div>
                )}
                {selectedLibraryPreset.fields.length ? selectedLibraryPreset.fields.filter((field) => field.key !== 'output_name' && !(structuredInputSelected && field.key === 'fields')).map((field) => (
                  <label key={field.key}>
                    <span>{field.label}</span>
                    {field.key === 'path' && fileReadPresetSelected ? (
                      <>
                        <div className="cf-library-file-picker">
                          <input
                            value={libraryPresetConfig[field.key] || ''}
                            placeholder={field.placeholder}
                            onChange={(event) => setLibraryPresetConfig((current) => ({ ...current, [field.key]: event.target.value }))}
                          />
                          <button type="button" disabled={uploadingLibraryFile} onClick={() => libraryFileInputRef.current?.click()}><FolderOpen />{uploadingLibraryFile ? '导入中' : '选择文件'}</button>
                        </div>
                        <input
                          ref={libraryFileInputRef}
                          type="file"
                          style={{ display: 'none' }}
                          onChange={(event) => {
                            void uploadLibraryFile(event.target.files?.[0] || null)
                            event.target.value = ''
                          }}
                        />
                      </>
                    ) : field.multiline ? (
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
                )) : !structuredInputSelected && <p>这个预设不需要额外参数。</p>}
              </section>
            </div>
            <footer>
              <span>{selectedNode ? `添加到“${selectedNode.display_name || selectedNode.title || selectedNode.id}”之后` : '添加到流程主链'}</span>
              <button type="button" disabled={creatingLibraryNode || (structuredInputSelected && validLibraryInputFields.length === 0)} onClick={() => void createSelectedLibraryNode()}><Plus />{creatingLibraryNode ? '添加中…' : '添加到流程'}</button>
            </footer>
          </Panel>
        )}
        {!compactStatic && <MiniMap pannable zoomable nodeColor={(node) => (node.data as unknown as FlowNode).locked ? '#b7bbb4' : getNodeCategory(node.data as unknown as FlowNode).bg} nodeStrokeColor={(node) => (node.data as unknown as FlowNode).locked ? '#898f87' : getNodeCategory(node.data as unknown as FlowNode).color} nodeBorderRadius={3} maskColor="rgb(var(--cf-accent-rgb) / .12)" />}
        {contextMenu && !compactStatic && !readOnlyGraph && (
            <div
              className={`cf-graph-context-menu submenu-${contextMenu.side || 'right'} submenu-${contextMenu.verticalSide || 'down'} nodrag nopan nowheel`}
              style={{ left: contextMenu.x, top: contextMenu.y } as CSSProperties}
              onPointerDown={(event) => event.stopPropagation()}
              onPointerUp={(event) => event.stopPropagation()}
              onClick={(event) => event.stopPropagation()}
              onWheel={(event) => event.stopPropagation()}
              onContextMenu={(event) => { event.preventDefault(); event.stopPropagation() }}
            >
            <strong>{contextMenu.edge ? `${contextMenu.edge.source} → ${contextMenu.edge.target}` : contextMenu.node ? contextMenu.node.title : '画布操作'}</strong>
            {contextMenu.edge ? (
              <>
                <span className="cf-graph-menu-label">连线操作</span>
                <button className="danger" onClick={() => deleteEdges([contextMenu.edge!])}>删除这条连线</button>
              </>
            ) : (
              <>
                <div className="cf-graph-menu-group cf-graph-menu-group-primary">
                  {contextMenu.node && onAnnotationsSave && <button type="button" onClick={() => createAnnotation(contextMenu.node)}><span>添加关联注释</span><MessageSquarePlus aria-hidden="true" /></button>}
                  <div className="cf-graph-submenu-item">
                    <button disabled={!contextMenu.node || !onCreateNode}>新增节点 <span aria-hidden="true">›</span></button>
                    <div className="cf-graph-submenu">
                      {authoringNodeCategories.map((category) => (
                        <button key={`flow-${category.id}`} onClick={() => contextMenu.node && onCreateNode?.(contextMenu.node, category.id, 'insert')} disabled={!contextMenu.node || !onCreateNode}>
                          {category.label}
                        </button>
                      ))}
                    </div>
                  </div>
                </div>
                {displayMode === 'engineering' && <div className="cf-graph-menu-group">
                  <button onClick={() => {
                    if (contextMenu.node) void copyNodeText(contextMenu.node, 'id')
                    setContextMenu(null)
                  }} disabled={!contextMenu.node}>复制节点 ID</button>
                  <button onClick={() => {
                    if (contextMenu.node) void copyNodeText(contextMenu.node, 'config')
                    setContextMenu(null)
                  }} disabled={!contextMenu.node}>复制节点配置</button>
                </div>}
                <div className="cf-graph-menu-group cf-graph-menu-group-danger">
                  <button className="danger" onClick={() => contextMenu.node && onDeleteNode?.(contextMenu.node)} disabled={!contextMenu.node || contextMenu.node.locked || !onDeleteNode}>删除节点</button>
                </div>
              </>
            )}
            </div>
        )}
        <FlowNodeInternalsSync nodeIds={canvasNodeIds} />
      </ReactFlow>
      </EngineeringNodeRenderContext.Provider>
      </OutcomeNodeRenderContext.Provider>
    </div>
  )
}
