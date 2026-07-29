import { useEffect, useMemo, useRef, useState } from 'react'
import {
  ArrowRight,
  BrainCircuit,
  Cable,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  CirclePlus,
  Copy,
  Download,
  FileJson,
  Info,
  PackageCheck,
  RefreshCw,
  Search,
  ShieldCheck,
  Upload,
  Workflow,
  Wrench,
  X,
  Zap,
} from 'lucide-react'
import {
  createLlmProvider,
  createStudioCredential,
  addMcpOperation,
  deleteLlmProvider,
  exportLlmConfig,
  fetchLlmAssignments,
  fetchFlowResourceCatalog,
  fetchMcpSource,
  fetchStudioEnvironment,
  fetchStudioPackages,
  fetchStudioReleasePreflight,
  fetchStudioResources,
  importOpenCodeConfig,
  packageCartridge,
  patchMcpOperationGraph,
  saveLlmAssignments,
  saveStudioResources,
  testLlmProvider,
  updateLlmProvider,
  type CartridgeDetail,
  type LlmAssignments,
  type LlmProvider,
  type McpTool,
  type McpSourceResponse,
  type StudioResources,
  type StudioPackageItem,
  type StudioReleasePreflight,
  type StudioToolResource,
  type FlowGraph,
  type FlowResourceCatalog,
} from '../../api.ts'
import { resolveNodeSemanticKind } from './flowNodeView.ts'

type ModelRole = { id: string; label: string; model?: string }
type ModelManagementStage = 'connections' | 'flow' | 'nodes'
type ProviderDraft = {
  id: string
  name: string
  apiKey: string
  baseUrl: string
  model: string
  wireApi: string
  timeout: number
}
type ToolDraft = {
  id: string
  name: string
  description: string
  kind: string
  server: string
  tool: string
  endpoint: string
  command: string
  args: string
  openapiUrl: string
  httpMethod: string
  authEnv: string
  apiKey: string
  enabled: boolean
  readOnly: boolean
}

const EMPTY_ASSIGNMENTS: LlmAssignments = { version: 1, defaults: {}, cartridges: {}, nodes: {} }
const EMPTY_RESOURCES: StudioResources = { version: 1, tools: [], bindings: { roles: {}, tools: {} }, builtin_tools: [] }

function downloadJson(filename: string, value: unknown) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2)], { type: 'application/json' }))
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}

function providerDraft(provider?: LlmProvider): ProviderDraft {
  return {
    id: provider?.id || '',
    name: provider?.name || '',
    apiKey: '',
    baseUrl: provider?.base_url || '',
    model: provider?.default_model || '',
    wireApi: provider?.wire_api || 'chat_completions',
    timeout: provider?.timeout || 120,
  }
}

function flowModelRoles(cartridge: CartridgeDetail): ModelRole[] {
  const recipe = cartridge.llm_recipe || cartridge.manifest?.llm_recipe || {}
  const roles = Array.isArray(recipe.roles) ? recipe.roles : []
  const normalized = roles.flatMap((item: any) => {
    const id = String(item?.id || '').trim()
    return id && id !== 'authoring' && id !== 'mentor' ? [{ id, label: String(item?.label || id), model: String(item?.model || '') }] : []
  })
  if (normalized.length) return normalized
  return [{ id: 'runtime', label: 'Runtime model' }]
}

function StatusMessage({ text, tone = 'neutral' }: { text: string; tone?: 'neutral' | 'success' | 'error' }) {
  return <div className={`cf-resource-feedback ${tone}`}>{tone === 'success' ? <CheckCircle2 /> : tone === 'error' ? <X /> : <Info />}<span>{text}</span></div>
}

export function ModelManagementPanel({ flowId, cartridge, graph }: { flowId: string; cartridge: CartridgeDetail; graph?: FlowGraph }) {
  const [providers, setProviders] = useState<LlmProvider[]>([])
  const [assignments, setAssignments] = useState<LlmAssignments>(EMPTY_ASSIGNMENTS)
  const [expandedId, setExpandedId] = useState('')
  const [draft, setDraft] = useState<ProviderDraft>(providerDraft())
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<{ text: string; tone: 'neutral' | 'success' | 'error' } | null>(null)
  const [activeStage, setActiveStage] = useState<ModelManagementStage>('connections')
  const importRef = useRef<HTMLInputElement>(null)
  const initialExpansionRef = useRef(false)
  const roles = useMemo(() => flowModelRoles(cartridge), [cartridge])
  const flowBindings = assignments.cartridges?.[flowId] || {}
  const decisionNodes = useMemo(() => (graph?.nodes || []).filter((node) => resolveNodeSemanticKind(node) === 'decision' || Boolean(node.model_role) || /decision|intent_router/i.test(`${node.type} ${node.action || ''}`)), [graph])
  const providerById = useMemo(() => new Map(providers.map((provider) => [provider.id, provider])), [providers])
  const flowProviderIds = useMemo(() => new Set(Object.values(flowBindings).map((binding) => binding.provider_id).filter(Boolean) as string[]), [flowBindings])
  const flowProviders = useMemo(() => providers.filter((provider) => flowProviderIds.has(provider.id)), [providers, flowProviderIds])
  const boundRoleCount = roles.filter((role) => Boolean(flowBindings[role.id]?.provider_id)).length
  const boundNodeCount = decisionNodes.filter((node) => Boolean(assignments.nodes?.[`${flowId}/${node.id}`]?.[node.model_role || 'runtime']?.provider_id)).length

  const reload = async () => {
    const [assignmentData, resourceCatalog] = await Promise.all([fetchLlmAssignments(), fetchFlowResourceCatalog(flowId)])
    const nextProviders = resourceCatalog.models.providers || []
    setProviders(nextProviders)
    const nextAssignments = assignmentData || EMPTY_ASSIGNMENTS
    nextAssignments.cartridges ||= {}
    nextAssignments.nodes ||= {}
    nextAssignments.cartridges[flowId] = resourceCatalog.models.flow_bindings || {}
    for (const item of resourceCatalog.models.node_bindings || []) {
      const key = `${flowId}/${item.node_id}`
      if (item.binding && item.role) nextAssignments.nodes[key] = { ...(nextAssignments.nodes[key] || {}), [item.role]: item.binding }
      else if (nextAssignments.nodes[key] && item.role) delete nextAssignments.nodes[key][item.role]
    }
    setAssignments(nextAssignments)
    if (!initialExpansionRef.current && nextProviders[0]) {
      initialExpansionRef.current = true
      setExpandedId(nextProviders[0].id)
      setDraft(providerDraft(nextProviders[0]))
    }
  }

  useEffect(() => { void reload().catch((error) => setMessage({ text: error.message, tone: 'error' })) }, [flowId])

  const openProvider = (provider: LlmProvider) => {
    const next = expandedId === provider.id ? '' : provider.id
    setExpandedId(next)
    setDraft(providerDraft(provider))
    setMessage(null)
  }

  const startNew = () => {
    setExpandedId('__new__')
    setDraft(providerDraft())
    setMessage(null)
  }

  const saveProvider = async () => {
    if (!draft.name.trim() || !draft.baseUrl.trim() || !draft.model.trim()) {
      setMessage({ text: '名称、Base URL 和默认模型不能为空。', tone: 'error' })
      return
    }
    setBusy(true)
    try {
      const payload = {
        id: draft.id,
        name: draft.name,
        api_type: 'openai',
        api_key: draft.apiKey,
        base_url: draft.baseUrl,
        default_model: draft.model,
        wire_api: draft.wireApi,
        capabilities: ['text_reasoning'],
        adapter_profile: 'standard',
        enabled: providers.length === 0,
        timeout: Number(draft.timeout) || 120,
      }
      const result = draft.id ? await updateLlmProvider(draft.id, payload) : await createLlmProvider(payload)
      await reload()
      setExpandedId(result.provider.id)
      setDraft(providerDraft(result.provider))
      setMessage({ text: '连接配置已保存在本机。', tone: 'success' })
    } catch (error: any) {
      setMessage({ text: error.message || '保存失败', tone: 'error' })
    } finally {
      setBusy(false)
    }
  }

  const testProvider = async () => {
    if (!draft.id) {
      setMessage({ text: '请先保存连接，再执行真实连通性测试。', tone: 'neutral' })
      return
    }
    setBusy(true)
    try {
      await testLlmProvider(draft.id, draft.model)
      await reload()
      setMessage({ text: '模型已返回真实响应，连接可用。', tone: 'success' })
    } catch (error: any) {
      setMessage({ text: error.message || '连接测试失败', tone: 'error' })
    } finally {
      setBusy(false)
    }
  }

  const bindRole = async (role: ModelRole, providerId: string) => {
    const next: LlmAssignments = JSON.parse(JSON.stringify(assignments || EMPTY_ASSIGNMENTS))
    next.cartridges ||= {}
    next.cartridges[flowId] ||= {}
    const provider = providerById.get(providerId)
    if (provider) next.cartridges[flowId][role.id] = { provider_id: provider.id, model: provider.default_model || role.model || '' }
    else delete next.cartridges[flowId][role.id]
    if (Object.keys(next.cartridges[flowId]).length === 0) delete next.cartridges[flowId]

    const nextFlowProviderIds = new Set(Object.values(next.cartridges?.[flowId] || {}).map((binding) => binding.provider_id).filter(Boolean))
    const affectedNodeKeys: string[] = []
    for (const [nodeKey, nodeRoles] of Object.entries(next.nodes || {})) {
      if (!nodeKey.startsWith(`${flowId}/`)) continue
      for (const [nodeRole, binding] of Object.entries(nodeRoles)) {
        if (binding.provider_id && !nextFlowProviderIds.has(binding.provider_id)) {
          affectedNodeKeys.push(`${nodeKey}:${nodeRole}`)
        }
      }
    }
    if (affectedNodeKeys.length && !window.confirm(`这次修改会让 ${affectedNodeKeys.length} 个节点绑定失去 Flow 级来源。是否同时解除这些节点绑定？`)) return
    for (const reference of affectedNodeKeys) {
      const splitAt = reference.lastIndexOf(':')
      const nodeKey = reference.slice(0, splitAt)
      const nodeRole = reference.slice(splitAt + 1)
      delete next.nodes[nodeKey][nodeRole]
      if (Object.keys(next.nodes[nodeKey]).length === 0) delete next.nodes[nodeKey]
    }
    setBusy(true)
    try {
      const result = await saveLlmAssignments(next)
      setAssignments(result.assignments)
      const suffix = affectedNodeKeys.length ? `，并解除 ${affectedNodeKeys.length} 个失去来源的节点绑定` : ''
      setMessage({ text: provider ? `${role.label} 已绑定连接 ID：${provider.id}${suffix}` : `${role.label} 已解除 Flow 绑定${suffix}。`, tone: 'success' })
    } catch (error: any) {
      setMessage({ text: error.message || '绑定失败', tone: 'error' })
    } finally {
      setBusy(false)
    }
  }

  const bindDecisionNode = async (node: FlowGraph['nodes'][number], providerId: string) => {
    const next: LlmAssignments = JSON.parse(JSON.stringify(assignments || EMPTY_ASSIGNMENTS))
    next.nodes ||= {}
    const key = `${flowId}/${node.id}`
    const role = node.model_role || 'runtime'
    const provider = flowProviders.find((item) => item.id === providerId)
    next.nodes[key] ||= {}
    if (provider) next.nodes[key][role] = { provider_id: provider.id, model: provider.default_model || '' }
    else delete next.nodes[key][role]
    if (Object.keys(next.nodes[key] || {}).length === 0) delete next.nodes[key]
    setBusy(true)
    try {
      const result = await saveLlmAssignments(next)
      setAssignments(result.assignments)
      setMessage({ text: provider ? `${node.display_name || node.title || node.id} 已绑定 ${provider.name || provider.id}。` : `${node.display_name || node.title || node.id} 已解除节点绑定。`, tone: 'success' })
    } catch (error: any) {
      setMessage({ text: error.message || '节点绑定失败', tone: 'error' })
    } finally { setBusy(false) }
  }

  const removeProvider = async (provider: LlmProvider) => {
    if (!window.confirm(`删除本机模型连接“${provider.name}”？`)) return
    setBusy(true)
    try {
      await deleteLlmProvider(provider.id)
      setExpandedId('')
      await reload()
      setMessage({ text: '本机模型连接已删除。', tone: 'success' })
    } catch (error: any) {
      setMessage({ text: error.message || '删除失败', tone: 'error' })
    } finally {
      setBusy(false)
    }
  }

  const importConfig = async (file?: File) => {
    if (!file) return
    setBusy(true)
    try {
      await importOpenCodeConfig(await file.text())
      await reload()
      setMessage({ text: 'OpenCode 配置已导入并完成自动检测。', tone: 'success' })
    } catch (error: any) {
      setMessage({ text: error.message || '导入失败', tone: 'error' })
    } finally {
      setBusy(false)
      if (importRef.current) importRef.current.value = ''
    }
  }

  return (
    <div className="cf-resource-manager">
      <div className="cf-resource-manager-actions">
        <button className="primary" type="button" onClick={startNew}><CirclePlus />新增连接</button>
        <button type="button" onClick={() => importRef.current?.click()}><Upload />导入配置</button>
        <button type="button" onClick={async () => downloadJson('cartridgeflow-models.json', await exportLlmConfig())}><Download />导出配置</button>
        <input ref={importRef} type="file" accept="application/json,.json" hidden onChange={(event) => void importConfig(event.target.files?.[0])} />
      </div>
      <nav className="cf-model-binding-path" aria-label="模型绑定层级">
        <button type="button" className={activeStage === 'connections' ? 'active' : ''} onClick={() => setActiveStage('connections')}>
          <i><Cable /></i><span><b>1. 模型 API</b><small>本机连接资源池</small></span><em>{providers.length} 个</em>
        </button>
        <ArrowRight className="cf-model-binding-arrow" />
        <button type="button" className={activeStage === 'flow' ? 'active' : ''} onClick={() => setActiveStage('flow')}>
          <i><Workflow /></i><span><b>2. 当前 Flow</b><small>按模型角色接入</small></span><em>{boundRoleCount}/{roles.length}</em>
        </button>
        <ArrowRight className="cf-model-binding-arrow" />
        <button type="button" className={activeStage === 'nodes' ? 'active' : ''} onClick={() => setActiveStage('nodes')}>
          <i><BrainCircuit /></i><span><b>3. AI 节点</b><small>分配到具体节点</small></span><em>{boundNodeCount}/{decisionNodes.length}</em>
        </button>
      </nav>
      <div className="cf-resource-scope-note"><Info /><span>连接先保存在本机资源池，再进入当前 Flow，最后才能分配给具体 AI 节点；API Key 始终不会写入 Flow。</span></div>
      {message && <StatusMessage {...message} />}

      {activeStage === 'connections' && <section className="cf-model-stage">
        <header className="cf-model-stage-head">
          <div><span>第 1 层</span><h3>模型 API 连接</h3><p>这里管理本机可用连接。新增或导入连接后，它仍未属于任何 Flow。</p></div>
          <strong>{providers.length}<small>资源池连接</small></strong>
        </header>
        <div className="cf-resource-list">
          {providers.length === 0 && expandedId !== '__new__' && <div className="cf-resource-empty"><FileJson /><b>还没有模型 API 连接</b><span>新增一个 OpenAI 兼容连接，保存后再进入下一层绑定当前 Flow。</span><button type="button" onClick={startNew}><CirclePlus />新增连接</button></div>}
          {[...(expandedId === '__new__' ? [{ id: '__new__', name: '新模型连接' } as LlmProvider] : []), ...providers].map((provider) => {
            const expanded = expandedId === provider.id
            const boundRoles = roles.filter((role) => flowBindings[role.id]?.provider_id === provider.id)
            const tested = provider.id === '__new__' ? false : provider.tested_ok
            return (
              <article key={provider.id} className={`cf-resource-card cf-model-resource-card ${expanded ? 'expanded' : ''}`}>
                <button className="cf-resource-card-summary" type="button" onClick={() => provider.id === '__new__' ? undefined : openProvider(provider)}>
                  <span className={`cf-resource-status ${tested ? 'ok' : 'pending'}`}><i />{tested ? '连接成功' : provider.id === '__new__' ? '尚未保存' : '等待测试'}</span>
                  <span className={`cf-resource-binding ${boundRoles.length ? 'ok' : ''}`}>{boundRoles.length ? <CheckCircle2 /> : <Info />}{boundRoles.length ? `当前 Flow · ${boundRoles.length} 个角色` : '资源池 · 未绑定 Flow'}</span>
                  {provider.id !== '__new__' && (expanded ? <ChevronUp /> : <ChevronDown />)}
                  <strong>{provider.name}</strong>
                  <small>{provider.id === '__new__' ? '填写连接信息后会生成稳定连接 ID' : `${provider.default_model || '未设置默认模型'} · 连接 ID：${provider.id}`}</small>
                </button>
                {expanded && (
                  <div className="cf-resource-card-body">
                    <div className="cf-resource-form">
                      <label><span>连接 ID</span><div className="with-action"><input value={draft.id || '保存后自动生成'} readOnly /><button type="button" disabled={!draft.id} onClick={() => navigator.clipboard.writeText(draft.id)} title="复制连接 ID"><Copy /></button></div></label>
                      <label><span>API Key</span><input type="password" value={draft.apiKey} placeholder={provider.has_key ? `已保存在本机 ${provider.key_preview || ''}` : '输入本机密钥'} onChange={(event) => setDraft({ ...draft, apiKey: event.target.value })} /></label>
                      <label><span>Base URL / 接口地址</span><input value={draft.baseUrl} placeholder="https://api.example.com/v1" onChange={(event) => setDraft({ ...draft, baseUrl: event.target.value })} /></label>
                      <label><span>模型</span><input list={`models-${provider.id}`} value={draft.model} onChange={(event) => setDraft({ ...draft, model: event.target.value })} /><datalist id={`models-${provider.id}`}>{(provider.available_models || []).map((model) => <option key={model} value={model} />)}</datalist></label>
                      <label><span>名称</span><input value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} /></label>
                      <label><span>调用协议</span><select value={draft.wireApi} onChange={(event) => setDraft({ ...draft, wireApi: event.target.value })}><option value="chat_completions">Chat Completions</option><option value="responses">Responses</option></select></label>
                      <label><span>超时时间</span><div className="input-suffix"><input type="number" min="1" max="900" value={draft.timeout} onChange={(event) => setDraft({ ...draft, timeout: Number(event.target.value) })} /><i>秒</i></div></label>
                    </div>
                    <div className="cf-resource-card-actions">
                      <button type="button" disabled={busy || !draft.id} onClick={() => void testProvider()}><Zap />测试连接</button>
                      {provider.id !== '__new__' && <button className="danger" type="button" disabled={busy} onClick={() => void removeProvider(provider)}>删除连接</button>}
                      {provider.id !== '__new__' && <button type="button" onClick={() => setActiveStage('flow')}>前往 Flow 绑定<ArrowRight /></button>}
                      <button className="primary" type="button" disabled={busy} onClick={() => void saveProvider()}>保存</button>
                    </div>
                  </div>
                )}
              </article>
            )
          })}
        </div>
      </section>}

      {activeStage === 'flow' && <section className="cf-model-stage">
        <header className="cf-model-stage-head">
          <div><span>第 2 层</span><h3>绑定到当前 Flow</h3><p>把资源池连接分配给当前 Flow 声明的模型角色。未选择的连接仍只属于本机资源池。</p></div>
          <strong>{boundRoleCount}/{roles.length}<small>角色已绑定</small></strong>
        </header>
        {providers.length === 0 ? <div className="cf-resource-empty"><Cable /><b>资源池中没有可绑定连接</b><span>请先新增并测试模型 API，再返回这里完成 Flow 绑定。</span><button type="button" onClick={() => { setActiveStage('connections'); startNew() }}><CirclePlus />新增连接</button></div> : <>
          <div className="cf-model-available-strip"><span>资源池可用</span>{providers.map((provider) => <button type="button" key={provider.id} onClick={() => { openProvider(provider); setActiveStage('connections') }}><i className={provider.tested_ok ? 'ok' : ''} />{provider.name || provider.id}<small>{provider.default_model}</small></button>)}</div>
          <div className="cf-model-binding-list">
            {roles.map((role) => {
              const binding = flowBindings[role.id]
              const provider = binding?.provider_id ? providerById.get(binding.provider_id) : undefined
              return <article className={binding ? 'is-bound' : ''} key={role.id}>
                <i><Workflow /></i>
                <span><b>{role.label}</b><code>{role.id}</code></span>
                <div>{provider ? <><b>{provider.name || provider.id}</b><small>{binding.model || provider.default_model || '使用连接默认模型'}</small></> : <><b>尚未绑定</b><small>此角色暂时不能运行</small></>}</div>
                <select aria-label={`为 ${role.label} 选择模型连接`} value={binding?.provider_id || ''} disabled={busy} onChange={(event) => void bindRole(role, event.target.value)}><option value="">不绑定</option>{providers.map((item) => <option key={item.id} value={item.id}>{item.name || item.id} · {item.default_model || '默认模型未设置'}</option>)}</select>
              </article>
            })}
          </div>
        </>}
        <footer className="cf-model-stage-next"><span>{boundRoleCount ? `当前 Flow 已使用 ${flowProviderIds.size} 个模型 API 连接。` : '完成至少一个 Flow 角色绑定后，才能继续分配具体节点。'}</span><button type="button" disabled={!flowProviderIds.size} onClick={() => setActiveStage('nodes')}>继续绑定 AI 节点<ArrowRight /></button></footer>
      </section>}

      {activeStage === 'nodes' && <section className="cf-model-stage">
        <header className="cf-model-stage-head">
          <div><span>第 3 层</span><h3>绑定具体 AI 节点</h3><p>节点只能选择已经进入当前 Flow 的模型 API；资源池中未绑定 Flow 的连接不会出现在这里。</p></div>
          <strong>{boundNodeCount}/{decisionNodes.length}<small>节点已绑定</small></strong>
        </header>
        {!flowProviders.length ? <div className="cf-resource-empty"><Workflow /><b>当前 Flow 还没有模型连接</b><span>先完成第 2 层 Flow 绑定，再为具体 AI 节点选择执行模型。</span><button type="button" onClick={() => setActiveStage('flow')}>返回 Flow 绑定</button></div> : decisionNodes.length === 0 ? <div className="cf-resource-empty"><BrainCircuit /><b>当前 Flow 没有 AI 决策节点</b><span>添加具有模型角色的 AI 决策节点后，它们会显示在这里。</span></div> : <div className="cf-model-binding-list node-list">
          {decisionNodes.map((node) => {
            const role = node.model_role || 'runtime'
            const binding = assignments.nodes?.[`${flowId}/${node.id}`]?.[role]
            const provider = binding?.provider_id ? providerById.get(binding.provider_id) : undefined
            return <article className={binding ? 'is-bound' : ''} key={node.id}>
              <i><BrainCircuit /></i>
              <span><b>{node.display_name || node.title || node.id}</b><code>{node.id} · {role}</code></span>
              <div>{provider ? <><b>{provider.name || provider.id}</b><small>{binding.model || provider.default_model || '使用连接默认模型'}</small></> : <><b>尚未绑定</b><small>运行前需要选择 Flow 内连接</small></>}</div>
              <select aria-label={`为 ${node.display_name || node.title || node.id} 选择模型连接`} value={binding?.provider_id || ''} disabled={busy} onChange={(event) => void bindDecisionNode(node, event.target.value)}><option value="">不绑定</option>{flowProviders.map((item) => <option key={item.id} value={item.id}>{item.name || item.id} · {item.default_model || '默认模型未设置'}</option>)}</select>
            </article>
          })}
        </div>}
        <footer className="cf-model-stage-next"><span>每个 AI 节点必须从当前 Flow 的连接池中明确选择模型；解绑后该节点不可运行。</span><button type="button" onClick={() => setActiveStage('flow')}>返回 Flow 绑定</button></footer>
      </section>}
      <p className="cf-resource-manager-foot"><Info />连接 ID 是本机模型插座编号；Flow 和节点只保存连接 ID 与模型角色，不保存 API Key。</p>
    </div>
  )
}

function toolDraft(tool?: StudioToolResource): ToolDraft {
  return {
    id: tool?.id || '',
    name: tool?.name || '',
    description: tool?.description || '',
    kind: tool?.kind === 'builtin' ? 'mcp' : tool?.kind || 'mcp',
    server: tool?.server || '',
    tool: tool?.tool || '',
    endpoint: tool?.endpoint || '',
    command: tool?.command || '',
    args: tool?.args || '',
    openapiUrl: tool?.openapi_url || '',
    httpMethod: tool?.http_method || 'POST',
    authEnv: tool?.auth_env || '',
    apiKey: '',
    enabled: tool?.enabled !== false,
    readOnly: tool?.read_only === true,
  }
}

function toolConfigured(tool: StudioToolResource, configuredKeys: Set<string>) {
  if (tool.source !== 'local_resource') return tool.status === 'ready' || tool.status === 'available'
  if (tool.kind === 'builtin') return true
  const transportReady = tool.kind === 'remote_api' ? Boolean(tool.endpoint || tool.openapi_url) : Boolean(tool.endpoint || tool.command)
  return transportReady && (!tool.auth_env || configuredKeys.has(tool.auth_env.toUpperCase()))
}

function toFlowMcpTool(tool: StudioToolResource): McpTool {
  return {
    id: tool.id,
    name: tool.name,
    type: tool.source === 'cartridge_dlc' ? 'cartridge_dlc' : tool.source === 'local_resource' ? 'local_resource' : 'base_builtin',
    server: tool.server || tool.id,
    tool: tool.tool || tool.id,
    description: tool.description,
    enabled: tool.enabled !== false,
    node_id: tool.node_id,
    transparency: tool.transparency,
    source_digest: tool.source_digest,
  }
}

function graphDraftFromSource(data: McpSourceResponse | null) {
  const model = data?.source_model
  return JSON.stringify({
    operations: model?.operations || [],
    edges: model?.edges || [],
    fallbacks: model?.fallbacks || [],
    capabilities: model?.capabilities || [],
    inputs: model?.inputs || {},
    outputs: model?.outputs || {},
  }, null, 2)
}

function operationGraphForPreview(tool: StudioToolResource, data: McpSourceResponse | null) {
  const model = data?.source_model
  return {
    operations: (model?.operations || tool.operation_graph?.operations || []).filter((item: any) => item && typeof item === 'object'),
    edges: (model?.edges || tool.operation_graph?.edges || []).filter((item: any) => item && typeof item === 'object'),
    fallbacks: (model?.fallbacks || tool.operation_graph?.fallbacks || []).filter((item: any) => item && typeof item === 'object'),
  }
}

function McpOperationGraphPreview({ tool, data }: { tool: StudioToolResource; data: McpSourceResponse | null }) {
  const graph = operationGraphForPreview(tool, data)
  if (!graph.operations.length) return null
  const fallbackByOperation = new Map<string, number>()
  for (const item of graph.fallbacks) {
    const from = String(item.from || '').trim()
    if (from) fallbackByOperation.set(from, (fallbackByOperation.get(from) || 0) + 1)
  }
  return (
    <div className="cf-mcp-operation-graph">
      <header>
        <b>内部流程</b>
        <span>{graph.operations.length} 个操作 · {graph.edges.length} 条连线 · {graph.fallbacks.length} 条备用路径</span>
      </header>
      <div className="cf-mcp-operation-rail">
        {graph.operations.map((operation: any, index: number) => {
          const operationId = String(operation.id || `operation_${index + 1}`)
          const next = graph.edges.filter((edge: any) => String(edge.from || '') === operationId).map((edge: any) => String(edge.to || '')).filter(Boolean)
          const capability = String(operation.capability || '').trim()
          return (
            <div className="cf-mcp-operation-node" key={operationId}>
              <strong>{operationId}</strong>
              <small>{String(operation.kind || 'operation')}</small>
              {capability && <code>{capability}</code>}
              {fallbackByOperation.get(operationId) ? <em>{fallbackByOperation.get(operationId)} 条备用路径</em> : null}
              {next.length > 0 && <span><ArrowRight />{next.join(', ')}</span>}
            </div>
          )
        })}
      </div>
    </div>
  )
}

function McpSourceEditor({ flowId, tool, onSaved }: { flowId: string; tool: StudioToolResource; onSaved: () => Promise<void> }) {
  const nodeId = String(tool.node_id || '').trim()
  const [data, setData] = useState<McpSourceResponse | null>(null)
  const [graphText, setGraphText] = useState('')
  const [operationText, setOperationText] = useState('{\n  "id": "new_operation",\n  "kind": "transform"\n}')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<{ text: string; tone: 'neutral' | 'success' | 'error' } | null>(null)
  if (tool.source !== 'cartridge_dlc' || !nodeId) return null

  const load = async () => {
    setBusy(true)
    try {
      const next = await fetchMcpSource(flowId, nodeId)
      setData(next)
      setGraphText(graphDraftFromSource(next))
      setMessage(null)
    } catch (error: any) {
      setMessage({ text: error.message || 'MCP 源码加载失败', tone: 'error' })
    } finally {
      setBusy(false)
    }
  }

  const saveGraph = async () => {
    if (!data?.source_digest) return
    setBusy(true)
    try {
      const graph = JSON.parse(graphText)
      const result = await patchMcpOperationGraph(flowId, nodeId, data.source_digest, graph)
      const next = { node_id: nodeId, path: data.path, source: result.source, source_digest: result.source_digest, source_model: result.source_model }
      setData(next)
      setGraphText(graphDraftFromSource(next))
      await onSaved()
      setMessage({ text: 'MCP 内部流程已保存，源码指纹已同步更新。', tone: 'success' })
    } catch (error: any) {
      setMessage({ text: error.message || 'MCP 内部流程保存失败', tone: 'error' })
    } finally {
      setBusy(false)
    }
  }

  const createOperation = async () => {
    if (!data?.source_digest) return
    setBusy(true)
    try {
      const operation = JSON.parse(operationText)
      const result = await addMcpOperation(flowId, nodeId, data.source_digest, operation)
      const next = { node_id: nodeId, path: data.path, source: result.source, source_digest: result.source_digest, source_model: result.source_model }
      setData(next)
      setGraphText(graphDraftFromSource(next))
      setOperationText('{\n  "id": "new_operation",\n  "kind": "transform"\n}')
      await onSaved()
      setMessage({ text: '已新增 MCP 操作，源码指纹已同步更新。', tone: 'success' })
    } catch (error: any) {
      setMessage({ text: error.message || '新增 MCP 操作失败', tone: 'error' })
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="cf-builtin-tool-detail">
      <b>MCP 源码与内部流程（v0.9）</b>
      <p>透明度：<code>{tool.transparency || 'unknown'}</code> · 解析状态：<code>{tool.parse_status || 'unknown'}</code> · 操作数：<code>{tool.operation_count || 0}</code></p>
      <McpOperationGraphPreview tool={tool} data={data} />
      {!data ? (
        <button type="button" disabled={busy} onClick={() => void load()}><FileJson />读取源码模型</button>
      ) : (
        <>
          <p>源码位置：<code>{data.path}</code></p>
          <p>源码指纹：<code>{data.source_digest}</code></p>
          <label className="wide"><span>内部流程 JSON</span><textarea rows={10} value={graphText} onChange={(event) => setGraphText(event.target.value)} /></label>
          <div className="cf-resource-card-actions">
            <button type="button" disabled={busy} onClick={() => void load()}><RefreshCw />重新读取</button>
            <button className="primary" type="button" disabled={busy} onClick={() => void saveGraph()}><Workflow />保存流程</button>
          </div>
          <label className="wide"><span>新增操作 JSON</span><textarea rows={4} value={operationText} onChange={(event) => setOperationText(event.target.value)} /></label>
          <div className="cf-resource-card-actions">
            <button type="button" disabled={busy} onClick={() => void createOperation()}><CirclePlus />新增操作</button>
          </div>
          <details><summary>源码预览</summary><pre>{data.source}</pre></details>
        </>
      )}
      {message && <StatusMessage {...message} />}
    </section>
  )
}

export function ToolManagementPanel({ flowId, onFlowToolsChange }: { flowId: string; onFlowToolsChange?: (tools: McpTool[]) => void }) {
  const [resources, setResources] = useState<StudioResources>(EMPTY_RESOURCES)
  const [catalog, setCatalog] = useState<FlowResourceCatalog | null>(null)
  const [configuredKeys, setConfiguredKeys] = useState<Set<string>>(new Set())
  const [expandedId, setExpandedId] = useState('')
  const [draft, setDraft] = useState<ToolDraft>(toolDraft())
  const [filter, setFilter] = useState<'all' | 'selected' | 'unused'>('all')
  const [kind, setKind] = useState('all')
  const [query, setQuery] = useState('')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<{ text: string; tone: 'neutral' | 'success' | 'error' } | null>(null)
  const importRef = useRef<HTMLInputElement>(null)
  const initialExpansionRef = useRef(false)
  const selectedIds = (catalog?.tools || []).filter((tool) => tool.flow_binding?.bound).map((tool) => tool.id)
  const selectedSet = useMemo(() => new Set(selectedIds), [selectedIds])
  const allTools = useMemo(() => catalog?.tools || [], [catalog])
  const visibleTools = useMemo(() => allTools.filter((tool) => {
    if (filter === 'selected' && !selectedSet.has(tool.id)) return false
    if (filter === 'unused' && selectedSet.has(tool.id)) return false
    if (kind !== 'all' && tool.kind !== kind) return false
    const needle = query.trim().toLowerCase()
    return !needle || `${tool.name} ${tool.id} ${tool.description || ''}`.toLowerCase().includes(needle)
  }), [allTools, filter, kind, query, selectedSet])

  const reload = async () => {
    const [resourceData, environment, resourceCatalog] = await Promise.all([fetchStudioResources(), fetchStudioEnvironment(), fetchFlowResourceCatalog(flowId)])
    setResources(resourceData)
    setCatalog(resourceCatalog)
    setConfiguredKeys(new Set((environment.credentials || []).filter((item) => item.has_value).map((item) => item.key.toUpperCase())))
    onFlowToolsChange?.(resourceCatalog.tools.filter((tool) => tool.status === 'ready' && tool.manifest_requirement?.declared).map(toFlowMcpTool))
    if (!initialExpansionRef.current) {
      const first = resourceCatalog.tools[0]
      if (first) {
        initialExpansionRef.current = true
        setExpandedId(first.id)
        setDraft(toolDraft(first))
      }
    }
  }
  useEffect(() => { void reload().catch((error) => setMessage({ text: error.message, tone: 'error' })) }, [flowId])

  const persist = async (next: StudioResources) => {
    await saveStudioResources({ version: next.version || 1, tools: next.tools || [], bindings: next.bindings || { roles: {}, tools: {} }, builtin_tools: [] })
    await reload()
  }

  const toggleFlowTool = async (tool: StudioToolResource) => {
    if (tool.source !== 'local_resource') return
    const next: StudioResources = JSON.parse(JSON.stringify(resources))
    next.bindings ||= { roles: {}, tools: {} }
    next.bindings.tools ||= {}
    const values = new Set(next.bindings.tools[flowId] || [])
    const resourceId = tool.resource_id || tool.id
    if (values.has(resourceId)) values.delete(resourceId); else values.add(resourceId)
    if (values.size) next.bindings.tools[flowId] = [...values]; else delete next.bindings.tools[flowId]
    setBusy(true)
    try {
      await persist(next)
      setMessage({ text: values.has(resourceId) ? `${tool.name} 已加入当前 Flow。` : `${tool.name} 已从当前 Flow 移除。`, tone: 'success' })
    } catch (error: any) {
      setMessage({ text: error.message || '更新 Flow 工具名单失败', tone: 'error' })
    } finally {
      setBusy(false)
    }
  }

  const openTool = (tool: StudioToolResource) => {
    setExpandedId(expandedId === tool.id ? '' : tool.id)
    setDraft(toolDraft(tool))
    setMessage(null)
  }

  const saveTool = async () => {
    if (!draft.id.trim() || !draft.name.trim() || !draft.server.trim() || !draft.tool.trim()) {
      setMessage({ text: '连接 ID、名称、Server 和 Tool 不能为空。', tone: 'error' })
      return
    }
    setBusy(true)
    try {
      if (draft.apiKey.trim() && draft.authEnv.trim()) {
        await createStudioCredential({ key: draft.authEnv.trim().toUpperCase(), label: `${draft.name} API Key`, value: draft.apiKey, secret: true })
      }
      const item: StudioToolResource = {
        id: draft.id,
        name: draft.name,
        description: draft.description,
        kind: draft.kind,
        server: draft.server,
        tool: draft.tool,
        endpoint: draft.endpoint,
        command: draft.command,
        args: draft.args,
        openapi_url: draft.openapiUrl,
        http_method: draft.httpMethod,
        auth_env: draft.authEnv.trim().toUpperCase(),
        capabilities: [],
        read_only: draft.readOnly,
        package_mode: 'descriptor',
        enabled: draft.enabled,
      }
      const next = { ...resources, tools: [...resources.tools.filter((old) => old.id !== item.id), item] }
      await persist(next)
      setExpandedId(item.id)
      setDraft(toolDraft(item))
      setMessage({ text: '工具连接已保存在本机。', tone: 'success' })
    } catch (error: any) {
      setMessage({ text: error.message || '保存工具失败', tone: 'error' })
    } finally {
      setBusy(false)
    }
  }

  const deleteTool = async (tool: StudioToolResource) => {
    if (tool.locked || !window.confirm(`删除本机工具“${tool.name}”？`)) return
    const next: StudioResources = JSON.parse(JSON.stringify(resources))
    next.tools = next.tools.filter((item) => item.id !== tool.id)
    for (const owner of Object.keys(next.bindings.tools || {})) {
      next.bindings.tools![owner] = next.bindings.tools![owner].filter((id) => id !== tool.id)
      if (!next.bindings.tools![owner].length) delete next.bindings.tools![owner]
    }
    setBusy(true)
    try {
      await persist(next)
      setExpandedId('')
      setMessage({ text: '本机工具连接已删除。', tone: 'success' })
    } catch (error: any) {
      setMessage({ text: error.message || '删除失败', tone: 'error' })
    } finally {
      setBusy(false)
    }
  }

  const importTools = async (file?: File) => {
    if (!file) return
    setBusy(true)
    try {
      const parsed = JSON.parse(await file.text())
      const imported = Array.isArray(parsed) ? parsed : parsed.tools
      if (!Array.isArray(imported)) throw new Error('配置中没有 tools 数组。')
      const byId = new Map(resources.tools.map((tool) => [tool.id, tool]))
      for (const tool of imported) if (tool?.id) byId.set(String(tool.id), tool)
      await persist({ ...resources, tools: [...byId.values()] })
      setMessage({ text: `已导入 ${imported.length} 个工具配置。`, tone: 'success' })
    } catch (error: any) {
      setMessage({ text: error.message || '导入失败', tone: 'error' })
    } finally {
      setBusy(false)
      if (importRef.current) importRef.current.value = ''
    }
  }

  return (
    <div className="cf-resource-manager tool-manager">
      <div className="cf-resource-manager-actions">
        <button className="primary" type="button" onClick={() => importRef.current?.click()}><Upload />导入配置</button>
        <button type="button" onClick={() => downloadJson('cartridgeflow-tools.json', { version: resources.version, tools: resources.tools })}><Download />导出配置</button>
        <button type="button" onClick={() => { setExpandedId('__new__'); setDraft(toolDraft()); setMessage(null) }}><CirclePlus />新增工具</button>
        <input ref={importRef} type="file" accept="application/json,.json" hidden onChange={(event) => void importTools(event.target.files?.[0])} />
      </div>
      <div className="cf-resource-scope-note blue"><Info /><span>所有 Flow 共享本机工具源，但“加入当前 Flow”名单独立；运行时只向这个 Flow 暴露已选择工具。</span></div>
      <section className="cf-tool-filters">
        <header><b>当前 Flow 使用工具筛选</b><span>{selectedIds.length} 个已加入</span></header>
        <div className="cf-tool-filter-modes">
          <button className={filter === 'all' ? 'active' : ''} type="button" onClick={() => setFilter('all')}>全部工具</button>
          <button className={filter === 'selected' ? 'active' : ''} type="button" onClick={() => setFilter('selected')}><CheckCircle2 />当前 Flow 已使用</button>
          <button className={filter === 'unused' ? 'active' : ''} type="button" onClick={() => setFilter('unused')}>未使用工具</button>
        </div>
        <div className="cf-tool-filter-fields">
          <label>工具类型<select value={kind} onChange={(event) => setKind(event.target.value)}><option value="all">全部类型</option><option value="builtin">底座内置</option><option value="mcp">MCP</option><option value="remote_api">远程 API</option><option value="plugin">本机插件</option></select></label>
          <label className="search"><Search /><input value={query} placeholder="搜索名称、ID 或说明" onChange={(event) => setQuery(event.target.value)} /></label>
        </div>
      </section>
      {message && <StatusMessage {...message} />}
      <div className="cf-resource-list">
        {visibleTools.length === 0 && expandedId !== '__new__' && <div className="cf-resource-empty"><Wrench /><b>这个筛选下没有工具</b><span>可以更换筛选条件，或新增一个 MCP / 远程 API 工具。</span></div>}
        {[...(expandedId === '__new__' ? [{ id: '__new__', name: '新工具连接', kind: 'mcp' } as StudioToolResource] : []), ...visibleTools].map((tool) => {
          const expanded = expandedId === tool.id
          const selected = selectedSet.has(tool.id)
          const configured = tool.id !== '__new__' && toolConfigured(tool, configuredKeys)
          return <article key={tool.id} className={`cf-resource-card cf-tool-resource-card ${expanded ? 'expanded' : ''}`}>
            <div className="cf-resource-card-summary tool-summary">
              <button className="cf-tool-select" type="button" disabled={busy || tool.id === '__new__' || tool.source !== 'local_resource'} onClick={() => void toggleFlowTool(tool)} aria-label={selected ? '从当前 Flow 移除' : '加入当前 Flow'}><i className={selected ? 'checked' : ''}>{selected && <Check />}</i></button>
              <div className="cf-tool-summary-main">
                <span className={`cf-resource-status ${configured ? 'ok' : 'pending'}`}><i />{configured ? '配置完整' : tool.id === '__new__' ? '尚未保存' : '等待配置'}</span>
                <button className={`cf-resource-binding cf-tool-binding-action ${selected ? 'ok' : ''}`} type="button" disabled={busy || tool.id === '__new__' || tool.source !== 'local_resource'} onClick={() => void toggleFlowTool(tool)}>{selected ? <CheckCircle2 /> : <CirclePlus />}{selected ? '已加入当前 Flow' : '加入当前 Flow'}</button>
                {tool.id !== '__new__' && <button className="cf-tool-expand-action" type="button" onClick={() => openTool(tool)} title={expanded ? '收起工具配置' : '展开工具配置'}>{expanded ? <ChevronUp /> : <ChevronDown />}</button>}
                <button className="cf-tool-summary-copy" type="button" onClick={() => tool.id === '__new__' ? undefined : openTool(tool)}><strong>{tool.name}</strong><small>{tool.source ? `${tool.source} · ` : ''}{tool.description || `${tool.kind} · ${tool.id}`}</small></button>
              </div>
            </div>
            {expanded && (
              <div className="cf-resource-card-body">
                {tool.locked ? (
                  <section className="cf-builtin-tool-detail"><b>底座内置工具</b><p>连接 ID：<code>{tool.id}</code></p><p>执行入口：<code>{tool.server}/{tool.tool}</code></p><span>内置工具由底座提供，不包含外部密钥，也不能在这里修改。</span></section>
                ) : (
                  <div className="cf-resource-form">
                    <label><span>连接 ID</span><input value={draft.id} disabled={tool.id !== '__new__'} onChange={(event) => setDraft({ ...draft, id: event.target.value })} /></label>
                    <label><span>名称</span><input value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} /></label>
                    <label><span>工具类型</span><select value={draft.kind} onChange={(event) => setDraft({ ...draft, kind: event.target.value })}><option value="mcp">MCP</option><option value="remote_api">远程 API</option><option value="plugin">本机插件</option></select></label>
                    <label><span>Server</span><input value={draft.server} onChange={(event) => setDraft({ ...draft, server: event.target.value })} /></label>
                    <label><span>Tool</span><input value={draft.tool} onChange={(event) => setDraft({ ...draft, tool: event.target.value })} /></label>
                    <label><span>Endpoint</span><input value={draft.endpoint} placeholder="https://... 或留空使用本机命令" onChange={(event) => setDraft({ ...draft, endpoint: event.target.value })} /></label>
                    <label><span>本机命令</span><input value={draft.command} placeholder="npx / python / 可执行文件" onChange={(event) => setDraft({ ...draft, command: event.target.value })} /></label>
                    <label><span>命令参数</span><input value={draft.args} onChange={(event) => setDraft({ ...draft, args: event.target.value })} /></label>
                    <label><span>凭据变量</span><input value={draft.authEnv} placeholder="例如 DOCS_API_KEY" onChange={(event) => setDraft({ ...draft, authEnv: event.target.value.toUpperCase() })} /></label>
                    <label><span>API Key</span><input type="password" value={draft.apiKey} placeholder={draft.authEnv && configuredKeys.has(draft.authEnv) ? '已保存在本机' : '可选，仅保存在本机'} onChange={(event) => setDraft({ ...draft, apiKey: event.target.value })} /></label>
                    <label className="wide"><span>说明</span><textarea rows={2} value={draft.description} onChange={(event) => setDraft({ ...draft, description: event.target.value })} /></label>
                  </div>
                )}
                <McpSourceEditor flowId={flowId} tool={tool} onSaved={reload} />
                <div className="cf-resource-card-actions">
                  <button type="button" onClick={() => setMessage({ text: configured ? '本机连接字段与凭据检查通过。实际工具调用仍由运行节点触发。' : '连接配置不完整，请检查 Endpoint / 命令与凭据变量。', tone: configured ? 'success' : 'error' })}><Zap />检查配置</button>
                  {!tool.locked && tool.id !== '__new__' && <button className="danger" type="button" disabled={busy} onClick={() => void deleteTool(tool)}>删除工具</button>}
                  {!tool.locked && <button className="primary" type="button" disabled={busy} onClick={() => void saveTool()}>保存</button>}
                </div>
              </div>
            )}
          </article>
        })}
      </div>
      <p className="cf-resource-manager-foot"><Info />工具连接保存在本机；Flow 只记录允许使用的连接 ID，密钥不会进入卡带。</p>
    </div>
  )
}

type PackageResult = {
  filename: string
  url: string
  size: number
  package_mode: string
}

function formatPackageSize(size: number) {
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / 1024 / 1024).toFixed(1)} MB`
}

function downloadPackage(item: PackageResult) {
  const link = document.createElement('a')
  link.href = item.url
  link.download = item.filename
  document.body.appendChild(link)
  link.click()
  link.remove()
}

function preflightStatus(status?: string) {
  return status === 'ok' || status === 'ready' || status === 'passed'
}

export function PackagingPanel({ flowId }: { flowId: string }) {
  const [preflight, setPreflight] = useState<StudioReleasePreflight | null>(null)
  const [packages, setPackages] = useState<StudioPackageItem[]>([])
  const [loading, setLoading] = useState(true)
  const [packagingMode, setPackagingMode] = useState<'dev' | 'production' | null>(null)
  const [message, setMessage] = useState<{ text: string; tone: 'neutral' | 'success' | 'error' } | null>(null)

  const load = async () => {
    setLoading(true)
    try {
      const [nextPreflight, packageData] = await Promise.all([
        fetchStudioReleasePreflight(flowId),
        fetchStudioPackages(),
      ])
      setPreflight(nextPreflight)
      setPackages((packageData.items || []).filter((item) => item.cartridge_id === flowId))
      setMessage(null)
    } catch (error: any) {
      setMessage({ text: error.message || '读取打包预检失败。', tone: 'error' })
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void load() }, [flowId])

  const buildPackage = async (mode: 'dev' | 'production') => {
    setPackagingMode(mode)
    setMessage(null)
    try {
      const result = await packageCartridge(flowId, mode)
      const packageData = await fetchStudioPackages()
      setPackages((packageData.items || []).filter((item) => item.cartridge_id === flowId))
      setMessage({ text: `${mode === 'production' ? '生产包' : '开发包'}已生成：${result.filename}`, tone: 'success' })
      downloadPackage(result)
    } catch (error: any) {
      setMessage({ text: error.message || '生成卡带包失败。', tone: 'error' })
    } finally {
      setPackagingMode(null)
    }
  }

  const statusItems = preflight ? [
    { label: '包内容检查', ready: preflightStatus(preflight.package_hygiene.status), detail: `${preflight.package_hygiene.scanned_files || 0} 个文件` },
    { label: '可移植性', ready: preflightStatus(preflight.portability.status), detail: `${preflight.portability.summary?.local_rebind || 0} 项需本地重绑` },
    { label: '开发包', ready: preflight.dev_ready, detail: preflight.dev_ready ? '可以生成' : '存在阻断项' },
    { label: '生产包', ready: preflight.production_ready, detail: preflight.production_ready ? '可以生成' : '未达到生产门槛' },
  ] : []

  return (
    <div className="cf-resource-manager cf-package-manager">
      <div className="cf-package-heading">
        <div><PackageCheck /><span><strong>{preflight?.cartridge.name || '当前卡带'}</strong><small>{preflight ? `${preflight.cartridge.id} · v${preflight.cartridge.version}` : '正在读取发布信息'}</small></span></div>
        <button type="button" disabled={loading || Boolean(packagingMode)} onClick={() => void load()}><RefreshCw className={loading ? 'spinning' : ''} />刷新预检</button>
      </div>

      {message && <StatusMessage {...message} />}
      {loading && !preflight ? (
        <div className="cf-package-loading"><RefreshCw className="spinning" /><span>正在检查卡带文件、依赖、模型和资源配置…</span></div>
      ) : preflight ? (
        <>
          <div className="cf-package-status-grid">
            {statusItems.map((item) => <div key={item.label} className={item.ready ? 'ready' : 'blocked'}><i>{item.ready ? <CheckCircle2 /> : <X />}</i><span><b>{item.label}</b><small>{item.detail}</small></span></div>)}
          </div>

          <section className="cf-package-issues">
            <header><div><ShieldCheck /><strong>发布预检</strong></div><span>{preflight.issues.length ? `${preflight.issues.length} 个问题` : '全部通过'}</span></header>
            {preflight.issues.length ? (
              <div>{preflight.issues.map((issue, index) => <article key={`${issue.area}-${index}`}><span className={issue.severity}>{issue.severity === 'error' || issue.severity === 'blocker' ? '阻断' : '提醒'}</span><p><b>{issue.area}</b>{issue.message}</p></article>)}</div>
            ) : <p className="empty"><CheckCircle2 />当前卡带没有发现发布阻断项。</p>}
          </section>

          <div className="cf-package-actions">
            <div><strong>开发包</strong><span>保留开发态信息，用于交接、备份和继续编辑。</span><button type="button" disabled={!preflight.dev_ready || Boolean(packagingMode)} onClick={() => void buildPackage('dev')}><Download />{packagingMode === 'dev' ? '正在生成…' : '生成并下载开发包'}</button></div>
            <div><strong>生产包</strong><span>执行更严格的生产门槛检查，用于正式部署。</span><button className="primary" type="button" disabled={!preflight.production_ready || Boolean(packagingMode)} onClick={() => void buildPackage('production')}><PackageCheck />{packagingMode === 'production' ? '正在生成…' : '生成并下载生产包'}</button></div>
          </div>

          <section className="cf-package-history">
            <header><strong>本卡带打包历史</strong><span>{packages.length} 个包</span></header>
            {packages.length ? packages.slice(0, 8).map((item) => (
              <article key={`${item.filename}-${item.modified_at}`}>
                <PackageCheck />
                <span><b>{item.filename}</b><small>{item.package_mode === 'production' ? '生产包' : '开发包'} · {formatPackageSize(item.size)} · {new Date(item.modified_at).toLocaleString('zh-CN')}</small></span>
                <button type="button" onClick={() => downloadPackage(item)} title={`下载 ${item.filename}`}><Download /><span>下载</span></button>
              </article>
            )) : <p className="empty">当前卡带还没有生成过安装包。</p>}
          </section>
        </>
      ) : null}
      <p className="cf-resource-manager-foot"><Info />包内不会写入本机保存的 API Key；部署到其他环境后，需要按预检报告重新绑定本地凭据。</p>
    </div>
  )
}
