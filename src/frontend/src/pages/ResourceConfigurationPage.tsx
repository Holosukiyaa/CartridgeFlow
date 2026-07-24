import { useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  activateLlmProvider,
  createLlmProvider,
  createStudioCredential,
  deleteLlmProvider,
  detectLlmProvider,
  exportLlmConfig,
  fetchLabFlows,
  fetchLlmAssignments,
  fetchLlmProviders,
  fetchStudioEnvironment,
  fetchStudioResources,
  importOpenCodeConfig,
  saveLlmAssignments,
  saveStudioResources,
  testLlmProvider,
  updateLlmProvider,
  type CartridgeSummary,
  type LlmAssignments,
  type LlmDetectionResult,
  type LlmProvider,
  type ResourceRequirement,
  type StudioEnvironmentSnapshot,
  type StudioResources,
  type StudioToolResource,
} from '../api.ts'
import ConfigModal from '../components/ConfigModal.tsx'
import { getRoleReadiness, normalizeRecipeRoles, providerRoleCompatibilityIssue, type LlmRecipeRole } from '../llmRecipe.ts'

type ResourceKind = 'model' | 'tool'
type EditorTab = 'connection' | 'assignments' | 'usage'
type PendingTarget =
  | { kind: 'model'; flow: CartridgeSummary; role: LlmRecipeRole }
  | { kind: 'tool'; flow: CartridgeSummary; requirement: ResourceRequirement }

type ProviderDraft = {
  id: string
  name: string
  api_type: string
  base_url: string
  api_key: string
  default_model: string
  wire_api: string
  capabilities: string[]
  available_models: string[]
  adapter_profile: string
  enabled: boolean
  timeout: string
}

const EMPTY_PROVIDER: ProviderDraft = {
  id: '', name: '', api_type: 'openai', base_url: '', api_key: '', default_model: '',
  wire_api: 'chat_completions', capabilities: ['text_reasoning'], available_models: [], adapter_profile: 'standard', enabled: false, timeout: '120',
}
const EMPTY_TOOL: StudioToolResource = {
  id: '', name: '', kind: 'remote_api', description: '', endpoint: '', command: '', args: '',
  openapi_url: '', http_method: 'POST', auth_env: '', auth_header: 'Authorization',
  auth_scheme: 'Bearer', capabilities: [], read_only: false, package_mode: 'descriptor', enabled: true,
}
const API_TYPES = [{ value: 'openai', label: 'OpenAI Compatible' }]
const WIRE_APIS = [
  { value: 'chat_completions', label: 'Chat Completions' },
  { value: 'responses', label: 'Responses' },
]
const TOOL_KINDS = [
  { value: 'remote_api', label: '远程 HTTP / OpenAPI' },
  { value: 'mcp', label: 'MCP 服务' },
  { value: 'plugin', label: 'CLI / 底座插件' },
]

function providerDraft(provider: LlmProvider): ProviderDraft {
  return {
    id: provider.id,
    name: provider.name,
    api_type: provider.api_type || 'openai',
    base_url: provider.base_url || '',
    api_key: '',
    default_model: provider.default_model || '',
    wire_api: provider.wire_api || 'chat_completions',
    capabilities: provider.capabilities || ['text_reasoning'],
    available_models: provider.available_models || [],
    adapter_profile: 'standard',
    enabled: provider.enabled !== false,
    timeout: String(provider.timeout || 120),
  }
}

function providerState(provider: LlmProvider) {
  if (provider.runtime_supported === false) return { key: 'unsupported', label: '协议不支持' }
  if (provider.tested_ok) return { key: 'verified', label: '连接正常' }
  if (provider.base_url && provider.has_key && provider.default_model) return { key: 'pending', label: '等待测试' }
  return { key: 'incomplete', label: '信息不完整' }
}

function savedProviderDetection(provider: LlmProvider): LlmDetectionResult['detection'] | null {
  const models = provider.available_models || []
  if (!models.length) return null
  return {
    capability: provider.capabilities?.[0] || 'text_reasoning',
    adapter_label: '普通文本模型',
    confidence: 'high',
    model_count: models.length,
    models,
    models_endpoint: '',
    summary: `已识别为普通文本模型，默认使用 ${provider.default_model || models[0]}`,
  }
}

function providerModelOptions(provider: LlmProvider): string[] {
  return Array.from(new Set([provider.default_model, ...(provider.available_models || [])].filter((model): model is string => Boolean(model))))
}

function toolKindLabel(tool: StudioToolResource) {
  if (tool.kind === 'remote_api') return '远程 API'
  if (tool.kind === 'mcp') return 'MCP'
  if (tool.kind === 'builtin') return '底座内置'
  return '底座插件'
}

function normalizeKind(kind: string) {
  return ({ remote: 'remote_api', web: 'remote_api', structured: 'remote_api', local_path: 'plugin' } as Record<string, string>)[kind] || kind
}

function toolMatches(item: StudioToolResource, requirement: ResourceRequirement) {
  const accepted = new Set((requirement.kinds || []).map(normalizeKind))
  if (accepted.size && !accepted.has(normalizeKind(item.kind || ''))) return false
  const capabilities = new Set(item.capabilities || [])
  if ((requirement.capabilities || []).some((capability) => !capabilities.has(capability))) return false
  return requirement.constraints?.read_only !== true || item.read_only === true
}

function copyAssignments(value: LlmAssignments): LlmAssignments {
  return {
    version: value.version || 1,
    defaults: { ...(value.defaults || {}) },
    cartridges: Object.fromEntries(Object.entries(value.cartridges || {}).map(([id, roles]) => [id, { ...roles }])),
    nodes: Object.fromEntries(Object.entries(value.nodes || {}).map(([id, roles]) => [id, { ...roles }])),
  }
}

function copyBindings(resources: StudioResources) {
  return {
    roles: Object.fromEntries(Object.entries(resources.bindings.roles || {}).map(([id, roles]) => [id, { ...roles }])),
    tools: Object.fromEntries(Object.entries(resources.bindings.tools || {}).map(([id, values]) => [id, [...values]])),
  }
}

export default function ResourceConfigurationPage({ embedded = false, onChanged }: { embedded?: boolean; onChanged?: () => void | Promise<void> }) {
  const [searchParams] = useSearchParams()
  const deepLinkHandled = useRef(false)
  const importInputRef = useRef<HTMLInputElement>(null)
  const [providers, setProviders] = useState<LlmProvider[]>([])
  const [assignments, setAssignments] = useState<LlmAssignments | null>(null)
  const [resources, setResources] = useState<StudioResources | null>(null)
  const [environment, setEnvironment] = useState<StudioEnvironmentSnapshot | null>(null)
  const [flows, setFlows] = useState<CartridgeSummary[]>([])
  const [editorKind, setEditorKind] = useState<ResourceKind | ''>('')
  const [editorTab, setEditorTab] = useState<EditorTab>('connection')
  const [selectedProviderId, setSelectedProviderId] = useState('')
  const [selectedToolId, setSelectedToolId] = useState('')
  const [providerForm, setProviderForm] = useState<ProviderDraft>(EMPTY_PROVIDER)
  const [toolForm, setToolForm] = useState<StudioToolResource>({ ...EMPTY_TOOL })
  const [toolCredential, setToolCredential] = useState('')
  const [pendingTarget, setPendingTarget] = useState<PendingTarget | null>(null)
  const [pendingModels, setPendingModels] = useState<Record<string, string>>({})
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [detecting, setDetecting] = useState(false)
  const [providerDetection, setProviderDetection] = useState<LlmDetectionResult['detection'] | null>(null)
  const [configBusy, setConfigBusy] = useState<'import' | 'export' | ''>('')
  const [createOpen, setCreateOpen] = useState(false)
  const [importOpen, setImportOpen] = useState(false)
  const [importText, setImportText] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const selectedProvider = providers.find((item) => item.id === selectedProviderId)
  const selectedTool = resources?.tools.find((item) => item.id === selectedToolId)
  const selectedCredential = environment?.credentials.find((item) => item.key === selectedTool?.auth_env)
  const modelTargets = useMemo(
    () => flows.flatMap((flow) => normalizeRecipeRoles(flow.llm_recipe).map((role) => ({ flow, role }))),
    [flows],
  )
  const toolTargets = useMemo(
    () => flows.flatMap((flow) => (flow.resource_requirements || []).map((requirement) => ({ flow, requirement }))),
    [flows],
  )

  async function load() {
    setLoading(true)
    setError('')
    try {
      const [providerResult, assignmentResult, resourceResult, environmentResult, flowResult] = await Promise.all([
        fetchLlmProviders(),
        fetchLlmAssignments(),
        fetchStudioResources(),
        fetchStudioEnvironment(),
        fetchLabFlows(),
      ])
      setProviders(providerResult.providers || [])
      setAssignments(assignmentResult)
      setResources(resourceResult)
      setEnvironment(environmentResult)
      setFlows(flowResult.items || [])
    } catch (reason: any) {
      setError(reason?.message || '读取资源配置失败')
    } finally {
      setLoading(false)
    }
  }

  async function notifyChanged() {
    try {
      await onChanged?.()
    } catch {
      // The embedded workspace remains usable even if its parent refresh fails.
    }
  }

  async function refreshAfterMutation() {
    await load()
    await notifyChanged()
  }

  useEffect(() => { void load() }, [])

  useEffect(() => {
    if (loading || deepLinkHandled.current) return
    deepLinkHandled.current = true
    const register = searchParams.get('register')
    const importMode = searchParams.get('import')
    const kind = searchParams.get('kind')
    const resourceId = searchParams.get('resource') || ''
    const requestedTab = searchParams.get('tab') === 'assignments' ? 'assignments' : searchParams.get('tab') === 'usage' ? 'usage' : 'connection'
    const target = searchParams.get('target') || ''
    if (importMode === 'opencode') { setImportOpen(true); return }
    if (register === 'model') { setCreateOpen(true); return }
    if (register === 'tool') { startNewTool(); return }
    if (kind === 'model' && resourceId) {
      const provider = providers.find((item) => item.id === resourceId)
      if (provider) openProvider(provider, requestedTab)
    }
    if (kind === 'tool' && resourceId) {
      const tool = resources?.tools.find((item) => item.id === resourceId)
      if (tool) openTool(tool, requestedTab)
    }
    if (kind === 'tool' && !resourceId) window.requestAnimationFrame(() => document.getElementById('resource-tools')?.scrollIntoView({ block: 'start' }))
    if (target) {
      const [targetKind, flowId, roleId] = target.split(':')
      const flow = flows.find((item) => item.id === flowId)
      if (targetKind === 'model' && flow) {
        const role = normalizeRecipeRoles(flow.llm_recipe).find((item) => item.id === roleId)
        if (role) setPendingTarget({ kind: 'model', flow, role })
      }
      if (targetKind === 'tool' && flow) {
        const requirement = (flow.resource_requirements || []).find((item) => item.role === roleId)
        if (requirement) setPendingTarget({ kind: 'tool', flow, requirement })
      }
    }
  }, [flows, loading, providers, resources, searchParams])

  function closeEditor() {
    setEditorKind('')
    setEditorTab('connection')
    setToolCredential('')
    setError('')
    setNotice('')
    setProviderDetection(null)
  }

  function startNewProvider(keepPending = false) {
    if (!keepPending) setPendingTarget(null)
    setCreateOpen(false)
    setSelectedProviderId('')
    setProviderForm({ ...EMPTY_PROVIDER })
    setEditorKind('model')
    setEditorTab('connection')
    setError('')
    setNotice('')
    setProviderDetection(null)
  }

  function openProvider(provider: LlmProvider, tab: EditorTab = 'connection') {
    setSelectedProviderId(provider.id)
    setProviderForm(providerDraft(provider))
    setEditorKind('model')
    setEditorTab(tab)
    setError('')
    setNotice('')
    setProviderDetection(savedProviderDetection(provider))
  }

  function startNewTool(keepPending = false) {
    if (!keepPending) setPendingTarget(null)
    setSelectedToolId('')
    setToolForm({ ...EMPTY_TOOL })
    setToolCredential('')
    setEditorKind('tool')
    setEditorTab('connection')
    setError('')
    setNotice('')
  }

  function openTool(tool: StudioToolResource, tab: EditorTab = 'connection') {
    setSelectedToolId(tool.id)
    setToolForm({ ...tool })
    setToolCredential('')
    setEditorKind('tool')
    setEditorTab(tab)
    setError('')
    setNotice('')
  }

  function openModelTarget(flow: CartridgeSummary, role: LlmRecipeRole) {
    setPendingModels({})
    setPendingTarget({ kind: 'model', flow, role })
    setEditorKind('')
  }

  async function bindModelTarget(flow: CartridgeSummary, role: LlmRecipeRole, providerId: string, providerOverride?: LlmProvider, modelOverride = '') {
    if (!assignments) return
    const provider = providerOverride || providers.find((item) => item.id === providerId)
    if (provider) {
      const issue = providerRoleCompatibilityIssue(role, provider)
      if (issue) { setError(issue); return }
    }
    const next = copyAssignments(assignments)
    const roles = { ...(next.cartridges[flow.id] || {}) }
    const fixedModel = role.model && role.model !== 'configured-locally' ? role.model : ''
    const selectedModel = fixedModel || modelOverride || provider?.default_model || ''
    if (providerId) roles[role.id] = { provider_id: providerId, model: selectedModel }
    else delete roles[role.id]
    if (Object.keys(roles).length) next.cartridges[flow.id] = roles
    else delete next.cartridges[flow.id]
    try {
      const result = await saveLlmAssignments(next)
      setAssignments(result.assignments)
      setError('')
      setNotice(providerId ? `已为 ${flow.name} / ${role.label} 分配 ${provider?.name || '模型连接'} · ${selectedModel}` : `已解除 ${flow.name} / ${role.label} 的分配`)
      await notifyChanged()
    } catch (reason: any) {
      setError(reason?.message || '保存模型分配失败')
    }
  }

  async function bindToolTarget(flow: CartridgeSummary, requirement: ResourceRequirement, toolId: string, toolOverride?: StudioToolResource, resourcesOverride?: StudioResources) {
    const sourceResources = resourcesOverride || resources
    if (!sourceResources) return
    const tool = toolOverride || sourceResources.tools.find((item) => item.id === toolId)
    if (tool && !toolMatches(tool, requirement)) { setError('这个工具不符合卡带角色的类型或能力要求'); return }
    const bindings = copyBindings(sourceResources)
    const roles = { ...(bindings.roles[flow.id] || {}) }
    if (toolId) roles[requirement.role] = toolId
    else delete roles[requirement.role]
    if (Object.keys(roles).length) bindings.roles[flow.id] = roles
    else delete bindings.roles[flow.id]
    try {
      const result = await saveStudioResources({ version: 1, tools: sourceResources.tools, bindings, builtin_tools: [] })
      setResources({ ...result.resources, builtin_tools: sourceResources.builtin_tools })
      setError('')
      setNotice(toolId ? `已为 ${flow.name} / ${requirement.role} 分配工具连接` : `已解除 ${flow.name} / ${requirement.role} 的分配`)
      await notifyChanged()
    } catch (reason: any) {
      setError(reason?.message || '保存工具分配失败')
    }
  }

  async function saveProvider(event: React.FormEvent) {
    event.preventDefault()
    if (!providerForm.name.trim()) { setError('请填写连接名称'); return }
    if (!providerForm.base_url.trim()) { setError('请填写模型服务 URL'); return }
    if (!providerForm.default_model.trim()) { setError('请填写默认模型标识'); return }
    setSaving(true)
    setError('')
    try {
      const payload = {
        id: providerForm.id,
        name: providerForm.name.trim(),
        api_type: providerForm.api_type,
        base_url: providerForm.base_url.trim(),
        api_key: providerForm.api_key,
        default_model: providerForm.default_model.trim(),
        wire_api: providerForm.wire_api,
        capabilities: providerForm.capabilities,
        available_models: providerForm.available_models,
        adapter_profile: 'standard',
        enabled: providerForm.enabled,
        timeout: Number(providerForm.timeout) || 120,
      }
      const result = providerForm.id ? await updateLlmProvider(providerForm.id, payload) : await createLlmProvider(payload)
      setSelectedProviderId(result.provider.id)
      setProviderForm(providerDraft(result.provider))
      if (pendingTarget?.kind === 'model') {
        await bindModelTarget(pendingTarget.flow, pendingTarget.role, result.provider.id, result.provider)
        setPendingTarget(null)
      }
      setNotice(providerForm.id ? '模型 API 连接已更新' : '模型 API 连接已创建')
      await refreshAfterMutation()
    } catch (reason: any) {
      setError(reason?.message || '保存模型 API 连接失败')
    } finally {
      setSaving(false)
    }
  }

  async function removeProvider() {
    if (!selectedProvider || !window.confirm(`删除模型 API 连接“${selectedProvider.name}”？\n\n关联分配会同时解除。`)) return
    const providerId = selectedProvider.id
    try {
      await deleteLlmProvider(providerId)
      setProviders((current) => current.filter((item) => item.id !== providerId))
      closeEditor()
      setNotice('模型 API 连接已删除')
      await refreshAfterMutation()
    } catch (reason: any) {
      setError(reason?.message || '删除模型 API 连接失败')
    }
  }

  async function activateProvider() {
    if (!selectedProvider) return
    try {
      const result = await activateLlmProvider(selectedProvider.id)
      setProviderForm(providerDraft(result.provider))
      setNotice('默认模型连接已切换')
      await refreshAfterMutation()
    } catch (reason: any) {
      setError(reason?.message || '切换默认模型连接失败')
    }
  }

  async function testProvider() {
    if (!selectedProvider) return
    setTesting(true)
    setError('')
    setNotice('')
    try {
      const result = await testLlmProvider(selectedProvider.id, selectedProvider.default_model)
      if (!result.ok) throw new Error(result.error || '模型服务没有通过连接测试')
      setNotice('模型 API 连接测试通过')
      await refreshAfterMutation()
    } catch (reason: any) {
      setNotice('')
      setError(reason?.message || '模型 API 连接测试失败')
    } finally {
      setTesting(false)
    }
  }

  async function detectProvider() {
    if (!providerForm.base_url.trim()) { setError('请填写模型服务 URL'); return }
    if (!providerForm.api_key.trim() && !selectedProvider?.has_key) { setError('请填写 API Key'); return }
    setDetecting(true)
    setError('')
    setNotice('')
    try {
      const result = await detectLlmProvider({
        provider_id: selectedProviderId,
        base_url: providerForm.base_url.trim(),
        api_key: providerForm.api_key,
        preferred_model: providerForm.default_model,
      })
      const detected = result.provider
      setProviderForm((current) => ({
        ...current,
        name: current.name.trim() || detected.name,
        api_type: detected.api_type,
        base_url: detected.base_url,
        default_model: detected.default_model,
        wire_api: detected.wire_api,
        capabilities: detected.capabilities,
        available_models: result.detection.models,
        adapter_profile: 'standard',
        timeout: String(detected.timeout),
      }))
      setProviderDetection(result.detection)
      setNotice(result.detection.summary)
    } catch (reason: any) {
      setProviderDetection(null)
      setError(reason?.message || '模型连接自动检测失败')
    } finally {
      setDetecting(false)
    }
  }

  async function exportConfig() {
    setConfigBusy('export')
    try {
      const data = await exportLlmConfig()
      const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }))
      const link = document.createElement('a')
      link.href = url
      link.download = 'cartridgeflow-model-connections.json'
      link.click()
      URL.revokeObjectURL(url)
      setNotice('模型连接已导出，文件不包含 API Key')
    } catch (reason: any) {
      setError(reason?.message || '导出模型连接失败')
    } finally {
      setConfigBusy('')
    }
  }

  async function importConfigFile(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) return
    setImportText(await file.text())
    setImportOpen(true)
  }

  async function importOpenCode() {
    if (!importText.trim()) { setError('请粘贴或选择 OpenCode JSON 配置'); return }
    setConfigBusy('import')
    setError('')
    setNotice('')
    try {
      const result = await importOpenCodeConfig(importText)
      setImportOpen(false)
      setImportText('')
      setNotice(`已导入并自动识别 ${result.providers.length} 个 OpenCode 模型连接`)
      await refreshAfterMutation()
    } catch (reason: any) {
      setError(reason?.message || '导入 OpenCode 配置失败')
    } finally {
      setConfigBusy('')
    }
  }

  async function saveTool(event: React.FormEvent) {
    event.preventDefault()
    if (!resources || !toolForm.name?.trim()) { setError('请填写工具连接名称'); return }
    if (toolForm.kind === 'mcp' && !toolForm.endpoint?.trim() && !toolForm.command?.trim()) { setError('MCP 服务需要地址或启动命令'); return }
    if (toolForm.kind === 'remote_api' && !toolForm.endpoint?.trim() && !toolForm.openapi_url?.trim()) { setError('远程 API 需要 Endpoint 或 OpenAPI URL'); return }
    if (toolForm.kind === 'plugin' && !toolForm.endpoint?.trim() && !toolForm.command?.trim()) { setError('底座插件需要入口地址或启动命令'); return }
    if (toolCredential && !toolForm.auth_env?.trim()) { setError('填写 API Key / Token 时需要同时填写凭据标识'); return }
    setSaving(true)
    setError('')
    try {
      const item = {
        ...toolForm,
        id: toolForm.id.trim() || toolForm.name.trim(),
        name: toolForm.name.trim(),
        auth_env: toolForm.auth_env?.trim().toUpperCase(),
      }
      if (item.auth_env && toolCredential) await createStudioCredential({ key: item.auth_env, label: `${item.name} 凭据`, value: toolCredential, secret: true })
      const tools = [...resources.tools]
      const index = tools.findIndex((entry) => entry.id === selectedToolId)
      if (index >= 0) tools[index] = item
      else tools.push(item)
      const result = await saveStudioResources({ version: 1, tools, bindings: resources.bindings, builtin_tools: [] })
      const savedTool = result.resources.tools.find((entry) => entry.id === item.id)
        || result.resources.tools.find((entry) => entry.name === item.name && entry.kind === item.kind)
        || item
      setSelectedToolId(savedTool.id)
      setToolForm({ ...savedTool })
      setToolCredential('')
      const updatedResources = { ...result.resources, builtin_tools: resources.builtin_tools }
      setResources(updatedResources)
      if (pendingTarget?.kind === 'tool') {
        await bindToolTarget(pendingTarget.flow, pendingTarget.requirement, savedTool.id, savedTool, updatedResources)
        setPendingTarget(null)
      }
      setNotice(selectedToolId ? '工具连接已更新' : '工具连接已创建')
      await refreshAfterMutation()
    } catch (reason: any) {
      setError(reason?.message || '保存工具连接失败')
    } finally {
      setSaving(false)
    }
  }

  async function removeTool() {
    if (!resources || !selectedTool || !window.confirm(`删除工具连接“${selectedTool.name}”？\n\n关联分配会同时解除。`)) return
    const bindings = copyBindings(resources)
    for (const flowId of Object.keys(bindings.tools)) bindings.tools[flowId] = bindings.tools[flowId].filter((id) => id !== selectedTool.id)
    for (const flowId of Object.keys(bindings.roles)) {
      bindings.roles[flowId] = Object.fromEntries(Object.entries(bindings.roles[flowId]).filter(([, id]) => id !== selectedTool.id))
      if (!Object.keys(bindings.roles[flowId]).length) delete bindings.roles[flowId]
    }
    try {
      await saveStudioResources({ version: 1, tools: resources.tools.filter((item) => item.id !== selectedTool.id), bindings, builtin_tools: [] })
      setResources((current) => current ? { ...current, tools: current.tools.filter((item) => item.id !== selectedTool.id) } : current)
      closeEditor()
      setNotice('工具连接已删除；共享凭据未自动删除')
      await refreshAfterMutation()
    } catch (reason: any) {
      setError(reason?.message || '删除工具连接失败')
    }
  }

  function setToolField(field: string, value: any) {
    setToolForm((current) => ({ ...current, [field]: value }))
  }

  const modelIssues = modelTargets.filter(({ flow, role }) => role.required && getRoleReadiness(flow.id, role, providers, assignments).state !== 'ready')
  const toolIssues = toolTargets.filter(({ flow, requirement }) => {
    if (requirement.required === false) return false
    const id = resources?.bindings.roles?.[flow.id]?.[requirement.role]
    const tool = resources?.tools.find((item) => item.id === id)
    return !tool || !toolMatches(tool, requirement)
  })
  const providerUsage = selectedProvider ? [
    ...Object.entries(assignments?.defaults || {}).filter(([, binding]) => binding.provider_id === selectedProvider.id).map(([role]) => ({ label: `默认角色 / ${role}`, detail: '底座默认模型' })),
    ...modelTargets.filter(({ flow, role }) => assignments?.cartridges?.[flow.id]?.[role.id]?.provider_id === selectedProvider.id).map(({ flow, role }) => ({ label: `${flow.name} / ${role.label}`, detail: `卡带角色 · ${role.capability}` })),
    ...Object.entries(assignments?.nodes || {}).flatMap(([nodeId, roles]) => Object.entries(roles).filter(([, binding]) => binding.provider_id === selectedProvider.id).map(([role]) => ({ label: `${nodeId} / ${role}`, detail: 'AI 节点覆盖' }))),
  ] : []
  const toolUsage = selectedTool ? [
    ...toolTargets.filter(({ flow, requirement }) => resources?.bindings.roles?.[flow.id]?.[requirement.role] === selectedTool.id).map(({ flow, requirement }) => ({ label: `${flow.name} / ${requirement.role}`, detail: `工具角色 · ${(requirement.capabilities || []).join(', ') || toolKindLabel(selectedTool)}` })),
    ...Object.entries(resources?.bindings.tools || {}).filter(([, ids]) => ids.includes(selectedTool.id)).map(([flowId]) => ({ label: flowId, detail: '卡带直接工具绑定' })),
  ] : []

  function renderEditorFeedback() {
    const message = error || notice
    if (!message) return null
    return <div className={`cf-resource-modal-feedback ${error ? 'danger' : 'success'}`} role={error ? 'alert' : 'status'}><span>{message}</span><button type="button" onClick={() => { setError(''); setNotice('') }} aria-label="关闭提示" title="关闭提示">×</button></div>
  }

  return (
    <div className={`cf-resource-page cf-resource-config-page ${embedded ? 'is-embedded' : ''}`}>
      {!embedded && <header className="cf-resource-heading cf-resource-config-heading">
        <div><span className="cf-resource-kicker">LOCAL RESOURCE CONFIGURATION</span><h1>资源配置</h1><p>创建模型与工具连接，并在同一资源弹窗内完成凭据、测试和角色分配。</p></div>
        <div className="cf-resource-module-actions"><button type="button" className="primary" onClick={() => setCreateOpen(true)}>新增模型 API</button><button type="button" onClick={() => startNewTool()}>新增工具连接</button></div>
      </header>}

      {!editorKind && error && <div className="cf-resource-alert danger">{error}</div>}
      {!editorKind && notice && <div className="cf-resource-alert success">{notice}</div>}

      <section className="cf-resource-library-section" id="resource-models">
        <div className="cf-resource-library-head"><div><span>MODEL API CONNECTIONS</span><h2>模型 API</h2><p>面向卡带模型角色和 AI 节点的 OpenAI Compatible 连接。</p></div><div><input ref={importInputRef} type="file" accept="application/json,.json" hidden onChange={(event) => void importConfigFile(event)} /><button type="button" onClick={() => void exportConfig()} disabled={Boolean(configBusy)}>导出</button><button type="button" className="primary" onClick={() => setCreateOpen(true)}>新增</button></div></div>
        <div className="cf-resource-card-grid">
          {providers.map((provider) => {
            const state = providerState(provider)
            const usage = [
              ...Object.values(assignments?.defaults || {}),
              ...Object.values(assignments?.cartridges || {}).flatMap((roles) => Object.values(roles)),
              ...Object.values(assignments?.nodes || {}).flatMap((roles) => Object.values(roles)),
            ].filter((binding) => binding.provider_id === provider.id).length
            return <button type="button" className="cf-resource-card" key={provider.id} onClick={() => openProvider(provider)}><span className="cf-resource-card-top"><i className={`cf-resource-state ${state.key}`} /><b className={state.key}>{state.label}</b>{provider.enabled && <em>默认</em>}</span><strong>{provider.name}</strong><small>{provider.default_model || '未填写默认模型'} · 普通文本模型</small><code>{provider.base_url || '未填写服务地址'}</code><span className="cf-resource-card-meta">{usage} 个角色已分配</span></button>
          })}
          {!providers.length && !loading && <div className="cf-resource-card-empty"><strong>还没有模型 API</strong><span>创建连接后可在同一弹窗中完成测试和角色分配。</span><button type="button" onClick={() => setCreateOpen(true)}>新增模型 API</button></div>}
        </div>
      </section>

      <section className="cf-resource-library-section" id="resource-tools">
        <div className="cf-resource-library-head"><div><span>TOOL CONNECTIONS</span><h2>工具连接</h2><p>官方远程 API、OpenAPI、MCP 服务和用户自部署插件；图片与视频能力从这里接入。</p></div><div><button type="button" className="primary" onClick={() => startNewTool()}>新增</button></div></div>
        <div className="cf-resource-card-grid">
          {(resources?.tools || []).map((tool) => {
            const credential = environment?.credentials.find((item) => item.key === tool.auth_env)
            const ready = Boolean((tool.endpoint || tool.command || tool.openapi_url) && (!tool.auth_env || credential?.has_value))
            const usage = Object.values(resources?.bindings.roles || {}).flatMap((roles) => Object.values(roles)).filter((id) => id === tool.id).length
              + Object.values(resources?.bindings.tools || {}).flat().filter((id) => id === tool.id).length
            return <button type="button" className="cf-resource-card" key={tool.id} onClick={() => openTool(tool)}><span className="cf-resource-card-top"><i className={`cf-resource-state ${ready ? 'verified' : 'incomplete'}`} /><b className={ready ? 'verified' : 'incomplete'}>{ready ? '可用' : tool.auth_env && !credential?.has_value ? '缺少凭据' : '待完善'}</b><em>{toolKindLabel(tool)}</em></span><strong>{tool.name}</strong><small>{tool.capabilities?.join(', ') || '未声明能力标签'}</small><code>{tool.endpoint || tool.command || tool.openapi_url || '未填写连接地址'}</code><span className="cf-resource-card-meta">{usage} 个角色已分配</span></button>
          })}
          {!resources?.tools.length && !loading && <div className="cf-resource-card-empty"><strong>还没有工具连接</strong><span>官方生图、生视频 API，以及自部署 AI 都从这里接入。</span><button type="button" onClick={() => startNewTool()}>新增工具连接</button></div>}
        </div>
        {(resources?.builtin_tools.length || 0) > 0 && <details className="cf-resource-builtin-details"><summary>底座内置工具 · {resources?.builtin_tools.length}</summary><div>{resources?.builtin_tools.map((tool) => <span key={tool.id}><strong>{tool.name}</strong><small>{tool.server}/{tool.tool}</small></span>)}</div></details>}
      </section>

      <section className="cf-resource-library-section cf-resource-needs-section">
        <div className="cf-resource-library-head"><div><span>UNRESOLVED REQUIREMENTS</span><h2>待分配需求</h2><p>从缺失角色直接选择已有资源，或新建连接后自动完成分配。</p></div><b className={modelIssues.length + toolIssues.length ? 'warning' : 'ok'}>{modelIssues.length + toolIssues.length}</b></div>
        <div className="cf-resource-needs-list">
          {modelIssues.map(({ flow, role }) => <button type="button" key={`model-${flow.id}-${role.id}`} onClick={() => openModelTarget(flow, role)}><span>模型角色</span><strong>{role.label}</strong><small>{flow.name} · {role.capability}</small><b>选择资源</b></button>)}
          {toolIssues.map(({ flow, requirement }) => <button type="button" key={`tool-${flow.id}-${requirement.role}`} onClick={() => setPendingTarget({ kind: 'tool', flow, requirement })}><span>工具角色</span><strong>{requirement.role}</strong><small>{flow.name} · {(requirement.capabilities || requirement.kinds || []).join(', ')}</small><b>选择资源</b></button>)}
          {!modelIssues.length && !toolIssues.length && !loading && <div className="cf-resource-overview-empty"><strong>没有待分配需求</strong><span>当前必需资源角色均已满足。</span></div>}
        </div>
      </section>

      <ConfigModal open={createOpen} title="新增资源" kicker="CREATE RESOURCE" className="cf-resource-create-modal" onClose={() => setCreateOpen(false)}>
        <div className="cf-provider-create-grid">
          <button type="button" onClick={() => startNewProvider(false)}><span>普通 LLM 连接</span><strong>MODEL API</strong><small>用于文本、推理、结构化输出与工具调用</small></button>
          <button type="button" className="import" onClick={() => { setCreateOpen(false); setImportOpen(true) }}><span>导入 OpenCode</span><strong>JSON</strong><small>读取 Provider、URL、Key 与模型目录，统一作为普通 LLM</small></button>
        </div>
      </ConfigModal>

      <ConfigModal open={editorKind === 'model'} title={selectedProviderId ? providerForm.name : '新增普通 LLM 连接'} kicker="MODEL RESOURCE" className="cf-resource-workspace-modal" onClose={closeEditor}>
        <div className="cf-resource-modal-tabs" role="tablist"><button type="button" className={editorTab === 'connection' ? 'active' : ''} onClick={() => setEditorTab('connection')}>连接与凭据</button><button type="button" disabled={!selectedProviderId} className={editorTab === 'assignments' ? 'active' : ''} onClick={() => setEditorTab('assignments')}>分配关系</button><button type="button" disabled={!selectedProviderId} className={editorTab === 'usage' ? 'active' : ''} onClick={() => setEditorTab('usage')}>使用情况</button></div>
        {renderEditorFeedback()}
        {editorTab === 'connection' && <form className="cf-model-provider-form" onSubmit={saveProvider} autoComplete="off">
          <div className="cf-resource-form-row"><label>连接名称<input value={providerForm.name} onChange={(event) => setProviderForm({ ...providerForm, name: event.target.value })} placeholder="例如：OpenAI 主连接" /></label><label>连接标识（可留空）<input value={providerForm.id} disabled={Boolean(selectedProviderId)} onChange={(event) => setProviderForm({ ...providerForm, id: event.target.value })} placeholder="自动生成" /></label></div>
          <label>服务 URL<input value={providerForm.base_url} onChange={(event) => { setProviderForm({ ...providerForm, base_url: event.target.value }); setProviderDetection(null) }} placeholder="https://..." /></label>
          <label>API Key<input type="password" autoComplete="new-password" value={providerForm.api_key} onChange={(event) => { setProviderForm({ ...providerForm, api_key: event.target.value }); setProviderDetection(null) }} placeholder={selectedProvider?.has_key ? '已保存，留空保持不变' : '仅保存在本机'} /></label>
          <div className={`cf-provider-autodetect ${providerDetection ? 'detected' : ''}`}>
            <div><span>AUTO CONFIGURATION</span><strong>{providerDetection ? `已识别为${providerDetection.adapter_label}，默认使用 ${providerForm.default_model}` : '等待自动检测'}</strong><small>{providerDetection ? `${providerDetection.model_count} 个模型 · ${providerDetection.adapter_label} · ${providerDetection.confidence === 'high' ? '高置信度' : '已识别'}` : 'URL 与凭据由底座在本机完成识别'}</small></div>
            <button type="button" onClick={() => void detectProvider()} disabled={detecting || !providerForm.base_url.trim() || (!providerForm.api_key.trim() && !selectedProvider?.has_key)}>{detecting ? '检测中…' : providerDetection ? '重新检测' : '检测并自动填写'}</button>
            {providerDetection && providerForm.available_models.length > 1 && <label className="cf-provider-default-model"><span>默认模型</span><select value={providerForm.default_model} onChange={(event) => setProviderForm({ ...providerForm, default_model: event.target.value })}>{providerForm.available_models.map((model) => <option key={model} value={model}>{model}</option>)}</select></label>}
          </div>
          <details className="cf-provider-advanced">
            <summary><span>高级连接参数</span><b>{providerForm.default_model || '检测后自动填写'}</b></summary>
            <div className="cf-provider-advanced-fields">
              <div className="cf-resource-form-row"><label>接口类型<select value={providerForm.api_type} onChange={(event) => setProviderForm({ ...providerForm, api_type: event.target.value, wire_api: 'chat_completions' })}>{API_TYPES.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label><label>调用协议<select value={providerForm.wire_api} onChange={(event) => setProviderForm({ ...providerForm, wire_api: event.target.value })}>{WIRE_APIS.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label></div>
              <div className="cf-provider-capability-note cf-provider-capability-wide"><span>底座只负责普通文本模型连接；图片和视频服务请配置为远程 API / MCP 工具。</span><code>text_reasoning</code></div>
              <div className="cf-resource-form-row"><label>默认模型标识<input list="cf-provider-model-options" value={providerForm.default_model} onChange={(event) => setProviderForm({ ...providerForm, default_model: event.target.value })} placeholder="检测后自动填写" /><datalist id="cf-provider-model-options">{providerForm.available_models.map((model) => <option key={model} value={model} />)}</datalist></label><label>超时（秒）<input value={providerForm.timeout} onChange={(event) => setProviderForm({ ...providerForm, timeout: event.target.value })} inputMode="numeric" /></label></div>
            </div>
          </details>
          <div className="cf-config-modal-actions">{selectedProvider && <><button type="button" className="danger" onClick={() => void removeProvider()}>删除连接</button><button type="button" onClick={() => void testProvider()} disabled={testing}>{testing ? '测试中…' : '测试连接'}</button>{selectedProvider.capabilities?.includes('text_reasoning') && <button type="button" onClick={() => void activateProvider()} disabled={Boolean(selectedProvider.enabled)}>设为默认</button>}</>}<button type="button" onClick={closeEditor}>取消</button><button type="submit" className="primary" disabled={saving}>{saving ? '保存中…' : '保存连接'}</button></div>
          <small className="cf-credential-storage">密钥只保存在本机；卡带只记录能力配方和资源角色。</small>
        </form>}
        {editorTab === 'assignments' && selectedProvider && <div className="cf-resource-modal-list">{modelTargets.map(({ flow, role }) => { const binding = assignments?.cartridges?.[flow.id]?.[role.id]; const assignedHere = binding?.provider_id === selectedProvider.id; const issue = providerRoleCompatibilityIssue(role, selectedProvider); return <div key={`${flow.id}-${role.id}`}><span><strong>{role.label}</strong><small>{flow.name} · {role.capability}</small></span><b>{assignedHere ? `已分配 · ${binding?.model || selectedProvider.default_model}` : binding?.provider_id ? '已分配到其他连接' : '尚未分配'}</b><button type="button" title={issue || undefined} disabled={Boolean(issue)} onClick={() => { if (assignedHere) void bindModelTarget(flow, role, ''); else openModelTarget(flow, role) }}>{issue ? '不兼容' : assignedHere ? '解除' : binding?.provider_id ? '更换连接与模型' : '选择连接与模型'}</button></div>})}{!modelTargets.length && <div className="cf-resource-modal-empty">没有卡带声明模型角色。</div>}</div>}
        {editorTab === 'usage' && selectedProvider && <div className="cf-resource-modal-list">{providerUsage.map((usage) => <div key={`${usage.label}-${usage.detail}`}><span><strong>{usage.label}</strong><small>{usage.detail}</small></span></div>)}{!providerUsage.length && <div className="cf-resource-modal-empty">这个模型连接尚未被使用。</div>}</div>}
      </ConfigModal>

      <ConfigModal open={importOpen} title="导入 OpenCode 配置" kicker="OPENCODE IMPORT" className="cf-resource-import-modal" onClose={() => { setImportOpen(false); setError('') }}>
        {renderEditorFeedback()}
        <div className="cf-opencode-importer">
          <textarea value={importText} onChange={(event) => setImportText(event.target.value)} rows={14} spellCheck={false} placeholder='{ "provider": { "openai": { "options": { "baseURL": "...", "apiKey": "..." }, "models": {} } } }' />
          <div className="cf-config-modal-actions"><button type="button" onClick={() => importInputRef.current?.click()}>选择 JSON 文件</button><button type="button" onClick={() => { setImportOpen(false); setError('') }}>取消</button><button type="button" className="primary" disabled={configBusy === 'import' || !importText.trim()} onClick={() => void importOpenCode()}>{configBusy === 'import' ? '检测并导入中…' : '检测并导入'}</button></div>
        </div>
      </ConfigModal>

      <ConfigModal open={editorKind === 'tool'} title={selectedToolId ? toolForm.name : '新增工具连接'} kicker="TOOL RESOURCE" className="cf-resource-workspace-modal" onClose={closeEditor}>
        <div className="cf-resource-modal-tabs" role="tablist"><button type="button" className={editorTab === 'connection' ? 'active' : ''} onClick={() => setEditorTab('connection')}>连接与凭据</button><button type="button" disabled={!selectedToolId} className={editorTab === 'assignments' ? 'active' : ''} onClick={() => setEditorTab('assignments')}>分配关系</button><button type="button" disabled={!selectedToolId} className={editorTab === 'usage' ? 'active' : ''} onClick={() => setEditorTab('usage')}>使用情况</button></div>
        {renderEditorFeedback()}
        {editorTab === 'connection' && <form className="cf-resource-editor" onSubmit={saveTool} autoComplete="off">
          <div className="cf-resource-form-row"><label>连接名称<input value={toolForm.name || ''} onChange={(event) => setToolField('name', event.target.value)} placeholder="例如：文生图 API" /></label><label>连接标识（可留空）<input value={toolForm.id || ''} disabled={Boolean(selectedToolId)} onChange={(event) => setToolField('id', event.target.value)} placeholder="自动生成" /></label></div>
          <div className="cf-resource-form-row"><label>连接类型<select value={toolForm.kind || ''} onChange={(event) => setToolField('kind', event.target.value)}>{TOOL_KINDS.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label>{toolForm.kind === 'remote_api' && <label>默认 HTTP 方法<select value={toolForm.http_method || 'POST'} onChange={(event) => setToolField('http_method', event.target.value)}>{['GET', 'POST', 'PUT', 'PATCH', 'DELETE'].map((method) => <option key={method} value={method}>{method}</option>)}</select></label>}</div>
          <label>服务地址 / Endpoint<input value={toolForm.endpoint || ''} onChange={(event) => setToolField('endpoint', event.target.value)} placeholder="https://...；本地 stdio 可留空" /></label>
          {['mcp', 'plugin'].includes(toolForm.kind) && <div className="cf-resource-form-row"><label>启动命令 / 入口<input value={toolForm.command || ''} onChange={(event) => setToolField('command', event.target.value)} placeholder="例如：npx server" /></label><label>参数<input value={toolForm.args || ''} onChange={(event) => setToolField('args', event.target.value)} placeholder="JSON 或空格分隔" /></label></div>}
          {toolForm.kind === 'remote_api' && <label>OpenAPI / Swagger URL<input value={toolForm.openapi_url || ''} onChange={(event) => setToolField('openapi_url', event.target.value)} placeholder="可选：https://.../openapi.json" /></label>}
          <div className="cf-resource-form-row"><label>凭据标识<input value={toolForm.auth_env || ''} onChange={(event) => setToolField('auth_env', event.target.value.toUpperCase())} placeholder="例如：IMAGE_API_KEY" /></label><label>API Key / Token<input type="password" autoComplete="new-password" value={toolCredential} onChange={(event) => setToolCredential(event.target.value)} placeholder={selectedCredential?.has_value ? '已保存，留空保持不变' : '仅保存在本机'} /></label></div>
          <div className="cf-resource-form-row"><label>认证 Header<input value={toolForm.auth_header || ''} onChange={(event) => setToolField('auth_header', event.target.value)} placeholder="Authorization" /></label><label>认证前缀<input value={toolForm.auth_scheme || ''} onChange={(event) => setToolField('auth_scheme', event.target.value)} placeholder="Bearer" /></label></div>
          <div className="cf-resource-form-note"><strong>媒体能力建议</strong><span>生图、生视频不走底座模型适配器，请在这里绑定官方远程 API、OpenAPI、MCP 或自部署服务。卡带只记录工具配方，不携带密钥。</span></div>
          <div className="cf-resource-form-row"><label>能力标签<input value={(toolForm.capabilities || []).join(', ')} onChange={(event) => setToolField('capabilities', event.target.value.split(',').map((item) => item.trim()).filter(Boolean))} placeholder="例如：image_generation 或 video_generation" /></label><label>迁移方式<select value={toolForm.package_mode || 'descriptor'} onChange={(event) => setToolField('package_mode', event.target.value)}><option value="descriptor">卡带只携带工具声明</option><option value="external">保持外部引用</option></select></label></div>
          <label className="cf-environment-secret-toggle"><input type="checkbox" checked={toolForm.read_only === true} onChange={(event) => setToolField('read_only', event.target.checked)} /><span>这个连接只执行读取操作</span></label>
          <label>备注<textarea value={toolForm.description || ''} onChange={(event) => setToolField('description', event.target.value)} rows={2} /></label>
          <div className="cf-config-modal-actions">{selectedTool && <button type="button" className="danger" onClick={() => void removeTool()}>删除</button>}<button type="button" onClick={closeEditor}>取消</button><button type="submit" className="primary" disabled={saving}>{saving ? '保存中…' : '保存连接'}</button></div>
          <small className="cf-credential-storage">凭据只保存在当前底座，不写入卡带；卡带只记录所需资源角色。</small>
        </form>}
        {editorTab === 'assignments' && selectedTool && <div className="cf-resource-modal-list">{toolTargets.map(({ flow, requirement }) => { const bindingId = resources?.bindings.roles?.[flow.id]?.[requirement.role]; const assignedHere = bindingId === selectedTool.id; const compatible = toolMatches(selectedTool, requirement); return <div key={`${flow.id}-${requirement.role}`}><span><strong>{requirement.role}</strong><small>{flow.name} · {(requirement.capabilities || requirement.kinds || []).join(', ')}</small></span><b>{assignedHere ? '已分配到此连接' : bindingId ? '已分配到其他连接' : '尚未分配'}</b><button type="button" disabled={!compatible} onClick={() => void bindToolTarget(flow, requirement, assignedHere ? '' : selectedTool.id)}>{compatible ? assignedHere ? '解除' : bindingId ? '改用此连接' : '分配' : '不兼容'}</button></div>})}{!toolTargets.length && <div className="cf-resource-modal-empty">没有卡带声明工具角色。</div>}</div>}
        {editorTab === 'usage' && selectedTool && <div className="cf-resource-modal-list">{toolUsage.map((usage) => <div key={`${usage.label}-${usage.detail}`}><span><strong>{usage.label}</strong><small>{usage.detail}</small></span></div>)}{!toolUsage.length && <div className="cf-resource-modal-empty">这个工具连接尚未被使用。</div>}</div>}
      </ConfigModal>

      <ConfigModal open={Boolean(pendingTarget && !editorKind)} title={pendingTarget?.kind === 'model' ? '选择连接与模型' : '选择资源'} kicker="RESOLVE REQUIREMENT" className="cf-resource-assignment-modal" onClose={() => { setPendingTarget(null); setPendingModels({}) }}>
        {pendingTarget && <><div className="cf-resource-target-summary"><span>{pendingTarget.kind === 'model' ? '模型角色' : '工具角色'}</span><strong>{pendingTarget.kind === 'model' ? pendingTarget.role.label : pendingTarget.requirement.role}</strong><small>{pendingTarget.flow.name}</small></div><div className="cf-resource-choice-list">
          {pendingTarget.kind === 'model' && providers.filter((provider) => !providerRoleCompatibilityIssue(pendingTarget.role, provider)).map((provider) => { const fixedModel = pendingTarget.role.model && pendingTarget.role.model !== 'configured-locally' ? pendingTarget.role.model : ''; const models = fixedModel ? [fixedModel] : providerModelOptions(provider); const binding = assignments?.cartridges?.[pendingTarget.flow.id]?.[pendingTarget.role.id]; const selectedModel = pendingModels[provider.id] || (binding?.provider_id === provider.id ? binding.model : '') || provider.default_model || models[0] || ''; return <div className="cf-resource-model-choice" key={provider.id}><i className={`cf-resource-state ${providerState(provider).key}`} /><span><strong>{provider.name}</strong><small>{models.length} 个可用模型</small></span><select aria-label={`${provider.name} 使用模型`} value={selectedModel} disabled={Boolean(fixedModel)} onChange={(event) => setPendingModels((current) => ({ ...current, [provider.id]: event.target.value }))}>{models.map((model) => <option key={model} value={model}>{model}</option>)}</select><button type="button" disabled={!selectedModel} onClick={() => { void bindModelTarget(pendingTarget.flow, pendingTarget.role, provider.id, undefined, selectedModel); setPendingTarget(null); setPendingModels({}) }}>选择</button></div> })}
          {pendingTarget.kind === 'tool' && (resources?.tools || []).filter((tool) => toolMatches(tool, pendingTarget.requirement)).map((tool) => <button type="button" key={tool.id} onClick={() => { void bindToolTarget(pendingTarget.flow, pendingTarget.requirement, tool.id); setPendingTarget(null) }}><i className="cf-resource-state verified" /><span><strong>{tool.name}</strong><small>{toolKindLabel(tool)} · {tool.capabilities?.join(', ')}</small></span><b>选择</b></button>)}
        </div><div className="cf-resource-create-for-target"><span>没有合适的资源？</span><button type="button" onClick={() => pendingTarget.kind === 'model' ? startNewProvider(true) : startNewTool(true)}>新建并自动分配</button></div></>}
      </ConfigModal>
    </div>
  )
}
