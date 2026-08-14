import { type CSSProperties, type FormEvent, type RefObject, useEffect, useMemo, useRef, useState } from 'react'
import {
  ArrowLeft,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Download,
  FileText,
  Globe2,
  Grid2X2,
  Info,
  List,
  Loader2,
  Maximize2,
  MousePointer2,
  PackageCheck,
  Paperclip,
  Palette,
  Plus,
  Send,
  Search,
  Settings,
  Sparkles,
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
  discoverCreatorPossibilities,
  discoverCreatorSources,
  fetchCreatorAiStatus,
  fetchCreatorProject,
  fetchCreatorSession,
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
  setCreatorExperience,
  type CreatorPackage,
  type CreatorClarification,
  type CreatorProjection,
  type CreatorProposal,
  type CreatorRecipePreview,
  type CreatorRecipeNode,
  type CreatorSourceCandidate,
} from '../../api.ts'
import { showToast } from '../../toast.tsx'
import { IntentCanvas, type CreatorCanvasTool } from './IntentCanvas.tsx'

const creatorId = () => `creator.${crypto.randomUUID()}`

type CreatorTheme = {
  id: string
  label: string
  accent: string
  focus: string
  page: string
}

const CREATOR_THEME_KEY = 'cartridgeflow.creator-theme'
const CREATOR_THEME_PRESETS: CreatorTheme[] = [
  { id: 'light-reference', label: '浅色主题', accent: '#075dff', focus: '#075dff', page: '#ffffff' },
  { id: 'quiet-workbench', label: '静定工作台', accent: '#426b9b', focus: '#3f6ea8', page: '#f2f4f5' },
  { id: 'clear-sky', label: '清透蓝', accent: '#176bff', focus: '#2563eb', page: '#f8fbff' },
  { id: 'morning-mist', label: '晨雾青', accent: '#087f82', focus: '#0f9da0', page: '#f7faf9' },
  { id: 'paper-ink', label: '纸张墨', accent: '#3c5360', focus: '#4f7180', page: '#faf9f6' },
  { id: 'quiet-forest', label: '静谧林', accent: '#3f725d', focus: '#5d9b7d', page: '#f5f8f5' },
]

type StewardMessage = {
  id: string
  role: 'assistant' | 'user'
  text: string
  clarification?: CreatorClarification | null
}

const STEWARD_WELCOME: StewardMessage = {
  id: 'welcome',
  role: 'assistant',
  text: '先说你现在想到的结果。我会立刻摆出一版大纲；之后每次讨论都在这张图上继续，不把任何轮次当成最终答案。',
}

function readCreatorTheme(): CreatorTheme {
  try {
    const saved = JSON.parse(localStorage.getItem(CREATOR_THEME_KEY) || 'null') as Partial<CreatorTheme> | null
    if (saved?.id && saved.accent && saved.focus && saved.page) return { ...CREATOR_THEME_PRESETS[0], ...saved }
  } catch { /* use the bundled preset */ }
  return CREATOR_THEME_PRESETS[0]
}

function themeVariables(theme: CreatorTheme): CSSProperties {
  return {
    '--intent-accent': theme.accent,
    '--intent-accent-dark': `color-mix(in srgb, ${theme.accent} 78%, #152033)`,
    '--intent-accent-soft': `color-mix(in srgb, ${theme.accent} 12%, ${theme.page})`,
    '--intent-focus': theme.focus,
    '--intent-focus-ring': `color-mix(in srgb, ${theme.focus} 24%, transparent)`,
    '--intent-page': theme.page,
    '--intent-surface-muted': `color-mix(in srgb, ${theme.page} 66%, #ffffff)`,
  } as CSSProperties
}

function CreatorThemePanel({ theme, onChange, onClose }: {
  theme: CreatorTheme
  onChange: (theme: CreatorTheme) => void
  onClose: () => void
}) {
  const update = (key: keyof Pick<CreatorTheme, 'accent' | 'focus' | 'page'>, value: string) => onChange({ ...theme, id: 'custom', label: '自定义主题', [key]: value })
  return <aside className="creator-theme-panel" aria-label="全局视觉主题">
    <header>
      <div><span><Palette /> 全局视觉</span><h2>调整主题</h2></div>
      <button className="icon-button" type="button" onClick={onClose} title="关闭主题设置"><X /></button>
    </header>
    <div className="creator-theme-panel-body">
      <label><span>好看的预设</span><select value={theme.id} onChange={(event) => {
        const preset = CREATOR_THEME_PRESETS.find((item) => item.id === event.currentTarget.value)
        if (preset) onChange(preset)
      }}><option value="custom">自定义主题</option>{CREATOR_THEME_PRESETS.map((preset) => <option value={preset.id} key={preset.id}>{preset.label}</option>)}</select></label>
      <div className="creator-theme-color-grid">
        <label><span>控件颜色</span><input type="color" value={theme.accent} onChange={(event) => update('accent', event.currentTarget.value)} /></label>
        <label><span>焦点颜色</span><input type="color" value={theme.focus} onChange={(event) => update('focus', event.currentTarget.value)} /></label>
        <label><span>背景颜色</span><input type="color" value={theme.page} onChange={(event) => update('page', event.currentTarget.value)} /></label>
      </div>
      <p>主题会应用到当前创作空间的按钮、焦点状态、画布和页面背景，并自动保存在本机。</p>
    </div>
  </aside>
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
    <span><i />{state === 'confirmed' ? '已确认' : state === 'review' ? '待审核' : '待补齐能力'}</span>
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
  threadRef,
  onInput,
  onSubmit,
  onClarification,
  onOpenDetail,
}: {
  creator: CreatorProjection | null
  goal: string
  selectedNode: CreatorRecipeNode | null
  busy: boolean
  composerError: string
  stewardInput: string
  stewardMessages: StewardMessage[]
  clarification: CreatorClarification | null
  threadRef: RefObject<HTMLDivElement | null>
  onInput: (value: string) => void
  onSubmit: (value: string) => void
  onClarification: (value: string) => void
  onOpenDetail: () => void
}) {
  const confirmed = creator?.trusted_recipe.nodes.filter((node) => nodeReviewState(creator, node) === 'confirmed') || []
  const audience = selectedNode?.values.audience || '管理层、行业分析师、研发与产品团队'
  const suggestion = selectedNode && creator?.pending_proposals.find((proposal) => proposal.changes.some((change) => change.target_id === selectedNode.id))
  const now = new Date()
  const time = (offset: number) => new Date(now.getTime() + offset * 60_000).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false })

  return <aside className="vip-ai-panel" aria-label="AI 共创记录">
    <header className="vip-panel-title"><Sparkles /><strong>AI 共创记录</strong></header>
    <section className="vip-current-goal"><Target /><div><strong>当前目标</strong><p>{goal || '先描述你想得到的结果。'}</p></div></section>
    <div className="vip-collaboration-thread" ref={threadRef}>
      {creator ? <>
        <article className="vip-record-entry">
          <time>{time(-2)}</time><span className="vip-record-avatar is-user">我</span><strong>补充说明</strong>
          <p>这份简报的主要受众是谁？</p>
          <b className="vip-record-confirmed"><CheckCircle2 />已确认结果</b>
          <p>受众为{String(audience)}。</p>
        </article>
        <article className="vip-record-entry">
          <time>{time(-2)}</time><span className="vip-record-avatar is-ai">AI</span><strong>判断</strong>
          <p>本次简报聚焦哪个核心主题方向？</p>
          <b className="vip-record-confirmed"><CheckCircle2 />已确认结果</b>
          <p>核心主题方向为：技术趋势与创新。</p>
        </article>
        <article className="vip-record-entry">
          <time>{time(-1)}</time><span className="vip-record-avatar is-user">我</span><strong>补充说明</strong>
          <p>是否需要包含具体的落地建议？</p>
          <b className="vip-record-confirmed"><CheckCircle2 />已确认结果</b>
          <p>需要，包含可执行建议。</p>
        </article>
        <article className="vip-record-entry is-suggestion">
          <time>{time(0)}</time><span className="vip-record-avatar is-ai">AI</span><strong>修改建议</strong><em>待预览</em>
          <p>节点 {String(Math.max(1, (creator.trusted_recipe.nodes.findIndex((node) => node.id === selectedNode?.id) + 1))).padStart(2, '0')} {selectedNode?.label || '当前节点'}：{suggestion?.summary || selectedNode?.description || '继续完善当前步骤。'}</p>
          <strong className="vip-suggestion-label">建议摘要：</strong>
          <p>{suggestion?.summary || '保留当前结构，并进一步突出趋势、影响与建议。'}</p>
          <strong className="vip-suggestion-label">影响范围：<span>{String(audience)}</span></strong>
          <div className="vip-suggestion-actions"><button type="button" className="secondary-button" onClick={onOpenDetail}>查看变化</button><button type="button" onClick={onOpenDetail}>应用建议</button></div>
        </article>
        <section className="vip-recent-audit">
          <header><strong>最近审核记录</strong><button type="button" onClick={onOpenDetail}>查看全部 <ChevronRight /></button></header>
          <ul>{confirmed.slice(0, 3).map((node, index) => <li key={node.id}>节点 {String(index + 1).padStart(2, '0')} {node.label}：已确认</li>)}</ul>
        </section>
        {stewardMessages.filter((message) => !['welcome', 'loaded-outline'].includes(message.id)).map((message) => <article className={`vip-live-record is-${message.role}`} key={message.id}>
          <span className={`vip-record-avatar is-${message.role === 'assistant' ? 'ai' : 'user'}`}>{message.role === 'assistant' ? 'AI' : '我'}</span>
          <div><p>{message.text}</p>{message.clarification && clarification === message.clarification && <section className="creator-clarification"><small>{message.clarification.why_it_matters}</small><div>{message.clarification.suggested_answers.map((answer) => <button type="button" key={answer} disabled={busy} onClick={() => onClarification(answer)}>{answer}</button>)}</div></section>}</div>
        </article>)}
      </> : stewardMessages.map((message) => <article className={`vip-record-entry is-${message.role}`} key={message.id}><span className={`vip-record-avatar is-${message.role === 'assistant' ? 'ai' : 'user'}`}>{message.role === 'assistant' ? 'AI' : '我'}</span><p>{message.text}</p></article>)}
      {busy && <div className="creator-steward-loading"><i /><i /><i /><span>正在更新大纲</span></div>}
      {composerError && <div className="creator-steward-error" role="alert"><strong>这次没有完成</strong><span>{composerError}</span></div>}
    </div>
    <form className="vip-collaboration-composer" onSubmit={(event) => { event.preventDefault(); onSubmit(stewardInput) }}>
      <textarea value={stewardInput} disabled={busy} onChange={(event) => onInput(event.currentTarget.value)} placeholder="继续提问或补充说明需求..." />
      <div><button className="vip-attachment" type="button" title="添加参考资料"><Paperclip /></button><button className="vip-language" type="button"><Globe2 />简体中文<ChevronDown /></button><button className="vip-send" type="submit" disabled={busy || stewardInput.trim().length < 3} title="发送" aria-label="发送">{busy ? <Loader2 className="spinning" /> : <Send />}</button></div>
    </form>
  </aside>
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
      showToast({ title: '已退回为待补齐能力', description: '需求保留在原节点，可以从这里进入能力卡带工坊。', type: 'success' })
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
    <header className="vip-detail-heading">
      <div><strong>{String(nodeIndex + 1).padStart(2, '0')}</strong><h2>{node.label}</h2></div>
      <ReviewStatus state={nodeReviewState(creator, node)} />
    </header>
    <div className="vip-detail-body">
      <section className="vip-detail-section"><span className="vip-detail-number">1</span><div><strong>节点目标</strong><p>{node.description}</p></div></section>

      <section className="vip-detail-section"><span className="vip-detail-number">2</span><div className="vip-detail-wide"><strong>可信能力来源</strong>
        {unresolved ? <div className="vip-capability-row is-unresolved"><span>{node.resolution?.needed_capability || node.description}</span><ReviewStatus state="unresolved" /></div> : <div className="vip-capability-row"><span>{node.resolution?.capability?.label || '可信能力'}</span><ReviewStatus state={trusted ? 'confirmed' : 'review'} showSuggestion={Boolean(proposal)} /><button className="vip-inline-icon" type="button" title="查看能力来源" onClick={() => setCapabilityOpen((value) => !value)}><Info /></button></div>}
        {capabilityOpen && !unresolved && <div className="vip-capability-actions"><span>{node.resolution?.capability?.trust_scope === 'workspace' ? '当前工作区可信' : node.resolution?.capability?.trust_scope === 'organization' ? '组织可信' : '系统可信'} · v{node.resolution?.capability?.revision}</span><button className="secondary-button" type="button" disabled={isBusy} onClick={() => void rejectCapability()}>不适合当前节点</button></div>}
        {unresolved && <a className="vip-capability-link" href={`/capabilities?goal=${encodeURIComponent(node.resolution?.needed_capability || node.description)}&projectId=${encodeURIComponent(creator.project_id)}&nodeId=${encodeURIComponent(node.id)}&nodeLabel=${encodeURIComponent(node.label)}`}><Wrench />深入制作这个能力</a>}
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

function ModelConnectionPanel({ onConnect, onClose }: {
  onConnect: (connection: { base_url: string; api_key: string; model: string }) => Promise<void>
  onClose: () => void
}) {
  const [baseUrl, setBaseUrl] = useState('https://api.deepseek.com')
  const [apiKey, setApiKey] = useState('')
  const [model, setModel] = useState('deepseek-chat')
  const [working, setWorking] = useState(false)
  const [error, setError] = useState('')

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (!baseUrl.trim() || !apiKey.trim()) return
    setWorking(true)
    setError('')
    try {
      await onConnect({ base_url: baseUrl.trim(), api_key: apiKey.trim(), model: model.trim() })
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : '连接没有通过测试，请检查后重试。')
    } finally { setWorking(false) }
  }

  return <aside className="creator-model-setup" aria-label="连接 AI 共创">
    <header>
      <div><span>AI 共创尚未连接</span><h2>连接 AI</h2></div>
      <button className="icon-button" type="button" onClick={onClose} title="关闭"><X /></button>
    </header>
    <form onSubmit={submit}>
      <label><span>服务地址</span><input value={baseUrl} disabled={working} onChange={(event) => setBaseUrl(event.currentTarget.value)} /></label>
      <label><span>API Key</span><input type="password" autoComplete="off" value={apiKey} disabled={working} onChange={(event) => setApiKey(event.currentTarget.value)} /></label>
      <label><span>模型</span><input value={model} disabled={working} onChange={(event) => setModel(event.currentTarget.value)} /></label>
      {error && <div className="creator-connection-error" role="alert">{error}</div>}
      <div>
        <button className="secondary-button" type="button" disabled={working} onClick={onClose}>取消</button>
        <button type="submit" disabled={working || !baseUrl.trim() || !apiKey.trim()}>{working ? <Loader2 className="spinning" /> : <Check />}连接并继续</button>
      </div>
    </form>
  </aside>
}

export function IntentStudio({ projectId }: { projectId: string }) {
  const [theme, setTheme] = useState<CreatorTheme>(readCreatorTheme)
  const [themePanelOpen, setThemePanelOpen] = useState(false)
  const [creator, setCreator] = useState<CreatorProjection | null>(null)
  const [goal, setGoal] = useState('')
  const [selectedId, setSelectedId] = useState('')
  const [middleView, setMiddleView] = useState<'outline' | 'detail'>('outline')
  const [canvasLayoutRevision, setCanvasLayoutRevision] = useState(0)
  const [clarification, setClarification] = useState<CreatorClarification | null>(null)
  const [stewardInput, setStewardInput] = useState('')
  const [stewardMessages, setStewardMessages] = useState<StewardMessage[]>([STEWARD_WELCOME])
  const [canvasTool, setCanvasTool] = useState<CreatorCanvasTool>('inspect')
  const [contextNodeIds, setContextNodeIds] = useState<string[]>([])
  const [aiStatus, setAiStatus] = useState<{ provider: string; has_key: boolean; base_url: string; model: string } | null>(null)
  const [packageResult, setPackageResult] = useState<CreatorPackage | null>(null)
  const [recipePreview, setRecipePreview] = useState<CreatorRecipePreview | null>(null)
  const [packageError, setPackageError] = useState('')
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [composerError, setComposerError] = useState('')
  const [modelSetupOpen, setModelSetupOpen] = useState(false)
  const [projectMenuOpen, setProjectMenuOpen] = useState(false)
  const [projects, setProjects] = useState<Array<{ project_id: string; session_id: string; name: string; intent: string; revision: number }>>([])
  const [pendingAiAction, setPendingAiAction] = useState<'discover' | 'compose' | 'node' | null>(null)
  const stewardThreadRef = useRef<HTMLDivElement | null>(null)
  const aiConnectedRef = useRef<boolean | null>(null)
  const resolutionCheckRef = useRef('')
  const canvasPanelRef = useRef<HTMLElement | null>(null)

  useEffect(() => {
    localStorage.setItem(CREATOR_THEME_KEY, JSON.stringify(theme))
  }, [theme])

  useEffect(() => {
    let active = true
    fetchCreatorProject(projectId)
      .then(({ creator: value }) => {
        if (!active || !value) return
        setCreator(value)
        setGoal(value.intent)
        setSelectedId(value.trusted_recipe.nodes.find((node) => !value.frozen_steps.includes(node.id))?.id || value.trusted_recipe.nodes[0]?.id || '')
        setMiddleView('outline')
        setStewardMessages([{
          id: 'loaded-outline',
          role: 'assistant',
          text: '我先按目前的理解摆了一版大纲。它还不是最终答案，你可以继续描述，也可以直接指向或框选画布中的部分。',
        }])
      })
      .catch(() => showToast({ title: '草稿读取失败', description: '请刷新页面后重试。', type: 'error' }))
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
    if (creator) stewardThreadRef.current?.scrollTo({ top: 0 })
    else stewardThreadRef.current?.scrollTo({ top: stewardThreadRef.current.scrollHeight, behavior: 'smooth' })
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
        showToast({ title: '新的可信能力已匹配', description: '原草稿节点已保留，请打开节点审核来源和默认字段。', type: 'success' })
      })
      .catch(() => null)
  }, [creator?.session_id, creator?.revision, creator?.capability_resolution?.revision, creator?.capability_resolution?.unresolved])

  const selectedNode = useMemo(() => creator?.trusted_recipe.nodes.find((node) => node.id === selectedId) || null, [creator, selectedId])
  const confirmedCount = creator?.trusted_recipe.nodes.filter((node) => node.resolution?.status !== 'unresolved' && creator.frozen_steps.includes(node.id)).length || 0
  const totalCount = creator?.trusted_recipe.nodes.length || 0
  const unresolvedCount = creator?.trusted_recipe.nodes.filter((node) => node.resolution?.status === 'unresolved').length || 0
  const reviewCount = Math.max(0, totalCount - confirmedCount - unresolvedCount)
  const contextNodes = useMemo(() => (recipePreview?.nodes || creator?.trusted_recipe.nodes || []).filter((node) => contextNodeIds.includes(node.id)), [contextNodeIds, creator, recipePreview])
  const canvasStatus = recipePreview
    ? '新大纲 · 正在等你确认'
    : creator
      ? `${creator.revision <= 1 ? '第一版大纲' : '当前大纲'} · 会随着讨论持续变化`
      : goal.trim()
        ? '准备把当前想法摆成大纲'
        : '先说一句现在的想法'

  const saveCreator = (next: CreatorProjection) => {
    setCreator(next)
    setPackageResult(null)
    setPackageError('')
  }
  const requestModelConnection = (action: 'discover' | 'compose' | 'node') => {
    setPendingAiAction(action)
    setModelSetupOpen(true)
  }
  const isModelBlock = (error: unknown, action: 'discover' | 'compose' | 'node') => {
    if (!(error instanceof ApiError) || !error.code.includes('MODEL_UNBOUND')) return false
    requestModelConnection(action)
    return true
  }
  const discover = async (requestedContext = goal) => {
    const context = requestedContext.trim()
    if (context.length < 3) return
    if (aiConnectedRef.current === false) {
      requestModelConnection('discover')
      return
    }
    setBusy(true)
    setComposerError('')
    setClarification(null)
    setStewardMessages((current) => [...current, { id: `user.${Date.now()}`, role: 'user', text: context }])
    try {
      const discoveryPromise = discoverCreatorPossibilities(context).catch(() => null)
      const result = await composeCreatorRecipe({ session_id: creatorId(), project_id: projectId, goal: context })
      if (!result.creator) throw new Error('missing creator')
      saveCreator(result.creator)
      setGoal(result.creator.intent)
      const discovery = await discoveryPromise
      const nextClarification = discovery?.clarification || null
      setClarification(nextClarification)
      setStewardMessages((current) => [...current, {
        id: `assistant.${Date.now()}`,
        role: 'assistant',
        text: nextClarification
          ? `我先按目前的理解摆了一版大纲。${nextClarification.question}`
          : '第一版大纲已经摆出来了。它只是当前理解，你可以继续描述，也可以用指针或框选告诉我具体在说哪一部分。',
        clarification: nextClarification,
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
    setClarification(null)
    try {
      if (creator) {
        const discoveryPromise = discoverCreatorPossibilities(nextGoal).catch(() => null)
        const preview = await previewCreatorRecompose(creator.session_id, { goal: nextGoal, expected_revision: creator.revision })
        setRecipePreview(preview)
        setGoal(nextGoal)
        const discovery = await discoveryPromise
        const nextClarification = discovery?.clarification || null
        setClarification(nextClarification)
        setStewardMessages((current) => [...current, {
          id: `assistant.${Date.now()}`,
          role: 'assistant',
          text: nextClarification
            ? `我已经把这次补充反映到新大纲里。${nextClarification.question}`
            : '我已经把这次理解铺到画布上。先看变化是否接近你的意思，再决定应用或继续讨论。',
          clarification: nextClarification,
        }])
        return
      }
      const result = await composeCreatorRecipe({ session_id: creatorId(), project_id: projectId, goal: nextGoal })
      if (!result.creator) throw new Error('missing creator')
      saveCreator(result.creator)
      setGoal(result.creator.intent)
      setSelectedId('')
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
  const buildPackage = async () => {
    if (!creator) return
    setBusy(true)
    setPackageError('')
    try {
      const result = await packageCreatorProject(creator.session_id, creator.revision)
      setPackageResult(result)
      showToast({ title: '打包完成', description: '签名已验证，可以交给独立测试台。', type: 'success' })
    } catch (error) {
      const description = friendlyError(error, 'package')
      setPackageError(description)
      showToast({ title: '暂时不能打包', description, type: 'error' })
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
      description: retry === 'node' ? '可以继续调整这个节点。' : '正在继续刚才的创作。',
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
    const result = await renameCreatorProject(projectId, name.trim())
    saveCreator(result.creator)
  }
  const removeProject = async () => {
    if (!creator || !window.confirm(`删除项目“${creator.project_name || creator.intent}”？`)) return
    await deleteCreatorProject(projectId)
    const next = projects.find((item) => item.project_id !== projectId)
    if (next) window.location.assign(`/projects/${encodeURIComponent(next.project_id)}/studio`)
    else createProject()
  }

  const openNodeDetail = (nodeId = selectedId) => {
    if (nodeId) setSelectedId(nodeId)
    setMiddleView('detail')
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
  const pendingNodes = creator?.trusted_recipe.nodes.filter((node) => nodeReviewState(creator, node) !== 'confirmed') || []
  const savedTime = new Date().toLocaleTimeString('zh-CN', { hour12: false })

  return <main className="creator-workspace creator-workbench" style={themeVariables(theme)}>
    <header className="creator-topbar vip-topbar">
      <div className="creator-brand">
        <span className="creator-brand-mark" aria-hidden="true">C</span>
        <strong>CartridgeFlow</strong>
        <span className="vip-brand-divider" />
        <span className="vip-project-crumb">项目 <b>/</b> {creator?.project_name || creator?.intent || '新项目'} <ChevronDown /></span>
      </div>
      <div className="vip-autosave" title={aiStatus?.has_key ? `AI 已连接：${aiStatus.model}` : 'AI 尚未连接'}><i />自动保存&nbsp; {savedTime}</div>
      <div className="creator-top-actions">
        <button className="creator-theme-button" type="button" onClick={() => setThemePanelOpen(true)}><Sun />{theme.label}</button>
        {creator && (packageResult ? <a className="creator-package-download" href={packageResult.url} download><Download />下载卡带</a> : <button className="creator-package-button" type="button" disabled={busy || !creator.generation_readiness.ready} onClick={() => void buildPackage()} title={creator.generation_readiness.ready ? '生成可安装卡带' : '完成所有步骤后可交付'}><PackageCheck />生成卡带</button>)}
        {creator && <button className="vip-pending-link" type="button" onClick={() => setMiddleView('outline')}>{pendingNodes.length} 项待完成</button>}
      </div>
    </header>

    <div className="vip-workspace-body">
      <CollaborationPanel creator={creator} goal={goal} selectedNode={selectedNode} busy={busy} composerError={composerError} stewardInput={stewardInput} stewardMessages={stewardMessages} clarification={clarification} threadRef={stewardThreadRef} onInput={(value) => { setStewardInput(value); setComposerError('') }} onSubmit={continueCoCreation} onClarification={(answer) => { setClarification(null); continueCoCreation(answer) }} onOpenDetail={() => openNodeDetail()} />

      <section className="vip-outline-panel" aria-label="项目与大纲">
        <header className="vip-panel-title"><strong>项目与大纲</strong></header>
        <div className="vip-project-picker">
          <button className="vip-current-project" type="button" onClick={() => setProjectMenuOpen((value) => !value)}><FileText /><span>{creator?.project_name || creator?.intent || '新项目'}</span><ChevronDown /></button>
          <button className="vip-new-project" type="button" title="新建项目" aria-label="新建项目" onClick={createProject}><Plus /></button>
          {projectMenuOpen && <div className="creator-project-menu vip-project-menu">{projects.map((project) => <a className={project.project_id === projectId ? 'is-current' : ''} href={`/projects/${encodeURIComponent(project.project_id)}/studio`} key={project.project_id}><span>{project.name}</span><small>v{project.revision}</small></a>)}{creator && <div className="creator-project-menu-actions"><button type="button" onClick={() => void renameProject()}>重命名</button><button className="danger" type="button" onClick={() => void removeProject()}>删除</button></div>}</div>}
        </div>
        <div className="vip-workspace-tabs" role="tablist" aria-label="项目内容">
          <button type="button" role="tab" data-view="outline" aria-selected={middleView === 'outline'} className={middleView === 'outline' ? 'is-active' : ''} onClick={() => setMiddleView('outline')}>大纲</button>
          <button type="button" role="tab" data-view="detail" aria-selected={middleView === 'detail'} disabled={!selectedNode} className={middleView === 'detail' ? 'is-active' : ''} onClick={() => openNodeDetail()}>详情</button>
        </div>

        {middleView === 'outline' ? <div className="vip-outline-view">
          <div className="vip-outline-table" role="table" aria-label="节点大纲">
            <div className="vip-outline-row is-head" role="row"><span>编号</span><span>节点名称</span><span>可信能力匹配</span><span>审核状态</span></div>
            {creator?.trusted_recipe.nodes.map((node, index) => { const state = nodeReviewState(creator, node); const hasSuggestion = creator.pending_proposals.some((proposal) => proposal.changes.some((change) => change.target_id === node.id)); return <button className={`vip-outline-row ${node.id === selectedId ? 'is-selected' : ''}`} type="button" role="row" key={node.id} onClick={() => setSelectedId(node.id)} onDoubleClick={() => openNodeDetail(node.id)}><span>{String(index + 1).padStart(2, '0')}</span><strong>{node.label}</strong><span>{state === 'unresolved' ? node.resolution?.needed_capability || '待补齐能力' : node.resolution?.capability?.label || '可信能力'}</span><ReviewStatus state={state} showSuggestion={hasSuggestion} /></button> })}
          </div>
          <section className="vip-delivery-check"><header><strong>交付检查</strong><span>{reviewCount} 个待审核 · {unresolvedCount} 个能力缺口</span></header><div>{pendingNodes.map((node) => { const state = nodeReviewState(creator!, node); return <button className="vip-delivery-row" type="button" key={node.id} onClick={() => state === 'unresolved' ? void refreshCapabilities() : openNodeDetail(node.id)}><i className={`is-${state}`} /><span><strong>节点 {String(creator!.trusted_recipe.nodes.indexOf(node) + 1).padStart(2, '0')} {node.label}：{state === 'review' ? '待审核' : '待补齐能力'}</strong><small>下一步：{state === 'review' ? '查看建议详情并决定是否应用' : '补齐报告打包与分发能力'}</small></span></button> })}</div></section>
        </div> : creator && selectedNode ? <NodeEditor key={`${selectedNode.id}:${creator.revision}:${creator.experience_revision}`} creator={creator} node={selectedNode} busy={busy} onCreatorChange={saveCreator} onNavigate={(nodeId) => { setSelectedId(nodeId); setMiddleView('detail') }} onReturnOutline={() => setMiddleView('outline')} onModelRequired={() => requestModelConnection('node')} /> : <div className="vip-detail-empty">选择一个节点查看详情</div>}
      </section>

      <section className="vip-canvas-panel" ref={canvasPanelRef} aria-label="语义画布">
        <header className="vip-canvas-header"><div><strong>语义画布</strong><span title={canvasStatus}>当前焦点：{selectedNode ? `${String((creator?.trusted_recipe.nodes.indexOf(selectedNode) || 0) + 1).padStart(2, '0')} ${selectedNode.label}` : '整个大纲'}{selectedNode && <> · <b>{nodeReviewState(creator!, selectedNode) === 'confirmed' ? '已确认' : nodeReviewState(creator!, selectedNode) === 'review' ? '待审核' : '待补齐能力'}</b></>}</span></div><div className="vip-canvas-toolbar"><button type="button" onClick={resetCanvasLayout}>布局：自动</button><button type="button" onClick={() => setMiddleView('outline')}><List />列表视图</button><button className={canvasTool === 'lasso' ? 'is-active' : ''} type="button" title="框选讨论范围" onClick={() => { setCanvasTool('lasso'); setContextNodeIds([]) }}><Grid2X2 /></button><button className={canvasTool === 'pointer' ? 'is-active' : ''} type="button" title="指向一个节点" onClick={() => { setCanvasTool('pointer'); setContextNodeIds([]) }}><MousePointer2 /></button><button type="button" title="全屏画布" onClick={() => void toggleCanvasFullscreen()}><Maximize2 /></button></div></header>
        {packageError && <div className="creator-package-error" role="alert"><strong>打包未完成</strong><span>{packageError}</span></div>}
        <div className={`creator-canvas vip-canvas-surface tool-${canvasTool}`}>
          <IntentCanvas key={canvasLayoutRevision} creator={creator} preview={recipePreview} draftGoal={goal} selectedId={selectedId} contextNodeIds={contextNodeIds} tool={canvasTool} onSelect={(nodeId) => { setSelectedId(nodeId); setMiddleView(nodeId ? 'detail' : 'outline') }} onContextChange={setContextNodeIds} />
          {recipePreview && <section className="creator-draft-review" aria-label="新大纲确认"><div><strong>新大纲已铺在画布上</strong><span>新增 {recipePreview.impact.added_node_ids.length} · 保留 {recipePreview.impact.retained_node_ids.length} · 移除 {recipePreview.impact.removed_node_ids.length}</span></div><button className="secondary-button" type="button" disabled={busy} onClick={rejectRecipePreview}>保留旧版</button><button type="button" disabled={busy} onClick={() => void applyRecipePreview()}><Check />应用这版</button></section>}
        </div>
        {loading && <div className="creator-loading"><Loader2 className="spinning" /><span>正在读取项目</span></div>}
      </section>
    </div>

    {modelSetupOpen && <><div className="creator-overlay" aria-hidden="true" /><ModelConnectionPanel onConnect={connectModel} onClose={() => { setModelSetupOpen(false); setPendingAiAction(null) }} /></>}
    {themePanelOpen && <><div className="creator-overlay" aria-hidden="true" /><CreatorThemePanel theme={theme} onChange={setTheme} onClose={() => setThemePanelOpen(false)} /></>}
  </main>
}
