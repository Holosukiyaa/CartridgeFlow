import { useEffect, useState } from 'react'
import { Braces, Check, Clipboard, Code2, Database, FileCode2, GitCompareArrows, Lock, LockOpen, RotateCcw, Route, Save, Settings2, ShieldCheck, Unplug } from 'lucide-react'
import type { FlowGraph, FlowNode, McpSourceResponse, StudioToolResource } from '../../api.ts'
import { showToast } from '../../toast.tsx'
import type { EngineeringNodeView, EngineeringSection } from './engineeringNode.ts'
import type { NodeDraft } from './types.ts'

type InspectorTab = 'overview' | 'schema' | 'bindings' | 'execution' | 'routes' | 'policies' | 'raw' | 'diff'

const TABS: Array<{ id: InspectorTab; label: string }> = [
  { id: 'overview', label: '概览' },
  { id: 'schema', label: '数据结构' },
  { id: 'bindings', label: '绑定' },
  { id: 'execution', label: '执行' },
  { id: 'routes', label: '流转' },
  { id: 'policies', label: '策略' },
  { id: 'raw', label: '原始 JSON' },
  { id: 'diff', label: '变更对比' },
]

const DRAFT_FIELD_LABELS: Partial<Record<keyof NodeDraft, string>> = {
  title: '节点名称', displayName: '显示名称', description: '说明', action: '动作', type: '类型',
  kind: '处理类别', executor: '执行器', effect: '副作用', next: '下一步', modelRole: '模型角色',
  input: '输入', output: '输出',
}

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
  const [tab, setTab] = useState<InspectorTab>('overview')
  useEffect(() => { setTab('overview') }, [node?.id])

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
  const visibleSections = tab === 'schema'
    ? ['inputs', 'outputs']
    : tab === 'overview'
      ? view.sections.map((section) => section.id)
      : [tab]
  const copyRaw = async () => {
    try {
      await navigator.clipboard.writeText(view.raw)
      showToast({ title: '节点原始配置已复制', type: 'success' })
    } catch (error: any) {
      showToast({ title: '复制失败', description: error?.message || String(error), type: 'error' })
    }
  }

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
            className={`cf-engineering-lock ${unlocked ? 'unlocked' : 'locked'}`}
            onClick={onToggleLock}
            title={unlocked ? '锁定节点详细设置' : '解锁后编辑节点详细设置'}
            aria-label={unlocked ? '锁定节点详细设置' : '解锁节点详细设置'}
            aria-pressed={unlocked}
            disabled={!canEdit}
          >
            {unlocked ? <LockOpen aria-hidden="true" /> : <Lock aria-hidden="true" />}
          </button>
        </div>
      </header>

      <nav className="cf-engineering-inspector-tabs" aria-label="工程配置检查器">
        {TABS.map((item) => (
          <button type="button" className={tab === item.id ? 'active' : ''} onClick={() => setTab(item.id)} key={item.id}>{item.label}</button>
        ))}
      </nav>

      <div className="cf-engineering-inspector-source">
        <span>文件路径</span>
        <code>/{view.source.path}:{view.source.line}</code>
        <button type="button" onClick={copyRaw} title="复制节点原始配置"><Clipboard aria-hidden="true" /></button>
      </div>

      <div className="cf-engineering-inspector-body">
        {tab === 'overview' && (
          <section className="cf-engineering-overview">
            {unlocked && canEdit && draft && onDraftChange && (
              <section className="cf-engineering-direct-editor">
                <header><Settings2 aria-hidden="true" /><strong>编辑节点配置</strong><span>{dirty ? '有未保存的修改' : '已保存'}</span></header>
                <div className="cf-engineering-direct-editor-grid">
                  {(['title', 'displayName', 'description', 'action', 'type', 'kind', 'executor', 'effect', 'next', 'modelRole', 'input', 'output'] as Array<keyof NodeDraft>).map((key) => {
                    const multiline = key === 'description'
                    return <label key={String(key)} className={multiline ? 'wide' : undefined}><span>{DRAFT_FIELD_LABELS[key] || String(key)}</span>{multiline ? <textarea value={String(draft[key] ?? '')} onChange={(event) => onDraftChange({ [key]: event.target.value } as Partial<NodeDraft>)} /> : <input value={String(draft[key] ?? '')} onChange={(event) => onDraftChange({ [key]: event.target.value } as Partial<NodeDraft>)} />}</label>
                  })}
                </div>
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
            {mcpTool && <section className="cf-engineering-mcp-summary">
              <header><Braces aria-hidden="true" /><strong>MCP 内部流程</strong><code>{mcpTool.transparency || 'unknown'}</code></header>
              <div><span>来源</span><code>{mcpSource?.path || mcpTool.implementation?.entry || mcpTool.source || '-'}</code></div>
              <div><span>解析</span><code>{mcpLoading ? '解析中' : mcpSource?.source_model.ok ? '已解析' : mcpTool.parse_status === 'opaque' ? '不可解析' : mcpTool.parse_status || '未知'}</code></div>
              <div><span>操作</span><code>{mcpSource?.source_model.operations.length ?? mcpTool.operation_count ?? 0}</code></div>
              <footer><button type="button" onClick={onOpenMcp}><Braces aria-hidden="true" />展开流程</button><button type="button" onClick={onOpenMcpSource}><FileCode2 aria-hidden="true" />打开源码</button></footer>
            </section>}
            {view.issues.length > 0 && <ul>{view.issues.map((issue) => <li className={issue.severity} key={issue.code}><b>{issue.code}</b>{issue.message}</li>)}</ul>}
          </section>
        )}

        {(tab === 'overview' || ['schema', 'bindings', 'execution', 'routes', 'policies'].includes(tab)) && visibleSections.map((id) => {
          const section = sectionById.get(id as EngineeringSection['id'])
          return section ? <SectionTable section={section} nodeId={node.id} selectable={stewardTool === 'pointer'} onFieldSelect={onStewardFieldSelect} key={section.id} /> : null
        })}

        {tab === 'raw' && <JsonSource value={view.raw} />}

        {tab === 'diff' && (
          <section className="cf-engineering-diff-empty">
            <GitCompareArrows aria-hidden="true" />
            <strong>当前没有待应用的变更</strong>
            <span>AI 或工程编辑产生补丁后，这里将逐字段显示修改前后内容。</span>
          </section>
        )}
      </div>

      <footer className="cf-engineering-inspector-footer">
        <span>节点字段 <b>{Object.keys(node).length}</b></span>
        <span>输入 <b>{sectionById.get('inputs')?.fields.length || 0}</b></span>
        <span>输出 <b>{sectionById.get('outputs')?.fields.length || 0}</b></span>
        <span>连接 <b>{graph.edges.filter((edge) => edge.from === node.id || edge.to === node.id).length}</b></span>
        <strong>没有隐藏数据</strong>
      </footer>
    </aside>
  )
}
