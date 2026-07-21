import { useEffect, useMemo, useState } from 'react'
import { fetchLabFlows, fetchStudioResources, saveStudioResources, type CartridgeSummary, type ResourceRequirement, type StudioResources, type StudioSourceResource, type StudioToolResource } from '../api.ts'
import ConfigModal from '../components/ConfigModal.tsx'

type ResourceMode = 'tools' | 'sources'
type ResourceItem = (StudioToolResource | StudioSourceResource) & {
  locked?: boolean
  server?: string
  tool?: string
  endpoint?: string
  location?: string
}

const emptyTool: StudioToolResource = { id: '', name: '', kind: 'mcp', description: '', endpoint: '', command: '', args: '', openapi_url: '', auth_env: '', capabilities: [], read_only: false, package_mode: 'descriptor', enabled: true }
const emptySource: StudioSourceResource = { id: '', name: '', kind: 'local_path', description: '', location: '', format: 'auto', auth_env: '', capabilities: [], read_only: true, refresh_mode: 'manual', package_mode: 'reference', enabled: true }

const toolKinds = [{ value: 'mcp', label: 'MCP 服务' }, { value: 'remote_api', label: '远程 API / Swagger' }, { value: 'plugin', label: '底座插件' }]
const sourceKinds = [{ value: 'local_path', label: '本地文件 / 文件夹' }, { value: 'web', label: '网页 / API' }, { value: 'structured', label: '结构化连接' }]
const toolKindIds = new Set(toolKinds.map((item) => item.value))
const sourceKindIds = new Set(sourceKinds.map((item) => item.value))

function normalizeKind(kind: string) {
  return kind === 'remote' ? 'remote_api' : kind
}

function requirementForMode(requirement: ResourceRequirement, isTools: boolean) {
  const accepted = new Set((requirement.kinds || []).map(normalizeKind))
  const kinds = isTools ? toolKindIds : sourceKindIds
  return [...accepted].some((kind) => kinds.has(kind))
}

function resourceMatchesRequirement(item: ResourceItem, requirement: ResourceRequirement) {
  const accepted = new Set((requirement.kinds || []).map(normalizeKind))
  if (!accepted.has(normalizeKind(item.kind || ''))) return false
  const available = new Set(item.capabilities || [])
  if ((requirement.capabilities || []).some((capability) => !available.has(capability))) return false
  if (requirement.constraints?.read_only === true && item.read_only !== true) return false
  return true
}

function copyBindings(resources: StudioResources) {
  return {
    roles: Object.fromEntries(Object.entries(resources.bindings.roles || {}).map(([id, roles]) => [id, { ...roles }])),
    tools: Object.fromEntries(Object.entries(resources.bindings.tools || {}).map(([id, values]) => [id, [...values]])),
    sources: Object.fromEntries(Object.entries(resources.bindings.sources || {}).map(([id, values]) => [id, [...values]])),
  }
}

function itemLabel(item: ResourceItem) {
  if (item.kind === 'builtin') return '底座内置'
  if (item.kind === 'mcp') return 'MCP'
  if (item.kind === 'remote_api') return '远程 API'
  if (item.kind === 'plugin') return '插件'
  if (item.kind === 'local_path') return '本地路径'
  if (item.kind === 'web') return '网页 / API'
  return '结构化'
}

export default function ResourceConfigPage({ mode }: { mode: ResourceMode }) {
  const isTools = mode === 'tools'
  const [resources, setResources] = useState<StudioResources | null>(null)
  const [flows, setFlows] = useState<CartridgeSummary[]>([])
  const [selectedId, setSelectedId] = useState('')
  const [draft, setDraft] = useState<ResourceItem>(isTools ? { ...emptyTool } : { ...emptySource })
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [editorOpen, setEditorOpen] = useState(false)

  const inventory = useMemo<ResourceItem[]>(() => {
    if (!resources) return []
    return (isTools ? [...(resources.builtin_tools || []), ...resources.tools] : resources.sources) as ResourceItem[]
  }, [isTools, resources])
  const selectedResource = inventory.find((item) => item.id === selectedId)

  async function load() {
    setLoading(true)
    setError('')
    try {
      const [resourceResult, flowResult] = await Promise.all([fetchStudioResources(), fetchLabFlows()])
      setResources(resourceResult)
      setFlows(flowResult.items || [])
      if (!selectedId) {
        const first = isTools ? [...(resourceResult.builtin_tools || []), ...resourceResult.tools][0] : resourceResult.sources[0]
        if (first) { setSelectedId(first.id); setDraft({ ...first }) }
      }
    } catch (reason: any) {
      setError(reason?.message || '读取资源配置失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void load() }, [mode])

  function startNew() {
    setSelectedId('')
    setDraft(isTools ? { ...emptyTool } : { ...emptySource })
    setNotice('')
    setEditorOpen(true)
  }

  function selectItem(item: ResourceItem) {
    setSelectedId(item.id)
    setDraft({ ...item })
    setNotice('')
  }

  function editSelected() {
    if (!selectedId || draft.locked) return
    setEditorOpen(true)
  }

  async function saveItem(event: React.FormEvent) {
    event.preventDefault()
    if (!resources || !draft.name?.trim()) { setError('请填写资源名称'); return }
    if (isTools) {
      const tool = draft as StudioToolResource
      if (tool.kind === 'mcp' && !tool.endpoint?.trim() && !tool.command?.trim()) { setError('MCP 服务需要填写服务地址或启动命令'); return }
      if (tool.kind === 'remote_api' && !tool.endpoint?.trim() && !tool.openapi_url?.trim()) { setError('远程 API 需要填写 Endpoint 或 OpenAPI URL'); return }
      if (tool.kind === 'plugin' && !tool.endpoint?.trim() && !tool.command?.trim()) { setError('底座插件需要填写入口地址或启动命令'); return }
    } else if (!(draft as StudioSourceResource).location?.trim()) {
      setError('数据来源需要填写位置或 URL')
      return
    }
    setSaving(true)
    setError('')
    try {
      const list = isTools ? [...resources.tools] : [...resources.sources]
      const item = { ...draft, name: draft.name.trim(), id: draft.id.trim() || draft.name.trim() } as ResourceItem
      const index = list.findIndex((entry) => entry.id === selectedId)
      if (index >= 0) list[index] = item as never
      else list.push(item as never)
      const payload = { version: 1, tools: isTools ? list : resources.tools, sources: isTools ? resources.sources : list, bindings: resources.bindings }
      const result = await saveStudioResources(payload)
      setResources({ ...result.resources, builtin_tools: resources.builtin_tools })
      const savedList = isTools ? result.resources.tools : result.resources.sources
      const savedItem = savedList.find((entry) => entry.id === item.id) || savedList.find((entry) => entry.name === item.name && entry.kind === item.kind)
      if (savedItem) {
        setSelectedId(savedItem.id)
        setDraft({ ...savedItem })
      }
      setEditorOpen(false)
      setNotice('资源已保存')
    } catch (reason: any) {
      setError(reason?.message || '保存资源失败')
    } finally {
      setSaving(false)
    }
  }

  async function deleteItem() {
    if (!resources || !selectedId || !window.confirm('删除这个全局资源？')) return
    const list = isTools ? resources.tools.filter((item) => item.id !== selectedId) : resources.sources.filter((item) => item.id !== selectedId)
    const bindings = copyBindings(resources)
    const key = isTools ? 'tools' : 'sources'
    for (const cartridgeId of Object.keys(bindings[key] || {})) bindings[key][cartridgeId] = (bindings[key][cartridgeId] || []).filter((id) => id !== selectedId)
    for (const cartridgeId of Object.keys(bindings.roles)) {
      bindings.roles[cartridgeId] = Object.fromEntries(Object.entries(bindings.roles[cartridgeId]).filter(([, resourceId]) => resourceId !== selectedId))
      if (!Object.keys(bindings.roles[cartridgeId]).length) delete bindings.roles[cartridgeId]
    }
    try {
      const result = await saveStudioResources({ version: 1, tools: isTools ? list : resources.tools, sources: isTools ? resources.sources : list, bindings })
      setResources({ ...result.resources, builtin_tools: resources.builtin_tools })
      setSelectedId('')
      setDraft(isTools ? { ...emptyTool } : { ...emptySource })
      setEditorOpen(false)
      setNotice('资源已删除')
    } catch (reason: any) {
      setError(reason?.message || '删除资源失败')
    }
  }

  async function bindToRole(cartridgeId: string, requirement: ResourceRequirement, resourceId: string) {
    if (!resources) return
    const resource = inventory.find((item) => item.id === resourceId && !item.locked)
    if (!resource || !resourceMatchesRequirement(resource, requirement)) {
      setError('这个资源不符合卡带角色要求')
      return
    }
    const bindings = copyBindings(resources)
    bindings.roles[cartridgeId] = { ...(bindings.roles[cartridgeId] || {}), [requirement.role]: resourceId }
    try {
      const result = await saveStudioResources({ version: 1, tools: resources.tools, sources: resources.sources, bindings })
      setResources({ ...result.resources, builtin_tools: resources.builtin_tools })
      setNotice(`资源角色 ${requirement.role} 已绑定`)
    } catch (reason: any) {
      setError(reason?.message || '保存卡带绑定失败')
    }
  }

  async function unbindRole(cartridgeId: string, role: string) {
    if (!resources) return
    const bindings = copyBindings(resources)
    const cartridgeRoles = { ...(bindings.roles[cartridgeId] || {}) }
    delete cartridgeRoles[role]
    if (Object.keys(cartridgeRoles).length) bindings.roles[cartridgeId] = cartridgeRoles
    else delete bindings.roles[cartridgeId]
    try {
      const result = await saveStudioResources({ version: 1, tools: resources.tools, sources: resources.sources, bindings })
      setResources({ ...result.resources, builtin_tools: resources.builtin_tools })
      setNotice(`资源角色 ${role} 已解除`)
    } catch (reason: any) {
      setError(reason?.message || '保存卡带绑定失败')
    }
  }

  function onDragStart(event: React.DragEvent, item: ResourceItem) {
    event.dataTransfer.setData('application/x-cf-resource', item.id)
    event.dataTransfer.effectAllowed = 'link'
  }

  function setField(field: string, value: any) {
    setDraft((current) => ({ ...current, [field]: value } as ResourceItem))
  }

  return (
    <div className="cf-resource-page">
      <header className="cf-resource-heading">
        <div><span className="cf-resource-kicker">BASE / {isTools ? 'TOOLS' : 'SOURCES'}</span><h1>{isTools ? '工具配置' : '数据来源'}</h1><p>{isTools ? '统一登记 MCP、远程 API 与底座插件，再按卡带声明绑定。' : '统一登记可复用的本地、网页和结构化数据入口。'}</p></div>
        <div className="cf-resource-heading-meta"><b>{inventory.length}</b><span>{isTools ? '个可用工具' : '个数据来源'}</span></div>
      </header>
      {error && <div className="cf-resource-alert danger">{error}</div>}
      {notice && <div className="cf-resource-alert success">{notice}</div>}
      <div className="cf-resource-layout">
        <section className="cf-resource-panel cf-resource-inventory-panel">
          <div className="cf-resource-panel-head"><div><span>{isTools ? 'TOOL INVENTORY' : 'SOURCE INVENTORY'}</span><h2>全局清单</h2></div><button type="button" onClick={startNew}>新增</button></div>
          <div className="cf-resource-inventory-list">
            {inventory.map((item) => <button key={item.id} type="button" draggable={!item.locked} onDragStart={(event) => { if (!item.locked) onDragStart(event, item) }} className={`cf-resource-inventory-item ${selectedId === item.id ? 'selected' : ''} ${item.locked ? 'locked' : ''}`} onClick={() => selectItem(item)}><span className="cf-resource-type">{itemLabel(item)}</span><span className="cf-resource-item-copy"><strong>{item.name}</strong><small>{item.description || (item.kind === 'builtin' ? `${item.server}/${item.tool}` : item.endpoint || item.location || '尚未填写位置')}</small></span><i>{item.package_mode || '引用'}</i></button>)}
            {!inventory.length && !loading && <div className="cf-resource-empty">还没有登记资源</div>}
          </div>
          {selectedResource ? <div className="cf-selected-resource-summary">
            <div className="cf-selected-resource-title"><span>SELECTED RESOURCE</span><strong>{selectedResource.name}</strong><code>{selectedResource.id}</code></div>
            <dl><div><dt>类型</dt><dd>{itemLabel(selectedResource)}</dd></div><div><dt>位置</dt><dd>{selectedResource.endpoint || selectedResource.location || (selectedResource.server && selectedResource.tool ? `${selectedResource.server}/${selectedResource.tool}` : '未填写')}</dd></div><div><dt>认证</dt><dd>{selectedResource.auth_env || '无需凭据'}</dd></div><div><dt>打包</dt><dd>{selectedResource.package_mode || '引用'}</dd></div></dl>
            <div className="cf-model-form-actions">{!selectedResource.locked && <><button type="button" className="primary" onClick={editSelected}>编辑资源</button><button type="button" className="danger" onClick={() => void deleteItem()}>删除</button></>}<span className="cf-drag-hint">拖动此项可绑定到右侧卡带</span></div>
          </div> : <div className="cf-selection-hint"><strong>{isTools ? '选择一个工具' : '选择一个数据来源'}</strong><span>查看配置详情，或点击“新增”登记全局资源。</span></div>}
        </section>

        <section className="cf-resource-panel cf-resource-binding-panel">
          <div className="cf-resource-panel-head"><div><span>CARTRIDGE BINDINGS</span><h2>卡带绑定</h2></div><small>拖动或下拉添加资源</small></div>
          <div className="cf-resource-binding-list">
            {flows.map((flow) => {
              const requirements = (flow.resource_requirements || []).filter((item) => requirementForMode(item, isTools))
              const roleBindings = resources?.bindings?.roles?.[flow.id] || {}
              const boundCount = requirements.filter((item) => roleBindings[item.role]).length
              return <article key={flow.id} className="cf-cartridge-resource-row">
                <div className="cf-cartridge-resource-head"><div><strong>{flow.name}</strong><code>{flow.id}</code></div><span>{requirements.length ? `${boundCount}/${requirements.length} 个角色已绑定` : '无资源角色'}</span></div>
                {requirements.length ? <div className="cf-model-role-drop-list">{requirements.map((requirement) => {
                  const resourceId = roleBindings[requirement.role] || ''
                  const resource = inventory.find((item) => item.id === resourceId)
                  const candidates = inventory.filter((item) => !item.locked && resourceMatchesRequirement(item, requirement))
                  return <div
                    key={requirement.role}
                    className={`cf-model-role-drop ${resource ? 'bound' : ''}`}
                    onDragOver={(event) => event.preventDefault()}
                    onDrop={(event) => { event.preventDefault(); const id = event.dataTransfer.getData('application/x-cf-resource'); if (id) void bindToRole(flow.id, requirement, id) }}
                  >
                    <span className="cf-role-drop-name"><b>{requirement.role}</b><code>{requirement.required === false ? '可选' : '必需'} · {(requirement.kinds || []).join(' / ')}</code></span>
                    <span className="cf-role-drop-value">{resource ? `已连接 ${resource.name}` : '尚未绑定本机资源'}</span>
                    <select
                      className="cf-role-binding-select"
                      value={resourceId}
                      onChange={(event) => event.target.value ? void bindToRole(flow.id, requirement, event.target.value) : void unbindRole(flow.id, requirement.role)}
                      aria-label={`为 ${requirement.role} 选择本机资源`}
                    >
                      <option value="">未绑定</option>
                      {candidates.map((item) => <option key={item.id} value={item.id}>{item.name} · {itemLabel(item)}</option>)}
                    </select>
                  </div>
                })}</div> : <div className="cf-resource-empty compact">卡带没有声明这一类资源角色</div>}
              </article>
            })}
            {!flows.length && !loading && <div className="cf-resource-empty">还没有可绑定的卡带</div>}
          </div>
        </section>
      </div>
      <ConfigModal open={editorOpen} title={selectedId ? `编辑 ${draft.name}` : `新增${isTools ? '工具' : '数据来源'}`} kicker={isTools ? 'GLOBAL TOOL' : 'GLOBAL DATA SOURCE'} onClose={() => setEditorOpen(false)}>
        <form className="cf-resource-editor" onSubmit={saveItem} autoComplete="off">
          <label>资源名称<input autoComplete="off" value={draft.name || ''} onChange={(e) => setField('name', e.target.value)} placeholder={isTools ? '例如：内容搜索 API' : '例如：产品文档'} /></label>
          <label>标识（可留空）<input autoComplete="off" value={draft.id || ''} disabled={Boolean(selectedId)} onChange={(e) => setField('id', e.target.value)} placeholder="自动生成" /></label>
          <label>类型<select value={draft.kind || ''} onChange={(e) => setField('kind', e.target.value)}>{(isTools ? toolKinds : sourceKinds).map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label>
          {isTools ? <>
            <label>服务地址 / Endpoint<input autoComplete="off" value={(draft as StudioToolResource).endpoint || ''} onChange={(e) => setField('endpoint', e.target.value)} placeholder="远程服务地址；本地 stdio 可留空" /></label>
            {['mcp', 'plugin'].includes((draft as StudioToolResource).kind) && <div className="cf-resource-form-row"><label>启动命令 / 入口<input autoComplete="off" value={(draft as StudioToolResource).command || ''} onChange={(e) => setField('command', e.target.value)} placeholder="例如：npx server" /></label><label>参数<input autoComplete="off" value={(draft as StudioToolResource).args || ''} onChange={(e) => setField('args', e.target.value)} placeholder="JSON 或空格分隔" /></label></div>}
            {(draft as StudioToolResource).kind === 'remote_api' && <label>OpenAPI / Swagger URL<input autoComplete="off" value={(draft as StudioToolResource).openapi_url || ''} onChange={(e) => setField('openapi_url', e.target.value)} placeholder="https://.../openapi.json" /></label>}
            <label>认证环境变量<input autoComplete="off" value={(draft as StudioToolResource).auth_env || ''} onChange={(e) => setField('auth_env', e.target.value.toUpperCase())} placeholder="例如：SEARCH_API_KEY" /></label>
            <label>能力标签<input autoComplete="off" value={(draft.capabilities || []).join(', ')} onChange={(e) => setField('capabilities', e.target.value.split(',').map((item) => item.trim()).filter(Boolean))} placeholder="例如：search, documents" /></label>
            <label className="cf-environment-secret-toggle"><input type="checkbox" checked={draft.read_only === true} onChange={(e) => setField('read_only', e.target.checked)} /><span>这个资源只执行读取操作</span></label>
            <label>打包策略<select value={draft.package_mode || 'descriptor'} onChange={(e) => setField('package_mode', e.target.value)}><option value="descriptor">随卡带携带声明</option><option value="external">保持外部引用</option></select></label>
          </> : <>
            <label>位置 / URL<input autoComplete="off" value={(draft as StudioSourceResource).location || ''} onChange={(e) => setField('location', e.target.value)} placeholder="路径或 https://..." /></label>
            <div className="cf-resource-form-row"><label>格式<input autoComplete="off" value={(draft as StudioSourceResource).format || ''} onChange={(e) => setField('format', e.target.value)} placeholder="auto / md / json" /></label><label>刷新<select value={(draft as StudioSourceResource).refresh_mode || 'manual'} onChange={(e) => setField('refresh_mode', e.target.value)}><option value="manual">手动</option><option value="run">运行前</option><option value="scheduled">定时</option></select></label></div>
            <label>认证环境变量<input autoComplete="off" value={(draft as StudioSourceResource).auth_env || ''} onChange={(e) => setField('auth_env', e.target.value.toUpperCase())} placeholder="可选" /></label>
            <label>能力标签<input autoComplete="off" value={(draft.capabilities || []).join(', ')} onChange={(e) => setField('capabilities', e.target.value.split(',').map((item) => item.trim()).filter(Boolean))} placeholder="例如：documents, product_data" /></label>
            <label>打包策略<select value={draft.package_mode || 'reference'} onChange={(e) => setField('package_mode', e.target.value)}><option value="reference">随卡带保留引用</option><option value="snapshot">打包快照</option><option value="external">保持外部引用</option></select></label>
          </>}
          <label>备注<textarea value={draft.description || ''} onChange={(e) => setField('description', e.target.value)} rows={2} /></label>
          <div className="cf-config-modal-actions"><button type="button" onClick={() => setEditorOpen(false)}>取消</button><button type="submit" className="primary" disabled={saving}>{saving ? '保存中…' : '保存资源'}</button></div>
        </form>
      </ConfigModal>
    </div>
  )
}
