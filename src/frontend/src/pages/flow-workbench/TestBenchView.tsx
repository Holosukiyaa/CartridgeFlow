import { useEffect, useMemo, useRef, useState, type ChangeEvent, type CSSProperties, type MouseEvent as ReactMouseEvent } from 'react'
import type { ArtifactItem, FlowEvent, FlowGraph, FlowLabDetail, FlowNode, RunResult, TestProbeRange } from '../../api.ts'
import { ApiError, controlCartridgeRun, fetchCartridgeRunCheckpoints, uploadWorkspaceFile } from '../../api.ts'
import { showToast } from '../../toast.tsx'
import { DlcSandboxFrame } from '../../components/DlcSandboxFrame.tsx'
import { InteractionSandboxFrame } from '../../components/InteractionSandboxFrame.tsx'
import { FlowGraphView } from './FlowGraphView.tsx'
import { buildNodeRunStates, extractUiHtml, getProbePayload, type NodeRunState } from './runState.ts'
import { getProcessDisplayLabel, getProtocolKind } from './nodeModel.ts'
import { passiveHtmlDocument } from './passiveHtml.ts'
import { resolveRunInputDefault } from './inputDefaults.ts'
import './TestBench.css'
type RunScope = 'full' | 'probe'
type RecoveryAction = 'retry_current_node' | 'resume_checkpoint' | 'rollback_to_node' | 'restart_run'

function pretty(value: any) {
  if (value === undefined || value === null || value === '') return ''
  if (typeof value === 'string') {
    const text = value.trim()
    if (text.startsWith('{') || text.startsWith('[')) {
      try {
        return JSON.stringify(JSON.parse(text), null, 2)
      } catch {
        return value
      }
    }
    return value
  }
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

function redactDiagnosticValue(value: any, key = ''): any {
  if (/api[_-]?key|authorization|password|secret|token|cookie/i.test(key)) return '[REDACTED]'
  if (Array.isArray(value)) return value.map((item) => redactDiagnosticValue(item))
  if (value && typeof value === 'object') {
    return Object.fromEntries(Object.entries(value).map(([childKey, childValue]) => [childKey, redactDiagnosticValue(childValue, childKey)]))
  }
  if (typeof value === 'string' && /\b(sk-[a-z0-9_-]{12,}|bearer\s+[a-z0-9._-]{12,})\b/i.test(value)) return '[REDACTED]'
  return value
}

function collectRunArtifacts(run?: RunResult | null): ArtifactItem[] {
  const deliveryArtifacts = run?.delivery?.artifacts || []
  const runArtifacts = run?.artifacts || []
  return (deliveryArtifacts.length ? deliveryArtifacts : runArtifacts).filter((item): item is ArtifactItem => !!item?.name)
}
function collectLatestArtifactBatch(events: FlowEvent[]): ArtifactItem[] {
  for (let index = events.length - 1; index >= 0; index -= 1) {
    const event = events[index]
    if (event.type !== 'lab_node_executed' && event.type !== 'artifact_collected') continue
    const artifacts = (event.data as any)?.artifacts
    if (!Array.isArray(artifacts)) continue
    const batch = artifacts.filter((item): item is ArtifactItem => !!item?.name)
    if (batch.length) return batch
  }
  return []
}

function artifactPath(item: ArtifactItem) {
  return item.display_path || item.path || item.url || item.name
}

function artifactTypeLabel(item: ArtifactItem) {
  const type = (item.type || '').toLowerCase()
  const mime = (item.mime_type || '').toLowerCase()
  if (type === 'html' || mime.includes('html') || item.name.endsWith('.html')) return 'HTML'
  if (type === 'image' || mime.startsWith('image/')) return '图片'
  if (type === 'video' || mime.startsWith('video/')) return '视频'
  if (type === 'json' || mime.includes('json') || item.name.endsWith('.json')) return 'JSON'
  if (type === 'text' || mime.startsWith('text/')) return '文本'
  return item.type || '文件'
}

function artifactSourceLabel(item: ArtifactItem, nodeById?: Map<string, FlowNode>) {
  const source = item.source || {}
  const nodeId = String(source.node_id || source.state || '')
  if (!nodeId) return ''
  return nodeById?.get(nodeId)?.title || nodeId
}

async function copyArtifactPath(item: ArtifactItem) {
  const text = artifactPath(item)
  try {
    await navigator.clipboard.writeText(text)
    showToast({ title: '路径已复制', description: text, type: 'success' })
  } catch (error: any) {
    showToast({ title: '复制失败', description: error?.message || String(error), type: 'error' })
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

function ArtifactList({
  artifacts,
  nodeById,
  compact = false,
}: {
  artifacts: ArtifactItem[]
  nodeById?: Map<string, FlowNode>
  compact?: boolean
}) {
  if (!artifacts.length) return null
  return (
    <div className={`cf-artifact-list ${compact ? 'compact' : ''}`}>
      {artifacts.map((item, index) => {
        const source = artifactSourceLabel(item, nodeById)
        const path = artifactPath(item)
        return (
          <div className="cf-artifact-card" key={`${item.artifact_id || item.name}-${index}`}>
            <div className="cf-artifact-main">
              <div className="cf-artifact-title-row">
                <strong>{item.name}</strong>
                <span>{artifactTypeLabel(item)}</span>
              </div>
              {source && <em>{source}</em>}
              <code title={path}>{path}</code>
            </div>
            <div className="cf-artifact-actions">
              <a
                className={`cf-artifact-action ${item.url ? '' : 'disabled'}`}
                href={item.url || '#'}
                target="_blank"
                rel="noreferrer"
                onClick={(event) => {
                  if (!item.url) event.preventDefault()
                }}
              >
                打开
              </a>
              <button type="button" className="cf-artifact-action" onClick={() => void copyArtifactPath(item)}>
                复制
              </button>
            </div>
          </div>
        )
      })}
    </div>
  )
}

function DeliveryArtifactsPanel({
  run,
  artifacts,
  nodeById,
}: {
  run?: RunResult
  artifacts: ArtifactItem[]
  nodeById: Map<string, FlowNode>
}) {
  if (!run || artifacts.length === 0) return null
  return (
    <section className="cf-artifacts-preview">
      <div className="cf-artifacts-preview-head">
        <div>
          <strong>交付产物</strong>
          <span>{artifacts.length} 个文件</span>
        </div>
      </div>
      {run.delivery?.summary && <p className="cf-artifacts-summary">{run.delivery.summary}</p>}
      <ArtifactList artifacts={artifacts} nodeById={nodeById} compact />
    </section>
  )
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
  events.forEach((event) => {
    if (event.type !== 'lab_node_failed') return
    const data = (event.data || {}) as any
    const validation = Array.isArray(data.decision_validation_errors) ? data.decision_validation_errors : []
    const validationText = validation.map((item: any) => `${item.code || 'validation'}: ${item.message || ''}`).join('; ')
    items.push({
      severity: 'error',
      nodeId: event.state || '',
      title: '节点失败',
      detail: validationText || (data.error_envelope ? `[${data.error_envelope.code}] ${data.error_envelope.message}` : data.error || data.reason || event.message || 'Node failed.'),
    })
  })
  return items
}
export function RunInputDialog({
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
      initial[input.id] = resolveRunInputDefault(input)
    })
    return initial
  })
  const missingRequiredInputs = useMemo(() => {
    return inputs.filter((input) => input.required && !String(values[input.id] || '').trim())
  }, [inputs, values])
  const canStart = !disabled && !uploadingFile && missingRequiredInputs.length === 0
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
          <p className="cf-input-form-hint">这些字段会作为本次真实运行的输入传入流程。</p>
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
                {input.required && !String(values[input.id] || '').trim() && (
                  <div className="cf-upload-error">该字段不能为空。</div>
                )}
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
                    type={input.type === 'date' ? 'date' : 'text'}
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
            <button type="button" className="cf-btn-accent" disabled={!canStart} onClick={() => canStart && onSubmit(values)}>开始运行</button>
          </div>
        </div>
      </div>
    </div>
  )
}

export function PendingInteractionForm({
  pending,
  disabled,
  onSubmit,
  artifacts = [],
  nodeById,
  artifactScopeLabel,
  onPresentationSize,
}: {
  pending: any
  disabled?: boolean
  onSubmit: (values: Record<string, any>, options?: Record<string, any>) => void
  artifacts?: ArtifactItem[]
  nodeById?: Map<string, FlowNode>
  artifactScopeLabel?: string
  onPresentationSize?: (size: { width: number; height: number }) => void
}) {
  const question = pending?.question || {}
  const isV2 = pending?.schema === 'cartridgeflow.pending_interaction.v2'
  const isSandboxed = isV2 && pending?.presentation?.component_runtime === 'sandboxed'
  const allowedActions = isV2 && Array.isArray(pending?.allowed_actions)
    ? pending.allowed_actions.map((item: any) => typeof item === 'string'
      ? { id: item, label: pending?.action_labels?.[item] || item }
      : item)
    : []
  const [selectedActionId, setSelectedActionId] = useState(String(allowedActions[0]?.id || ''))
  const schema = isV2 ? pending?.action_schemas?.[selectedActionId] || { type: 'object' } : question.input_schema || {}
  const properties = schema?.type === 'object' ? schema.properties || {} : { answer: { type: 'string', title: '回复' } }
  const required = new Set<string>(Array.isArray(schema.required) ? schema.required : [])
  const [values, setValues] = useState<Record<string, any>>({})
  const [sandboxDraftHash, setSandboxDraftHash] = useState('')
  const [showArtifacts, setShowArtifacts] = useState(false)
  const presentationFrameRef = useRef<HTMLIFrameElement | null>(null)
  const canSubmitValues = (candidate: Record<string, any>) => Object.keys(properties).every((key) => !required.has(key) || candidate[key] !== undefined && candidate[key] !== '')
  const isConfirmValue = (item: string) => ['approve', 'approved', 'confirm', 'confirmed', 'yes', '通过'].includes(item.trim().toLowerCase())
  const isRevisionValue = (item: any) => {
    const value = String(item || '').trim().toLowerCase()
    return value.startsWith('revise') || ['reject', 'rejected', 'revision', 'modify', 'no', '驳回'].includes(value)
  }
  const revisionSelected = Object.entries(properties).some(([key, config]: [string, any]) => {
    return Array.isArray(config?.enum) && isRevisionValue(values[key])
  })
  const revisionFeedbackKey = Object.entries(properties).find(([key, config]: [string, any]) => {
    return !Array.isArray(config?.enum) && config?.type !== 'boolean' && /feedback|意见|reason|原因/i.test(`${key} ${config?.title || ''}`)
  })?.[0]
  const hasRevisionFeedback = !revisionFeedbackKey || String(values[revisionFeedbackKey] || '').trim().length > 0
  const canSubmit = canSubmitValues(values) && (!revisionSelected || hasRevisionFeedback)
  const submitValue = (key: string, value: any) => setValues((current) => ({ ...current, [key]: value }))
  const choiceLabel = (key: string, item: string, configuredLabel = '') => {
    if (isConfirmValue(item)) return configuredLabel || '确认决策'
    if (!isRevisionValue(item)) return configuredLabel || item
    const route = (pending?.resume?.answer_routes || []).find((candidate: any) => {
      const match = candidate?.match || {}
      return match.field === key && String(match.equals || '').toLowerCase() === item.toLowerCase()
    })
    if (route?.policy === 'resume_target_node') return configuredLabel ? `${configuredLabel}（回到上一步）` : '回到上一步重做'
    return configuredLabel || '修改决策'
  }
  useEffect(() => {
    setValues({})
    setSandboxDraftHash('')
    setShowArtifacts(false)
    const firstAction = pending?.allowed_actions?.[0]
    setSelectedActionId(String(typeof firstAction === 'string' ? firstAction : firstAction?.id || ''))
  }, [pending?.interaction_id])
  const measurePresentation = () => {
    const frame = presentationFrameRef.current
    const document = frame?.contentDocument
    const body = document?.body
    if (!document || !body || !onPresentationSize) return
    const style = frame.contentWindow?.getComputedStyle(body)
    const paddingX = Number.parseFloat(style?.paddingLeft || '0') + Number.parseFloat(style?.paddingRight || '0')
    const paddingBottom = Number.parseFloat(style?.paddingBottom || '0')
    const bodyRect = body.getBoundingClientRect()
    const children = [...body.children] as HTMLElement[]
    const naturalWidth = Math.max(0, ...children.map((item) => item.getBoundingClientRect().width)) + paddingX
    const naturalBottom = Math.max(bodyRect.top, ...children.map((item) => item.getBoundingClientRect().bottom))
    onPresentationSize({
      width: Math.ceil(Math.max(320, Math.min(960, naturalWidth || body.scrollWidth))),
      height: Math.ceil(Math.max(120, Math.min(600, naturalBottom - bodyRect.top + paddingBottom))),
    })
  }
  return (
    <div className="cf-pending-card">
      <div className="cf-pending-head">
        <strong>等待用户确认</strong>
        <code>{question.store_key || pending?.interaction_id || 'user_reply'}</code>
      </div>
      <p>{question.prompt || '该节点需要用户输入后继续。'}</p>
      {question.review_content && (
        <div className="cf-pending-review-content">
          <span>待审核内容</span>
          <pre>{question.review_content}</pre>
        </div>
      )}
      {isV2 && pending?.presentation?.html && (
        <iframe ref={presentationFrameRef} className="cf-passive-interaction-frame" title="interaction preview" sandbox="allow-same-origin" srcDoc={passiveHtmlDocument(pending.presentation.html)} onLoad={measurePresentation} />
      )}
      {isSandboxed && (
        <InteractionSandboxFrame
          pending={pending}
          onDraft={(value, draftHash) => { setValues(value); setSandboxDraftHash(draftHash) }}
          onPropose={(actionId) => { if (allowedActions.some((item: any) => item.id === actionId)) setSelectedActionId(actionId) }}
        />
      )}
      {isV2 && allowedActions.length > 1 && (
        <div className="cf-host-action-picker">
          <span>由底座提交下一步</span>
          <div>
            {allowedActions.map((action: any) => (
              <button key={action.id} type="button" className={selectedActionId === action.id ? 'active' : ''} onClick={() => { setSelectedActionId(action.id); setValues({}) }}>
                {action.label || action.id}
              </button>
            ))}
          </div>
        </div>
      )}
      {artifacts.length > 0 && <div className="cf-pending-draft-entry">
          <div className="cf-pending-draft-copy">
            <strong>草稿作品</strong>
            <span>确认前可查看 {artifacts.length} 个相关产物</span>
          </div>
          <button
            type="button"
            className="cf-btn-outline cf-pending-draft-toggle"
            onClick={() => setShowArtifacts((value) => !value)}
          >
            {showArtifacts ? '收起草稿' : '查看草稿'}
          </button>
        </div>}
      {showArtifacts && artifacts.length > 0 && (
        <div className="cf-pending-draft-panel">
          <div className="cf-pending-draft-panel-head">
            <strong>{artifactScopeLabel || '本次草稿'}</strong>
            <span>{artifacts.length} 项</span>
          </div>
          <ArtifactList artifacts={artifacts} nodeById={nodeById} compact />
        </div>
      )}
      {!isSandboxed && <div className="cf-pending-fields">
        {Object.entries(properties).map(([key, config]: [string, any]) => {
          const enumValues = Array.isArray(config?.enum) ? config.enum.map((item: any) => String(item)) : []
          const enumNames = Array.isArray(config?.enumNames) ? config.enumNames.map((item: any) => String(item)) : []
          const label = String(config?.title || config?.label || key)
          const feedbackRequired = revisionSelected && key === revisionFeedbackKey
          return (
            <label key={key} className="cf-pending-field">
              <span>{label}{(required.has(key) || feedbackRequired) && <b>*</b>}</span>
              {enumValues.length ? (
                <div className="cf-pending-choice">
                  {enumValues.map((item: string, index: number) => (
                    <button
                      key={item}
                      type="button"
                      disabled={disabled}
                      className={values[key] === item ? 'active' : ''}
                      onClick={() => submitValue(key, item)}
                    >
                      {choiceLabel(key, item, enumNames[index])}
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
                  rows={2}
                  value={values[key] || ''}
                  placeholder={config?.description || ''}
                  onChange={(event) => setValues((current) => ({ ...current, [key]: event.target.value }))}
                />
              )}
            </label>
          )
        })}
      </div>}
      {isSandboxed && <div className={`cf-sandbox-draft-state ${sandboxDraftHash ? 'ready' : ''}`}><strong>{sandboxDraftHash ? '草稿已由底座保存' : '等待组件写入草稿'}</strong><span>{sandboxDraftHash ? `sha256:${sandboxDraftHash.slice(0, 12)}…` : '脚本不能直接提交或改变 Flow'}</span></div>}
      {revisionSelected && !hasRevisionFeedback && (
        <p className="cf-pending-validation">回到上一步前，请填写本次不满意的原因或具体修改要求。</p>
      )}
      <button type="button" className="cf-btn-accent" disabled={disabled || !canSubmit || (isV2 && !selectedActionId) || (isSandboxed && !sandboxDraftHash)} onClick={() => onSubmit(values, isV2 ? {
        action_id: selectedActionId,
        input_revision: pending?.input_snapshot?.input_revision,
        idempotency_key: `${pending?.interaction_id}:${selectedActionId}:${pending?.input_snapshot?.input_revision || ''}`,
        ...(isSandboxed ? { draft_hash: sandboxDraftHash } : {}),
      } : undefined)}>
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
  kind?: 'data' | 'html' | 'artifacts'
}

function NodeInspector({
  node,
  state,
  artifacts,
  nodeById,
  onClose,
}: {
  node: FlowNode
  state: NodeRunState
  artifacts: ArtifactItem[]
  nodeById: Map<string, FlowNode>
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
    if (artifacts.length > 0) items.push({ key: 'artifacts', title: '产物', value: artifacts, kind: 'artifacts' })
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
              nodeById={nodeById}
            />
          )) : <div className="cf-inspector-empty">这个节点还没有运行数据。</div>}
        </div>
      </div>
      {modalSection && <InspectorValueModal section={modalSection} nodeById={nodeById} onClose={() => setModalSection(null)} />}
    </aside>
  )
}

function InspectorSectionPanel({
  section,
  expanded,
  onToggle,
  onPopout,
  nodeById,
}: {
  section: InspectorSection
  expanded: boolean
  onToggle: () => void
  onPopout: () => void
  nodeById: Map<string, FlowNode>
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
          : section.kind === 'artifacts'
            ? <ArtifactList artifacts={section.value as ArtifactItem[]} nodeById={nodeById} />
            : <pre className="cf-field-value cf-inspector-value">{pretty(section.value)}</pre>
      )}
    </section>
  )
}

function InspectorValueModal({ section, nodeById, onClose }: {
  section: InspectorSection
  nodeById: Map<string, FlowNode>
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
          : section.kind === 'artifacts'
            ? <div className="cf-inspector-modal-value"><ArtifactList artifacts={section.value as ArtifactItem[]} nodeById={nodeById} /></div>
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
      {events.map((event, index) => {
        const isThinking = event.type === 'lab_node_llm_started'
        const isError = event.type?.includes('fail') || event.type?.includes('error')
        return (
          <div
            key={`${event.type}-${event.state}-${index}`}
            className={`cf-log-row ${isThinking ? 'thinking' : ''} ${isError ? 'error' : ''}`}
          >
            <span className="cf-log-idx">{index + 1}</span>
            <span className="cf-log-tag">{event.state || 'system'}</span>
            <div className="cf-log-main">
              <div className="cf-log-label">{isThinking ? 'AI 思考中' : (event.type || 'event')}</div>
              <div className="cf-log-detail">{event.message || (isThinking ? '正在等待模型响应' : compact(event.data))}</div>
              {expanded && (
                <div className="cf-log-meta">
                  {(event.data as any)?.action && <code>{(event.data as any).action}</code>}
                  {(event.data as any)?.input_key && <code>in:{(event.data as any).input_key}</code>}
                  {(event.data as any)?.output && <code>out:{(event.data as any).output}</code>}
                  {isThinking && <code>thinking</code>}
                  {(event.data as any)?.decision_validation_errors && <code>decision_validation_errors</code>}
                </div>
              )}
            </div>
          </div>
        )
      })}
    </div>
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
  onRun,
  onSelectRun,
  onAnswerPendingInteraction,
  onRefresh,
}: {
  detail: FlowLabDetail
  runs: RunResult[]
  events: FlowEvent[]
  onRun: (inputs: Record<string, string>, probeRange?: TestProbeRange, mode?: 'full' | 'probe') => Promise<void> | void
  onSelectRun?: (runId: string) => Promise<void> | void
  onAnswerPendingInteraction?: (runId: string, values: Record<string, any>, options?: Record<string, any>) => Promise<void> | void
  onRefresh: () => void
}) {
  const latestRun = runs[0]
  const [selectedNode, setSelectedNode] = useState<FlowNode | null>(null)
  const [runScope] = useState<RunScope>('full')
  const [showInputForm, setShowInputForm] = useState(false)
  const [pendingModalOpen, setPendingModalOpen] = useState(false)
  const [isRunning, setIsRunning] = useState(false)
  const [logsOpen, setLogsOpen] = useState(true)
  const [logTab, setLogTab] = useState<'diag' | 'log'>('diag')
  const [autoScroll, setAutoScroll] = useState(true)
  const [logPreviewOpen, setLogPreviewOpen] = useState(false)
  const [logHeight, setLogHeight] = useState(150)
  const [logMaxHeight, setLogMaxHeight] = useState(180)
  const [showUiPreview, setShowUiPreview] = useState(false)
  const [showArtifactsPreview, setShowArtifactsPreview] = useState(false)
  const [resultModalOpen, setResultModalOpen] = useState(false)
  const [lockedPendingKey, setLockedPendingKey] = useState('')
  const [dismissedStatusKey, setDismissedStatusKey] = useState('')
  const [recoveryBusy, setRecoveryBusy] = useState<RecoveryAction | ''>('')
  const logBodyRef = useRef<HTMLDivElement | null>(null)
  const logDragRef = useRef<{ startY: number; startHeight: number } | null>(null)
  const probePanelRef = useRef<HTMLElement | null>(null)
  const autoOpenedPendingRef = useRef('')
  const defaultNodeId = detail.graph.nodes[0]?.id || ''
  const [startNodeId, setStartNodeId] = useState(defaultNodeId)
  const [endNodeId, setEndNodeId] = useState(defaultNodeId)

  const cartridgeInputs = detail.cartridge.inputs || []
  const nodeById = useMemo(() => new Map(detail.graph.nodes.map((node) => [node.id, node])), [detail.graph.nodes])
  const runArtifacts = useMemo(() => collectRunArtifacts(latestRun), [latestRun])
  const latestArtifactBatch = useMemo(() => collectLatestArtifactBatch(events), [events])
  const nodeRunStates = useMemo(() => buildNodeRunStates(detail.graph, events), [detail.graph, events])
  const diagnostics = useMemo(() => buildDiagnostics(events, latestRun), [events, latestRun])
  const selectedState = selectedNode ? nodeRunStates.get(selectedNode.id) : null
  const selectedArtifacts = selectedNode
    ? runArtifacts.filter((artifact) => artifact?.source?.node_id === selectedNode.id)
    : []
  const rawPendingInteraction = latestRun?.status === 'paused_waiting_user' && latestRun.pending_interaction ? latestRun.pending_interaction : null
  const rawPendingId = String(rawPendingInteraction?.interaction_id || rawPendingInteraction?.node_id || '')
  const rawPendingKey = rawPendingInteraction
    ? `${rawPendingId}:${latestRun?.updated_at || ''}:${events.length}`
    : ''
  const pendingInteraction = rawPendingInteraction && rawPendingKey !== lockedPendingKey ? rawPendingInteraction : null
  const pendingNode = useMemo(() => {
    for (const [nodeId, state] of nodeRunStates.entries()) {
      if (state.status === 'paused' && state.pendingInteraction) return nodeById.get(nodeId) || null
    }
    const pausedEvent = [...events].reverse().find((event) => event.type === 'lab_node_paused' && event.state)
    return pausedEvent?.state ? nodeById.get(pausedEvent.state) || null : null
  }, [events, nodeById, nodeRunStates])
  const pendingArtifactNodeId = pendingNode?.id || ''
  const pendingArtifacts = useMemo(() => {
    if (latestArtifactBatch.length) return latestArtifactBatch
    if (!runArtifacts.length) return []
    if (!pendingArtifactNodeId) return runArtifacts
    const scoped = runArtifacts.filter((artifact) => artifact?.source?.node_id === pendingArtifactNodeId)
    return scoped.length > 0 ? scoped : runArtifacts
  }, [latestArtifactBatch, pendingArtifactNodeId, runArtifacts])
  const pendingArtifactsLabel = latestArtifactBatch.length
    ? '当前最新草稿'
    : pendingArtifactNodeId && runArtifacts.some((artifact) => artifact?.source?.node_id === pendingArtifactNodeId)
      ? getNodeTitle(pendingNode)
      : '本次运行'
  const probePayload = useMemo(() => getProbePayload(detail.graph, startNodeId, endNodeId), [detail.graph, startNodeId, endNodeId])
  const runCompleted = latestRun?.status === 'completed' && !isRunning
  const runFailed = ['failed', 'interrupted'].includes(latestRun?.status || '') && !isRunning
  const recoveryHints = latestRun?.error?.recovery_actions || []
  const runRecoverable = latestRun?.status === 'interrupted' || latestRun?.error?.recoverable !== false
  const canRetryCurrentNode = latestRun?.status === 'interrupted'
    || latestRun?.error?.retryable === true
    || recoveryHints.some((action) => ['retry_node', 'retry_source_node', 'rebuild_artifact'].includes(action))
  const canViewDlcResult = runCompleted && Boolean(detail.cartridge.portable_dlc)
  const latestPausedEvent = [...events].reverse().find((event) => event.type === 'lab_node_paused') as any
  const latestPausedEventId = String(latestPausedEvent?.event_id || '')
  const statusBannerKey = pendingInteraction
    ? `pending:${latestRun?.run_id || ''}:${rawPendingId}:${latestPausedEventId || latestRun?.updated_at || ''}`
    : runCompleted
      ? `completed:${latestRun?.run_id || ''}:${latestRun?.updated_at || ''}`
      : runFailed
        ? `${latestRun?.status || 'failed'}:${latestRun?.run_id || ''}:${latestRun?.updated_at || ''}`
      : ''
  const showStatusBanner = Boolean(statusBannerKey && statusBannerKey !== dismissedStatusKey)
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
    setShowArtifactsPreview(false)
    setResultModalOpen(false)
  }, [latestRun?.run_id])

  useEffect(() => {
    if (latestRun?.status !== 'completed') return
    setShowUiPreview(false)
    setShowArtifactsPreview(false)
    setPendingModalOpen(false)
    setSelectedNode(null)
  }, [latestRun?.status, latestRun?.updated_at])

  useEffect(() => {
    if (!runArtifacts.length) setShowArtifactsPreview(false)
  }, [runArtifacts.length])

  useEffect(() => {
    if (!autoScroll || !logsOpen || !logBodyRef.current) return
    logBodyRef.current.scrollTo({ top: logBodyRef.current.scrollHeight, behavior: 'smooth' })
  }, [autoScroll, events, logsOpen, logTab])

  useEffect(() => {
    if (!pendingInteraction) setPendingModalOpen(false)
  }, [pendingInteraction])

  useEffect(() => {
    const pendingKey = latestRun?.run_id && rawPendingId ? `${latestRun.run_id}:${rawPendingId}` : ''
    if (!pendingInteraction || !pendingKey || autoOpenedPendingRef.current === pendingKey) return
    autoOpenedPendingRef.current = pendingKey
    if (pendingNode) setSelectedNode(pendingNode)
    setPendingModalOpen(true)
  }, [latestRun?.run_id, pendingInteraction, pendingNode, rawPendingId])

  useEffect(() => {
    if (!rawPendingInteraction) setLockedPendingKey('')
    else if (rawPendingKey && rawPendingKey !== lockedPendingKey) setLockedPendingKey('')
  }, [lockedPendingKey, rawPendingInteraction, rawPendingKey])

  useEffect(() => {
    const updateLogLimit = () => {
      const viewportHeight = window.visualViewport?.height || window.innerHeight
      const probeBottom = probePanelRef.current?.getBoundingClientRect().bottom
      const availableBelowProbe = probeBottom ? viewportHeight - probeBottom + 10 : viewportHeight * 0.34
      const nextMax = Math.round(Math.max(112, Math.min(viewportHeight * 0.5, availableBelowProbe)))
      setLogMaxHeight(nextMax)
      setLogHeight((current) => Math.min(Math.max(88, current), nextMax))
    }
    updateLogLimit()
    const frame = window.requestAnimationFrame(updateLogLimit)
    window.addEventListener('resize', updateLogLimit)
    window.visualViewport?.addEventListener('resize', updateLogLimit)
    return () => {
      window.cancelAnimationFrame(frame)
      window.removeEventListener('resize', updateLogLimit)
      window.visualViewport?.removeEventListener('resize', updateLogLimit)
    }
  }, [runScope])

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
      const nextHeight = Math.max(88, Math.min(logMaxHeight, drag.startHeight + drag.startY - moveEvent.clientY))
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

  const exportDiagnostics = async () => {
    if (!latestRun) return
    try {
      const checkpointResult = latestRun.run_id
        ? await fetchCartridgeRunCheckpoints(latestRun.run_id).catch(() => ({ items: [] as any[] }))
        : { items: [] as any[] }
      const bundle = redactDiagnosticValue({
        schema: 'cartridgeflow.diagnostic_bundle.v1',
        exported_at: new Date().toISOString(),
        cartridge: { id: detail.cartridge.id, version: detail.cartridge.version },
        run: latestRun,
        diagnostics,
        events,
        checkpoints: checkpointResult.items || [],
      })
      const blob = new Blob([JSON.stringify(bundle, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `diagnostic-${latestRun.run_id || Date.now()}.json`
      link.click()
      URL.revokeObjectURL(url)
      showToast({ title: '诊断包已导出', type: 'success' })
    } catch (error: any) {
      showToast({ title: '导出诊断包失败', description: error?.message || String(error), type: 'error' })
    }
  }

  const runWithInputs = async (inputs: Record<string, string>) => {
    setShowInputForm(false)
    setShowUiPreview(false)
    setShowArtifactsPreview(false)
    setSelectedNode(null)
    setDismissedStatusKey('')
    setLogsOpen(true)
    setLogTab('log')
    setIsRunning(true)
    try {
      if (runScope === 'probe') {
        await onRun(inputs, probePayload || undefined, 'probe')
      } else {
        await onRun(inputs, undefined, 'full')
      }
    } finally {
      setIsRunning(false)
    }
  }

  const answerPending = (values: Record<string, any>, options?: Record<string, any>) => {
    if (!latestRun?.run_id || !onAnswerPendingInteraction) return
    if (rawPendingKey) setLockedPendingKey(rawPendingKey)
    setIsRunning(true)
    setShowUiPreview(false)
    setShowArtifactsPreview(false)
    setDismissedStatusKey('')
    setLogsOpen(true)
    setLogTab('log')
    setPendingModalOpen(false)
    const releaseTimer = window.setTimeout(() => {
      setIsRunning(false)
    }, 900)
    void Promise.resolve(onAnswerPendingInteraction(latestRun.run_id, values, options))
      .catch(() => {
        setLockedPendingKey('')
      })
      .finally(() => {
        window.clearTimeout(releaseTimer)
        setIsRunning(false)
        void onRefresh()
      })
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

  const recoverRun = async (action: RecoveryAction, targetNode?: string) => {
    if (!latestRun?.run_id || recoveryBusy) return
    let confirmSideEffect = false
    setRecoveryBusy(action)
    try {
      for (;;) {
        try {
          await controlCartridgeRun(latestRun.run_id, action, {
            ...(targetNode ? { target_node: targetNode } : {}),
            confirm_side_effect: confirmSideEffect,
            feedback: { source: 'test_bench', selected_node: targetNode || '' },
          })
          break
        } catch (error) {
          const replayConfirmation = error instanceof ApiError && error.envelope?.code === 'REPLAY_CONFIRMATION_REQUIRED'
          if (!replayConfirmation || confirmSideEffect) throw error
          const confirmed = window.confirm('恢复路径可能再次执行外部写入或其他副作用。确认仍要继续吗？')
          if (!confirmed) return
          confirmSideEffect = true
        }
      }
      showToast({
        title: action === 'restart_run' ? '已创建新的运行' : '恢复操作已完成',
        description: action === 'rollback_to_node' && targetNode ? `已从 ${getNodeTitle(nodeById.get(targetNode)) || targetNode} 重新执行` : undefined,
        type: 'success',
      })
      await Promise.resolve(onRefresh())
    } catch (error: any) {
      showToast({ title: '恢复运行失败', description: error?.message || String(error), type: 'error' })
    } finally {
      setRecoveryBusy('')
    }
  }

  return (
    <div className="cf-tb">
      <div className="cf-tb-top">
        <aside className="cf-tb-op cf-run-history-panel">
          <div className="cf-run-history-head">
            <div><strong>运行历史</strong><span>{runs.length} 条记录</span></div>
            <button type="button" onClick={onRefresh}>刷新</button>
          </div>
          <div className="cf-run-history-list">
            {runs.length ? runs.map((run) => (
              <button
                type="button"
                key={run.run_id}
                className={run.run_id === latestRun?.run_id ? 'active' : ''}
                onClick={() => void onSelectRun?.(run.run_id)}
              >
                <span className="cf-run-history-summary">
                  <i className={run.status} aria-hidden="true" />
                  <b>{({ completed: '已完成', failed: '失败', running: '运行中', paused: '已暂停', paused_waiting_user: '等待交互', cancelled: '已停止', interrupted: '已中断' } as Record<string, string>)[run.status] || run.status}</b>
                  <time>{String(run.updated_at || run.created_at || '').replace('T', ' ').slice(5, 16) || '时间未知'}</time>
                </span>
                <code>{run.run_id}</code>
                <small>{run.current_state || '尚未进入节点'}</small>
              </button>
            )) : <div className="cf-run-history-empty">还没有运行记录。</div>}
          </div>
        </aside>

        <div className={`cf-tb-graph ${showStatusBanner ? 'has-status-banner' : ''}`}>
          {pendingInteraction && showStatusBanner && (
            <div className="cf-run-status-banner waiting" role="status">
              <span className="cf-run-status-mark">待确认</span>
              <span className="cf-run-status-copy">
                <strong>流程正在等待用户交互</strong>
                <span>{pendingNode ? `${getNodeTitle(pendingNode)} 已准备好，请打开并确认后继续。` : '当前节点需要你的确认后才能继续。'}</span>
              </span>
              <span className="cf-run-status-actions">
                <button type="button" onClick={openPendingInteraction}>打开交互</button>
                <button type="button" className="cf-run-status-close" title="关闭提示" aria-label="关闭提示" onClick={() => setDismissedStatusKey(statusBannerKey)}>×</button>
              </span>
            </div>
          )}
          {runCompleted && !pendingInteraction && showStatusBanner && (
            <div className="cf-run-status-banner completed" role="status">
              <span className="cf-run-status-mark">已完成</span>
              <span className="cf-run-status-copy">
                <strong>流程运行完成</strong>
                <span>{runArtifacts.length > 0 ? `本次运行已生成 ${runArtifacts.length} 个交付产物。` : '本次流程已经完整执行结束。'}</span>
              </span>
              <span className="cf-run-status-actions">
                {canViewDlcResult && (
                  <button type="button" onClick={() => setResultModalOpen(true)}>查看扩展结果</button>
                )}
                {runArtifacts.length > 0 && (
                  <button
                    type="button"
                    onClick={() => {
                      setShowUiPreview(false)
                      setShowArtifactsPreview(true)
                    }}
                  >
                    查看产物
                  </button>
                )}
                <button type="button" className="cf-run-status-close" title="关闭提示" aria-label="关闭提示" onClick={() => setDismissedStatusKey(statusBannerKey)}>×</button>
              </span>
            </div>
          )}
          {runFailed && !pendingInteraction && showStatusBanner && (
            <div className="cf-run-status-banner failed" role="alert">
              <span className="cf-run-status-mark">{latestRun?.status === 'interrupted' ? '运行中断' : '执行失败'}</span>
              <span className="cf-run-status-copy">
                <strong>{latestRun?.error?.message || (latestRun?.status === 'interrupted' ? '底座进程中断了这次运行，可以从检查点恢复。' : '流程没有完成。')}</strong>
                <span>{latestRun?.error?.code ? `错误码 ${latestRun.error.code}，错误 ID ${latestRun.error.error_id || '未记录'}。` : '可查看诊断，或使用持久检查点恢复运行。'}</span>
              </span>
              <span className="cf-run-status-actions">
                <button type="button" onClick={() => { setLogsOpen(true); setLogTab('diag') }}>查看诊断</button>
                <button type="button" disabled={Boolean(recoveryBusy) || !canRetryCurrentNode} title={canRetryCurrentNode ? '从失败节点的前置检查点重试' : '当前错误不允许直接重试'} onClick={() => void recoverRun('retry_current_node')}>
                  {recoveryBusy === 'retry_current_node' ? '正在重试...' : '重试当前节点'}
                </button>
                {runRecoverable && (
                  <details className="cf-recovery-menu">
                    <summary>更多恢复</summary>
                    <div>
                      <button type="button" disabled={Boolean(recoveryBusy)} onClick={() => void recoverRun('resume_checkpoint')}>从检查点继续</button>
                      <button type="button" disabled={Boolean(recoveryBusy || !selectedNode)} title={selectedNode ? `回滚到 ${getNodeTitle(selectedNode)}` : '先在流程图中选择一个节点'} onClick={() => selectedNode && void recoverRun('rollback_to_node', selectedNode.id)}>回滚到所选节点</button>
                      <button type="button" disabled={Boolean(recoveryBusy)} onClick={() => void recoverRun('restart_run')}>使用原始输入重新运行</button>
                    </div>
                  </details>
                )}
                <button type="button" onClick={() => void exportDiagnostics()}>导出诊断包</button>
                <button type="button" className="cf-run-status-close" title="关闭提示" aria-label="关闭提示" onClick={() => setDismissedStatusKey(statusBannerKey)}>×</button>
              </span>
            </div>
          )}
          <FlowGraphView
            graph={detail.graph}
            selectedNode={selectedNode}
            focusNodeId={null}
            onSelectNode={selectRunNode}
            readOnlyGraph
            nodeRunStates={nodeRunStates}
            runEvents={events}
          />
          {selectedNode && selectedState && (
            <NodeInspector node={selectedNode} state={selectedState} artifacts={selectedArtifacts} nodeById={nodeById} onClose={() => setSelectedNode(null)} />
          )}
          <div className="cf-graph-actions">
            {latestUiHtml && !showUiPreview && (
              <button
                type="button"
                className="cf-graph-action"
                onClick={() => {
                  setShowArtifactsPreview(false)
                  setShowUiPreview(true)
                }}
              >
                查看 UI
              </button>
            )}
            {runArtifacts.length > 0 && !showArtifactsPreview && (
              <button
                type="button"
                className="cf-graph-action"
                onClick={() => {
                  setShowUiPreview(false)
                  setShowArtifactsPreview(true)
                }}
              >
                查看产物
              </button>
            )}
            {canViewDlcResult && (
              <button type="button" className="cf-graph-action" onClick={() => setResultModalOpen(true)}>查看扩展结果</button>
            )}
          </div>
          {latestUiHtml && showUiPreview && (
            <div className="cf-welcome-preview">
              <div className="cf-welcome-preview-head">
                <strong>UI 预览</strong>
                <button type="button" onClick={() => setShowUiPreview(false)}>x</button>
              </div>
              <iframe className="cf-welcome-frame" title="latest-ui-preview" srcDoc={passiveHtmlDocument(latestUiHtml)} sandbox="" />
            </div>
          )}
          {latestRun && showArtifactsPreview && runArtifacts.length > 0 && (
            <div className="cf-artifacts-preview-shell">
              <div className="cf-artifacts-preview-shell-head">
                <strong>本次运行交付</strong>
                <button type="button" onClick={() => setShowArtifactsPreview(false)}>x</button>
              </div>
              <DeliveryArtifactsPanel run={latestRun} artifacts={runArtifacts} nodeById={nodeById} />
            </div>
          )}
        </div>
      </div>

      <div
        className={`cf-tb-bottom ${logsOpen ? 'open' : 'closed'}`}
        style={logsOpen ? ({ '--cf-log-height': `${logHeight}px`, '--cf-log-max-height': `${logMaxHeight}px` } as CSSProperties) : undefined}
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
          <div className={`cf-pending-modal ${pendingInteraction.ui_extension === 'portable_dlc' ? 'cf-pending-modal-dlc' : ''}`} onClick={(event) => event.stopPropagation()}>
            <div className="cf-pending-modal-head">
              <strong>{pendingNode ? `与 ${getNodeTitle(pendingNode)} 交互` : '等待用户交互'}</strong>
              <button type="button" onClick={() => setPendingModalOpen(false)}>x</button>
            </div>
            {pendingInteraction.ui_extension === 'portable_dlc' && detail.cartridge.portable_dlc && latestRun ? (
              <DlcSandboxFrame cartridgeId={detail.cartridge.id} runId={latestRun.run_id} onSubmit={answerPending} />
            ) : (
              <PendingInteractionForm
                pending={pendingInteraction}
                disabled={isRunning || !onAnswerPendingInteraction}
                onSubmit={answerPending}
                artifacts={pendingArtifacts}
                nodeById={nodeById}
                artifactScopeLabel={pendingArtifactsLabel}
              />
            )}
          </div>
        </div>
      )}

      {resultModalOpen && canViewDlcResult && latestRun && (
        <div className="cf-pending-modal-backdrop" onClick={() => setResultModalOpen(false)}>
          <div className="cf-pending-modal cf-pending-modal-dlc" onClick={(event) => event.stopPropagation()}>
            <div className="cf-pending-modal-head">
              <strong>本次扩展交付</strong>
              <button type="button" onClick={() => setResultModalOpen(false)}>x</button>
            </div>
            <DlcSandboxFrame cartridgeId={detail.cartridge.id} runId={latestRun.run_id} mode="result" />
          </div>
        </div>
      )}

      {showInputForm && (
        <RunInputDialog
          inputs={cartridgeInputs as any[]}
          disabled={isRunning}
          onSubmit={runWithInputs}
          onCancel={() => setShowInputForm(false)}
        />
      )}
    </div>
  )
}
