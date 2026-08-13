import { type CSSProperties, type FormEvent, useEffect, useMemo, useRef, useState } from 'react'
import {
  Bot,
  Check,
  CheckCircle2,
  ChevronDown,
  Download,
  FileText,
  Globe2,
  Loader2,
  MousePointer2,
  PackageCheck,
  Paperclip,
  Palette,
  Plus,
  Redo2,
  RefreshCw,
  Scan,
  Send,
  Share2,
  Search,
  Settings,
  ShieldCheck,
  Sparkles,
  Target,
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
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [projectMenuOpen, setProjectMenuOpen] = useState(false)
  const [projects, setProjects] = useState<Array<{ project_id: string; session_id: string; name: string; intent: string; revision: number }>>([])
  const [pendingAiAction, setPendingAiAction] = useState<'discover' | 'compose' | 'node' | null>(null)
  const stewardThreadRef = useRef<HTMLDivElement | null>(null)
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
        setSelectedId('')
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
    stewardThreadRef.current?.scrollTo({ top: stewardThreadRef.current.scrollHeight, behavior: 'smooth' })
  }, [busy, stewardMessages])

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
  const canvasStatus = recipePreview ? 'AI 刚提出一版新大纲，正在等你确认' : creator ? '大纲会随着讨论持续变化' : goal.trim() ? '准备把当前想法摆成大纲' : '先说一句现在的想法'

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

  return <main className="creator-workspace creator-workbench" style={themeVariables(theme)}>
    <header className="creator-topbar is-co-create creator-workbench-header">
      <div className="creator-brand">
        <span className="creator-brand-mark" aria-hidden="true"><Share2 /></span>
        <div className="creator-brand-copy">
          <div className="creator-workspace-heading"><strong>CARTRIDGE WORKSPACE</strong><span>/ 卡带工作台</span></div>
          <div className="creator-brand-tags" aria-label="工作台状态"><span>语义大纲</span><span>持续共创</span><span>简体中文</span></div>
        </div>
      </div>
      <div className="creator-top-actions">
        <span className="creator-design-mode"><Workflow />设计</span>
        {creator && <>
          <span className="creator-saved"><CheckCircle2 />已自动保存</span>
          <button className="icon-button" type="button" title="当前没有可撤销的操作" disabled><Undo2 /></button>
          <button className="icon-button" type="button" title="当前没有可重做的操作" disabled><Redo2 /></button>
        </>}
        <button className="creator-theme-button" type="button" onClick={() => setThemePanelOpen(true)}><Palette />主题</button>
        {creator && (packageResult ? <a className="creator-package-download" href={packageResult.url} download><Download />下载卡带</a> : <button className="creator-package-button" type="button" disabled={busy || !creator?.generation_readiness.ready} onClick={() => void buildPackage()} title={creator?.generation_readiness.ready ? '生成可安装卡带' : '完成所有步骤后可交付'}><PackageCheck />生成卡带</button>)}
      </div>
    </header>

    <div className="creator-commandbar">
      <div className="creator-commandbar-left">
        <span className="creator-mode-indicator"><i />选择模式</span>
        <span className="creator-view-indicator"><Workflow />大纲视图</span>
        <span className="creator-canvas-status"><i className={recipePreview ? 'is-preview' : ''} />{canvasStatus}</span>
        <span className="creator-outline-metrics">{totalCount} 步骤 · {confirmedCount} 已确认 · {reviewCount} 待审核 · {unresolvedCount} 待补齐</span>
      </div>
      <div className="creator-commandbar-actions" role="tablist" aria-label="右侧面板">
        <button type="button" role="tab" aria-selected={Boolean(selectedNode)} disabled={!selectedNode} className={selectedNode ? 'is-active' : ''} onClick={() => setCanvasTool('inspect')}><FileText />详情</button>
        <button type="button" role="tab" aria-selected={!selectedNode} className={!selectedNode ? 'is-active' : ''} onClick={() => setSelectedId('')}><Bot />AI 管家</button>
      </div>
    </div>

    <div className="creator-shell is-co-create">
      <nav className="creator-tool-rail" aria-label="画布工具">
        <button className={canvasTool === 'inspect' ? 'is-active' : ''} type="button" title="打开步骤详情" onClick={() => { setCanvasTool('inspect'); setContextNodeIds([]) }}><Search /><span>查看</span></button>
        <button className={canvasTool === 'pointer' ? 'is-active' : ''} type="button" title="指向一个步骤继续讨论" onClick={() => { setCanvasTool('pointer'); setSelectedId(''); setContextNodeIds([]) }}><MousePointer2 /><span>指向</span></button>
        <button className={canvasTool === 'lasso' ? 'is-active' : ''} type="button" title="框选一组步骤继续讨论" onClick={() => { setCanvasTool('lasso'); setSelectedId(''); setContextNodeIds([]) }}><Scan /><span>框选</span></button>
        <span className="creator-tool-divider" />
        <button className={sidebarOpen ? 'is-active' : ''} type="button" title="打开项目和大纲" aria-expanded={sidebarOpen} onClick={() => setSidebarOpen((value) => !value)}><FileText /><span>项目</span></button>
        <button type="button" title="调整全局主题" onClick={() => setThemePanelOpen(true)}><Palette /><span>主题</span></button>
        <button type="button" title={creator?.generation_readiness.ready ? '生成可安装卡带' : '完成所有步骤后可交付'} disabled={!creator || busy || !creator.generation_readiness.ready} onClick={() => void buildPackage()}><PackageCheck /><span>打包</span></button>
      </nav>

      <aside className={`creator-sidebar ${sidebarOpen ? 'is-open' : ''}`} aria-label="项目与大纲">
        <header className="creator-sidebar-drawer-head"><div><FileText /><span><strong>项目与大纲</strong><small>在画布旁快速定位</small></span></div><button className="icon-button" type="button" title="收起项目面板" onClick={() => setSidebarOpen(false)}><X /></button></header>
        <section className="creator-sidebar-section creator-project-section">
          <header><strong>项目</strong><button className="sidebar-icon-button" type="button" onClick={createProject}><Plus />新建项目</button></header>
          <button className="creator-current-project" type="button" onClick={() => setProjectMenuOpen((value) => !value)}><FileText /><span>{creator?.project_name || creator?.intent || '新项目'}</span><ChevronDown /></button>
          {projectMenuOpen && <div className="creator-project-menu">{projects.map((project) => <a className={project.project_id === projectId ? 'is-current' : ''} href={`/projects/${encodeURIComponent(project.project_id)}/studio`} key={project.project_id}><span>{project.name}</span><small>v{project.revision}</small></a>)}{creator && <div className="creator-project-menu-actions"><button type="button" onClick={() => void renameProject()}>重命名</button><button className="danger" type="button" onClick={() => void removeProject()}>删除</button></div>}</div>}
          <button className="creator-settings-link" type="button" disabled={!creator} onClick={() => void renameProject()}><Settings />项目设置</button>
        </section>

        <section className="creator-sidebar-section creator-outline">
          <header><strong>当前大纲</strong><span>{confirmedCount}/{totalCount || 0}</span></header>
          <div className="creator-outline-list">
            {creator?.trusted_recipe.nodes.map((node, index) => {
              const unresolved = node.resolution?.status === 'unresolved'
              const confirmed = !unresolved && creator.frozen_steps.includes(node.id)
              return <button className={node.id === selectedId || contextNodeIds.includes(node.id) ? 'is-selected' : ''} type="button" key={node.id} onClick={() => {
                if (canvasTool === 'inspect') setSelectedId(node.id)
                else setContextNodeIds([node.id])
              }}>
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

      <section className="creator-stage is-co-create" aria-label="持续共创大纲">
        {packageError && <div className="creator-package-error" role="alert"><strong>打包未完成</strong><span>{packageError}</span></div>}
        <div className={`creator-canvas tool-${canvasTool}`}>
          <IntentCanvas creator={creator} preview={recipePreview} draftGoal={goal} selectedId={selectedId} contextNodeIds={contextNodeIds} tool={canvasTool} onSelect={setSelectedId} onContextChange={setContextNodeIds} />
          {recipePreview && <section className="creator-draft-review" aria-label="新大纲确认">
            <div><strong>新大纲已铺在画布上</strong><span>新增 {recipePreview.impact.added_node_ids.length} · 保留 {recipePreview.impact.retained_node_ids.length} · 移除 {recipePreview.impact.removed_node_ids.length}</span></div>
            <button className="secondary-button" type="button" disabled={busy} onClick={rejectRecipePreview}>保留旧版</button>
            <button type="button" disabled={busy} onClick={() => void applyRecipePreview()}><Check />应用这版</button>
          </section>}
        </div>
        {loading && <div className="creator-loading"><Loader2 className="spinning" /><span>正在读取项目</span></div>}
      </section>

      <aside className="creator-inspector creator-steward" aria-label="AI 管家">
        {canvasTool === 'inspect' && creator && selectedNode && !recipePreview ? <NodeEditor key={`${selectedNode.id}:${creator.revision}:${creator.experience_revision}`} creator={creator} node={selectedNode} busy={busy} onCreatorChange={saveCreator} onClose={() => setSelectedId('')} onModelRequired={() => requestModelConnection('node')} /> : <>
          <header className="creator-steward-head"><span><Bot /></span><div><strong>AI 管家</strong><small>{aiStatus?.has_key ? '和大纲一起持续靠近你的想法' : '连接后开始共同搭建'}</small></div></header>
          <div className="creator-steward-tools">
            <button className={canvasTool === 'pointer' ? 'is-active' : ''} type="button" onClick={() => { setCanvasTool('pointer'); setContextNodeIds([]) }}><MousePointer2 /><span>指向一步</span></button>
            <button className={canvasTool === 'lasso' ? 'is-active' : ''} type="button" onClick={() => { setCanvasTool('lasso'); setContextNodeIds([]) }}><Scan /><span>框选一段</span></button>
          </div>
          <div className={`creator-steward-selection ${contextNodes.length ? 'has-selection' : ''}`}><span>讨论范围</span><strong>{contextNodes.length ? contextNodes.map((node) => node.label).join('、') : '整个大纲'}</strong>{contextNodes.length > 0 && <button type="button" title="清除讨论范围" onClick={() => setContextNodeIds([])}><X /></button>}</div>
          <div className="creator-steward-thread" ref={stewardThreadRef} aria-live="polite">
            {stewardMessages.map((message) => <article className={`creator-steward-message is-${message.role}`} key={message.id}>
              {message.role === 'assistant' && <span><Bot /></span>}
              <div><p>{message.text}</p>{message.clarification && clarification === message.clarification && <section className="creator-clarification"><small>{message.clarification.why_it_matters}</small><div>{message.clarification.suggested_answers.map((answer) => <button type="button" key={answer} disabled={busy} onClick={() => { setClarification(null); continueCoCreation(answer) }}>{answer}</button>)}</div></section>}</div>
            </article>)}
            {busy && <div className="creator-steward-loading"><i /><i /><i /><span>正在把这句话放进大纲</span></div>}
            {composerError && <div className="creator-steward-error" role="alert"><strong>这次没有完成</strong><span>{composerError}</span></div>}
          </div>
          <form className="creator-steward-composer" onSubmit={(event) => { event.preventDefault(); continueCoCreation(stewardInput) }}>
            <textarea autoFocus={!creator} value={stewardInput} disabled={busy} onChange={(event) => { setStewardInput(event.currentTarget.value); setComposerError('') }} onKeyDown={(event) => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); continueCoCreation(stewardInput) } }} placeholder={creator ? '继续说哪里不对，或先用指针、框选限定范围' : '例如：每天整理可信的 AI 动态，给我一份可审核的中文简报'} />
            <div><button className="icon-button" type="button" title="添加参考资料"><Paperclip /></button><span><Globe2 />简体中文输出</span><button type="submit" disabled={busy || stewardInput.trim().length < 3} title="发送给 AI 管家" aria-label="发送给 AI 管家">{busy ? <Loader2 className="spinning" /> : <Send />}</button></div>
          </form>
          <p className="creator-steward-footnote">每次回答都只是下一版可见大纲，不代表 AI 已经完全理解。</p>
        </>}
      </aside>
    </div>

    {modelSetupOpen && <><div className="creator-overlay" aria-hidden="true" /><ModelConnectionPanel onConnect={connectModel} onClose={() => { setModelSetupOpen(false); setPendingAiAction(null) }} /></>}
    {themePanelOpen && <><div className="creator-overlay" aria-hidden="true" /><CreatorThemePanel theme={theme} onChange={setTheme} onClose={() => setThemePanelOpen(false)} /></>}
  </main>
}
