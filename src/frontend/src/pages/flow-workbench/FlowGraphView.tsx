import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  ReactFlow,
  Background,
  ConnectionLineType,
  Handle,
  MarkerType,
  MiniMap,
  Panel,
  Position,
  addEdge,
  applyEdgeChanges,
  applyNodeChanges,
  type Connection,
  type Edge,
  type EdgeChange,
  type Node,
  type NodeChange,
  type ReactFlowInstance,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import type { FlowEdge, FlowEvent, FlowGraph, FlowNode } from '../../api.ts'
import { showToast } from '../../toast.tsx'
import type { CreateNodeHandler } from './types.ts'
import { NODE_CATEGORIES, buildAutoAlignLayout, buildBalancedLayout, buildFactoryLayout, buildZigzagLayout, getNodeCategory, getProcessDisplayLabel, getProtocolKind, isStartNode } from './nodeModel.ts'
import type { NodeRunState } from './TestBenchView.tsx'

type FlowGraphNode = Node<Record<string, unknown>>
type FlowGraphEdge = Edge<Record<string, unknown>>
type PortSide = 'left' | 'right' | 'top' | 'bottom'
type SidePortCounts = Record<PortSide, number>
type PortCounts = { incoming: SidePortCounts; outgoing: SidePortCounts }
type EdgePortAssignment = { sourceSide: PortSide; targetSide: PortSide; sourceIndex: number; targetIndex: number }
type RunEdgeStatus = 'visited' | 'active'
type TestProbeKind = 'start' | 'end'
type TestProbeState = {
  startNodeId: string
  endNodeId: string
  selectedNodeIds: string[]
  onDropProbe: (kind: TestProbeKind, nodeId: string) => void
}

const PORT_LIMIT = 5
const EMPTY_FLOW_EVENTS: FlowEvent[] = []
const TEST_PROBE_MIME = 'application/x-cf-test-probe'
const TARGET_PORT_TOPS = [[44], [34, 50], [26, 42, 58], [18, 34, 50, 66], [14, 28, 42, 56, 70]]
const SOURCE_PORT_TOPS = [[56], [50, 66], [42, 58, 74], [34, 50, 66, 82], [30, 44, 58, 72, 86]]
const TARGET_PORT_LEFTS = [[44], [34, 50], [26, 42, 58], [18, 34, 50, 66], [14, 28, 42, 56, 70]]
const SOURCE_PORT_LEFTS = [[56], [50, 66], [42, 58, 74], [34, 50, 66, 82], [30, 44, 58, 72, 86]]
const PORT_SIDES: PortSide[] = ['left', 'right', 'top', 'bottom']
const PORT_SIDE_POSITION: Record<PortSide, Position> = {
  left: Position.Left,
  right: Position.Right,
  top: Position.Top,
  bottom: Position.Bottom,
}

function createSidePortCounts(): SidePortCounts {
  return { left: 0, right: 0, top: 0, bottom: 0 }
}

function createPortCounts(): PortCounts {
  return { incoming: createSidePortCounts(), outgoing: createSidePortCounts() }
}

function getPortHandleId(type: 'target' | 'source', side: PortSide, index: number) {
  return `${type}-${side}-${index}`
}

function getRenderedPortCount(count: number) {
  return Math.max(1, Math.min(PORT_LIMIT, count || 1))
}

function getToolSpecs(node: FlowNode) {
  const specs = Array.isArray(node.tools) ? [...node.tools] : []
  const presetConfig = node.params?.preset_config || {}
  if (presetConfig.server || presetConfig.tool || presetConfig.mcp_tool_id) {
    specs.push({
      type: 'builtin',
      server: presetConfig.server,
      tool: presetConfig.tool,
      mcp_tool_id: presetConfig.mcp_tool_id,
    })
  }
  return specs.filter((item) => item && typeof item === 'object')
}

function getRemoteServiceLabel(node: FlowNode) {
  const category = node.params?.node_category || node.data?.params?.node_category
  const kind = getProtocolKind(node)
  const configuredService = String(node.params?.remote_service || node.params?.preset_config?.remote_service || node.params?.preset_config?.service || '').trim()
  const isRemoteNode = node.action === 'remote_call'
    || kind === 'remote_call'
    || category === 'remote'
    || Boolean(node.params?.remote_required || node.params?.remote_dependency)
  if (!isRemoteNode) return ''
  if (configuredService) return configuredService
  const specs = getToolSpecs(node)
  if (!specs.length) return 'Remote'
  const named = specs.find((item) => item.service || item.resource_id || item.server)
  return String(named?.service || named?.resource_id || named?.server || 'Remote')
}

function getPortStyle(type: 'target' | 'source', side: PortSide, index: number, count: number) {
  const groups = side === 'left' || side === 'right'
    ? type === 'target' ? TARGET_PORT_TOPS : SOURCE_PORT_TOPS
    : type === 'target' ? TARGET_PORT_LEFTS : SOURCE_PORT_LEFTS
  const tops = groups[getRenderedPortCount(count) - 1]
  const value = `${tops[index % tops.length]}%`
  return side === 'left' || side === 'right' ? { top: value } : { left: value }
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

export function FlowGraphView({ graph, selectedNode, focusNodeId, onSelectNode, onLayoutSave, onEdgesSave, onCreateNode, onDeleteNode, compactStatic = false, readOnlyGraph = false, nodeRunStates, runEvents, testProbeState }: {
  graph: FlowGraph
  selectedNode: FlowNode | null
  focusNodeId: string | null
  onSelectNode: (node: FlowNode) => void
  onLayoutSave?: (layout: Record<string, { x: number; y: number }>) => Promise<void>
  onEdgesSave?: (edges: FlowEdge[]) => Promise<void>
  onCreateNode?: CreateNodeHandler
  onDeleteNode?: (node: FlowNode) => Promise<void>
  compactStatic?: boolean
  readOnlyGraph?: boolean
  nodeRunStates?: Map<string, NodeRunState>
  runEvents?: FlowEvent[]
  testProbeState?: TestProbeState
}) {
  const [fullscreen, setFullscreen] = useState(false)
  const [contextMenu, setContextMenu] = useState<{ x: number; y: number; node: FlowNode | null; edge?: FlowGraphEdge | null } | null>(null)
  const [flowInstance, setFlowInstance] = useState<ReactFlowInstance | null>(null)
  const wrapperRef = useRef<HTMLDivElement | null>(null)
  const deletingNodeRef = useRef(false)
  const lastAutoFitSignatureRef = useRef('')
  const nodeOrder = useMemo(() => new Map(graph.nodes.map((node, index) => [node.id, index + 1])), [graph.nodes])
  const nodeById = useMemo(() => new Map(graph.nodes.map((node) => [node.id, node])), [graph.nodes])
  const probeSelectedNodeIds = useMemo(() => new Set(testProbeState?.selectedNodeIds || []), [testProbeState?.selectedNodeIds])
  const graphEdges = useMemo(() => normalizeGraphEdges(graph.edges), [graph.edges])
  const stableRunEvents = runEvents ?? EMPTY_FLOW_EVENTS
  const runEdgeStates = useMemo(() => buildRunEdgeStates(graphEdges, stableRunEvents), [graphEdges, stableRunEvents])
  const renderGraph = useMemo(() => ({ ...graph, edges: graphEdges }), [graph, graphEdges])
  const layout = useMemo(() => buildBalancedLayout(renderGraph), [renderGraph])
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
    const category = getNodeCategory(node)
    const protocolLabel = getProcessDisplayLabel(node)
    const isSelected = selectedNode?.id === node.id
    const runState = nodeRunStates?.get(node.id)
    const hasStartProbe = testProbeState?.startNodeId === node.id
    const hasEndProbe = testProbeState?.endNodeId === node.id
    const isProbeSelected = probeSelectedNodeIds.has(node.id)
    const caps: string[] = []
    const params = node.params || {}
    const isImportantNode = Boolean(params.important_node || node.data?.params?.important_node)
    const remoteServiceLabel = getRemoteServiceLabel(node)
    const milestoneLabel = String(params.milestone_label || node.data?.params?.milestone_label || '').trim()
    const moduleLabel = String(params.module_label || node.data?.params?.module_label || '').trim()
    const counts = edgePortPlan.counts.get(node.id) || createPortCounts()
    const incomingTotal = PORT_SIDES.reduce((total, side) => total + counts.incoming[side], 0)
    const outgoingTotal = PORT_SIDES.reduce((total, side) => total + counts.outgoing[side], 0)
    if (node.agent) caps.push(`AI:${node.agent}`)
    if (node.tools?.length) caps.push(`工具:${node.tools.length}`)
    if (node.tool_summary?.mcp) caps.push(`MCP:${node.tool_summary.mcp}`)
    if (remoteServiceLabel) caps.push(`远端:${remoteServiceLabel}`)
    if (!isImportantNode && moduleLabel) caps.push(moduleLabel)

    const runClass = runState ? `node-run-${runState.status}` : ''
    const hasRunData = runState && runState.status !== 'idle'
    const startProbeDrag = (kind: TestProbeKind) => (event: any) => {
      event.stopPropagation()
      event.dataTransfer.setData(TEST_PROBE_MIME, kind)
      event.dataTransfer.effectAllowed = 'move'
    }
    const handleProbeDragOver = (event: any) => {
      if (!testProbeState || !Array.from(event.dataTransfer.types || []).includes(TEST_PROBE_MIME)) return
      event.preventDefault()
      event.dataTransfer.dropEffect = 'move'
    }
    const handleProbeDrop = (event: any) => {
      if (!testProbeState) return
      const kind = event.dataTransfer.getData(TEST_PROBE_MIME) as TestProbeKind
      if (kind !== 'start' && kind !== 'end') return
      event.preventDefault()
      event.stopPropagation()
      testProbeState.onDropProbe(kind, node.id)
    }

    return (
      <div
        className={`flow-node-card ${isSelected ? 'selected' : ''} ${node.locked ? 'locked' : 'unlocked'} ${isImportantNode ? 'important-node' : ''} ${remoteServiceLabel ? 'remote-service-node' : ''} ${compactStatic && isSelected ? 'compact-focus' : ''} ${isProbeSelected ? 'probe-selected' : ''} ${hasStartProbe ? 'probe-start' : ''} ${hasEndProbe ? 'probe-end' : ''} ${runClass}`}
        style={!node.locked && !runState ? { borderColor: category.color, background: category.bg } : undefined}
        onClick={() => onSelectNode(node)}
        onDragOver={handleProbeDragOver}
        onDrop={handleProbeDrop}
        onContextMenu={(event) => {
          if (compactStatic || readOnlyGraph) return
          event.preventDefault()
          event.stopPropagation()
          setContextMenu({ x: event.clientX, y: event.clientY, node })
        }}
      >
        {!isStartNode(node, node.id) && PORT_SIDES.flatMap((side) => {
          const count = counts.incoming[side] > 0 ? getRenderedPortCount(counts.incoming[side]) : incomingTotal === 0 && side === 'left' ? 1 : 0
          return Array.from({ length: count }).map((_, index) => (
            <Handle
              key={`target-${side}-${index}`}
              id={getPortHandleId('target', side, index)}
              className={`cf-node-port cf-node-port-in cf-node-port-side-${side}`}
              type="target"
              position={PORT_SIDE_POSITION[side]}
              style={getPortStyle('target', side, index, count)}
            />
          ))
        })}
        {testProbeState && (hasStartProbe || hasEndProbe) && (
          <div className="cf-node-probe-stack">
            {hasStartProbe && (
              <button type="button" draggable onDragStart={startProbeDrag('start')} onClick={(event) => event.stopPropagation()} className="cf-node-probe-badge start" title="拖动开始探针">S</button>
            )}
            {hasEndProbe && (
              <button type="button" draggable onDragStart={startProbeDrag('end')} onClick={(event) => event.stopPropagation()} className="cf-node-probe-badge end" title="拖动结束探针">E</button>
            )}
          </div>
        )}
        <div className="flow-node-title">
          <strong style={{ background: node.locked ? undefined : category.bg, color: node.locked ? undefined : category.color }}>
            {String(nodeOrder.get(node.id) || 0).padStart(2, '0')}
          </strong>
          {isImportantNode && <span className="flow-node-milestone">{milestoneLabel || '重点'}</span>}
          {remoteServiceLabel && <span className="flow-node-remote">{remoteServiceLabel}</span>}
          {node.display_name || node.title}
          {runState?.status === 'running' && <span className="node-run-pulse" aria-hidden="true" />}
          {runState?.status === 'completed' && <span className="node-run-check">✓</span>}
          {runState?.status === 'paused' && <span className="node-run-pause">?</span>}
          {runState?.status === 'failed' && <span className="node-run-fail">✗</span>}
        </div>
        <div className="flow-node-meta">{protocolLabel || category.shortLabel} · {node.action || 'none'}</div>
        {hasRunData ? (
          <div className="flow-node-run-io">
            {runState.inputValue && <span title={`??: ${runState.inputValue}`}>in: <b>{runState.inputValue.length > 16 ? `${runState.inputValue.slice(0, 16)}?` : runState.inputValue}</b></span>}
            {runState.outputValue && <span title={`??: ${runState.outputValue}`}>out: <b>{runState.outputValue.length > 16 ? `${runState.outputValue.slice(0, 16)}?` : runState.outputValue}</b></span>}
          </div>
        ) : (
          <div className="flow-node-scope">{node.scope === 'root' ? '根节点 · 锁定' : `${protocolLabel || category.label} · 可配置`}</div>
        )}
        {caps.length > 0 && <div className="flow-node-cap">{caps.join(' · ')}</div>}
        {(node.type !== 'terminal' || isStartNode(node, node.id)) && PORT_SIDES.flatMap((side) => {
          const count = counts.outgoing[side] > 0 ? getRenderedPortCount(counts.outgoing[side]) : outgoingTotal === 0 && side === 'right' ? 1 : 0
          return Array.from({ length: count }).map((_, index) => (
            <Handle
              key={`source-${side}-${index}`}
              id={getPortHandleId('source', side, index)}
              className={`cf-node-port cf-node-port-out cf-node-port-side-${side}`}
              type="source"
              position={PORT_SIDE_POSITION[side]}
              style={getPortStyle('source', side, index, count)}
            />
          ))
        })}
      </div>
    )
  }, [compactStatic, edgePortPlan, nodeOrder, nodeRunStates, onSelectNode, probeSelectedNodeIds, readOnlyGraph, selectedNode, testProbeState])

  const nodeTypes = useMemo(() => ({ custom: CustomNode }), [CustomNode])
  const initialNodes: FlowGraphNode[] = useMemo(() => graph.nodes.map((node) => ({
    id: node.id,
    type: 'custom',
    position: layout[node.id] || { x: node.x, y: node.y },
    data: node as unknown as Record<string, unknown>,
    deletable: !node.locked && !isStartNode(node, node.id),
  })), [graph.nodes, layout])
  const initialEdges: FlowGraphEdge[] = useMemo(() => {
    const branchLaneBySource = new Map<string, number>()
    return graphEdges.map((edge, index) => {
      const branch = edge.scope === 'branch'
      const runEdgeStatus = runEdgeStates.get(`${edge.from}->${edge.to}`)
      const isRunActive = runEdgeStatus === 'active'
      const isRunVisited = runEdgeStatus === 'visited'
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
          stroke: isRunActive ? '#d05b2f' : isRunVisited ? '#2f9e63' : branch ? '#5e8bd8' : '#ba6440',
          strokeWidth: isRunActive ? 5 : isRunVisited ? 3.4 : branch ? 2.4 : 2.8,
          strokeDasharray: isRunActive ? 'none' : branch ? '6 5' : undefined,
          filter: isRunActive ? 'drop-shadow(0 0 4px rgba(208, 91, 47, .72))' : undefined,
        },
        markerEnd: { type: MarkerType.ArrowClosed, color: isRunActive ? '#d05b2f' : isRunVisited ? '#2f9e63' : branch ? '#5e8bd8' : '#ba6440' },
      }
    })
  }, [edgePortPlan, graphEdges, layout, runEdgeStates])

  const [nodes, setNodes] = useState<FlowGraphNode[]>(initialNodes)
  const [edges, setEdges] = useState<FlowGraphEdge[]>(initialEdges)

  useEffect(() => setNodes(initialNodes), [initialNodes])
  useEffect(() => setEdges(initialEdges), [initialEdges])
  useEffect(() => {
    if (!flowInstance || compactStatic || initialNodes.length === 0) return
    const signature = `${graph.id || ''}:${initialNodes.map((node) => node.id).join('|')}:${focusNodeId || ''}`
    if (lastAutoFitSignatureRef.current === signature) return
    lastAutoFitSignatureRef.current = signature
    const frame = window.requestAnimationFrame(() => {
      flowInstance.fitView({ padding: 0.2, duration: 260, maxZoom: 1.05 })
    })
    return () => window.cancelAnimationFrame(frame)
  }, [compactStatic, flowInstance, focusNodeId, graph.id, initialNodes])

  const buildLayoutFromNodes = useCallback((items: FlowGraphNode[]) => {
    const nextLayout: Record<string, { x: number; y: number }> = {}
    items.forEach((node) => { nextLayout[node.id] = { x: Math.round(node.position.x), y: Math.round(node.position.y) } })
    return nextLayout
  }, [])

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
        const zoom = compactStatic ? 0.72 : 0.95
        const width = firstNode.width || 220
        const height = firstNode.height || 104
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
  }, [compactStatic, flowInstance, initialFocusId, initialNodes])

  const handleFlowInit = useCallback((instance: ReactFlowInstance) => {
    setFlowInstance(instance)
    const runFit = () => instance.fitView({ padding: 0.22, duration: 260, maxZoom: compactStatic ? 0.82 : 1.05 })
    window.requestAnimationFrame(() => {
      runFit()
      window.requestAnimationFrame(runFit)
      window.setTimeout(runFit, 260)
    })
  }, [compactStatic])

  const handleAutoAlign = useCallback(async () => {
    if (!onLayoutSave) return
    const currentNodes = (flowInstance?.getNodes() as FlowGraphNode[] | undefined) || nodes
    const alignedLayout = buildAutoAlignLayout(renderGraph)
    const aligned = currentNodes.map((node) => ({ ...node, position: alignedLayout[node.id] || node.position }))
    setNodes(aligned)
    await onLayoutSave(buildLayoutFromNodes(aligned))
    window.requestAnimationFrame(() => focusGraph(240))
  }, [buildLayoutFromNodes, flowInstance, focusGraph, renderGraph, nodes, onLayoutSave])

  const handleZigzagAlign = useCallback(async () => {
    if (!onLayoutSave) return
    const currentNodes = (flowInstance?.getNodes() as FlowGraphNode[] | undefined) || nodes
    const alignedLayout = buildZigzagLayout(renderGraph)
    const aligned = currentNodes.map((node) => ({ ...node, position: alignedLayout[node.id] || node.position }))
    setNodes(aligned)
    await onLayoutSave(buildLayoutFromNodes(aligned))
    window.requestAnimationFrame(() => focusGraph(240))
  }, [buildLayoutFromNodes, flowInstance, focusGraph, renderGraph, nodes, onLayoutSave])

  const handleFactoryAlign = useCallback(async () => {
    if (!onLayoutSave) return
    const currentNodes = (flowInstance?.getNodes() as FlowGraphNode[] | undefined) || nodes
    const alignedLayout = buildFactoryLayout(renderGraph)
    const aligned = currentNodes.map((node) => ({ ...node, position: alignedLayout[node.id] || node.position }))
    setNodes(aligned)
    await onLayoutSave(buildLayoutFromNodes(aligned))
    window.requestAnimationFrame(() => focusGraph(240))
  }, [buildLayoutFromNodes, flowInstance, focusGraph, renderGraph, nodes, onLayoutSave])

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
      const width = node.width || 220
      const height = node.height || 104
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
          <span>右键画布或让创作管家生成 Flow 后，这里会出现可配置节点。</span>
        </div>
      </div>
    )
  }

  return (
    <div ref={wrapperRef} className={`cf-flow-graph-shell ${fullscreen ? 'fullscreen' : ''}`}>
      {!compactStatic && (
        <button type="button" className="cf-flow-recenter-btn" onClick={() => focusGraph(220)}>
          回到节点 · {initialNodes.length}
        </button>
      )}
      <ReactFlow<FlowGraphNode, FlowGraphEdge>
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        onInit={handleFlowInit}
        fitView
        fitViewOptions={{ padding: 0.22, maxZoom: compactStatic ? 0.82 : 1.05 }}
        defaultViewport={{ x: 0, y: 0, zoom: compactStatic ? 0.72 : 1.05 }}
        minZoom={0.18}
        maxZoom={1.8}
        nodesDraggable={!compactStatic && !readOnlyGraph}
        nodesConnectable={!compactStatic && !readOnlyGraph}
        elementsSelectable={!compactStatic}
        panOnDrag={!compactStatic}
        zoomOnScroll={!compactStatic}
        panOnScroll={false}
        zoomOnPinch={!compactStatic}
        zoomOnDoubleClick={!compactStatic}
        zoomActivationKeyCode={null}
        preventScrolling={!compactStatic}
        onNodesChange={(changes: NodeChange[]) => {
          setNodes((current) => applyNodeChanges(changes, current) as FlowGraphNode[])
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
          if (compactStatic || readOnlyGraph) return
          event.preventDefault()
          setContextMenu({ x: event.clientX, y: event.clientY, node: null, edge })
        }}
        deleteKeyCode={['Delete', 'Backspace']}
        connectionLineType={ConnectionLineType.Bezier}
        connectionLineStyle={{ stroke: '#ba6440', strokeWidth: 2.8 }}
        onPaneClick={() => setContextMenu(null)}
        onPaneContextMenu={(event) => {
          if (compactStatic || readOnlyGraph) return
          event.preventDefault()
          setContextMenu({ x: event.clientX, y: event.clientY, node: null, edge: null })
        }}
        proOptions={{ hideAttribution: true }}
      >
        <Background color="#ececec" gap={16} />
        {!compactStatic && (
          <Panel position="bottom-left" className="cf-flow-left-panel">
            <div className="cf-flow-panel-group">
              {onLayoutSave && <button className="cf-flow-panel-btn" onClick={handleAutoAlign} title="自动对齐并保存" aria-label="自动对齐并保存">⇆</button>}
              {onLayoutSave && <button className="cf-flow-panel-btn" onClick={handleZigzagAlign} title="Z 字整理并保存" aria-label="Z 字整理并保存">Z</button>}
              {onLayoutSave && <button className="cf-flow-panel-btn" onClick={handleFactoryAlign} title="工厂整理并保存" aria-label="工厂整理并保存">工</button>}
              <button className="cf-flow-panel-btn" onClick={() => setFullscreen((value) => !value)} title={fullscreen ? '退出全屏' : '全屏查看'}>{fullscreen ? '↙' : '⛶'}</button>
              <button className="cf-flow-panel-btn" onClick={() => flowInstance?.zoomIn({ duration: 180 })} title="放大">+</button>
              <button className="cf-flow-panel-btn" onClick={() => flowInstance?.zoomOut({ duration: 180 })} title="缩小">−</button>
              <button className="cf-flow-panel-btn" onClick={() => flowInstance?.fitView({ padding: 0.18, duration: 240 })} title="适配视图">⌂</button>
            </div>
          </Panel>
        )}
        {!compactStatic && <MiniMap pannable zoomable style={{ width: 120, height: 72 }} nodeColor={(node) => (node.data as unknown as FlowNode).locked ? '#b7bbb4' : getNodeCategory(node.data as unknown as FlowNode).bg} nodeStrokeColor={(node) => (node.data as unknown as FlowNode).locked ? '#898f87' : getNodeCategory(node.data as unknown as FlowNode).color} nodeBorderRadius={3} maskColor="rgba(90, 68, 55, 0.12)" />}
        {contextMenu && !compactStatic && !readOnlyGraph && (
          <div className="cf-graph-context-menu" style={{ left: contextMenu.x, top: contextMenu.y }}>
            <strong>{contextMenu.edge ? `${contextMenu.edge.source} → ${contextMenu.edge.target}` : contextMenu.node ? contextMenu.node.title : '画布操作'}</strong>
            {contextMenu.edge ? (
              <>
                {contextMenu.edge.data?.scope === 'branch' && <button onClick={() => renameBranchEdge(contextMenu.edge!)}>命名分支</button>}
                <button onClick={() => deleteEdges([contextMenu.edge!])}>删除这条链路</button>
              </>
            ) : (
              <>
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
                <button onClick={() => contextMenu.node && onDeleteNode?.(contextMenu.node)} disabled={!contextMenu.node || contextMenu.node.locked || !onDeleteNode}>删除节点</button>
              </>
            )}
          </div>
        )}
      </ReactFlow>
    </div>
  )
}
