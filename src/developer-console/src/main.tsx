import { useEffect, useMemo, useState } from 'react'
import { createRoot } from 'react-dom/client'
import {
  ArrowLeft, Boxes, Check, CircleAlert, FilePlus2, Network, PackageCheck,
  Plus, RefreshCw, Save, ShieldCheck, Trash2, Wrench,
} from 'lucide-react'
import {
  Background, BackgroundVariant, Controls, MarkerType, MiniMap, Position, ReactFlow,
  addEdge, applyEdgeChanges, applyNodeChanges,
  type Connection, type Edge, type EdgeChange, type Node, type NodeChange,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { developerApi } from './api'
import { type AnyRecord } from './model'
import './styles.css'

const array = (value: unknown) => Array.isArray(value) ? value as AnyRecord[] : []
const object = (value: unknown) => value && typeof value === 'object' && !Array.isArray(value) ? value as AnyRecord : {}
const pretty = (value: unknown) => JSON.stringify(value, null, 2)
const slug = (value: string) => value.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 70)

function withExecutionEdges(detail: AnyRecord, filesResponse: AnyRecord): AnyRecord {
  const graph = { ...object(detail.graph) }
  try {
    const files = object(filesResponse.files)
    const rootFlow = JSON.parse(String(files.root_flow || '{}')) as AnyRecord
    const plan = object(rootFlow.execution_plan)
    if (Array.isArray(plan.edges)) graph.edges = plan.edges
  } catch { /* The readiness response will surface invalid Root Flow JSON. */ }
  return { ...detail, graph }
}

function graphNodes(graph: AnyRecord): Node[] {
  return array(graph.nodes).map((node, index) => {
    const position = object(node.position)
    const layout = object(node.layout)
    return {
      id: String(node.id),
      position: {
        x: Number(position.x ?? layout.x ?? 70 + (index % 4) * 230),
        y: Number(position.y ?? layout.y ?? 70 + Math.floor(index / 4) * 150),
      },
      data: {
        label: <div className="flow-node-label"><strong>{String(node.title || node.label || node.id)}</strong><small>{String(node.kind || node.type || 'state')} · {String(node.executor || 'lifecycle')}</small></div>,
      },
      className: `flow-node ${node.type === 'terminal' ? 'terminal' : ''} ${node.locked ? 'locked' : ''}`,
      sourcePosition: Position.Right,
      targetPosition: Position.Left,
    }
  })
}

function graphEdges(graph: AnyRecord): Edge[] {
  return array(graph.edges).map((edge, index) => ({
    id: String(edge.id || `edge-${edge.from || edge.source}-${edge.to || edge.target}-${index}`),
    source: String(edge.from || edge.source),
    target: String(edge.to || edge.target),
    label: edge.label ? String(edge.label) : undefined,
    markerEnd: { type: MarkerType.ArrowClosed },
  }))
}

function Graph({ flowId, graph, selected, onSelect, onReload }: {
  flowId: string; graph: AnyRecord; selected: string; onSelect: (id: string) => void; onReload: () => Promise<void>
}) {
  const [nodes, setNodes] = useState<Node[]>(() => graphNodes(graph))
  const [edges, setEdges] = useState<Edge[]>(() => graphEdges(graph))
  useEffect(() => { setNodes(graphNodes(graph)); setEdges(graphEdges(graph)) }, [graph])

  const persistEdges = async (next: Edge[]) => {
    await developerApi.saveEdges(flowId, next.map((edge) => ({ from: edge.source, to: edge.target, scope: 'root', ...(edge.label ? { label: String(edge.label) } : {}) })))
    await onReload()
  }
  const connect = (connection: Connection) => {
    const next = addEdge({ ...connection, markerEnd: { type: MarkerType.ArrowClosed } }, edges)
    setEdges(next)
    void persistEdges(next)
  }
  const changeEdges = (changes: EdgeChange[]) => {
    const next = applyEdgeChanges(changes, edges)
    setEdges(next)
    if (changes.some((change) => change.type === 'remove')) void persistEdges(next)
  }
  const changeNodes = (changes: NodeChange[]) => setNodes((current) => applyNodeChanges(changes, current))
  const saveLayout = async () => {
    const layout = Object.fromEntries(nodes.map((node) => [node.id, { x: Math.round(node.position.x), y: Math.round(node.position.y) }]))
    await developerApi.saveLayout(flowId, layout)
  }

  return <section className="workshop-canvas" aria-label="能力内部链路图">
    <div className="canvas-heading"><div><Network /><span>内部 Flow</span></div><small>{nodes.length} 个节点 · {edges.length} 条链路 · 拖动节点，连接端口</small></div>
    <div className="flowmap">
      <ReactFlow
        nodes={nodes.map((node) => ({ ...node, selected: node.id === selected }))}
        edges={edges}
        onNodesChange={changeNodes}
        onEdgesChange={changeEdges}
        onConnect={connect}
        onNodeClick={(_, node) => onSelect(node.id)}
        onNodeDragStop={() => void saveLayout()}
        fitView
        minZoom={0.35}
        maxZoom={1.8}
        deleteKeyCode={['Backspace', 'Delete']}
      >
        <Background variant={BackgroundVariant.Dots} gap={20} size={1} />
        <MiniMap pannable zoomable />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  </section>
}

function NodeEditor({ flowId, node, onSaved }: { flowId: string; node: AnyRecord; onSaved: () => Promise<void> }) {
  const [title, setTitle] = useState(String(node.title || node.label || node.id || ''))
  const [kind, setKind] = useState(String(node.kind || 'transfer'))
  const [executor, setExecutor] = useState(String(node.executor || 'deterministic'))
  const [effect, setEffect] = useState(String(node.effect || 'writes_store'))
  const [action, setAction] = useState(String(node.action || 'pass_result'))
  const [params, setParams] = useState(pretty(object(node.params)))
  const [working, setWorking] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    setTitle(String(node.title || node.label || node.id || ''))
    setKind(String(node.kind || 'transfer'))
    setExecutor(String(node.executor || 'deterministic'))
    setEffect(String(node.effect || 'writes_store'))
    setAction(String(node.action || 'pass_result'))
    setParams(pretty(object(node.params)))
  }, [node])

  const save = async () => {
    let parsed: AnyRecord
    try { parsed = JSON.parse(params) as AnyRecord } catch { setError('节点参数不是合法 JSON。'); return }
    setWorking(true); setError('')
    try {
      await developerApi.updateNode(flowId, String(node.id), { title, display_name: title, kind, executor, effect, action, params: parsed })
      await onSaved()
    } catch (reason) { setError(reason instanceof Error ? reason.message : '节点保存失败。') } finally { setWorking(false) }
  }
  const remove = async () => {
    if (!confirm(`删除节点“${title}”？`)) return
    setWorking(true); setError('')
    try { await developerApi.deleteNode(flowId, String(node.id)); await onSaved() }
    catch (reason) { setError(reason instanceof Error ? reason.message : '节点删除失败。') }
    finally { setWorking(false) }
  }

  if (node.locked || node.type !== 'process') return <aside className="node-editor"><header><span>生命周期节点</span><strong>{title}</strong></header><p>该节点由 Root Flow 边界维护。</p></aside>
  return <aside className="node-editor">
    <header><span>节点实现</span><strong>{title}</strong></header>
    <label><span>名称</span><input value={title} onChange={(event) => setTitle(event.currentTarget.value)} /></label>
    <div className="field-grid">
      <label><span>类型</span><select value={kind} onChange={(event) => setKind(event.currentTarget.value)}><option value="transfer">数据转换</option><option value="decision">AI 决策</option><option value="mcp_read">工具读取</option><option value="mcp_execute">工具执行</option><option value="interaction">人工确认</option></select></label>
      <label><span>执行器</span><select value={executor} onChange={(event) => setExecutor(event.currentTarget.value)}><option value="deterministic">确定性处理</option><option value="llm">模型</option><option value="mcp">MCP / DLC</option><option value="remote">远程接口</option><option value="interaction">人工交互</option></select></label>
      <label><span>动作</span><select value={action} onChange={(event) => setAction(event.currentTarget.value)}><option value="pass_result">传递结果</option><option value="prompt">模型提示</option><option value="tool_call">调用工具</option><option value="remote_call">远程调用</option><option value="request_input">请求输入</option></select></label>
      <label><span>副作用</span><select value={effect} onChange={(event) => setEffect(event.currentTarget.value)}><option value="pure">无副作用</option><option value="read_only">只读</option><option value="writes_store">写入流程数据</option><option value="external_write">写入外部系统</option></select></label>
    </div>
    <details className="advanced"><summary>高级执行参数</summary><label><span>参数 JSON</span><textarea value={params} onChange={(event) => setParams(event.currentTarget.value)} spellCheck={false} /></label></details>
    {error && <p className="error"><CircleAlert />{error}</p>}
    <div className="editor-actions"><button type="button" onClick={() => void save()} disabled={working}><Save />保存节点</button><button className="danger" type="button" onClick={() => void remove()} disabled={working}><Trash2 />删除</button></div>
  </aside>
}

type FieldDraft = { key: string; id: string; label: string; valueType: string; required: boolean; defaultValue: string; binding: string }
type PortDraft = { key: string; id: string; label: string; required: boolean; schemaType: string; storeKey: string }

const fieldDraft = (): FieldDraft => ({ key: crypto.randomUUID(), id: '', label: '', valueType: 'string', required: true, defaultValue: '', binding: '' })
const portDraft = (): PortDraft => ({ key: crypto.randomUUID(), id: '', label: '', required: true, schemaType: 'object', storeKey: '' })

function FieldEditor({ items, onChange }: { items: FieldDraft[]; onChange: (items: FieldDraft[]) => void }) {
  const update = (key: string, patch: Partial<FieldDraft>) => onChange(items.map((item) => item.key === key ? { ...item, ...patch } : item))
  return <section className="contract-section">
    <header><div><strong>Creator 可调整字段</strong><small>只公开业务参数，不公开执行结构</small></div><button type="button" onClick={() => onChange([...items, fieldDraft()])}><Plus />添加字段</button></header>
    {items.length === 0 ? <p className="contract-empty">这个能力没有需要 Creator 调整的字段。</p> : items.map((item) => <div className="contract-row field-row" key={item.key}>
      <label><span>字段 ID</span><input value={item.id} onChange={(event) => update(item.key, { id: event.currentTarget.value })} placeholder="feed_urls" /></label>
      <label><span>显示名称</span><input value={item.label} onChange={(event) => update(item.key, { label: event.currentTarget.value })} placeholder="RSS 地址" /></label>
      <label><span>类型</span><select value={item.valueType} onChange={(event) => update(item.key, { valueType: event.currentTarget.value })}><option value="string">文本</option><option value="string_list">文本列表</option><option value="number">数字</option><option value="boolean">开关</option></select></label>
      <label><span>默认值</span>{item.valueType === 'boolean' ? <select value={item.defaultValue || 'false'} onChange={(event) => update(item.key, { defaultValue: event.currentTarget.value })}><option value="false">关闭</option><option value="true">开启</option></select> : <input value={item.defaultValue} onChange={(event) => update(item.key, { defaultValue: event.currentTarget.value })} placeholder={item.valueType === 'string_list' ? '每行一个值' : ''} />}</label>
      <label className="binding"><span>内部参数路径</span><input value={item.binding} onChange={(event) => update(item.key, { binding: event.currentTarget.value })} placeholder="states.fetch.params.tools.0.params.urls" /></label>
      <label className="required"><input type="checkbox" checked={item.required} onChange={(event) => update(item.key, { required: event.currentTarget.checked })} />必填</label>
      <button className="icon danger" type="button" title="删除字段" onClick={() => onChange(items.filter((candidate) => candidate.key !== item.key))}><Trash2 /></button>
    </div>)}
  </section>
}

function PortEditor({ title, description, items, onChange }: { title: string; description: string; items: PortDraft[]; onChange: (items: PortDraft[]) => void }) {
  const update = (key: string, patch: Partial<PortDraft>) => onChange(items.map((item) => item.key === key ? { ...item, ...patch } : item))
  return <section className="contract-section">
    <header><div><strong>{title}</strong><small>{description}</small></div><button type="button" onClick={() => onChange([...items, portDraft()])}><Plus />添加端口</button></header>
    {items.length === 0 ? <p className="contract-empty">未声明端口。</p> : items.map((item) => <div className="contract-row port-row" key={item.key}>
      <label><span>端口 ID</span><input value={item.id} onChange={(event) => update(item.key, { id: event.currentTarget.value })} placeholder="items" /></label>
      <label><span>显示名称</span><input value={item.label} onChange={(event) => update(item.key, { label: event.currentTarget.value })} /></label>
      <label><span>数据类型</span><select value={item.schemaType} onChange={(event) => update(item.key, { schemaType: event.currentTarget.value })}><option value="object">对象</option><option value="array">列表</option><option value="string">文本</option><option value="number">数字</option><option value="boolean">布尔值</option></select></label>
      <label><span>Flow 数据键</span><input value={item.storeKey} onChange={(event) => update(item.key, { storeKey: event.currentTarget.value })} placeholder="items" /></label>
      <label className="required"><input type="checkbox" checked={item.required} onChange={(event) => update(item.key, { required: event.currentTarget.checked })} />必需</label>
      <button className="icon danger" type="button" title="删除端口" onClick={() => onChange(items.filter((candidate) => candidate.key !== item.key))}><Trash2 /></button>
    </div>)}
  </section>
}

function PublishPanel({ flowId, flowName, goal, validation, capabilities, onPublished }: {
  flowId: string; flowName: string; goal: string; validation: AnyRecord; capabilities: AnyRecord[]; onPublished: () => Promise<void>
}) {
  const [id, setId] = useState(`workspace.${slug(flowName || flowId) || 'capability'}`)
  const [label, setLabel] = useState(goal || flowName)
  const [description, setDescription] = useState(goal || `由 ${flowName} 提供的可复用能力。`)
  const [terms, setTerms] = useState(goal || flowName)
  const [fields, setFields] = useState<FieldDraft[]>([])
  const [inputs, setInputs] = useState<PortDraft[]>([])
  const [outputs, setOutputs] = useState<PortDraft[]>([])
  const [dependencyIds, setDependencyIds] = useState<string[]>([])
  const [working, setWorking] = useState(false)
  const [error, setError] = useState('')
  const [done, setDone] = useState('')

  const publish = async () => {
    setWorking(true); setError(''); setDone('')
    try {
      const editableFields = fields.map((field) => ({
        id: field.id.trim(), label: field.label.trim(), value_type: field.valueType, required: field.required,
        default: field.valueType === 'string_list'
          ? field.defaultValue.split(/\r?\n/).map((item) => item.trim()).filter(Boolean)
          : field.valueType === 'number'
            ? Number(field.defaultValue)
            : field.valueType === 'boolean'
              ? field.defaultValue === 'true'
              : field.defaultValue,
      }))
      const ports = (items: PortDraft[]) => items.map((port) => ({
        id: port.id.trim(), label: port.label.trim() || port.id.trim(), required: port.required,
        schema: { type: port.schemaType }, store_key: port.storeKey.trim(),
      }))
      const dependencies = dependencyIds.map((dependencyId) => {
        const release = capabilities.find((item) => String(item.id) === dependencyId)!
        return { id: release.id, revision: release.revision, digest: release.digest }
      })
      const result = await developerApi.publishCapability(flowId, {
        capability_id: id.trim(), label: label.trim(), description: description.trim(),
        match_terms: terms.split(/[\n,，]/).map((item) => item.trim()).filter(Boolean),
        editable_fields: editableFields,
        creator_bindings: Object.fromEntries(fields.map((field) => [field.id.trim(), field.binding.trim()])),
        public_inputs: ports(inputs), public_outputs: ports(outputs), dependencies,
        trust_scope: 'workspace',
      })
      const release = object(result.release)
      setDone(`已发布 ${String(release.id)} v${String(release.revision)}，Creator 会重新检查原节点。`)
      await onPublished()
    } catch (reason) { setError(reason instanceof Error ? reason.message : '能力发布失败。') } finally { setWorking(false) }
  }

  return <section className="publish-panel">
    <header><div><ShieldCheck /><span>发布为可信能力</span></div><small>{validation.valid ? '能力边界校验通过' : '发布条件尚未满足'}</small></header>
    <div className="publish-fields">
      <label><span>能力 ID</span><input value={id} onChange={(event) => setId(event.currentTarget.value)} /></label>
      <label><span>显示名称</span><input value={label} onChange={(event) => setLabel(event.currentTarget.value)} /></label>
      <label className="wide"><span>能力说明</span><textarea value={description} onChange={(event) => setDescription(event.currentTarget.value)} /></label>
      <label className="wide"><span>匹配词</span><input value={terms} onChange={(event) => setTerms(event.currentTarget.value)} /></label>
    </div>
    <details open><summary>公开接口与可编辑字段</summary><div className="contract-editor">
      <FieldEditor items={fields} onChange={setFields} />
      <PortEditor title="公开输入" description="从上游能力接收的数据" items={inputs} onChange={setInputs} />
      <PortEditor title="公开输出" description="提供给下游能力的数据" items={outputs} onChange={setOutputs} />
      <section className="contract-section"><header><div><strong>依赖能力</strong><small>固定当前不可变版本；打包时递归校验</small></div></header>
        {capabilities.length === 0 ? <p className="contract-empty">当前没有其他可复用能力。</p> : <div className="dependency-list">{capabilities.filter((item) => String(item.id) !== id.trim()).map((item) => <label key={String(item.id)}><input type="checkbox" checked={dependencyIds.includes(String(item.id))} onChange={(event) => setDependencyIds((current) => event.currentTarget.checked ? [...current, String(item.id)] : current.filter((value) => value !== String(item.id)))} /><span><strong>{String(object(item.creator).label || item.id)}</strong><small>{String(item.id)} · v{String(item.revision)} · {String(item.trust_scope)}</small></span></label>)}</div>}
      </section>
    </div></details>
    {!validation.valid && array(validation.findings).map((finding, index) => <p className="error" key={`${String(finding.code)}:${index}`}><CircleAlert />{String(finding.message || '能力 Flow 尚未形成完整的成功路径。')}</p>)}
    {error && <p className="error"><CircleAlert />{error}</p>}
    {done && <p className="success"><Check />{done}</p>}
    <button type="button" onClick={() => void publish()} disabled={working || !validation.valid || !id.trim() || !label.trim()}><PackageCheck />发布工作区可信版本</button>
  </section>
}

function Workshop() {
  const query = useMemo(() => new URLSearchParams(location.search), [])
  const creatorGoal = query.get('goal') || ''
  const projectId = query.get('projectId') || ''
  const [flows, setFlows] = useState<AnyRecord[]>([])
  const [flowId, setFlowId] = useState(query.get('flowId') || '')
  const [detail, setDetail] = useState<AnyRecord>({})
  const [validation, setValidation] = useState<AnyRecord>({ valid: false })
  const [selected, setSelected] = useState('')
  const [capabilities, setCapabilities] = useState<AnyRecord[]>([])
  const [error, setError] = useState('')
  const [newName, setNewName] = useState(creatorGoal || '新的能力卡带')

  const loadRegistry = async () => {
    const result = await developerApi.capabilityRegistry()
    setCapabilities(result.capabilities)
  }
  const loadFlows = async (preferred = flowId) => {
    const result = await developerApi.flows()
    setFlows(result.items)
    const next = preferred || (creatorGoal ? '' : String(result.items[0]?.id || ''))
    setFlowId(next)
    if (next) await load(next)
  }
  const load = async (id = flowId) => {
    if (!id) return
    setError('')
    try {
      const [nextDetail, nextFiles, nextValidation] = await Promise.all([
        developerApi.flow(id), developerApi.files(id), developerApi.capabilityReadiness(id),
      ])
      const mergedDetail = withExecutionEdges(nextDetail, nextFiles)
      setDetail(mergedDetail); setValidation(nextValidation)
      const nodes = array(object(mergedDetail.graph).nodes)
      setSelected((current) => nodes.some((node) => String(node.id) === current) ? current : String(nodes.find((node) => node.type === 'process')?.id || nodes[0]?.id || ''))
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Flow 读取失败。') }
  }

  useEffect(() => { Promise.all([loadFlows(), loadRegistry()]).catch((reason) => setError(reason instanceof Error ? reason.message : '工坊加载失败。')) }, [])

  const createFlow = async () => {
    const flowSlug = slug(newName) || crypto.randomUUID().slice(0, 8)
    try {
      const result = await developerApi.createFlow({ flow_id: `dev.${flowSlug}`, name: newName, description: creatorGoal })
      await loadFlows(String(result.id))
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Flow 创建失败。') }
  }
  const addNode = async (templateId: string) => {
    if (!flowId) return
    const nodeId = `${templateId}-${Date.now().toString(36)}`
    try {
      await developerApi.createNode(flowId, { template_id: templateId, node_id: nodeId, title: templateId === 'prompt' ? 'AI 处理' : templateId === 'remote_call' ? '外部能力' : '数据处理', after_node_id: selected || undefined })
      await load(flowId); setSelected(nodeId)
    } catch (reason) { setError(reason instanceof Error ? reason.message : '节点创建失败。') }
  }

  const graph = object(detail.graph)
  const nodes = array(graph.nodes)
  const selectedNode = nodes.find((node) => String(node.id) === selected)
  const cartridge = object(detail.cartridge)
  return <main className="workshop">
    <header className="topbar">
      <div><b>CartridgeFlow</b><span>能力卡带工坊</span><small>Developer Flow</small></div>
      <div className="header-actions">
        {projectId && <a href={`/projects/${encodeURIComponent(projectId)}/creator`}><ArrowLeft />返回 Creator</a>}
        <span><Boxes />{capabilities.length} 个已发布能力</span>
        <select aria-label="选择 Flow" value={flowId} onChange={(event) => { setFlowId(event.target.value); void load(event.target.value) }}><option value="">选择 Flow</option>{flows.map((flow) => <option key={String(flow.id)} value={String(flow.id)}>{String(flow.name || flow.id)}</option>)}</select>
        <button type="button" title="刷新" disabled={!flowId} onClick={() => void load()}><RefreshCw /></button>
      </div>
    </header>
    {error && <p className="page-error"><CircleAlert />{error}</p>}
    {!flowId ? <section className="empty-workshop"><Wrench /><h1>新建能力卡带</h1><input value={newName} onChange={(event) => setNewName(event.currentTarget.value)} /><button type="button" onClick={() => void createFlow()} disabled={!newName.trim()}><FilePlus2 />创建内部 Flow</button></section> : <>
      <div className="workshop-toolbar"><strong>{String(cartridge.name || flowId)}</strong><div><button type="button" onClick={() => void addNode('runtime')}><Plus />处理节点</button><button type="button" onClick={() => void addNode('prompt')}><Plus />AI 节点</button><button type="button" onClick={() => void addNode('remote_call')}><Plus />外部能力节点</button></div></div>
      <div className="workshop-body">
        <Graph flowId={flowId} graph={graph} selected={selected} onSelect={setSelected} onReload={() => load(flowId)} />
        {selectedNode && <NodeEditor key={`${flowId}:${selected}`} flowId={flowId} node={selectedNode} onSaved={() => load(flowId)} />}
      </div>
      <PublishPanel flowId={flowId} flowName={String(cartridge.name || flowId)} goal={creatorGoal} validation={validation} capabilities={capabilities} onPublished={loadRegistry} />
    </>}
  </main>
}

createRoot(document.getElementById('root')!).render(<Workshop />)
