import { type CSSProperties, type FormEvent, useEffect, useMemo, useRef, useState } from 'react'
import {
  Bot,
  BarChart3,
  Braces,
  Check,
  CheckCircle2,
  ChevronDown,
  Download,
  FileText,
  FolderOpen,
  Globe2,
  Lightbulb,
  Loader2,
  PackageCheck,
  Paperclip,
  Palette,
  PenLine,
  Plus,
  Redo2,
  RefreshCw,
  Send,
  Search,
  Settings,
  ShieldCheck,
  Sparkles,
  Target,
  Users,
  Undo2,
  Workflow,
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
  type CreatorPossibility,
  type CreatorProjection,
  type CreatorProposal,
  type CreatorRecipePreview,
  type CreatorRecipeNode,
  type CreatorSourceCandidate,
} from '../../api.ts'
import { showToast } from '../../toast.tsx'
import { IntentCanvas } from './IntentCanvas.tsx'

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
  { id: 'morning-mist', label: '晨雾青', accent: '#087f82', focus: '#0f9da0', page: '#f7faf9' },
  { id: 'paper-ink', label: '纸张墨', accent: '#3c5360', focus: '#4f7180', page: '#faf9f6' },
  { id: 'quiet-forest', label: '静谧林', accent: '#3f725d', focus: '#5d9b7d', page: '#f5f8f5' },
]

const CREATOR_RECENT_EXAMPLES = [
  { title: '整理本周 AI 行业动态', description: '生成中文简报', icon: FileText },
  { title: '分析竞品对手动态', description: '生成对比分析报告', icon: BarChart3 },
  { title: '撰写产品发布文案', description: '面向开发者的介绍', icon: PenLine },
  { title: '整理用户反馈要点', description: '生成洞察与建议', icon: Users },
  { title: '研究某个技术主题', description: '生成学习笔记', icon: FolderOpen },
]

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
    '--intent-accent-dark': `color-mix(in srgb, ${theme.accent} 78%, #12363a)`,
    '--intent-accent-soft': `color-mix(in srgb, ${theme.accent} 12%, ${theme.page})`,
    '--intent-focus': theme.focus,
    '--intent-focus-ring': `color-mix(in srgb, ${theme.focus} 30%, transparent)`,
    '--intent-page': theme.page,
    '--intent-surface-muted': `color-mix(in srgb, ${theme.page} 58%, #ffffff)`,
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

function NodeEditor({ creator, node, busy, onCreatorChange, onClose, onModelRequired }: {
  creator: CreatorProjection
  node: CreatorRecipeNode
  busy: boolean
  onCreatorChange: (creator: CreatorProjection) => void
  onClose: () => void
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
  const trusted = creator.frozen_steps.includes(node.id)
  const unresolved = node.resolution?.status === 'unresolved'
  const capabilityConfirmed = trusted && !unresolved
  const changed = JSON.stringify(values) !== JSON.stringify(node.values)
  const freezeRevision = creator.active_freezes.find((freeze) => freeze.steps.includes(node.id))?.freeze_revision
  const isBusy = busy || working

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

  return <aside className="creator-node-editor" aria-label={`调整 ${node.label}`}>
    <header>
      <div><span className={`creator-status-label ${trusted && !unresolved ? 'is-confirmed' : ''}`}>{unresolved ? <Wrench /> : trusted ? <CheckCircle2 /> : <ShieldCheck />}{unresolved ? '待补齐能力' : trusted ? '已确认' : '待审核'}</span><h2>{node.label}</h2><p>{node.description}</p></div>
      <button className="icon-button" type="button" onClick={onClose} title="关闭节点"><X /></button>
    </header>
    <div className="creator-node-editor-body">
      <section className="creator-node-goal"><header><Target /><strong>目标</strong></header><p>{node.description}</p></section>
      {unresolved && <section className="creator-capability-gap"><div><span>这个步骤需要一种新的做法</span><strong>{node.resolution?.needed_capability || node.description}</strong><p>你的原始目标会留在这里。进入下一层完成内部流程后，新能力会自动回到这个步骤。</p></div><a href={`/capabilities?goal=${encodeURIComponent(node.resolution?.needed_capability || node.description)}&projectId=${encodeURIComponent(creator.project_id)}&nodeId=${encodeURIComponent(node.id)}&nodeLabel=${encodeURIComponent(node.label)}`}><Wrench />深入制作这个能力</a></section>}
      {!unresolved && node.resolution?.capability && <section className="creator-capability-source"><ShieldCheck /><div><strong>{node.resolution.capability.label}</strong><span>{node.resolution.capability.trust_scope === 'workspace' ? '当前工作区可信' : node.resolution.capability.trust_scope === 'organization' ? '组织可信' : '系统可信'} · v{node.resolution.capability.revision}</span></div><button className="secondary-button" type="button" disabled={isBusy} onClick={() => void rejectCapability()}><X />不适合当前节点</button></section>}
      {!unresolved && <ExperienceEditor creator={creator} node={node} disabled={isBusy} onChange={onCreatorChange} onBusy={setWorking} />}
      {!proposal && <>
        <FieldEditor node={node} values={values} onChange={setValues} disabled={isBusy} />
        <details className="creator-source-discovery"><summary><Globe2 />查找并审核资料来源</summary>
          <div className="creator-source-query"><input value={sourceRequest} disabled={isBusy} onChange={(event) => setSourceRequest(event.currentTarget.value)} placeholder="例如：适合关注生成式 AI 产品发布的公开来源" /><button type="button" disabled={isBusy || sourceRequest.trim().length < 3} onClick={() => void discoverSources()}><Search />查找候选来源</button></div>
          {sourceCandidates.map((candidate) => { const inspection = sourceInspections[candidate.id]; return <article key={candidate.id}><div><strong>{candidate.name}</strong><a href={candidate.rss_url || candidate.remote_url} target="_blank" rel="noreferrer">{candidate.rss_url || candidate.remote_url}</a><p>{candidate.provides}</p><small>注意：{candidate.risk} · 审核：{candidate.review_focus}</small></div><div><button className="secondary-button" type="button" disabled={isBusy} onClick={() => void inspectSource(candidate)}><Globe2 />{inspection ? '重新检查' : '检查可达性'}</button><button type="button" disabled={isBusy || !inspection} onClick={() => void adoptSource(candidate)}><Check />采用来源</button></div>{inspection && <p className="creator-source-inspection"><b>{inspection.status}</b> · {inspection.content_type || '未知类型'} · {inspection.bytes} bytes<br />{inspection.sample}</p>}</article> })}
        </details>
        <button className="secondary-button" type="button" disabled={isBusy || !changed} onClick={() => void stage()}><Check />保存字段修改</button>
        <div className="creator-ai-refine">
          <label><span>继续和 AI 对齐这个节点</span><textarea value={prompt} disabled={isBusy || changed} onChange={(event) => setPrompt(event.currentTarget.value)} placeholder="例如：只保留中文来源，并按重要性排序" /></label>
          <button type="button" disabled={isBusy || changed || !prompt.trim()} onClick={() => void ask()}><Sparkles />生成调整建议</button>
        </div>
        <button className="confirm-button" type="button" disabled={isBusy || trusted || changed} onClick={() => void confirm()}><ShieldCheck />{unresolved ? trusted ? '需求已确认' : '确认这项需求' : capabilityConfirmed ? '节点已确认' : '确认这个节点'}</button>
      </>}
      {proposal && <section className="creator-review">
        <span>修改确认</span>
        <h3>{proposal.summary}</h3>
        <ProposalChanges node={node} proposal={proposal} />
        <p>{impact || '先检查这次修改的影响，再决定是否应用。'}</p>
        <div>
          <button className="secondary-button" type="button" disabled={isBusy} onClick={() => void reject()}>放弃</button>
          {!impact && <button type="button" disabled={isBusy} onClick={() => void preview()}>检查修改</button>}
          {impact && <button type="button" disabled={isBusy} onClick={() => void accept()}><Check />应用修改</button>}
        </div>
      </section>}
    </div>
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
  const [possibilities, setPossibilities] = useState<CreatorPossibility[]>([])
  const [clarification, setClarification] = useState<CreatorClarification | null>(null)
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
  const [workspaceMode, setWorkspaceMode] = useState<'discover' | 'compose'>('discover')
  const composerRef = useRef<HTMLTextAreaElement | null>(null)
  const aiConnectedRef = useRef<boolean | null>(null)
  const resolutionCheckRef = useRef('')

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
        setSelectedId(value.trusted_recipe.nodes.find((node) => node.resolution?.status === 'unresolved')?.id || value.trusted_recipe.nodes[0]?.id || '')
        setWorkspaceMode(value.trusted_recipe.nodes.length ? 'compose' : 'discover')
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
    setPossibilities([])
    setClarification(null)
    try {
      const result = await discoverCreatorPossibilities(context)
      setPossibilities(result.possibilities)
      setClarification(result.clarification)
    } catch (error) {
      if (isModelBlock(error, 'discover')) return
      const description = friendlyError(error, 'discover')
      setComposerError(description)
      showToast({ title: '暂时无法打开新方向', description, type: 'error' })
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
        return
      }
      const result = await composeCreatorRecipe({ session_id: creatorId(), project_id: projectId, goal: nextGoal })
      if (!result.creator) throw new Error('missing creator')
      saveCreator(result.creator)
      setGoal(result.creator.intent)
      setSelectedId('')
      showToast({ title: creator ? '整体草稿已更新' : '整体草稿已生成', description: '请逐个打开节点进行审核。', type: 'success' })
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
      setRecipePreview(null)
      showToast({ title: '整体草稿已更新', description: '请逐个打开节点继续审核。', type: 'success' })
    } catch (error) {
      showToast({ title: '预览已失效', description: friendlyError(error, 'compose'), type: 'error' })
    } finally { setBusy(false) }
  }
  const submit = (event: FormEvent) => {
    event.preventDefault()
    void compose(goal)
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

  return <main className="creator-workspace" style={themeVariables(theme)}>
    <header className={`creator-topbar is-${workspaceMode}`}>
      <div className="creator-brand">
        <span className="creator-brand-mark" aria-hidden="true"><Workflow /></span>
        <strong>CartridgeFlow</strong>
        <span>创作空间</span>
      </div>
      <nav className="creator-mode-switch" aria-label="创作进度">
        <button className={workspaceMode === 'discover' ? 'is-active' : ''} type="button" onClick={() => setWorkspaceMode('discover')}><span>1</span><Lightbulb />想法</button>
        <button className={workspaceMode === 'compose' ? 'is-active' : ''} type="button" onClick={() => setWorkspaceMode('compose')}><span>2</span><Workflow />方案</button>
        <button className={packageResult ? 'is-complete' : ''} type="button" disabled={!creator?.generation_readiness.ready} onClick={() => void buildPackage()}><span>3</span><PackageCheck />交付</button>
      </nav>
      <div className="creator-top-actions">
        <button className="creator-theme-button" type="button" onClick={() => setThemePanelOpen(true)}><Palette />主题</button>
        {workspaceMode === 'compose' && <>
          <span className="creator-saved"><CheckCircle2 />已自动保存</span>
          <button className="icon-button" type="button" title="当前没有可撤销的操作" disabled><Undo2 /></button>
          <button className="icon-button" type="button" title="当前没有可重做的操作" disabled><Redo2 /></button>
          {packageResult ? <a className="creator-package-download" href={packageResult.url} download><Download />下载卡带</a> : <button className="creator-package-button" type="button" disabled={busy || !creator?.generation_readiness.ready} onClick={() => void buildPackage()} title={creator?.generation_readiness.ready ? '生成可安装卡带' : '完成所有步骤后可交付'}><PackageCheck />生成卡带</button>}
        </>}
      </div>
    </header>

    <div className={`creator-shell is-${workspaceMode}`}>
      <aside className="creator-sidebar">
        <section className="creator-sidebar-section creator-project-section">
          <header><strong>项目</strong><button className="sidebar-icon-button" type="button" onClick={createProject}><Plus />新建项目</button></header>
          <button className="creator-current-project" type="button" onClick={() => setProjectMenuOpen((value) => !value)}><FileText /><span>{creator?.project_name || creator?.intent || '新项目'}</span><ChevronDown /></button>
          {projectMenuOpen && <div className="creator-project-menu">{projects.map((project) => <a className={project.project_id === projectId ? 'is-current' : ''} href={`/projects/${encodeURIComponent(project.project_id)}/studio`} key={project.project_id}><span>{project.name}</span><small>v{project.revision}</small></a>)}{creator && <div className="creator-project-menu-actions"><button type="button" onClick={() => void renameProject()}>重命名</button><button className="danger" type="button" onClick={() => void removeProject()}>删除</button></div>}</div>}
          <button className="creator-settings-link" type="button" disabled={!creator} onClick={() => void renameProject()}><Settings />项目设置</button>
        </section>

        <section className="creator-sidebar-section creator-outline">
          <header><strong>方案步骤</strong><span>{confirmedCount}/{totalCount || 0}</span></header>
          <div className="creator-outline-list">
            {creator?.trusted_recipe.nodes.map((node, index) => {
              const unresolved = node.resolution?.status === 'unresolved'
              const confirmed = !unresolved && creator.frozen_steps.includes(node.id)
              return <button className={node.id === selectedId ? 'is-selected' : ''} type="button" key={node.id} onClick={() => { setWorkspaceMode('compose'); setSelectedId(node.id) }}>
                <span className="outline-index">{String(index + 1).padStart(2, '0')}</span>
                <span className="outline-label">{node.label}</span>
                <span className={`outline-state ${unresolved ? 'is-unresolved' : confirmed ? 'is-confirmed' : 'is-review'}`}>{unresolved ? <><Wrench />待补齐</> : confirmed ? <><Check />已确认</> : <><span className="state-ring" />待审核</>}</span>
              </button>
            }) || <p className="creator-empty-copy">生成草稿后会在这里显示步骤。</p>}
          </div>
        </section>

        <section className="creator-sidebar-section creator-progress">
          <header><strong>完成情况</strong><ChevronDown /></header>
          <div className="creator-progress-summary">
            <div className="creator-progress-ring" style={{ '--progress': `${totalCount ? Math.round((confirmedCount / totalCount) * 100) : 0}%` } as CSSProperties}><strong>{confirmedCount}/{totalCount || 0}</strong><small>已完成</small></div>
            <div className="creator-progress-legend"><span><i className="confirmed" />已确认 <b>{confirmedCount}</b></span><span><i className="review" />待审核 <b>{reviewCount}</b></span><span><i className="unresolved" />待补齐能力 <b>{unresolvedCount}</b></span></div>
          </div>
          {unresolvedCount > 0 && <button className="creator-refresh-capabilities" type="button" disabled={busy} onClick={() => void refreshCapabilities()}><RefreshCw />重新检查可信能力</button>}
          <p>所有步骤确认后即可生成可安装卡带</p>
        </section>
      </aside>

      <section className={`creator-stage is-${workspaceMode}`} aria-label={workspaceMode === 'compose' ? '项目链路图' : '方向探索'}>
        {packageError && <div className="creator-package-error" role="alert"><strong>打包未完成</strong><span>{packageError}</span></div>}
        {workspaceMode === 'compose' ? <>
          <div className="creator-canvas"><IntentCanvas creator={creator} selectedId={selectedId} onSelect={setSelectedId} /></div>
          <form className="creator-composer" onSubmit={submit}>
            <div className="creator-composer-heading"><div><Bot /><strong>调整整个方案</strong></div><button className="creator-variable-button" type="button" title="插入项目变量"><Braces />变量</button></div>
            {composerError && <div className="creator-composer-error" role="alert"><strong>这次没有完成编排</strong><span>{composerError} 你的想法已经保留，可以直接重试。</span></div>}
            <label className="creator-goal-input"><textarea ref={composerRef} value={goal} disabled={busy} onChange={(event) => { setGoal(event.currentTarget.value); setComposerError('') }} placeholder="告诉 AI 你想增加、删除或调整什么" aria-label="整体调整要求" /></label>
            <div className="creator-composer-actions"><div><button className="icon-button" type="button" title="添加参考资料"><Paperclip /></button><button className="icon-button" type="button" title="让 AI 优化指令"><Sparkles /></button></div><button type="submit" disabled={busy || goal.trim().length < 3}>{busy ? <Loader2 className="spinning" /> : <Sparkles />}{creator ? '重新生成' : '生成方案'}</button></div>
          </form>
        </> : <section className="creator-discovery">
          <div className="creator-discovery-intro"><span><Lightbulb /></span><div><small>从一个想法开始</small><h1>你想让这张卡带帮你做什么？</h1><p>先说结果，不用考虑模型、工具或流程。AI 会先判断信息是否足够，必要时只追问一个关键问题。</p><div className="creator-ai-context"><span><Bot />{aiStatus?.has_key ? aiStatus.provider : '尚未连接 AI'}</span><span><Globe2 />简体中文输出</span></div></div></div>
          <form onSubmit={(event) => { event.preventDefault(); void discover() }}><textarea autoFocus value={goal} onChange={(event) => { setGoal(event.currentTarget.value); setComposerError(''); setClarification(null); setPossibilities([]) }} placeholder="例如：每天早上整理可信的 AI 行业动态，生成一份中文简报" /><button type="submit" disabled={busy || goal.trim().length < 3}>{busy ? <Loader2 className="spinning" /> : <Sparkles />}拆解想法</button></form>
          {composerError && <div className="creator-discovery-error" role="alert"><strong>这次没有生成方向建议</strong><span>{composerError} 你的输入已经保留，可以直接重试。</span></div>}
          {clarification && <section className="creator-clarification" aria-label="AI 需要确认"><header><span><Bot /></span><div><small>先确认一件事</small><h2>{clarification.question}</h2><p>{clarification.why_it_matters}</p></div></header><div>{clarification.suggested_answers.map((answer) => <button type="button" key={answer} disabled={busy} onClick={() => { const nextContext = `${goal.trim()}\n补充：${answer}`; setGoal(nextContext); setClarification(null); void discover(nextContext) }}>{answer}</button>)}</div><small>也可以直接修改上面的描述，再次拆解。</small></section>}
          {!clarification && <div className="creator-possibilities" aria-label="AI 方向建议">{possibilities.length ? possibilities.map((item) => {
            const subject = item.title.replace(/^(把|生成|形成)/, '')
            const recommended = subject.length >= 4 && goal.includes(subject)
            return <article className={recommended ? 'is-recommended' : ''} key={item.id}><span><Target /></span>{recommended && <em><CheckCircle2 />推荐</em>}<h3>{item.title}</h3><p>{item.outcome}</p><small>{item.why_it_fits}</small><button type="button" onClick={() => { setGoal(item.recipe.intent); setWorkspaceMode('compose'); void compose(item.recipe.intent) }}><Send />用这个方向生成方案</button></article>
          }) : <div className={`creator-discovery-empty ${goal.trim() ? 'has-goal' : ''}`}><Sparkles /><strong>AI 会先理解你的目标</strong><span>信息不足时先追问，足够时再给出可比较的方向。</span><div className="creator-recent-examples"><strong>最近的示例</strong><div>{CREATOR_RECENT_EXAMPLES.map(({ title, description, icon: Icon }) => <button type="button" key={title} onClick={() => setGoal(title)}><Icon /><span><strong>{title}</strong><small>{description}</small></span><Send /></button>)}</div></div></div>}</div>}
        </section>}
        {loading && <div className="creator-loading"><Loader2 className="spinning" /><span>正在读取项目</span></div>}
      </section>

      <aside className="creator-inspector">
        {workspaceMode === 'compose' && creator && selectedNode && !recipePreview ? <NodeEditor key={`${selectedNode.id}:${creator.revision}:${creator.experience_revision}`} creator={creator} node={selectedNode} busy={busy} onCreatorChange={saveCreator} onClose={() => setSelectedId('')} onModelRequired={() => requestModelConnection('node')} /> : <div className="creator-inspector-empty"><Workflow /><strong>{workspaceMode === 'discover' ? '方向探索' : '选择一个步骤'}</strong><p>{workspaceMode === 'discover' ? '比较候选方向后进入方案编排。' : '在画布或项目大纲中选择节点，审核目标、业务参数和能力来源。'}</p></div>}
      </aside>
    </div>

    {creator && recipePreview && <aside className="creator-recipe-preview" aria-label="整体草稿预览"><header><div><span>整体改动预览</span><h2>{recipePreview.goal}</h2></div><button className="icon-button" type="button" title="关闭预览" onClick={() => setRecipePreview(null)}><X /></button></header><div className="creator-recipe-preview-body"><p>新草稿包含 {recipePreview.nodes.length} 个步骤，其中 {recipePreview.nodes.filter((node) => node.resolution === 'unresolved').length} 个需要补齐能力。</p>{recipePreview.nodes.map((node, index) => <article key={node.id}><span>{index + 1}</span><div><strong>{node.label}</strong><p>{node.description}</p><small>{node.resolution === 'resolved' ? '已有可信能力' : '保留为待补齐能力'}</small></div></article>)}<div className="creator-recipe-impact"><span>新增 {recipePreview.impact.added_node_ids.length}</span><span>保留 {recipePreview.impact.retained_node_ids.length}</span><span>移除 {recipePreview.impact.removed_node_ids.length}</span></div><div className="creator-recipe-preview-actions"><button className="secondary-button" type="button" disabled={busy} onClick={() => setRecipePreview(null)}>放弃这版</button><button type="button" disabled={busy} onClick={() => void applyRecipePreview()}><Check />应用整体改动</button></div></div></aside>}
    {modelSetupOpen && <><div className="creator-overlay" aria-hidden="true" /><ModelConnectionPanel onConnect={connectModel} onClose={() => { setModelSetupOpen(false); setPendingAiAction(null) }} /></>}
    {themePanelOpen && <><div className="creator-overlay" aria-hidden="true" /><CreatorThemePanel theme={theme} onChange={setTheme} onClose={() => setThemePanelOpen(false)} /></>}
  </main>
}
