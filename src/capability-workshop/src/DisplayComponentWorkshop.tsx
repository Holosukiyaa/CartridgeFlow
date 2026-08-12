import { useEffect, useMemo, useState } from 'react'
import { Check, CircleAlert, Eye, LayoutTemplate, List, PanelTop, Plus, Rows3, Save, Trash2 } from 'lucide-react'
import { capabilityApi } from './api'
import {
  componentSlug, displaySources, generatedComponentDraft, mockDisplayValue, nextComponentId,
  type DisplayFieldDraft, type DisplayFieldType, type PreviewState,
} from './componentAuthoring'
import { type AnyRecord } from './model'

const array = (value: unknown) => Array.isArray(value) ? value as AnyRecord[] : []
const object = (value: unknown) => value && typeof value === 'object' && !Array.isArray(value) ? value as AnyRecord : {}

const templates = [
  { id: 'summary', label: '摘要', icon: LayoutTemplate },
  { id: 'list', label: '列表', icon: List },
  { id: 'data_panel', label: '数据面板', icon: PanelTop },
]

const blankField = (index = 1): DisplayFieldDraft => ({ id: `field_${index}`, label: `字段 ${index}`, type: 'text', required: false, source: 'store:result' })

function PreviewValue({ field, state }: { field: DisplayFieldDraft; state: PreviewState }) {
  const value = mockDisplayValue(field, state)
  if (field.type === 'list') {
    const items = Array.isArray(value) ? value : []
    return items.length ? <ul>{items.map((item, index) => <li key={`${field.id}:${index}`}>{String(item)}</li>)}</ul> : <div className="component-preview-empty">暂无内容</div>
  }
  if (value === null || value === '') return <div className="component-preview-empty">暂无内容</div>
  if (field.type === 'boolean') return <strong>{value ? '是' : '否'}</strong>
  return <strong>{String(value)}</strong>
}

export function DisplayComponentWorkshop({ flowId, graph, manifestInputs, components, onCreateDisplayNode, onSaved }: {
  flowId: string
  graph: AnyRecord
  manifestInputs: AnyRecord[]
  components: AnyRecord[]
  onCreateDisplayNode: () => Promise<string | undefined>
  onSaved: () => Promise<void>
}) {
  const authoredComponents = components.filter((item) => object(item.authoring).kind === 'passive_display_v1')
  const displayNodes = array(graph.nodes).filter((node) => node.type === 'process' && node.kind === 'interaction' && node.action === 'render_interaction')
  const sources = useMemo(() => displaySources(graph, manifestInputs), [graph, manifestInputs])
  const [componentId, setComponentId] = useState('result.panel')
  const [label, setLabel] = useState('结果面板')
  const [description, setDescription] = useState('把本次运行结果清楚地交付给用户')
  const [templateId, setTemplateId] = useState('summary')
  const [fields, setFields] = useState<DisplayFieldDraft[]>([{ id: 'result', label: '结果', type: 'text', required: true, source: 'store:result' }])
  const [targetNodeId, setTargetNodeId] = useState('')
  const [previewState, setPreviewState] = useState<PreviewState>('normal')
  const [working, setWorking] = useState(false)
  const [error, setError] = useState('')
  const [done, setDone] = useState('')

  useEffect(() => {
    if (!displayNodes.some((node) => String(node.id) === targetNodeId)) setTargetNodeId(String(displayNodes[0]?.id || ''))
  }, [graph, targetNodeId])

  const chooseComponent = (component: AnyRecord) => {
    const draft = generatedComponentDraft(component)
    if (!draft) return
    setComponentId(String(component.id || ''))
    setLabel(String(component.label || component.id || ''))
    setDescription(String(component.description || ''))
    setTemplateId(draft.templateId)
    setFields(draft.fields.length ? draft.fields : [blankField()])
    const boundNode = displayNodes.find((node) => node.component_ref === component.id)
    setTargetNodeId(String(boundNode?.id || displayNodes[0]?.id || ''))
    setError(''); setDone('')
  }

  const createNew = () => {
    const nextId = nextComponentId(components.map((item) => String(item.id)))
    setComponentId(nextId); setLabel('结果面板'); setDescription('把本次运行结果清楚地交付给用户')
    setTemplateId('summary'); setFields([{ id: 'result', label: '结果', type: 'text', required: true, source: 'store:result' }])
    setTargetNodeId(String(displayNodes[0]?.id || '')); setError(''); setDone('')
  }

  const updateField = (index: number, patch: Partial<DisplayFieldDraft>) => setFields((current) => current.map((field, itemIndex) => itemIndex === index ? { ...field, ...patch } : field))
  const addField = () => setFields((current) => [...current, blankField(current.length + 1)])
  const save = async () => {
    const normalizedId = componentSlug(componentId)
    if (!normalizedId || !label.trim() || !targetNodeId || !fields.length) return
    setWorking(true); setError(''); setDone('')
    try {
      await capabilityApi.saveDisplayComponent(flowId, normalizedId, {
        label: label.trim(), description: description.trim(), template_id: templateId,
        target_node_id: targetNodeId,
        fields: fields.map((field) => ({ ...field, id: field.id.trim(), label: field.label.trim(), source: field.source.trim() })),
      })
      setComponentId(normalizedId)
      setDone('组件、字段映射和展示节点已一起保存。')
      await onSaved()
    } catch (reason) { setError(reason instanceof Error ? reason.message : '展示组件保存失败。') } finally { setWorking(false) }
  }

  const createDisplayNode = async () => {
    setWorking(true); setError('')
    try {
      const nodeId = await onCreateDisplayNode()
      if (nodeId) setTargetNodeId(nodeId)
    } catch (reason) { setError(reason instanceof Error ? reason.message : '展示节点创建失败。') } finally { setWorking(false) }
  }

  return <div className="phase-workspace component-workspace">
    <header><div><span>展示组件</span><h2>把运行结果变成可选择、可映射的用户体验</h2></div><small>{authoredComponents.length ? <><Check />{authoredComponents.length} 个自定义组件</> : '尚未创建自定义组件'}</small></header>
    <div className="component-authoring-layout">
      <aside className="component-library-pane">
        <header><strong>组件</strong><button type="button" title="新建组件" onClick={createNew}><Plus />新建</button></header>
        <div>{authoredComponents.map((component) => <button className={component.id === componentId ? 'is-active' : ''} type="button" key={String(component.id)} onClick={() => chooseComponent(component)}><Rows3 /><span><strong>{String(component.label || component.id)}</strong><small>{String(component.id)} · v{String(component.version)}</small></span></button>)}</div>
        {!authoredComponents.length && <p>当前 Flow 还没有自定义展示组件。</p>}
      </aside>

      <section className="component-definition-pane">
        <div className="component-identity-fields">
          <label><span>组件名称</span><input value={label} onChange={(event) => { setLabel(event.currentTarget.value); if (!authoredComponents.some((item) => item.id === componentId)) setComponentId(componentSlug(event.currentTarget.value) || componentId) }} /></label>
          <label><span>组件标识</span><input value={componentId} onChange={(event) => setComponentId(componentSlug(event.currentTarget.value))} /></label>
          <label className="wide"><span>交付说明</span><input value={description} onChange={(event) => setDescription(event.currentTarget.value)} /></label>
        </div>

        <section className="component-template-section"><header><div><strong>布局模板</strong><small>v0.1 正式模板</small></div></header><div className="component-template-options">{templates.map((template) => { const Icon = template.icon; return <button className={templateId === template.id ? 'is-active' : ''} type="button" key={template.id} onClick={() => setTemplateId(template.id)}><Icon /><span>{template.label}</span></button> })}</div></section>

        <section className="component-fields-section"><header><div><strong>展示字段</strong><small>{fields.length}/12</small></div><button type="button" onClick={addField} disabled={fields.length >= 12}><Plus />添加字段</button></header><div className="component-field-list">{fields.map((field, index) => <div className="component-field-row" key={index}>
          <label><span>名称</span><input value={field.label} onChange={(event) => updateField(index, { label: event.currentTarget.value })} /></label>
          <label><span>字段标识</span><input value={field.id} onChange={(event) => updateField(index, { id: event.currentTarget.value.replace(/[^A-Za-z0-9_]/g, '') })} /></label>
          <label><span>内容类型</span><select value={field.type} onChange={(event) => updateField(index, { type: event.currentTarget.value as DisplayFieldType })}><option value="text">文本</option><option value="number">数字</option><option value="boolean">是/否</option><option value="list">列表</option></select></label>
          <label><span>数据来源</span><input list={`component-sources-${index}`} value={field.source} onChange={(event) => updateField(index, { source: event.currentTarget.value })} /><datalist id={`component-sources-${index}`}>{sources.map((source) => <option value={source.value} key={source.value}>{source.label}</option>)}</datalist></label>
          <label className="component-field-required"><input type="checkbox" checked={field.required} onChange={(event) => updateField(index, { required: event.currentTarget.checked })} />必填</label>
          <button className="danger" type="button" title="删除字段" disabled={fields.length === 1} onClick={() => setFields((current) => current.filter((_, itemIndex) => itemIndex !== index))}><Trash2 /></button>
        </div>)}</div></section>
      </section>

      <aside className="component-preview-pane">
        <header><div><Eye /><strong>模拟预览</strong></div><div className="component-preview-states">{(['normal', 'long', 'empty'] as PreviewState[]).map((state) => <button className={previewState === state ? 'is-active' : ''} type="button" key={state} onClick={() => setPreviewState(state)}>{state === 'normal' ? '正常' : state === 'long' ? '长内容' : '空态'}</button>)}</div></header>
        <div className={`component-preview component-preview--${templateId}`}><div className="component-preview-head"><small>CartridgeFlow 运行呈现</small><h3>{label || '未命名组件'}</h3><p>{description || '运行结果'}</p></div><div className="component-preview-fields">{fields.map((field) => <section className={`is-${field.type}`} key={field.id}><span>{field.label || field.id}</span><PreviewValue field={field} state={previewState} /></section>)}</div></div>
        <section className="component-target"><header><strong>绑定到 Flow</strong><small>{displayNodes.length} 个展示节点</small></header>{displayNodes.length ? <label><span>展示节点</span><select value={targetNodeId} onChange={(event) => setTargetNodeId(event.currentTarget.value)}>{displayNodes.map((node) => <option value={String(node.id)} key={String(node.id)}>{String(node.display_name || node.title || node.id)}</option>)}</select></label> : <button type="button" onClick={() => void createDisplayNode()} disabled={working}><Plus />添加“展示结果”节点</button>}</section>
        {error && <p className="error"><CircleAlert />{error}</p>}{done && <p className="success"><Check />{done}</p>}
        <button id="display-component-save" className="component-save" type="button" onClick={() => void save()} disabled={working || !componentSlug(componentId) || !label.trim() || !targetNodeId || fields.some((field) => !field.id.trim() || !field.label.trim() || !/^(store|artifact):[A-Za-z0-9._-]+$/.test(field.source))}><Save />保存并绑定组件</button>
      </aside>
    </div>
  </div>
}
