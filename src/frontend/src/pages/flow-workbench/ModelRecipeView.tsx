import { useEffect, useMemo, useState } from 'react'

import {
  fetchLlmAssignments,
  fetchLlmProviders,
  saveLabFlowFile,
  saveLlmAssignments,
  type FlowFiles,
  type FlowLabDetail,
  type LlmAssignments,
  type LlmProvider,
} from '../../api.ts'
import { getRoleReadiness, normalizeRecipeRoles, type LlmRecipeRole } from '../../llmRecipe.ts'
import { showToast } from '../../toast.tsx'

const EMPTY_ASSIGNMENTS: LlmAssignments = { version: 1, defaults: {}, cartridges: {}, nodes: {} }

const CAPABILITIES = [
  { value: 'text_generation', label: '文本生成' },
  { value: 'vision', label: '视觉理解' },
  { value: 'image_generation', label: '图片生成' },
  { value: 'embedding', label: '向量嵌入' },
  { value: 'audio', label: '音频处理' },
]

const API_TYPES = [
  { value: 'openai', label: 'OpenAI Compatible' },
  { value: 'anthropic', label: 'Anthropic' },
]

const WIRE_APIS = [
  { value: 'chat_completions', label: 'Chat Completions' },
  { value: 'responses', label: 'Responses' },
  { value: 'messages', label: 'Messages' },
  { value: 'images', label: 'Images' },
  { value: 'embeddings', label: 'Embeddings' },
]

function parseManifest(detail: FlowLabDetail, files: FlowFiles) {
  if (files.manifest) {
    try {
      return JSON.parse(files.manifest)
    } catch {
      // The workbench already reports malformed files; keep this view usable from loaded detail.
    }
  }
  return JSON.parse(JSON.stringify(detail.cartridge.manifest || {}))
}

function roleStateLabel(state: string) {
  if (state === 'ready') return '已就绪'
  if (state === 'mismatch') return '不兼容'
  if (state === 'missing') return '连接不完整'
  return '未连接'
}

function defaultWireApi(apiType: string, capability: string) {
  if (capability === 'image_generation') return 'images'
  if (capability === 'embedding') return 'embeddings'
  return apiType === 'anthropic' ? 'messages' : 'chat_completions'
}

export function ModelRecipeView({ detail, files, flowId, editable, onRefresh }: {
  detail: FlowLabDetail
  files: FlowFiles
  flowId: string
  editable: boolean
  onRefresh: () => Promise<void>
}) {
  const [roles, setRoles] = useState<LlmRecipeRole[]>([])
  const [providers, setProviders] = useState<LlmProvider[]>([])
  const [assignments, setAssignments] = useState<LlmAssignments>(EMPTY_ASSIGNMENTS)
  const [loading, setLoading] = useState(true)
  const [savingRecipe, setSavingRecipe] = useState(false)
  const [savingBinding, setSavingBinding] = useState('')
  const [dirty, setDirty] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    const manifest = parseManifest(detail, files)
    setRoles(normalizeRecipeRoles(manifest.llm_recipe))
    setDirty(false)
  }, [detail, files.manifest, flowId])

  const loadLocalConnections = async () => {
    setLoading(true)
    try {
      const [providerData, assignmentData] = await Promise.all([fetchLlmProviders(), fetchLlmAssignments()])
      setProviders(providerData.providers || [])
      setAssignments(assignmentData || EMPTY_ASSIGNMENTS)
      setError('')
    } catch (reason: any) {
      setError(reason?.message || '本机模型连接读取失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void loadLocalConnections() }, [flowId])

  const readiness = useMemo(
    () => roles.map((role) => getRoleReadiness(flowId, role, providers, assignments)),
    [assignments, flowId, providers, roles],
  )
  const requiredIssues = readiness.filter((role) => role.required && role.state !== 'ready')

  const updateRole = (index: number, patch: Partial<LlmRecipeRole>) => {
    setRoles((current) => current.map((role, roleIndex) => roleIndex === index ? { ...role, ...patch } : role))
    setDirty(true)
  }

  const addRole = () => {
    let number = roles.length + 1
    let id = `model_role_${number}`
    while (roles.some((role) => role.id === id)) {
      number += 1
      id = `model_role_${number}`
    }
    setRoles((current) => [...current, {
      id,
      label: `模型角色 ${number}`,
      capability: 'text_generation',
      api_type: 'openai',
      wire_api: 'chat_completions',
      model: '',
      required: true,
    }])
    setDirty(true)
  }

  const removeRole = (index: number) => {
    setRoles((current) => current.filter((_, roleIndex) => roleIndex !== index))
    setDirty(true)
  }

  const validateRecipe = () => {
    const ids = new Set<string>()
    for (const [index, role] of roles.entries()) {
      const prefix = `角色 ${index + 1}`
      if (!role.id || !/^[A-Za-z0-9_.-]+$/.test(role.id)) return `${prefix} ID 只能包含字母、数字、点、横线和下划线`
      if (ids.has(role.id)) return `角色 ID 重复：${role.id}`
      ids.add(role.id)
      if (!role.label.trim()) return `${prefix}缺少名称`
      if (!role.model.trim()) return `${prefix}缺少固定模型名`
      if (!role.api_type.trim() || !role.wire_api.trim()) return `${prefix}缺少接口约束`
    }
    return ''
  }

  const saveRecipe = async () => {
    const validationError = validateRecipe()
    if (validationError) {
      setError(validationError)
      return
    }
    setSavingRecipe(true)
    try {
      const manifest = parseManifest(detail, files)
      manifest.llm_recipe = {
        schema: 'cartridgeflow.llm_recipe.v1',
        roles: roles.map((role) => ({
          id: role.id.trim(),
          label: role.label.trim(),
          capability: role.capability,
          api_type: role.api_type,
          wire_api: role.wire_api,
          model: role.model.trim(),
          required: role.required,
        })),
      }
      await saveLabFlowFile(flowId, 'manifest', `${JSON.stringify(manifest, null, 2)}\n`)

      const currentBindings = assignments.cartridges?.[flowId] || {}
      const retainedIds = new Set(roles.map((role) => role.id))
      const syncedBindings = Object.fromEntries(Object.entries(currentBindings)
        .filter(([roleId]) => retainedIds.has(roleId))
        .map(([roleId, binding]) => {
          const role = roles.find((item) => item.id === roleId)
          return [roleId, { ...binding, model: role?.model || binding.model }]
        }))
      if (JSON.stringify(currentBindings) !== JSON.stringify(syncedBindings)) {
        const nextAssignments = {
          ...assignments,
          cartridges: { ...assignments.cartridges, [flowId]: syncedBindings },
        }
        const result = await saveLlmAssignments(nextAssignments)
        setAssignments(result.assignments)
      }
      setDirty(false)
      setError('')
      await onRefresh()
      showToast({ title: '模型配方已保存', type: 'success' })
    } catch (reason: any) {
      setError(reason?.message || '模型配方保存失败')
      showToast({ title: '模型配方保存失败', description: reason?.message, type: 'error' })
    } finally {
      setSavingRecipe(false)
    }
  }

  const bindProvider = async (role: LlmRecipeRole, providerId: string) => {
    setSavingBinding(role.id)
    try {
      const cartridgeBindings = { ...(assignments.cartridges?.[flowId] || {}) }
      if (providerId) cartridgeBindings[role.id] = { provider_id: providerId, model: role.model }
      else delete cartridgeBindings[role.id]
      const nextAssignments: LlmAssignments = {
        ...assignments,
        cartridges: { ...assignments.cartridges, [flowId]: cartridgeBindings },
      }
      const result = await saveLlmAssignments(nextAssignments)
      setAssignments(result.assignments)
      setError('')
      showToast({ title: providerId ? '本机连接已绑定' : '本机连接已解除', type: 'success' })
    } catch (reason: any) {
      setError(reason?.message || '本机连接保存失败')
    } finally {
      setSavingBinding('')
    }
  }

  return (
    <div className="cf-model-recipe-page">
      <section className="cf-model-summary">
        <div>
          <span className="cf-model-eyebrow">Portable Recipe</span>
          <h2>模型角色与本机连接</h2>
          <p>卡带只保存角色、能力和模型约束；URL 与 Key 仅保留在当前底座。</p>
        </div>
        <div className="cf-model-summary-stats" aria-label="模型配方状态">
          <div><strong>{roles.length}</strong><span>模型角色</span></div>
          <div className={requiredIssues.length ? 'warning' : 'ok'}><strong>{requiredIssues.length}</strong><span>必需项待处理</span></div>
        </div>
        <div className="cf-model-summary-actions">
          <button type="button" className="cf-model-secondary" onClick={() => void loadLocalConnections()} disabled={loading}>重新检测</button>
          {editable && <button type="button" className="cf-model-primary" onClick={() => void saveRecipe()} disabled={savingRecipe || !dirty}>{savingRecipe ? '保存中...' : '保存配方'}</button>}
        </div>
      </section>

      {error && <div className="cf-model-alert danger">{error}</div>}
      <div className="cf-model-alert privacy">
        <b>本机凭据隔离</b>
        <span>发布或复制卡带时不会携带连接地址与密钥。缺失项需在当前底座的 <code>.data/user/config/llm/providers.json</code> 中补齐。</span>
      </div>

      <div className="cf-model-section-head">
        <div><span>Recipe Roles</span><h3>配方角色</h3></div>
        {editable && <button type="button" className="cf-model-add" onClick={addRole}>添加角色</button>}
      </div>

      {loading && roles.length === 0 ? (
        <div className="cf-model-empty">正在读取本机连接...</div>
      ) : roles.length === 0 ? (
        <div className="cf-model-empty">
          <strong>这个卡带暂不需要模型</strong>
          <span>需要文本、视觉或生图能力时，在这里添加模型角色。</span>
          {editable && <button type="button" onClick={addRole}>添加第一个角色</button>}
        </div>
      ) : (
        <div className="cf-model-role-list">
          {roles.map((role, index) => {
            const status = readiness[index]
            const binding = assignments.cartridges?.[flowId]?.[role.id]
            return (
              <article className="cf-model-role" key={`${index}-${role.id}`}>
                <div className="cf-model-role-head">
                  <div className="cf-model-role-index">{String(index + 1).padStart(2, '0')}</div>
                  <div className="cf-model-role-title">
                    <strong>{role.label || role.id || '未命名角色'}</strong>
                    <code>{role.id || 'role_id'}</code>
                  </div>
                  <span className={`cf-model-status ${status?.state || 'unbound'}`}>{roleStateLabel(status?.state || 'unbound')}</span>
                  {editable && <button type="button" className="cf-model-remove" onClick={() => removeRole(index)} aria-label={`删除 ${role.label || role.id}`}>删除</button>}
                </div>

                <div className="cf-model-role-body">
                  <div className="cf-model-recipe-fields">
                    <label><span>角色 ID</span><input value={role.id} disabled={!editable} onChange={(event) => updateRole(index, { id: event.target.value })} /></label>
                    <label><span>显示名称</span><input value={role.label} disabled={!editable} onChange={(event) => updateRole(index, { label: event.target.value })} /></label>
                    <label><span>能力</span><select value={role.capability} disabled={!editable} onChange={(event) => {
                      const capability = event.target.value
                      updateRole(index, { capability, wire_api: defaultWireApi(role.api_type, capability) })
                    }}>{CAPABILITIES.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label>
                    <label><span>接口类型</span><select value={role.api_type} disabled={!editable} onChange={(event) => {
                      const apiType = event.target.value
                      updateRole(index, { api_type: apiType, wire_api: defaultWireApi(apiType, role.capability) })
                    }}>{API_TYPES.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label>
                    <label><span>调用协议</span><select value={role.wire_api} disabled={!editable} onChange={(event) => updateRole(index, { wire_api: event.target.value })}>{WIRE_APIS.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label>
                    <label><span>固定模型</span><input value={role.model} disabled={!editable} placeholder="例如 gpt-4.1-mini" onChange={(event) => updateRole(index, { model: event.target.value })} /></label>
                    <label className="cf-model-required"><input type="checkbox" checked={role.required} disabled={!editable} onChange={(event) => updateRole(index, { required: event.target.checked })} /><span>运行必需</span></label>
                  </div>

                  <div className="cf-model-local-binding">
                    <div className="cf-model-binding-head"><span>Local Binding</span><b>本机 Provider</b></div>
                    <select
                      value={binding?.provider_id || ''}
                      disabled={savingBinding === role.id || dirty}
                      onChange={(event) => void bindProvider(role, event.target.value)}
                    >
                      <option value="">未绑定</option>
                      {providers.map((provider) => <option key={provider.id} value={provider.id}>{provider.name} · {provider.api_type}</option>)}
                    </select>
                    <div className={`cf-model-binding-result ${status?.state || 'unbound'}`}>
                      <strong>{dirty ? '请先保存配方，再绑定本机 Provider' : status?.message || '未绑定本机 Provider；URL / Key 待填写'}</strong>
                      {status?.provider && <span>{status.provider.base_url || 'URL 未填写'} · {status.provider.has_key ? 'Key 已存在' : 'Key 未填写'}</span>}
                    </div>
                    <dl>
                      <div><dt>卡带约束</dt><dd>{role.api_type} / {role.wire_api}</dd></div>
                      <div><dt>模型</dt><dd>{role.model || '未填写'}</dd></div>
                    </dl>
                  </div>
                </div>
              </article>
            )
          })}
        </div>
      )}
    </div>
  )
}
