import { useEffect, useState } from 'react'
import { Braces, Check, Clipboard, Code2, Copy, Database, ExternalLink, Factory, FileCode2, FlaskConical, GitCompareArrows, Pencil, RotateCcw, Route, Save, Settings2, ShieldCheck, Unplug, X } from 'lucide-react'
import type { FlowGraph, FlowNode, McpSourceResponse, StudioToolResource } from '../../api.ts'
import { showToast } from '../../toast.tsx'
import { buildEngineeringRecipe, type EngineeringNodeView, type EngineeringRecipeItem, type EngineeringSection } from './engineeringNode.ts'
import { connectionStatusLabel, getMcpPresentationMode, mcpPresentationLabel } from './McpDetailTemplates.tsx'
import type { NodeDraft } from './types.ts'

type InspectorTab = 'machine' | 'production' | 'contract' | 'fixture' | 'technical'
type TechnicalView = 'raw' | 'diff'

const BASE_TABS: Array<{ id: InspectorTab; label: string }> = [
  { id: 'machine', label: '节点基础' },
  { id: 'production', label: '生产配置' },
  { id: 'contract', label: '数据契约' },
  { id: 'technical', label: '技术视图' },
]

const DRAFT_FIELD_LABELS: Partial<Record<keyof NodeDraft, string>> = {
  title: '节点名称', displayName: '显示名称', description: '说明', action: '动作', type: '类型',
  kind: '处理类别', executor: '执行器', effect: '副作用', next: '下一步', modelRole: '模型角色',
  input: '输入', output: '输出',
}

const PRIMARY_DRAFT_FIELDS: Array<keyof NodeDraft> = ['title', 'displayName', 'description']
const ADVANCED_DRAFT_FIELDS: Array<keyof NodeDraft> = ['action', 'type', 'kind', 'executor', 'effect', 'next', 'modelRole', 'input', 'output']

const SECTION_ICONS = {
  inputs: Database,
  outputs: Unplug,
  bindings: GitCompareArrows,
  execution: Settings2,
  routes: Route,
  policies: ShieldCheck,
}

const SECTION_PATHS: Record<EngineeringSection['id'], string> = {
  inputs: 'input_schema.properties',
  outputs: 'output',
  bindings: 'input_binding',
  execution: '',
  routes: 'action_routes',
  policies: '',
}

function engineeringFieldPath(nodeId: string, sectionId: EngineeringSection['id'], fieldKey: string) {
  if (sectionId === 'outputs') return `states.${nodeId}.output`
  if (sectionId === 'routes' && fieldKey === 'next') return `states.${nodeId}.next`
  const suffix = [SECTION_PATHS[sectionId], fieldKey].filter(Boolean).join('.')
  return `states.${nodeId}.${suffix}`
}

function SectionTable({ section, nodeId, selectable, onFieldSelect }: {
  section: EngineeringSection
  nodeId: string
  selectable: boolean
  onFieldSelect?: (fieldPath: string) => void
}) {
  const Icon = SECTION_ICONS[section.id]
  return (
    <section className="cf-engineering-inspector-section">
      <header><Icon aria-hidden="true" /><strong>{section.label}</strong><span>{section.fields.length}</span></header>
      {section.fields.length ? (
        <div className="cf-engineering-property-list">
          {section.fields.map((field) => (
            <div
              key={`${field.key}:${field.value}`}
              data-tone={field.tone}
              className={selectable ? 'cf-steward-field-target' : undefined}
              role={selectable ? 'button' : undefined}
              tabIndex={selectable ? 0 : undefined}
              onClick={selectable ? () => onFieldSelect?.(engineeringFieldPath(nodeId, section.id, field.key)) : undefined}
              onKeyDown={selectable ? (event) => {
                if (event.key === 'Enter' || event.key === ' ') onFieldSelect?.(engineeringFieldPath(nodeId, section.id, field.key))
              } : undefined}
            >
              <code>{field.key}</code>
              <span title={field.value}>{field.value}</span>
              <em>{field.meta || ''}</em>
            </div>
          ))}
        </div>
      ) : <p className="cf-engineering-empty-inline">未声明字段</p>}
    </section>
  )
}

function JsonSource({ value }: { value: string }) {
  return (
    <pre className="cf-engineering-json" aria-label="节点原始 JSON">
      {value.split('\n').map((line, index) => (
        <span key={index}><i>{index + 1}</i><code>{line || ' '}</code></span>
      ))}
    </pre>
  )
}

function StructuredValue({ value }: { value: unknown }) {
  if (Array.isArray(value)) {
    return (
      <ol className="cf-engineering-structured-array">
        {value.map((item, index) => <li key={index}><i>{index + 1}</i><StructuredValue value={item} /></li>)}
      </ol>
    )
  }
  if (value && typeof value === 'object') {
    return (
      <dl className="cf-engineering-structured-object">
        {Object.entries(value as Record<string, unknown>).map(([key, item]) => (
          <div key={key}><dt>{key}</dt><dd><StructuredValue value={item} /></dd></div>
        ))}
      </dl>
    )
  }
  return <span className="cf-engineering-structured-scalar">{value === null ? 'null' : typeof value === 'boolean' ? String(value) : String(value ?? '')}</span>
}

type TestFixtureView = {
  schema: string
  status: string
  summary: string
  payload: unknown
  consumePath: string
}

function parseRecord(value: unknown): Record<string, any> | null {
  if (value && typeof value === 'object' && !Array.isArray(value)) return value as Record<string, any>
  if (typeof value !== 'string' || !value.trim()) return null
  try {
    const parsed = JSON.parse(value)
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : null
  } catch {
    return null
  }
}

function buildTestFixtureView(node: FlowNode): TestFixtureView | null {
  const raw = parseRecord(node.data) || {}
  const contract = parseRecord(node.decision_contract) || parseRecord(raw.decision_contract)
  const fixture = parseRecord(contract?.offline_decision)
  if (!fixture) return null
  return {
    schema: String(fixture.schema || contract?.schema || 'decision_envelope.v1'),
    status: String(fixture.status || 'resolved'),
    summary: String(fixture.summary || '未填写样例摘要'),
    payload: fixture.payload ?? fixture,
    consumePath: String(contract?.consume?.path || '-'),
  }
}

function fixtureValue(value: unknown) {
  if (typeof value === 'string') return value
  try { return JSON.stringify(value, null, 2) || '' } catch { return String(value ?? '') }
}

function TestFixturePanel({ fixture, onCopy }: { fixture: TestFixtureView; onCopy: (value: string, label: string) => void }) {
  const payloadText = fixtureValue(fixture.payload)
  return (
    <section className="cf-engineering-fixture">
      <header className="cf-engineering-layer-heading">
        <FlaskConical aria-hidden="true" />
        <div><strong>测试夹具</strong><span>Mock 模式的确定性样例</span></div>
        <em>仅测试</em>
      </header>
      <section className="cf-engineering-fixture-notice" role="note">
        <ShieldCheck aria-hidden="true" />
        <div>
          <strong>不会发送给真实模型</strong>
          <p>仅在明确启用 mock_resolved 测试模式时作为固定输出；模型不可用时节点仍会失败，不会把它当作生产结果继续运行。</p>
        </div>
      </section>
      <dl className="cf-engineering-fixture-facts">
        <div><dt>触发模式</dt><dd>mock_resolved</dd></div>
        <div><dt>结果状态</dt><dd>{fixture.status}</dd></div>
        <div><dt>契约</dt><dd>{fixture.schema}</dd></div>
        <div><dt>消费路径</dt><dd>{fixture.consumePath}</dd></div>
      </dl>
      <section className="cf-engineering-fixture-summary">
        <span>样例摘要</span>
        <p>{fixture.summary}</p>
      </section>
      <section className="cf-engineering-fixture-payload">
        <header>
          <div><strong>固定模拟输出</strong><span>{payloadText.length} 字符</span></div>
          <button type="button" onClick={() => onCopy(payloadText, '测试夹具输出')} title="复制测试夹具输出"><Copy aria-hidden="true" /></button>
        </header>
        <div><StructuredValue value={fixture.payload} /></div>
      </section>
    </section>
  )
}

function productionItemMeta(item: EngineeringRecipeItem) {
  if (Array.isArray(item.data)) return `${item.data.length} 项`
  if (item.data && typeof item.data === 'object') return `${Object.keys(item.data as Record<string, unknown>).length} 项`
  return item.long ? `${item.value.length} 字符` : ''
}

function ProductionConfiguration({ items, sources, onCopy }: {
  items: EngineeringRecipeItem[]
  sources: EngineeringNodeView['remoteSources']
  onCopy: (value: string, label: string) => void
}) {
  const compactItems = items.filter((item) => !item.long && item.data === undefined)
  const detailItems = items.filter((item) => item.long || item.data !== undefined)
  return (
    <section className="cf-engineering-production">
      <header className="cf-engineering-layer-heading">
        <Factory aria-hidden="true" />
        <div><strong>生产配置</strong><span>配方、提示词与信源</span></div>
        <em>{items.length + sources.length} 项</em>
      </header>
      {compactItems.length > 0 && <dl className="cf-engineering-production-facts">
        {compactItems.map((item) => <div key={item.label}><dt>{item.label}</dt><dd className={item.mono ? 'mono' : undefined}>{item.value}</dd></div>)}
      </dl>}
      {detailItems.map((item) => (
        <section className="cf-engineering-production-detail" key={item.label}>
          <header>
            <div><strong>{item.label}</strong><span>{productionItemMeta(item)}</span></div>
            <button type="button" onClick={() => onCopy(item.value, item.label)} title={`复制${item.label}`}><Copy aria-hidden="true" /></button>
          </header>
          {item.data !== undefined ? <StructuredValue value={item.data} /> : <pre>{item.value}</pre>}
        </section>
      ))}
      {sources.length > 0 && <section className="cf-engineering-production-sources">
        <header><Database aria-hidden="true" /><strong>信源</strong><span>{sources.length}</span></header>
        <ul>
          {sources.map((source) => <li key={source.url}>
            <div><strong>{source.name}</strong><code>{source.url}</code></div>
            <span>
              <button type="button" onClick={() => onCopy(source.url, `${source.name} 地址`)} title="复制地址"><Copy aria-hidden="true" /></button>
              <a href={source.url} target="_blank" rel="noreferrer" title={`打开 ${source.url}`}><ExternalLink aria-hidden="true" /></a>
            </span>
          </li>)}
        </ul>
      </section>}
      {!items.length && !sources.length && <div className="cf-engineering-production-empty"><Factory aria-hidden="true" /><strong>这个节点没有生产配置</strong><span>它仅使用节点基础定义和数据契约运行。</span></div>}
    </section>
  )
}

export function EngineeringInspector({ node, graph, view, unlocked, canEdit, onToggleLock, draft, dirty, saving, onDraftChange, onResetDraft, onSaveDraft, stewardTool = 'none', onStewardFieldSelect, mcpTool, mcpSource, mcpLoading = false, onOpenMcp, onOpenMcpSource }: {
  node: FlowNode | null
  graph: FlowGraph
  view: EngineeringNodeView | null
  unlocked: boolean
  canEdit: boolean
  onToggleLock: () => void
  draft?: NodeDraft
  dirty?: boolean
  saving?: boolean
  onDraftChange?: (patch: Partial<NodeDraft>) => void
  onResetDraft?: () => void
  onSaveDraft?: () => void
  stewardTool?: 'none' | 'pointer' | 'lasso'
  onStewardFieldSelect?: (fieldPath: string) => void
  mcpTool?: StudioToolResource | null
  mcpSource?: McpSourceResponse | null
  mcpLoading?: boolean
  onOpenMcp?: () => void
  onOpenMcpSource?: () => void
}) {
  const [tab, setTab] = useState<InspectorTab>('machine')
  const [technicalView, setTechnicalView] = useState<TechnicalView>('raw')
  useEffect(() => { setTab('machine'); setTechnicalView('raw') }, [node?.id])

  if (!node || !view) {
    return (
      <aside className="cf-engineering-inspector empty">
        <Code2 aria-hidden="true" />
        <strong>未选择节点</strong>
        <span>选择画布节点以检查完整工程配置。</span>
      </aside>
    )
  }

  const sectionById = new Map(view.sections.map((section) => [section.id, section]))
  const mcpPresentationMode = mcpTool ? getMcpPresentationMode(mcpTool) : null
  const recipe = buildEngineeringRecipe(node)
  const testFixture = buildTestFixtureView(node)
  const tabs = testFixture
    ? [...BASE_TABS.slice(0, 3), { id: 'fixture' as const, label: '测试夹具' }, BASE_TABS[3]]
    : BASE_TABS
  const copyValue = async (value: string, label: string) => {
    try {
      await navigator.clipboard.writeText(value)
      showToast({ title: `${label}已复制`, type: 'success' })
    } catch (error: any) {
      showToast({ title: '复制失败', description: error?.message || String(error), type: 'error' })
    }
  }
  const copyRaw = () => copyValue(view.raw, '节点原始配置')

  return (
    <aside className="cf-engineering-inspector">
      <header className="cf-engineering-inspector-head">
        <span>{String(graph.nodes.findIndex((item) => item.id === node.id) + 1).padStart(2, '0')}</span>
        <div className="cf-engineering-inspector-title">
          <strong title={node.display_name || node.title}>{node.display_name || node.title}</strong>
          <code title={node.id}>{node.id}</code>
        </div>
        <div className="cf-engineering-inspector-actions">
          <i className={`health-${view.configHealth}`}><Check aria-hidden="true" />{view.configHealthLabel}</i>
          <button
            type="button"
            className={`cf-engineering-edit-toggle ${unlocked ? 'editing' : ''}`}
            onClick={() => { if (!unlocked) setTab('machine'); onToggleLock() }}
            title={!canEdit ? '该节点由流程边界或工程投影管理，不能直接编辑' : unlocked ? '退出节点编辑' : '编辑节点配置'}
            aria-label={unlocked ? '退出节点编辑' : '编辑节点配置'}
            aria-pressed={unlocked}
            disabled={!canEdit}
          >
            {unlocked ? <X aria-hidden="true" /> : <Pencil aria-hidden="true" />}
            <span>{unlocked ? '退出编辑' : '编辑'}</span>
          </button>
        </div>
      </header>

      <nav className={`cf-engineering-inspector-tabs ${testFixture ? 'has-fixture' : ''}`} aria-label="工程配置检查器">
        {tabs.map((item) => (
          <button type="button" className={tab === item.id ? 'active' : ''} onClick={() => setTab(item.id)} key={item.id}>{item.label}</button>
        ))}
      </nav>

      <div className="cf-engineering-inspector-source">
        <span>文件路径</span>
        <code>/{view.source.path}:{view.source.line}</code>
        <button type="button" onClick={copyRaw} title="复制节点原始配置"><Clipboard aria-hidden="true" /></button>
      </div>

      <div className="cf-engineering-inspector-body">
        {tab === 'machine' && (
          <section className="cf-engineering-overview">
            <header className="cf-engineering-layer-heading">
              <Settings2 aria-hidden="true" />
              <div><strong>节点基础</strong><span>机器定义与执行能力</span></div>
            </header>
            {unlocked && canEdit && draft && onDraftChange && (
              <section className="cf-engineering-direct-editor">
                <header><Settings2 aria-hidden="true" /><strong>编辑节点配置</strong><span>{dirty ? '有未保存的修改' : '已保存'}</span></header>
                <div className="cf-engineering-direct-editor-grid">
                  {PRIMARY_DRAFT_FIELDS.map((key) => {
                    const multiline = key === 'description'
                    return <label key={String(key)} className={multiline ? 'wide' : undefined}><span>{DRAFT_FIELD_LABELS[key] || String(key)}</span>{multiline ? <textarea value={String(draft[key] ?? '')} onChange={(event) => onDraftChange({ [key]: event.target.value } as Partial<NodeDraft>)} /> : <input value={String(draft[key] ?? '')} onChange={(event) => onDraftChange({ [key]: event.target.value } as Partial<NodeDraft>)} />}</label>
                  })}
                </div>
                <details className="cf-engineering-advanced-editor">
                  <summary><span>运行与契约字段</span><small>{ADVANCED_DRAFT_FIELDS.length} 项</small></summary>
                  <div className="cf-engineering-direct-editor-grid">
                    {ADVANCED_DRAFT_FIELDS.map((key) => <label key={String(key)}><span>{DRAFT_FIELD_LABELS[key] || String(key)}</span><input value={String(draft[key] ?? '')} onChange={(event) => onDraftChange({ [key]: event.target.value } as Partial<NodeDraft>)} /></label>)}
                  </div>
                </details>
                <footer>
                  <button type="button" disabled={!dirty || saving} onClick={onResetDraft}><RotateCcw aria-hidden="true" />重置</button>
                  <button type="button" className="primary" disabled={!dirty || saving} onClick={onSaveDraft}><Save aria-hidden="true" />{saving ? '保存中...' : '保存节点'}</button>
                </footer>
              </section>
            )}
            <div><span>类型</span><code>{node.type}</code></div>
            <div><span>处理类别</span><code>{view.semanticKind}</code></div>
            <div><span>动作</span><code>{node.action || '-'}</code></div>
            <div><span>作用范围</span><code>{node.scope || 'root'}</code></div>
            <p>{view.description}</p>
            {mcpTool && mcpPresentationMode === 'local_parsable' && <section className="cf-engineering-mcp-summary">
              <header><Braces aria-hidden="true" /><strong>本地 MCP 内部流程</strong><code>{mcpTool.transparency || 'unknown'}</code></header>
              <div><span>来源</span><code>{mcpSource?.path || mcpTool.implementation?.entry || mcpTool.source || '-'}</code></div>
              <div><span>解析</span><code>{mcpLoading ? '解析中' : mcpSource?.source_model.ok ? '已解析' : mcpTool.parse_status === 'opaque' ? '不可解析' : '状态未知'}</code></div>
              <div><span>操作</span><code>{mcpSource?.source_model.operations.length ?? mcpTool.operation_count ?? 0}</code></div>
              <footer><button type="button" onClick={onOpenMcp}><Braces aria-hidden="true" />展开内部流程</button><button type="button" onClick={onOpenMcpSource}><FileCode2 aria-hidden="true" />查看源码</button></footer>
            </section>}
            {mcpTool && mcpPresentationMode === 'external_connector' && <section className="cf-engineering-mcp-summary">
              <header><Braces aria-hidden="true" /><strong>外部 MCP</strong><code>{mcpTool.transparency || 'unknown'}</code></header>
              <div><span>服务 / 工具</span><code>{[mcpTool.server, mcpTool.tool].filter(Boolean).join(' / ') || '未声明'}</code></div>
              <div><span>连接状态</span><code>{connectionStatusLabel(mcpTool.health?.connection.status)}</code></div>
              <div><span>透明度</span><code>{mcpPresentationLabel(mcpTool)}</code></div>
              <footer><button type="button" onClick={onOpenMcp}><Braces aria-hidden="true" />查看连接详情</button></footer>
            </section>}
            {mcpTool && mcpPresentationMode === 'unauditable' && <section className="cf-engineering-mcp-summary">
              <header><Braces aria-hidden="true" /><strong>不可审计 MCP</strong><code>{mcpTool.transparency || 'unknown'}</code></header>
              <div><span>服务 / 工具</span><code>{[mcpTool.server, mcpTool.tool].filter(Boolean).join(' / ') || '未声明'}</code></div>
              <div><span>内部实现</span><code>不可观测</code></div>
              <div><span>可用信息</span><code>已知调用契约</code></div>
              <footer><button type="button" onClick={onOpenMcp}><Braces aria-hidden="true" />查看已知契约</button></footer>
            </section>}
            {view.issues.length > 0 && <ul>{view.issues.map((issue) => <li className={issue.severity} key={issue.code}><b>{issue.origin === 'runtime_preflight' ? '运行前检查' : '配置提示'} · {issue.code}</b>{issue.message}</li>)}</ul>}
          </section>
        )}

        {tab === 'machine' && ['execution', 'routes', 'policies'].map((id) => {
          const section = sectionById.get(id as EngineeringSection['id'])
          return section ? <SectionTable section={section} nodeId={node.id} selectable={stewardTool === 'pointer'} onFieldSelect={onStewardFieldSelect} key={section.id} /> : null
        })}

        {tab === 'production' && <ProductionConfiguration items={recipe} sources={view.remoteSources} onCopy={(value, label) => void copyValue(value, label)} />}

        {tab === 'contract' && <>
          <header className="cf-engineering-layer-heading cf-engineering-contract-heading">
            <Database aria-hidden="true" />
            <div><strong>数据契约</strong><span>输入、输出与绑定关系</span></div>
          </header>
          {['inputs', 'outputs', 'bindings'].map((id) => {
          const section = sectionById.get(id as EngineeringSection['id'])
          return section ? <SectionTable section={section} nodeId={node.id} selectable={stewardTool === 'pointer'} onFieldSelect={onStewardFieldSelect} key={section.id} /> : null
          })}
        </>}

        {tab === 'fixture' && testFixture && <TestFixturePanel fixture={testFixture} onCopy={(value, label) => void copyValue(value, label)} />}

        {tab === 'technical' && <section className="cf-engineering-technical">
          <nav aria-label="技术视图">
            <button type="button" className={technicalView === 'raw' ? 'active' : ''} onClick={() => setTechnicalView('raw')}><Braces aria-hidden="true" />原始 JSON</button>
            <button type="button" className={technicalView === 'diff' ? 'active' : ''} onClick={() => setTechnicalView('diff')}><GitCompareArrows aria-hidden="true" />变更对比</button>
          </nav>
          {technicalView === 'raw' ? <JsonSource value={view.raw} /> : (
            <section className="cf-engineering-diff-empty">
              <GitCompareArrows aria-hidden="true" />
              <strong>当前没有待应用的变更</strong>
              <span>AI 或工程编辑产生补丁后，这里将逐字段显示修改前后内容。</span>
            </section>
          )}
        </section>}
      </div>

      <footer className="cf-engineering-inspector-footer">
        <span>节点字段 <b>{Object.keys(node).length}</b></span>
        <span>输入 <b>{sectionById.get('inputs')?.fields.length || 0}</b></span>
        <span>输出 <b>{sectionById.get('outputs')?.fields.length || 0}</b></span>
        <span>连接 <b>{graph.edges.filter((edge) => edge.from === node.id || edge.to === node.id).length}</b></span>
        <strong>{tab === 'production' ? '完整配方' : tab === 'machine' ? '静态定义' : tab === 'contract' ? '数据边界' : tab === 'fixture' ? '测试数据' : '技术数据'}</strong>
      </footer>
    </aside>
  )
}
