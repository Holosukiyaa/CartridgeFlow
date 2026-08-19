import { lazy, Suspense, type ReactNode, type RefObject, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  ArrowLeft,
  Bot,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Cloud,
  FileText,
  Globe2,
  History,
  Info,
  Loader2,
  Maximize2,
  MousePointer2,
  Package,
  PackageCheck,
  Paperclip,
  Pause,
  PencilRuler,
  Play,
  Plus,
  Puzzle,
  RefreshCw,
  RotateCcw,
  ScanLine,
  Send,
  Search,
  Settings,
  Sparkles,
  Square,
  Sun,
  Target,
  Wrench,
  X,
} from 'lucide-react'
import {
  ApiError,
  acceptCreatorProposal,
  acceptCreatorRecompose,
  composeCreatorRecipe,
  connectCreatorAi,
  confirmCreatorNode,
  deleteCreatorProject,
  deliverCreatorProject,
  discoverCreatorPossibilities,
  discoverCreatorSources,
  fetchCreatorAiStatus,
  fetchDesktopRunnerStatus,
  fetchCreatorProject,
  fetchCreatorSession,
  fetchCreatorWorkspace,
  packageCreatorProject,
  inspectCreatorSource,
  listCreatorProjects,
  previewCreatorProposal,
  proposeCreatorNodeValues,
  previewCreatorRecompose,
  renameCreatorProject,
  refineCreatorNodeWithAi,
  rejectCreatorCapability,
  rejectCreatorProposal,
  resolveCreatorCapabilities,
  saveCreatorWorkspace,
  setCreatorExperience,
  type CreatorPackage,
  type CreatorRunnerDelivery,
  type CreatorClarification,
  type CreatorPossibility,
  type CreatorProjection,
  type CreatorProposal,
  type CreatorRecipePreview,
  type CreatorRecipeNode,
  type CreatorSourceCandidate,
  type DesktopRunnerStatus,
} from '../../api.ts'
import { showToast } from '../../toast.tsx'
import { Button, Dialog, Field, IconButton, SemanticWorkbench, useAppTheme, type SemanticPanelId } from '../../ui/index.ts'
import { IntentCanvas, type CreatorCanvasTool, type CreatorRelationKind } from './IntentCanvas.tsx'

const ModelConnectionDialog = lazy(() => import('./ModelConnectionDialog.tsx').then((module) => ({ default: module.ModelConnectionDialog })))
const ResourceManagerDialog = lazy(() => import('./ResourceManagerDialog.tsx').then((module) => ({ default: module.ResourceManagerDialog })))
const ThemeDialog = lazy(() => import('./ThemeDialog.tsx').then((module) => ({ default: module.ThemeDialog })))

const creatorId = () => `creator.${crypto.randomUUID()}`

type StewardMessage = {
  id: string
  role: 'assistant' | 'user'
  text: string
  clarification?: CreatorClarification | null
}

type WorkspacePane = 'collaboration' | 'outline' | 'canvas'

type GuidanceAction = 'connect-ai' | 'focus-composer' | 'show-directions' | 'open-node' | 'build-package' | 'deliver-runner' | 'open-runner' | 'download-package'

type CreatorGuidance = {
  stage: 'connect-ai' | 'describe' | 'clarify' | 'choose' | 'complete-step' | 'prepare-run' | 'run-ready'
  step: number
  title: string
  detail: string
  action: GuidanceAction
  actionLabel: string
  nodeId?: string
}

type CreatorWorkspaceSnapshot = {
  version: 1
  goal: string
  messages: StewardMessage[]
  clarification: CreatorClarification | null
  possibilities: CreatorPossibility[]
  selectedId: string
  middleView: 'outline' | 'detail'
  workspacePane: WorkspacePane
  packageResult: CreatorPackage | null
  packageRevision: number | null
}

const CREATOR_WORKSPACE_KEY = (projectId: string) => `cartridgeflow.creator-workspace.v1.${projectId}`

function isCreatorClarification(value: unknown): value is CreatorClarification {
  if (!value || typeof value !== 'object') return false
  const item = value as Partial<CreatorClarification>
  return typeof item.question === 'string' && typeof item.why_it_matters === 'string' && Array.isArray(item.suggested_answers) && item.suggested_answers.every((answer) => typeof answer === 'string')
}

function isCreatorPossibility(value: unknown): value is CreatorPossibility {
  if (!value || typeof value !== 'object') return false
  const item = value as Partial<CreatorPossibility>
  return typeof item.id === 'string' && typeof item.title === 'string' && typeof item.outcome === 'string' && Boolean(item.recipe && typeof item.recipe.intent === 'string')
}

function normalizeCreatorWorkspace(value: unknown): CreatorWorkspaceSnapshot | null {
  try {
    const snapshot = value as Partial<CreatorWorkspaceSnapshot> | null
    if (!snapshot || snapshot.version !== 1 || !Array.isArray(snapshot.messages) || !Array.isArray(snapshot.possibilities)) return null
    const messages = snapshot.messages.filter((item): item is StewardMessage =>
      Boolean(item && typeof item.id === 'string' && (item.role === 'assistant' || item.role === 'user') && typeof item.text === 'string'),
    ).slice(-80)
    return {
      version: 1,
      goal: typeof snapshot.goal === 'string' ? snapshot.goal : '',
      messages: messages.length ? messages : [STEWARD_WELCOME],
      clarification: isCreatorClarification(snapshot.clarification) ? snapshot.clarification : null,
      possibilities: snapshot.possibilities.filter(isCreatorPossibility).slice(0, 6),
      selectedId: typeof snapshot.selectedId === 'string' ? snapshot.selectedId : '',
      middleView: snapshot.middleView === 'detail' ? 'detail' : 'outline',
      workspacePane: ['collaboration', 'outline', 'canvas'].includes(String(snapshot.workspacePane)) ? snapshot.workspacePane as WorkspacePane : 'collaboration',
      packageResult: snapshot.packageResult || null,
      packageRevision: typeof snapshot.packageRevision === 'number' ? snapshot.packageRevision : null,
    }
  } catch { return null }
}

function readCreatorWorkspace(projectId: string): CreatorWorkspaceSnapshot | null {
  try { return normalizeCreatorWorkspace(JSON.parse(localStorage.getItem(CREATOR_WORKSPACE_KEY(projectId)) || 'null')) }
  catch { return null }
}

function capabilityWorkshopUrl(creator: CreatorProjection, node: CreatorRecipeNode) {
  const query = new URLSearchParams({
    goal: node.resolution?.needed_capability || node.description,
    projectId: creator.project_id,
    nodeId: node.id,
    nodeLabel: node.label,
  })
  return `/capabilities?${query.toString()}`
}

function creatorGuidance(
  creator: CreatorProjection | null,
  clarification: CreatorClarification | null,
  possibilities: CreatorPossibility[],
  packageResult: CreatorPackage | null,
  aiConnected: boolean | null,
  runnerStatus: DesktopRunnerStatus | null,
  runnerDelivery: CreatorRunnerDelivery | null,
): CreatorGuidance {
  if (aiConnected === false) return { stage: 'connect-ai', step: 1, title: '先连接共创 AI', detail: '连接会先经过真实可达性和模型响应测试，通过后继续当前步骤。', action: 'connect-ai', actionLabel: '连接 AI' }
  if (!creator) {
    if (clarification) return { stage: 'clarify', step: 2, title: '回答这个关键问题', detail: clarification.question, action: 'focus-composer', actionLabel: '继续回答' }
    if (possibilities.length) return { stage: 'choose', step: 3, title: '选择最接近的方向', detail: `AI 给出了 ${possibilities.length} 个可比较方向，选定后再生成方案。`, action: 'show-directions', actionLabel: '查看方向' }
    return { stage: 'describe', step: 2, title: '说清想得到什么', detail: '用结果和使用场景描述，不需要先考虑模型、工具或流程。', action: 'focus-composer', actionLabel: '描述目标' }
  }
  const nextNode = creator.trusted_recipe.nodes.find((node) => nodeReviewState(creator, node) !== 'confirmed')
  if (nextNode) {
    const state = nodeReviewState(creator, nextNode)
    return {
      stage: 'complete-step',
      step: 4,
      title: state === 'unresolved' ? `补齐「${nextNode.label}」` : `确认「${nextNode.label}」`,
      detail: state === 'unresolved'
        ? '原方案会保留。完成内部做法并发布后，这一步会自动回填。'
        : '检查业务参数、资料来源和结果界面；确认后会自动前往下一步。',
      action: 'open-node',
      actionLabel: state === 'unresolved' ? '开始补齐' : '检查并确认',
      nodeId: nextNode.id,
    }
  }
  if (!packageResult) return { stage: 'prepare-run', step: 5, title: '方案已完成审核', detail: '生成经过签名验证的试运行包，再交给 Desktop Runner 使用真实输入运行。', action: 'build-package', actionLabel: '准备试运行' }
  if (runnerDelivery?.status === 'trust_required') return { stage: 'run-ready', step: 5, title: '请确认本地发布者', detail: '签名本身有效。请在 Desktop Runner 中核对发布者与密钥指纹，再决定是否信任并安装。', action: 'open-runner', actionLabel: '前往确认' }
  if (runnerDelivery) return { stage: 'run-ready', step: 5, title: '已送入 Desktop Runner', detail: '卡带已通过 Runner 的独立验签和安装，现在可以输入真实样例运行。', action: 'open-runner', actionLabel: '开始实际试运行' }
  if (runnerStatus?.available) return { stage: 'run-ready', step: 5, title: 'Desktop Runner 已就绪', detail: '把当前签名包直接送入 Runner，安装通过后即可输入真实样例。', action: 'deliver-runner', actionLabel: '发送到 Runner' }
  return { stage: 'run-ready', step: 5, title: '试运行包已就绪', detail: 'Runner 尚未连通。先下载签名包，启动 Desktop Runner 后再启用。', action: 'download-package', actionLabel: '下载试运行包' }
}

const STEWARD_WELCOME: StewardMessage = {
  id: 'welcome',
  role: 'assistant',
  text: '先说你现在想得到的结果。我会先追问一个关键问题或给出少量方向；你选定方向后，我们再把它变成可审核的大纲。',
}

function friendlyError(error: unknown, action: 'discover' | 'compose' | 'node' | 'package') {
  const code = error instanceof ApiError ? error.code : ''
  if (code.includes('MODEL_UNBOUND')) return 'AI 共创服务尚未准备好。'
  if (code.includes('TIMEOUT')) return 'AI 响应超时，请稍后重试。'
  if (action === 'discover' && code.includes('OUTPUT_INVALID')) return 'AI 已返回内容，但自动修正后仍未通过格式检查。请重试或切换模型。'
  if (code.includes('REVISION')) return '草稿已经发生变化，请重新操作。'
  if (action === 'package' && (code.includes('BLOCKED') || code.includes('FREEZE'))) return '还有节点没有完成审核，暂时不能打包。'
  if (action === 'package') return '打包校验没有通过，请检查所有节点后重试。'
  if (action === 'discover') return '暂时无法生成新方向，请稍后重试。'
  if (action === 'node') return '这次节点调整没有完成，请重试。'
  return '这次整体编排没有完成，请重试。'
}

function FieldEditor({ node, values, onChange, disabled }: {
  node: CreatorRecipeNode
  values: Record<string, unknown>
  onChange: (values: Record<string, unknown>) => void
  disabled: boolean
}) {
  return <div className="creator-fields">
    {node.editable_fields.map((field) => {
      const value = values[field.id] ?? field.default ?? ''
      if (field.value_type === 'boolean') {
        return <label className="creator-check-field" key={field.id}>
          <input type="checkbox" checked={Boolean(value)} disabled={disabled} onChange={(event) => onChange({ ...values, [field.id]: event.target.checked })} />
          <span>{field.label}</span>
        </label>
      }
      if (field.value_type === 'string_list') {
        return <label key={field.id}><span>{field.label}{field.required ? ' *' : ''}</span><textarea disabled={disabled} value={Array.isArray(value) ? value.join('\n') : ''} onChange={(event) => onChange({ ...values, [field.id]: event.currentTarget.value.split('\n').map((item) => item.trim()).filter(Boolean) })} /></label>
      }
      return <label key={field.id}><span>{field.label}{field.required ? ' *' : ''}</span><input disabled={disabled} type={field.value_type === 'number' ? 'number' : 'text'} value={String(value)} onChange={(event) => onChange({ ...values, [field.id]: field.value_type === 'number' ? Number(event.currentTarget.value) : event.currentTarget.value })} /></label>
    })}
  </div>
}

function ExperienceEditor({ creator, node, disabled, onChange, onBusy }: {
  creator: CreatorProjection
  node: CreatorRecipeNode
  disabled: boolean
  onChange: (creator: CreatorProjection) => void
  onBusy: (busy: boolean) => void
}) {
  const experience = node.experience
  const [drafts, setDrafts] = useState<Record<string, { componentId: string; fieldSources: Record<string, string> }>>(() =>
    Object.fromEntries((experience?.slots || []).map((slot) => [slot.id, {
      componentId: slot.selected_component_id,
      fieldSources: { ...slot.field_sources },
    }])),
  )
  if (!experience || experience.status !== 'available') return null

  const chooseComponent = (slotId: string, componentId: string) => {
    const slot = experience.slots.find((item) => item.id === slotId)
    const component = slot?.components.find((item) => item.id === componentId)
    const fieldSources: Record<string, string> = {}
    component?.fields.forEach((field) => {
      const current = drafts[slotId]?.fieldSources[field.id]
      const first = field.compatible_source_ids[0]
      if (current && field.compatible_source_ids.includes(current)) fieldSources[field.id] = current
      else if (first) fieldSources[field.id] = first
    })
    setDrafts((value) => ({ ...value, [slotId]: { componentId, fieldSources } }))
  }
  const save = async (slotId: string) => {
    const draft = drafts[slotId]
    if (!draft) return
    onBusy(true)
    try {
      const result = await setCreatorExperience(creator.session_id, node.id, {
        expected_revision: creator.revision,
        expected_experience_revision: creator.experience_revision || 0,
        slot_id: slotId,
        component_id: draft.componentId,
        field_sources: draft.fieldSources,
      })
      onChange(result.creator)
      showToast({ title: '呈现方式已保存', description: '打包后会在运行台按这个方式显示。', type: 'success' })
    } catch (error) {
      showToast({ title: '呈现方式没有保存', description: friendlyError(error, 'node'), type: 'error' })
    } finally { onBusy(false) }
  }

  return <section className="creator-experience">
    <header><Settings /><div><strong>运行时呈现</strong><span>选择用户在运行台看到的样子</span></div></header>
    {experience.slots.map((slot) => {
      const draft = drafts[slot.id] || { componentId: slot.selected_component_id, fieldSources: slot.field_sources }
      const component = slot.components.find((item) => item.id === draft.componentId)
      const complete = !!component && component.available && component.fields.every((field) => !field.required || !!draft.fieldSources[field.id])
      const dirty = draft.componentId !== slot.selected_component_id || JSON.stringify(draft.fieldSources) !== JSON.stringify(slot.field_sources)
      return <div className="creator-experience-slot" key={slot.id}>
        <div className="creator-experience-title"><strong>{slot.label}</strong><span>{slot.status === 'configured' && !dirty ? '已配置' : '待保存'}</span></div>
        <div className="creator-component-options" role="radiogroup" aria-label={`${slot.label}呈现方式`}>
          {slot.components.map((item) => <button
            type="button"
            role="radio"
            aria-checked={draft.componentId === item.id}
            className={draft.componentId === item.id ? 'is-selected' : ''}
            disabled={disabled || !item.available}
            key={item.id}
            onClick={() => chooseComponent(slot.id, item.id)}
          ><span><strong>{item.label}</strong><small>{item.description}</small></span>{draft.componentId === item.id && <Check />}</button>)}
        </div>
        {component && <>
          <div className="creator-component-preview">
            <iframe title={`${component.label}预览`} sandbox="" srcDoc={component.preview_html} />
          </div>
          {!!component.fields.length && <div className="creator-field-mapping">
            {component.fields.map((field) => <label key={field.id}><span>{field.label}</span><select
              value={draft.fieldSources[field.id] || ''}
              disabled={disabled}
              onChange={(event) => setDrafts((value) => ({ ...value, [slot.id]: {
                ...draft,
                fieldSources: { ...draft.fieldSources, [field.id]: event.currentTarget.value },
              } }))}
            ><option value="">选择数据</option>{slot.sources.filter((source) => field.compatible_source_ids.includes(source.id)).map((source) => <option key={source.id} value={source.id}>{source.label}</option>)}</select></label>)}
          </div>}
        </>}
        <button type="button" className="secondary-button creator-experience-save" disabled={disabled || !dirty || !complete} onClick={() => void save(slot.id)}><Check />保存呈现方式</button>
      </div>
    })}
  </section>
}

function proposalValue(value: unknown) {
  if (Array.isArray(value)) return value.join('、')
  if (typeof value === 'boolean') return value ? '开启' : '关闭'
  if (value == null || value === '') return '留空'
  return String(value)
}

function ProposalChanges({ node, proposal }: { node: CreatorRecipeNode; proposal: CreatorProposal }) {
  const fieldLabels = new Map(node.editable_fields.map((field) => [field.id, field.label]))
  const rows = proposal.changes.flatMap((change) => {
    if (change.operation === 'set_creator_binding' && change.value && typeof change.value === 'object' && !Array.isArray(change.value)) {
      return Object.entries(change.value).map(([key, value]) => ({ label: fieldLabels.get(key) || key, value: proposalValue(value) }))
    }
    if (change.operation === 'set_step_intent') return [{ label: '节点目标', value: proposalValue(change.value) }]
    return [{ label: '调整内容', value: proposalValue(change.value) }]
  })
  return <div className="creator-review-changes">
    {rows.map((row, index) => <div key={`${row.label}:${index}`}><strong>{row.label}</strong><span>{row.value}</span></div>)}
  </div>
}

function nodeReviewState(creator: CreatorProjection, node: CreatorRecipeNode) {
  if (node.resolution?.status === 'unresolved') return 'unresolved' as const
  return creator.frozen_steps.includes(node.id) ? 'confirmed' as const : 'review' as const
}

function ReviewStatus({ state, showSuggestion = false }: { state: 'confirmed' | 'review' | 'unresolved'; showSuggestion?: boolean }) {
  return <span className={`vip-review-status is-${state}`}>
    <span><i />{state === 'confirmed' ? '已确认' : state === 'review' ? '待审核' : '需要补齐'}</span>
    {showSuggestion && <small>1项建议待预览</small>}
  </span>
}

function CollaborationPanel({
  creator,
  goal,
  selectedNode,
  busy,
  composerError,
  stewardInput,
  stewardMessages,
  clarification,
  guidance,
  runnerUrl,
  threadRef,
  composerRef,
  onInput,
  onSubmit,
  onClarification,
  onGuidanceAction,
  onOpenDetail,
  onClose,
  directions,
}: {
  creator: CreatorProjection | null
  goal: string
  selectedNode: CreatorRecipeNode | null
  busy: boolean
  composerError: string
  stewardInput: string
  stewardMessages: StewardMessage[]
  clarification: CreatorClarification | null
  guidance: CreatorGuidance
  runnerUrl: string
  threadRef: RefObject<HTMLDivElement | null>
  composerRef: RefObject<HTMLTextAreaElement | null>
  onInput: (value: string) => void
  onSubmit: (value: string) => void
  onClarification: (value: string) => void
  onGuidanceAction: () => void
  onOpenDetail: () => void
  onClose: () => void
  directions?: ReactNode
}) {
  const confirmed = creator?.trusted_recipe.nodes.filter((node) => nodeReviewState(creator, node) === 'confirmed') || []
  const suggestion = selectedNode && creator?.pending_proposals.find((proposal) => proposal.changes.some((change) => change.target_id === selectedNode.id))
  const [auditExpanded, setAuditExpanded] = useState(false)
  const auditItems = [
    ...(creator?.history || []).map((item) => ({ id: item.id, label: `v${item.revision} ${item.summary}` })),
    ...confirmed.map((node) => ({ id: `confirmed:${node.id}`, label: `已确认节点：${node.label}` })),
  ]
  const visibleAuditItems = auditExpanded ? auditItems : auditItems.slice(-3)

  return <section className="vip-ai-panel" aria-label="AI 共创记录">
    <header className="vip-panel-title"><Sparkles /><strong>AI 管家</strong><IconButton label="折叠 AI 管家" variant="subtle" size="sm" onClick={onClose}><X /></IconButton></header>
    {(creator || goal) && <section className="vip-current-goal"><Target /><div><strong>当前目标</strong><p>{goal}</p></div></section>}
    <div className="vip-collaboration-thread" ref={threadRef}>
      <section className={`vip-next-action is-${guidance.stage}`} aria-label="当前下一步">
        <header><span>{creator ? '项目推进' : guidance.stage === 'connect-ai' ? '创作准备' : '目标与方向'}</span><small>当前任务</small></header>
        <strong>{guidance.title}</strong>
        <p>{guidance.detail}</p>
        <button type="button" disabled={busy} onClick={onGuidanceAction}>{['build-package', 'deliver-runner', 'download-package'].includes(guidance.action) ? <PackageCheck /> : guidance.action === 'open-node' || guidance.action === 'open-runner' ? <ChevronRight /> : <Sparkles />}{guidance.actionLabel}</button>
        {guidance.stage === 'run-ready' && <a href={runnerUrl} target="_blank" rel="noreferrer">在 Desktop Runner 中启用 <ChevronRight /></a>}
      </section>
      {stewardMessages.map((message) => <article className={`vip-live-record is-${message.role}`} key={message.id}>
        <span className={`vip-record-avatar is-${message.role === 'assistant' ? 'ai' : 'user'}`}>{message.role === 'assistant' ? 'AI' : '我'}</span>
        <div><p>{message.text}</p>{message.clarification && clarification?.question === message.clarification.question && <section className="creator-clarification"><small>{message.clarification.why_it_matters}</small><div>{message.clarification.suggested_answers.map((answer) => <button type="button" key={answer} disabled={busy} onClick={() => onClarification(answer)}>{answer}</button>)}</div></section>}</div>
      </article>)}
      {directions}
      {suggestion && selectedNode && <article className="vip-record-entry is-suggestion">
        <span className="vip-record-avatar is-ai">AI</span><strong>待审核建议</strong><em>未应用</em>
        <p>节点 {String(Math.max(1, (creator!.trusted_recipe.nodes.findIndex((node) => node.id === selectedNode.id) + 1))).padStart(2, '0')} {selectedNode.label}</p>
        <strong className="vip-suggestion-label">{suggestion.summary}</strong>
        <strong className="vip-suggestion-label">影响范围：<span>{suggestion.changes.length} 项变更</span></strong>
        <div className="vip-suggestion-actions"><button type="button" onClick={onOpenDetail}>查看并审核</button></div>
      </article>}
      {!!auditItems.length && <section className="vip-recent-audit">
        <header><strong>审核记录</strong><button type="button" onClick={() => setAuditExpanded((value) => !value)}>{auditExpanded ? '收起' : '查看全部'} <ChevronRight /></button></header>
        <ul>{visibleAuditItems.map((item) => <li key={item.id}>{item.label}</li>)}</ul>
      </section>}
      {busy && <div className="creator-steward-loading"><i /><i /><i /><span>正在更新大纲</span></div>}
      {composerError && <div className="creator-steward-error" role="alert"><strong>这次没有完成</strong><span>{composerError}</span></div>}
    </div>
    <form className="vip-collaboration-composer" onSubmit={(event) => { event.preventDefault(); onSubmit(stewardInput) }}>
      <textarea ref={composerRef} value={stewardInput} disabled={busy} onChange={(event) => onInput(event.currentTarget.value)} placeholder={creator ? '继续提问或补充说明需求...' : '描述你想得到的结果和使用场景...'} />
      <div>{creator && <button className="vip-attachment" type="button" disabled={!selectedNode} title={selectedNode ? '在节点详情中添加资料来源' : '先选择一个节点'} onClick={onOpenDetail}><Paperclip /></button>}<span className="vip-language"><Globe2 />简体中文</span><button className="vip-send" type="submit" disabled={busy || stewardInput.trim().length < 3} title="发送" aria-label="发送">{busy ? <Loader2 className="spinning" /> : <Send />}</button></div>
    </form>
  </section>
}

function DirectionExplorer({
  goal,
  clarification,
  possibilities,
  busy,
  onChoose,
}: {
  goal: string
  clarification: CreatorClarification | null
  possibilities: CreatorPossibility[]
  busy: boolean
  onChoose: (possibility: CreatorPossibility) => void
}) {
  return <div className="vip-discovery-view" aria-label="AI 方向建议">
    <header>
      <small>方向探索</small>
      <strong>{clarification ? '还需要确认一件事' : possibilities.length ? '选择一个方向生成方案' : '从真实目标开始'}</strong>
      <p>{clarification
        ? '请在左侧回答 AI 的问题。信息充分后才会生成候选方向。'
        : possibilities.length
          ? '这些方向来自已连接的 AI，选择后才会查询可信能力并生成可审核大纲。'
          : goal.trim()
            ? '发送左侧描述后，AI 会先判断是否需要澄清。'
            : '在左侧描述想得到的结果，不需要先考虑模型、工具或流程。'}</p>
    </header>
    {possibilities.length ? <div className="vip-direction-list">{possibilities.map((item, index) => <article key={item.id}>
      <span>方向 {String(index + 1).padStart(2, '0')}</span>
      <h3>{item.title}</h3>
      <p>{item.outcome}</p>
      <small>{item.why_it_fits}</small>
      <button type="button" disabled={busy} onClick={() => onChoose(item)}><CheckCircle2 />用这个方向生成方案</button>
    </article>)}</div> : <div className="vip-discovery-empty"><Sparkles /><strong>{busy ? 'AI 正在理解目标' : clarification ? clarification.question : '等待你的目标描述'}</strong><span>{busy ? '只使用已连接的真实模型，不会生成占位方向。' : clarification?.why_it_matters || '候选方向出现前不会读取能力目录。'}</span></div>}
  </div>
}

function NodeEditor({ creator, node, busy, onCreatorChange, onNavigate, onReturnOutline, onModelRequired }: {
  creator: CreatorProjection
  node: CreatorRecipeNode
  busy: boolean
  onCreatorChange: (creator: CreatorProjection) => void
  onNavigate: (nodeId: string) => void
  onReturnOutline: () => void
  onModelRequired: () => void
}) {
  const [values, setValues] = useState<Record<string, unknown>>(node.values)
  const [prompt, setPrompt] = useState('')
  const [proposal, setProposal] = useState<CreatorProposal | null>(() => creator.pending_proposals.find((item) => item.changes.some((change) => change.target_id === node.id)) || null)
  const [impact, setImpact] = useState('')
  const [sourceRequest, setSourceRequest] = useState('')
  const [sourceCandidates, setSourceCandidates] = useState<CreatorSourceCandidate[]>([])
  const [sourceInspections, setSourceInspections] = useState<Record<string, { status: string; url: string; content_type: string; bytes: number; sample: string; content_digest: string }>>({})
  const [working, setWorking] = useState(false)
  const [capabilityOpen, setCapabilityOpen] = useState(false)
  const trusted = creator.frozen_steps.includes(node.id)
  const unresolved = node.resolution?.status === 'unresolved'
  const capabilityConfirmed = trusted && !unresolved
  const changed = JSON.stringify(values) !== JSON.stringify(node.values)
  const freezeRevision = creator.active_freezes.find((freeze) => freeze.steps.includes(node.id))?.freeze_revision
  const isBusy = busy || working
  const nodeIndex = creator.trusted_recipe.nodes.findIndex((item) => item.id === node.id)
  const previousNode = creator.trusted_recipe.nodes[nodeIndex - 1]
  const nextNode = creator.trusted_recipe.nodes[nodeIndex + 1]
  const incomingRelation = creator.trusted_recipe.relations.find((relation) => relation.to_node_id === node.id)
  const sourceNode = creator.trusted_recipe.nodes.find((item) => item.id === incomingRelation?.from_node_id)
  const presentationSlots = node.experience?.status === 'available' ? node.experience.slots : []

  useEffect(() => {
    setValues(node.values)
    setPrompt('')
    setProposal(creator.pending_proposals.find((item) => item.changes.some((change) => change.target_id === node.id)) || null)
    setImpact('')
  }, [creator.pending_proposals, node.id, node.values])

  const fail = (error: unknown) => {
    if (error instanceof ApiError && error.code.includes('MODEL_UNBOUND')) {
      onModelRequired()
      return
    }
    showToast({ title: '节点调整未完成', description: friendlyError(error, 'node'), type: 'error' })
  }
  const stage = async () => {
    setWorking(true)
    try {
      const result = await proposeCreatorNodeValues(creator.session_id, {
        expected_revision: creator.revision,
        author: 'creator',
        summary: `调整 ${node.label}`,
        changes: [{ id: `edit.${node.id}.${creator.revision}`, target_id: node.id, operation: 'set_creator_binding', value: values }],
      })
      setProposal(result.proposal)
      setImpact('')
    } catch (error) { fail(error) } finally { setWorking(false) }
  }
  const ask = async () => {
    if (!prompt.trim()) return
    setWorking(true)
    try {
      const result = await refineCreatorNodeWithAi(creator.session_id, node.id, {
        prompt: prompt.trim(), expected_revision: creator.revision, author: 'creator', summary: `深化 ${node.label}`,
      })
      setProposal(result.proposal)
      setImpact('')
    } catch (error) { fail(error) } finally { setWorking(false) }
  }
  const preview = async () => {
    if (!proposal) return
    setWorking(true)
    try {
      const result = await previewCreatorProposal(creator.session_id, proposal.proposal_id, freezeRevision)
      const changedSteps = result.impact.changed_steps?.length || 1
      setImpact(changedSteps === 1
        ? '检查完成：这次修改只影响当前节点。'
        : `检查完成：这次修改会同时影响 ${changedSteps} 个相关节点。`)
    } catch (error) { fail(error) } finally { setWorking(false) }
  }
  const accept = async () => {
    if (!proposal) return
    setWorking(true)
    try {
      const result = await acceptCreatorProposal(creator.session_id, proposal.proposal_id, freezeRevision)
      onCreatorChange(result.creator)
      setProposal(null)
      setImpact('')
      setPrompt('')
      showToast({ title: '修改已保存', type: 'success' })
    } catch (error) { fail(error) } finally { setWorking(false) }
  }
  const reject = async () => {
    if (!proposal) return
    setWorking(true)
    try {
      const result = await rejectCreatorProposal(creator.session_id, proposal.proposal_id)
      onCreatorChange(result.creator)
      setValues(node.values)
      setProposal(null)
      setImpact('')
    } catch (error) { fail(error) } finally { setWorking(false) }
  }
  const confirm = async () => {
    setWorking(true)
    try {
      await confirmCreatorNode(creator.session_id, node.id)
      const result = await fetchCreatorSession(creator.session_id)
      onCreatorChange(result.creator)
      if (nextNode) onNavigate(nextNode.id)
      showToast({ title: '节点已确认', type: 'success' })
    } catch (error) { fail(error) } finally { setWorking(false) }
  }
  const rejectCapability = async () => {
    setWorking(true)
    try {
      const result = await rejectCreatorCapability(creator.session_id, node.id, creator.revision)
      onCreatorChange(result.creator)
      showToast({ title: '已退回为需要补齐', description: '需求保留在原节点，可以从这里进入能力工坊。', type: 'success' })
    } catch (error) { fail(error) } finally { setWorking(false) }
  }
  const discoverSources = async () => {
    if (!sourceRequest.trim()) return
    setWorking(true)
    try {
      const result = await discoverCreatorSources(creator.session_id, sourceRequest.trim())
      setSourceCandidates(result.candidates)
      setSourceInspections({})
    } catch (error) { fail(error) } finally { setWorking(false) }
  }
  const inspectSource = async (candidate: CreatorSourceCandidate) => {
    const url = candidate.rss_url || candidate.remote_url
    if (!url) return
    setWorking(true)
    try {
      const inspection = await inspectCreatorSource(url)
      setSourceInspections((current) => ({ ...current, [candidate.id]: inspection }))
    } catch (error) { fail(error) } finally { setWorking(false) }
  }
  const adoptSource = async (candidate: CreatorSourceCandidate) => {
    const inspection = sourceInspections[candidate.id]
    if (!inspection) return
    setWorking(true)
    try {
      const source = {
        id: `source.${candidate.id}`, kind: 'source', digest: inspection.content_digest,
        role: `Reviewed for ${node.label}`, name: candidate.name, provides: candidate.provides,
        remote_url: inspection.url, ...(candidate.rss_url ? { rss_url: candidate.rss_url } : {}),
        review_focus: candidate.review_focus,
      }
      const changes: Array<Record<string, unknown>> = [{ id: `source.${candidate.id}.${creator.revision}`, target_id: source.id, operation: 'add_source', value: source }]
      const urlField = node.editable_fields.find((field) => /url|source|feed/i.test(field.id) && ['string', 'string_list'].includes(field.value_type))
      if (urlField) {
        const nextValues = { ...values, [urlField.id]: urlField.value_type === 'string_list' ? [inspection.url] : inspection.url }
        changes.push({ id: `source-binding.${node.id}.${creator.revision}`, target_id: node.id, operation: 'set_creator_binding', value: nextValues })
      }
      const result = await proposeCreatorNodeValues(creator.session_id, {
        expected_revision: creator.revision, author: 'creator', summary: `采用并记录来源：${candidate.name}`, changes,
      })
      setProposal(result.proposal)
      setImpact('')
    } catch (error) { fail(error) } finally { setWorking(false) }
  }

  const choosePresentation = async (slotId: string, componentId: string) => {
    const slot = presentationSlots.find((item) => item.id === slotId)
    const component = slot?.components.find((item) => item.id === componentId)
    if (!slot || !component || component.fields.length) return
    setWorking(true)
    try {
      const result = await setCreatorExperience(creator.session_id, node.id, {
        expected_revision: creator.revision,
        expected_experience_revision: creator.experience_revision || 0,
        slot_id: slotId,
        component_id: componentId,
        field_sources: {},
      })
      onCreatorChange(result.creator)
      showToast({ title: '呈现方式已保存', type: 'success' })
    } catch (error) { fail(error) } finally { setWorking(false) }
  }

  return <aside className="creator-node-editor vip-detail-panel" aria-label={`调整 ${node.label}`}>
    <header className="semantic-side-head vip-detail-heading">
      <div><strong>{String(nodeIndex + 1).padStart(2, '0')}</strong><h2>{node.label}</h2></div>
      <ReviewStatus state={nodeReviewState(creator, node)} />
    </header>
    <div className="vip-detail-body">
      <section className="vip-detail-section"><span className="vip-detail-number">1</span><div><strong>节点目标</strong><p>{node.description}</p></div></section>

      <section className="vip-detail-section"><span className="vip-detail-number">2</span><div className="vip-detail-wide"><strong>当前做法</strong>
        {unresolved ? <div className="vip-capability-row is-unresolved"><span>{node.resolution?.needed_capability || node.description}</span><ReviewStatus state="unresolved" /></div> : <div className="vip-capability-row"><span>{node.resolution?.capability?.label || '可用做法'}</span><ReviewStatus state={trusted ? 'confirmed' : 'review'} showSuggestion={Boolean(proposal)} /><button className="vip-inline-icon" type="button" title="查看高级信息" onClick={() => setCapabilityOpen((value) => !value)}><Info /></button></div>}
        {capabilityOpen && !unresolved && <div className="vip-capability-actions"><span>{node.resolution?.capability?.trust_scope === 'workspace' ? '当前工作区可信' : node.resolution?.capability?.trust_scope === 'organization' ? '组织可信' : '系统可信'} · v{node.resolution?.capability?.revision}</span><button className="secondary-button" type="button" disabled={isBusy} onClick={() => void rejectCapability()}>不适合当前节点</button></div>}
        {unresolved && <a className="vip-capability-link" href={capabilityWorkshopUrl(creator, node)}><Wrench />补齐这个步骤</a>}
      </div></section>

      <section className="vip-detail-section"><span className="vip-detail-number">3</span><div className="vip-detail-wide"><strong>业务参数</strong><div className="vip-detail-fields"><FieldEditor node={node} values={values} onChange={setValues} disabled={isBusy} /></div>{changed && <button className="vip-save-fields" type="button" disabled={isBusy} onClick={() => void stage()}><Check />保存参数修改</button>}</div></section>

      <details className="vip-detail-section vip-source-section"><summary><span className="vip-detail-number">4</span><div><strong>资料来源</strong><p>{sourceNode ? <>来自节点：{String(creator.trusted_recipe.nodes.indexOf(sourceNode) + 1).padStart(2, '0')} {sourceNode.label}<span>{sourceNode.description}</span></> : '使用当前项目已审核的资料来源'}</p></div></summary>
        <div className="creator-source-query"><input value={sourceRequest} disabled={isBusy} onChange={(event) => setSourceRequest(event.currentTarget.value)} placeholder="查找并审核新的公开来源" /><button type="button" disabled={isBusy || sourceRequest.trim().length < 3} onClick={() => void discoverSources()}><Search />查找</button></div>
        {sourceCandidates.map((candidate) => { const inspection = sourceInspections[candidate.id]; return <article key={candidate.id}><div><strong>{candidate.name}</strong><p>{candidate.provides}</p></div><div><button className="secondary-button" type="button" disabled={isBusy} onClick={() => void inspectSource(candidate)}>{inspection ? '重新检查' : '检查可达性'}</button><button type="button" disabled={isBusy || !inspection} onClick={() => void adoptSource(candidate)}>采用来源</button></div></article> })}
      </details>

      <section className="vip-detail-section"><span className="vip-detail-number">5</span><div className="vip-detail-wide"><strong>可选择呈现方式</strong>{presentationSlots.length ? presentationSlots.map((slot) => <div className="vip-presentation-options" key={slot.id}>{slot.components.map((component) => <button type="button" className={slot.selected_component_id === component.id ? 'is-selected' : ''} disabled={isBusy || !component.available} key={component.id} onClick={() => void choosePresentation(slot.id, component.id)}>{component.label}</button>)}</div>) : <p>使用卡带默认呈现方式</p>}
        {presentationSlots.some((slot) => slot.components.some((component) => component.fields.length > 0)) && <ExperienceEditor creator={creator} node={node} disabled={isBusy} onChange={onCreatorChange} onBusy={setWorking} />}
      </div></section>

      <section className="vip-detail-section vip-ai-preview"><span className="vip-detail-number">6</span><div className="vip-detail-wide"><strong>AI 修改预览</strong>{proposal ? <>
        <div className="vip-preview-compare"><article><small>原始内容（当前版本）</small><p>{node.description}</p></article><ChevronRight /><article><small>AI 建议（预览）</small><p>{proposal.summary}</p>{!impact && <button className="vip-view-all-changes" type="button" disabled={isBusy} onClick={() => void preview()}>查看全部修改 ({proposal.changes.length}) <ChevronRight /></button>}</article></div>
        {impact && <div className="vip-expanded-review"><ProposalChanges node={node} proposal={proposal} /><p className="vip-impact-copy">{impact}</p><div className="vip-preview-actions"><button className="secondary-button" type="button" disabled={isBusy} onClick={() => void reject()}>放弃建议</button><button type="button" disabled={isBusy} onClick={() => void accept()}><Check />应用建议</button></div></div>}
      </> : <div className="vip-ai-refine"><textarea value={prompt} disabled={isBusy || changed} onChange={(event) => setPrompt(event.currentTarget.value)} placeholder="继续说明你希望如何调整这个节点" /><button type="button" disabled={isBusy || changed || !prompt.trim()} onClick={() => void ask()}><Sparkles />生成调整建议</button></div>}</div></section>

      <section className="vip-detail-section vip-confirm-copy"><span className="vip-detail-number">7</span><div><strong>确认节点</strong><p>确认后将进入下一节点，并影响后续输出与交付。</p></div></section>
    </div>
    <footer className="vip-detail-actions"><button className="secondary-button" type="button" disabled={!previousNode} onClick={() => previousNode && onNavigate(previousNode.id)}><ArrowLeft />返回上一节点</button><button className="secondary-button" type="button" onClick={onReturnOutline}>暂不确认</button><button type="button" disabled={isBusy || trusted || changed || unresolved} onClick={() => void confirm()}><Check />{capabilityConfirmed ? '节点已确认' : nextNode ? '确认并进入下一节点' : '确认节点'}</button></footer>
  </aside>
}

export function IntentStudio({ projectId }: { projectId: string }) {
  const [restoredWorkspace] = useState(() => readCreatorWorkspace(projectId))
  const { theme, setTheme } = useAppTheme()
  const [themePanelOpen, setThemePanelOpen] = useState(false)
  const themeButtonRef = useRef<HTMLButtonElement>(null)
  const [creator, setCreator] = useState<CreatorProjection | null>(null)
  const [goal, setGoal] = useState(restoredWorkspace?.goal || '')
  const [selectedId, setSelectedId] = useState(restoredWorkspace?.selectedId || '')
  const [possibilities, setPossibilities] = useState<CreatorPossibility[]>(restoredWorkspace?.possibilities || [])
  const [middleView, setMiddleView] = useState<'outline' | 'detail'>(restoredWorkspace?.middleView || 'outline')
  const [workspacePane, setWorkspacePane] = useState<WorkspacePane>(restoredWorkspace?.workspacePane || 'collaboration')
  const [detailOpen, setDetailOpen] = useState(restoredWorkspace?.middleView === 'detail')
  const [aiPanelOpen, setAiPanelOpen] = useState(false)
  const [activePanel, setActivePanel] = useState<SemanticPanelId>('canvas')
  const [visibleRelations, setVisibleRelations] = useState<CreatorRelationKind[]>(['control', 'data', 'dependency'])
  const [resourceManager, setResourceManager] = useState<'models' | 'tools' | null>(null)
  const [nestedNode, setNestedNode] = useState<{ node: CreatorRecipeNode; mode: 'edit' | 'preview' } | null>(null)
  const [canvasLayoutRevision, setCanvasLayoutRevision] = useState(0)
  const [clarification, setClarification] = useState<CreatorClarification | null>(restoredWorkspace?.clarification || null)
  const [stewardInput, setStewardInput] = useState('')
  const [stewardMessages, setStewardMessages] = useState<StewardMessage[]>(restoredWorkspace?.messages || [STEWARD_WELCOME])
  const [canvasTool, setCanvasTool] = useState<CreatorCanvasTool>('inspect')
  const [contextNodeIds, setContextNodeIds] = useState<string[]>([])
  const [aiStatus, setAiStatus] = useState<{ provider: string; has_key: boolean; base_url: string; model: string } | null>(null)
  const [packageResult, setPackageResult] = useState<CreatorPackage | null>(restoredWorkspace?.packageResult || null)
  const [packageRevision, setPackageRevision] = useState<number | null>(restoredWorkspace?.packageRevision || null)
  const [runnerStatus, setRunnerStatus] = useState<DesktopRunnerStatus | null>(null)
  const [runnerDelivery, setRunnerDelivery] = useState<CreatorRunnerDelivery | null>(null)
  const [recipePreview, setRecipePreview] = useState<CreatorRecipePreview | null>(null)
  const [packageError, setPackageError] = useState('')
  const [runnerError, setRunnerError] = useState('')
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [composerError, setComposerError] = useState('')
  const [modelSetupOpen, setModelSetupOpen] = useState(false)
  const [projectMenuOpen, setProjectMenuOpen] = useState(false)
  const [syncState, setSyncState] = useState<'loading' | 'saving' | 'loaded' | 'saved' | 'new' | 'error'>('loading')
  const [savedAt, setSavedAt] = useState<Date | null>(null)
  const [projects, setProjects] = useState<Array<{ project_id: string; session_id: string; name: string; intent: string; revision: number }>>([])
  const [pendingAiAction, setPendingAiAction] = useState<'discover' | 'compose' | 'node' | null>(null)
  const stewardThreadRef = useRef<HTMLDivElement | null>(null)
  const stewardComposerRef = useRef<HTMLTextAreaElement | null>(null)
  const aiConnectedRef = useRef<boolean | null>(null)
  const workspaceRevisionRef = useRef(0)
  const workspaceHydratedRef = useRef(false)
  const workspaceErrorShownRef = useRef(false)
  const resolutionCheckRef = useRef('')
  const canvasPanelRef = useRef<HTMLElement | null>(null)

  useEffect(() => {
    const snapshot: CreatorWorkspaceSnapshot = {
      version: 1,
      goal,
      messages: stewardMessages.slice(-80),
      clarification,
      possibilities,
      selectedId,
      middleView,
      workspacePane,
      packageResult,
      packageRevision,
    }
    localStorage.setItem(CREATOR_WORKSPACE_KEY(projectId), JSON.stringify(snapshot))
    if (!workspaceHydratedRef.current) return
    setSyncState('saving')
    const timer = window.setTimeout(() => {
      saveCreatorWorkspace(projectId, snapshot, workspaceRevisionRef.current)
        .then(({ workspace }) => {
          workspaceRevisionRef.current = workspace.revision
          workspaceErrorShownRef.current = false
          setSavedAt(new Date(workspace.updated_at))
          setSyncState('saved')
        })
        .catch((error) => {
          setSyncState('error')
          if (workspaceErrorShownRef.current) return
          workspaceErrorShownRef.current = true
          showToast({
            title: error instanceof ApiError && error.code.includes('REVISION_CONFLICT') ? '草稿在另一个页面已更新' : '草稿同步失败',
            description: '本机副本仍然保留。刷新页面可重新读取服务端版本。',
            type: 'error',
          })
        })
    }, 700)
    return () => window.clearTimeout(timer)
  }, [clarification, goal, middleView, packageResult, packageRevision, possibilities, projectId, selectedId, stewardMessages, workspacePane])

  useEffect(() => {
    let active = true
    Promise.all([fetchCreatorProject(projectId), fetchCreatorWorkspace<CreatorWorkspaceSnapshot>(projectId)])
      .then(([{ creator: value }, { workspace }]) => {
        if (!active) return
        const recovered = normalizeCreatorWorkspace(workspace?.snapshot) || restoredWorkspace
        workspaceRevisionRef.current = workspace?.revision || 0
        workspaceHydratedRef.current = true
        if (recovered) {
          setGoal(recovered.goal)
          setStewardMessages(recovered.messages)
          setClarification(recovered.clarification)
          setPossibilities(recovered.possibilities)
          setSelectedId(recovered.selectedId)
          setMiddleView(recovered.middleView)
          setWorkspacePane(recovered.workspacePane)
          setPackageResult(recovered.packageResult)
          setPackageRevision(recovered.packageRevision)
          if (workspace) setSavedAt(new Date(workspace.updated_at))
        }
        if (!value) {
          setSyncState('new')
          return
        }
        setCreator(value)
        setGoal(value.intent)
        const returnedNodeId = new URLSearchParams(window.location.search).get('nodeId') || ''
        const restoredNodeId = recovered?.selectedId || ''
        const nextNodeId = value.trusted_recipe.nodes.find((node) => nodeReviewState(value, node) !== 'confirmed')?.id || value.trusted_recipe.nodes[0]?.id || ''
        const selected = value.trusted_recipe.nodes.some((node) => node.id === returnedNodeId)
          ? returnedNodeId
          : value.trusted_recipe.nodes.some((node) => node.id === restoredNodeId) ? restoredNodeId : nextNodeId
        setSelectedId(selected)
        setMiddleView(returnedNodeId ? 'detail' : recovered?.middleView || 'outline')
        setWorkspacePane(returnedNodeId ? 'outline' : recovered?.workspacePane || 'collaboration')
        if (recovered?.packageRevision !== value.revision) {
          setPackageResult(null)
          setPackageRevision(null)
          setRunnerDelivery(null)
        }
        setSyncState('loaded')
        const publishedCapability = new URLSearchParams(window.location.search).get('capabilityPublished')
        setStewardMessages((current) => current.length > 1 ? current : [{
          id: 'loaded-outline', role: 'assistant',
          text: publishedCapability ? '新做法已经回填到原方案。请检查这一节点的参数和结果界面，然后确认继续。' : '已加载当前项目大纲。它还不是最终答案，你可以继续描述，也可以直接指向或框选画布中的部分。',
        }])
        if (publishedCapability) {
          showToast({ title: '新做法已回填', description: '原方案没有丢失，现在可以继续审核当前步骤。', type: 'success' })
          const cleanUrl = new URL(window.location.href)
          cleanUrl.searchParams.delete('capabilityPublished')
          cleanUrl.searchParams.delete('nodeId')
          window.history.replaceState(null, '', `${cleanUrl.pathname}${cleanUrl.search}${cleanUrl.hash}`)
        }
      })
      .catch(() => {
        setSyncState('error')
        showToast({ title: '草稿读取失败', description: '请刷新页面后重试。', type: 'error' })
      })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [projectId])

  useEffect(() => {
    listCreatorProjects().then((result) => setProjects(result.projects)).catch(() => null)
  }, [projectId, creator?.revision])

  useEffect(() => {
    fetchCreatorAiStatus()
      .then((status) => {
        setAiStatus(status)
        aiConnectedRef.current = status.has_key
      })
      .catch(() => null)
  }, [])

  useEffect(() => {
    fetchDesktopRunnerStatus().then(setRunnerStatus).catch(() => null)
  }, [])

  useEffect(() => {
    stewardThreadRef.current?.scrollTo({ top: stewardThreadRef.current.scrollHeight, behavior: 'smooth' })
  }, [busy, creator, stewardMessages])

  useEffect(() => {
    if (!creator || !creator.capability_resolution?.unresolved) return
    const key = `${creator.session_id}:${creator.capability_resolution.revision}`
    if (resolutionCheckRef.current === key) return
    resolutionCheckRef.current = key
    resolveCreatorCapabilities(creator.session_id, creator.revision)
      .then((result) => {
        if (!result.resolved_node_ids.length) return
        saveCreator(result.creator)
        setSelectedId(result.resolved_node_ids[0])
        setMiddleView('detail')
        setWorkspacePane('outline')
        setStewardMessages((current) => [...current, {
          id: `capability.${Date.now()}`,
          role: 'assistant',
          text: '新的做法已经放回原步骤。请检查参数和结果界面，确认后我会带你继续下一步。',
        }])
        showToast({ title: '新的可信能力已匹配', description: '原草稿节点已保留，请打开节点审核来源和默认字段。', type: 'success' })
      })
      .catch(() => null)
  }, [creator?.session_id, creator?.revision, creator?.capability_resolution?.revision, creator?.capability_resolution?.unresolved])

  useEffect(() => {
    if (!creator) return
    const selected = creator.trusted_recipe.nodes.find((node) => node.id === selectedId)
    if (selected && nodeReviewState(creator, selected) !== 'confirmed') return
    const next = creator.trusted_recipe.nodes.find((node) => nodeReviewState(creator, node) !== 'confirmed')
    if (next) setSelectedId(next.id)
  }, [creator?.session_id, creator?.revision, creator?.experience_revision])

  const selectedNode = useMemo(() => creator?.trusted_recipe.nodes.find((node) => node.id === selectedId) || null, [creator, selectedId])
  const guidance = useMemo(
    () => creatorGuidance(creator, clarification, possibilities, packageResult, aiStatus?.has_key ?? null, runnerStatus, runnerDelivery),
    [aiStatus?.has_key, clarification, creator, packageResult, possibilities, runnerDelivery, runnerStatus],
  )
  const confirmedCount = creator?.trusted_recipe.nodes.filter((node) => node.resolution?.status !== 'unresolved' && creator.frozen_steps.includes(node.id)).length || 0
  const totalCount = creator?.trusted_recipe.nodes.length || 0
  const unresolvedCount = creator?.trusted_recipe.nodes.filter((node) => node.resolution?.status === 'unresolved').length || 0
  const reviewCount = Math.max(0, totalCount - confirmedCount - unresolvedCount)
  const contextNodes = useMemo(() => (recipePreview?.nodes || creator?.trusted_recipe.nodes || []).filter((node) => contextNodeIds.includes(node.id)), [contextNodeIds, creator, recipePreview])
  const saveCreator = (next: CreatorProjection) => {
    setCreator(next)
    setSyncState('saved')
    setSavedAt(new Date())
    setPackageResult(null)
    setPackageRevision(null)
    setPackageError('')
    setRunnerDelivery(null)
    setRunnerError('')
  }
  const requestModelConnection = (action: 'discover' | 'compose' | 'node' | null = null) => {
    setPendingAiAction(action)
    setModelSetupOpen(true)
  }
  const isModelBlock = (error: unknown, action: 'discover' | 'compose' | 'node') => {
    if (!(error instanceof ApiError) || !error.code.includes('MODEL_UNBOUND')) return false
    requestModelConnection(action)
    return true
  }
  const discover = async (requestedContext = goal, visibleMessage = requestedContext) => {
    const context = requestedContext.trim()
    if (context.length < 3) return
    if (aiConnectedRef.current === false) {
      requestModelConnection('discover')
      return
    }
    setBusy(true)
    setComposerError('')
    setPossibilities([])
    setClarification(null)
    setGoal(context)
    setStewardMessages((current) => [...current, { id: `user.${Date.now()}`, role: 'user', text: visibleMessage.trim() }])
    try {
      const discovery = await discoverCreatorPossibilities(context)
      setPossibilities(discovery.possibilities)
      setClarification(discovery.clarification)
      setWorkspacePane(discovery.possibilities.length ? 'outline' : 'collaboration')
      setStewardMessages((current) => [...current, {
        id: `assistant.${Date.now()}`,
        role: 'assistant',
        text: discovery.clarification
          ? discovery.clarification.question
          : `我整理了 ${discovery.possibilities.length} 个可比较方向。选择一个方向后，我才会查询可信能力并生成大纲。`,
        clarification: discovery.clarification,
      }])
    } catch (error) {
      if (isModelBlock(error, 'discover')) return
      const description = friendlyError(error, 'discover')
      setComposerError(description)
      showToast({ title: '暂时无法摆出大纲', description, type: 'error' })
    } finally { setBusy(false) }
  }
  const compose = async (requestedGoal: string) => {
    const nextGoal = requestedGoal.trim()
    if (nextGoal.length < 3) return
    if (aiConnectedRef.current === false) {
      requestModelConnection('compose')
      return
    }
    setBusy(true)
    setComposerError('')
    setPossibilities([])
    setClarification(null)
    try {
      if (creator) {
        const preview = await previewCreatorRecompose(creator.session_id, { goal: nextGoal, expected_revision: creator.revision })
        setRecipePreview(preview)
        setGoal(nextGoal)
        setStewardMessages((current) => [...current, {
          id: `assistant.${Date.now()}`,
          role: 'assistant',
          text: '我已经把这次补充反映到新大纲预览里。先看变化是否接近你的意思，再决定应用或继续讨论。',
        }])
        return
      }
      const result = await composeCreatorRecipe({ session_id: creatorId(), project_id: projectId, goal: nextGoal })
      if (!result.creator) throw new Error('missing creator')
      saveCreator(result.creator)
      setGoal(result.creator.intent)
      setSelectedId(result.creator.trusted_recipe.nodes[0]?.id || '')
      setMiddleView('outline')
      setWorkspacePane('outline')
      setStewardMessages((current) => [...current, { id: `assistant.${Date.now()}`, role: 'assistant', text: '已根据选定方向生成第一版大纲。请逐个审核节点、能力来源与业务参数。' }])
      showToast({ title: '整体草稿已生成', description: '你可以继续对话或直接指向大纲内容。', type: 'success' })
    } catch (error) {
      if (isModelBlock(error, 'compose')) return
      const description = friendlyError(error, 'compose')
      setComposerError(description)
      showToast({ title: '整体编排未完成', description, type: 'error' })
    } finally { setBusy(false) }
  }
  const applyRecipePreview = async () => {
    if (!creator || !recipePreview) return
    setBusy(true)
    try {
      const result = await acceptCreatorRecompose(creator.session_id, recipePreview.proposal_id, creator.revision)
      saveCreator(result.creator)
      setGoal(result.creator.intent)
      setSelectedId('')
      setContextNodeIds([])
      setRecipePreview(null)
      setStewardMessages((current) => [...current, { id: `assistant.${Date.now()}`, role: 'assistant', text: '这版已经应用，但仍然不是终稿。继续指出不对的地方，我会沿着你的意思再调整。' }])
      showToast({ title: '整体草稿已更新', description: '请逐个打开节点继续审核。', type: 'success' })
    } catch (error) {
      showToast({ title: '预览已失效', description: friendlyError(error, 'compose'), type: 'error' })
    } finally { setBusy(false) }
  }
  const rejectRecipePreview = () => {
    setRecipePreview(null)
    setContextNodeIds([])
    if (creator) setGoal(creator.intent)
    setStewardMessages((current) => [...current, {
      id: `assistant.${Date.now()}`,
      role: 'assistant',
      text: '这版先不采用，画布已经回到原来的大纲。继续说你想保留什么、换掉什么。',
    }])
  }
  const continueCoCreation = (message: string) => {
    const feedback = message.trim()
    if (!feedback || busy) return
    const scope = contextNodes.length
      ? `本轮只讨论这些步骤：${contextNodes.map((node) => `“${node.label}”`).join('、')}。\n`
      : ''
    const nextGoal = `${goal.trim()}\n${scope}本轮补充：${feedback}`.trim()
    setStewardInput('')
    setGoal(creator ? nextGoal : feedback)
    if (creator) {
      setStewardMessages((current) => [...current, { id: `user.${Date.now()}`, role: 'user', text: feedback }])
      void compose(nextGoal)
    } else void discover(feedback)
  }
  const answerClarification = (answer: string) => {
    const nextContext = `${goal.trim()}\n补充：${answer}`.trim()
    setClarification(null)
    void discover(nextContext, answer)
  }
  const chooseDirection = (possibility: CreatorPossibility) => {
    const nextGoal = possibility.recipe.intent.trim()
    setGoal(nextGoal)
    setPossibilities([])
    setStewardMessages((current) => [...current, { id: `user.${Date.now()}`, role: 'user', text: `采用方向：${possibility.title}` }])
    void compose(nextGoal)
  }
  const buildPackage = async () => {
    if (!creator) return
    setBusy(true)
    setPackageError('')
    try {
      const result = await packageCreatorProject(creator.session_id, creator.revision)
      setPackageResult(result)
      setPackageRevision(creator.revision)
      setRunnerDelivery(null)
      setRunnerError('')
      fetchDesktopRunnerStatus().then(setRunnerStatus).catch(() => null)
      setWorkspacePane('collaboration')
      setStewardMessages((current) => [...current, {
        id: `package.${Date.now()}`,
        role: 'assistant',
        text: '试运行包已经通过签名验证。下载后在 Desktop Runner 中启用，就能用真实输入运行并查看结果。',
      }])
      showToast({ title: '打包完成', description: '签名已验证，可以交给独立测试台。', type: 'success' })
    } catch (error) {
      const description = friendlyError(error, 'package')
      setPackageError(description)
      showToast({ title: '暂时不能打包', description, type: 'error' })
    } finally { setBusy(false) }
  }
  const deliverToRunner = async () => {
    if (!creator || !packageResult) return
    setBusy(true)
    setRunnerError('')
    try {
      const result = await deliverCreatorProject(creator.session_id, creator.revision)
      setPackageResult(result.package)
      setPackageRevision(creator.revision)
      setRunnerDelivery(result)
      setRunnerStatus((current) => current ? {
        ...current,
        available: true,
        cartridge: result.status === 'installed' ? result.delivery.cartridge : current.cartridge,
      } : current)
      setStewardMessages((current) => [...current, {
        id: `runner.${Date.now()}`,
        role: 'assistant',
        text: result.status === 'trust_required'
          ? 'Desktop Runner 已验证签名，但这个本地发布者尚未获得你的信任。请在 Runner 中核对密钥指纹并确认，随后会自动安装。'
          : '签名包已经由 Desktop Runner 独立验签并安装。现在打开 Runner，放入真实样例即可试运行。',
      }])
      showToast(result.status === 'trust_required'
        ? { title: '等待发布者确认', description: '请前往 Runner 核对并确认本地发布者。', type: 'info' }
        : { title: '已送入 Desktop Runner', description: 'Runner 已完成独立验签和安装。', type: 'success' })
    } catch (error) {
      const description = error instanceof ApiError ? error.message : 'Desktop Runner 没有接收当前试运行包。'
      setRunnerError(description)
      fetchDesktopRunnerStatus().then(setRunnerStatus).catch(() => null)
      showToast({ title: '暂时无法送入 Runner', description, type: 'error' })
    } finally { setBusy(false) }
  }
  const refreshCapabilities = async () => {
    if (!creator) return
    setBusy(true)
    try {
      const result = await resolveCreatorCapabilities(creator.session_id, creator.revision)
      saveCreator(result.creator)
      showToast({
        title: result.resolved_node_ids.length ? '已补齐可用能力' : '能力状态已是最新',
        description: result.resolved_node_ids.length ? `已在原草稿中匹配 ${result.resolved_node_ids.length} 个节点，请审核来源和字段。` : undefined,
        type: 'success',
      })
    } catch (error) {
      showToast({ title: '能力检查未完成', description: friendlyError(error, 'compose'), type: 'error' })
    } finally { setBusy(false) }
  }
  const connectModel = async (connection: { base_url: string; api_key: string; model: string }) => {
    await connectCreatorAi(connection)
    aiConnectedRef.current = true
    fetchCreatorAiStatus().then(setAiStatus).catch(() => null)
    const retry = pendingAiAction
    setModelSetupOpen(false)
    setPendingAiAction(null)
    showToast({
      title: 'AI 已连接',
      description: retry === 'node' ? '可以继续调整这个节点。' : retry ? '正在继续刚才的创作。' : '现在可以从目标描述开始。',
      type: 'success',
    })
    if (retry === 'discover') void discover()
    if (retry === 'compose') void compose(goal)
  }
  const createProject = () => {
    const nextId = `project.${crypto.randomUUID()}`
    localStorage.setItem('cartridgeflow.creator-project', nextId)
    window.location.assign(`/projects/${encodeURIComponent(nextId)}/studio`)
  }
  const renameProject = async () => {
    if (!creator) return
    const name = window.prompt('项目名称', creator.project_name || creator.intent)
    if (!name?.trim()) return
    setBusy(true)
    try {
      const result = await renameCreatorProject(projectId, name.trim())
      saveCreator(result.creator)
      setProjectMenuOpen(false)
      showToast({ title: '项目已重命名', type: 'success' })
    } catch (error) {
      showToast({ title: '项目重命名失败', description: friendlyError(error, 'compose'), type: 'error' })
    } finally { setBusy(false) }
  }
  const removeProject = async () => {
    if (!creator || !window.confirm(`删除项目“${creator.project_name || creator.intent}”？`)) return
    setBusy(true)
    try {
      await deleteCreatorProject(projectId)
      const next = projects.find((item) => item.project_id !== projectId)
      if (next) window.location.assign(`/projects/${encodeURIComponent(next.project_id)}/studio`)
      else createProject()
    } catch (error) {
      showToast({ title: '项目删除失败', description: friendlyError(error, 'compose'), type: 'error' })
      setBusy(false)
    }
  }

  const openNodeDetail = (nodeId = selectedId) => {
    if (nodeId) setSelectedId(nodeId)
    setMiddleView('detail')
    setDetailOpen(true)
    setActivePanel('detail')
  }
  const openNestedLayer = useCallback((nodeId: string, mode: 'edit' | 'preview' = 'edit') => {
    const node = creator?.trusted_recipe.nodes.find((item) => item.id === nodeId)
    if (node) setNestedNode({ node, mode })
  }, [creator])
  const runGuidanceAction = () => {
    if (guidance.action === 'connect-ai') {
      requestModelConnection()
      return
    }
    if (guidance.action === 'focus-composer') {
      setAiPanelOpen(true)
      setActivePanel('ai')
      requestAnimationFrame(() => stewardComposerRef.current?.focus())
      return
    }
    if (guidance.action === 'show-directions') {
      setAiPanelOpen(true)
      setActivePanel('ai')
      return
    }
    if (guidance.action === 'open-node' && creator && guidance.nodeId) {
      const node = creator.trusted_recipe.nodes.find((item) => item.id === guidance.nodeId)
      if (node?.resolution?.status === 'unresolved') {
        openNestedLayer(node.id)
        return
      }
      openNodeDetail(guidance.nodeId)
      return
    }
    if (guidance.action === 'build-package') {
      void buildPackage()
      return
    }
    if (guidance.action === 'deliver-runner') {
      void deliverToRunner()
      return
    }
    if (guidance.action === 'open-runner') {
      window.open(runnerDelivery?.delivery.runner_url || runnerStatus?.url || 'http://127.0.0.1:18990/', '_blank', 'noopener,noreferrer')
      return
    }
    if (guidance.action === 'download-package' && packageResult) {
      const download = document.createElement('a')
      download.href = packageResult.url
      download.download = packageResult.filename
      download.click()
    }
  }
  const resetCanvasLayout = () => {
    localStorage.removeItem(`cartridgeflow.creator-layout.v2.${projectId}.horizontal`)
    localStorage.removeItem(`cartridgeflow.creator-layout.v2.${projectId}.vertical`)
    setCanvasLayoutRevision((value) => value + 1)
  }
  const toggleCanvasFullscreen = async () => {
    if (document.fullscreenElement) await document.exitFullscreen()
    else await canvasPanelRef.current?.requestFullscreen()
  }
  const projectDisplayName = creator?.project_name || creator?.intent || (projectId.startsWith('project.') ? '未命名项目' : projectId)
  const syncLabel = busy
    ? '正在处理'
    : syncState === 'saving'
      ? '正在保存草稿'
    : syncState === 'saved' && savedAt
      ? `已保存 ${savedAt.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false })}`
      : syncState === 'loaded'
        ? '项目已加载'
        : syncState === 'new'
          ? aiStatus?.has_key ? '等待目标描述' : '等待连接 AI'
          : syncState === 'error'
            ? '同步失败'
            : '正在加载'
  const routeNodes = creator?.trusted_recipe.nodes || []
  const toggleRelation = (kind: CreatorRelationKind) => setVisibleRelations((current) => current.includes(kind) ? current.filter((item) => item !== kind) : [...current, kind])
  const canvasToolbar = <nav className="semantic-canvas-toolstack" aria-label="画布工具">
    <IconButton label="选择节点" variant={canvasTool === 'inspect' ? 'filled' : 'subtle'} onClick={() => { setCanvasTool('inspect'); setContextNodeIds([]) }}><MousePointer2 /></IconButton>
    <IconButton label="指向 AI 讨论对象" variant={canvasTool === 'pointer' ? 'filled' : 'subtle'} onClick={() => { setCanvasTool('pointer'); setContextNodeIds([]) }}><Target /></IconButton>
    <IconButton label="框选 AI 讨论范围" variant={canvasTool === 'lasso' ? 'filled' : 'subtle'} onClick={() => { setCanvasTool('lasso'); setContextNodeIds([]) }}><ScanLine /></IconButton>
    <i />
    <IconButton label="模型配置" variant="subtle" onClick={() => setResourceManager('models')}><Cloud /></IconButton>
    <IconButton label="工具配置" variant="subtle" onClick={() => setResourceManager('tools')}><Wrench /></IconButton>
    <IconButton label="重新检查可用能力" variant="subtle" disabled={!unresolvedCount || busy} onClick={() => void refreshCapabilities()}><RefreshCw /></IconButton>
    <IconButton label="打包与交付" variant="subtle" disabled={!creator?.generation_readiness.ready} onClick={() => void buildPackage()}><Package /></IconButton>
    <i />
    <IconButton label="重新自动布局" variant="subtle" onClick={resetCanvasLayout}><RotateCcw /></IconButton>
    <IconButton label="全屏画布" variant="subtle" onClick={() => void toggleCanvasFullscreen()}><Maximize2 /></IconButton>
  </nav>

  return <>
    <SemanticWorkbench
      detailOpen={detailOpen}
      aiOpen={aiPanelOpen}
      activePanel={activePanel}
      onActivePanelChange={setActivePanel}
      header={<header className="creator-topbar vip-topbar">
      <div className="creator-brand">
        <span className="creator-brand-mark" aria-hidden="true">C</span>
        <strong>CartridgeFlow</strong>
        <span className="vip-brand-divider" />
        <Button className="vip-project-crumb" variant="subtle" onClick={() => setProjectMenuOpen((value) => !value)}>项目 <b>/</b> {projectDisplayName} <ChevronDown /></Button>
        {projectMenuOpen && <div className="creator-project-menu semantic-project-menu">{projects.map((project) => <a className={project.project_id === projectId ? 'is-current' : ''} href={`/projects/${encodeURIComponent(project.project_id)}/studio`} key={project.project_id}><span>{project.name}</span><small>v{project.revision}</small></a>)}<div className="creator-project-menu-actions"><Button variant="subtle" onClick={createProject}><Plus />新建</Button>{creator && <><Button variant="subtle" onClick={() => void renameProject()}>重命名</Button><Button color="red" variant="subtle" onClick={() => void removeProject()}>删除</Button></>}</div></div>}
      </div>
      <div className="semantic-runtime-bar" aria-label="设计与运行">
        <Button variant="default" className="is-active" leftSection={<PencilRuler />}>设计</Button>
        <Button variant="subtle" leftSection={<Play />} disabled={!creator?.generation_readiness.ready}>运行</Button>
        <IconButton label="暂停" variant="subtle" disabled><Pause /></IconButton>
        <IconButton label="停止" variant="subtle" disabled><Square /></IconButton>
        <IconButton label="历史" variant="subtle" onClick={() => { setAiPanelOpen(true); setActivePanel('ai') }}><History /></IconButton>
      </div>
      <div className="creator-top-actions">
        <div className={`vip-autosave is-${busy ? 'busy' : syncState}`} title={aiStatus?.has_key ? `AI 已连接：${aiStatus.model}` : 'AI 尚未连接'}><i />{syncLabel}</div>
        <Button className={`creator-ai-button ${aiStatus?.has_key ? 'is-connected' : ''}`} variant="default" onClick={() => setResourceManager('models')} leftSection={<Cloud />}>{aiStatus?.has_key ? aiStatus.model || 'AI 已连接' : '连接 AI'}</Button>
        <IconButton ref={themeButtonRef} label={`外观：${theme.label}`} variant="subtle" onClick={() => setThemePanelOpen(true)}><Sun /></IconButton>
      </div>
    </header>}
      commandBar={<header className="semantic-commandbar">
        <div className="semantic-command-main">
        <div className="semantic-relation-filters" aria-label="语义关系显示">
          <Field.Checkbox label="主流程" checked={visibleRelations.includes('control')} onChange={() => toggleRelation('control')} />
          <Field.Checkbox label="数据流" checked={visibleRelations.includes('data')} onChange={() => toggleRelation('data')} />
          <Field.Checkbox label="资源依赖" checked={visibleRelations.includes('dependency')} onChange={() => toggleRelation('dependency')} />
          <span>{routeNodes.length || 2} 节点 · {confirmedCount} 可信 · {reviewCount} 待审核 · {unresolvedCount || (!creator ? 2 : 0)} 待补齐</span>
        </div>
        <nav className="semantic-node-route" aria-label="节点快速导航">
          {(routeNodes.length ? routeNodes : [{ id: 'placeholder-start', label: '开始' }, { id: 'placeholder-end', label: '结束' }]).map((node, index, nodes) => {
            const trusted = creator ? creator.frozen_steps.includes(node.id) : false
            return <span key={node.id}><Button variant="subtle" className={`${trusted ? 'is-trusted' : 'is-untrusted'}${selectedId === node.id ? ' is-current' : ''}`} title={node.label} onClick={() => { if (creator) setSelectedId(node.id); setActivePanel('canvas') }}><i />{String(index + 1).padStart(2, '0')}</Button>{index < nodes.length - 1 && <b />}</span>
          })}
        </nav>
        </div>
        <div className="semantic-panel-actions">
          <Button variant={detailOpen ? 'light' : 'default'} disabled={!selectedNode} onClick={() => { setDetailOpen((value) => !value); setActivePanel(detailOpen ? 'canvas' : 'detail') }} leftSection={<FileText />}>详情</Button>
          <Button variant={aiPanelOpen ? 'light' : 'default'} onClick={() => { setAiPanelOpen((value) => !value); setActivePanel(aiPanelOpen ? 'canvas' : 'ai') }} leftSection={<Bot />}>AI 管家</Button>
        </div>
      </header>}
      canvas={<section className="vip-canvas-panel" ref={canvasPanelRef} aria-label="语义画布">
        {packageError && <div className="creator-package-error" role="alert"><strong>打包未完成</strong><span>{packageError}</span></div>}
        {runnerError && <div className="creator-package-error creator-runner-error" role="alert"><strong>Runner 未接收</strong><span>{runnerError}</span></div>}
        <div className={`creator-canvas vip-canvas-surface tool-${canvasTool}`}>
          <IntentCanvas key={canvasLayoutRevision} creator={creator} preview={recipePreview} draftGoal={goal} selectedId={selectedId} contextNodeIds={contextNodeIds} tool={canvasTool} visibleRelations={visibleRelations} toolbar={canvasToolbar} onSelect={(nodeId) => { setSelectedId(nodeId); if (nodeId) { setMiddleView('detail'); setDetailOpen(true); setActivePanel('detail') } }} onContextChange={setContextNodeIds} onOpenLayer={(nodeId) => openNestedLayer(nodeId)} onPreviewLayer={(nodeId) => openNestedLayer(nodeId, 'preview')} />
          {recipePreview && <section className="creator-draft-review" aria-label="新大纲确认"><div><strong>新大纲已铺在画布上</strong><span>新增 {recipePreview.impact.added_node_ids.length} · 保留 {recipePreview.impact.retained_node_ids.length} · 移除 {recipePreview.impact.removed_node_ids.length}</span></div><Button variant="default" disabled={busy} onClick={rejectRecipePreview}>保留旧版</Button><Button disabled={busy} onClick={() => void applyRecipePreview()} leftSection={<Check />}>应用这版</Button></section>}
        </div>
        {loading && <div className="creator-loading"><Loader2 className="spinning" /><span>正在读取项目</span></div>}
      </section>}
      detail={selectedNode && creator ? <div className="semantic-detail-stack"><header className="semantic-side-head"><div><FileText /><strong>详情</strong><span>{selectedNode.label}</span></div><IconButton label="折叠详情" variant="subtle" onClick={() => { setDetailOpen(false); setActivePanel('canvas') }}><X /></IconButton></header><NodeEditor key={`${selectedNode.id}:${creator.revision}:${creator.experience_revision}`} creator={creator} node={selectedNode} busy={busy} onCreatorChange={saveCreator} onNavigate={(nodeId) => { setSelectedId(nodeId); setMiddleView('detail') }} onReturnOutline={() => { setDetailOpen(false); setActivePanel('canvas') }} onModelRequired={() => requestModelConnection('node')} /></div> : undefined}
      ai={<CollaborationPanel creator={creator} goal={goal} selectedNode={selectedNode} busy={busy} composerError={composerError} stewardInput={stewardInput} stewardMessages={stewardMessages} clarification={clarification} guidance={guidance} runnerUrl={runnerDelivery?.delivery.runner_url || runnerStatus?.url || 'http://127.0.0.1:18990/'} threadRef={stewardThreadRef} composerRef={stewardComposerRef} onInput={(value) => { setStewardInput(value); setComposerError('') }} onSubmit={continueCoCreation} onClarification={answerClarification} onGuidanceAction={runGuidanceAction} onOpenDetail={() => openNodeDetail()} onClose={() => { setAiPanelOpen(false); setActivePanel('canvas') }} directions={(possibilities.length || clarification) ? <DirectionExplorer goal={goal} clarification={clarification} possibilities={possibilities} busy={busy} onChoose={chooseDirection} /> : undefined} />}
    />
    <Suspense fallback={null}>
      {modelSetupOpen && <ModelConnectionDialog opened current={aiStatus} onConnect={connectModel} onClose={() => { setModelSetupOpen(false); setPendingAiAction(null) }} />}
      {resourceManager && <ResourceManagerDialog opened initialTab={resourceManager} projectId={projectId} onClose={() => { setResourceManager(null); fetchCreatorAiStatus().then(setAiStatus).catch(() => null) }} />}
      {themePanelOpen && <ThemeDialog opened theme={theme} onChange={setTheme} onClose={() => {
        setThemePanelOpen(false)
        requestAnimationFrame(() => themeButtonRef.current?.focus())
      }} />}
    </Suspense>
    {nestedNode && creator && <Dialog opened size="calc(100vw - 80px)" title={`${nestedNode.mode === 'preview' ? '查看内部逻辑' : '第二层语义'} · ${nestedNode.node.label}`} onClose={() => setNestedNode(null)} aria-label="子卡带语义层">
      <section className="nested-cartridge-shell"><header><span><Puzzle />母节点</span><strong>{nestedNode.node.label}</strong><small>{nestedNode.node.resolution?.capability?.label || '待补齐子卡带'}</small></header><iframe title={`${nestedNode.node.label} 第二层语义`} src={capabilityWorkshopUrl(creator, nestedNode.node)} /></section>
    </Dialog>}
  </>
}
