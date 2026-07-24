import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  fetchLabFlows,
  fetchLlmAssignments,
  fetchLlmProviders,
  fetchStudioEnvironment,
  fetchStudioResources,
  type CartridgeSummary,
  type LlmAssignments,
  type LlmProvider,
  type ResourceRequirement,
  type StudioEnvironmentSnapshot,
  type StudioResources,
  type StudioToolResource,
} from '../api.ts'
import ConfigModal from '../components/ConfigModal.tsx'
import PrimaryPageHeader from '../components/PrimaryPageHeader.tsx'
import { getRoleReadiness, normalizeRecipeRoles } from '../llmRecipe.ts'
import ResourceConfigurationPage from './ResourceConfigurationPage.tsx'

type OverviewDetail = 'models' | 'runtime' | 'tools' | 'variables'

const DETAIL_META: Record<OverviewDetail, { title: string; kicker: string }> = {
  models: { title: '模型配置详情', kicker: 'MODEL CONFIGURATION' },
  runtime: { title: '底座环境详情', kicker: 'BASE ENVIRONMENT' },
  tools: { title: '工具配置详情', kicker: 'TOOL CONFIGURATION' },
  variables: { title: '环境变量详情', kicker: 'ENVIRONMENT VARIABLES' },
}

function providerState(provider: LlmProvider) {
  if (provider.runtime_supported === false) return { key: 'unsupported', label: '协议不支持' }
  if (provider.tested_ok) return { key: 'verified', label: '连接正常' }
  if (provider.base_url && provider.has_key && provider.default_model) return { key: 'pending', label: '等待测试' }
  return { key: 'incomplete', label: '信息不完整' }
}

function toolKindLabel(tool: StudioToolResource) {
  if (tool.kind === 'remote_api') return '远程 API'
  if (tool.kind === 'mcp') return 'MCP'
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

export default function ResourceOverviewPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [providers, setProviders] = useState<LlmProvider[]>([])
  const [assignments, setAssignments] = useState<LlmAssignments | null>(null)
  const [resources, setResources] = useState<StudioResources | null>(null)
  const [environment, setEnvironment] = useState<StudioEnvironmentSnapshot | null>(null)
  const [flows, setFlows] = useState<CartridgeSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

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
      setError(reason?.message || '读取资源概览失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void load() }, [])

  const report = useMemo(() => {
    const modelIssues = flows.flatMap((flow) => normalizeRecipeRoles(flow.llm_recipe).map((role) => ({ flow, role })))
      .filter(({ flow, role }) => role.required && getRoleReadiness(flow.id, role, providers, assignments).state !== 'ready')
    const toolIssues = flows.flatMap((flow) => (flow.resource_requirements || []).map((requirement) => ({ flow, requirement })))
      .filter(({ flow, requirement }) => {
        if (requirement.required === false) return false
        const resourceId = resources?.bindings.roles?.[flow.id]?.[requirement.role]
        const resource = resources?.tools.find((item) => item.id === resourceId)
        return !resource || !toolMatches(resource, requirement)
      })
    const providerUsage = new Map<string, number>()
    for (const binding of Object.values(assignments?.defaults || {})) {
      if (binding.provider_id) providerUsage.set(binding.provider_id, (providerUsage.get(binding.provider_id) || 0) + 1)
    }
    for (const roles of Object.values(assignments?.cartridges || {})) {
      for (const binding of Object.values(roles)) if (binding.provider_id) providerUsage.set(binding.provider_id, (providerUsage.get(binding.provider_id) || 0) + 1)
    }
    for (const roles of Object.values(assignments?.nodes || {})) {
      for (const binding of Object.values(roles)) if (binding.provider_id) providerUsage.set(binding.provider_id, (providerUsage.get(binding.provider_id) || 0) + 1)
    }
    const toolUsage = new Map<string, number>()
    for (const roles of Object.values(resources?.bindings.roles || {})) {
      for (const resourceId of Object.values(roles)) toolUsage.set(resourceId, (toolUsage.get(resourceId) || 0) + 1)
    }
    for (const ids of Object.values(resources?.bindings.tools || {})) {
      for (const resourceId of ids) toolUsage.set(resourceId, (toolUsage.get(resourceId) || 0) + 1)
    }
    const readyProviders = providers.filter((item) => providerState(item).key === 'verified').length
    const readyTools = (resources?.tools || []).filter((tool) => {
      const credential = environment?.credentials.find((item) => item.key === tool.auth_env)
      return Boolean((tool.endpoint || tool.command || tool.openapi_url) && (!tool.auth_env || credential?.has_value))
    }).length
    return { modelIssues, toolIssues, providerUsage, toolUsage, readyProviders, readyTools }
  }, [assignments, environment, flows, providers, resources])

  const environmentVariables = useMemo(() => {
    const byKey = new Map((environment?.references || []).map((item) => [item.key, {
      key: item.key,
      label: item.label,
      owners: item.owners,
      configured: item.configured,
      source: '',
      preview: '',
    }]))
    for (const credential of environment?.credentials || []) {
      const current = byKey.get(credential.key)
      byKey.set(credential.key, {
        key: credential.key,
        label: current?.label || credential.label,
        owners: current?.owners || ['自定义变量'],
        configured: credential.has_value,
        source: credential.source,
        preview: credential.preview,
      })
    }
    return [...byKey.values()].sort((left, right) => Number(right.configured) - Number(left.configured) || left.key.localeCompare(right.key))
  }, [environment])

  const runtimeIssues = environment?.checks.filter((item) => item.status !== 'ok').length || 0
  const configuredVariables = environmentVariables.filter((item) => item.configured).length
  const detailParam = searchParams.get('detail')
  const expandedPanel = detailParam && Object.prototype.hasOwnProperty.call(DETAIL_META, detailParam) ? detailParam as OverviewDetail : null
  const configKeys = ['kind', 'resource', 'register', 'tab', 'target']
  const configOpen = searchParams.get('config') === '1' || configKeys.some((key) => searchParams.has(key))

  function openConfiguration(params: Record<string, string> = {}) {
    const next = new URLSearchParams(searchParams)
    next.delete('detail')
    next.set('config', '1')
    configKeys.forEach((key) => next.delete(key))
    Object.entries(params).forEach(([key, value]) => next.set(key, value))
    setSearchParams(next, { replace: true })
  }

  function closeConfiguration() {
    const next = new URLSearchParams(searchParams)
    next.delete('config')
    configKeys.forEach((key) => next.delete(key))
    setSearchParams(next, { replace: true })
    void load()
  }

  function setExpandedPanel(panel: OverviewDetail | null) {
    const next = new URLSearchParams(searchParams)
    next.delete('config')
    configKeys.forEach((key) => next.delete(key))
    if (panel) next.set('detail', panel)
    else next.delete('detail')
    setSearchParams(next, { replace: true })
  }

  return (
    <div className="cf-resource-center-page cf-primary-page-surface">
      <PrimaryPageHeader
        eyebrow="Local Resource Center"
        title="资源中心"
        description="集中查看底座可调用的模型、工具、本机环境与待分配需求。"
        actions={(
          <div className="cf-resource-center-actions">
            <button type="button" onClick={() => void load()} disabled={loading}>{loading ? '刷新中…' : '刷新状态'}</button>
            <button type="button" className="primary" onClick={() => openConfiguration()}>配置资源</button>
          </div>
        )}
      />

      {error && <div className="cf-resource-alert danger">{error}</div>}

      <section className="cf-resource-center-summary" aria-label="资源状态摘要">
        <button type="button" onClick={() => setExpandedPanel('models')}>
          <span>模型连接</span><strong>{report.readyProviders}<small> / {providers.length}</small></strong><em>连接可用</em>
          <i><b style={{ width: `${providers.length ? Math.round((report.readyProviders / providers.length) * 100) : 0}%` }} /></i>
        </button>
        <button type="button" onClick={() => setExpandedPanel('tools')}>
          <span>工具资源</span><strong>{report.readyTools}<small> / {resources?.tools.length || 0}</small></strong><em>本机连接可用</em>
          <i><b style={{ width: `${resources?.tools.length ? Math.round((report.readyTools / resources.tools.length) * 100) : 0}%` }} /></i>
        </button>
        <button type="button" className={report.modelIssues.length + report.toolIssues.length ? 'attention' : ''} onClick={() => openConfiguration({ tab: 'assignments' })}>
          <span>待分配需求</span><strong>{report.modelIssues.length + report.toolIssues.length}</strong><em>{report.modelIssues.length + report.toolIssues.length ? '需要开发者处理' : '必需角色均已满足'}</em>
          <i><b style={{ width: report.modelIssues.length + report.toolIssues.length ? '38%' : '100%' }} /></i>
        </button>
        <button type="button" onClick={() => setExpandedPanel('variables')}>
          <span>本机变量</span><strong>{configuredVariables}<small> / {environmentVariables.length}</small></strong><em>已配置并脱敏</em>
          <i><b style={{ width: `${environmentVariables.length ? Math.round((configuredVariables / environmentVariables.length) * 100) : 0}%` }} /></i>
        </button>
      </section>

      <div className="cf-resource-center-layout">
        <div className="cf-resource-center-library">
          <section className="cf-resource-center-section cf-resource-connection-card">
            <header className="cf-resource-center-section-head">
              <div><span>MODEL CONNECTIONS</span><h2>模型连接</h2><p>为 Flow 内的模型配方提供本机 API 连接。</p></div>
              <div><b>{providers.length} 个</b><button type="button" onClick={() => setExpandedPanel('models')}>查看详情</button><button type="button" className="primary" onClick={() => openConfiguration({ register: 'model' })}>新增模型</button></div>
            </header>
            <div className="cf-resource-center-list">
            {providers.map((provider) => {
              const state = providerState(provider)
              return <button type="button" className="cf-resource-center-row" key={provider.id} onClick={() => openConfiguration({ kind: 'model', resource: provider.id })}><i className={`cf-resource-state ${state.key}`} /><span><strong>{provider.name}</strong><small>{provider.default_model || '未填写默认模型'} · {provider.wire_api || '未声明协议'}</small></span><b className={state.key}>{state.label}</b><em>{report.providerUsage.get(provider.id) || 0} 处使用</em></button>
            })}
            {!providers.length && !loading && <div className="cf-resource-center-empty"><strong>还没有模型连接</strong><span>新增模型 API 后，可在卡带里按配方名称自动接入。</span><button type="button" onClick={() => openConfiguration({ register: 'model' })}>新增模型 API</button></div>}
            </div>
          </section>

          <section className="cf-resource-center-section cf-resource-connection-card">
            <header className="cf-resource-center-section-head">
              <div><span>TOOL CONNECTIONS</span><h2>工具连接</h2><p>统一管理远程 API、MCP 服务和底座插件。</p></div>
              <div><b>{resources?.tools.length || 0} 个</b><button type="button" onClick={() => setExpandedPanel('tools')}>查看详情</button><button type="button" className="primary" onClick={() => openConfiguration({ register: 'tool' })}>新增工具</button></div>
            </header>
            <div className="cf-resource-center-list">
            {(resources?.tools || []).map((tool) => {
              const credential = environment?.credentials.find((item) => item.key === tool.auth_env)
              const ready = Boolean((tool.endpoint || tool.command || tool.openapi_url) && (!tool.auth_env || credential?.has_value))
              return <button type="button" className="cf-resource-center-row" key={tool.id} onClick={() => openConfiguration({ kind: 'tool', resource: tool.id })}><i className={`cf-resource-state ${ready ? 'verified' : 'incomplete'}`} /><span><strong>{tool.name}</strong><small>{toolKindLabel(tool)} · {tool.capabilities?.join(', ') || '未声明能力'}</small></span><b className={ready ? 'verified' : 'incomplete'}>{ready ? '可用' : tool.auth_env && !credential?.has_value ? '缺少凭据' : '信息不完整'}</b><em>{report.toolUsage.get(tool.id) || 0} 处使用</em></button>
            })}
            {!resources?.tools.length && !loading && <div className="cf-resource-center-empty"><strong>还没有工具连接</strong><span>文生图 API、MCP 和本机插件都从同一工作区创建。</span><button type="button" onClick={() => openConfiguration({ register: 'tool' })}>新增工具连接</button></div>}
            </div>
          </section>
        </div>

        <aside className="cf-resource-center-side">
          <section className="cf-resource-center-section cf-resource-center-environment">
            <header className="cf-resource-center-section-head">
              <div><span>BASE ENVIRONMENT</span><h2>底座环境</h2><p>运行时与工作目录只读检查。</p></div>
              <div><b className={runtimeIssues ? 'warning' : 'ok'}>{runtimeIssues ? `${runtimeIssues} 项关注` : '状态正常'}</b><button type="button" onClick={() => setExpandedPanel('runtime')}>完整信息</button></div>
            </header>
            <div className="cf-resource-center-list compact">
              {(environment?.checks || []).map((check) => <button type="button" className="cf-resource-center-row runtime" key={check.id} onClick={() => setExpandedPanel('runtime')}><i className={`cf-check-status ${check.status}`} /><span><strong>{check.label}</strong><small>{check.version || check.path || '未读取版本'}</small></span><b className={check.status}>{check.status === 'ok' ? '正常' : '需关注'}</b></button>)}
              {!environment?.checks.length && !loading && <div className="cf-resource-center-empty compact"><strong>没有环境检查结果</strong><span>请刷新状态或检查底座服务。</span></div>}
            </div>
          </section>

          <section className="cf-resource-center-section cf-resource-center-attention">
            <header className="cf-resource-center-section-head">
              <div><span>RESOURCE ATTENTION</span><h2>待处理需求</h2><p>卡带声明但尚未满足的必需角色。</p></div>
              <div><b className={report.modelIssues.length + report.toolIssues.length ? 'warning' : 'ok'}>{report.modelIssues.length + report.toolIssues.length}</b><button type="button" onClick={() => openConfiguration({ tab: 'assignments' })}>进入配置</button></div>
            </header>
            <div className="cf-resource-center-needs">
              {report.modelIssues.map(({ flow, role }) => <button type="button" key={`model-${flow.id}-${role.id}`} onClick={() => openConfiguration({ kind: 'model', tab: 'assignments' })}><span>模型角色</span><strong>{role.label}</strong><small>{flow.name} · {role.capability}</small><b>处理</b></button>)}
              {report.toolIssues.map(({ flow, requirement }) => <button type="button" key={`tool-${flow.id}-${requirement.role}`} onClick={() => openConfiguration({ kind: 'tool', tab: 'assignments' })}><span>工具角色</span><strong>{requirement.role}</strong><small>{flow.name} · {(requirement.capabilities || requirement.kinds || []).join(', ')}</small><b>处理</b></button>)}
              {!report.modelIssues.length && !report.toolIssues.length && !loading && <div className="cf-resource-center-clear"><i /><strong>当前资源角色均已满足</strong><span>新卡带的资源需求会自动汇总到这里。</span></div>}
            </div>
            <button type="button" className="cf-resource-center-variable-link" onClick={() => setExpandedPanel('variables')}><span>本机变量</span><strong>{configuredVariables}/{environmentVariables.length}</strong><small>查看脱敏状态与引用位置</small></button>
          </section>
        </aside>
      </div>

      <ConfigModal open={configOpen} title="资源配置" kicker="LOCAL RESOURCE WORKSPACE" className="cf-resource-center-config-modal" initialFocus="dialog" onClose={closeConfiguration}>
        <ResourceConfigurationPage embedded onChanged={load} />
      </ConfigModal>

      <ConfigModal
        open={Boolean(expandedPanel)}
        title={expandedPanel ? DETAIL_META[expandedPanel].title : '资源详情'}
        kicker={expandedPanel ? DETAIL_META[expandedPanel].kicker : 'RESOURCE DETAIL'}
        className="cf-resource-overview-modal"
        onClose={() => setExpandedPanel(null)}
      >
        {expandedPanel === 'models' && <div className="cf-resource-detail-workspace">
          <div className="cf-resource-detail-summary"><div><span>已注册</span><strong>{providers.length}</strong></div><div><span>连接可用</span><strong>{report.readyProviders}</strong></div><div><span>待分配需求</span><strong>{report.modelIssues.length}</strong></div></div>
          <div className="cf-resource-detail-list">
            {providers.map((provider) => { const state = providerState(provider); return <article key={provider.id}><i className={`cf-resource-state ${state.key}`} /><div><header><strong>{provider.name}</strong><b className={state.key}>{state.label}</b></header><dl><div><dt>连接标识</dt><dd>{provider.id}</dd></div><div><dt>默认模型</dt><dd>{provider.default_model || '未填写'}</dd></div><div><dt>调用协议</dt><dd>{provider.wire_api || '未声明'}</dd></div><div><dt>服务地址</dt><dd>{provider.base_url || '未填写'}</dd></div><div><dt>凭据</dt><dd>{provider.has_key ? provider.key_preview || '已保存' : '未配置'}</dd></div><div><dt>使用位置</dt><dd>{report.providerUsage.get(provider.id) || 0}</dd></div><div><dt>配置来源</dt><dd>{provider.source || '本机'}</dd></div><div><dt>最近测试</dt><dd>{provider.tested_at || '尚未测试'}</dd></div></dl></div></article> })}
            {!providers.length && <div className="cf-resource-detail-empty">还没有模型连接。</div>}
          </div>
        </div>}

        {expandedPanel === 'runtime' && <div className="cf-resource-detail-workspace">
          <div className="cf-resource-detail-summary"><div><span>检查项目</span><strong>{environment?.checks.length || 0}</strong></div><div><span>状态正常</span><strong>{(environment?.checks.length || 0) - runtimeIssues}</strong></div><div><span>需要关注</span><strong>{runtimeIssues}</strong></div></div>
          <div className="cf-resource-detail-list">
            {(environment?.checks || []).map((check) => <article key={check.id}><i className={`cf-check-status ${check.status}`} /><div><header><strong>{check.label}</strong><b className={check.status}>{check.status === 'ok' ? '正常' : '需关注'}</b></header><dl><div><dt>检查标识</dt><dd>{check.id}</dd></div><div><dt>版本 / 状态</dt><dd>{check.version || '未读取'}</dd></div><div className="wide"><dt>可执行文件 / 路径</dt><dd>{check.path || '未检测到'}</dd></div></dl></div></article>)}
          </div>
          <section className="cf-resource-detail-paths"><header><span>BASE PATHS</span><h3>底座数据路径</h3></header><dl>{Object.entries(environment?.paths || {}).map(([key, value]) => <div key={key}><dt>{key}</dt><dd>{value}</dd></div>)}</dl></section>
        </div>}

        {expandedPanel === 'tools' && <div className="cf-resource-detail-workspace">
          <div className="cf-resource-detail-summary"><div><span>本机连接</span><strong>{resources?.tools.length || 0}</strong></div><div><span>连接可用</span><strong>{report.readyTools}</strong></div><div><span>底座内置</span><strong>{resources?.builtin_tools.length || 0}</strong></div><div><span>待分配需求</span><strong>{report.toolIssues.length}</strong></div></div>
          <div className="cf-resource-detail-list">
            {(resources?.tools || []).map((tool) => { const credential = environment?.credentials.find((item) => item.key === tool.auth_env); const ready = Boolean((tool.endpoint || tool.command || tool.openapi_url) && (!tool.auth_env || credential?.has_value)); return <article key={tool.id}><i className={`cf-resource-state ${ready ? 'verified' : 'incomplete'}`} /><div><header><strong>{tool.name}</strong><b className={ready ? 'verified' : 'incomplete'}>{ready ? '可用' : '待完善'}</b></header><dl><div><dt>连接标识</dt><dd>{tool.id}</dd></div><div><dt>连接类型</dt><dd>{toolKindLabel(tool)}</dd></div><div><dt>能力</dt><dd>{tool.capabilities?.join(', ') || '未声明'}</dd></div><div><dt>使用位置</dt><dd>{report.toolUsage.get(tool.id) || 0}</dd></div><div className="wide"><dt>服务地址 / 命令</dt><dd>{tool.endpoint || tool.command || tool.openapi_url || '未填写'}</dd></div><div><dt>凭据标识</dt><dd>{tool.auth_env || '无需凭据'}</dd></div><div><dt>访问限制</dt><dd>{tool.read_only ? '只读' : '未限制'}</dd></div></dl></div></article> })}
            {!resources?.tools.length && <div className="cf-resource-detail-empty">还没有本机工具连接。</div>}
          </div>
          {(resources?.builtin_tools.length || 0) > 0 && <section className="cf-resource-detail-paths"><header><span>BUILT-IN TOOLS</span><h3>底座内置工具</h3></header><dl>{resources?.builtin_tools.map((tool) => <div key={tool.id}><dt>{tool.name}</dt><dd>{tool.server}/{tool.tool}</dd></div>)}</dl></section>}
        </div>}

        {expandedPanel === 'variables' && <div className="cf-resource-detail-workspace">
          <div className="cf-resource-detail-summary"><div><span>引用变量</span><strong>{environmentVariables.length}</strong></div><div><span>已配置</span><strong>{configuredVariables}</strong></div><div><span>未配置</span><strong>{environmentVariables.length - configuredVariables}</strong></div></div>
          <div className="cf-resource-detail-list cf-resource-variable-detail-list">
            {environmentVariables.map((item) => <article key={item.key}><i className={`cf-resource-state ${item.configured ? 'verified' : 'incomplete'}`} /><div><header><strong>{item.key}</strong><b className={item.configured ? 'verified' : 'incomplete'}>{item.configured ? '已配置' : '未配置'}</b></header><dl><div><dt>显示名称</dt><dd>{item.label}</dd></div><div><dt>配置来源</dt><dd>{item.configured ? item.source === 'local' ? '本机配置' : '进程继承' : '无'}</dd></div><div><dt>脱敏值</dt><dd>{item.configured ? item.preview || '已配置' : '未配置'}</dd></div><div className="wide"><dt>引用位置</dt><dd>{item.owners.join(' · ') || '自定义变量'}</dd></div></dl></div></article>)}
          </div>
          {environment?.paths.credentials && <section className="cf-resource-detail-paths"><header><span>LOCAL STORAGE</span><h3>本机变量存储</h3></header><dl><div><dt>credentials</dt><dd>{environment.paths.credentials}</dd></div></dl></section>}
        </div>}
      </ConfigModal>
    </div>
  )
}
