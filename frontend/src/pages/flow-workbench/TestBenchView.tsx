import { useEffect, useMemo, useRef, useState, type ChangeEvent, type CSSProperties, type MouseEvent as ReactMouseEvent } from 'react'
import type { FlowEvent, FlowGraph, FlowLabDetail, FlowNode, RunResult, TestProbeRange } from '../../api.ts'
import { uploadWorkspaceFile } from '../../api.ts'
import { FlowGraphView } from './FlowGraphView.tsx'
import { getProcessDisplayLabel, getProtocolKind } from './nodeModel.ts'
import './TestBench.css'

export type NodeRunState = {
  status: 'idle' | 'running' | 'completed' | 'failed' | 'paused'
  inputKey?: string
  inputValue?: string
  outputKey?: string
  outputValue?: string
  action?: string
  errorMsg?: string
  pendingInteraction?: any
  decisionConsume?: any
  decisionValidationErrors?: any[]
  toolResults?: any[]
  uiHtml?: string
  uiMarkdown?: string
  events: FlowEvent[]
}

type RunScope = 'full' | 'probe'
type DecisionTestMode = 'live_collaboration' | 'mock_resolved'
type ProbeKind = 'start' | 'end'

const TEST_PROBE_MIME = 'application/x-cf-test-probe'

const DECISION_OPTIONS: Array<{ value: DecisionTestMode; label: string; hint: string }> = [
  { value: 'live_collaboration', label: '真实协作', hint: '真实调用 LLM，协作节点先暂停等待确认。' },
  { value: 'mock_resolved', label: 'Mock', hint: 'AI 决策节点直接 resolved，用于快速跑通流程。' },
]

function pretty(value: any) {
  if (value === undefined || value === null || value === '') return ''
  if (typeof value === 'string') return value
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}

function compact(value: any, limit = 180) {
  const text = pretty(value).replace(/\s+/g, ' ').trim()
  return text.length > limit ? `${text.slice(0, limit)}...` : text
}

function extractUiHtml(data: any) {
  if (typeof data?.ui_html === 'string' && data.ui_html.trim()) return data.ui_html
  const output = data?.output_value
  if (output && typeof output === 'object' && typeof output.html === 'string') return output.html
  if (typeof output !== 'string') return ''
  const text = output.trim()
  if (!text) return ''
  if (text.startsWith('<!doctype') || text.startsWith('<html') || text.includes('<body')) return output
  try {
    const parsed = JSON.parse(text)
    return typeof parsed?.html === 'string' ? parsed.html : ''
  } catch {
    return ''
  }
}

function extractUiMarkdown(data: any) {
  if (typeof data?.ui_markdown === 'string' && data.ui_markdown.trim()) return data.ui_markdown
  const output = data?.output_value
  if (output && typeof output === 'object' && typeof output.markdown === 'string') return output.markdown
  if (typeof output !== 'string') return ''
  try {
    const parsed = JSON.parse(output)
    return typeof parsed?.markdown === 'string' ? parsed.markdown : ''
  } catch {
    return ''
  }
}

function getWelcomeHtml(detail: FlowLabDetail) {
  const html = detail.cartridge.welcome_html_content
  if (typeof html === 'string' && html.trim()) return html
  const content = detail.cartridge.welcome_content
  if (typeof content === 'string' && content.trim().startsWith('<')) return content
  return ''
}

function getNodeTitle(node?: FlowNode | null) {
  if (!node) return ''
  return node.title || node.id
}

function buildNodeRunStates(graph: FlowGraph, events: FlowEvent[]) {
  const map = new Map<string, NodeRunState>()
  graph.nodes.forEach((node) => {
    map.set(node.id, { status: 'idle', events: [] })
  })

  events.forEach((event) => {
    const nodeId = event.state
    if (!nodeId || !map.has(nodeId)) return
    const state = map.get(nodeId)!
    state.events.push(event)
    const data = (event.data || {}) as any
    if (event.type === 'state_entered') {
      if (state.status === 'idle') state.status = 'running'
      state.action = data.action || state.action
      return
    }
    if (event.type === 'lab_node_executed' || event.type === 'lab_node_skipped') {
      state.status = 'completed'
    } else if (event.type === 'lab_node_failed') {
      state.status = 'failed'
      state.errorMsg = data.error || data.reason || 'Node failed.'
    } else if (event.type === 'lab_node_paused') {
      state.status = 'paused'
      state.pendingInteraction = data.pending_interaction
    } else {
      return
    }
    state.action = data.action || state.action
    state.inputKey = data.input_key || data.input || state.inputKey
    state.inputValue = data.input_value ?? state.inputValue
    state.outputKey = data.output || state.outputKey
    state.outputValue = data.output_value ?? state.outputValue
    state.toolResults = data.tool_results || state.toolResults
    state.decisionConsume = data.decision_consume || state.decisionConsume
    state.decisionValidationErrors = data.decision_validation_errors || state.decisionValidationErrors
    if (data.action === 'show_ui' || data.action === 'show_welcome' || data.action === 'render_ui' || data.action === 'show_result') {
      state.uiHtml = extractUiHtml(data) || state.uiHtml
      state.uiMarkdown = extractUiMarkdown(data) || state.uiMarkdown
    }
  })
  return map
}

function buildDiagnostics(events: FlowEvent[], latestRun?: RunResult) {
  const items: Array<{ severity: 'error' | 'info'; nodeId: string; title: string; detail: string }> = []
  const dataChain = latestRun?.data_chain || [...events].reverse().find((event) => (event.data as any)?.data_chain)?.data?.data_chain
  ;(dataChain?.breaks || []).forEach((item: any) => {
    items.push({
      severity: 'error',
      nodeId: item.node,
      title: '数据链断裂',
      detail: `${item.node} requires store key "${item.key}", but it was not produced.`,
    })
  })
  ;(dataChain?.missing_optional || []).forEach((item: any) => {
    items.push({
      severity: 'info',
      nodeId: item.node,
      title: '可选输入缺失',
      detail: `${item.node} optional input "${item.key}" was not present.`,
    })
  })
  events.forEach((event) => {
    if (event.type !== 'lab_node_failed') return
    const data = (event.data || {}) as any
    const validation = Array.isArray(data.decision_validation_errors) ? data.decision_validation_errors : []
    const validationText = validation.map((item: any) => `${item.code || 'validation'}: ${item.message || ''}`).join('; ')
    items.push({
      severity: 'error',
      nodeId: event.state || '',
      title: '节点失败',
      detail: validationText || data.error || data.reason || event.message || 'Node failed.',
    })
  })
  return items
}

function getProbePayload(graph: FlowGraph, startId: string, endId: string): TestProbeRange | null {
  const nodes = graph.nodes
  const startIndex = nodes.findIndex((node) => node.id === startId)
  const endIndex = nodes.findIndex((node) => node.id === endId)
  if (startIndex < 0 || endIndex < 0) return null
  const from = Math.min(startIndex, endIndex)
  const to = Math.max(startIndex, endIndex)
  return {
    start_node_id: nodes[from].id,
    end_node_id: nodes[to].id,
    node_ids: nodes.slice(from, to + 1).map((node) => node.id),
  }
}

function InputForm({
  inputs,
  disabled,
  onSubmit,
  onCancel,
}: {
  inputs: any[]
  disabled?: boolean
  onSubmit: (values: Record<string, string>) => void
  onCancel: () => void
}) {
  const filePickerRef = useRef<HTMLInputElement | null>(null)
  const [uploadFieldId, setUploadFieldId] = useState('')
  const [uploadingFile, setUploadingFile] = useState(false)
  const [uploadInfo, setUploadInfo] = useState<{ fieldId: string; filename: string; path: string } | null>(null)
  const [uploadError, setUploadError] = useState('')
  const [values, setValues] = useState<Record<string, string>>(() => {
    const initial: Record<string, string> = {}
    inputs.forEach((input) => {
      initial[input.id] = String(input.default || '')
    })
    return initial
  })
  const pickUploadFile = (id: string) => {
    setUploadFieldId(id)
    setUploadError('')
    filePickerRef.current?.click()
  }
  const handleUploadFile = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file || !uploadFieldId) return
    setUploadingFile(true)
    setUploadError('')
    try {
      const result = await uploadWorkspaceFile(file)
      setValues((current) => ({ ...current, [uploadFieldId]: result.path }))
      setUploadInfo({ fieldId: uploadFieldId, filename: result.filename, path: result.path })
    } catch (error: any) {
      setUploadError(error?.message || '上传失败')
    } finally {
      setUploadingFile(false)
    }
  }
  return (
    <div className="cf-input-modal-backdrop" onClick={onCancel}>
      <div className="cf-input-modal" onClick={(event) => event.stopPropagation()}>
        <div className="cf-input-modal-head">
          <strong>运行输入</strong>
          <button type="button" className="cf-input-modal-close" onClick={onCancel}>x</button>
        </div>
        <div className="cf-input-form">
          <p className="cf-input-form-hint">这些字段会作为本次测试的真实输入传入流程。</p>
          <div className="cf-input-fields">
            <input
              ref={filePickerRef}
              type="file"
              style={{ display: 'none' }}
              accept=".txt,.md,.markdown,.json,.csv,.log,.html,.htm,.xml,.yaml,.yml,.gd,.tscn,.tres,.png,.jpg,.jpeg,.webp"
              onChange={handleUploadFile}
            />
            {inputs.map((input) => {
              const isFilePathInput = input.id === 'file_path' || input.type === 'file'
              return (
              <div key={input.id} className="cf-input-field">
                <label htmlFor={`cf-input-${input.id}`}>
                  {input.label || input.id}
                  {input.required && <span className="cf-required-star">*</span>}
                </label>
                {isFilePathInput && (
                  <div className="cf-upload-row">
                    <button
                      type="button"
                      className="cf-btn-outline"
                      disabled={disabled || uploadingFile}
                      onClick={() => pickUploadFile(input.id)}
                    >
                      {uploadingFile && uploadFieldId === input.id ? '上传中...' : '上传本地文件'}
                    </button>
                    <span>
                      {uploadInfo && uploadInfo.fieldId === input.id ? `已上传：${uploadInfo.filename}` : '上传后自动填入工作区路径'}
                    </span>
                  </div>
                )}
                {uploadError && isFilePathInput && <div className="cf-upload-error">{uploadError}</div>}
                {input.type === 'textarea' ? (
                  <textarea
                    id={`cf-input-${input.id}`}
                    value={values[input.id] || ''}
                    placeholder={input.placeholder || ''}
                    rows={4}
                    onChange={(event) => setValues((current) => ({ ...current, [input.id]: event.target.value }))}
                  />
                ) : input.type === 'select' && Array.isArray(input.options) ? (
                  <select
                    id={`cf-input-${input.id}`}
                    value={values[input.id] || ''}
                    onChange={(event) => setValues((current) => ({ ...current, [input.id]: event.target.value }))}
                  >
                    {input.options.map((option: any) => (
                      <option key={option.value} value={option.value}>{option.label || option.value}</option>
                    ))}
                  </select>
                ) : (
                  <input
                    id={`cf-input-${input.id}`}
                    value={values[input.id] || ''}
                    placeholder={input.placeholder || ''}
                    onChange={(event) => setValues((current) => ({ ...current, [input.id]: event.target.value }))}
                  />
                )}
              </div>
            )})}
          </div>
          <div className="cf-input-actions">
            <button type="button" className="cf-btn-outline" onClick={onCancel}>取消</button>
            <button type="button" className="cf-btn-accent" disabled={disabled} onClick={() => onSubmit(values)}>开始运行</button>
          </div>
        </div>
      </div>
    </div>
  )
}

function PendingInteractionForm({
  pending,
  disabled,
  onSubmit,
}: {
  pending: any
  disabled?: boolean
  onSubmit: (values: Record<string, any>) => void
}) {
  const question = pending?.question || {}
  const schema = question.input_schema || {}
  const properties = schema?.type === 'object' && schema.properties ? schema.properties : { answer: { type: 'string', title: '回复' } }
  const required = new Set<string>(Array.isArray(schema.required) ? schema.required : [])
  const [values, setValues] = useState<Record<string, any>>({})
  const canSubmit = Object.keys(properties).every((key) => !required.has(key) || values[key] !== undefined && values[key] !== '')
  return (
    <div className="cf-pending-card">
      <div className="cf-pending-head">
        <strong>等待用户确认</strong>
        <code>{question.store_key || pending?.interaction_id || 'user_reply'}</code>
      </div>
      <p>{question.prompt || '该节点需要用户输入后继续。'}</p>
      <div className="cf-pending-fields">
        {Object.entries(properties).map(([key, config]: [string, any]) => {
          const enumValues = Array.isArray(config?.enum) ? config.enum.map((item: any) => String(item)) : []
          const label = String(config?.title || config?.label || key)
          return (
            <label key={key} className="cf-pending-field">
              <span>{label}{required.has(key) && <b>*</b>}</span>
              {enumValues.length ? (
                <div className="cf-pending-choice">
                  {enumValues.map((item: string) => (
                    <button
                      key={item}
                      type="button"
                      className={values[key] === item ? 'active' : ''}
                      onClick={() => setValues((current) => ({ ...current, [key]: item }))}
                    >
                      {item === 'approve' ? '满意，继续' : item === 'revise' ? '不满意，重做' : item}
                    </button>
                  ))}
                </div>
              ) : config?.type === 'boolean' ? (
                <input
                  type="checkbox"
                  checked={Boolean(values[key])}
                  onChange={(event) => setValues((current) => ({ ...current, [key]: event.target.checked }))}
                />
              ) : (
                <textarea
                  rows={3}
                  value={values[key] || ''}
                  placeholder={config?.description || ''}
                  onChange={(event) => setValues((current) => ({ ...current, [key]: event.target.value }))}
                />
              )}
            </label>
          )
        })}
      </div>
      <button type="button" className="cf-btn-accent" disabled={disabled || !canSubmit} onClick={() => onSubmit(values)}>
        提交并继续
      </button>
    </div>
  )
}

type InspectorSection = {
  key: string
  title: string
  keyName?: string
  value: any
  variant?: 'default' | 'error' | 'success'
  kind?: 'data' | 'html'
}

function NodeInspector({
  node,
  state,
  artifacts,
  onClose,
}: {
  node: FlowNode
  state: NodeRunState
  artifacts: any[]
  onClose: () => void
}) {
  const label = getProcessDisplayLabel(node) || getProtocolKind(node) || node.action || node.type || 'node'
  const sections = useMemo<InspectorSection[]>(() => {
    const items: InspectorSection[] = []
    if (state.pendingInteraction) items.push({ key: 'pending', title: '待用户输入', value: state.pendingInteraction })
    if (state.errorMsg) items.push({ key: 'error', title: '执行错误', value: state.errorMsg, variant: 'error' })
    if (state.decisionValidationErrors?.length) items.push({ key: 'decision_validation', title: 'Decision validation', value: state.decisionValidationErrors, variant: 'error' })
    if (state.inputValue || state.inputKey) items.push({ key: 'input', title: '输入数据', keyName: state.inputKey, value: state.inputValue || '(missing input value)' })
    if (state.decisionConsume) items.push({ key: 'decision_consume', title: '决策消费', value: state.decisionConsume, variant: state.decisionConsume.status === 'failed' ? 'error' : 'success' })
    if (state.outputValue || state.outputKey) items.push({ key: 'output', title: '输出数据', keyName: state.outputKey, value: state.outputValue || '(empty output)' })
    if (state.toolResults?.length) items.push({ key: 'tools', title: '工具结果', value: state.toolResults })
    if (artifacts.length > 0) items.push({ key: 'artifacts', title: '产物', value: artifacts })
    if (state.uiHtml) items.push({ key: 'ui_html', title: 'UI HTML 预览', value: state.uiHtml, kind: 'html' })
    if (state.uiMarkdown) items.push({ key: 'ui_markdown', title: 'UI Markdown', value: state.uiMarkdown })
    if (state.events.length > 0) items.push({ key: 'events', title: '节点事件', value: state.events.map((event) => ({ type: event.type, message: event.message, data: event.data })) })
    return items
  }, [artifacts, state.decisionConsume, state.decisionValidationErrors, state.errorMsg, state.events, state.inputKey, state.inputValue, state.outputKey, state.outputValue, state.pendingInteraction, state.toolResults, state.uiHtml, state.uiMarkdown])
  const defaultOpenKey = sections[0]?.key || ''
  const [openKey, setOpenKey] = useState(defaultOpenKey)
  const [modalSection, setModalSection] = useState<InspectorSection | null>(null)

  useEffect(() => {
    setOpenKey(defaultOpenKey)
    setModalSection(null)
  }, [defaultOpenKey, node.id])

  return (
    <aside className="cf-node-inspector" style={{ width: 520 }}>
      <div className="cf-inspector-head">
        <div>
          <span className={`cf-status-pill ${state.status}`}>{state.status}</span>
          <strong>{getNodeTitle(node)}</strong>
        </div>
        <button type="button" className="cf-inspector-close" onClick={onClose}>x</button>
      </div>
      <div className="cf-inspector-body">
        <div className="cf-node-tags">
          <span>{label}</span>
          {state.action && <code>{state.action}</code>}
        </div>
        <div className="cf-inspector-sections">
          {sections.length ? sections.map((section) => (
            <InspectorSectionPanel
              key={section.key}
              section={section}
              expanded={openKey === section.key}
              onToggle={() => setOpenKey(openKey === section.key ? '' : section.key)}
              onPopout={() => setModalSection(section)}
            />
          )) : <div className="cf-inspector-empty">这个节点还没有运行数据。</div>}
        </div>
      </div>
      {modalSection && <InspectorValueModal section={modalSection} onClose={() => setModalSection(null)} />}
    </aside>
  )
}

function InspectorSectionPanel({
  section,
  expanded,
  onToggle,
  onPopout,
}: {
  section: InspectorSection
  expanded: boolean
  onToggle: () => void
  onPopout: () => void
}) {
  return (
    <section className={`cf-drawer-section cf-inspector-section ${section.variant || 'default'} ${expanded ? 'open' : 'closed'}`}>
      <div className="cf-drawer-section-head cf-inspector-section-head">
        <button type="button" className="cf-inspector-section-toggle" onClick={onToggle}>
          <strong>{section.title}</strong>
          {section.keyName && <code>{section.keyName}</code>}
          <span>{expanded ? '收起' : '展开'}</span>
        </button>
        <button type="button" className="cf-inspector-popout" onClick={onPopout}>弹窗</button>
      </div>
      {expanded && (
        section.kind === 'html'
          ? <iframe className="cf-ui-preview cf-inspector-html" title={`${section.key}-preview`} srcDoc={String(section.value || '')} sandbox="" />
          : <pre className="cf-field-value cf-inspector-value">{pretty(section.value)}</pre>
      )}
    </section>
  )
}

function InspectorValueModal({ section, onClose }: {
  section: InspectorSection
  onClose: () => void
}) {
  return (
    <div className="cf-inspector-modal-backdrop" onClick={onClose}>
      <div className="cf-inspector-modal" onClick={(event) => event.stopPropagation()}>
        <div className="cf-inspector-modal-head">
          <strong>{section.title}</strong>
          <button type="button" onClick={onClose}>x</button>
        </div>
        {section.kind === 'html'
          ? <iframe className="cf-inspector-modal-html" title={`${section.key}-modal-preview`} srcDoc={String(section.value || '')} sandbox="" />
          : <pre className="cf-inspector-modal-value">{pretty(section.value)}</pre>}
      </div>
    </div>
  )
}

function DiagnosticsPanel({ items, onSelectNode, graph }: {
  items: ReturnType<typeof buildDiagnostics>
  onSelectNode: (node: FlowNode) => void
  graph: FlowGraph
}) {
  const nodeById = useMemo(() => new Map(graph.nodes.map((node) => [node.id, node])), [graph.nodes])
  if (!items.length) {
    return <div className="cf-diag-empty">暂无诊断问题。</div>
  }
  return (
    <div className="cf-diag-list">
      {items.map((item, index) => (
        <button
          key={`${item.nodeId}-${item.title}-${index}`}
          type="button"
          className={`cf-diag-item ${item.severity}`}
          onClick={() => {
            const node = nodeById.get(item.nodeId)
            if (node) onSelectNode(node)
          }}
        >
          <span>{item.title}</span>
          <strong>{item.nodeId || 'system'}</strong>
          <p>{item.detail}</p>
        </button>
      ))}
    </div>
  )
}

function LogTimeline({ events, expanded = false }: { events: FlowEvent[]; expanded?: boolean }) {
  if (!events.length) return <div className="cf-log-empty">暂无运行日志。</div>
  return (
    <div className={`cf-log-timeline ${expanded ? 'expanded' : ''}`}>
      {events.map((event, index) => (
        <div
          key={`${event.type}-${event.state}-${index}`}
          className={`cf-log-row ${event.type?.includes('fail') || event.type?.includes('error') ? 'error' : ''}`}
        >
          <span className="cf-log-idx">{index + 1}</span>
          <span className="cf-log-tag">{event.state || 'system'}</span>
          <div className="cf-log-main">
            <div className="cf-log-label">{event.type || 'event'}</div>
            <div className="cf-log-detail">{event.message || compact(event.data)}</div>
            {expanded && (
              <div className="cf-log-meta">
                {(event.data as any)?.action && <code>{(event.data as any).action}</code>}
                {(event.data as any)?.input_key && <code>in:{(event.data as any).input_key}</code>}
                {(event.data as any)?.output && <code>out:{(event.data as any).output}</code>}
                {(event.data as any)?.decision_validation_errors && <code>decision_validation_errors</code>}
              </div>
            )}
          </div>
        </div>
      ))}
    </div>
  )
}

function ProbeChip({ kind, node, disabled, onActivate }: {
  kind: ProbeKind
  node?: FlowNode
  disabled?: boolean
  onActivate: () => void
}) {
  const label = kind === 'start' ? '开始' : '结束'
  return (
    <button
      type="button"
      className="cf-probe-chip"
      draggable={!disabled}
      disabled={disabled}
      onClick={onActivate}
      onDragStart={(event) => {
        if (disabled) return
        onActivate()
        event.dataTransfer.setData(TEST_PROBE_MIME, kind)
        event.dataTransfer.effectAllowed = 'move'
      }}
      title={`拖动${label}探针到流程节点`}
    >
      <b>{kind === 'start' ? 'S' : 'E'}</b>
      <span>{label}</span>
      <em>{node?.title || node?.id || '未放置'}</em>
    </button>
  )
}

function LogPreviewModal({ events, diagnostics, tab, graph, onSelectNode, onClose }: {
  events: FlowEvent[]
  diagnostics: ReturnType<typeof buildDiagnostics>
  tab: 'diag' | 'log'
  graph: FlowGraph
  onSelectNode: (node: FlowNode) => void
  onClose: () => void
}) {
  const [activeTab, setActiveTab] = useState<'diag' | 'log' | 'raw'>(tab)
  return (
    <div className="cf-log-modal-backdrop" onClick={onClose}>
      <div className="cf-log-modal" onClick={(event) => event.stopPropagation()}>
        <div className="cf-log-modal-head">
          <strong>运行详情</strong>
          <div className="cf-log-modal-tabs">
            <button type="button" className={activeTab === 'diag' ? 'active' : ''} onClick={() => setActiveTab('diag')}>诊断</button>
            <button type="button" className={activeTab === 'log' ? 'active' : ''} onClick={() => setActiveTab('log')}>日志</button>
            <button type="button" className={activeTab === 'raw' ? 'active' : ''} onClick={() => setActiveTab('raw')}>原始事件</button>
            <button type="button" className="cf-log-modal-close" onClick={onClose}>x</button>
          </div>
        </div>
        <div className="cf-log-modal-body">
          {activeTab === 'diag' && <DiagnosticsPanel items={diagnostics} graph={graph} onSelectNode={onSelectNode} />}
          {activeTab === 'log' && <LogTimeline events={events} expanded />}
          {activeTab === 'raw' && <pre className="cf-log-modal-raw">{pretty(events)}</pre>}
        </div>
      </div>
    </div>
  )
}

export function TestBenchView({
  detail,
  runs,
  events,
  onTestRun,
  onAnswerPendingInteraction,
  onRefresh,
}: {
  detail: FlowLabDetail
  runs: RunResult[]
  events: FlowEvent[]
  onTestRun: (inputs: Record<string, string>, probeRange?: TestProbeRange, mode?: 'full' | 'probe', testMode?: Record<string, any>) => Promise<void> | void
  onAnswerPendingInteraction?: (runId: string, values: Record<string, any>) => Promise<void> | void
  onRefresh: () => void
  onManageMcp?: () => void
}) {
  const latestRun = runs[0]
  const [selectedNode, setSelectedNode] = useState<FlowNode | null>(null)
  const [runScope, setRunScope] = useState<RunScope>('full')
  const [decisionMode, setDecisionMode] = useState<DecisionTestMode>('live_collaboration')
  const [showInputForm, setShowInputForm] = useState(false)
  const [pendingModalOpen, setPendingModalOpen] = useState(false)
  const [isRunning, setIsRunning] = useState(false)
  const [logsOpen, setLogsOpen] = useState(true)
  const [logTab, setLogTab] = useState<'diag' | 'log'>('diag')
  const [autoScroll, setAutoScroll] = useState(true)
  const [logPreviewOpen, setLogPreviewOpen] = useState(false)
  const [logHeight, setLogHeight] = useState(150)
  const [showUiPreview, setShowUiPreview] = useState(true)
  const logBodyRef = useRef<HTMLDivElement | null>(null)
  const logDragRef = useRef<{ startY: number; startHeight: number } | null>(null)
  const defaultNodeId = detail.graph.nodes[0]?.id || ''
  const [startNodeId, setStartNodeId] = useState(defaultNodeId)
  const [endNodeId, setEndNodeId] = useState(defaultNodeId)

  const cartridgeInputs = detail.cartridge.inputs || []
  const nodeById = useMemo(() => new Map(detail.graph.nodes.map((node) => [node.id, node])), [detail.graph.nodes])
  const nodeRunStates = useMemo(() => buildNodeRunStates(detail.graph, events), [detail.graph, events])
  const diagnostics = useMemo(() => buildDiagnostics(events, latestRun), [events, latestRun])
  const selectedState = selectedNode ? nodeRunStates.get(selectedNode.id) : null
  const selectedArtifacts = selectedNode
    ? (latestRun?.artifacts || []).filter((artifact: any) => artifact?.source?.node_id === selectedNode.id)
    : []
  const pendingInteraction = latestRun?.status === 'paused_waiting_user' && latestRun.pending_interaction ? latestRun.pending_interaction : null
  const pendingNode = useMemo(() => {
    for (const [nodeId, state] of nodeRunStates.entries()) {
      if (state.status === 'paused' && state.pendingInteraction) return nodeById.get(nodeId) || null
    }
    const pausedEvent = [...events].reverse().find((event) => event.type === 'lab_node_paused' && event.state)
    return pausedEvent?.state ? nodeById.get(pausedEvent.state) || null : null
  }, [events, nodeById, nodeRunStates])
  const startNode = nodeById.get(startNodeId)
  const endNode = nodeById.get(endNodeId)
  const probePayload = useMemo(() => getProbePayload(detail.graph, startNodeId, endNodeId), [detail.graph, startNodeId, endNodeId])
  const selectedProbeNodeIds = probePayload?.node_ids || []
  const canRun = !isRunning && (runScope === 'full' || !!probePayload)
  const latestUiHtml = useMemo(() => {
    for (let index = events.length - 1; index >= 0; index -= 1) {
      const data = events[index]?.data || {}
      const action = data.action
      if (action === 'show_ui' || action === 'show_welcome' || action === 'render_ui' || action === 'show_result') {
        const html = extractUiHtml(data)
        if (html) return html
      }
    }
    return getWelcomeHtml(detail)
  }, [detail, events])
  useEffect(() => {
    if (!autoScroll || !logsOpen || !logBodyRef.current) return
    logBodyRef.current.scrollTo({ top: logBodyRef.current.scrollHeight, behavior: 'smooth' })
  }, [autoScroll, events, logsOpen, logTab])

  useEffect(() => {
    if (!pendingInteraction) setPendingModalOpen(false)
  }, [pendingInteraction])

  useEffect(() => {
    if (!detail.graph.nodes.some((node) => node.id === startNodeId)) {
      setStartNodeId(defaultNodeId)
    }
    if (!detail.graph.nodes.some((node) => node.id === endNodeId)) {
      setEndNodeId(defaultNodeId)
    }
  }, [defaultNodeId, detail.graph.nodes, endNodeId, startNodeId])

  const beginLogResize = (event: ReactMouseEvent<HTMLDivElement>) => {
    event.preventDefault()
    logDragRef.current = { startY: event.clientY, startHeight: logHeight }
    const onMove = (moveEvent: MouseEvent) => {
      const drag = logDragRef.current
      if (!drag) return
      const maxHeight = Math.max(88, Math.min(window.innerHeight * 0.18, 160))
      const nextHeight = Math.max(88, Math.min(maxHeight, drag.startHeight + drag.startY - moveEvent.clientY))
      setLogHeight(nextHeight)
    }
    const onUp = () => {
      logDragRef.current = null
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
  }

  const exportLogs = () => {
    const text = events
      .map((event, index) => `[${index + 1}] ${event.state || 'system'} | ${event.type || 'event'} | ${event.message || ''}\nData: ${JSON.stringify(event.data || {}, null, 2)}`)
      .join('\n\n')
    const blob = new Blob([text], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `test-log-${Date.now()}.txt`
    link.click()
    URL.revokeObjectURL(url)
  }

  const runWithInputs = async (inputs: Record<string, string>) => {
    setShowInputForm(false)
    setLogsOpen(true)
    setLogTab('log')
    setIsRunning(true)
    const testMode = { decision: decisionMode }
    try {
      if (runScope === 'probe') {
        await onTestRun(inputs, probePayload || undefined, 'probe', testMode)
      } else {
        await onTestRun(inputs, undefined, 'full', testMode)
      }
    } finally {
      setIsRunning(false)
    }
  }

  const answerPending = async (values: Record<string, any>) => {
    if (!latestRun?.run_id || !onAnswerPendingInteraction) return
    setIsRunning(true)
    setLogsOpen(true)
    setLogTab('log')
    try {
      await onAnswerPendingInteraction(latestRun.run_id, values)
    } finally {
      setIsRunning(false)
    }
  }

  const openPendingInteraction = () => {
    if (!pendingInteraction) return
    if (pendingNode) setSelectedNode(pendingNode)
    setPendingModalOpen(true)
  }

  const selectRunNode = (node: FlowNode) => {
    setSelectedNode(node)
    if (pendingInteraction && pendingNode?.id === node.id) {
      setPendingModalOpen(true)
    }
  }

  return (
    <div className="cf-tb">
      <div className="cf-tb-top">
        <aside className="cf-tb-op">
          {latestRun && (
            <div className={`cf-op-laststatus ${latestRun.status}`}>
              <span>最近</span>
              <b>{latestRun.status}</b>
              <em>{latestRun.run_mode || 'full_flow'}</em>
              <em>{latestRun.test_mode?.decision || 'live_collaboration'}</em>
            </div>
          )}

          <section className="cf-op-section">
            <strong>决策模式</strong>
            <div className="cf-segment">
              {DECISION_OPTIONS.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  className={decisionMode === option.value ? 'active' : ''}
                  disabled={isRunning}
                  onClick={() => setDecisionMode(option.value)}
                  title={option.hint}
                >
                  {option.label}
                </button>
              ))}
            </div>
            <p>{DECISION_OPTIONS.find((option) => option.value === decisionMode)?.hint}</p>
          </section>

          <section className="cf-probe-panel">
            <div className="cf-probe-head">运行范围</div>
            <div className="cf-range-choices">
              <button
                type="button"
                className={`cf-range-choice ${runScope === 'full' ? 'active' : ''}`}
                disabled={isRunning}
                onClick={() => setRunScope('full')}
              >
                <b>全流程</b>
                <span>从入口节点运行到流程结束</span>
              </button>
              <button
                type="button"
                className={`cf-range-choice ${runScope === 'probe' ? 'active' : ''}`}
                disabled={isRunning}
                onClick={() => setRunScope('probe')}
              >
                <b>探针范围</b>
                <span>拖动 S/E 到节点后只运行选中区间</span>
              </button>
            </div>
            <div className="cf-probe-actions">
              <button type="button" className="cf-btn-accent" disabled={!canRun} onClick={() => cartridgeInputs.length ? setShowInputForm(true) : runWithInputs({})}>
                {isRunning ? '运行中...' : runScope === 'full' ? '运行全流程' : '运行探针范围'}
              </button>
              <button type="button" className="cf-btn-outline" disabled={isRunning} onClick={onRefresh}>刷新</button>
            </div>
            <div className="cf-probe-chips">
              <ProbeChip
                kind="start"
                node={startNode}
                disabled={isRunning}
                onActivate={() => setRunScope('probe')}
              />
              <ProbeChip
                kind="end"
                node={endNode}
                disabled={isRunning}
                onActivate={() => setRunScope('probe')}
              />
            </div>
            {runScope === 'probe' && (
              <p className="cf-probe-hint">拖动 S/E 探针或节点上的 S/E 标记来调整范围。</p>
            )}
          </section>
        </aside>

        <div className={`cf-tb-graph ${pendingInteraction ? 'has-pending' : ''}`}>
          {pendingInteraction && (
            <button type="button" className="cf-pending-bubble" onClick={openPendingInteraction}>
              <strong>等待交互</strong>
              <span>{pendingNode ? `点击与 ${getNodeTitle(pendingNode)} 交互` : '点击打开交互界面'}</span>
            </button>
          )}
          <FlowGraphView
            graph={detail.graph}
            selectedNode={selectedNode}
            focusNodeId={null}
            onSelectNode={selectRunNode}
            readOnlyGraph
            nodeRunStates={nodeRunStates}
            testProbeState={runScope === 'probe' ? {
              startNodeId,
              endNodeId,
              selectedNodeIds: selectedProbeNodeIds,
              onDropProbe: (kind, nodeId) => {
                setRunScope('probe')
                if (kind === 'start') setStartNodeId(nodeId)
                else setEndNodeId(nodeId)
              },
            } : undefined}
          />
          {selectedNode && selectedState && (
            <NodeInspector node={selectedNode} state={selectedState} artifacts={selectedArtifacts} onClose={() => setSelectedNode(null)} />
          )}
          {latestUiHtml && showUiPreview && (
            <div className="cf-welcome-preview">
              <div className="cf-welcome-preview-head">
                <strong>UI 预览</strong>
                <button type="button" onClick={() => setShowUiPreview(false)}>x</button>
              </div>
              <iframe className="cf-welcome-frame" title="latest-ui-preview" srcDoc={latestUiHtml} sandbox="" />
            </div>
          )}
          {latestUiHtml && !showUiPreview && (
            <button type="button" className="cf-welcome-reopen" onClick={() => setShowUiPreview(true)}>
              查看 UI
            </button>
          )}
        </div>
      </div>

      <div
        className={`cf-tb-bottom ${logsOpen ? 'open' : 'closed'}`}
        style={logsOpen ? ({ '--cf-log-height': `${logHeight}px` } as CSSProperties) : undefined}
      >
        <div className="cf-log-resize-handle" onMouseDown={beginLogResize} title="拖动调整日志高度" />
        <div className="cf-bottom-bar">
          <div className="cf-bottom-tabs">
            <button type="button" className={`cf-bottom-tab ${logTab === 'diag' ? 'active' : ''}`} onClick={() => { setLogTab('diag'); setLogsOpen(true) }}>
              诊断{diagnostics.length > 0 && <span className="cf-tab-badge">{diagnostics.length}</span>}
            </button>
            <button type="button" className={`cf-bottom-tab ${logTab === 'log' ? 'active' : ''}`} onClick={() => { setLogTab('log'); setLogsOpen(true) }}>日志</button>
          </div>
          <div className="cf-bottom-tools">
            <label className="cf-autoscroll">
              <input type="checkbox" checked={autoScroll} onChange={(event) => setAutoScroll(event.target.checked)} />
              自动滚动
            </label>
            <button type="button" className="cf-bottom-preview" onClick={() => setLogPreviewOpen(true)}>
              弹窗查看
            </button>
            <button type="button" className="cf-bottom-preview" disabled={!events.length} onClick={exportLogs}>
              导出日志
            </button>
            <button type="button" className="cf-bottom-collapse" onClick={() => setLogsOpen((value) => !value)}>
              {logsOpen ? '收起' : '展开'}
            </button>
          </div>
        </div>
        {logsOpen && (
          <div className="cf-bottom-body" ref={logBodyRef}>
            {logTab === 'diag'
              ? <DiagnosticsPanel items={diagnostics} graph={detail.graph} onSelectNode={selectRunNode} />
              : <LogTimeline events={events} />}
          </div>
        )}
      </div>

      {logPreviewOpen && (
        <LogPreviewModal
          events={events}
          diagnostics={diagnostics}
          tab={logTab}
          graph={detail.graph}
          onSelectNode={selectRunNode}
          onClose={() => setLogPreviewOpen(false)}
        />
      )}

      {pendingModalOpen && pendingInteraction && (
        <div className="cf-pending-modal-backdrop" onClick={() => setPendingModalOpen(false)}>
          <div className="cf-pending-modal" onClick={(event) => event.stopPropagation()}>
            <div className="cf-pending-modal-head">
              <strong>{pendingNode ? `与 ${getNodeTitle(pendingNode)} 交互` : '等待用户交互'}</strong>
              <button type="button" onClick={() => setPendingModalOpen(false)}>x</button>
            </div>
            <PendingInteractionForm
              pending={pendingInteraction}
              disabled={isRunning || !onAnswerPendingInteraction}
              onSubmit={async (values) => {
                await answerPending(values)
                setPendingModalOpen(false)
              }}
            />
          </div>
        </div>
      )}

      {showInputForm && (
        <InputForm
          inputs={cartridgeInputs as any[]}
          disabled={isRunning}
          onSubmit={runWithInputs}
          onCancel={() => setShowInputForm(false)}
        />
      )}
    </div>
  )
}
