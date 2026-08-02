import { memo } from 'react'
import { AlertTriangle, Bot, Box, Check, CircleDot, Cloud, Database, FileCode2, LoaderCircle, PanelTop, Play, Route, ShieldCheck, Wrench } from 'lucide-react'
import { Handle, Position } from '@xyflow/react'
import type { FlowNode } from '../../api.ts'
import { getNodePalette } from './nodeModel.ts'
import type { NodeRunState } from './runState.ts'
import type { PortCounts } from './FlowNodePorts.tsx'
import { buildEngineeringRecipe, engineeringControlHandleId, engineeringHandleId, summarizeEngineeringRecipeItem, type EngineeringNodeRenderModel } from './engineeringNode.ts'

function NodeKindIcon({ iconKey }: { iconKey: string }) {
  if (iconKey === 'start') return <Play aria-hidden="true" />
  if (iconKey === 'interaction') return <PanelTop aria-hidden="true" />
  if (iconKey === 'decision') return <Bot aria-hidden="true" />
  if (iconKey === 'input' || iconKey === 'retrieval') return <Database aria-hidden="true" />
  if (iconKey === 'mcp_read' || iconKey === 'mcp_execute') return <Wrench aria-hidden="true" />
  if (iconKey === 'remote') return <Cloud aria-hidden="true" />
  if (iconKey === 'routing') return <Route aria-hidden="true" />
  if (iconKey === 'validation' || iconKey === 'gate' || iconKey === 'human_gate') return <ShieldCheck aria-hidden="true" />
  return <Box aria-hidden="true" />
}

function ResourceKindIcon({ kind }: { kind: NonNullable<EngineeringNodeRenderModel['resource']>['kind'] }) {
  if (kind === 'ui') return <PanelTop aria-hidden="true" />
  if (kind === 'mcp') return <Cloud aria-hidden="true" />
  if (kind === 'model') return <Bot aria-hidden="true" />
  if (kind === 'tool') return <Wrench aria-hidden="true" />
  return <Box aria-hidden="true" />
}

function ResourcePreview({ title }: { title: string }) {
  return (
    <div className="cf-engineering-resource-preview" aria-label={`${title} HTML 预览`}>
      <div className="cf-engineering-resource-preview-bar"><i /><span /><span /></div>
      <div className="cf-engineering-resource-preview-body">
        <b>{title}</b>
        <span />
        <span />
        <em>交互组件</em>
      </div>
    </div>
  )
}

function EngineeringResourceCard({ node, model, selected, onSelect }: {
  node: FlowNode
  model: EngineeringNodeRenderModel
  selected: boolean
  onSelect: (node: FlowNode) => void
}) {
  const resource = model.resource!
  return (
    <article
      className={`cf-engineering-node engineering-resource resource-${resource.kind} ${selected ? 'selected' : ''}`}
      style={{ '--node-accent': '#72609c', '--node-tint': '#f3f0f8' } as React.CSSProperties}
      data-node-id={node.id}
      data-resource-kind={resource.kind}
      onClick={() => onSelect(node)}
    >
      <Handle type="target" position={Position.Left} id={engineeringHandleId('target', 'resource')} className="cf-engineering-resource-port" />
      <header>
        <i className="cf-engineering-resource-icon"><ResourceKindIcon kind={resource.kind} /></i>
        <div>
          <span className="cf-engineering-resource-kind">{resource.kindLabel}</span>
          <strong title={resource.title}>{resource.title}</strong>
          <small title={resource.reference}>{resource.detail}</small>
        </div>
        <span className="cf-engineering-resource-state">{resource.stateLabel}</span>
      </header>
      {resource.kind === 'ui' && <ResourcePreview title={resource.title} />}
      <dl className="cf-engineering-resource-meta">
        {resource.metadata.map((item) => <div key={item.label}><dt>{item.label}</dt><dd title={item.value}>{item.value}</dd></div>)}
      </dl>
      <footer><FileCode2 aria-hidden="true" /><span>分析投影</span></footer>
    </article>
  )
}

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
  const { view, connectedInputs, connectedOutputs, dependencyInputs, dependencyOutputs } = model
  if (model.resource) return <EngineeringResourceCard node={node} model={model} selected={selected} onSelect={onSelect} />
  const palette = getNodePalette(node)
  // Only input/output sections stay on the card (they carry the data-chain
  // ports); bindings/execution/routes/policies live in the detail panel.
  const sections = view.sections.filter((section) => (section.id === 'inputs' || section.id === 'outputs') && section.fields.length)
  const recipe = buildEngineeringRecipe(node)
  const PORT_SIDE_POSITION: Record<'left' | 'right' | 'top' | 'bottom', Position> = {
    left: Position.Left,
    right: Position.Right,
    top: Position.Top,
    bottom: Position.Bottom,
  }
  const statusIcon = runState?.status === 'running'
    ? <LoaderCircle className="spin" aria-hidden="true" />
    : view.configHealth === 'blocked'
      ? <AlertTriangle aria-hidden="true" />
      : <Check aria-hidden="true" />

  return (
    <article
      className={`cf-engineering-node ${node.scope === 'engineering_resource' ? 'engineering-resource' : ''} ${selected ? 'selected' : ''} status-${runState?.status || view.configHealth}`}
      style={{ '--node-accent': palette.color, '--node-tint': palette.bg } as React.CSSProperties}
      data-node-id={node.id}
      onClick={() => onSelect(node)}
    >
      {(Object.keys(counts.incoming) as Array<keyof typeof counts.incoming>).filter((side) => counts.incoming[side] > 0).map((side) => (
        <Handle key={`in-${side}`} type="target" position={PORT_SIDE_POSITION[side]} id={engineeringControlHandleId('target', side)} className={`cf-engineering-control-port in side-${side}`} />
      ))}
      {(Object.keys(counts.outgoing) as Array<keyof typeof counts.outgoing>).filter((side) => counts.outgoing[side] > 0).map((side) => (
        <Handle key={`out-${side}`} type="source" position={PORT_SIDE_POSITION[side]} id={engineeringControlHandleId('source', side)} className={`cf-engineering-control-port out side-${side}`} />
      ))}
      <header>
        <span className="cf-engineering-node-order">{node.scope === 'engineering_resource' ? 'R' : String(order).padStart(2, '0')}</span>
        <div>
          <strong title={node.display_name || node.title}>{node.display_name || node.title}</strong>
          <small className="cf-engineering-node-category"><NodeKindIcon iconKey={view.iconKey} />{view.kindLabel}</small>
        </div>
        <span className={`cf-engineering-node-health ${view.configHealth}`} title={view.configHealthLabel}>
          {statusIcon}
        </span>
      </header>
      <div className="cf-engineering-guided">
        <p className="cf-engineering-guided-what" title={view.what}>{view.what}</p>
        <small className="cf-engineering-guided-tip"><i>提示</i>{view.beginnerTip}</small>
      </div>
      {recipe.length > 0 && (
        <section className="cf-engineering-recipe" aria-label="处理配方">
          <h5 className="cf-engineering-recipe-title">配方</h5>
          <dl>
            {recipe.map((item) => (
              <div key={item.label} title={item.value}>
                <dt>{item.label}</dt>
                <dd className={`${item.mono ? 'mono' : ''}${item.long ? ' long' : ''}`}>{summarizeEngineeringRecipeItem(item)}</dd>
              </div>
            ))}
          </dl>
          {view.remoteSources && view.remoteSources.length > 0 && (
            <div className="cf-engineering-recipe-sources">
              <span>信源</span>
              <div title={view.remoteSources.map((source) => source.name).join('、')}>
                <strong>{view.remoteSources.length} 个地址已配置</strong>
                <small>{view.remoteSources.map((source) => source.name).join('、')}</small>
              </div>
            </div>
          )}
        </section>
      )}
      <div className="cf-engineering-node-sections">
        {sections.map((section) => {
          const visibleFields = section.fields
          return (
          <section key={section.id} data-section={section.id}>
            <h4>{section.label}<span>{section.fields.length}</span></h4>
            {visibleFields.map((field) => {
              const connectedAsInput = connectedInputs.has(field.key)
              const connectedAsOutput = connectedOutputs.has(field.key)
              const dataConnected = connectedAsInput || connectedAsOutput
              return (
                <div className="cf-engineering-field" data-tone={field.tone} key={`${field.key}:${field.value}`} title={`${field.key}: ${field.value}`}>
                  {connectedAsInput && <Handle type="target" position={Position.Left} id={engineeringHandleId('target', field.key)} className={`cf-engineering-field-port in ${dependencyInputs.has(field.key) ? 'dependency' : ''}`} />}
                  {dataConnected ? <CircleDot aria-hidden="true" /> : <i className="cf-engineering-field-marker" aria-hidden="true" />}
                  <code>{field.key}</code>
                  <span>{field.value}</span>
                  {field.meta && <em>{field.meta}</em>}
                  {connectedAsOutput && <Handle type="source" position={Position.Right} id={engineeringHandleId('source', field.key)} className={`cf-engineering-field-port out ${dependencyOutputs.has(field.key) ? 'dependency' : ''}`} />}
                </div>
              )
            })}
          </section>
          )
        })}
      </div>
      <footer title={`${view.source.path}:${view.source.line}`}>
        <span>来源</span><code>{view.source.path}:{view.source.line}</code>
      </footer>
    </article>
  )
})
