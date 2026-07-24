import { pageTemplates } from './pages.js?v=20260724-live-1'
import { componentSystem } from './component-system.js?v=20260724-components-1'
import {
  animateDisclosure,
  animateModalClose,
  animateModalOpen,
  animateNavSelection,
  animatePageEnter,
  animateRefresh,
  animateRowRemoval,
  animateSelection,
  animateSettingPreview,
  animateToast,
  setUserReducedMotion,
} from './motion-system.js?v=20260724-assets-1'

const API_BASE = window.location.port === '5174' ? 'http://127.0.0.1:8765' : ''

const api = async (path, options = {}) => {
  const headers = new Headers(options.headers || {})
  if (options.body && !(options.body instanceof FormData) && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json')
  const response = await fetch(`${API_BASE}${path}`, { ...options, headers })
  if (!response.ok) {
    const raw = await response.text()
    let payload = null
    try { payload = JSON.parse(raw) } catch { /* keep the plain response */ }
    const detail = payload?.detail
    const message = payload?.error_envelope?.message
      || (typeof detail === 'string' ? detail : detail?.message)
      || raw
      || `请求失败: ${response.status}`
    const error = new Error(message)
    error.status = response.status
    error.payload = payload
    throw error
  }
  return response.json()
}

const apiText = async (path, options = {}) => {
  const response = await fetch(`${API_BASE}${path}`, options)
  if (!response.ok) throw new Error((await response.text()) || `请求失败: ${response.status}`)
  return response.text()
}

const $ = (selector) => document.querySelector(selector)
const liveState = {
  flows: [],
  runs: [],
  providers: [],
  resources: null,
  environment: null,
  base: null,
  conformance: null,
  packages: [],
  selectedRunId: '',
  selectedReleaseId: '',
  currentPage: 'overview',
}

const escapeHtml = (value) => String(value ?? '')
  .replaceAll('&', '&amp;')
  .replaceAll('<', '&lt;')
  .replaceAll('>', '&gt;')
  .replaceAll('"', '&quot;')
  .replaceAll("'", '&#039;')
const shortText = (value, max = 30) => {
  const text = String(value || '')
  return text.length > max ? `${text.slice(0, max - 1)}…` : text
}

const completedStatuses = new Set(['completed', 'succeeded', 'success'])
const activeStatuses = new Set(['created', 'pending', 'running', 'recovering', 'paused_waiting_user'])
const waitingStatuses = new Set(['created', 'pending', 'recovering', 'paused_waiting_user'])

function renderIcons() {
  window.lucide?.createIcons({ attrs: { 'stroke-width': 1.8 } })
}

function formatTime(value) {
  if (!value) return '暂无记录'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  const today = new Date()
  const sameDay = date.toDateString() === today.toDateString()
  return sameDay
    ? `今天 ${date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}`
    : date.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

function statusLabel(status) {
  return ({
    created: '已创建', pending: '等待中', running: '进行中', recovering: '恢复中', paused_waiting_user: '等待输入',
    completed: '已完成', succeeded: '已完成', success: '已完成', failed: '失败', cancelled: '已取消', paused: '已暂停',
  })[status] || status || '未知'
}

function statusTone(status) {
  if (status === 'failed') return 'red'
  if (completedStatuses.has(status)) return 'green'
  if (activeStatuses.has(status)) return 'blue'
  return 'amber'
}

const lineIcon = (name) => `<i class="line-icon" data-lucide="${name}" aria-hidden="true"></i>`

function liveStateMarkup(message, error = false) {
  return `<div class="live-state ${error ? 'error' : ''}">${lineIcon(error ? 'circle-alert' : 'loader')}<strong>${escapeHtml(message)}</strong>${error ? '<button class="page-button" data-action="retry-page">重试</button>' : ''}</div>`
}

function flowCardMarkup(flow) {
  const protocol = flow.runtime_contract?.protocol
  const protocolVersion = flow.runtime_contract?.protocol_version
  const protocolLabel = protocol ? `${protocol}${protocolVersion ? `@${protocolVersion}` : ''}` : '未声明'
  const runtime = flow.runtime?.type || flow.runtime?.adapter || '未声明'
  const tools = (flow.mcp_tools || []).length
  return `<article class="flow-card" data-flow-id="${escapeHtml(flow.id)}">
    <button class="flow-card-open" data-action="open-flow" data-flow-id="${escapeHtml(flow.id)}"><span class="tone-dot ${flow.editable ? 'green' : 'blue'}"></span><strong>${escapeHtml(flow.name || flow.id)}</strong>${flow.editable ? '<span class="editable-dot"></span><em>开发中可修改</em>' : '<em>已安装</em>'}<span class="flow-enter">进入工作台 ${lineIcon('arrow-right')}</span></button>
    <p>${escapeHtml(flow.description || '未填写卡带说明')}</p>
    <div class="flow-meta">
      <span><small>卡带 ID</small><b>${escapeHtml(flow.id)}</b></span><span><small>版本</small><b>${escapeHtml(flow.version || '—')}</b></span><span><small>协议</small><b>${escapeHtml(protocolLabel)}</b></span><span><small>来源</small><b>${flow.editable ? '本机开发' : escapeHtml(flow.source || '已安装')}</b></span><span><small>工具 / 运行</small><b>${tools} / ${escapeHtml(runtime)}</b></span>
    </div>
    <div class="flow-card-actions"><button data-action="open-flow" data-flow-id="${escapeHtml(flow.id)}">${lineIcon('square-pen')}编辑卡带</button><button data-action="bind-flow-resources" data-flow-id="${escapeHtml(flow.id)}">${lineIcon('link')}绑定资源</button><button data-action="open-flow-directory" data-flow-id="${escapeHtml(flow.id)}">${lineIcon('folder')}打开目录</button><button class="danger-text" data-action="delete-flow" data-flow-id="${escapeHtml(flow.id)}" ${flow.editable ? '' : 'disabled'}>${lineIcon('trash-2')}删除卡带</button></div>
  </article>`
}

function flowCreateCardMarkup() {
  return `<button class="flow-create-card" data-action="create-flow">
    <span class="flow-create-icon">${lineIcon('plus')}</span>
    <span class="flow-create-copy"><strong>新建开发卡带</strong><small>从空白 Flow 开始组织流程、配方与交付内容</small></span>
    <span class="flow-create-enter">开始创建 ${lineIcon('arrow-right')}</span>
  </button>`
}

function renderFlowsPage(items) {
  const page = document.querySelector('.flows-page')
  if (!page) return
  liveState.flows = items
  const scroll = page.querySelector('.flows-scroll')
  if (!items.length) {
    page.classList.add('empty-mode')
    scroll.innerHTML = `<div class="flow-empty-panel"><div class="empty-blueprint"><div class="blueprint-cube">${lineIcon('package-open')}</div><div class="blueprint-workflow">${lineIcon('workflow')}</div></div><h2>从第一张卡带开始</h2><p>创建开发卡带，或导入已有的可迁移卡带包。</p><div class="empty-actions"><button class="page-button primary" data-action="create-flow">创建开发卡带</button><button class="page-button" data-action="import-flow">导入已有卡带</button></div></div>`
  } else {
    page.classList.remove('empty-mode')
    scroll.innerHTML = `<div class="section-row"><h2>开发卡带 <span>${items.length}</span></h2></div><div class="flow-card-grid">${items.map(flowCardMarkup).join('')}${flowCreateCardMarkup()}</div>`
  }
  renderIcons()
}

async function loadFlowsPage() {
  const scroll = document.querySelector('.flows-page .flows-scroll')
  if (!scroll) return
  scroll.innerHTML = liveStateMarkup('正在读取本机卡带')
  try {
    const payload = await api('/api/lab/flows')
    if (liveState.currentPage !== 'flows') return
    renderFlowsPage(payload.items || [])
  } catch (error) {
    scroll.innerHTML = liveStateMarkup(error.message, true)
    renderIcons()
  }
}

function runRowMarkup(run) {
  const tone = statusTone(run.status)
  return `<button class="run-row ${run.run_id === liveState.selectedRunId ? 'selected' : ''}" data-run-id="${escapeHtml(run.run_id)}" data-status="${escapeHtml(run.status)}" title="${escapeHtml(`${run.cartridge_id} / ${run.run_id}`)}"><i class="tone-dot ${tone}"></i><span><strong title="${escapeHtml(run.cartridge_id)}">${escapeHtml(run.cartridge_id)}</strong><small title="${escapeHtml(run.run_id)}">${escapeHtml(run.run_id)}</small></span><em class="${tone}-text">${escapeHtml(statusLabel(run.status))}${run.current_state ? `<small title="${escapeHtml(run.current_state)}">${escapeHtml(run.current_state)}</small>` : ''}</em><time>${escapeHtml(formatTime(run.updated_at || run.created_at))}</time></button>`
}

function renderDiagnosticDetail(run, bundle) {
  const container = document.querySelector('.diagnostic-detail')
  if (!container) return
  if (!run) {
    container.innerHTML = liveStateMarkup('暂无运行记录')
    renderIcons()
    return
  }
  const error = run.error || (run.errors || []).at(-1) || null
  const events = bundle?.events || []
  const checkpoints = bundle?.checkpoints || []
  const summary = bundle?.summary || {}
  const artifacts = run.artifacts || []
  const duration = run.created_at && run.updated_at ? Math.max(0, (new Date(run.updated_at) - new Date(run.created_at)) / 1000).toFixed(2) : '—'
  const canRetry = Boolean(error?.retryable)
  container.innerHTML = `<div class="selected-run panel-frame">
      <div class="selected-run-main"><span class="failure-badge ${run.status === 'failed' ? '' : 'neutral'}">${escapeHtml(statusLabel(run.status))}</span><strong>${escapeHtml(run.cartridge_id)}</strong><small>run_id: ${escapeHtml(run.run_id)}</small></div>
      <div><small>当前节点</small><b>${escapeHtml(run.current_state || '—')}</b></div><div><small>时间</small><b>${escapeHtml(formatTime(run.updated_at || run.created_at))}</b><small>耗时 ${duration}s</small></div>
      <div class="selected-actions"><button class="page-button" data-action="open-run-workbench" data-flow-id="${escapeHtml(run.cartridge_id)}">${lineIcon('play')}打开测试台</button><button class="page-button" data-action="copy-diagnostic">${lineIcon('copy')}复制最近诊断</button><button class="page-button" data-action="export-diagnostic">${lineIcon('download')}导出 JSON</button><button class="page-button danger-text" data-action="delete-run">${lineIcon('trash-2')}删除记录</button></div>
    </div>
    <div class="cause-recovery panel-frame"><div class="root-cause"><h2>根因</h2><dl><dt>错误码</dt><dd class="${error ? 'red-text' : ''}">${escapeHtml(error?.code || '无')}</dd><dt>说明</dt><dd>${escapeHtml(error?.message || '当前运行没有记录错误。')}</dd><dt>分类</dt><dd>${escapeHtml(error?.category || '—')}</dd><dt>节点</dt><dd>${escapeHtml(error?.node_id || run.current_state || '—')}</dd><dt>可重试</dt><dd class="${canRetry ? 'green-text' : 'red-text'}">${canRetry ? '是' : '否'}</dd></dl></div>
      <div class="recovery-actions"><h2>恢复动作</h2><button data-action="retry-run" ${canRetry ? '' : 'disabled'}>${lineIcon('refresh-cw')}重试当前节点${canRetry ? '' : '（不可用）'}<small>${canRetry ? '重新执行失败节点' : '当前错误不允许直接重试'}</small></button><button data-action="restart-run">${lineIcon('rotate-ccw')}使用原始输入重开<small>基于本次运行的原始输入重新执行 Flow</small></button></div></div>
    <div class="evidence-grid"><div class="event-panel panel-frame"><div class="panel-title"><h2>事件时间线</h2><span>${events.length} 项</span></div><div class="timeline">${events.length ? events.map((event) => `<div class="timeline-row ${String(event.type).includes('failed') ? 'error' : ''}" title="${escapeHtml(event.message || event.type)}"><time>${escapeHtml(formatTime(event.created_at))}</time><i></i><span><b>${escapeHtml(shortText(event.message || event.type))}</b><small>${escapeHtml(event.type || '事件')}</small></span><b>${lineIcon('chevron-down')}</b></div>`).join('') : '<div class="compact-inline-empty">暂无事件</div>'}</div></div>
      <div class="checkpoint-panel panel-frame"><div class="panel-title"><h2>检查点</h2><span>${checkpoints.length} 项</span></div><div class="checkpoint-table"><div class="table-head"><span>检查点名称</span><span>时间</span><span>状态</span><span>可用性</span></div>${checkpoints.length ? checkpoints.map((checkpoint) => { const ok = checkpoint.outcome === 'completed'; const failed = checkpoint.outcome === 'failed'; return `<div><span>${escapeHtml(checkpoint.node_id || checkpoint.checkpoint_id)}</span><span>${escapeHtml(formatTime(checkpoint.created_at))}</span><span class="checkpoint-state ${ok ? 'green-text' : failed ? 'red-text' : ''}">${ok ? lineIcon('circle-check') + '完成' : failed ? lineIcon('circle-x') + '失败' : escapeHtml(checkpoint.outcome || checkpoint.phase || '已记录')}</span><span class="${checkpoint.replay?.replay_safe ? 'green-text' : ''}">${checkpoint.replay?.replay_safe ? '可安全恢复' : '仅供诊断'}</span></div>` }).join('') : '<div class="compact-inline-empty">暂无检查点</div>'}</div></div></div>
    <div class="artifact-strip panel-frame"><div data-action="toggle-disclosure" role="button" tabindex="0" aria-expanded="true"><h2>产物与交付 <span>（${artifacts.length || summary.artifact_count || 0} 项）</span></h2><b>${lineIcon('chevron-up')}</b></div><p><strong>${artifacts.length ? '运行产物已记录' : '暂无产物'}</strong><small>${artifacts.length ? artifacts.map((item) => item.name || item.path).filter(Boolean).join(' · ') : '当前运行未生成任何产物或交付物。'}</small></p></div>`
  renderIcons()
}

async function selectRun(runId) {
  liveState.selectedRunId = runId
  document.querySelectorAll('.run-row').forEach((row) => row.classList.toggle('selected', row.dataset.runId === runId))
  const container = document.querySelector('.diagnostic-detail')
  if (container) container.innerHTML = liveStateMarkup('正在读取诊断证据')
  try {
    const bundle = await api(`/api/cartridge-runs/${encodeURIComponent(runId)}/diagnostics`)
    if (liveState.currentPage !== 'diagnostics' || liveState.selectedRunId !== runId) return
    renderDiagnosticDetail(bundle.run, bundle)
  } catch (error) {
    if (container) container.innerHTML = liveStateMarkup(error.message, true)
    renderIcons()
  }
}

function applyRunFilter() {
  const query = (document.querySelector('[data-run-search]')?.value || '').trim().toLowerCase()
  const status = document.querySelector('.run-tabs button.active')?.dataset.status || 'all'
  document.querySelectorAll('.run-row').forEach((row) => {
    const matchesQuery = !query || row.textContent.toLowerCase().includes(query)
    const rowStatus = row.dataset.status
    const matchesStatus = status === 'all'
      || (status === 'failed' && rowStatus === 'failed')
      || (status === 'active' && activeStatuses.has(rowStatus))
      || (status === 'completed' && completedStatuses.has(rowStatus))
    row.hidden = !(matchesQuery && matchesStatus)
  })
}

async function loadDiagnosticsPage() {
  const list = document.querySelector('.diagnostics-page .run-list')
  const detail = document.querySelector('.diagnostic-detail')
  if (!list || !detail) return
  list.innerHTML = liveStateMarkup('正在读取运行记录')
  detail.innerHTML = liveStateMarkup('请选择一条运行记录')
  try {
    const payload = await api('/api/cartridge-runs')
    if (liveState.currentPage !== 'diagnostics') return
    const runs = payload.items || []
    liveState.runs = runs
    liveState.selectedRunId = runs.some((run) => run.run_id === liveState.selectedRunId) ? liveState.selectedRunId : (runs.find((run) => run.status === 'failed') || runs[0])?.run_id || ''
    const failed = runs.filter((run) => run.status === 'failed').length
    const active = runs.filter((run) => activeStatuses.has(run.status)).length
    const completed = runs.filter((run) => completedStatuses.has(run.status)).length
    const metricValues = document.querySelectorAll('.header-run-metrics b')
    ;[runs.length, failed, active, completed].forEach((value, index) => { if (metricValues[index]) metricValues[index].textContent = String(value) })
    list.innerHTML = runs.length ? runs.map(runRowMarkup).join('') : liveStateMarkup('暂无运行记录')
    renderIcons()
    if (liveState.selectedRunId) await selectRun(liveState.selectedRunId)
    else renderDiagnosticDetail(null, null)
  } catch (error) {
    list.innerHTML = liveStateMarkup(error.message, true)
    detail.innerHTML = liveStateMarkup('诊断详情暂时不可用', true)
    renderIcons()
  }
}

function renderResourceModalData(providers, resources) {
  const modal = document.querySelector('.resource-modal')
  if (!modal) return
  const externalTools = resources?.tools || []
  const summaryValues = modal.querySelectorAll('.modal-summary b')
  if (summaryValues[1]) summaryValues[1].textContent = `${providers.length} 个`
  if (summaryValues[2]) summaryValues[2].textContent = `${externalTools.length} 个`
  if (summaryValues[3]) summaryValues[3].innerHTML = `刚刚同步 ${lineIcon('refresh-cw')}`

  const table = modal.querySelector('.modal-table')
  if (table) {
    const rows = providers.length ? providers.map((provider, index) => `<div><span class="resource-brand-name">${lineIcon('brain-circuit')}${escapeHtml(provider.name || provider.id)}</span><span>${escapeHtml(provider.default_model || '未选择')}</span><span>${escapeHtml(provider.adapter_label || '普通模型')}</span><span class="${provider.tested_ok ? 'green-text' : 'orange-text'} modal-state">${lineIcon(provider.tested_ok ? 'circle-check' : 'circle-alert')}${provider.tested_ok ? '连接正常' : '需要测试'}</span><span>${index === 0 ? '<b class="default-pill">默认</b>' : '—'}</span><span>由卡带配方绑定</span><span>${escapeHtml(provider.tested_at ? formatTime(provider.tested_at) : '尚未测试')}</span><span class="blue-text">${provider.enabled === false ? '已停用' : '已启用'}</span></div>`).join('') : '<div class="modal-empty-row">暂无模型连接</div>'
    table.innerHTML = `<div class="table-head"><span>模型名称</span><span>模型 ID</span><span>模型类型</span><span>连接状态</span><span>默认</span><span>角色分配</span><span>最近测试时间</span><span>状态</span></div>${rows}<footer>共 ${providers.length} 条 <span>${lineIcon('chevron-left')}<b>1</b>${lineIcon('chevron-right')}10 条/页 ${lineIcon('chevron-down')}</span></footer>`
  }

  const toolPanel = modal.querySelector('.modal-tool-empty')
  if (toolPanel) {
    if (externalTools.length) {
      toolPanel.classList.add('has-tools')
      toolPanel.innerHTML = externalTools.map((tool) => `<div class="modal-tool-row"><span>${lineIcon(tool.kind === 'mcp' ? 'plug-zap' : 'cloud')}<strong>${escapeHtml(tool.name || tool.id)}</strong></span><em>${escapeHtml(tool.kind || 'tool')}</em><b class="${tool.enabled === false ? '' : 'green-text'}">${tool.enabled === false ? '已停用' : '已启用'}</b></div>`).join('')
    } else {
      toolPanel.classList.remove('has-tools')
      toolPanel.innerHTML = `<div>${lineIcon('plug-zap')}</div><strong>当前为空</strong><p>外部 API、OpenAPI、MCP 与用户自部署服务均从这里接入。</p><button class="page-button primary" type="button">${lineIcon('plus')}新增工具连接</button>`
    }
  }
}

function renderResourcesPage(providers, resources, environment) {
  const content = document.querySelector('.resources-content')
  if (!content) return
  const externalTools = resources?.tools || []
  const builtinTools = resources?.builtin_tools || []
  const allTools = [...builtinTools, ...externalTools]
  const enabledTools = allTools.filter((tool) => tool.enabled !== false)
  const readyProviders = providers.filter((provider) => provider.enabled !== false && provider.has_key && provider.base_url && provider.default_model && provider.tested_ok)
  const credentials = environment?.references || []
  const configured = credentials.filter((item) => item.configured)
  const checks = environment?.checks || []
  const warnings = checks.filter((check) => check.status !== 'ok')
  const providerRows = providers.length ? providers.map((provider) => `<div><span class="resource-brand-name">${lineIcon('brain-circuit')}${escapeHtml(provider.name || provider.id)}</span><span>${escapeHtml(provider.default_model || '未选择')}</span><span>${escapeHtml(provider.wire_api || provider.api_type || '—')}</span><span class="status-pill ${provider.tested_ok ? 'green' : 'amber'}">${lineIcon(provider.tested_ok ? 'circle-check' : 'circle-alert')}${provider.tested_ok ? '连接正常' : '需要测试'}</span><span class="${provider.enabled === false ? '' : 'blue-text'}">${provider.enabled === false ? '已停用' : '已启用'}</span><span><button data-action="open-resource-config">配置</button></span></div>`).join('') : '<div class="compact-inline-empty">暂无模型连接</div>'
  const toolBody = externalTools.length ? `<div class="tool-live-list">${externalTools.slice(0, 5).map((tool) => `<div><span>${lineIcon(tool.kind === 'mcp' ? 'plug-zap' : 'cloud')}<b>${escapeHtml(tool.name || tool.id)}</b></span><em>${escapeHtml(tool.kind || 'tool')}</em><strong class="${tool.enabled === false ? '' : 'green-text'}">${tool.enabled === false ? '停用' : '启用'}</strong></div>`).join('')}</div>` : `<div class="compact-empty"><div>${lineIcon('briefcase-business')}</div><strong>暂无外部工具</strong><p>底座内置 ${builtinTools.length} 项工具；外部 API、OpenAPI 和 MCP 在配置器中接入。</p><span><button class="page-button orange-text" data-action="open-resource-config">配置工具</button></span></div>`
  content.innerHTML = `<div class="resource-summary panel-frame"><span>${lineIcon('box')}<em>模型连接<b class="${readyProviders.length ? 'green-text' : 'blue-text'}">${readyProviders.length}/${providers.length}</b></em></span><span>${lineIcon('wrench')}<em>工具资源<b class="blue-text">${enabledTools.length}/${allTools.length}</b></em></span><span>${lineIcon('clipboard-list')}<em>待处理状态<b class="${warnings.length ? 'orange-text' : 'green-text'}">${warnings.length}</b></em></span><span>${lineIcon('code-xml')}<em>本机凭据<b class="blue-text">${configured.length}/${credentials.length}</b></em></span></div>
    <div class="resource-main-grid"><article class="resource-table-card panel-frame"><h2>模型连接</h2><div class="resource-table"><div class="table-head"><span>资源名称</span><span>模型名</span><span>协议</span><span>状态</span><span>使用状态</span><span>操作</span></div>${providerRows}</div></article><article class="tool-empty-card panel-frame"><h2>工具连接</h2>${toolBody}</article></div>
    <div class="resource-bottom-grid"><article class="environment-card panel-frame"><h2>底座环境</h2><div class="environment-list">${checks.map((check) => `<div>${lineIcon(check.id === 'workspace' ? 'folder' : 'terminal')}<b>${escapeHtml(check.label)}</b><span>${escapeHtml(check.version || '—')}</span><em class="status-pill ${check.status === 'ok' ? 'green' : 'amber'}">${lineIcon(check.status === 'ok' ? 'circle-check' : 'circle-alert')}${check.status === 'ok' ? '正常' : '需要关注'}</em><button title="${escapeHtml(check.path || '')}">本机检查 ${lineIcon('chevron-right')}</button></div>`).join('')}</div><footer>共 ${checks.length} 项检查，<b class="${warnings.length ? 'orange-text' : 'green-text'}">${warnings.length} 项需要关注</b><button data-action="refresh-resources">重新检查 ${lineIcon('refresh-cw')}</button></footer></article>
      <div class="resource-side-stack"><article class="requirements-card panel-frame"><h2>资源状态</h2><div><i>${lineIcon(warnings.length || !readyProviders.length ? 'circle-alert' : 'circle-check')}</i><span><strong>${warnings.length || !readyProviders.length ? '仍有资源需要处理' : '底座资源已经就绪'}</strong><p>${!readyProviders.length ? '当前没有通过测试的模型连接。' : warnings.length ? `${warnings.length} 项本机环境检查需要关注。` : '模型、工具与环境可供卡带绑定。'}</p></span><button class="page-button orange-text" data-action="open-resource-config">进入配置</button></div></article><article class="local-vars-card panel-frame"><h2>本机变量</h2><div><span>${lineIcon('shield-check')}敏感状态 <b class="status-pill green">后端已脱敏</b></span><button class="page-button" data-action="open-resource-config">管理凭据</button></div><div><span>${lineIcon('code-xml')}配置状态 <b class="status-pill">${configured.length} 项已配置</b></span><button class="page-button" data-action="open-resource-config">查看配置</button></div></article></div></div>`
  liveState.providers = providers
  liveState.resources = resources
  liveState.environment = environment
  renderResourceModalData(providers, resources)
  renderIcons()
}

async function loadResourcesPage() {
  const content = document.querySelector('.resources-content')
  if (!content) return
  content.innerHTML = liveStateMarkup('正在检查本机资源')
  try {
    const [providerPayload, resources, environment] = await Promise.all([
      api('/api/llm/providers'), api('/api/studio/resources'), api('/api/studio/environment'),
    ])
    if (liveState.currentPage !== 'resources') return
    renderResourcesPage(providerPayload.providers || [], resources, environment)
  } catch (error) {
    content.innerHTML = liveStateMarkup(error.message, true)
    renderIcons()
  }
}

function releasePreflightMarkup(flow, report) {
  const issues = report?.issues || []
  const blockers = issues.filter((item) => ['blocker', 'error'].includes(item.severity))
  const portability = report?.portability?.summary || {}
  const sections = [
    ['协议兼容', report?.compatibility?.ok], ['协议认证', report?.certification?.ok],
    ['运行环境', report?.environment?.status === 'ok'], ['依赖解析', report?.dependencies?.status === 'ok'],
    ['模型配方', report?.models?.status === 'ok'], ['发布包卫生', report?.package_hygiene?.status === 'ok'],
  ]
  return `<div class="release-steps panel-frame"><span class="active" aria-current="step"><b>1</b><strong>预检</strong></span><i class="release-connector"></i><span><b>2</b><strong>迁移检查</strong></span><i class="release-connector"></i><span><b>3</b><strong>包策略</strong></span><i class="release-connector"></i><span><b>4</b><strong>生成结果</strong></span></div>
    <section class="preflight panel-frame"><h2>预检</h2><div class="preflight-summary"><span>${lineIcon('circle-check')}开发包状态　<b class="${report?.dev_ready ? 'green-text' : 'red-text'}">${report?.dev_ready ? '可生成' : '被阻塞'}</b></span><span>${lineIcon('circle-x')}<b class="red-text">阻塞问题　${blockers.length}</b></span><span>${lineIcon('info')}迁移内容　<b class="blue-text">${portability.portable || 0}</b></span><span>${lineIcon(report?.production_ready ? 'circle-check' : 'circle-alert')}生产包 ${report?.production_ready ? '可生成' : '未就绪'}</span></div><div class="preflight-body"><div><div class="table-head"><span>检查项</span><span>结果</span><span>说明</span></div>${sections.map(([label, ok]) => `<p><span class="preflight-item">${lineIcon(ok ? 'circle-check' : 'circle-alert')}${label}</span><b class="${ok ? 'green-text' : 'red-text'}">${ok ? '通过' : '待处理'}</b><em>${ok ? '检查项满足当前发布要求。' : '查看右侧问题并完成修复。'}</em></p>`).join('')}</div><aside><h3>待处理项（阻塞）<span>${blockers.length} 项</span></h3><div>${lineIcon(blockers.length ? 'circle-alert' : 'circle-check')}<b>${escapeHtml(blockers[0]?.message || '当前没有阻塞项')}</b><p>${blockers.length ? '修复后重新执行预检。' : '可以继续选择包策略并生成卡带包。'}</p><em>${blockers.length ? '阻塞' : '通过'}</em></div></aside></div></section>
    <section class="migration panel-frame"><h2>迁移检查 <small>（${report?.portability?.status === 'ok' ? '已完成' : '待处理'}）</small></h2><div><span>随包携带<b class="green-text">${portability.portable || 0}</b></span><span>本机重绑<b>${portability.local_rebind || 0}</b></span><span>缺失阻断<b>${portability.missing_blockers || 0}</b></span><span>禁止打包<b>${portability.forbidden || 0}</b></span></div><p>${lineIcon('info')}${escapeHtml(report?.portability?.status === 'ok' ? '迁移检查通过，卡带不携带本机密钥与地址。' : '迁移检查包含阻断项，暂时不能生成包。')}</p></section>
    <div class="release-bottom"><section class="package-strategy panel-frame"><div class="panel-title"><h2>包策略</h2><button class="page-button" data-action="refresh-release">${lineIcon('refresh-cw')}刷新预检</button></div><p>选择生成类型</p><div class="segmented" data-choice-group data-package-mode><button class="active" data-mode="dev">开发包</button><button data-mode="production" ${report?.production_ready ? '' : 'disabled'}>生产包</button></div><dl><dt>协议认证</dt><dd>${escapeHtml(report?.certification?.label || report?.certification?.status || '未认证')}</dd><dt>当前版本</dt><dd>${escapeHtml(flow.version || '—')}</dd></dl></section><section class="package-preview panel-frame"><h2>产物生成预览</h2><dl><dt>包名</dt><dd>${escapeHtml(flow.id)}-${escapeHtml(flow.version || '0.0.0')}.cartridge.zip</dd><dt>版本</dt><dd>${escapeHtml(flow.version || '—')}</dd><dt>目标卡带</dt><dd>${escapeHtml(flow.id)}</dd><dt>生成类型</dt><dd>开发包</dd><dt>预检状态</dt><dd>${report?.dev_ready ? '可生成' : '被阻塞'}</dd></dl><div class="package-cube">${lineIcon('package-open')}</div></section></div>`
}

async function selectReleaseFlow(flowId) {
  liveState.selectedReleaseId = flowId
  document.querySelectorAll('.target-flow button[data-flow-id]').forEach((button) => button.classList.toggle('selected', button.dataset.flowId === flowId))
  const main = document.querySelector('.release-main')
  if (main) main.innerHTML = liveStateMarkup('正在执行发布预检')
  try {
    const report = await api(`/api/studio/release/${encodeURIComponent(flowId)}/preflight`)
    if (liveState.currentPage !== 'release' || liveState.selectedReleaseId !== flowId) return
    liveState.releasePreflight = report
    const flow = liveState.flows.find((item) => item.id === flowId) || report.cartridge
    main.innerHTML = releasePreflightMarkup(flow, report)
    const footer = document.querySelector('.release-footer')
    footer.innerHTML = `<span>${lineIcon(report.dev_ready ? 'circle-check' : 'circle-alert')}<strong>${report.dev_ready ? '开发包已就绪' : '发布预检存在阻塞'}</strong><small>${report.dev_ready ? '后端预检通过，可以生成可下载的开发包。' : '处理阻塞项后重新预检。'}</small></span><div><button class="page-button" data-action="export-preflight">${lineIcon('file-down')}导出预检报告</button><button class="page-button primary" data-action="package-flow" ${report.dev_ready ? '' : 'disabled'}>${lineIcon('package-check')}生成开发包</button></div>`
    renderIcons()
  } catch (error) {
    if (main) main.innerHTML = liveStateMarkup(error.message, true)
    renderIcons()
  }
}

async function loadReleasePage() {
  const target = document.querySelector('.target-flow')
  const history = document.querySelector('.release-history')
  const main = document.querySelector('.release-main')
  const footer = document.querySelector('.release-footer')
  if (!target || !history) return
  target.innerHTML = `<h2>选择目标卡带</h2>${liveStateMarkup('正在读取卡带')}`
  history.innerHTML = liveStateMarkup('正在读取历史产物')
  if (main) main.innerHTML = liveStateMarkup('正在准备发布预检')
  if (footer) footer.innerHTML = '<span><strong>正在读取发布状态</strong><small>请稍候</small></span>'
  try {
    const [flowsPayload, packagesPayload] = await Promise.all([api('/api/lab/flows'), api('/api/studio/packages')])
    if (liveState.currentPage !== 'release') return
    const flows = flowsPayload.items || []
    const packages = packagesPayload.items || []
    liveState.flows = flows
    liveState.packages = packages
    const releaseMetrics = document.querySelectorAll('.release-metrics b')
    const devPackages = packages.filter((item) => item.package_mode !== 'production').length
    const productionPackages = packages.filter((item) => item.package_mode === 'production').length
    ;[packages.length, devPackages, productionPackages].forEach((value, index) => { if (releaseMetrics[index]) releaseMetrics[index].textContent = String(value) })
    liveState.selectedReleaseId = flows.some((flow) => flow.id === liveState.selectedReleaseId) ? liveState.selectedReleaseId : flows[0]?.id || ''
    target.innerHTML = `<h2>选择目标卡带</h2><div class="run-search">${lineIcon('search')}选择需要预检和打包的开发卡带</div>${flows.map((flow) => `<button class="${flow.id === liveState.selectedReleaseId ? 'selected' : ''}" data-flow-id="${escapeHtml(flow.id)}"><i class="tone-dot ${flow.editable ? 'green' : 'blue'}"></i><span><strong>${escapeHtml(flow.name || flow.id)}</strong><small>${escapeHtml(flow.id)}</small></span><b>${escapeHtml(flow.version || '—')}</b></button>`).join('') || '<div class="compact-inline-empty">暂无可发布卡带</div>'}`
    history.innerHTML = `<div class="panel-title"><h2>历史产物</h2><span>${packages.length} 条</span></div>${packages.map((item) => `<div><i class="tone-dot green"></i><span>${escapeHtml(item.name || item.cartridge_id)}<small>${escapeHtml(item.filename)}</small></span><em class="green-text">${escapeHtml(item.package_mode || 'dev')}</em><time>${escapeHtml(formatTime(item.modified_at))}</time></div>`).join('') || '<div class="compact-inline-empty">暂无历史产物</div>'}`
    renderIcons()
    if (liveState.selectedReleaseId) await selectReleaseFlow(liveState.selectedReleaseId)
    else document.querySelector('.release-main').innerHTML = liveStateMarkup('请先创建开发卡带')
  } catch (error) {
    target.innerHTML = `<h2>选择目标卡带</h2>${liveStateMarkup(error.message, true)}`
    history.innerHTML = liveStateMarkup('历史产物暂时不可用', true)
    renderIcons()
  }
}

function renderTodo(text, sourceName = 'TODO.md') {
  const lines = String(text || '').split(/\r?\n/)
  const items = lines
    .filter((line) => /^\s*- \[ \]/.test(line))
    .map((line) => line.replace(/^\s*- \[ \]\s*/, '').replace(/[`*_]/g, '').trim())
    .filter(Boolean)
    .slice(0, 6)
  const list = $('#todoList')
  if (!list) return

  if (!items.length) {
    const empty = document.createElement('div')
    empty.className = 'todo-empty-state'
    empty.textContent = '当前没有待处理事项'
    list.replaceChildren(empty)
    return
  }

  const rows = items.map((task, index) => {
    const row = document.createElement('div')
    row.className = 'todo-row'

    const taskCell = document.createElement('span')
    taskCell.className = 'todo-task'
    const check = document.createElement('i')
    check.className = 'todo-check'
    const label = document.createElement('b')
    label.textContent = task
    taskCell.append(check, label)

    const status = document.createElement('em')
    status.className = 'todo-status'
    status.textContent = '待处理'
    const order = document.createElement('em')
    order.className = 'todo-priority'
    order.textContent = `#${index + 1}`
    const source = document.createElement('span')
    source.textContent = sourceName

    row.append(taskCell, status, order, source)
    return row
  })
  list.replaceChildren(...rows)
}

async function loadDashboard() {
  const environmentPromise = api('/api/studio/environment')
  const results = await Promise.allSettled([
    api('/api/cartridge-runs'),
    apiText('/api/studio/todo/file'),
    api('/api/lab/flows'),
    api('/api/base'),
    api('/api/llm/providers'),
    api('/api/studio/resources'),
  ])
  const value = (index, fallback) => results[index].status === 'fulfilled' ? results[index].value : fallback
  const runs = value(0, { items: liveState.runs }).items || []
  const todoText = value(1, '')
  const flows = value(2, { items: liveState.flows }).items || []
  const basePayload = value(3, liveState.base ? { base: liveState.base } : null)
  const providers = value(4, { providers: liveState.providers }).providers || []
  const resources = value(5, liveState.resources)
  const environment = liveState.environment

  Object.assign(liveState, {
    runs,
    flows,
    providers,
    resources,
    environment,
    base: basePayload?.base || liveState.base,
    conformance: basePayload?.base?.conformance?.latest_report || liveState.conformance,
  })

  const failed = runs.filter((run) => run.status === 'failed').length
  const active = runs.filter((run) => activeStatuses.has(run.status)).length
  const completed = runs.filter((run) => completedStatuses.has(run.status)).length
  const healthy = completed
  const successRate = runs.length ? `${((completed / runs.length) * 100).toFixed(1)}%` : '—'
  ;['#allRuns', '#diagnosticAll'].forEach((selector) => { if ($(selector)) $(selector).textContent = String(runs.length) })
  ;['#failedRuns', '#diagnosticFailed', '#overviewFailed'].forEach((selector) => { if ($(selector)) $(selector).textContent = String(failed) })
  ;['#activeRuns', '#diagnosticActive'].forEach((selector) => { if ($(selector)) $(selector).textContent = String(active) })
  if ($('#completedRuns')) $('#completedRuns').textContent = String(completed)
  if ($('#overviewSuccessRate')) $('#overviewSuccessRate').textContent = successRate
  if ($('#overviewAttention')) $('#overviewAttention').textContent = String(failed + active)
  if ($('#overviewWaiting')) $('#overviewWaiting').textContent = String(runs.filter((run) => waitingStatuses.has(run.status)).length)
  if ($('#overviewHealthy')) $('#overviewHealthy').textContent = String(healthy)
  if ($('#overviewFlowCount')) $('#overviewFlowCount').textContent = String(flows.length)
  renderRunChart(runs)
  if (todoText) renderTodo(todoText)
  else if ($('#todoList')) $('#todoList').innerHTML = '<div class="todo-empty-state">TODO.md 暂时无法读取</div>'

  const recentId = localStorage.getItem('cf.studio.recent_project')
  const flow = flows.find((item) => item.id === recentId) || flows.find((item) => item.editable) || flows[0]
  if (flow) {
    const protocol = flow.runtime_contract?.protocol
    const protocolVersion = flow.runtime_contract?.protocol_version
    const latestRun = runs.find((run) => run.cartridge_id === flow.id)
    $('#recentFlowId').textContent = flow.id
    $('#recentFlowName').textContent = flow.name || flow.id
    $('#recentTime').textContent = formatTime(flow.updated_at)
    $('#recentFlowVersion').textContent = flow.version || '—'
    $('#recentFlowProtocol').textContent = protocol ? `${protocol}${protocolVersion ? `@${protocolVersion}` : ''}` : '未声明'
    $('#recentFlowTools').textContent = String((flow.mcp_tools || []).length)
    $('#recentRunResult').textContent = latestRun ? `● ${statusLabel(latestRun.status)}` : '暂无运行'
    $('#recentRunResult').classList.toggle('meta-ok', Boolean(latestRun && completedStatuses.has(latestRun.status)))
  } else {
    $('#recentFlowId').textContent = '暂无卡带'
    $('#recentFlowName').textContent = ''
    $('#recentTime').textContent = '—'
  }

  const latestFailure = runs.find((run) => run.status === 'failed')
  if ($('#diagnosticCode')) $('#diagnosticCode').textContent = latestFailure?.error?.code || '暂无故障'
  if ($('#diagnosticNode')) $('#diagnosticNode').textContent = latestFailure?.error?.node_id || latestFailure?.current_state || '—'
  if ($('#diagnosticNotice')) $('#diagnosticNotice').textContent = failed ? `${failed} 个失败运行需要处理` : '当前没有失败运行'
  if ($('#diagnosticUpdated')) $('#diagnosticUpdated').textContent = runs[0]?.updated_at ? `最近更新 ${formatTime(runs[0].updated_at)}` : '诊断记录为空'

  const base = liveState.base || {}
  const report = liveState.conformance || base.conformance?.latest_report || {}
  const protocols = base.supported_protocols || []
  const recommended = [...protocols].reverse().find((item) => item.id === 'CF-FARP') || protocols.at(-1)
  const capabilityCounts = report.capabilities?.counts || {}
  const tests = report.tests || {}
  if ($('#baseProtocolId')) $('#baseProtocolId').textContent = recommended?.id || base.base_contract?.id || '未声明'
  if ($('#baseProtocolVersion')) $('#baseProtocolVersion').textContent = recommended ? `${recommended.id}@${recommended.version}` : '未声明'
  if ($('#baseEvidence')) $('#baseEvidence').textContent = `${capabilityCounts.verified || 0} / ${report.capabilities?.declared || (base.capabilities || []).length}`
  if ($('#baseTests')) $('#baseTests').textContent = `${tests.counts?.passed || 0} / ${tests.total || 0}`
  if ($('#baseStatus')) $('#baseStatus').textContent = report.status === 'passed' ? '● 通过' : report.status === 'partial' ? '● 部分验证' : '● 未验证'

  const readyProviders = providers.filter((provider) => provider.enabled !== false && provider.has_key && provider.base_url && provider.default_model && provider.tested_ok)
  const allTools = [...(resources?.builtin_tools || []), ...(resources?.tools || [])]
  const enabledTools = allTools.filter((tool) => tool.enabled !== false)
  const credentialReferences = environment?.references || []
  const configuredCredentials = credentialReferences.filter((credential) => credential.configured)
  if ($('#modelResourceStatus')) $('#modelResourceStatus').textContent = readyProviders.length ? '已连接 ●' : '需要配置'
  if ($('#modelResourceName')) $('#modelResourceName').textContent = readyProviders[0]?.name || providers[0]?.name || '暂无模型连接'
  if ($('#modelResourceCount')) $('#modelResourceCount').textContent = `${readyProviders.length} / ${providers.length} 路可用`
  if ($('#toolResourceStatus')) $('#toolResourceStatus').textContent = enabledTools.length ? '已接入 ●' : '暂无工具'
  if ($('#toolResourceCount')) $('#toolResourceCount').textContent = `${enabledTools.length} / ${allTools.length} 项启用`
  if ($('#credentialStatus')) $('#credentialStatus').textContent = configuredCredentials.length ? '已绑定 ●' : '未配置'
  if ($('#credentialCount')) $('#credentialCount').textContent = `${configuredCredentials.length} / ${credentialReferences.length} 项已配置`
  renderIcons()
  environmentPromise.then((snapshot) => {
    liveState.environment = snapshot
    if (liveState.currentPage !== 'overview') return
    const configuredItems = (snapshot.references || []).filter((item) => item.configured)
    if ($('#credentialStatus')) $('#credentialStatus').textContent = configuredItems.length ? '已绑定 ●' : '未配置'
    if ($('#credentialCount')) $('#credentialCount').textContent = `${configuredItems.length} / ${(snapshot.references || []).length} 项已配置`
  }).catch(() => {
    if ($('#credentialStatus')) $('#credentialStatus').textContent = '检查失败'
  })
}

function renderRunChart(runs) {
  const bars = document.querySelector('.bars')
  const labels = document.querySelector('.y-labels')
  if (!bars || !labels) return
  const days = Array.from({ length: 7 }, (_, offset) => {
    const date = new Date()
    date.setHours(0, 0, 0, 0)
    date.setDate(date.getDate() - (6 - offset))
    const next = new Date(date)
    next.setDate(next.getDate() + 1)
    const dayRuns = runs.filter((run) => {
      const at = new Date(run.created_at || run.updated_at || 0)
      return at >= date && at < next
    })
    return { date, count: dayRuns.length, failed: dayRuns.some((run) => run.status === 'failed'), active: dayRuns.some((run) => activeStatuses.has(run.status)) }
  })
  const max = Math.max(1, ...days.map((day) => day.count))
  labels.innerHTML = `<span>${max}</span><span>${Math.ceil(max * .67)}</span><span>${Math.ceil(max * .33)}</span><span>0</span>`
  bars.innerHTML = days.map((day) => `<i class="bar ${day.failed ? 'fail-bar' : day.active ? 'running-bar' : 'success-bar'}" style="height:${Math.max(4, (day.count / max) * 100)}%"></i>`).join('')
  const chart = bars.closest('.chart')
  let axis = chart?.querySelector('.chart-x-labels')
  if (!axis && chart) {
    axis = document.createElement('div')
    axis.className = 'chart-x-labels'
    chart.append(axis)
  }
  if (axis) axis.innerHTML = days.map((day) => `<span><i class="bar-month">${String(day.date.getMonth() + 1).padStart(2, '0')}-</i>${String(day.date.getDate()).padStart(2, '0')}</span>`).join('')
}

function openTodoDialog(title, body) {
  const dialog = $('#todoDialog')
  $('#dialogTitle').textContent = title
  $('#dialogBody').textContent = body
  if (typeof dialog.showModal === 'function') dialog.showModal()
  else dialog.setAttribute('open', '')
}

const frame = $('.dashboard-frame')
const overviewMarkup = frame.innerHTML

function canonicalPage(page) {
  const requested = page || 'overview'
  return requested === 'overview' || pageTemplates[requested] ? requested : 'overview'
}

function activeNavigationPage(page) {
  if (page === 'flows-empty') return 'flows'
  return page
}

function showPage(page, updateHash = true) {
  const target = canonicalPage(page)
  liveState.currentPage = target
  frame.className = target === 'overview' ? 'dashboard-frame' : `dashboard-frame page-${target}`
  frame.innerHTML = target === 'overview' ? overviewMarkup : pageTemplates[target]()
  document.querySelectorAll('.nav-item[data-page]').forEach((node) => {
    node.classList.toggle('active', node.dataset.page === activeNavigationPage(target))
  })
  prepareLivePage(target)
  renderIcons()
  if (target === 'overview') {
    if ($('#todoList')) $('#todoList').innerHTML = '<div class="todo-empty-state">正在读取 TODO.md</div>'
    loadDashboard()
  } else if (target === 'flows') {
    loadFlowsPage()
  } else if (target === 'diagnostics') {
    loadDiagnosticsPage()
  } else if (target === 'resources') {
    loadResourcesPage()
  } else if (target === 'release') {
    loadReleasePage()
  } else if (target === 'settings') {
    syncSettingsPage()
  }
  requestAnimationFrame(() => {
    animatePageEnter(frame)
    animateNavSelection(document.querySelector('.nav-item[data-page].active'))
  })
  if (updateHash) history.replaceState(null, '', target === 'overview' ? '#overview' : `#${target}`)
}

function prepareLivePage(target) {
  const actions = document.querySelectorAll('.subpage-header .page-button')
  if (target === 'flows') {
    ;['import-flow', 'refresh-flows', 'create-flow'].forEach((action, index) => { if (actions[index]) actions[index].dataset.action = action })
    document.querySelector('.flows-scroll')?.replaceChildren()
  } else if (target === 'diagnostics') {
    if (actions[0]) actions[0].dataset.action = 'refresh-diagnostics'
    const search = document.querySelector('.run-search')
    if (search) search.innerHTML = `${lineIcon('search')}<input data-run-search type="search" placeholder="搜索卡带名称或 run_id" aria-label="搜索运行记录">`
    const tabs = document.querySelectorAll('.run-tabs button')
    ;['all', 'failed', 'active', 'completed'].forEach((status, index) => { if (tabs[index]) tabs[index].dataset.status = status })
  } else if (target === 'resources') {
    if (actions[0]) actions[0].dataset.action = 'refresh-resources'
    if (actions[1]) actions[1].dataset.action = 'open-resource-config'
  } else if (target === 'release') {
    if (actions[0]) actions[0].dataset.action = 'refresh-release'
  }
}

async function handleTodoAction(action) {
  try {
    const path = action === 'template' ? '/api/studio/todo/template' : '/api/studio/todo/file'
    const content = await apiText(path)
    openTodoDialog(action === 'template' ? 'TODO_TEMPLATE.md' : 'TODO.md', content)
  } catch (error) {
    openTodoDialog('读取失败', error.message)
  }
}

const APPEARANCE_KEY = 'cf.studio.appearance'
const defaultAppearance = { fontScale: 110, fontFamily: 'developer', fontWeight: 'strong', density: 'comfortable', reducedMotion: false, scrollbarMode: 'subtle', scope: 'current_workspace' }

function loadAppearance() {
  try { return { ...defaultAppearance, ...JSON.parse(localStorage.getItem(APPEARANCE_KEY) || '{}') } }
  catch { return { ...defaultAppearance } }
}

function applyAppearance(settings) {
  const root = document.documentElement
  root.dataset.liveFontFamily = settings.fontFamily
  root.dataset.liveFontWeight = settings.fontWeight
  root.dataset.liveDensity = settings.density
  root.dataset.liveScrollbar = settings.scrollbarMode
  root.style.setProperty('--live-font-scale', String(settings.fontScale / 110))
  setUserReducedMotion(settings.reducedMotion)
}

function saveAppearance(settings) {
  localStorage.setItem(APPEARANCE_KEY, JSON.stringify(settings))
  applyAppearance(settings)
}

function syncSettingsPage() {
  const settings = loadAppearance()
  const range = document.querySelector('[data-setting="font"]')
  if (range) range.value = String(settings.fontScale)
  const indexes = {
    style: { system: 0, classic: 1, developer: 2 }[settings.fontFamily] ?? 2,
    weight: settings.fontWeight === 'regular' ? 0 : 1,
    density: settings.density === 'compact' ? 1 : 0,
    scroll: settings.scrollbarMode === 'always' ? 1 : 0,
    scope: settings.scope === 'all_workspaces' ? 1 : 0,
  }
  document.querySelectorAll('[data-setting-group]').forEach((group) => {
    group.querySelectorAll('button').forEach((button, index) => button.classList.toggle('active', index === indexes[group.dataset.settingGroup]))
  })
  const motionSwitch = document.querySelector('.settings-motion-switch')
  if (motionSwitch) motionSwitch.checked = settings.reducedMotion
  document.querySelectorAll('.setting-font-value,.summary-font').forEach((item) => { item.textContent = `${settings.fontScale}%` })
  document.querySelectorAll('.summary-motion').forEach((item) => { item.textContent = settings.reducedMotion ? 'reduced' : 'normal' })
  document.querySelector('.preview-scroll')?.style.setProperty('--preview-scale', String(settings.fontScale / 100))
  applyAppearance(settings)
}

function updateAppearanceFromPage() {
  const activeIndex = (group) => [...document.querySelectorAll(`[data-setting-group="${group}"] button`)].findIndex((button) => button.classList.contains('active'))
  const settings = {
    fontScale: Number(document.querySelector('[data-setting="font"]')?.value || 110),
    fontFamily: ['system', 'classic', 'developer'][activeIndex('style')] || 'developer',
    fontWeight: activeIndex('weight') === 0 ? 'regular' : 'strong',
    density: activeIndex('density') === 1 ? 'compact' : 'comfortable',
    scrollbarMode: activeIndex('scroll') === 1 ? 'always' : 'subtle',
    scope: activeIndex('scope') === 1 ? 'all_workspaces' : 'current_workspace',
    reducedMotion: Boolean(document.querySelector('.settings-motion-switch')?.checked),
  }
  saveAppearance(settings)
  return settings
}

function resetSettings() {
  const range = document.querySelector('[data-setting="font"]')
  if (range) range.value = '110'
  const defaults = { style: 2, weight: 1, density: 0, scroll: 0, scope: 0 }
  document.querySelectorAll('[data-setting-group]').forEach((group) => {
    const buttons = [...group.querySelectorAll('button')]
    buttons.forEach((button, index) => button.classList.toggle('active', index === defaults[group.dataset.settingGroup]))
  })
  document.querySelectorAll('.settings-motion-switch').forEach((item) => { item.checked = false })
  setUserReducedMotion(false)
  document.querySelectorAll('.setting-font-value,.summary-font').forEach((item) => { item.textContent = '110%' })
  document.querySelectorAll('.summary-motion').forEach((item) => { item.textContent = 'normal' })
  document.querySelector('.preview-scroll')?.style.setProperty('--preview-scale', '1.1')
  saveAppearance({ ...defaultAppearance })
  animateSettingPreview(document.querySelector('.settings-preview'))
}

function showToast(message) {
  let toast = document.querySelector('.page-toast')
  if (!toast) {
    toast = document.createElement('div')
    toast.className = 'page-toast'
    document.body.append(toast)
  }
  toast.textContent = message
  toast.classList.add('visible')
  animateToast(toast)
  clearTimeout(showToast.timer)
  showToast.timer = setTimeout(() => toast.classList.remove('visible'), 2000)
}

async function closeResourceModal() {
  const backdrop = document.querySelector('.resource-modal-backdrop')
  if (!backdrop || backdrop.hasAttribute('hidden')) return
  await animateModalClose(backdrop, backdrop.querySelector('.resource-modal'))
  backdrop.setAttribute('hidden', '')
}

async function exportSelectedRun() {
  if (!liveState.selectedRunId) throw new Error('请先选择运行记录')
  const payload = await api(`/api/cartridge-runs/${encodeURIComponent(liveState.selectedRunId)}/diagnostics`)
  const link = document.createElement('a')
  link.href = URL.createObjectURL(new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' }))
  link.download = `${liveState.selectedRunId}-diagnostic.json`
  link.click()
  URL.revokeObjectURL(link.href)
}

async function importCartridgeFile(file) {
  const contentBase64 = await new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onerror = () => reject(reader.error || new Error('读取卡带文件失败'))
    reader.onload = () => resolve(String(reader.result || '').split(',').at(-1))
    reader.readAsDataURL(file)
  })
  return api('/api/cartridges/import', { method: 'POST', body: JSON.stringify({ filename: file.name, content_base64: contentBase64, install_mode: 'keep_existing' }) })
}

function openLegacyWorkbench(flowId, workspace = 'design') {
  if (!flowId) {
    showToast('当前没有可打开的卡带')
    return
  }
  localStorage.setItem('cf.studio.recent_project', flowId)
  const origin = window.location.port === '5174' ? 'http://127.0.0.1:5173' : window.location.origin
  window.open(`${origin}/projects/${encodeURIComponent(flowId)}/${workspace}`, '_blank', 'noopener')
}

document.addEventListener('click', async (event) => {
  const navigation = event.target.closest('.nav-item[data-page]')
  if (navigation) {
    showPage(navigation.dataset.page)
    return
  }

  const todoButton = event.target.closest('.todo-tools button')
  if (todoButton) {
    await handleTodoAction(todoButton.dataset.action)
    return
  }

  const settingButton = event.target.closest('[data-setting-group] button')
  if (settingButton) {
    settingButton.parentElement.querySelectorAll('button').forEach((button) => button.classList.toggle('active', button === settingButton))
    updateAppearanceFromPage()
    animateSelection(settingButton)
    animateSettingPreview(document.querySelector('.settings-preview'))
    return
  }

  const choiceButton = event.target.closest('[data-choice-group] button')
  if (choiceButton) {
    choiceButton.parentElement.querySelectorAll('button').forEach((button) => button.classList.toggle('active', button === choiceButton))
    animateSelection(choiceButton)
    return
  }

  const runTab = event.target.closest('.run-tabs button')
  if (runTab) {
    runTab.parentElement.querySelectorAll('button').forEach((button) => button.classList.toggle('active', button === runTab))
    animateSelection(runTab)
    applyRunFilter()
    return
  }

  const runRow = event.target.closest('.run-row')
  if (runRow) {
    animateSelection(runRow)
    await selectRun(runRow.dataset.runId)
    return
  }

  const releaseTarget = event.target.closest('.target-flow button[data-flow-id]')
  if (releaseTarget) {
    await selectReleaseFlow(releaseTarget.dataset.flowId)
    return
  }

  const action = event.target.closest('[data-action]')?.dataset.action
  if (action === 'open-resource-modal' || action === 'open-resource-config') {
    const backdrop = document.querySelector('.resource-modal-backdrop')
    if (backdrop) {
      backdrop.removeAttribute('hidden')
      animateModalOpen(backdrop, backdrop.querySelector('.resource-modal'))
    }
  } else if (action === 'close-resource-modal') {
    await closeResourceModal()
  } else if (action === 'toggle-disclosure') {
    const trigger = event.target.closest('[data-action="toggle-disclosure"]')
    await animateDisclosure(trigger, trigger?.nextElementSibling)
  } else if (action === 'copy-diagnostic') {
    const bundle = await api(`/api/cartridge-runs/${encodeURIComponent(liveState.selectedRunId)}/diagnostics`)
    const run = bundle.run || {}
    const error = run.error || (run.errors || []).at(-1) || {}
    await navigator.clipboard?.writeText([error.code || 'NO_ERROR', run.cartridge_id, run.run_id, error.node_id || run.current_state, error.message || ''].filter(Boolean).join('\n'))
    showToast('当前诊断已复制')
  } else if (action === 'export-diagnostic') {
    await exportSelectedRun()
    showToast('诊断 JSON 已导出')
  } else if (action === 'delete-run') {
    if (!liveState.selectedRunId || !confirm(`确定删除运行记录 ${liveState.selectedRunId}？`)) return
    await api(`/api/cartridge-runs/${encodeURIComponent(liveState.selectedRunId)}`, { method: 'DELETE' })
    liveState.selectedRunId = ''
    await loadDiagnosticsPage()
    showToast('运行记录已删除')
  } else if (action === 'retry-run' || action === 'restart-run') {
    if (!liveState.selectedRunId) return
    const controlAction = action === 'retry-run' ? 'retry_current_node' : 'restart_run'
    if (controlAction === 'restart_run' && !confirm('将使用原始输入重新开始这次运行，是否继续？')) return
    await api(`/api/cartridge-runs/${encodeURIComponent(liveState.selectedRunId)}/control`, { method: 'POST', body: JSON.stringify({ action: controlAction }) })
    await selectRun(liveState.selectedRunId)
    showToast('恢复动作已提交')
  } else if (action === 'open-flow') {
    openLegacyWorkbench(event.target.closest('[data-flow-id]')?.dataset.flowId)
  } else if (action === 'open-run-workbench') {
    openLegacyWorkbench(event.target.closest('[data-flow-id]')?.dataset.flowId, 'test')
  } else if (action === 'bind-flow-resources') {
    openLegacyWorkbench(event.target.closest('[data-flow-id]')?.dataset.flowId, 'resources')
  } else if (action === 'open-flow-directory') {
    await api(`/api/lab/flows/${encodeURIComponent(event.target.closest('[data-flow-id]').dataset.flowId)}/open-directory`, { method: 'POST' })
    showToast('已打开卡带目录')
  } else if (action === 'delete-flow') {
    const id = event.target.closest('[data-flow-id]').dataset.flowId
    if (!confirm(`确定删除开发卡带 ${id}？运行产物不会随之删除。`)) return
    await api(`/api/lab/flows/${encodeURIComponent(id)}`, { method: 'DELETE' })
    await loadFlowsPage()
    showToast('卡带已删除')
  } else if (action === 'create-flow') {
    const flowId = prompt('卡带 ID（仅字母、数字、点、下划线和连字符）')?.trim()
    if (!flowId) return
    const name = prompt('卡带名称', flowId)?.trim() || flowId
    const description = prompt('一句话说明', '')?.trim() || ''
    await api('/api/lab/flows', { method: 'POST', body: JSON.stringify({ flow_id: flowId, name, description }) })
    await loadFlowsPage()
    showToast('开发卡带已创建')
  } else if (action === 'import-flow') {
    document.querySelector('#cartridgeImportInput')?.click()
  } else if (action === 'refresh-flows') {
    await loadFlowsPage()
  } else if (action === 'refresh-diagnostics') {
    await loadDiagnosticsPage()
  } else if (action === 'refresh-resources') {
    await loadResourcesPage()
  } else if (action === 'refresh-release') {
    await loadReleasePage()
  } else if (action === 'package-flow') {
    const mode = document.querySelector('[data-package-mode] button.active')?.dataset.mode || 'dev'
    const result = await api(`/api/cartridges/${encodeURIComponent(liveState.selectedReleaseId)}/package`, { method: 'POST', body: JSON.stringify({ package_mode: mode }) })
    showToast(`已生成 ${result.filename}`)
    await loadReleasePage()
  } else if (action === 'export-preflight') {
    const data = JSON.stringify(liveState.releasePreflight || {}, null, 2)
    const link = document.createElement('a')
    link.href = URL.createObjectURL(new Blob([data], { type: 'application/json' }))
    link.download = `${liveState.selectedReleaseId}-preflight.json`
    link.click()
    URL.revokeObjectURL(link.href)
  } else if (action === 'open-resources') {
    showPage('resources')
  } else if (action === 'open-diagnostics') {
    showPage('diagnostics')
  } else if (action === 'continue-recent') {
    const id = liveState.flows.find((flow) => flow.id === localStorage.getItem('cf.studio.recent_project'))?.id || liveState.flows[0]?.id
    if (id) openLegacyWorkbench(id)
    else showPage('flows')
  } else if (action === 'open-evidence') {
    const payload = await api('/api/studio/conformance')
    openTodoDialog('能力证据与自动测试', JSON.stringify(payload.report || payload, null, 2))
  } else if (action === 'retry-page') {
    showPage(liveState.currentPage, false)
  } else if (action === 'reset-settings') {
    resetSettings()
  } else if (event.target.closest('#refreshButton')) {
    animateRefresh(event.target.closest('#refreshButton'))
    await loadDashboard()
  } else if (event.target.closest('#closeDialog')) {
    $('#todoDialog').close()
  } else if (event.target.matches('.resource-modal-backdrop')) {
    await closeResourceModal()
  }
})

document.addEventListener('keydown', (event) => {
  const disclosure = event.target.closest?.('[data-action="toggle-disclosure"]')
  if (disclosure && ['Enter', ' '].includes(event.key)) {
    event.preventDefault()
    disclosure.click()
    return
  }
  if (event.key === 'Escape') closeResourceModal()
})

document.addEventListener('input', (event) => {
  if (event.target.matches('[data-run-search]')) {
    applyRunFilter()
    return
  }
  if (event.target.matches('[data-setting="font"]')) {
    const value = `${event.target.value}%`
    document.querySelectorAll('.setting-font-value,.summary-font').forEach((item) => { item.textContent = value })
    document.querySelector('.preview-scroll')?.style.setProperty('--preview-scale', String(event.target.value / 100))
    updateAppearanceFromPage()
    animateSettingPreview(document.querySelector('.settings-preview'))
  }
})

document.addEventListener('change', async (event) => {
  if (event.target.matches('#cartridgeImportInput')) {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) return
    try {
      const result = await importCartridgeFile(file)
      showToast(`已导入 ${result.cartridge?.name || result.cartridge?.id || file.name}`)
      if (liveState.currentPage === 'flows') await loadFlowsPage()
    } catch (error) {
      showToast(`导入失败：${error.message}`)
    }
    return
  }
  if (event.target.matches('.settings-motion-switch')) {
    const reduced = event.target.checked
    const label = event.target.nextElementSibling
    if (label) label.textContent = reduced ? '开启' : '关闭'
    document.querySelectorAll('.summary-motion').forEach((item) => { item.textContent = reduced ? 'reduced' : 'normal' })
    updateAppearanceFromPage()
    animateSettingPreview(document.querySelector('.settings-preview'))
  }
})

window.addEventListener('hashchange', () => showPage(location.hash.slice(1), false))
window.addEventListener('unhandledrejection', (event) => {
  event.preventDefault()
  showToast(`操作失败：${event.reason?.message || event.reason || '未知错误'}`)
})
document.documentElement.dataset.componentSystem = componentSystem.name
applyAppearance(loadAppearance())
showPage(location.hash.slice(1) || 'overview', false)
