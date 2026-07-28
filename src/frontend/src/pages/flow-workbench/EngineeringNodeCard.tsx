import { memo } from 'react'
import { AlertTriangle, Check, CircleDot, LoaderCircle } from 'lucide-react'
import { Handle, Position } from '@xyflow/react'
import type { FlowNode } from '../../api.ts'
import { getNodePalette } from './nodeModel.ts'
import type { NodeRunState } from './runState.ts'
import type { PortCounts } from './FlowNodePorts.tsx'
import { engineeringControlHandleId, engineeringHandleId, type EngineeringNodeRenderModel } from './engineeringNode.ts'

export const EngineeringNodeCard = memo(function EngineeringNodeCard({
  node,
  model,
  order,
  selected,
  counts,
  runState,
  onSelect,
}: {
  node: FlowNode
  model: EngineeringNodeRenderModel
  order: number
  selected: boolean
  counts: PortCounts
  runState?: NodeRunState
  onSelect: (node: FlowNode) => void
}) {
  const { view, connectedFields, connectedInputs, connectedOutputs, dependencyInputs, dependencyOutputs } = model
  const palette = getNodePalette(node)
  const sections = view.sections.filter((section) => section.fields.length)
  const hasIncomingControl = Object.values(counts.incoming).some(Boolean)
  const hasOutgoingControl = Object.values(counts.outgoing).some(Boolean)
  const statusIcon = runState?.status === 'running'
    ? <LoaderCircle className="spin" aria-hidden="true" />
    : view.configHealth === 'blocked'
      ? <AlertTriangle aria-hidden="true" />
      : <Check aria-hidden="true" />

  return (
    <article
      className={`cf-engineering-node ${selected ? 'selected' : ''} status-${runState?.status || view.configHealth}`}
      style={{ '--node-accent': palette.color, '--node-tint': palette.bg } as React.CSSProperties}
      data-node-id={node.id}
      onClick={() => onSelect(node)}
    >
      {hasIncomingControl && <Handle type="target" position={Position.Left} id={engineeringControlHandleId('target')} className="cf-engineering-control-port in" />}
      {hasOutgoingControl && <Handle type="source" position={Position.Right} id={engineeringControlHandleId('source')} className="cf-engineering-control-port out" />}
      <header>
        <span className="cf-engineering-node-order">{String(order).padStart(2, '0')}</span>
        <div>
          <strong title={node.display_name || node.title}>{node.display_name || node.title}</strong>
          <small title={node.id}>{node.id} · {view.semanticKind}</small>
        </div>
        <span className={`cf-engineering-node-health ${view.configHealth}`} title={view.configHealthLabel}>
          {statusIcon}
        </span>
      </header>
      <div className="cf-engineering-node-sections">
        {sections.map((section) => {
          const visibleFields = section.fields.slice().sort((left, right) => Number(connectedFields.has(right.key)) - Number(connectedFields.has(left.key))).slice(0, 3)
          return (
          <section key={section.id} data-section={section.id}>
            <h4>{section.label}<span>{section.fields.length}</span></h4>
            {visibleFields.map((field) => {
              const dataConnected = (section.id === 'inputs' && connectedInputs.has(field.key)) || (section.id === 'outputs' && connectedOutputs.has(field.key))
              return (
                <div className="cf-engineering-field" data-tone={field.tone} key={`${field.key}:${field.value}`} title={`${field.key}: ${field.value}`}>
                  {section.id === 'inputs' && dataConnected && <Handle type="target" position={Position.Left} id={engineeringHandleId('target', field.key)} className={`cf-engineering-field-port in ${dependencyInputs.has(field.key) ? 'dependency' : ''}`} />}
                  {dataConnected ? <CircleDot aria-hidden="true" /> : <i className="cf-engineering-field-marker" aria-hidden="true" />}
                  <code>{field.key}</code>
                  <span>{field.value}</span>
                  {field.meta && <em>{field.meta}</em>}
                  {section.id === 'outputs' && dataConnected && <Handle type="source" position={Position.Right} id={engineeringHandleId('source', field.key)} className={`cf-engineering-field-port out ${dependencyOutputs.has(field.key) ? 'dependency' : ''}`} />}
                </div>
              )
            })}
            {section.fields.length > 3 && <small className="cf-engineering-more">+{section.fields.length - 3} fields</small>}
          </section>
          )
        })}
      </div>
      <footer title={`${view.source.path}:${view.source.line}`}>
        <span>Source</span><code>{view.source.path}:{view.source.line}</code>
      </footer>
    </article>
  )
})
