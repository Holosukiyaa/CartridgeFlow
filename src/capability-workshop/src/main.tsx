import { useEffect, useMemo, useState } from 'react'
import { createRoot } from 'react-dom/client'
import dagre from '@dagrejs/dagre'
import {
  ArrowLeft, Bell, Bot, Box, Boxes, Check, CheckCircle2, ChevronDown, CircleAlert, CircleHelp,
  Database, FilePlus2, GitBranch, PackageCheck, Play, Plug, Plus, Power, RefreshCw,
  Save, Search, ShieldCheck, Trash2, User, Wrench, X,
} from 'lucide-react'
import {
  Background, BackgroundVariant, Controls, MarkerType, MiniMap, Position, ReactFlow,
  addEdge, applyEdgeChanges, applyNodeChanges,
  type Connection, type Edge, type EdgeChange, type Node, type NodeChange,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { capabilityApi } from './api'
import { type AnyRecord } from './model'
import { CartridgeSettingsEditor } from './CartridgeSettingsEditor'
import { DisplayComponentWorkshop } from './DisplayComponentWorkshop'
import { buildNodePresentationFiles, nodeSettingDrafts, type NodeSettingDraft, type PresentationFiles } from './settingsPresentation'
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
  const sourceNodes = array(graph.nodes)
  const storedPositions = new Map(sourceNodes.map((node, index) => {
    const position = object(node.position)
    const layout = object(node.layout)
    return [String(node.id), {
      x: Number(position.x ?? layout.x ?? 70 + (index % 4) * 230),
      y: Number(position.y ?? layout.y ?? 70 + Math.floor(index / 4) * 150),
    }]
  }))
  const sourceEdges = array(graph.edges).map((edge) => ({ source: String(edge.from || edge.source), target: String(edge.to || edge.target) }))
  const backwards = sourceEdges.filter((edge) => (storedPositions.get(edge.source)?.x ?? 0) >= (storedPositions.get(edge.target)?.x ?? 0)).length
  const shouldRepairLayout = sourceEdges.length > 0 && backwards / sourceEdges.length >= 0.25
  const projectedPositions = new Map(storedPositions)
  if (shouldRepairLayout) {
    const layoutGraph = new dagre.graphlib.Graph().setDefaultEdgeLabel(() => ({}))
    layoutGraph.setGraph({ rankdir: 'LR', ranksep: 88, nodesep: 64, marginx: 38, marginy: 38 })
    sourceNodes.forEach((node) => layoutGraph.setNode(String(node.id), { width: 172, height: 76 }))
    sourceEdges.forEach((edge) => layoutGraph.setEdge(edge.source, edge.target))
    dagre.layout(layoutGraph)
    sourceNodes.forEach((node) => {
      const point = layoutGraph.node(String(node.id))
      projectedPositions.set(String(node.id), { x: point.x - 86, y: point.y - 38 })
    })
    const failureIds = new Set(sourceNodes.filter((node) => /fail|error|reject/i.test(String(node.id))).map((node) => String(node.id)))
    for (const failureId of failureIds) {
      const failurePosition = projectedPositions.get(failureId)
      if (!failurePosition) continue
      const successId = sourceNodes.map((node) => String(node.id)).find((id) => {
        const position = projectedPositions.get(id)
        return !failureIds.has(id) && position && Math.abs(position.x - failurePosition.x) < 4 && position.y > failurePosition.y
      })
      if (!successId) continue
      const successPosition = projectedPositions.get(successId)!
      projectedPositions.set(failureId, { ...failurePosition, y: successPosition.y })
      projectedPositions.set(successId, { ...successPosition, y: failurePosition.y })
    }
  }
  return sourceNodes.map((node) => {
    return {
      id: String(node.id),
      position: projectedPositions.get(String(node.id)) || { x: 70, y: 70 },
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
  return array(graph.edges).map((edge, index) => {
    const source = String(edge.from || edge.source)
    const target = String(edge.to || edge.target)
    const failure = /fail|error|reject/i.test(`${target} ${String(edge.label || '')}`)
    return {
      id: String(edge.id || `edge-${source}-${target}-${index}`), source, target,
      label: edge.label ? String(edge.label) : undefined,
      className: failure ? 'failure-edge' : 'success-edge',
      markerEnd: { type: MarkerType.ArrowClosed, color: failure ? '#e14f46' : '#2b8f6a' },
    }
  })
}

function Graph({ flowId, graph, selected, onSelect, onReload }: {
  flowId: string; graph: AnyRecord; selected: string; onSelect: (id: string) => void; onReload: () => Promise<void>
}) {
  const [nodes, setNodes] = useState<Node[]>(() => graphNodes(graph))
  const [edges, setEdges] = useState<Edge[]>(() => graphEdges(graph))
  useEffect(() => { setNodes(graphNodes(graph)); setEdges(graphEdges(graph)) }, [graph])

  const persistEdges = async (next: Edge[]) => {
    await capabilityApi.saveEdges(flowId, next.map((edge) => ({ from: edge.source, to: edge.target, scope: 'root', ...(edge.label ? { label: String(edge.label) } : {}) })))
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
    await capabilityApi.saveLayout(flowId, layout)
  }

  return <section className="workshop-canvas" aria-label="能力内部链路图">
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
        <MiniMap pannable zoomable position="bottom-left" />
        <Controls showInteractive={false} position="top-left" />
      </ReactFlow>
    </div>
  </section>
}

function CapabilityNodeEditor({ flowId, node, tools, manifestInputs, files, onSaved, onClose }: {
  flowId: string; node: AnyRecord; tools: AnyRecord[]; manifestInputs: AnyRecord[]; files: PresentationFiles; onSaved: () => Promise<void>; onClose: () => void
}) {
  const [title, setTitle] = useState(String(node.title || node.label || node.id || ''))
  const [endpoint, setEndpoint] = useState(String(node.endpoint || ''))
  const [params, setParams] = useState(pretty(object(node.params)))
  const [inputs, setInputs] = useState(pretty(object(node.inputs)))
  const [outputs, setOutputs] = useState(pretty(object(node.outputs)))
  const [allowedTools, setAllowedTools] = useState<string[]>(array(node.allowed_tools).map(String))
  const [flowInputs, setFlowInputs] = useState(pretty(manifestInputs))
  const [working, setWorking] = useState(false)
  const [error, setError] = useState('')
  const [editorTab, setEditorTab] = useState<'config' | 'contract' | 'run'>('config')
  const initialSettings = useMemo(() => nodeSettingDrafts(files, String(node.id), object(node.params)), [files, node])
  const [settingDrafts, setSettingDrafts] = useState<NodeSettingDraft[]>(initialSettings.drafts)

  useEffect(() => {
    setTitle(String(node.title || node.label || node.id || ''))
    setEndpoint(String(node.endpoint || ''))
    setParams(pretty(object(node.params)))
    setInputs(pretty(object(node.inputs)))
    setOutputs(pretty(object(node.outputs)))
    setAllowedTools(array(node.allowed_tools).map(String))
    setFlowInputs(pretty(manifestInputs))
    const nextSettings = nodeSettingDrafts(files, String(node.id), object(node.params))
    setSettingDrafts(nextSettings.drafts)
  }, [node, manifestInputs, files])

  const parseObject = (label: string, value: string) => {
    const parsed = JSON.parse(value)
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) throw new Error(`${label}必须是 JSON 对象。`)
    return parsed as AnyRecord
  }
  const save = async () => {
    setWorking(true); setError('')
    try {
      const parsedParams = parseObject('执行参数', params)
      const parsedInputs = parseObject('输入端口', inputs)
      const parsedOutputs = parseObject('输出端口', outputs)
      const parsedFlowInputs = JSON.parse(flowInputs)
      if (!Array.isArray(parsedFlowInputs)) throw new Error('Flow 输入必须是 JSON 数组。')
      const presentationFiles = buildNodePresentationFiles(files, String(node.id), parsedParams, settingDrafts)
      const result = await capabilityApi.updateNode(flowId, String(node.id), {
        title, display_name: title, endpoint: endpoint.trim() || null,
        params: parsedParams, inputs: parsedInputs, outputs: parsedOutputs,
        allowed_tools: allowedTools,
        mcp_binding: allowedTools.length ? { allowed_tools: allowedTools } : null,
        manifest_inputs: parsedFlowInputs,
        files: presentationFiles,
      })
      if (object(result.validation).valid !== true) {
        const finding = array(object(result.validation).findings)[0]
        const validationErrors = Array.isArray(object(result.validation).errors) ? object(result.validation).errors as unknown[] : []
        throw new Error(String(finding?.message || validationErrors[0] || '节点或运行设置没有通过校验。'))
      }
      await onSaved()
    } catch (reason) { setError(reason instanceof Error ? reason.message : '节点保存失败。') } finally { setWorking(false) }
  }
  const remove = async () => {
    if (!confirm(`删除节点“${title}”？`)) return
    setWorking(true); setError('')
    try { await capabilityApi.deleteNode(flowId, String(node.id)); await onSaved() }
    catch (reason) { setError(reason instanceof Error ? reason.message : '节点删除失败。') }
    finally { setWorking(false) }
  }

  if (node.locked || node.type !== 'process') return <aside className="node-editor boundary-editor"><header><span>节点配置</span><strong>{title}</strong></header><div className="boundary-copy"><ShieldCheck /><p>开始和完成节点由能力 Flow 的边界维护，不允许修改执行契约。</p></div></aside>
  return <aside className="node-editor capability-node-editor">
    <header><span>节点配置</span><strong>{title}</strong><button className="mobile-node-close" type="button" title="返回能力画布" onClick={onClose}><X /></button></header>
    <nav className="node-editor-tabs" aria-label="节点编辑区"><button className={editorTab === 'config' ? 'is-active' : ''} type="button" onClick={() => setEditorTab('config')}>配置</button><button className={editorTab === 'contract' ? 'is-active' : ''} type="button" onClick={() => setEditorTab('contract')}>契约</button><button className={editorTab === 'run' ? 'is-active' : ''} type="button" onClick={() => setEditorTab('run')}>运行</button></nav>
    <div className="node-editor-content">
      {editorTab === 'config' && <>
        <label><span>节点名称</span><input value={title} onChange={(event) => setTitle(event.currentTarget.value)} /></label>
        <div className="execution-contract"><span><small>类型</small><strong>{String(node.kind || 'process')}</strong></span><span><small>执行器</small><strong>{String(node.executor || 'runtime')}</strong></span><span><small>动作</small><strong>{String(node.action || 'none')}</strong></span></div>
        {(node.action === 'remote_call' || endpoint) && <label><span>远程服务地址</span><input value={endpoint} onChange={(event) => setEndpoint(event.currentTarget.value)} placeholder="https://api.example.com/v1/action" /></label>}
        <fieldset className="tool-binding"><legend>允许调用的工具</legend>{tools.length === 0 ? <p>先在“工具与资源”中声明可调用接口。</p> : tools.map((tool) => <label key={String(tool.id)}><input type="checkbox" checked={allowedTools.includes(String(tool.id))} onChange={(event) => setAllowedTools((current) => event.currentTarget.checked ? [...current, String(tool.id)] : current.filter((id) => id !== String(tool.id)))} /><span>{String(tool.name || tool.id)}</span></label>)}</fieldset>
      </>}
      {editorTab === 'contract' && <div className="contract-json-fields"><label><span>能力运行输入 JSON</span><textarea value={flowInputs} onChange={(event) => setFlowInputs(event.currentTarget.value)} spellCheck={false} /></label><label><span>输入端口 JSON</span><textarea value={inputs} onChange={(event) => setInputs(event.currentTarget.value)} spellCheck={false} /></label><label><span>输出端口 JSON</span><textarea value={outputs} onChange={(event) => setOutputs(event.currentTarget.value)} spellCheck={false} /></label></div>}
      {editorTab === 'run' && <div className="run-config"><label><span>执行参数 JSON</span><textarea value={params} onChange={(event) => {
        const value = event.currentTarget.value
        setParams(value)
        try {
          const parsed = parseObject('执行参数', value)
          const currentByParam = new Map(settingDrafts.map((item) => [item.param, item]))
          const next = nodeSettingDrafts(files, String(node.id), parsed).drafts.map((item) => currentByParam.get(item.param) || item)
          setSettingDrafts(next)
        } catch { /* Save reports malformed JSON; keep the last valid setting selection. */ }
      }} spellCheck={false} /></label><p>选择要交给卡带使用者调整的参数；控件随 CF-CRE@2 进入 Desktop Runner。</p><CartridgeSettingsEditor drafts={settingDrafts} params={(() => { try { return parseObject('执行参数', params) } catch { return {} } })()} errors={initialSettings.errors} onChange={setSettingDrafts} /></div>}
      {error && <p className="error"><CircleAlert />{error}</p>}
    </div>
    <div className="editor-actions"><button id="capability-node-save" type="button" onClick={() => void save()} disabled={working}><Save />保存节点</button><button className="danger" type="button" onClick={() => void remove()} disabled={working} title="删除节点"><Trash2 /></button></div>
  </aside>
}

type FieldDraft = { key: string; id: string; label: string; valueType: string; required: boolean; defaultValue: string; binding: string }
type PortDraft = { key: string; id: string; label: string; required: boolean; schemaType: string; storeKey: string }

const fieldDraft = (): FieldDraft => ({ key: crypto.randomUUID(), id: '', label: '', valueType: 'string', required: true, defaultValue: '', binding: '' })
const portDraft = (): PortDraft => ({ key: crypto.randomUUID(), id: '', label: '', required: true, schemaType: 'object', storeKey: '' })

function FieldEditor({ items, onChange }: { items: FieldDraft[]; onChange: (items: FieldDraft[]) => void }) {
  const update = (key: string, patch: Partial<FieldDraft>) => onChange(items.map((item) => item.key === key ? { ...item, ...patch } : item))
  return <section className="contract-section">
    <header><div><strong>创作者可调整字段</strong><small>只公开业务参数，不公开执行结构</small></div><button type="button" onClick={() => onChange([...items, fieldDraft()])}><Plus />添加字段</button></header>
    {items.length === 0 ? <p className="contract-empty">这个能力没有需要创作者调整的字段。</p> : items.map((item) => <div className="contract-row field-row" key={item.key}>
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

function AssistantPanel({ flowId, selectedId }: { flowId: string; selectedId: string }) {
  const [prompt, setPrompt] = useState('')
  const [answer, setAnswer] = useState<AnyRecord>({})
  const [working, setWorking] = useState(false)
  const [error, setError] = useState('')
  const ask = async () => {
    setWorking(true); setError('')
    try {
      const result = await capabilityApi.aiSteward(flowId, {
        message: prompt, mode: 'delegated', view: 'engineering', tool: 'pointer',
        selection: { node_ids: selectedId ? [selectedId] : [], edge_ids: [], field_paths: [] },
        scope_policy: 'selected_and_direct_edges',
      })
      setAnswer(object(result.message))
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'AI 建议生成失败。') } finally { setWorking(false) }
  }
  return <details className="workbench-panel assistant-panel"><summary><Bot />AI 实现助手</summary>
    <p>AI 只在当前 Flow 和选中节点范围内给出可审计的实现建议，应用修改仍由你确认。</p>
    <textarea value={prompt} onChange={(event) => setPrompt(event.currentTarget.value)} placeholder="例如：这个节点要读取一个公开接口，并把结果整理成 items 输出，应该怎样声明工具和数据端口？" />
    <button type="button" disabled={working || !prompt.trim()} onClick={() => void ask()}><Bot />生成实现建议</button>
    {error && <p className="error"><CircleAlert />{error}</p>}
    {Object.keys(answer).length > 0 && <div className="assistant-answer"><strong>{String(answer.understanding || '实现建议')}</strong><p>{String(answer.answer || '')}</p>{array(answer.operations).map((item, index) => <div key={index}><b>{String(item.op)}</b><span>{String(item.description)}</span></div>)}<small>{String(answer.next_step || '')}</small></div>}
  </details>
}

function ToolResourcePanel({ flowId, tools, catalog, onChanged }: {
  flowId: string; tools: AnyRecord[]; catalog: AnyRecord; onChanged: () => Promise<void>
}) {
  const [name, setName] = useState('')
  const [endpoint, setEndpoint] = useState('')
  const [authEnv, setAuthEnv] = useState('')
  const [working, setWorking] = useState(false)
  const [error, setError] = useState('')
  const addRemote = async () => {
    const id = slug(name) || `remote-${Date.now().toString(36)}`
    setWorking(true); setError('')
    try {
      const current = await capabilityApi.studioResources()
      const resource = {
        id, name, kind: 'remote_api', description: `供 ${flowId} 使用的远程接口`,
        server: id, tool: 'call', endpoint, http_method: 'POST', auth_env: authEnv,
        auth_header: 'Authorization', auth_scheme: 'Bearer', capabilities: ['remote.call'],
        read_only: false, package_mode: 'external', enabled: true,
      }
      const resources = array(current.tools).filter((item) => String(item.id) !== id)
      const bindings = object(current.bindings)
      const toolBindings = { ...object(bindings.tools) }
      toolBindings[flowId] = Array.from(new Set([...array(toolBindings[flowId]).map(String), id]))
      await capabilityApi.saveStudioResources({ version: 1, tools: [...resources, resource], bindings: { ...bindings, tools: toolBindings } })
      if (!tools.some((tool) => String(tool.id) === id)) {
        await capabilityApi.createMcpTool(flowId, { id, name, type: 'builtin', server: id, tool: 'call', description: resource.description, required: true, enabled: true, contract: { side_effect: 'external' } })
      }
      setName(''); setEndpoint(''); setAuthEnv('')
      await onChanged()
    } catch (reason) { setError(reason instanceof Error ? reason.message : '接口保存失败。') } finally { setWorking(false) }
  }
  const check = async (resourceId: string) => {
    setWorking(true); setError('')
    try { await capabilityApi.resourceConnectivity(flowId, resourceId); await onChanged() }
    catch (reason) { setError(reason instanceof Error ? reason.message : '连通性检查失败。') } finally { setWorking(false) }
  }
  return <details className="workbench-panel resource-panel"><summary><Plug />工具与资源</summary>
    <div className="resource-list">{array(catalog.tools).filter((item) => array(item.node_references).length || String(item.source) !== 'base_builtin').map((item) => <div key={String(item.resource_id || item.id)}><span><strong>{String(item.name || item.id)}</strong><small>{String(item.source)} · {String(item.status)}</small></span>{String(item.source) !== 'base_builtin' && <button type="button" disabled={working} onClick={() => void check(String(item.resource_id))}><RefreshCw />检查</button>}</div>)}</div>
    <section className="resource-create"><strong>声明一个外部接口</strong><label><span>名称</span><input value={name} onChange={(event) => setName(event.currentTarget.value)} /></label><label><span>HTTPS 地址</span><input value={endpoint} onChange={(event) => setEndpoint(event.currentTarget.value)} placeholder="https://api.example.com/action" /></label><label><span>凭据环境变量（可选）</span><input value={authEnv} onChange={(event) => setAuthEnv(event.currentTarget.value)} placeholder="EXAMPLE_API_TOKEN" /></label><button type="button" disabled={working || !name.trim() || !endpoint.trim()} onClick={() => void addRemote()}><Plus />保存并绑定到 Flow</button></section>
    {error && <p className="error"><CircleAlert />{error}</p>}
  </details>
}

async function waitForRun(runId: string) {
  for (let attempt = 0; attempt < 120; attempt += 1) {
    const run = await capabilityApi.run(runId)
    if (['completed', 'failed', 'cancelled', 'paused_waiting_user'].includes(String(run.status))) return run
    await new Promise((resolve) => window.setTimeout(resolve, 500))
  }
  throw new Error('运行没有在规定时间内结束。')
}

function DlcPanel({ flowId, onChanged }: { flowId: string; onChanged: () => Promise<void> }) {
  const [descriptor, setDescriptor] = useState<AnyRecord>({ tools: [] })
  const [name, setName] = useState('自定义能力')
  const [nodeId, setNodeId] = useState('custom_adapter')
  const [server, setServer] = useState('custom_adapter')
  const [tool, setTool] = useState('run')
  const [source, setSource] = useState('')
  const [sourceDigest, setSourceDigest] = useState('')
  const [working, setWorking] = useState(false)
  const [error, setError] = useState('')
  const load = async () => {
    const result = await capabilityApi.dlc(flowId)
    setDescriptor(result)
    const first = array(result.tools)[0]
    if (first?.node_id) {
      const response = await capabilityApi.mcpSource(flowId, String(first.node_id))
      setSource(String(response.source || '')); setSourceDigest(String(response.source_digest || ''))
    } else { setSource(''); setSourceDigest('') }
  }
  useEffect(() => { void load().catch(() => null) }, [flowId])
  const create = async () => {
    setWorking(true); setError('')
    try {
      await capabilityApi.scaffoldDlc(flowId, { node_id: nodeId, server, tool, name, description: `由 ${flowId} 自带并隔离运行的自定义实现` })
      await load(); await onChanged()
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'DLC 创建失败。') } finally { setWorking(false) }
  }
  const save = async () => {
    const first = array(descriptor.tools)[0]
    if (!first?.node_id) return
    setWorking(true); setError('')
    try {
      const result = await capabilityApi.replaceMcpSource(flowId, String(first.node_id), source, sourceDigest)
      setSource(String(result.source || source)); setSourceDigest(String(result.source_digest || ''))
      await onChanged()
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'DLC 源码没有通过协议检查。') } finally { setWorking(false) }
  }
  const exists = Boolean(descriptor.portable_dlc)
  return <details className="workbench-panel dlc-panel"><summary><Database />包内自定义适配器</summary>
    {!exists ? <div className="dlc-scaffold"><p>当外部没有现成工具或接口时，在卡带内部创建受协议约束的实现。骨架只提供隔离宿主，不包含任何业务逻辑。</p><label><span>名称</span><input value={name} onChange={(event) => setName(event.currentTarget.value)} /></label><label><span>源码节点 ID</span><input value={nodeId} onChange={(event) => setNodeId(event.currentTarget.value)} /></label><label><span>工具服务</span><input value={server} onChange={(event) => setServer(event.currentTarget.value)} /></label><label><span>工具动作</span><input value={tool} onChange={(event) => setTool(event.currentTarget.value)} /></label><button type="button" disabled={working || !name.trim() || !nodeId.trim()} onClick={() => void create()}><Plus />创建 DLC 骨架</button></div> : <div className="dlc-source"><div><strong>{String(object(descriptor.portable_dlc).id)}</strong><small>{String(array(descriptor.tools)[0]?.server)}/{String(array(descriptor.tools)[0]?.tool)} · {sourceDigest}</small></div><textarea value={source} spellCheck={false} onChange={(event) => setSource(event.currentTarget.value)} /><button type="button" disabled={working || !source.trim()} onClick={() => void save()}><Save />静态检查并保存源码</button></div>}
    {error && <p className="error"><CircleAlert />{error}</p>}
  </details>
}

function VerificationPanel({ flowId, onVerified }: { flowId: string; onVerified: (token: string) => void }) {
  const [successInputs, setSuccessInputs] = useState('{}')
  const [failureInputs, setFailureInputs] = useState('{}')
  const [successRun, setSuccessRun] = useState<AnyRecord>({})
  const [failureRun, setFailureRun] = useState<AnyRecord>({})
  const [working, setWorking] = useState('')
  const [error, setError] = useState('')
  const runCase = async (kind: 'success' | 'failure') => {
    setWorking(kind); setError(''); onVerified('')
    try {
      const inputs = JSON.parse(kind === 'success' ? successInputs : failureInputs) as AnyRecord
      const started = await capabilityApi.testRun(flowId, inputs)
      const completed = await waitForRun(String(object(started.run).run_id))
      if (kind === 'success') setSuccessRun(completed); else setFailureRun(completed)
    } catch (reason) { setError(reason instanceof Error ? reason.message : '运行失败。') } finally { setWorking('') }
  }
  const register = async () => {
    setWorking('register'); setError('')
    try {
      const result = await capabilityApi.verifyCapability(flowId, { success_run_id: String(successRun.run_id), failure_run_id: String(failureRun.run_id) })
      onVerified(String(object(result.verification).token))
    } catch (reason) { setError(reason instanceof Error ? reason.message : '运行证据登记失败。') } finally { setWorking('') }
  }
  return <section className="workbench-panel verification-panel"><header><div><Play /><span>真实运行证据</span></div><small>可信版本必须同时证明正常结果和安全失败</small></header>
    <div className="verification-cases"><label><span>成功用例输入 JSON</span><textarea value={successInputs} onChange={(event) => setSuccessInputs(event.currentTarget.value)} /><button type="button" disabled={Boolean(working)} onClick={() => void runCase('success')}><Play />运行成功用例</button><small className={successRun.status === 'completed' ? 'success' : ''}>{successRun.run_id ? `${String(successRun.status)} · ${String(successRun.run_id)}` : '尚未运行'}</small></label><label><span>失败用例输入 JSON</span><textarea value={failureInputs} onChange={(event) => setFailureInputs(event.currentTarget.value)} /><button type="button" disabled={Boolean(working)} onClick={() => void runCase('failure')}><CircleAlert />运行失败用例</button><small className={failureRun.status === 'failed' ? 'success' : ''}>{failureRun.run_id ? `${String(failureRun.status)} · ${String(failureRun.run_id)}` : '尚未运行'}</small></label></div>
    <button type="button" disabled={Boolean(working) || successRun.status !== 'completed' || failureRun.status !== 'failed'} onClick={() => void register()}><ShieldCheck />登记为当前源码证据</button>
    {error && <p className="error"><CircleAlert />{error}</p>}
  </section>
}

function PublishPanel({ flowId, flowName, goal, projectId, nodeId, verificationToken, validation, capabilities, onPublished }: {
  flowId: string; flowName: string; goal: string; projectId: string; nodeId: string; verificationToken: string; validation: AnyRecord; capabilities: AnyRecord[]; onPublished: () => Promise<void>
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
      const result = await capabilityApi.publishCapability(flowId, {
        capability_id: id.trim(), label: label.trim(), description: description.trim(),
        match_terms: terms.split(/[\n,，]/).map((item) => item.trim()).filter(Boolean),
        editable_fields: editableFields,
        creator_bindings: Object.fromEntries(fields.map((field) => [field.id.trim(), field.binding.trim()])),
        public_inputs: ports(inputs), public_outputs: ports(outputs), dependencies,
        trust_scope: 'workspace',
        verification_token: verificationToken,
        target_project_id: projectId || undefined,
        target_node_id: nodeId || undefined,
      })
      const release = object(result.release)
      setDone(`已发布 ${String(release.id)} v${String(release.revision)}，创作空间会重新检查原节点。`)
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
    {!verificationToken && <p className="contract-empty">先完成上方两次真实运行并登记证据，才能发布可信版本。</p>}
    <button type="button" onClick={() => void publish()} disabled={working || !validation.valid || !verificationToken || !id.trim() || !label.trim()}><PackageCheck />发布工作区可信版本</button>
  </section>
}

function Workshop() {
  const query = useMemo(() => new URLSearchParams(location.search), [])
  const creatorGoal = query.get('goal') || ''
  const projectId = query.get('projectId') || ''
  const targetNodeId = query.get('nodeId') || ''
  const [flows, setFlows] = useState<AnyRecord[]>([])
  const [flowId, setFlowId] = useState(query.get('flowId') || '')
  const [detail, setDetail] = useState<AnyRecord>({})
  const [flowFiles, setFlowFiles] = useState<PresentationFiles>({})
  const [validation, setValidation] = useState<AnyRecord>({ valid: false })
  const [selected, setSelected] = useState('')
  const [capabilities, setCapabilities] = useState<AnyRecord[]>([])
  const [capabilityEntries, setCapabilityEntries] = useState<AnyRecord[]>([])
  const [tools, setTools] = useState<AnyRecord[]>([])
  const [resourceCatalog, setResourceCatalog] = useState<AnyRecord>({ tools: [] })
  const [components, setComponents] = useState<AnyRecord[]>([])
  const [verificationToken, setVerificationToken] = useState('')
  const [error, setError] = useState('')
  const [newName, setNewName] = useState(creatorGoal || '新的能力卡带')
  const [workspaceTab, setWorkspaceTab] = useState<'design' | 'experience' | 'verify' | 'publish'>('design')
  const [capabilitySearch, setCapabilitySearch] = useState('')

  const loadRegistry = async () => {
    const result = await capabilityApi.capabilityRegistry()
    setCapabilities(result.capabilities)
    setCapabilityEntries(result.entries || [])
  }
  const loadFlows = async (preferred = flowId) => {
    const result = await capabilityApi.flows()
    setFlows(result.items)
    const next = preferred || (creatorGoal ? '' : String(result.items[0]?.id || ''))
    setFlowId(next)
    if (next) await load(next)
  }
  const load = async (id = flowId) => {
    if (!id) return
    setError('')
    try {
      const [nextDetail, nextFiles, nextValidation, nextTools, nextResources, nextAssets] = await Promise.all([
        capabilityApi.flow(id), capabilityApi.files(id), capabilityApi.capabilityReadiness(id), capabilityApi.mcpTools(id), capabilityApi.resources(id), capabilityApi.assets(id),
      ])
      const mergedDetail = withExecutionEdges(nextDetail, nextFiles)
      setDetail(mergedDetail); setValidation(nextValidation)
      setFlowFiles(object(nextFiles.files))
      setTools(array(nextTools.mcp_tools)); setResourceCatalog(nextResources); setComponents(array(nextAssets.components)); setVerificationToken('')
      const nodes = array(object(mergedDetail.graph).nodes)
      setSelected((current) => nodes.some((node) => String(node.id) === current) ? current : String(nodes.find((node) => node.type === 'process')?.id || nodes[0]?.id || ''))
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Flow 读取失败。') }
  }

  useEffect(() => { Promise.all([loadFlows(), loadRegistry()]).catch((reason) => setError(reason instanceof Error ? reason.message : '工坊加载失败。')) }, [])

  const createFlow = async () => {
    const flowSlug = slug(newName) || crypto.randomUUID().slice(0, 8)
    try {
      const result = await capabilityApi.createFlow({ flow_id: `dev.${flowSlug}`, name: newName, description: creatorGoal })
      await loadFlows(String(result.id))
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Flow 创建失败。') }
  }
  const addNode = async (templateId: string): Promise<string | undefined> => {
    if (!flowId) return undefined
    const nodeId = `${templateId}-${Date.now().toString(36)}`
    try {
      const title = templateId === 'prompt' ? 'AI 处理' : templateId === 'tool_call' ? '调用工具' : templateId === 'remote_call' ? '远程调用' : templateId === 'checkpoint' ? '人工审核' : templateId === 'interaction' ? '展示结果' : '数据处理'
      await capabilityApi.createNode(flowId, { template_id: templateId, node_id: nodeId, title, after_node_id: selected || undefined })
      await load(flowId); setSelected(nodeId)
      return nodeId
    } catch (reason) { setError(reason instanceof Error ? reason.message : '节点创建失败。'); return undefined }
  }

  const graph = object(detail.graph)
  const nodes = array(graph.nodes)
  const selectedNode = nodes.find((node) => String(node.id) === selected)
  const cartridge = object(detail.cartridge)
  const filteredCapabilities = capabilities.filter((item) => `${String(item.id)} ${String(object(item.creator).label || '')}`.toLowerCase().includes(capabilitySearch.toLowerCase()))
  const findingCount = array(validation.findings).length
  return <main className="workshop">
    <header className="topbar">
      <div className="workshop-brand"><b>CartridgeFlow</b><span>/</span><strong>能力工坊</strong>{creatorGoal && <><i /><small>AI 日报 / {creatorGoal}</small></>}</div>
      <div className="header-actions">
        {projectId && <a href={`/projects/${encodeURIComponent(projectId)}/studio`}><ArrowLeft />返回创作空间</a>}
        <button className="icon" type="button" title="帮助"><CircleHelp /></button><button className="icon" type="button" title="通知"><Bell /></button>
        <select aria-label="选择 Flow" value={flowId} onChange={(event) => { setFlowId(event.target.value); void load(event.target.value) }}><option value="">选择 Flow</option>{flows.map((flow) => <option key={String(flow.id)} value={String(flow.id)}>{String(flow.name || flow.id)}</option>)}</select>
        <span className="workshop-user">CF</span>
      </div>
    </header>
    {error && <p className="page-error"><CircleAlert />{error}</p>}
    {!flowId ? <section className="empty-workshop"><Wrench /><h1>新建能力卡带</h1><input value={newName} onChange={(event) => setNewName(event.currentTarget.value)} /><button type="button" onClick={() => void createFlow()} disabled={!newName.trim()}><FilePlus2 />创建内部 Flow</button></section> : <div className="workshop-product">
      <section className="capability-header">
        <div className="capability-identity"><Box /><div><strong>{String(cartridge.name || flowId)}</strong><span>v{String(cartridge.version || '1.0.0')} · 开发中版本</span></div><small className={validation.valid ? 'is-valid' : ''}><CheckCircle2 />{validation.valid ? '校验通过' : `${findingCount} 项待校验`}</small></div>
        <nav className="workshop-tabs" aria-label="能力制作阶段"><button className={workspaceTab === 'design' ? 'is-active' : ''} type="button" onClick={() => setWorkspaceTab('design')}><GitBranch />实现设计</button><button className={workspaceTab === 'experience' ? 'is-active' : ''} type="button" onClick={() => setWorkspaceTab('experience')}><Box />展示组件</button><button className={workspaceTab === 'verify' ? 'is-active' : ''} type="button" onClick={() => setWorkspaceTab('verify')}><Play />运行验证</button><button className={workspaceTab === 'publish' ? 'is-active' : ''} type="button" onClick={() => setWorkspaceTab('publish')}><PackageCheck />版本发布</button></nav>
        <div className="capability-actions"><button type="button" onClick={() => void load()}><RefreshCw />刷新</button><button type="button" onClick={() => setWorkspaceTab('verify')}><Play />运行能力</button><button className="primary" type="button" disabled={workspaceTab === 'design' ? !selectedNode : workspaceTab !== 'experience'} onClick={() => { if (workspaceTab === 'experience') document.getElementById('display-component-save')?.click(); else { setWorkspaceTab('design'); requestAnimationFrame(() => document.getElementById('capability-node-save')?.click()) } }}><Save />{workspaceTab === 'experience' ? '保存组件' : '保存节点'}</button></div>
      </section>

      <div className="workshop-shell">
        <aside className="workshop-sidebar">
          <details open><summary>节点库<ChevronDown /></summary><div className="node-library"><button type="button" disabled><Play /><span>开始</span></button><button type="button" onClick={() => void addNode('interaction')}><Box /><span>展示结果</span></button><button type="button" onClick={() => void addNode('checkpoint')}><User /><span>人工审核</span></button><button type="button" onClick={() => void addNode('runtime')}><GitBranch /><span>数据处理</span></button><button type="button" onClick={() => void addNode('tool_call')}><Plug /><span>调用工具</span></button><button type="button" onClick={() => void addNode('prompt')}><Bot /><span>AI 处理</span></button></div><div className="node-library-footer"><button type="button" onClick={() => void addNode('remote_call')}>服务节点</button><button type="button" onClick={() => setWorkspaceTab('experience')}>设计展示</button></div></details>
          <details open><summary>可复用能力<ChevronDown /></summary><label className="capability-search"><Search /><input value={capabilitySearch} onChange={(event) => setCapabilitySearch(event.currentTarget.value)} placeholder="搜索可复用能力" /></label><div className="reusable-capabilities">{filteredCapabilities.length ? filteredCapabilities.map((item) => <button type="button" key={String(item.id)} title={String(item.id)}><strong>{String(object(item.creator).label || item.id)}</strong><small>v{String(item.revision)} · {String(item.trust_scope || 'workspace')}</small></button>) : <p>没有匹配的已发布能力。</p>}</div></details>
          <AssistantPanel flowId={flowId} selectedId={selected} />
          <ToolResourcePanel flowId={flowId} tools={tools} catalog={resourceCatalog} onChanged={() => load(flowId)} />
          <DlcPanel flowId={flowId} onChanged={() => load(flowId)} />
          <details open className="proof-library"><summary>基础运行证明<ChevronDown /></summary>{capabilities.slice(0, 3).map((item) => <div key={String(item.id)}><ShieldCheck /><span><strong>{String(object(item.creator).label || item.id)}</strong><small>workspace · v{String(item.revision)}</small></span></div>)}</details>
        </aside>

        <section className={`workshop-stage is-${workspaceTab}`}>
          {workspaceTab === 'design' && <div className="workshop-body"><Graph flowId={flowId} graph={graph} selected={selected} onSelect={setSelected} onReload={() => load(flowId)} />{selectedNode ? <CapabilityNodeEditor key={`${flowId}:${selected}`} flowId={flowId} node={selectedNode} tools={tools} manifestInputs={array(cartridge.inputs)} files={flowFiles} onSaved={() => load(flowId)} onClose={() => setSelected('')} /> : <aside className="node-editor boundary-editor"><div className="boundary-copy"><GitBranch /><p>选择一个节点后在这里配置实现、契约和运行参数。</p></div></aside>}</div>}
          {workspaceTab === 'experience' && <DisplayComponentWorkshop flowId={flowId} graph={graph} manifestInputs={array(cartridge.inputs)} components={components} onCreateDisplayNode={() => addNode('interaction')} onSaved={() => load(flowId)} />}
          {workspaceTab === 'verify' && <div className="phase-workspace verification-workspace"><header><div><span>运行验证</span><h2>用真实成功与失败路径证明能力边界</h2></div><small>{verificationToken ? <><CheckCircle2 />运行证据已登记</> : '需要 2 个互补用例'}</small></header><VerificationPanel flowId={flowId} onVerified={setVerificationToken} /></div>}
          {workspaceTab === 'publish' && <div className="phase-workspace publish-workspace"><PublishPanel flowId={flowId} flowName={String(cartridge.name || flowId)} goal={creatorGoal} projectId={projectId} nodeId={targetNodeId} verificationToken={verificationToken} validation={validation} capabilities={capabilities} onPublished={loadRegistry} /><details className="workbench-panel capability-registry"><summary><Boxes />已发布能力与版本</summary>{capabilityEntries.length === 0 ? <p>还没有发布过能力。</p> : capabilityEntries.map((entry) => <div key={String(entry.id)}><span><strong>{String(object(entry.current).creator ? object(object(entry.current).creator).label : entry.id)}</strong><small>{String(entry.id)} · {String(entry.status)} · {array(entry.revisions).length || 1} 个版本</small></span><button type="button" onClick={async () => { await capabilityApi.activateCapability(String(entry.id), entry.status !== 'active'); await loadRegistry() }}><Power />{entry.status === 'active' ? '停用' : '启用'}</button></div>)}</details></div>}
        </section>
      </div>

      <footer className="workshop-readiness"><div><CircleAlert /><span>未解决校验</span><b>{findingCount}</b></div><div><span>契约完整度</span><small className={validation.valid ? 'ready' : ''}>{validation.valid ? '可完成' : '待补齐'}</small></div><div><span>运行证明</span><small className={verificationToken ? 'ready' : ''}>{verificationToken ? '已就绪 2/2' : '尚未登记'}</small></div><div><span>发布就绪度</span><small className={validation.valid && verificationToken ? 'ready' : ''}>{validation.valid && verificationToken ? '可发布' : '待完成'}</small></div><button type="button" onClick={() => setWorkspaceTab(workspaceTab === 'design' ? 'experience' : workspaceTab === 'experience' ? 'verify' : 'publish')} disabled={workspaceTab === 'publish'}>{workspaceTab === 'design' ? <><Box />进入展示组件</> : workspaceTab === 'experience' ? <><Play />进入运行验证</> : workspaceTab === 'verify' ? <><PackageCheck />进入版本发布</> : <><Check />已进入发布</>}</button></footer>
    </div>}
  </main>
}

createRoot(document.getElementById('root')!).render(<Workshop />)
