import { memo } from 'react'
import { AlertTriangle, ArrowRight, Bot, Box, Check, Cloud, FileCode2, LoaderCircle, PanelTop, Wrench } from 'lucide-react'
import { Handle, Position } from '@xyflow/react'
import type { FlowNode } from '../../api.ts'
import { getNodePalette } from './nodeModel.ts'
import type { NodeRunState } from './runState.ts'
import type { PortCounts } from './FlowNodePorts.tsx'
import { buildEngineeringRecipe, engineeringControlHandleId, engineeringHandleId, humanizeEngineeringKey, recipeDisplayName, summarizeEngineeringRecipeItem, type EngineeringNodeRenderModel } from './engineeringNode.ts'

const HIDDEN_CANVAS_RECIPE_FACTS = new Set(['模型角色', '输出结构', '审核键', '输出键', '输入来源', '交付输出'])

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
        {resource.metadata.map((item, index) => <div key={`${item.label}:${index}`}><dt>{item.label}</dt><dd title={item.value}>{item.value}</dd></div>)}
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
  const recipeName = recipeDisplayName(node, node.id)
  const uniqueFields = (fields: EngineeringNodeRenderModel['view']['sections'][number]['fields']) => {
    const seen = new Set<string>()
    return fields.filter((field) => {
      if (seen.has(field.key)) return false
      seen.add(field.key)
      return true
    })
  }
  const inputFields = uniqueFields(view.sections.find((section) => section.id === 'inputs')?.fields || [])
  const outputFields = uniqueFields(view.sections.find((section) => section.id === 'outputs')?.fields || [])
  const recipe = buildEngineeringRecipe(node).filter((item) => !HIDDEN_CANVAS_RECIPE_FACTS.has(item.label))
  const materialLabel = (key: string, direction: 'input' | 'output') => {
    const normalized = key.toLowerCase()
    if (normalized.includes('failure') || normalized.includes('error')) return '失败信息'
    if (normalized === 'result' || normalized.includes('complete')) return '处理结果'
    if (normalized === 'generated_content') return '生成内容'
    if (/^(?:start|process_[a-z0-9]+)_/.test(normalized)) return direction === 'input' ? '上一步产物' : '处理结果'
    return humanizeEngineeringKey(key)
  }
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
          <strong title={recipeName}>{recipeName}</strong>
        </div>
        <span className={`cf-engineering-node-health ${view.configHealth}`} title={view.configHealthLabel}>
          {statusIcon}
        </span>
      </header>
      <div className="cf-engineering-guided">
        <p className="cf-engineering-guided-what" title={view.what}>{view.what}</p>
      </div>
      {recipe.length > 0 && (
        <section className="cf-engineering-recipe" aria-label="处理配方">
          <h5 className="cf-engineering-recipe-title">配方</h5>
          <dl>
            {recipe.map((item, index) => (
              <div key={`${item.label}:${index}`} title={item.value}>
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
      {(inputFields.length > 0 || outputFields.length > 0) && <div className="cf-engineering-material-flow" aria-label="配方物料流向">
        <div className="inputs"><small>入料</small>{inputFields.length ? inputFields.map((field, index) => <span key={`${field.key}:${index}`} title={field.key}>{connectedInputs.has(field.key) && <Handle type="target" position={Position.Left} id={engineeringHandleId('target', field.key)} className={`cf-engineering-field-port in ${dependencyInputs.has(field.key) ? 'dependency' : ''}`} />}{materialLabel(field.key, 'input')}</span>) : <em>无</em>}</div>
        <ArrowRight aria-hidden="true" />
        <div className="outputs"><small>出料</small>{outputFields.length ? outputFields.map((field, index) => <span key={`${field.key}:${index}`} title={field.key}>{materialLabel(field.key, 'output')}{connectedOutputs.has(field.key) && <Handle type="source" position={Position.Right} id={engineeringHandleId('source', field.key)} className={`cf-engineering-field-port out ${dependencyOutputs.has(field.key) ? 'dependency' : ''}`} />}</span>) : <em>无</em>}</div>
      </div>}
    </article>
  )
})
