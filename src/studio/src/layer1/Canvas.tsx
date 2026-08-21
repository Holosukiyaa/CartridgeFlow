import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  MarkerType,
  Panel,
  ReactFlow,
  useNodesState,
  type Edge,
  type Node,
  type NodeProps,
  type ReactFlowInstance,
} from '@xyflow/react'
import { Minus, Plus, Puzzle } from 'lucide-react'
import type { CreatorProjection, CreatorRecipeNode, CreatorRecipePreview } from '../api/types.ts'
import { LAYOUT_KEY, RELATION_KIND_FILTERS } from '../config.ts'
import { copy } from '../copy.ts'
import { StatusBadge, cx, useTheme } from '../ui/index.ts'
import {
  assignEdgePorts,
  emptyPortCounts,
  getPortHandleId,
  kindLabel,
  layoutGraph,
  semanticEdges,
  stepContract,
  stepNodeSize,
  type PortCounts,
  type RelationKind,
} from './graph.ts'
import { nodeReviewState } from './model.ts'
import { StepPorts } from './Ports.tsx'
import '@xyflow/react/dist/style.css'

type CanvasData = {
  order: number
  label: string
  description: string
  state: 'review' | 'confirmed' | 'unresolved'
  need: string
  inputs: string[]
  outputs: string[]
  counts: PortCounts
  vertical: boolean
  impact?: 'added' | 'removed' | 'kept'
  params: string[]
  dim?: boolean
  onOpenLayer: () => void
}

type CanvasNode = Node<CanvasData, 'step'>

function StepNode({ data, selected }: NodeProps<CanvasNode>) {
  return <div className={`creator-node is-${data.state}${selected ? ' is-selected' : ''}${data.impact ? ` is-${data.impact}` : ''}${data.dim ? ' is-dim' : ''}`}>
    <StepPorts counts={data.counts} vertical={data.vertical} />
    <header>
      <span className="order">{String(data.order).padStart(2, '0')}</span>
      <span className="node-head-actions">
        {data.impact === 'added' ? <span className="impact-tag is-added">{copy.impactAdded}</span> : null}
        {data.impact === 'removed' ? <span className="impact-tag is-removed">{copy.impactRemoved}</span> : null}
        <StatusBadge state={data.state} />
        <button type="button" className="node-layer" aria-label={copy.openLayer2} title={copy.openLayer2} onClick={(event) => { event.stopPropagation(); data.onOpenLayer() }}>
          <Puzzle size={14} />
        </button>
      </span>
    </header>
    <h3>{data.label}</h3>
    <p>{data.description}</p>
    {data.state === 'unresolved'
      ? <div className="need-chip">需求：{data.need}</div>
      : <div className="approach-chip">做法：{data.need}</div>}
    {data.params.length ? <p className="node-params">使用者参数 {data.params.join('、')}</p> : null}
  </div>
}

const nodeTypes = { step: StepNode }

function edgeColor(kind: RelationKind) {
  const token = kind === 'data' ? '--color-edge-data' : kind === 'uses' ? '--color-edge-uses' : '--color-edge-control'
  return getComputedStyle(document.documentElement).getPropertyValue(token).trim() || '#8b8ba8'
}

function readSavedPositions(projectId: string) {
  if (!projectId) return {} as Record<string, { x: number; y: number }>
  try {
    const saved = JSON.parse(localStorage.getItem(`${LAYOUT_KEY}.${projectId}`) || '{}')
    if (!saved || typeof saved !== 'object' || Array.isArray(saved)) return {}
    return Object.fromEntries(Object.entries(saved).filter(([, value]) => {
      const point = value as { x?: unknown; y?: unknown }
      return Number.isFinite(point?.x) && Number.isFinite(point?.y)
    })) as Record<string, { x: number; y: number }>
  } catch {
    return {}
  }
}

function savePositions(projectId: string, nodes: CanvasNode[]) {
  if (!projectId) return
  const positions = Object.fromEntries(nodes.map((node) => [node.id, node.position]))
  localStorage.setItem(`${LAYOUT_KEY}.${projectId}`, JSON.stringify(positions))
}

function asRecipeNode(item: CreatorRecipePreview['nodes'][number]): CreatorRecipeNode {
  return {
    id: item.id,
    label: item.label,
    description: item.description,
    values: {},
    editable_fields: [],
    resolution: { status: item.resolution, needed_capability: item.description },
  }
}

export function Canvas({
  creator,
  selectedId,
  contextIds,
  preview,
  vertical,
  onSelect,
  onOpenLayer,
  onApplyPreview,
  onRejectPreview,
  reviewFilter,
}: {
  creator: CreatorProjection | null
  selectedId: string
  contextIds: string[]
  preview: CreatorRecipePreview | null
  vertical: boolean
  onSelect: (nodeId: string, additive?: boolean) => void
  onOpenLayer: (nodeId: string) => void
  onApplyPreview?: () => void
  onRejectPreview?: () => void
  reviewFilter?: string
}) {
  const [flow, setFlow] = useState<ReactFlowInstance<CanvasNode, Edge> | null>(null)
  const [zoom, setZoom] = useState(1)
  const [visible, setVisible] = useState<RelationKind[]>(['control', 'data', 'uses'])
  const { theme } = useTheme()
  const layoutScope = creator?.project_id || ''
  const savedRef = useRef(readSavedPositions(layoutScope))

  const elements = useMemo(() => {
    if (!creator) return { nodes: [] as CanvasNode[], edges: [] as Edge[] }
    const added = new Set(preview?.impact.added_node_ids || [])
    const removed = new Set(preview?.impact.removed_node_ids || [])
    const sourceNodes: CreatorRecipeNode[] = preview
      ? [
          ...creator.trusted_recipe.nodes.filter((node) => !added.has(node.id)),
          ...preview.nodes.filter((node) => added.has(node.id)).map(asRecipeNode),
        ]
      : creator.trusted_recipe.nodes
    const recipe = preview
      ? { ...creator, trusted_recipe: { ...creator.trusted_recipe, nodes: sourceNodes, relations: preview.relations } }
      : creator
    const allEdges = semanticEdges(recipe)
    const shown = allEdges.filter((edge) => visible.includes(edge.kind))
    const { counts, ports } = assignEdgePorts(shown, vertical)
    const highlighted = new Set(contextIds.length ? contextIds : selectedId ? [selectedId] : [])
    const nodes: CanvasNode[] = sourceNodes.map((node, index) => {
      const live = creator.trusted_recipe.nodes.find((item) => item.id === node.id)
      const previewNode = preview?.nodes.find((item) => item.id === node.id)
      const drawn = previewNode ? { ...(live || node), label: previewNode.label, description: previewNode.description } : (live || node)
      const state = live ? nodeReviewState(creator, live) : previewNode?.resolution === 'unresolved' ? 'unresolved' : 'review'
      const size = stepNodeSize(drawn, state === 'unresolved')
      const contract = stepContract(recipe, drawn)
      const impact = added.has(node.id) ? 'added' as const : removed.has(node.id) ? 'removed' as const : preview ? 'kept' as const : undefined
      return {
        id: node.id,
        type: 'step',
        width: size.width,
        height: size.height,
        position: { x: 0, y: 0 },
        selected: highlighted.has(node.id),
        data: {
          order: index + 1,
          label: drawn.label,
          description: drawn.description,
          state,
          need: state === 'unresolved' ? contract.need : (live?.studio_layer2?.step_name || contract.capabilityLabel || live?.resolution?.capability?.label || '已有做法'),
          inputs: contract.inputs.map((item) => item.label),
          outputs: contract.outputs.map((item) => item.label),
          counts: counts.get(node.id) || emptyPortCounts(),
          vertical,
          impact,
          params: (live?.studio_layer2?.params || []).map((item) => item.label),
          dim: Boolean(reviewFilter && state !== reviewFilter),
          onOpenLayer: () => onOpenLayer(node.id),
        },
        hidden: Boolean(reviewFilter && state !== reviewFilter),
      }
    })
    const grid = [
      { x: 24, y: 56 }, { x: 214, y: 56 }, { x: 404, y: 56 }, { x: 594, y: 56 },
      { x: 214, y: 254 }, { x: 404, y: 254 }, { x: 594, y: 254 },
    ]
    const placed = (vertical ? layoutGraph(nodes, shown, vertical) : nodes.map((node, index) => ({
      ...node,
      position: grid[index] || { x: 24 + (index % 4) * 190, y: 56 + Math.floor(index / 4) * 198 },
    }))).map((node) => ({
      ...node,
      position: savedRef.current[node.id] || node.position,
    }))
    const edges: Edge[] = shown.map((edge) => {
      const port = ports.get(edge.id)
      const color = edgeColor(edge.kind)
      return {
        id: edge.id,
        source: edge.source,
        target: edge.target,
        sourceHandle: port ? getPortHandleId('source', port.sourceSide, port.sourceIndex) : undefined,
        targetHandle: port ? getPortHandleId('target', port.targetSide, port.targetIndex) : undefined,
        type: 'smoothstep',
        label: undefined,
        className: `creator-edge is-${edge.kind}`,
        animated: false,
        markerEnd: { type: MarkerType.ArrowClosed, color, width: 8, height: 8 },
        style: { stroke: color, strokeWidth: 1.4, ...(edge.kind === 'uses' ? { strokeDasharray: '4 3' } : {}) },
      }
    })
    return { nodes: placed, edges }
  }, [contextIds, creator, onOpenLayer, preview, reviewFilter, selectedId, vertical, visible])

  const [nodes, setNodes, onNodesChange] = useNodesState<CanvasNode>([])
  useEffect(() => { setNodes(elements.nodes) }, [elements.nodes, setNodes])

  const fit = useCallback(() => {
    void flow?.fitView({ padding: 0.16, duration: 180 })
  }, [flow])

  useEffect(() => {
    savedRef.current = readSavedPositions(layoutScope)
  }, [layoutScope])


  const toggleKind = (kind: RelationKind) => {
    setVisible((current) => current.includes(kind)
      ? current.filter((item) => item !== kind)
      : [...current, kind])
  }

  if (!creator) return null
  if (vertical) {
    return <div className="mobile-wrap">
    <div className="mobile-list">
      <div className="legend-row">
        {RELATION_KIND_FILTERS.map((item) => <span key={item.id} className={`is-${item.id}`}><i />{item.label}</span>)}
      </div>
      {creator.trusted_recipe.nodes.map((node, index) => {
        const state = nodeReviewState(creator, node)
        return <div key={node.id}>
          {index ? <div className="mobile-link">↓</div> : null}
          <article className={`mobile-card is-${state}${selectedId === node.id ? ' is-selected' : ''}`} onClick={() => onSelect(node.id)}>
            <header>
              <span className="order">{String(index + 1).padStart(2, '0')}</span>
              <StatusBadge state={state} />
              <span className="topbar-spacer" />
              {index === 0 ? <button type="button" className="node-layer" aria-label={copy.openLayer2} onClick={(event) => { event.stopPropagation(); onOpenLayer(node.id) }}><Puzzle size={14} /></button> : null}
            </header>
            <h3>{node.label}</h3>
            <p>{node.description}</p>
            {state !== 'unresolved' ? <div className="approach-chip">做法：{node.studio_layer2?.step_name || node.resolution?.capability?.label || '已有做法'}</div> : null}
          </article>
        </div>
      })}
    </div>
      <div className="mobile-l2">
        <button type="button" className="btn btn-outline" onClick={() => selectedId ? onOpenLayer(selectedId) : onOpenLayer(creator.trusted_recipe.nodes[0]?.id || '')}>{copy.goWorkshop}</button>
      </div>
    </div>
  }


  return <ReactFlow
    nodes={nodes}
    edges={elements.edges}
    nodeTypes={nodeTypes}
    onInit={setFlow}
    onNodesChange={onNodesChange}
    onNodeClick={(event, node) => onSelect(node.id, event.shiftKey)}
    onPaneClick={() => onSelect('')}
    onNodeDragStop={(_, _moved, next) => {
      savePositions(layoutScope, next)
      savedRef.current = Object.fromEntries(next.map((item) => [item.id, item.position]))
    }}
    onMoveEnd={(_, viewport) => setZoom(viewport.zoom)}
    nodesConnectable={false}
    nodesDraggable
    colorMode={theme}
    defaultViewport={{ x: 0, y: 0, zoom: 1 }}
    minZoom={0.35}
    maxZoom={1.35}
    proOptions={{ hideAttribution: true }}
  >
    {preview && onApplyPreview && onRejectPreview ? <Panel className="preview-bar" position="top-center">
      <span>{copy.previewOnCanvas}</span>
      <button type="button" onClick={onRejectPreview}>{copy.stewardReject}</button>
      <button type="button" className="is-apply" onClick={onApplyPreview}>{copy.stewardApply}</button>
    </Panel> : null}
    <Panel className="relation-filters" position="top-left">
      {RELATION_KIND_FILTERS.map((item) => <button
        key={item.id}
        type="button"
        className={cx('relation-chip', `is-${item.id}`, visible.includes(item.id) && 'is-on')}
        aria-pressed={visible.includes(item.id)}
        onClick={() => toggleKind(item.id)}
      >{kindLabel(item.id)}</button>)}
    </Panel>
    <Panel className="zoom" position="bottom-left">
      <button type="button" aria-label="缩小" onClick={() => void flow?.zoomOut({ duration: 150 })}><Minus size={14} /></button>
      <span>{Math.round(zoom * 100)}%</span>
      <button type="button" aria-label="放大" onClick={() => void flow?.zoomIn({ duration: 150 })}><Plus size={14} /></button>
      <button type="button" aria-label="铺满" onClick={fit}>铺满</button>
    </Panel>
  </ReactFlow>
}
