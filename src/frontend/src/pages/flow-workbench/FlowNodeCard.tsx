import { memo, type DragEvent, type ReactNode } from 'react'
import { ArrowDownToLine, ArrowLeftRight, ArrowRight, Bot, Braces, CheckCircle2, Cloud, Database, FileCheck2, Flag, GitBranch, PackageCheck, PanelTop, Play, Route, Search, ShieldCheck, Shuffle, UserCheck, Wrench } from 'lucide-react'
import type { FlowNode } from '../../api.ts'
import { getNodePalette, type FlowNodeViewMode } from './nodeModel.ts'
import { buildEngineeringRecipe, summarizeEngineeringRecipeItem } from './engineeringNode.ts'
import { FlowNodePorts, type PortCounts } from './FlowNodePorts.tsx'
import { buildFlowNodeCardView, buildOutcomeNodeCardView, type OutcomeNodeCardView } from './flowNodeView.ts'
import type { NodeRunState } from './runState.ts'

export type TestProbeKind = 'start' | 'end'
export type FlowNodeProbeState = {
  startNodeId: string
  endNodeId: string
  selectedNodeIds: string[]
  onDropProbe: (kind: TestProbeKind, nodeId: string) => void
}

export const TEST_PROBE_MIME = 'application/x-cf-test-probe'

type FlowNodeCardProps = {
  node: FlowNode
  viewMode: FlowNodeViewMode
  order: number
  selected: boolean
  detailOwner: boolean
  compactStatic: boolean
  counts: PortCounts
  incomingNodes: FlowNode[]
  outgoingNodes: FlowNode[]
  presentation?: OutcomeNodeCardView
  runState?: NodeRunState
  probeState?: FlowNodeProbeState
  probeSelected: boolean
  onSelect: (node: FlowNode) => void
}

function ProbeBadges({ hasStart, hasEnd, onDragStart }: { hasStart: boolean; hasEnd: boolean; onDragStart: (kind: TestProbeKind) => (event: DragEvent<HTMLButtonElement>) => void }) {
  if (!hasStart && !hasEnd) return null
  return (
    <div className="cf-node-probe-stack">
      {hasStart && <button type="button" draggable onDragStart={onDragStart('start')} onClick={(event) => event.stopPropagation()} className="cf-node-probe-badge start" title="拖动开始探针">S</button>}
      {hasEnd && <button type="button" draggable onDragStart={onDragStart('end')} onClick={(event) => event.stopPropagation()} className="cf-node-probe-badge end" title="拖动结束探针">E</button>}
    </div>
  )
}

function NodeKindIcon({ iconKey }: { iconKey: string }) {
  if (iconKey === 'start') return <Play aria-hidden="true" />
  if (iconKey === 'terminal') return <Flag aria-hidden="true" />
  if (iconKey === 'checkpoint') return <FileCheck2 aria-hidden="true" />
  if (iconKey === 'input') return <Database aria-hidden="true" />
  if (iconKey === 'interaction') return <PanelTop aria-hidden="true" />
  if (iconKey === 'decision') return <Bot aria-hidden="true" />
  if (iconKey === 'retrieval') return <Search aria-hidden="true" />
  if (iconKey === 'mcp_read') return <ArrowDownToLine aria-hidden="true" />
  if (iconKey === 'mcp_execute') return <Wrench aria-hidden="true" />
  if (iconKey === 'remote') return <Cloud aria-hidden="true" />
  if (iconKey === 'transfer') return <ArrowLeftRight aria-hidden="true" />
  if (iconKey === 'transform') return <Shuffle aria-hidden="true" />
  if (iconKey === 'validation') return <CheckCircle2 aria-hidden="true" />
  if (iconKey === 'routing') return <Route aria-hidden="true" />
  if (iconKey === 'gate') return <ShieldCheck aria-hidden="true" />
  if (iconKey === 'human_gate') return <UserCheck aria-hidden="true" />
  if (iconKey === 'delivery') return <PackageCheck aria-hidden="true" />
  return <Braces aria-hidden="true" />
}

function DetailedNodeContent({ node, order, view, runState }: Pick<FlowNodeCardProps, 'node' | 'order' | 'runState'> & { view: OutcomeNodeCardView }) {
  return (
    <div className="flow-node-outcome-content">
      <header className="flow-node-detailed-head">
        <div className="flow-node-title">
          <strong style={{ background: node.locked ? undefined : view.category.bg, color: node.locked ? undefined : view.category.color }}>{String(order).padStart(2, '0')}</strong>
          <i className="flow-node-category-icon"><NodeKindIcon iconKey={view.iconKey} /></i>
          <span className="flow-node-title-copy">
            <span className="flow-node-title-line">
              <b className="flow-node-title-text" title={`${view.title}（原节点：${node.display_name || node.title}）`}>{view.title}</b>
              <span className="flow-node-category-pill" style={{ background: view.category.bg, color: view.category.color }}><NodeKindIcon iconKey={view.iconKey} />{view.kindLabel}</span>
            </span>
          </span>
        </div>
        <span className={`flow-node-status status-${runState?.status || view.configHealth}`}>{view.runStatusLabel}</span>
        <p className="flow-node-beginner-tip"><b>提示：</b>{view.beginnerTip}</p>
      </header>
      <section className="flow-node-recipe" aria-label="节点处理配方">
        <span className="flow-node-recipe-label">配方</span>
        <span className="flow-node-recipe-item input" title={view.inputs.map((item) => item.label).join('、')}>{view.inputs[0]?.label || '输入物料'}</span>
        <ArrowRight aria-hidden="true" />
        <span className="flow-node-recipe-action" title={view.what}>{view.kindLabel}</span>
        <ArrowRight aria-hidden="true" />
        <span className="flow-node-recipe-item output" title={view.outputs.map((item) => item.label).join('、')}>{view.outputs[0]?.label || '处理结果'}</span>
      </section>
      {(() => {
        const recipe = buildEngineeringRecipe(node)
        if (!recipe.length) return null
        return (
          <section className="flow-node-recipe-detail" aria-label="处理配方明细">
            <dl>
              {recipe.map((item) => (
                <div key={item.label} title={item.value}>
                  <dt>{item.label}</dt>
                  <dd className={item.mono ? 'mono' : ''}>{summarizeEngineeringRecipeItem(item)}</dd>
                </div>
              ))}
            </dl>
          </section>
        )
      })()}
      <section className="flow-node-outcome-band summary">
        <h4><GitBranch />做什么</h4>
        <p title={view.what}>{view.what}</p>
        {view.primaryIssue && <small className={`flow-node-issue ${view.primaryIssue.severity}`} title={view.primaryIssue.message}>{view.primaryIssue.origin === 'runtime_preflight' ? (view.primaryIssue.severity === 'blocker' ? '运行前阻断' : '运行前提醒') : '配置提示'} · {view.primaryIssue.message}</small>}
      </section>
    </div>
  )
}

function CompactNodeContent({ node, order, runState }: Pick<FlowNodeCardProps, 'node' | 'order' | 'runState'>) {
  const view = buildFlowNodeCardView(node, runState)
  return (
    <>
      <div className="flow-node-title">
        <strong style={{ background: node.locked ? undefined : view.category.bg, color: node.locked ? undefined : view.category.color }}>{String(order).padStart(2, '0')}</strong>
        <span className="flow-node-category-pill" style={{ background: view.category.bg, color: view.category.color }}><NodeKindIcon iconKey={view.iconKey} />{view.kindLabel}</span>
        {view.isImportantNode && <span className="flow-node-milestone">{view.milestoneLabel || '重点'}</span>}
        {view.remoteServiceLabel && <span className="flow-node-remote">{view.remoteServiceLabel}</span>}
        {node.display_name || node.title}
        {runState?.status === 'running' && <span className="node-run-pulse" aria-hidden="true" />}
        {runState?.status === 'completed' && <span className="node-run-check">✓</span>}
        {runState?.status === 'paused' && <span className="node-run-pause">?</span>}
        {runState?.status === 'failed' && <span className="node-run-fail">✗</span>}
      </div>
      <div className="flow-node-meta">{view.protocolLabel || view.category.shortLabel} · {node.action || 'none'}</div>
      {view.description && <p className="flow-node-description">{view.description}</p>}
      {view.hasRunData ? (
        <div className="flow-node-run-io">
          {runState?.inputValue && <span title={`输入: ${runState.inputValue}`}>in: <b>{runState.inputValue.length > 16 ? `${runState.inputValue.slice(0, 16)}...` : runState.inputValue}</b></span>}
          {runState?.outputValue && <span title={`输出: ${runState.outputValue}`}>out: <b>{runState.outputValue.length > 16 ? `${runState.outputValue.slice(0, 16)}...` : runState.outputValue}</b></span>}
        </div>
      ) : <div className="flow-node-scope">{node.scope === 'root' ? '根节点 · 锁定' : `${view.protocolLabel || view.category.label} · 可配置`}</div>}
      {view.caps.length > 0 && <div className="flow-node-cap">{view.caps.join(' · ')}</div>}
    </>
  )
}

export const FlowNodeCard = memo(function FlowNodeCard(props: FlowNodeCardProps): ReactNode {
  const { node, viewMode, order, selected, detailOwner, compactStatic, counts, incomingNodes, outgoingNodes, presentation, runState, probeState, probeSelected, onSelect } = props
  const view = presentation || buildOutcomeNodeCardView(node, runState, { incomingNodes, outgoingNodes })
  const palette = getNodePalette(node)
  const boundaryNode = node.id === 'start' || node.id === 'complete' || node.action === 'complete' || node.action === 'end'
  const hasStartProbe = probeState?.startNodeId === node.id
  const hasEndProbe = probeState?.endNodeId === node.id
  const startProbeDrag = (kind: TestProbeKind) => (event: DragEvent<HTMLButtonElement>) => {
    event.stopPropagation()
    event.dataTransfer.setData(TEST_PROBE_MIME, kind)
    event.dataTransfer.effectAllowed = 'move'
  }
  const handleProbeDragOver = (event: DragEvent<HTMLDivElement>) => {
    if (!probeState || !Array.from(event.dataTransfer.types || []).includes(TEST_PROBE_MIME)) return
    event.preventDefault()
    event.dataTransfer.dropEffect = 'move'
  }
  const handleProbeDrop = (event: DragEvent<HTMLDivElement>) => {
    if (!probeState) return
    const kind = event.dataTransfer.getData(TEST_PROBE_MIME) as TestProbeKind
    if (kind !== 'start' && kind !== 'end') return
    event.preventDefault()
    event.stopPropagation()
    probeState.onDropProbe(kind, node.id)
  }
  return (
    <div
      className={`flow-node-card ${viewMode === 'detailed' ? 'detailed-node' : 'compact-node'} ${detailOwner ? 'detail-owner-node' : ''} ${selected ? 'selected' : ''} ${node.locked ? 'locked' : 'unlocked'} ${boundaryNode ? 'boundary-node' : ''} ${view.isImportantNode ? 'important-node' : ''} ${view.remoteServiceLabel ? 'remote-service-node' : ''} ${compactStatic && selected ? 'compact-focus' : ''} ${probeSelected ? 'probe-selected' : ''} ${hasStartProbe ? 'probe-start' : ''} ${hasEndProbe ? 'probe-end' : ''} ${view.runClass}`}
      data-node-id={node.id}
      data-node-kind={view.semanticKind}
      data-config-health={view.configHealth}
      style={{ '--node-accent': palette.color, '--node-tint': palette.bg, ...(!node.locked && !runState ? { borderColor: palette.color, background: palette.bg } : {}) } as React.CSSProperties}
      onClick={() => onSelect(node)}
      onDragOver={handleProbeDragOver}
      onDrop={handleProbeDrop}
    >
      <FlowNodePorts node={node} counts={counts} />
      {probeState && <ProbeBadges hasStart={Boolean(hasStartProbe)} hasEnd={Boolean(hasEndProbe)} onDragStart={startProbeDrag} />}
      {viewMode === 'detailed'
        ? <DetailedNodeContent node={node} order={order} view={view} runState={runState} />
        : <CompactNodeContent node={node} order={order} runState={runState} />}
    </div>
  )
})
