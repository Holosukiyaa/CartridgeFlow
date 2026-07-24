import { useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import {
  fetchStudioResources,
  saveLabFlowFile,
  saveStudioResources,
  type FlowFiles,
  type FlowLabDetail,
  type ResourceRequirement,
  type StudioResources,
  type StudioToolResource,
} from '../../api.ts'
import { showToast } from '../../toast.tsx'
import { ModelRecipeView } from './ModelRecipeView.tsx'

function parseManifest(detail: FlowLabDetail, files: FlowFiles) {
  if (files.manifest) {
    try { return JSON.parse(files.manifest) } catch { /* The workbench reports malformed files elsewhere. */ }
  }
  return JSON.parse(JSON.stringify(detail.cartridge.manifest || {}))
}

function normalizeKind(kind: string) {
  return ({ remote: 'remote_api', web: 'remote_api', structured: 'remote_api', local_path: 'plugin' } as Record<string, string>)[kind] || kind
}

function toolMatches(tool: StudioToolResource, requirement: ResourceRequirement) {
  const accepted = new Set((requirement.kinds || []).map(normalizeKind))
  if (accepted.size && !accepted.has(normalizeKind(tool.kind || ''))) return false
  const capabilities = new Set(tool.capabilities || [])
  if ((requirement.capabilities || []).some((capability) => !capabilities.has(capability))) return false
  return requirement.constraints?.read_only !== true || tool.read_only === true
}

function copyBindings(resources: StudioResources) {
  return {
    roles: Object.fromEntries(Object.entries(resources.bindings.roles || {}).map(([id, roles]) => [id, { ...roles }])),
    tools: Object.fromEntries(Object.entries(resources.bindings.tools || {}).map(([id, values]) => [id, [...values]])),
  }
}

function ToolRequirementsView({ detail, files, flowId, editable, onRefresh }: {
  detail: FlowLabDetail
  files: FlowFiles
  flowId: string
  editable: boolean
  onRefresh: () => Promise<void>
}) {
  const [requirements, setRequirements] = useState<ResourceRequirement[]>([])
  const [resources, setResources] = useState<StudioResources | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [dirty, setDirty] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    const manifest = parseManifest(detail, files)
    setRequirements(Array.isArray(manifest.resource_requirements)
      ? manifest.resource_requirements.map((item: ResourceRequirement) => ({
        role: String(item.role || ''),
        kinds: [...(item.kinds || [])],
        required: item.required !== false,
        capabilities: [...(item.capabilities || [])],
        constraints: { ...(item.constraints || {}) },
      }))
      : [])
    setDirty(false)
  }, [detail, files.manifest, flowId])

  async function loadResources() {
    setLoading(true)
    try {
      setResources(await fetchStudioResources())
      setError('')
    } catch (reason: any) {
      setError(reason?.message || '读取本机工具连接失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void loadResources() }, [flowId])

  const assignedCount = useMemo(
    () => requirements.filter((item) => resources?.bindings.roles?.[flowId]?.[item.role]).length,
    [flowId, requirements, resources],
  )

  function updateRequirement(index: number, patch: Partial<ResourceRequirement>) {
    setRequirements((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, ...patch } : item))
    setDirty(true)
  }

  function addRequirement() {
    let number = requirements.length + 1
    let role = `tool_role_${number}`
    while (requirements.some((item) => item.role === role)) { number += 1; role = `tool_role_${number}` }
    setRequirements((current) => [...current, { role, kinds: ['remote_api'], required: true, capabilities: [], constraints: {} }])
    setDirty(true)
  }

  function removeRequirement(index: number) {
    setRequirements((current) => current.filter((_, itemIndex) => itemIndex !== index))
    setDirty(true)
  }

  async function saveRequirements() {
    if (!resources) return
    const roles = new Set<string>()
    for (const [index, requirement] of requirements.entries()) {
      if (!requirement.role || !/^[A-Za-z0-9_.-]+$/.test(requirement.role)) { setError(`工具角色 ${index + 1} 的 ID 无效`); return }
      if (roles.has(requirement.role)) { setError(`工具角色 ID 重复：${requirement.role}`); return }
      if (!requirement.kinds?.length) { setError(`工具角色 ${requirement.role} 至少需要一种连接类型`); return }
      roles.add(requirement.role)
    }
    setSaving(true)
    try {
      const manifest = parseManifest(detail, files)
      manifest.resource_requirements = requirements.map((item) => ({
        role: item.role.trim(),
        kinds: (item.kinds || []).map((value) => value.trim()).filter(Boolean),
        required: item.required !== false,
        capabilities: (item.capabilities || []).map((value) => value.trim()).filter(Boolean),
        ...(item.constraints?.read_only === true ? { constraints: { read_only: true } } : {}),
      }))
      await saveLabFlowFile(flowId, 'manifest', `${JSON.stringify(manifest, null, 2)}\n`)

      const bindings = copyBindings(resources)
      const retained = new Set(requirements.map((item) => item.role))
      const currentRoles = bindings.roles[flowId] || {}
      const nextRoles = Object.fromEntries(Object.entries(currentRoles).filter(([role]) => retained.has(role)))
      if (Object.keys(nextRoles).length) bindings.roles[flowId] = nextRoles
      else delete bindings.roles[flowId]
      const result = await saveStudioResources({ version: 1, tools: resources.tools, bindings, builtin_tools: [] })
      setResources({ ...result.resources, builtin_tools: resources.builtin_tools })
      setDirty(false)
      setError('')
      await onRefresh()
      showToast({ title: '卡带工具需求已保存', type: 'success' })
    } catch (reason: any) {
      setError(reason?.message || '保存卡带工具需求失败')
    } finally {
      setSaving(false)
    }
  }

  async function bindTool(requirement: ResourceRequirement, toolId: string) {
    if (!resources) return
    if (dirty) { setError('请先保存工具需求，再修改本机分配'); return }
    const tool = resources.tools.find((item) => item.id === toolId)
    if (tool && !toolMatches(tool, requirement)) { setError('这个工具不满足当前角色的类型或能力约束'); return }
    const bindings = copyBindings(resources)
    const roles = { ...(bindings.roles[flowId] || {}) }
    if (toolId) roles[requirement.role] = toolId
    else delete roles[requirement.role]
    if (Object.keys(roles).length) bindings.roles[flowId] = roles
    else delete bindings.roles[flowId]
    try {
      const result = await saveStudioResources({ version: 1, tools: resources.tools, bindings, builtin_tools: [] })
      setResources({ ...result.resources, builtin_tools: resources.builtin_tools })
      setError('')
      showToast({ title: toolId ? '本机工具已绑定' : '本机工具已解除', type: 'success' })
    } catch (reason: any) {
      setError(reason?.message || '保存本机工具分配失败')
    }
  }

  return (
    <div className="cf-cartridge-tools-page">
      <section className="cf-model-summary cf-cartridge-tool-summary">
        <div><span className="cf-model-eyebrow">Portable Requirements</span><h2>工具需求与本机连接</h2><p>卡带声明需要什么工具；当前底座选择具体连接，地址和凭据不会写入卡带。</p></div>
        <div className="cf-model-summary-stats"><div><strong>{requirements.length}</strong><span>工具角色</span></div><div className={assignedCount === requirements.length ? 'ok' : 'warning'}><strong>{assignedCount}</strong><span>已绑定本机资源</span></div></div>
        <div className="cf-model-summary-actions"><button type="button" className="cf-model-secondary" onClick={() => void loadResources()} disabled={loading}>刷新连接</button>{editable && <button type="button" className="cf-model-primary" onClick={() => void saveRequirements()} disabled={!dirty || saving}>{saving ? '保存中…' : '保存需求'}</button>}</div>
      </section>

      {error && <div className="cf-model-alert danger">{error}</div>}
      <div className="cf-model-alert privacy"><b>双向配置</b><span>这里从卡带角色选择本机资源；模型 API、工具地址和密钥统一在 <Link to="/resources/config">资源配置</Link> 中维护。</span></div>
      <div className="cf-model-section-head"><div><span>Tool Requirements</span><h3>工具角色</h3></div>{editable && <button type="button" className="cf-model-add" onClick={addRequirement}>添加角色</button>}</div>

      {!requirements.length && !loading ? <div className="cf-model-empty"><strong>这个卡带暂不需要外部工具</strong><span>需要文生图、检索、MCP 或远程 API 时，在这里添加工具角色。</span>{editable && <button type="button" onClick={addRequirement}>添加第一个工具角色</button>}</div> : <div className="cf-cartridge-tool-role-list">
        {requirements.map((requirement, index) => {
          const bindingId = resources?.bindings.roles?.[flowId]?.[requirement.role] || ''
          const binding = resources?.tools.find((item) => item.id === bindingId)
          const candidates = (resources?.tools || []).filter((item) => toolMatches(item, requirement))
          return <article className="cf-cartridge-tool-role" key={`${index}-${requirement.role}`}>
            <div className="cf-cartridge-tool-role-head"><span>{String(index + 1).padStart(2, '0')}</span><div><strong>{requirement.role || '未命名工具角色'}</strong><small>{binding ? `已绑定 ${binding.name}` : '尚未绑定本机工具'}</small></div><b className={binding ? 'ready' : 'unbound'}>{binding ? '已连接' : '未连接'}</b>{editable && <button type="button" onClick={() => removeRequirement(index)}>删除</button>}</div>
            <div className="cf-cartridge-tool-fields">
              <label>角色 ID<input value={requirement.role} disabled={!editable} onChange={(event) => updateRequirement(index, { role: event.target.value })} /></label>
              <label>允许的连接类型<input value={(requirement.kinds || []).join(', ')} disabled={!editable} onChange={(event) => updateRequirement(index, { kinds: event.target.value.split(',').map((item) => item.trim()).filter(Boolean) })} placeholder="remote_api, mcp" /></label>
              <label>所需能力<input value={(requirement.capabilities || []).join(', ')} disabled={!editable} onChange={(event) => updateRequirement(index, { capabilities: event.target.value.split(',').map((item) => item.trim()).filter(Boolean) })} placeholder="image_generation" /></label>
              <label>本机工具<select value={bindingId} disabled={dirty} onChange={(event) => void bindTool(requirement, event.target.value)}><option value="">未绑定</option>{candidates.map((tool) => <option key={tool.id} value={tool.id}>{tool.name}</option>)}</select></label>
              <label className="cf-cartridge-tool-check"><input type="checkbox" checked={requirement.required !== false} disabled={!editable} onChange={(event) => updateRequirement(index, { required: event.target.checked })} /><span>运行时必需</span></label>
              <label className="cf-cartridge-tool-check"><input type="checkbox" checked={requirement.constraints?.read_only === true} disabled={!editable} onChange={(event) => updateRequirement(index, { constraints: { ...(requirement.constraints || {}), read_only: event.target.checked } })} /><span>只允许只读工具</span></label>
            </div>
          </article>
        })}
      </div>}
    </div>
  )
}

export function CartridgeResourcesView(props: {
  detail: FlowLabDetail
  files: FlowFiles
  flowId: string
  editable: boolean
  onRefresh: () => Promise<void>
}) {
  const [searchParams] = useSearchParams()
  const [tab, setTab] = useState<'models' | 'tools'>(() => searchParams.get('resourceTab') === 'tools' ? 'tools' : 'models')
  return (
    <section className="cf-cartridge-resources-view">
      <nav className="cf-cartridge-resource-tabs" aria-label="卡带资源类型"><button type="button" className={tab === 'models' ? 'active' : ''} onClick={() => setTab('models')}>模型需求</button><button type="button" className={tab === 'tools' ? 'active' : ''} onClick={() => setTab('tools')}>工具需求</button><Link to="/resources/config">本地资源配置</Link></nav>
      {tab === 'models' ? <ModelRecipeView {...props} /> : <ToolRequirementsView {...props} />}
    </section>
  )
}
