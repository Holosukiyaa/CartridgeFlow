import { type FormEvent, useEffect, useMemo, useRef, useState } from 'react'
import {
  Check,
  CheckCircle2,
  Download,
  Lightbulb,
  Loader2,
  PackageCheck,
  Send,
  ShieldCheck,
  Sparkles,
  X,
} from 'lucide-react'
import {
  ApiError,
  acceptCreatorProposal,
  composeCreatorRecipe,
  confirmCreatorNode,
  discoverCreatorPossibilities,
  fetchCreatorProject,
  fetchCreatorSession,
  packageCreatorProject,
  previewCreatorProposal,
  proposeCreatorNodeValues,
  recomposeCreatorRecipe,
  refineCreatorNodeWithAi,
  rejectCreatorProposal,
  type CreatorCapabilityGap,
  type CreatorPackage,
  type CreatorPossibility,
  type CreatorProjection,
  type CreatorProposal,
  type CreatorRecipeNode,
} from '../../api.ts'
import { showToast } from '../../toast.tsx'
import { CreatorCanvas } from './CreatorCanvas.tsx'

const creatorId = () => `creator.${crypto.randomUUID()}`

function friendlyError(error: unknown, action: 'discover' | 'compose' | 'node' | 'package') {
  const code = error instanceof ApiError ? error.code : ''
  if (code.includes('MODEL_UNBOUND')) return 'AI 共创服务尚未准备好。'
  if (code.includes('TIMEOUT')) return 'AI 响应超时，请稍后重试。'
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

function NodeEditor({ creator, node, busy, onCreatorChange, onClose }: {
  creator: CreatorProjection
  node: CreatorRecipeNode
  busy: boolean
  onCreatorChange: (creator: CreatorProjection) => void
  onClose: () => void
}) {
  const [values, setValues] = useState<Record<string, unknown>>(node.values)
  const [prompt, setPrompt] = useState('')
  const [proposal, setProposal] = useState<CreatorProposal | null>(() => creator.pending_proposals.find((item) => item.changes.some((change) => change.target_id === node.id)) || null)
  const [impact, setImpact] = useState('')
  const [working, setWorking] = useState(false)
  const trusted = creator.frozen_steps.includes(node.id)
  const changed = JSON.stringify(values) !== JSON.stringify(node.values)
  const freezeRevision = creator.active_freezes.find((freeze) => freeze.steps.includes(node.id))?.freeze_revision
  const isBusy = busy || working

  useEffect(() => {
    setValues(node.values)
    setPrompt('')
    setProposal(creator.pending_proposals.find((item) => item.changes.some((change) => change.target_id === node.id)) || null)
    setImpact('')
  }, [creator.pending_proposals, node.id, node.values])

  const fail = (error: unknown) => showToast({ title: '节点调整未完成', description: friendlyError(error, 'node'), type: 'error' })
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
      setImpact(result.impact.plain_summary || '本次修改只影响当前节点。')
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

  return <aside className="creator-node-editor" aria-label={`调整 ${node.label}`}>
    <header>
      <div><span className={`creator-status-label ${trusted ? 'is-confirmed' : ''}`}>{trusted ? <CheckCircle2 /> : <ShieldCheck />}{trusted ? '已确认' : '待审核'}</span><h2>{node.label}</h2><p>{node.description}</p></div>
      <button className="icon-button" type="button" onClick={onClose} title="关闭节点"><X /></button>
    </header>
    <div className="creator-node-editor-body">
      {!proposal && <>
        <FieldEditor node={node} values={values} onChange={setValues} disabled={isBusy} />
        <button className="secondary-button" type="button" disabled={isBusy || !changed} onClick={() => void stage()}><Check />保存字段修改</button>
        <div className="creator-ai-refine">
          <label><span>继续和 AI 对齐这个节点</span><textarea value={prompt} disabled={isBusy || changed} onChange={(event) => setPrompt(event.currentTarget.value)} placeholder="例如：只保留中文来源，并按重要性排序" /></label>
          <button type="button" disabled={isBusy || changed || !prompt.trim()} onClick={() => void ask()}><Sparkles />生成调整建议</button>
        </div>
        <button className="confirm-button" type="button" disabled={isBusy || trusted || changed} onClick={() => void confirm()}><ShieldCheck />{trusted ? '节点已确认' : '确认这个节点'}</button>
      </>}
      {proposal && <section className="creator-review">
        <span>修改确认</span>
        <h3>{proposal.summary}</h3>
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

export function CreatorStudio({ projectId }: { projectId: string }) {
  const [creator, setCreator] = useState<CreatorProjection | null>(null)
  const [goal, setGoal] = useState('')
  const [selectedId, setSelectedId] = useState('')
  const [possibilities, setPossibilities] = useState<CreatorPossibility[]>([])
  const [gap, setGap] = useState<CreatorCapabilityGap | null>(null)
  const [packageResult, setPackageResult] = useState<CreatorPackage | null>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const composerRef = useRef<HTMLTextAreaElement | null>(null)

  useEffect(() => {
    let active = true
    fetchCreatorProject(projectId)
      .then(({ creator: value }) => {
        if (!active || !value) return
        setCreator(value)
        setGoal(value.intent)
      })
      .catch(() => showToast({ title: '草稿读取失败', description: '请刷新页面后重试。', type: 'error' }))
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [projectId])

  const selectedNode = useMemo(() => creator?.trusted_recipe.nodes.find((node) => node.id === selectedId) || null, [creator, selectedId])
  const confirmedCount = creator?.frozen_steps.length || 0
  const totalCount = creator?.trusted_recipe.nodes.length || 0

  const saveCreator = (next: CreatorProjection) => {
    setCreator(next)
    setPackageResult(null)
  }
  const discover = async () => {
    if (goal.trim().length < 3) return
    setBusy(true)
    setGap(null)
    try {
      const result = await discoverCreatorPossibilities(goal.trim())
      setPossibilities(result.possibilities)
    } catch (error) {
      showToast({ title: '暂时无法打开新方向', description: friendlyError(error, 'discover'), type: 'error' })
    } finally { setBusy(false) }
  }
  const compose = async (requestedGoal: string) => {
    const nextGoal = requestedGoal.trim()
    if (nextGoal.length < 3) return
    setBusy(true)
    setGap(null)
    setPossibilities([])
    try {
      const result = creator
        ? await recomposeCreatorRecipe(creator.session_id, { goal: nextGoal, expected_revision: creator.revision })
        : await composeCreatorRecipe({ session_id: creatorId(), project_id: projectId, goal: nextGoal })
      if (result.capability_gap) {
        setGap(result.capability_gap)
        return
      }
      if (!result.creator) throw new Error('missing creator')
      saveCreator(result.creator)
      setGoal(result.creator.intent)
      setSelectedId('')
      showToast({ title: creator ? '整体草稿已更新' : '整体草稿已生成', description: '请逐个打开节点进行审核。', type: 'success' })
    } catch (error) {
      showToast({ title: '整体编排未完成', description: friendlyError(error, 'compose'), type: 'error' })
    } finally { setBusy(false) }
  }
  const submit = (event: FormEvent) => {
    event.preventDefault()
    void compose(goal)
  }
  const buildPackage = async () => {
    if (!creator) return
    setBusy(true)
    try {
      const result = await packageCreatorProject(creator.session_id, creator.revision)
      setPackageResult(result)
      showToast({ title: '打包完成', description: '签名已验证，可以交给独立测试台。', type: 'success' })
    } catch (error) {
      showToast({ title: '暂时不能打包', description: friendlyError(error, 'package'), type: 'error' })
    } finally { setBusy(false) }
  }

  return <main className="creator-workspace">
    <header className="creator-topbar">
      <div><strong>CartridgeFlow</strong><span>Creator Studio</span></div>
      <div className="creator-project-state">
        {creator ? <><span><Check />已自动保存</span><span>{confirmedCount}/{totalCount} 个节点已确认</span></> : <span>新项目</span>}
      </div>
      <div className="creator-package-action">
        {packageResult ? <a href={packageResult.url} download><Download />下载包</a> : <button type="button" disabled={busy || !creator?.generation_readiness.ready} onClick={() => void buildPackage()} title={creator?.generation_readiness.ready ? '打包当前项目' : '确认全部节点后可打包'}>{busy && creator?.generation_readiness.ready ? <Loader2 className="spinning" /> : <PackageCheck />}打包</button>}
      </div>
    </header>

    <section className="creator-canvas" aria-label="项目链路图">
      <CreatorCanvas creator={creator} selectedId={selectedId} onSelect={setSelectedId} />
      {loading && <div className="creator-loading"><Loader2 className="spinning" /><span>正在读取草稿</span></div>}
    </section>

    {!selectedNode && !loading && <form className="creator-composer" onSubmit={submit}>
      <div className="creator-composer-heading">
        <div><span>{creator ? '调整整体草稿' : '从一个想法开始'}</span><strong>{creator ? creator.intent : '你想得到什么？'}</strong></div>
        {possibilities.length > 0 && <button className="icon-button" type="button" title="关闭方向建议" onClick={() => setPossibilities([])}><X /></button>}
      </div>
      {possibilities.length > 0 && <div className="creator-possibilities" aria-label="AI 方向建议">
        {possibilities.map((item) => <article key={item.id}>
          <h3>{item.title}</h3>
          <p>{item.outcome}</p>
          <small>{item.why_it_fits}</small>
          <button type="button" onClick={() => { setGoal(item.recipe.intent); void compose(item.recipe.intent) }}><Send />沿这个方向生成草稿</button>
        </article>)}
      </div>}
      <label className="creator-goal-input"><textarea ref={composerRef} value={goal} disabled={busy} onChange={(event) => setGoal(event.currentTarget.value)} placeholder={creator ? '例如：增加来源审核，并让最终内容更适合每天阅读' : '例如：我想每天收到一份可靠的 AI 日报，但不知道该选哪些来源'} aria-label={creator ? '整体调整要求' : '创作目标'} /></label>
      <div className="creator-composer-actions">
        {!creator && <button className="secondary-button" type="button" disabled={busy || goal.trim().length < 3} onClick={() => void discover()}>{busy ? <Loader2 className="spinning" /> : <Lightbulb />}帮我打开思路</button>}
        <button type="submit" disabled={busy || goal.trim().length < 3}>{busy ? <Loader2 className="spinning" /> : <Sparkles />}{creator ? '重新编排整体草稿' : '生成整体草稿'}</button>
      </div>
      {gap && <div className="creator-gap" role="status"><ShieldCheck /><div><strong>当前可信能力还不够</strong>{gap.needed_capabilities.map((item) => <span key={item}>{item}</span>)}<small>能力补齐后，可在这里直接重新生成。</small></div></div>}
    </form>}

    {creator && selectedNode && <NodeEditor key={`${selectedNode.id}:${creator.revision}`} creator={creator} node={selectedNode} busy={busy} onCreatorChange={saveCreator} onClose={() => setSelectedId('')} />}
  </main>
}
