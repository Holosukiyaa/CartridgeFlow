import { useEffect, useMemo, useRef, useState } from 'react'
import {
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  CirclePlus,
  Copy,
  Download,
  FileJson,
  Info,
  Search,
  Upload,
  Wrench,
  X,
  Zap,
} from 'lucide-react'
import {
  createLlmProvider,
  createStudioCredential,
  deleteLlmProvider,
  exportLlmConfig,
  fetchLlmAssignments,
  fetchLlmProviders,
  fetchStudioEnvironment,
  fetchStudioResources,
  importOpenCodeConfig,
  saveLlmAssignments,
  saveStudioResources,
  testLlmProvider,
  updateLlmProvider,
  type CartridgeDetail,
  type LlmAssignments,
  type LlmProvider,
  type McpTool,
  type StudioResources,
  type StudioToolResource,
} from '../../api.ts'

type ModelRole = { id: string; label: string; model?: string }
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
    return id ? [{ id, label: String(item?.label || id), model: String(item?.model || '') }] : []
  })
  return normalized.length ? normalized : [{ id: 'runtime', label: '默认运行模型' }]
}

function StatusMessage({ text, tone = 'neutral' }: { text: string; tone?: 'neutral' | 'success' | 'error' }) {
  return <div className={`cf-resource-feedback ${tone}`}>{tone === 'success' ? <CheckCircle2 /> : tone === 'error' ? <X /> : <Info />}<span>{text}</span></div>
}

export function ModelManagementPanel({ flowId, cartridge }: { flowId: string; cartridge: CartridgeDetail }) {
  const [providers, setProviders] = useState<LlmProvider[]>([])
  const [assignments, setAssignments] = useState<LlmAssignments>(EMPTY_ASSIGNMENTS)
  const [expandedId, setExpandedId] = useState('')
  const [draft, setDraft] = useState<ProviderDraft>(providerDraft())
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<{ text: string; tone: 'neutral' | 'success' | 'error' } | null>(null)
  const importRef = useRef<HTMLInputElement>(null)
  const initialExpansionRef = useRef(false)
  const roles = useMemo(() => flowModelRoles(cartridge), [cartridge])
  const flowBindings = assignments.cartridges?.[flowId] || {}

  const reload = async () => {
    const [providerData, assignmentData] = await Promise.all([fetchLlmProviders(), fetchLlmAssignments()])
    const nextProviders = providerData.providers || []
    setProviders(nextProviders)
    setAssignments(assignmentData || EMPTY_ASSIGNMENTS)
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

  const bindRole = async (role: ModelRole, provider: LlmProvider) => {
    const next: LlmAssignments = JSON.parse(JSON.stringify(assignments || EMPTY_ASSIGNMENTS))
    next.cartridges ||= {}
    next.cartridges[flowId] ||= {}
    const current = next.cartridges[flowId][role.id]
    if (current?.provider_id === provider.id) delete next.cartridges[flowId][role.id]
    else next.cartridges[flowId][role.id] = { provider_id: provider.id, model: draft.model || provider.default_model || role.model || '' }
    if (Object.keys(next.cartridges[flowId]).length === 0) delete next.cartridges[flowId]
    setBusy(true)
    try {
      const result = await saveLlmAssignments(next)
      setAssignments(result.assignments)
      setMessage({ text: current?.provider_id === provider.id ? `${role.label} 已恢复使用全局默认连接。` : `${role.label} 已绑定连接 ID：${provider.id}`, tone: 'success' })
    } catch (error: any) {
      setMessage({ text: error.message || '绑定失败', tone: 'error' })
    } finally {
      setBusy(false)
    }
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
        <button className="primary" type="button" onClick={() => importRef.current?.click()}><Upload />导入配置</button>
        <button type="button" onClick={async () => downloadJson('cartridgeflow-models.json', await exportLlmConfig())}><Download />导出配置</button>
        <button type="button" onClick={startNew}><CirclePlus />新增连接</button>
        <input ref={importRef} type="file" accept="application/json,.json" hidden onChange={(event) => void importConfig(event.target.files?.[0])} />
      </div>
      <div className="cf-resource-scope-note"><Info /><span>模型连接由底座统一保管；当前 Flow 只保存连接 ID 与模型角色，不会写入 API Key。</span></div>
      {message && <StatusMessage {...message} />}
      <div className="cf-resource-list">
        {providers.length === 0 && expandedId !== '__new__' && <div className="cf-resource-empty"><FileJson /><b>还没有模型连接</b><span>导入 OpenCode 配置，或手动新增一个 OpenAI 兼容连接。</span></div>}
        {[...(expandedId === '__new__' ? [{ id: '__new__', name: '新模型连接' } as LlmProvider] : []), ...providers].map((provider) => {
          const expanded = expandedId === provider.id
          const boundRoles = roles.filter((role) => flowBindings[role.id]?.provider_id === provider.id)
          const tested = provider.id === '__new__' ? false : provider.tested_ok
          return (
            <article key={provider.id} className={`cf-resource-card ${expanded ? 'expanded' : ''}`}>
              <button className="cf-resource-card-summary" type="button" onClick={() => provider.id === '__new__' ? undefined : openProvider(provider)}>
                <span className={`cf-resource-status ${tested ? 'ok' : 'pending'}`}><i />{tested ? '连接成功' : provider.id === '__new__' ? '尚未保存' : '等待测试'}</span>
                <span className={`cf-resource-binding ${boundRoles.length ? 'ok' : ''}`}>{boundRoles.length ? <CheckCircle2 /> : <Info />}{boundRoles.length ? `已绑定 ${boundRoles.length} 个角色` : '未绑定当前 Flow'}</span>
                {provider.id !== '__new__' && (expanded ? <ChevronUp /> : <ChevronDown />)}
                <strong>{provider.name}</strong>
                <small>{provider.id === '__new__' ? '填写连接信息后会生成稳定连接 ID' : `连接 ID：${provider.id}`}</small>
              </button>
              {expanded && (
                <div className="cf-resource-card-body">
                  <section className="cf-resource-flow-bindings">
                    <header><div><b>当前 Flow 模型角色</b><span>每个角色可以使用不同连接；打包时只携带角色与连接 ID。</span></div></header>
                    {roles.map((role) => {
                      const binding = flowBindings[role.id]
                      const selected = binding?.provider_id === provider.id
                      return <div key={role.id}><span><b>{role.label}</b><code>{role.id}</code></span><em>{selected ? binding.model || provider.default_model : binding?.provider_id ? `当前：${binding.provider_id}` : '使用全局默认'}</em><button className={selected ? 'selected' : ''} type="button" disabled={busy || provider.id === '__new__'} onClick={() => void bindRole(role, provider)}>{selected ? <><Check />已绑定</> : '使用此连接'}</button></div>
                    })}
                  </section>
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
                    <button className="primary" type="button" disabled={busy} onClick={() => void saveProvider()}>保存</button>
                  </div>
                </div>
              )}
            </article>
          )
        })}
      </div>
      <p className="cf-resource-manager-foot"><Info />连接 ID 是 Flow 的本地插座编号；换机器后只需用同名 ID 重新接上模型。</p>
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
  if (tool.kind === 'builtin') return true
  const transportReady = tool.kind === 'remote_api' ? Boolean(tool.endpoint || tool.openapi_url) : Boolean(tool.endpoint || tool.command)
  return transportReady && (!tool.auth_env || configuredKeys.has(tool.auth_env.toUpperCase()))
}

function toFlowMcpTool(tool: StudioToolResource): McpTool {
  return {
    id: tool.id,
    name: tool.name,
    type: 'builtin',
    server: tool.server || tool.id,
    tool: tool.tool || tool.id,
    description: tool.description,
    enabled: tool.enabled !== false,
  }
}

export function ToolManagementPanel({ flowId, onFlowToolsChange }: { flowId: string; onFlowToolsChange?: (tools: McpTool[]) => void }) {
  const [resources, setResources] = useState<StudioResources>(EMPTY_RESOURCES)
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
  const selectedIds = resources.bindings.tools?.[flowId] || []
  const selectedSet = useMemo(() => new Set(selectedIds), [selectedIds])
  const allTools = useMemo(() => [...(resources.builtin_tools || []), ...(resources.tools || [])], [resources])
  const visibleTools = useMemo(() => allTools.filter((tool) => {
    if (filter === 'selected' && !selectedSet.has(tool.id)) return false
    if (filter === 'unused' && selectedSet.has(tool.id)) return false
    if (kind !== 'all' && tool.kind !== kind) return false
    const needle = query.trim().toLowerCase()
    return !needle || `${tool.name} ${tool.id} ${tool.description || ''}`.toLowerCase().includes(needle)
  }), [allTools, filter, kind, query, selectedSet])

  const reload = async () => {
    const [resourceData, environment] = await Promise.all([fetchStudioResources(), fetchStudioEnvironment()])
    setResources(resourceData)
    setConfiguredKeys(new Set((environment.credentials || []).filter((item) => item.has_value).map((item) => item.key.toUpperCase())))
    const selected = new Set(resourceData.bindings.tools?.[flowId] || [])
    onFlowToolsChange?.([...(resourceData.builtin_tools || []), ...(resourceData.tools || [])].filter((tool) => selected.has(tool.id)).map(toFlowMcpTool))
    if (!initialExpansionRef.current) {
      const first = [...(resourceData.builtin_tools || []), ...(resourceData.tools || [])][0]
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
    const next: StudioResources = JSON.parse(JSON.stringify(resources))
    next.bindings ||= { roles: {}, tools: {} }
    next.bindings.tools ||= {}
    const values = new Set(next.bindings.tools[flowId] || [])
    if (values.has(tool.id)) values.delete(tool.id); else values.add(tool.id)
    if (values.size) next.bindings.tools[flowId] = [...values]; else delete next.bindings.tools[flowId]
    setBusy(true)
    try {
      await persist(next)
      setMessage({ text: values.has(tool.id) ? `${tool.name} 已加入当前 Flow。` : `${tool.name} 已从当前 Flow 移除。`, tone: 'success' })
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
          return <article key={tool.id} className={`cf-resource-card ${expanded ? 'expanded' : ''}`}>
            <div className="cf-resource-card-summary tool-summary">
              <button className="cf-tool-select" type="button" disabled={busy || tool.id === '__new__'} onClick={() => void toggleFlowTool(tool)} aria-label={selected ? '从当前 Flow 移除' : '加入当前 Flow'}><i className={selected ? 'checked' : ''}>{selected && <Check />}</i></button>
              <button className="cf-tool-summary-main" type="button" onClick={() => tool.id === '__new__' ? undefined : openTool(tool)}>
                <span className={`cf-resource-status ${configured ? 'ok' : 'pending'}`}><i />{configured ? '配置完整' : tool.id === '__new__' ? '尚未保存' : '等待配置'}</span>
                <span className={`cf-resource-binding ${selected ? 'ok' : ''}`}>{selected ? <CheckCircle2 /> : <CirclePlus />}{selected ? '已加入当前 Flow' : '加入当前 Flow'}</span>
                {tool.id !== '__new__' && (expanded ? <ChevronUp /> : <ChevronDown />)}
                <strong>{tool.name}</strong>
                <small>{tool.description || `${tool.kind} · ${tool.id}`}</small>
              </button>
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
