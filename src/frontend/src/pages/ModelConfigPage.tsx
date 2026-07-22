import { useEffect, useMemo, useState } from 'react'
import {
  activateLlmProvider,
  createLlmProvider,
  deleteLlmProvider,
  fetchLabFlows,
  fetchLlmAssignments,
  fetchLlmProviders,
  saveLlmAssignments,
  testLlmProvider,
  updateLlmProvider,
  type CartridgeSummary,
  type LlmAssignments,
  type LlmProvider,
} from '../api.ts'
import { findExactProviderMatch, normalizeRecipeRoles, type LlmRecipeRole } from '../llmRecipe.ts'
import ConfigModal from '../components/ConfigModal.tsx'

type ProviderDraft = {
  id: string
  name: string
  api_type: string
  base_url: string
  api_key: string
  default_model: string
  wire_api: string
  enabled: boolean
  timeout: string
}

const EMPTY_DRAFT: ProviderDraft = {
  id: '', name: '', api_type: 'openai', base_url: '', api_key: '', default_model: '',
  wire_api: 'chat_completions', enabled: true, timeout: '120',
}

const API_TYPES = [
  { value: 'openai', label: 'OpenAI Compatible' },
  { value: 'anthropic', label: 'Anthropic Messages' },
  { value: 'gemini', label: 'Gemini' },
]

function copyAssignments(value: LlmAssignments): LlmAssignments {
  return {
    version: value.version || 1,
    defaults: { ...(value.defaults || {}) },
    cartridges: Object.fromEntries(Object.entries(value.cartridges || {}).map(([id, roles]) => [id, { ...(roles || {}) }])),
    nodes: Object.fromEntries(Object.entries(value.nodes || {}).map(([id, roles]) => [id, { ...(roles || {}) }])),
  }
}

function draftFromProvider(provider: LlmProvider): ProviderDraft {
  return {
    id: provider.id,
    name: provider.name,
    api_type: provider.api_type || 'openai',
    base_url: provider.base_url || '',
    api_key: '',
    default_model: provider.default_model || '',
    wire_api: provider.wire_api || 'chat_completions',
    enabled: provider.enabled !== false,
    timeout: String(provider.timeout || 120),
  }
}

function exactMatches(flows: CartridgeSummary[], providers: LlmProvider[], assignments: LlmAssignments) {
  const next = copyAssignments(assignments)
  let changed = false
  for (const flow of flows) {
    const roles = normalizeRecipeRoles(flow.llm_recipe)
    for (const role of roles) {
      const current = next.cartridges[flow.id]?.[role.id]
      if (current?.provider_id) continue
      const provider = findExactProviderMatch(role, providers)
      if (!provider) continue
      next.cartridges[flow.id] = { ...(next.cartridges[flow.id] || {}), [role.id]: {
        provider_id: provider.id,
        model: role.model || provider.default_model || '',
      } }
      changed = true
    }
  }
  return { next, changed }
}

export default function ModelConfigPage() {
  const [providers, setProviders] = useState<LlmProvider[]>([])
  const [flows, setFlows] = useState<CartridgeSummary[]>([])
  const [assignments, setAssignments] = useState<LlmAssignments | null>(null)
  const [selectedId, setSelectedId] = useState('')
  const [draft, setDraft] = useState<ProviderDraft>(EMPTY_DRAFT)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [editorOpen, setEditorOpen] = useState(false)

  const selectedProvider = useMemo(() => providers.find((item) => item.id === selectedId), [providers, selectedId])
  const activeProvider = useMemo(() => providers.find((item) => item.enabled), [providers])
  const modelStats = useMemo(() => {
    const readyProviders = providers.filter((item) => item.base_url && item.has_key && item.default_model).length
    const testedProviders = providers.filter((item) => item.tested_ok).length
    let totalRoles = 0
    let boundRoles = 0
    for (const flow of flows) {
      const roles = normalizeRecipeRoles(flow.llm_recipe)
      totalRoles += roles.length
      for (const role of roles) {
        const providerId = assignments?.cartridges?.[flow.id]?.[role.id]?.provider_id
        if (providerId && providers.some((item) => item.id === providerId)) boundRoles += 1
      }
    }
    return { readyProviders, testedProviders, totalRoles, boundRoles }
  }, [assignments, flows, providers])

  async function load(preferredId = selectedId) {
    setLoading(true)
    setError('')
    try {
      const [providerResult, assignmentResult, flowResult] = await Promise.all([fetchLlmProviders(), fetchLlmAssignments(), fetchLabFlows()])
      const providerItems = providerResult.providers || []
      const flowItems = flowResult.items || []
      const reconciled = exactMatches(flowItems, providerItems, assignmentResult)
      let nextAssignments = assignmentResult
      if (reconciled.changed) {
        const saved = await saveLlmAssignments(reconciled.next)
        nextAssignments = saved.assignments
        setNotice('已按配方名称接入本机连接')
      }
      setProviders(providerItems)
      setFlows(flowItems)
      setAssignments(nextAssignments)
      const preferred = providerItems.find((item) => item.id === preferredId) || (!preferredId ? providerItems[0] : undefined)
      if (preferred) {
        setSelectedId(preferred.id)
        setDraft(draftFromProvider(preferred))
      }
    } catch (reason: any) {
      setError(reason?.message || '读取模型配置失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void load() }, [])

  function selectProvider(provider: LlmProvider) {
    setSelectedId(provider.id)
    setDraft(draftFromProvider(provider))
    setNotice('')
  }

  function startNew() {
    setSelectedId('')
    setDraft(EMPTY_DRAFT)
    setNotice('')
    setEditorOpen(true)
  }

  function editSelected() {
    if (!selectedProvider) return
    setDraft(draftFromProvider(selectedProvider))
    setEditorOpen(true)
  }

  async function saveProvider(event: React.FormEvent) {
    event.preventDefault()
    if (!draft.name.trim()) { setError('请填写连接名称'); return }
    setSaving(true)
    setError('')
    try {
      const payload = {
        id: draft.id,
        name: draft.name.trim(),
        api_type: draft.api_type,
        base_url: draft.base_url.trim(),
        api_key: draft.api_key,
        default_model: draft.default_model.trim(),
        wire_api: draft.wire_api,
        enabled: draft.enabled,
        timeout: Number(draft.timeout) || 120,
      }
      const result = draft.id ? await updateLlmProvider(draft.id, payload) : await createLlmProvider(payload)
      setNotice(draft.id ? '本机连接已更新' : '本机连接已创建')
      setSelectedId(result.provider.id)
      setEditorOpen(false)
      await load(result.provider.id)
    } catch (reason: any) {
      setError(reason?.message || '保存模型连接失败')
    } finally {
      setSaving(false)
    }
  }

  async function removeProvider() {
    if (!selectedProvider || !window.confirm(`删除本机连接“${selectedProvider.name}”？`)) return
    try {
      await deleteLlmProvider(selectedProvider.id)
      setSelectedId('')
      setDraft(EMPTY_DRAFT)
      setEditorOpen(false)
      await load('')
      setNotice('本机连接已删除')
    } catch (reason: any) {
      setError(reason?.message || '删除模型连接失败')
    }
  }

  async function activateProvider() {
    if (!selectedProvider) return
    try {
      await activateLlmProvider(selectedProvider.id)
      setNotice('默认连接已切换')
      await load()
    } catch (reason: any) {
      setError(reason?.message || '切换默认连接失败')
    }
  }

  async function testProvider() {
    if (!selectedProvider) return
    setTesting(true)
    setError('')
    setNotice('')
    try {
      const result = await testLlmProvider(selectedProvider.id, draft.default_model)
      if (!result.ok) throw new Error(result.error || '模型服务没有通过连接测试')
      setNotice('连接测试通过')
      await load()
    } catch (reason: any) {
      setError((typeof reason?.detail === 'string' && reason.detail) || reason?.message || '连接测试失败')
    } finally {
      setTesting(false)
    }
  }

  async function bindProvider(flowId: string, role: LlmRecipeRole, providerId: string) {
    if (!assignments) return
    const next = copyAssignments(assignments)
    const flowBindings = { ...(next.cartridges[flowId] || {}) }
    if (providerId) flowBindings[role.id] = { provider_id: providerId, model: role.model || providers.find((p) => p.id === providerId)?.default_model || '' }
    else delete flowBindings[role.id]
    if (Object.keys(flowBindings).length) next.cartridges[flowId] = flowBindings
    else delete next.cartridges[flowId]
    try {
      const result = await saveLlmAssignments(next)
      setAssignments(result.assignments)
      setNotice(providerId ? '配方角色已绑定' : '配方角色已解除绑定')
    } catch (reason: any) {
      setError(reason?.message || '保存配方绑定失败')
    }
  }

  function onProviderDrag(event: React.DragEvent, providerId: string) {
    event.dataTransfer.setData('application/x-cf-model-provider', providerId)
    event.dataTransfer.effectAllowed = 'link'
  }

  function onRoleDrop(event: React.DragEvent, flowId: string, role: LlmRecipeRole) {
    event.preventDefault()
    const providerId = event.dataTransfer.getData('application/x-cf-model-provider')
    if (providerId) void bindProvider(flowId, role, providerId)
  }

  return (
    <div className="cf-resource-page cf-model-config-page">
      <header className="cf-resource-heading cf-model-config-heading">
        <div>
          <span className="cf-resource-kicker">MODEL ROUTING</span>
          <h1>模型配置</h1>
          <p>本机模型连接与卡带配方角色的路由总表</p>
        </div>
        <div className={`cf-overview-health ${modelStats.testedProviders > 0 ? 'ok' : 'partial'}`}>
          <i />
          <span>{modelStats.testedProviders > 0 ? `${modelStats.testedProviders} 个连接已验证` : '尚无已验证连接'}</span>
        </div>
      </header>
      {error && <div className="cf-resource-alert danger">{error}</div>}
      {notice && <div className="cf-resource-alert success">{notice}</div>}

      <section className="cf-model-config-stats" aria-label="模型路由摘要">
        <div className="primary">
          <span>DEFAULT ROUTE</span>
          <strong>{activeProvider?.name || '未设置默认连接'}</strong>
          <small>{activeProvider ? `${activeProvider.api_type} / ${activeProvider.default_model || '未指定模型'}` : '选择一个本机连接作为默认路由'}</small>
        </div>
        <div><span>本机连接</span><strong>{providers.length}</strong><small>{modelStats.readyProviders} 个配置完整</small></div>
        <div><span>真实验证</span><strong>{modelStats.testedProviders}</strong><small>最近连接测试通过</small></div>
        <div><span>配方接入</span><strong>{modelStats.boundRoles}<em>/ {modelStats.totalRoles}</em></strong><small>已绑定模型角色</small></div>
      </section>

      <div className="cf-resource-layout cf-model-routing-surface">
        <section className="cf-resource-panel cf-model-provider-panel">
          <div className="cf-resource-panel-head"><div><span>LOCAL CONNECTIONS</span><h2>连接目录</h2></div><button type="button" onClick={startNew}>新增连接</button></div>
          <div className="cf-model-provider-list">
            {providers.map((provider) => {
              const complete = Boolean(provider.has_key && provider.base_url && provider.default_model)
              const state = provider.tested_ok ? 'verified' : complete ? 'pending' : 'incomplete'
              const stateLabel = provider.tested_ok ? '已验证' : complete ? '待验证' : '未配置'
              return <button key={provider.id} type="button" draggable onDragStart={(event) => onProviderDrag(event, provider.id)} className={`cf-model-provider-item ${selectedId === provider.id ? 'selected' : ''}`} onClick={() => selectProvider(provider)}>
                <span className={`cf-provider-dot ${state}`} />
                <span className="cf-model-provider-copy"><strong>{provider.name}</strong><small>{provider.api_type} / {provider.default_model || '未指定模型'}</small></span>
                <span className="cf-model-provider-state"><b className={state}>{stateLabel}</b>{provider.enabled && <i>默认</i>}</span>
              </button>
            })}
            {loading && <div className="cf-resource-empty compact">正在读取本机连接</div>}
            {!providers.length && !loading && <div className="cf-resource-empty">还没有本机连接</div>}
          </div>
          {selectedProvider ? <div className="cf-selected-resource-summary">
            <div className="cf-selected-resource-title"><span>SELECTED CONNECTION</span><strong>{selectedProvider.name}</strong><code>{selectedProvider.id}</code></div>
            <dl><div><dt>URL</dt><dd>{selectedProvider.base_url || '未填写'}</dd></div><div><dt>模型</dt><dd>{selectedProvider.default_model || '未填写'}</dd></div><div><dt>Key</dt><dd>{selectedProvider.has_key ? `已保存 ${selectedProvider.key_preview || ''}` : '未填写'}</dd></div><div><dt>协议</dt><dd>{selectedProvider.api_type} / {selectedProvider.wire_api}</dd></div></dl>
            <div className="cf-model-form-actions"><button type="button" className="primary" onClick={editSelected}>编辑连接</button><button type="button" onClick={() => void testProvider()} disabled={saving || testing}>{testing ? '测试中…' : '测试连接'}</button><button type="button" onClick={() => void activateProvider()} disabled={saving || testing || selectedProvider.enabled}>设为默认</button><button type="button" className="danger" onClick={() => void removeProvider()} disabled={saving || testing}>删除</button></div>
          </div> : <div className="cf-selection-hint"><strong>选择一个本机连接</strong><span>查看状态，或将它拖到右侧配方角色。</span></div>}
        </section>

        <section className="cf-resource-panel cf-model-binding-panel">
          <div className="cf-resource-panel-head"><div><span>CARTRIDGE RECIPES</span><h2>卡带模型路由</h2></div><small>{modelStats.boundRoles} / {modelStats.totalRoles} 已接入</small></div>
          <div className="cf-model-binding-list">
            {flows.map((flow) => {
              const roles = normalizeRecipeRoles(flow.llm_recipe)
              return <article className="cf-cartridge-resource-row" key={flow.id}>
                <div className="cf-cartridge-resource-head"><div><strong>{flow.name}</strong><code>{flow.id}</code></div><span>{roles.length ? `${roles.length} 个角色` : '无模型配方'}</span></div>
                {roles.length > 0 ? <div className="cf-model-role-drop-list">{roles.map((role) => {
                  const binding = assignments?.cartridges?.[flow.id]?.[role.id]
                  const provider = providers.find((item) => item.id === binding?.provider_id)
                  const match = !binding ? findExactProviderMatch(role, providers) : undefined
                  const providerComplete = Boolean(provider?.base_url && provider?.has_key && provider?.default_model)
                  const bindingState = provider ? (providerComplete ? 'bound' : 'unavailable') : binding ? 'unavailable' : match ? 'auto-match' : ''
                  const bindingLabel = provider ? (provider.tested_ok ? '连接已验证' : providerComplete ? '等待连接验证' : '连接信息不完整') : match ? `可精确匹配：${match.name}` : binding ? '绑定的连接已不存在' : '尚未绑定'
                  return <div className={`cf-model-role-drop ${bindingState}`} key={role.id} onDragOver={(event) => event.preventDefault()} onDrop={(event) => onRoleDrop(event, flow.id, role)}><span className="cf-role-drop-name"><b>{role.label}</b><code>{role.id}</code></span><span className="cf-role-drop-value">{bindingLabel}</span><select className="cf-role-binding-select" value={binding?.provider_id || ''} onChange={(event) => void bindProvider(flow.id, role, event.target.value)} aria-label={`为 ${role.label} 选择本机连接`}><option value="">未绑定</option>{providers.map((item) => { const compatible = (!role.api_type || item.api_type === role.api_type) && (!role.wire_api || !item.wire_api || item.wire_api === role.wire_api); return <option key={item.id} value={item.id} disabled={!compatible}>{item.name}{compatible ? '' : '（协议不兼容）'}</option> })}</select></div>
                })}</div> : <div className="cf-resource-empty compact">配方未声明模型角色</div>}
              </article>
            })}
            {loading && <div className="cf-resource-empty">正在读取卡带配方</div>}
            {!flows.length && !loading && <div className="cf-resource-empty">还没有可绑定的卡带</div>}
          </div>
        </section>
      </div>
      <ConfigModal open={editorOpen} title={draft.id ? `编辑 ${draft.name}` : '新增本机模型连接'} kicker="LOCAL MODEL CONNECTION" onClose={() => setEditorOpen(false)}>
        <form className="cf-model-provider-form" onSubmit={saveProvider} autoComplete="off">
          <label>连接名称<input name="cf-provider-name" autoComplete="off" value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} placeholder="例如：xxx站-xxx gpt-5.5" /></label>
          <label>标识（可留空）<input name="cf-provider-id" autoComplete="off" value={draft.id} disabled={Boolean(selectedProvider)} onChange={(e) => setDraft({ ...draft, id: e.target.value })} placeholder="自动生成" /></label>
          <div className="cf-resource-form-row"><label>接口类型<select value={draft.api_type} onChange={(e) => setDraft({ ...draft, api_type: e.target.value, wire_api: e.target.value === 'anthropic' ? 'messages' : 'chat_completions' })}>{API_TYPES.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label><label>调用协议<select value={draft.wire_api} onChange={(e) => setDraft({ ...draft, wire_api: e.target.value })}><option value="chat_completions">chat_completions</option><option value="messages">messages</option><option value="generate_content">generate_content</option></select></label></div>
          <label>URL<input name="cf-provider-url" autoComplete="off" value={draft.base_url} onChange={(e) => setDraft({ ...draft, base_url: e.target.value })} placeholder="https://..." /></label>
          <label>Key<input name="cf-provider-secret" autoComplete="new-password" type="password" value={draft.api_key} onChange={(e) => setDraft({ ...draft, api_key: e.target.value })} placeholder={selectedProvider?.has_key ? '已保存，留空保持不变' : '仅保存在本机'} /></label>
          <div className="cf-resource-form-row"><label>默认模型<input name="cf-provider-model" autoComplete="off" value={draft.default_model} onChange={(e) => setDraft({ ...draft, default_model: e.target.value })} placeholder="例如：gpt-5.5" /></label><label>超时（秒）<input value={draft.timeout} onChange={(e) => setDraft({ ...draft, timeout: e.target.value })} inputMode="numeric" /></label></div>
          <div className="cf-config-modal-actions"><button type="button" onClick={() => setEditorOpen(false)}>取消</button><button type="submit" className="primary" disabled={saving}>{saving ? '保存中…' : '保存连接'}</button></div>
        </form>
      </ConfigModal>
    </div>
  )
}
