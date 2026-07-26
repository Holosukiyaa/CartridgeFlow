import { useMemo } from 'react'
import { Activity, ArrowDownToLine, ArrowUpFromLine, Boxes, Bot, GripHorizontal, PackageCheck, Pin, PinOff, PlugZap, Route, ShieldCheck, SlidersHorizontal, X } from 'lucide-react'
import type { FlowEdge, FlowEvent, FlowNode } from '../../api.ts'
import { buildNodeDetailFacts, resolveNodeSemanticKind } from './flowNodeView.ts'
import { getNodeCategory, getNodePalette, getProcessDisplayLabel } from './nodeModel.ts'
import { NODE_DETAIL_SECTION_BY_ID, type NodeDetailSection } from './nodeDetails.ts'
import type { NodeRunState } from './runState.ts'

function SectionIcon({ section }: { section: Exclude<NodeDetailSection, 'config'> }) {
  if (section === 'inputs') return <ArrowDownToLine aria-hidden="true" />
  if (section === 'outputs') return <ArrowUpFromLine aria-hidden="true" />
  if (section === 'component') return <Boxes aria-hidden="true" />
  if (section === 'model') return <Bot aria-hidden="true" />
  if (section === 'resources') return <PlugZap aria-hidden="true" />
  if (section === 'routing') return <Route aria-hidden="true" />
  if (section === 'safety') return <ShieldCheck aria-hidden="true" />
  if (section === 'runtime') return <Activity aria-hidden="true" />
  if (section === 'artifacts') return <PackageCheck aria-hidden="true" />
  return <SlidersHorizontal aria-hidden="true" />
}

export function NodeDetailCard({ node, section, graphEdges, pinned, runState, runEvents = [], onTogglePin, onClose }: {
  node: FlowNode
  section: Exclude<NodeDetailSection, 'config'>
  graphEdges: FlowEdge[]
  pinned: boolean
  runState?: NodeRunState
  runEvents?: FlowEvent[]
  onTogglePin: () => void
  onClose: () => void
}) {
  const category = getNodeCategory(node)
  const palette = getNodePalette(node)
  const semanticKind = resolveNodeSemanticKind(node)
  const meta = NODE_DETAIL_SECTION_BY_ID.get(section)!
  const details = useMemo(() => buildNodeDetailFacts(node, section, {
    edges: graphEdges,
    runState,
    runEvents,
  }), [graphEdges, node, runEvents, runState, section])
  const displayLabel = getProcessDisplayLabel(node) || category.label

  return (
    <aside
      className={`cf-node-satellite cf-node-satellite-${section}`}
      data-node-id={node.id}
      data-node-kind={semanticKind}
      data-detail-section={section}
      style={{ '--satellite-accent': palette.color, '--satellite-tint': palette.bg } as React.CSSProperties}
    >
      <header className="cf-node-satellite-head">
        <div className="cf-node-satellite-heading">
          <span className="cf-node-satellite-icon"><SectionIcon section={section} /></span>
          <strong>{node.display_name || node.title || node.id}</strong>
          <span className="cf-node-satellite-kind">{details.title || meta.label}</span>
        </div>
        <div className="cf-node-satellite-actions">
          <span className="cf-node-satellite-drag" title="拖动详情组件"><GripHorizontal aria-hidden="true" /></span>
          <button type="button" className={`cf-node-satellite-pin ${pinned ? 'active' : ''}`} aria-label={pinned ? '取消钉住详情组件' : '钉住详情组件'} aria-pressed={pinned} title={pinned ? '已钉住，刷新后恢复' : '未钉住，刷新后不恢复'} onClick={onTogglePin}>{pinned ? <Pin aria-hidden="true" /> : <PinOff aria-hidden="true" />}</button>
          <button type="button" className="cf-node-satellite-close" aria-label="关闭详情组件" title="关闭详情组件" onClick={onClose}><X aria-hidden="true" /></button>
        </div>
        <p><span>{displayLabel}</span><code>{node.id}</code></p>
      </header>
      <section className="cf-node-satellite-body" aria-label={`${details.title}详情`}>
        <article className={`cf-node-detail-card ${section}`} data-detail-section={section}>
          <header><SectionIcon section={section} /><strong>{details.title}</strong></header>
          <p className="cf-node-detail-description">{details.description}</p>
          <dl>
            {details.fields.map((item) => (
              <div key={item.label} data-tone={item.tone || 'default'}>
                <dt>{item.label}</dt>
                <dd className={item.mono ? 'mono' : ''} title={item.value}>{item.value}</dd>
              </div>
            ))}
          </dl>
        </article>
      </section>
    </aside>
  )
}
