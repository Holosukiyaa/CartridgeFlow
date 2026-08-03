import { useEffect, useState } from 'react'
import { Braces, Check, ChevronDown, Clipboard, Code2, Copy, Database, ExternalLink, Factory, FileCode2, FlaskConical, GitCompareArrows, Link2, Maximize2, Minimize2, Pencil, RotateCcw, Route, Save, Search, Settings2, ShieldCheck, Unplug, WrapText, X } from 'lucide-react'
import type { FlowGraph, FlowNode, McpSourceResponse, StudioToolResource } from '../../api.ts'
import { showToast } from '../../toast.tsx'
import { buildEngineeringRecipe, humanizeEngineeringKey, humanizeEngineeringValue, type EngineeringNodeView, type EngineeringRecipeItem, type EngineeringSection } from './engineeringNode.ts'
import { connectionStatusLabel, getMcpPresentationMode, mcpPresentationLabel } from './McpDetailTemplates.tsx'
import { NodeExperiencePanel } from './NodeExperiencePanel.tsx'
import type { NodeDraft } from './types.ts'

type InspectorTab = 'experience' | 'machine' | 'production' | 'contract' | 'fixture' | 'technical'
type TechnicalView = 'raw' | 'diff'

const BASE_TABS: Array<{ id: InspectorTab; label: string }> = [
  { id: 'experience', label: '用户体验' },
  { id: 'production', label: '节点调优' },
  { id: 'machine', label: '节点基础' },
  { id: 'contract', label: '数据契约' },
  { id: 'technical', label: '技术视图' },
]

const SECTION_ICONS = {
  inputs: Database,
  outputs: Unplug,
  bindings: GitCompareArrows,
  execution: Settings2,
  routes: Route,
  policies: ShieldCheck,
}

const BASIC_FACTS = [
  { key: 'type', label: '节点类型', help: '决定节点在流程中的基础职责。' },
  { key: 'kind', label: '处理类别', help: '由节点决策并执行业务细节。' },
  { key: 'action', label: '执行动作', help: '描述节点实际执行的操作。' },
  { key: 'executor', label: '执行器', help: '负责运行并生成结果的能力。' },
  { key: 'scope', label: '作用范围', help: '说明节点属于流程中的哪一层。' },
  { key: 'effect', label: '副作用', help: '说明是否会向外部系统写入数据。' },
] as const

const DRAFT_FIELD_LABELS: Partial<Record<keyof NodeDraft, string>> = {
  title: '节点名称', displayName: '显示名称', description: '说明', systemPrompt: '系统指令', prompt: '处理指令', temperature: '温度', maxTokens: '最大输出', action: '动作', type: '类型',
  kind: '处理类别', executor: '执行器', effect: '副作用', next: '下一步', modelRole: '模型角色',
  input: '输入', output: '输出', timeoutMs: '超时（毫秒）',
}

const KEY_PARAMETER_FIELDS: Array<keyof NodeDraft> = ['title', 'displayName', 'description', 'systemPrompt', 'prompt', 'modelRole', 'temperature', 'maxTokens', 'timeoutMs']

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
              <div className="cf-engineering-property-name">
                <strong>{humanizeEngineeringKey(field.key)}</strong>
                {humanizeEngineeringKey(field.key) !== field.key && <code>{field.key}</code>}
              </div>
              <span title={field.value}>{humanizeEngineeringValue(field.value)}</span>
              <em>{humanizeEngineeringValue(field.meta || '')}</em>
            </div>
          ))}
        </div>
      ) : <p className="cf-engineering-empty-inline">未声明字段</p>}
    </section>
  )
}

function JsonLine({ line, search }: { line: string; search: string }) {
  const pattern = /("(?:\\.|[^"\\])*")(\s*:)?|(-?\d+(?:\.\d+)?)|\b(true|false|null)\b/g
  const parts: Array<{ text: string; tone?: string }> = []
  let cursor = 0
  for (const match of line.matchAll(pattern)) {
    const index = match.index || 0
    if (index > cursor) parts.push({ text: line.slice(cursor, index) })
    parts.push({
      text: match[0],
      tone: match[2] ? 'key' : match[1] ? 'string' : match[3] ? 'number' : 'literal',
    })
    cursor = index + match[0].length
  }
  if (cursor < line.length) parts.push({ text: line.slice(cursor) })
  const normalizedSearch = search.trim().toLowerCase()
  return <>{parts.length ? parts.map((part, index) => {
    const matched = Boolean(normalizedSearch && part.text.toLowerCase().includes(normalizedSearch))
    return <span className={[part.tone ? `token-${part.tone}` : '', matched ? 'search-match' : ''].filter(Boolean).join(' ')} key={index}>{part.text}</span>
  }) : ' '}</>
}

function JsonSource({ value, search = '', wrap = true }: { value: string; search?: string; wrap?: boolean }) {
  return (
    <pre className={`cf-engineering-json ${wrap ? 'wrap' : 'nowrap'}`} aria-label="节点原始 JSON">
      {value.split('\n').map((line, index) => (
        <span key={index}><i>{index + 1}</i><code><JsonLine line={line} search={search} /></code></span>
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
          <div key={key}>
            <dt><strong>{humanizeEngineeringKey(key)}</strong>{humanizeEngineeringKey(key) !== key && <code>{key}</code>}</dt>
            <dd><StructuredValue value={item} /></dd>
          </div>
        ))}
      </dl>
    )
  }
  return <span className="cf-engineering-structured-scalar">{value === null ? '空值' : typeof value === 'boolean' ? value ? '是' : '否' : String(value ?? '')}</span>
}

function structuredSummary(value: unknown) {
  if (Array.isArray(value)) return `列表，共 ${value.length} 项`
  if (value && typeof value === 'object') {
    const keys = Object.keys(value as Record<string, unknown>)
    return `对象，共 ${keys.length} 个字段${keys.length ? `：${keys.slice(0, 3).map(humanizeEngineeringKey).join('、')}` : ''}`
  }
  return '结构化数据'
}

function StructuredPreview({ value, onOpen }: { value: unknown; onOpen: () => void }) {
  return (
    <button type="button" className="cf-engineering-structured-preview" onClick={onOpen}>
      <span><Database aria-hidden="true" /><strong>{structuredSummary(value)}</strong></span>
      <em>在大窗口中查看完整层级</em>
      <Maximize2 aria-hidden="true" />
    </button>
  )
}

function JsonDetailDialog({ title, value, onCopy, onClose }: { title: string; value: unknown; onCopy: () => void; onClose: () => void }) {
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => { if (event.key === 'Escape') onClose() }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [onClose])
  return (
    <div className="cf-engineering-json-dialog-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose() }}>
      <section className="cf-engineering-json-dialog" role="dialog" aria-modal="true" aria-label={`${title}结构详情`}>
        <header>
          <div><span>结构化数据</span><strong>{title}</strong><small>{structuredSummary(value)}</small></div>
          <button type="button" onClick={onCopy} title="复制完整数据"><Copy aria-hidden="true" /></button>
          <button type="button" onClick={onClose} title="关闭"><X aria-hidden="true" /></button>
        </header>
        <div className="cf-engineering-json-dialog-body"><StructuredValue value={value} /></div>
      </section>
    </div>
  )
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

function TestFixturePanel({ fixture, onCopy, onOpenJson }: { fixture: TestFixtureView; onCopy: (value: string, label: string) => void; onOpenJson: (title: string, value: unknown) => void }) {
  const payloadText = fixtureValue(fixture.payload)
  const payloadRecord = parseRecord(fixture.payload)
  const payloadKeys = payloadRecord ? Object.keys(payloadRecord) : []
  const payloadType = Array.isArray(fixture.payload) ? '列表' : payloadRecord ? '对象' : '文本'
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
        <div><dt>结果状态</dt><dd>{humanizeEngineeringValue(fixture.status)}</dd></div>
        <div><dt>数据契约</dt><dd>{fixture.schema}</dd></div>
        <div><dt>消费路径</dt><dd>{fixture.consumePath}</dd></div>
      </dl>
      <section className="cf-engineering-fixture-summary">
        <span>样例摘要</span>
        <p>{fixture.summary}</p>
      </section>
      <section className="cf-engineering-fixture-payload">
        <header><strong>固定模拟输出</strong></header>
        <div className="cf-engineering-fixture-payload-card">
          <Braces aria-hidden="true" />
          <dl>
            <div><dt>数据类型</dt><dd>{payloadType}</dd></div>
            <div><dt>字段数量</dt><dd>{payloadKeys.length || 1} 个字段</dd></div>
            <div><dt>主要字段</dt><dd>{payloadKeys[0] ? humanizeEngineeringKey(payloadKeys[0]) : '固定结果'}</dd></div>
          </dl>
          <footer>
            <button type="button" onClick={() => onCopy(payloadText, '测试夹具输出')}><Copy aria-hidden="true" />复制</button>
            <button type="button" className="primary" onClick={() => onOpenJson('测试夹具固定输出', fixture.payload)}>查看完整结构<Maximize2 aria-hidden="true" /></button>
          </footer>
        </div>
      </section>
    </section>
  )
}

function productionItemMeta(item: EngineeringRecipeItem) {
  if (Array.isArray(item.data)) return `${item.data.length} 项`
  if (item.data && typeof item.data === 'object') return `${Object.keys(item.data as Record<string, unknown>).length} 项`
  return item.long ? `${item.value.length} 字符` : ''
}

function compactPrompt(value: string, limit = 220) {
  const normalized = value.replace(/\s+/g, ' ').trim()
  return normalized.length > limit ? `${normalized.slice(0, limit)}...` : normalized
}

function ProductionConfiguration({ node, items, sources, onCopy, onOpenJson }: {
  node: FlowNode
  items: EngineeringRecipeItem[]
  sources: EngineeringNodeView['remoteSources']
  onCopy: (value: string, label: string) => void
  onOpenJson: (title: string, value: unknown) => void
}) {
  const byLabel = new Map(items.map((item) => [item.label, item]))
  const roleItem = byLabel.get('模型角色')
  const parameterItem = byLabel.get('模型参数')
  const systemItem = byLabel.get('系统指令')
  const promptItem = byLabel.get('处理指令')
  const outputItem = byLabel.get('输出结构')
  const isPromptRecipe = Boolean(systemItem || promptItem)
  const maxTokens = parameterItem?.value.match(/最大输出\s+(\d+)/)?.[1] || '-'
  const timeout = parameterItem?.value.match(/超时\s+(\d+)/)?.[1] || '-'
  const outputPath = outputItem?.value.split('→')[0]?.trim() || ''
  const outputField = outputPath.split('.').filter(Boolean).at(-1) || 'output'
  const taskGoal = promptItem?.value.split(/返回\s+ONLY|返回\s+一个|返回格式|要求[：:]/)[0]?.trim() || ''
  const constraintCount = Math.max(0, (promptItem?.value.match(/(?:^|\n)\s*-\s+/g) || []).length)
  const compactItems = items.filter((item) => !item.long && item.data === undefined)
  const detailItems = items.filter((item) => item.long || item.data !== undefined)
  return (
    <section className="cf-engineering-production">
      {isPromptRecipe ? <>
        <p className="cf-engineering-production-intro">决定 AI 如何理解任务并生成{humanizeEngineeringKey(outputField)}</p>
        <dl className="cf-engineering-production-metrics">
          <div><dt>模型角色</dt><dd>{humanizeEngineeringValue(roleItem?.value || node.model_role || '-')}</dd></div>
          <div><dt>最大输出</dt><dd>{maxTokens}</dd></div>
          <div><dt>超时</dt><dd>{timeout} 秒</dd></div>
        </dl>
        {systemItem && <section className="cf-engineering-prompt-card">
          <header>
            <div><strong>系统指令</strong><span>{systemItem.value.length} 字符</span></div>
            <button type="button" onClick={() => onCopy(systemItem.value, systemItem.label)} title="复制系统指令"><Copy aria-hidden="true" /></button>
            <button type="button" onClick={() => onOpenJson('完整系统指令', systemItem.value)}>查看完整指令<ExternalLink aria-hidden="true" /></button>
          </header>
          <p className="cf-engineering-prompt-purpose">指导 AI 的整体行为与输出风格，是整段任务的系统级约束。</p>
          <pre>{compactPrompt(systemItem.value)}</pre>
        </section>}
        {promptItem && <section className="cf-engineering-prompt-card process">
          <header>
            <div><strong>处理指令</strong><span>{promptItem.value.length} 字符</span></div>
            <button type="button" onClick={() => onCopy(promptItem.value, promptItem.label)} title="复制处理指令"><Copy aria-hidden="true" /></button>
            <button type="button" onClick={() => onOpenJson('完整处理指令', promptItem.value)}>查看完整提示词<ExternalLink aria-hidden="true" /></button>
          </header>
          <dl className="cf-engineering-process-summary">
            <div><dt>任务目标</dt><dd>{taskGoal || compactPrompt(promptItem.value, 90)}</dd></div>
            <div><dt>返回格式</dt><dd>{/JSON/i.test(promptItem.value) ? 'JSON' : '结构化结果'}</dd></div>
            <div><dt>输出字段</dt><dd><code>{outputField}</code></dd></div>
            <div><dt>约束条件</dt><dd>{constraintCount || '多'} 条</dd></div>
          </dl>
        </section>}
        {outputItem && <section className="cf-engineering-output-schema">
          <header><strong>输出结构</strong><span>Schema 概览</span><button type="button" onClick={() => onCopy(outputItem.value, outputItem.label)} title="复制输出结构"><Copy aria-hidden="true" /></button></header>
          <div className="cf-engineering-schema-tree">
            <div><code>status</code><span>决策 / 处理状态</span></div>
            <div><code>payload</code><span>输出内容容器</span></div>
            <div className="nested"><code>{outputField}</code><span>{humanizeEngineeringKey(outputField)}（主输出）</span></div>
            <div><code>...</code><span>其他可选字段</span></div>
          </div>
        </section>}
      </> : <>
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
            {item.data !== undefined
              ? <StructuredPreview value={item.data} onOpen={() => onOpenJson(item.label, item.data)} />
              : <pre>{item.value}</pre>}
          </section>
        ))}
      </>}
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

function contractFieldType(value: string) {
  const type = value.split('->')[0]?.trim() || value
  return humanizeEngineeringValue(type)
}

function contractTarget(value: string) {
  return value.includes('->') ? value.split('->').at(-1)?.trim() || '' : ''
}

function ContractConfiguration({ inputs, outputs, bindings, nodeId, selectable, onFieldSelect }: {
  inputs?: EngineeringSection
  outputs?: EngineeringSection
  bindings?: EngineeringSection
  nodeId: string
  selectable: boolean
  onFieldSelect?: (fieldPath: string) => void
}) {
  return (
    <section className="cf-engineering-contract">
      <p className="cf-engineering-contract-intro">定义节点接收的数据、产出的数据以及流转位置。</p>
      <section className="cf-engineering-contract-group">
        <header><Database aria-hidden="true" /><strong>输入</strong><span>{inputs?.fields.length || 0}</span></header>
        <div className="cf-engineering-contract-cards">
          {inputs?.fields.length ? inputs.fields.map((field) => <article key={`${field.key}:${field.value}`} className={selectable ? 'cf-steward-field-target' : undefined} onClick={selectable ? () => onFieldSelect?.(engineeringFieldPath(nodeId, 'inputs', field.key)) : undefined}>
            <header><strong>{humanizeEngineeringKey(field.key)}</strong><span>{contractFieldType(field.value)}</span><em>{humanizeEngineeringValue(field.meta || '')}</em></header>
            <p>来源：流程存储 <code>{field.key}</code></p>
            <code>{field.key}</code>
          </article>) : <p className="cf-engineering-contract-empty">此节点不接收显式输入。</p>}
        </div>
      </section>
      <section className="cf-engineering-contract-group outputs">
        <header><Unplug aria-hidden="true" /><strong>输出</strong><span>{outputs?.fields.length || 0}</span></header>
        <div className="cf-engineering-contract-cards">
          {outputs?.fields.length ? outputs.fields.map((field) => {
            const target = contractTarget(field.value)
            const declared = /declared output|contract/i.test(field.value)
            return <article key={`${field.key}:${field.value}`} className={selectable ? 'cf-steward-field-target' : undefined} onClick={selectable ? () => onFieldSelect?.(engineeringFieldPath(nodeId, 'outputs', field.key)) : undefined}>
              <header><strong>{humanizeEngineeringKey(field.key)}</strong><span>{contractFieldType(field.value)}</span><em>{humanizeEngineeringValue(field.meta || '')}</em></header>
              <p>{target ? <>写入位置：<code>{target}</code></> : declared ? '供后续节点读取' : '作为节点处理结果继续流转'}</p>
              <code>{field.key}</code>
            </article>
          }) : <p className="cf-engineering-contract-empty">此节点没有声明输出。</p>}
        </div>
      </section>
      {bindings?.fields.length ? <SectionTable section={bindings} nodeId={nodeId} selectable={selectable} onFieldSelect={onFieldSelect} /> : <div className="cf-engineering-contract-no-binding"><Link2 aria-hidden="true" /><span>此节点无需额外字段绑定</span></div>}
    </section>
  )
}

export function EngineeringInspector({ node, graph, view, unlocked, canEdit, versioned, onToggleLock, draft, dirty, saving, onDraftChange, onResetDraft, onSaveDraft, stewardTool = 'none', onStewardFieldSelect, mcpTool, mcpSource, mcpLoading = false, onOpenMcp, onOpenMcpSource }: {
  node: FlowNode | null
  graph: FlowGraph
  view: EngineeringNodeView | null
  unlocked: boolean
  canEdit: boolean
  versioned: boolean
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
  const [tab, setTab] = useState<InspectorTab>('experience')
  const [technicalView, setTechnicalView] = useState<TechnicalView>('raw')
  const [technicalSearch, setTechnicalSearch] = useState('')
  const [jsonWrap, setJsonWrap] = useState(true)
  const [technicalFullscreen, setTechnicalFullscreen] = useState(false)
  const [jsonDialog, setJsonDialog] = useState<{ title: string; value: unknown } | null>(null)
  useEffect(() => { setTab('experience'); setTechnicalView('raw'); setTechnicalSearch(''); setTechnicalFullscreen(false); setJsonDialog(null) }, [node?.id])

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
    ? [...BASE_TABS.slice(0, 4), { id: 'fixture' as const, label: '测试夹具' }, BASE_TABS[4]]
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
    <>
    <aside className={`cf-engineering-inspector tab-${tab}`}>
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
            onClick={() => { if (!unlocked) setTab('experience'); onToggleLock() }}
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

      {tab === 'technical' && <div className="cf-engineering-inspector-source technical-meta">
        <span>文件路径</span>
        <code>/{view.source.path}:{view.source.line}</code>
        <em>{Object.keys(node).length} 个字段 · 只读</em>
        <button type="button" onClick={copyRaw} title="复制节点原始配置"><Clipboard aria-hidden="true" /></button>
      </div>}

      <div className="cf-engineering-inspector-body">
        {tab === 'experience' && draft && <NodeExperiencePanel
          node={node}
          draft={draft}
          editing={Boolean(unlocked && canEdit)}
          versioned={versioned}
          dirty={dirty}
          saving={saving}
          onDraftChange={onDraftChange}
          onReset={onResetDraft}
          onSave={onSaveDraft}
        />}

        {tab === 'machine' && (
          <section className="cf-engineering-overview">
            <p className="cf-engineering-basic-intro">节点基础描述节点身份、执行方式和运行边界；业务内容请前往生产配置查看。</p>
            <div className="cf-engineering-basic-identity"><Settings2 aria-hidden="true" /><strong>{humanizeEngineeringValue(view.semanticKind)}</strong><span>·</span><strong>{humanizeEngineeringValue(node.action || '-')}</strong><span>·</span><strong>{humanizeEngineeringValue(node.scope || 'root')}内运行</strong></div>
            {BASIC_FACTS.map((fact) => {
              const rawValue = fact.key === 'kind' ? view.semanticKind : fact.key === 'action' ? node.action || '-' : fact.key === 'scope' ? node.scope || 'root' : fact.key === 'executor' ? node.executor || '-' : fact.key === 'effect' ? node.effect || 'none' : node.type
              return <div className="cf-engineering-basic-fact" key={fact.key}><span>{fact.label}</span><strong>{humanizeEngineeringValue(String(rawValue))}</strong>{humanizeEngineeringValue(String(rawValue)) !== String(rawValue) && <code>{String(rawValue)}</code>}<small>{fact.help}</small></div>
            })}
            <p className="cf-engineering-basic-description"><strong>节点说明</strong>{view.description}</p>
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
            <div className="cf-engineering-basic-accordions">
              <details><summary><Settings2 aria-hidden="true" /><span>执行信息</span><ChevronDown aria-hidden="true" /></summary>{['execution', 'routes', 'policies'].map((id) => {
                const section = sectionById.get(id as EngineeringSection['id'])
                return section ? <SectionTable section={section} nodeId={node.id} selectable={stewardTool === 'pointer'} onFieldSelect={onStewardFieldSelect} key={section.id} /> : null
              })}</details>
              <details><summary><Unplug aria-hidden="true" /><span>输入与输出（{(sectionById.get('inputs')?.fields.length || 0) + (sectionById.get('outputs')?.fields.length || 0)}）</span><ChevronDown aria-hidden="true" /></summary>{['inputs', 'outputs'].map((id) => {
                const section = sectionById.get(id as EngineeringSection['id'])
                return section ? <SectionTable section={section} nodeId={node.id} selectable={stewardTool === 'pointer'} onFieldSelect={onStewardFieldSelect} key={section.id} /> : null
              })}</details>
              <details><summary><Factory aria-hidden="true" /><span>配方与系统指令</span><ChevronDown aria-hidden="true" /></summary><div className="cf-engineering-basic-recipe-list">{recipe.length ? recipe.map((item) => <div key={item.label}><strong>{item.label}</strong><span>{productionItemMeta(item) || compactPrompt(item.value, 52)}</span></div>) : <p>此节点没有独立生产配方。</p>}</div></details>
              <details><summary><Link2 aria-hidden="true" /><span>来源与引用</span><ChevronDown aria-hidden="true" /></summary><div className="cf-engineering-basic-recipe-list">{view.remoteSources.length ? view.remoteSources.map((source) => <div key={source.url}><strong>{source.name}</strong><code>{source.url}</code></div>) : <p>此节点没有外部信源。</p>}</div></details>
              <details><summary><Code2 aria-hidden="true" /><span>运行日志</span><ChevronDown aria-hidden="true" /></summary><p className="cf-engineering-basic-log-note">节点运行后，可在运行详情中查看实时输入、输出与执行事件。</p></details>
            </div>
          </section>
        )}

        {tab === 'production' && <>
          {unlocked && canEdit && draft && onDraftChange && <section className="cf-engineering-direct-editor cf-key-parameter-editor">
            <header><Settings2 aria-hidden="true" /><strong>关键参数</strong><span>{dirty ? '有未保存的修改' : '已保存'}</span></header>
            <div className="cf-engineering-direct-editor-grid">
              {KEY_PARAMETER_FIELDS.map((key) => {
                const multiline = key === 'description' || key === 'systemPrompt' || key === 'prompt'
                const numeric = key === 'temperature' || key === 'maxTokens' || key === 'timeoutMs'
                return <label key={String(key)} className={multiline ? 'wide' : undefined}><span>{DRAFT_FIELD_LABELS[key] || String(key)}</span>{multiline ? <textarea value={String(draft[key] ?? '')} onChange={(event) => onDraftChange({ [key]: event.target.value } as Partial<NodeDraft>)} /> : <input type={numeric ? 'number' : 'text'} step={key === 'temperature' ? '0.1' : '1'} value={String(draft[key] ?? '')} onChange={(event) => onDraftChange({ [key]: event.target.value } as Partial<NodeDraft>)} />}</label>
              })}
            </div>
            <footer>
              <button type="button" disabled={!dirty || saving} onClick={onResetDraft}><RotateCcw aria-hidden="true" />重置</button>
              <button type="button" className="primary" disabled={!dirty || saving} onClick={onSaveDraft}><Save aria-hidden="true" />{saving ? '保存中...' : '保存调优'}</button>
            </footer>
          </section>}
          <ProductionConfiguration node={node} items={recipe} sources={view.remoteSources} onCopy={(value, label) => void copyValue(value, label)} onOpenJson={(title, value) => setJsonDialog({ title, value })} />
        </>}

        {tab === 'contract' && <ContractConfiguration inputs={sectionById.get('inputs')} outputs={sectionById.get('outputs')} bindings={sectionById.get('bindings')} nodeId={node.id} selectable={stewardTool === 'pointer'} onFieldSelect={onStewardFieldSelect} />}

        {tab === 'fixture' && testFixture && <TestFixturePanel fixture={testFixture} onCopy={(value, label) => void copyValue(value, label)} onOpenJson={(title, value) => setJsonDialog({ title, value })} />}

        {tab === 'technical' && <>
          {technicalFullscreen && <button type="button" className="cf-engineering-technical-backdrop" onClick={() => setTechnicalFullscreen(false)} aria-label="退出技术视图全屏" />}
          <section className={`cf-engineering-technical ${technicalFullscreen ? 'fullscreen' : ''}`}>
          <nav aria-label="技术视图">
            <button type="button" className={technicalView === 'raw' ? 'active' : ''} onClick={() => setTechnicalView('raw')}><Braces aria-hidden="true" />原始 JSON</button>
            <button type="button" className={technicalView === 'diff' ? 'active' : ''} onClick={() => setTechnicalView('diff')}><GitCompareArrows aria-hidden="true" />变更对比</button>
            <label className="cf-engineering-json-search"><Search aria-hidden="true" /><input value={technicalSearch} onChange={(event) => setTechnicalSearch(event.target.value)} placeholder="搜索" aria-label="搜索 JSON" /></label>
            <button type="button" className={jsonWrap ? 'active subtle' : 'subtle'} onClick={() => setJsonWrap((current) => !current)} aria-pressed={jsonWrap}><WrapText aria-hidden="true" />自动换行<i /></button>
            <button type="button" className="subtle" onClick={copyRaw}><Copy aria-hidden="true" />复制</button>
            <button type="button" className="subtle" onClick={() => setTechnicalFullscreen((current) => !current)}>{technicalFullscreen ? <Minimize2 aria-hidden="true" /> : <Maximize2 aria-hidden="true" />}{technicalFullscreen ? '退出全屏' : '全屏查看'}</button>
          </nav>
          {technicalView === 'raw' ? <JsonSource value={view.raw} search={technicalSearch} wrap={jsonWrap} /> : (
            <section className="cf-engineering-diff-empty">
              <GitCompareArrows aria-hidden="true" />
              <strong>当前没有待应用的变更</strong>
              <span>AI 或用户编辑配置后，这里将逐字段显示修改前后的内容。</span>
            </section>
          )}
          </section>
        </>}
      </div>

      <footer className="cf-engineering-inspector-footer">
        <span>节点字段 <b>{Object.keys(node).length}</b></span>
        <span>输入 <b>{sectionById.get('inputs')?.fields.length || 0}</b></span>
        <span>输出 <b>{sectionById.get('outputs')?.fields.length || 0}</b></span>
        <span>连接 <b>{graph.edges.filter((edge) => edge.from === node.id || edge.to === node.id).length}</b></span>
        <strong>{tab === 'experience' ? '用户投影' : tab === 'production' ? '内部调优' : tab === 'machine' ? '静态定义' : tab === 'contract' ? '数据边界' : tab === 'fixture' ? '测试数据' : '技术数据'}</strong>
      </footer>
    </aside>
    {jsonDialog && <JsonDetailDialog title={jsonDialog.title} value={jsonDialog.value} onCopy={() => void copyValue(fixtureValue(jsonDialog.value), jsonDialog.title)} onClose={() => setJsonDialog(null)} />}
    </>
  )
}
