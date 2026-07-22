import { useEffect, useMemo, useState } from 'react'
import {
  fetchLabFlows,
  fetchStudioResources,
  saveStudioResources,
  type CartridgeSummary,
  type ResourceRequirement,
  type StudioResources,
  type StudioToolResource,
} from '../api.ts'
import ConfigModal from '../components/ConfigModal.tsx'

const emptyTool: StudioToolResource = {
  id: '', name: '', kind: 'mcp', description: '', endpoint: '', command: '', args: '',
  openapi_url: '', http_method: 'POST', auth_env: '', auth_header: 'Authorization',
  auth_scheme: 'Bearer', capabilities: [], read_only: false, package_mode: 'descriptor', enabled: true,
}

const toolKinds = [
  { value: 'mcp', label: 'MCP 服务' },
  { value: 'remote_api', label: '远程 API / Swagger' },
  { value: 'plugin', label: 'CLI / 基座插件' },
]

const kindAliases: Record<string, string> = {
  remote: 'remote_api', web: 'remote_api', structured: 'remote_api', local_path: 'plugin',
}

function normalizeKind(kind: string) { return kindAliases[kind] || kind }

function resourceMatchesRequirement(item: StudioToolResource, requirement: ResourceRequirement) {
  const accepted = new Set((requirement.kinds || []).map(normalizeKind))
  if (accepted.size && !accepted.has(normalizeKind(item.kind || ''))) return false
  const available = new Set(item.capabilities || [])
  if ((requirement.capabilities || []).some((capability) => !available.has(capability))) return false
  return requirement.constraints?.read_only !== true || item.read_only === true
}

function copyBindings(resources: StudioResources) {
  return {
    roles: Object.fromEntries(Object.entries(resources.bindings.roles || {}).map(([id, roles]) => [id, { ...roles }])),
    tools: Object.fromEntries(Object.entries(resources.bindings.tools || {}).map(([id, values]) => [id, [...values]])),
  }
}

function itemLabel(item: StudioToolResource) {
  if (item.kind === 'builtin') return '底座内置'
  if (item.kind === 'mcp') return 'MCP'
  if (item.kind === 'remote_api') return '远程 API'
  return '基座插件'
}

export default function ResourceConfigPage() {
  const [resources, setResources] = useState<StudioResources | null>(null)
  const [flows, setFlows] = useState<CartridgeSummary[]>([])
  const [selectedId, setSelectedId] = useState('')
  const [draft, setDraft] = useState<StudioToolResource>({ ...emptyTool })
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [editorOpen, setEditorOpen] = useState(false)

  const inventory = useMemo(
    () => resources ? [...(resources.builtin_tools || []), ...resources.tools] : [],
    [resources],
  )
  const selectedResource = inventory.find((item) => item.id === selectedId)

  async function load() {
    setLoading(true)
    setError('')
    try {
      const [resourceResult, flowResult] = await Promise.all([fetchStudioResources(), fetchLabFlows()])
      setResources(resourceResult)
      setFlows(flowResult.items || [])
      const first = [...(resourceResult.builtin_tools || []), ...resourceResult.tools][0]
      if (first && !selectedId) { setSelectedId(first.id); setDraft({ ...first }) }
    } catch (reason: any) {
      setError(reason?.message || '读取工具配置失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void load() }, [])

  function startNew() {
    setSelectedId('')
    setDraft({ ...emptyTool })
    setNotice('')
    setEditorOpen(true)
  }

  function selectItem(item: StudioToolResource) {
    setSelectedId(item.id)
    setDraft({ ...item })
    setNotice('')
  }

  async function persist(tools: StudioToolResource[], bindings = resources?.bindings) {
    if (!resources) throw new Error('工具配置尚未载入')
    const result = await saveStudioResources({ version: 1, tools, bindings: bindings || { roles: {}, tools: {} }, builtin_tools: [] })
    setResources({ ...result.resources, builtin_tools: resources.builtin_tools })
    return result.resources
  }

  async function saveItem(event: React.FormEvent) {
    event.preventDefault()
    if (!resources || !draft.name?.trim()) { setError('请填写工具名称'); return }
    if (draft.kind === 'mcp' && !draft.endpoint?.trim() && !draft.command?.trim()) { setError('MCP 服务需要地址或启动命令'); return }
    if (draft.kind === 'remote_api' && !draft.endpoint?.trim() && !draft.openapi_url?.trim()) { setError('远程 API 需要 Endpoint 或 OpenAPI URL'); return }
    if (draft.kind === 'plugin' && !draft.endpoint?.trim() && !draft.command?.trim()) { setError('基座插件需要入口地址或启动命令'); return }
    setSaving(true)
    setError('')
    try {
      const tools = [...resources.tools]
      const item = { ...draft, name: draft.name.trim(), id: draft.id.trim() || draft.name.trim() }
      const index = tools.findIndex((entry) => entry.id === selectedId)
      if (index >= 0) tools[index] = item
      else tools.push(item)
      const saved = await persist(tools)
      const savedItem = saved.tools.find((entry) => entry.id === item.id)
        || saved.tools.find((entry) => entry.name === item.name && entry.kind === item.kind)
      if (savedItem) { setSelectedId(savedItem.id); setDraft({ ...savedItem }) }
      setEditorOpen(false)
      setNotice('工具已保存')
    } catch (reason: any) {
      setError(reason?.message || '保存工具失败')
    } finally {
      setSaving(false)
    }
  }

  async function deleteItem() {
    if (!resources || !selectedId || !window.confirm('删除这个全局工具？')) return
    const bindings = copyBindings(resources)
    for (const cartridgeId of Object.keys(bindings.tools)) bindings.tools[cartridgeId] = bindings.tools[cartridgeId].filter((id) => id !== selectedId)
    for (const cartridgeId of Object.keys(bindings.roles)) {
      bindings.roles[cartridgeId] = Object.fromEntries(Object.entries(bindings.roles[cartridgeId]).filter(([, resourceId]) => resourceId !== selectedId))
      if (!Object.keys(bindings.roles[cartridgeId]).length) delete bindings.roles[cartridgeId]
    }
    try {
      await persist(resources.tools.filter((item) => item.id !== selectedId), bindings)
      setSelectedId('')
      setDraft({ ...emptyTool })
      setEditorOpen(false)
      setNotice('工具已删除')
    } catch (reason: any) { setError(reason?.message || '删除工具失败') }
  }

  async function bindToRole(cartridgeId: string, requirement: ResourceRequirement, resourceId: string) {
    if (!resources) return
    const resource = resources.tools.find((item) => item.id === resourceId)
    if (!resource || !resourceMatchesRequirement(resource, requirement)) { setError('这个工具不符合卡带角色要求'); return }
    const bindings = copyBindings(resources)
    bindings.roles[cartridgeId] = { ...(bindings.roles[cartridgeId] || {}), [requirement.role]: resourceId }
    try { await persist(resources.tools, bindings); setNotice(`工具角色 ${requirement.role} 已连接`) }
    catch (reason: any) { setError(reason?.message || '保存卡带绑定失败') }
  }

  async function unbindRole(cartridgeId: string, role: string) {
    if (!resources) return
    const bindings = copyBindings(resources)
    const cartridgeRoles = { ...(bindings.roles[cartridgeId] || {}) }
    delete cartridgeRoles[role]
    if (Object.keys(cartridgeRoles).length) bindings.roles[cartridgeId] = cartridgeRoles
    else delete bindings.roles[cartridgeId]
    try { await persist(resources.tools, bindings); setNotice(`工具角色 ${role} 已解除`) }
    catch (reason: any) { setError(reason?.message || '保存卡带绑定失败') }
  }

  function setField(field: string, value: any) { setDraft((current) => ({ ...current, [field]: value })) }

  return (
    <div className="cf-resource-page">
      <header className="cf-resource-heading">
        <div><span className="cf-resource-kicker">BASE / TOOLS</span><h1>工具配置</h1><p>本机只保存 MCP、远程 API 和基座插件的连接；卡带只声明需要的工具角色。</p></div>
        <div className="cf-resource-heading-meta"><b>{inventory.length}</b><span>个可用工具</span></div>
      </header>
      {error && <div className="cf-resource-alert danger">{error}</div>}
      {notice && <div className="cf-resource-alert success">{notice}</div>}
      <div className="cf-resource-layout">
        <section className="cf-resource-panel cf-resource-inventory-panel">
          <div className="cf-resource-panel-head"><div><span>TOOL INVENTORY</span><h2>全局工具</h2></div><button type="button" onClick={startNew}>新增</button></div>
          <div className="cf-resource-inventory-list">
            {inventory.map((item) => <button key={item.id} type="button" className={`cf-resource-inventory-item ${selectedId === item.id ? 'selected' : ''} ${item.locked ? 'locked' : ''}`} onClick={() => selectItem(item)}><span className="cf-resource-type">{itemLabel(item)}</span><span className="cf-resource-item-copy"><strong>{item.name}</strong><small>{item.description || (item.kind === 'builtin' ? `${item.server}/${item.tool}` : item.endpoint || item.command || '尚未填写连接')}</small></span><i>{item.package_mode || '引用'}</i></button>)}
            {!inventory.length && !loading && <div className="cf-resource-empty">还没有登记工具</div>}
          </div>
          {selectedResource ? <div className="cf-selected-resource-summary">
            <div className="cf-selected-resource-title"><span>SELECTED TOOL</span><strong>{selectedResource.name}</strong><code>{selectedResource.id}</code></div>
            <dl><div><dt>类型</dt><dd>{itemLabel(selectedResource)}</dd></div><div><dt>连接</dt><dd>{selectedResource.endpoint || selectedResource.command || (selectedResource.server && selectedResource.tool ? `${selectedResource.server}/${selectedResource.tool}` : '未填写')}</dd></div><div><dt>认证</dt><dd>{selectedResource.auth_env || '无需凭据'}</dd></div><div><dt>迁移</dt><dd>{selectedResource.locked ? '由底座提供' : '只携带工具声明'}</dd></div></dl>
            <div className="cf-model-form-actions">{!selectedResource.locked && <><button type="button" className="primary" onClick={() => setEditorOpen(true)}>编辑工具</button><button type="button" className="danger" onClick={() => void deleteItem()}>删除</button></>}</div>
          </div> : <div className="cf-selection-hint"><strong>选择一个工具</strong><span>查看连接详情，或新增一个本机工具。</span></div>}
        </section>

        <section className="cf-resource-panel cf-resource-binding-panel">
          <div className="cf-resource-panel-head"><div><span>CARTRIDGE BINDINGS</span><h2>卡带工具角色</h2></div><small>本机连接不会写入卡带</small></div>
          <div className="cf-resource-binding-list">
            {flows.map((flow) => {
              const requirements = flow.resource_requirements || []
              const roleBindings = resources?.bindings?.roles?.[flow.id] || {}
              const boundCount = requirements.filter((item) => roleBindings[item.role]).length
              return <article key={flow.id} className="cf-cartridge-resource-row">
                <div className="cf-cartridge-resource-head"><div><strong>{flow.name}</strong><code>{flow.id}</code></div><span>{requirements.length ? `${boundCount}/${requirements.length} 个角色已连接` : '未声明工具角色'}</span></div>
                {requirements.length ? <div className="cf-model-role-drop-list">{requirements.map((requirement) => {
                  const resourceId = roleBindings[requirement.role] || ''
                  const resource = resources?.tools.find((item) => item.id === resourceId)
                  const candidates = (resources?.tools || []).filter((item) => resourceMatchesRequirement(item, requirement))
                  return <div key={requirement.role} className={`cf-model-role-drop ${resource ? 'bound' : ''}`}>
                    <span className="cf-role-drop-name"><b>{requirement.role}</b><code>{requirement.required === false ? '可选' : '必需'} · {(requirement.kinds || []).map(normalizeKind).join(' / ')}</code></span>
                    <span className="cf-role-drop-value">{resource ? `已连接 ${resource.name}` : '尚未绑定本机工具'}</span>
                    <select className="cf-role-binding-select" value={resourceId} onChange={(event) => event.target.value ? void bindToRole(flow.id, requirement, event.target.value) : void unbindRole(flow.id, requirement.role)} aria-label={`为 ${requirement.role} 选择本机工具`}><option value="">未绑定</option>{candidates.map((item) => <option key={item.id} value={item.id}>{item.name} · {itemLabel(item)}</option>)}</select>
                  </div>
                })}</div> : <div className="cf-resource-empty compact">卡带没有声明工具角色</div>}
              </article>
            })}
            {!flows.length && !loading && <div className="cf-resource-empty">还没有可绑定的卡带</div>}
          </div>
        </section>
      </div>

      <ConfigModal open={editorOpen} title={selectedId ? `编辑 ${draft.name}` : '新增工具'} kicker="GLOBAL TOOL" onClose={() => setEditorOpen(false)}>
        <form className="cf-resource-editor" onSubmit={saveItem} autoComplete="off">
          <label>工具名称<input value={draft.name || ''} onChange={(e) => setField('name', e.target.value)} placeholder="例如：内容检索 API" /></label>
          <label>标识（可留空）<input value={draft.id || ''} disabled={Boolean(selectedId)} onChange={(e) => setField('id', e.target.value)} placeholder="自动生成" /></label>
          <label>类型<select value={draft.kind || ''} onChange={(e) => setField('kind', e.target.value)}>{toolKinds.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label>
          <label>服务地址 / Endpoint<input value={draft.endpoint || ''} onChange={(e) => setField('endpoint', e.target.value)} placeholder="远程服务地址；本地 stdio 可留空" /></label>
          {['mcp', 'plugin'].includes(draft.kind) && <div className="cf-resource-form-row"><label>启动命令 / 入口<input value={draft.command || ''} onChange={(e) => setField('command', e.target.value)} placeholder="例如：npx server" /></label><label>参数<input value={draft.args || ''} onChange={(e) => setField('args', e.target.value)} placeholder="JSON 或空格分隔" /></label></div>}
          {draft.kind === 'remote_api' && <><label>OpenAPI / Swagger URL<input value={draft.openapi_url || ''} onChange={(e) => setField('openapi_url', e.target.value)} placeholder="https://.../openapi.json" /></label><label>默认 HTTP 方法<select value={draft.http_method || 'POST'} onChange={(e) => setField('http_method', e.target.value)}>{['GET', 'POST', 'PUT', 'PATCH', 'DELETE'].map((method) => <option key={method} value={method}>{method}</option>)}</select></label></>}
          <label>认证环境变量<input value={draft.auth_env || ''} onChange={(e) => setField('auth_env', e.target.value.toUpperCase())} placeholder="例如：SEARCH_API_KEY" /></label>
          <div className="cf-resource-form-row"><label>认证 Header<input value={draft.auth_header || ''} onChange={(e) => setField('auth_header', e.target.value)} placeholder="Authorization" /></label><label>认证前缀<input value={draft.auth_scheme || ''} onChange={(e) => setField('auth_scheme', e.target.value)} placeholder="Bearer" /></label></div>
          <label>能力标签<input value={(draft.capabilities || []).join(', ')} onChange={(e) => setField('capabilities', e.target.value.split(',').map((item) => item.trim()).filter(Boolean))} placeholder="例如：search, documents" /></label>
          <label className="cf-environment-secret-toggle"><input type="checkbox" checked={draft.read_only === true} onChange={(e) => setField('read_only', e.target.checked)} /><span>这个工具只执行读取操作</span></label>
          <label>迁移策略<select value={draft.package_mode || 'descriptor'} onChange={(e) => setField('package_mode', e.target.value)}><option value="descriptor">卡带只携带工具声明</option><option value="external">保持外部引用</option></select></label>
          <label>备注<textarea value={draft.description || ''} onChange={(e) => setField('description', e.target.value)} rows={2} /></label>
          <div className="cf-config-modal-actions"><button type="button" onClick={() => setEditorOpen(false)}>取消</button><button type="submit" className="primary" disabled={saving}>{saving ? '保存中…' : '保存工具'}</button></div>
        </form>
      </ConfigModal>
    </div>
  )
}
