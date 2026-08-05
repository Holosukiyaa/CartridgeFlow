import { type FormEvent, useEffect, useMemo, useRef, useState } from 'react'
import {
  Check,
  CheckCircle2,
  Download,
  Lightbulb,
  Loader2,
  PackageCheck,
  RefreshCw,
  Send,
  ShieldCheck,
  Sparkles,
  Wrench,
  X,
} from 'lucide-react'
import {
  ApiError,
  acceptCreatorProposal,
  composeCreatorRecipe,
  connectCreatorAi,
  confirmCreatorNode,
  discoverCreatorPossibilities,
  fetchCreatorAiStatus,
  fetchCreatorProject,
  fetchCreatorSession,
  packageCreatorProject,
  previewCreatorProposal,
  proposeCreatorNodeValues,
  recomposeCreatorRecipe,
  refineCreatorNodeWithAi,
  rejectCreatorProposal,
  resolveCreatorCapabilities,
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

  return <aside className="creator-node-editor" aria-label={`调整 ${node.label}`}>
    <header>
      <div><span className={`creator-status-label ${trusted && !unresolved ? 'is-confirmed' : ''}`}>{unresolved ? <Wrench /> : trusted ? <CheckCircle2 /> : <ShieldCheck />}{unresolved ? '待补齐能力' : trusted ? '已确认' : '待审核'}</span><h2>{node.label}</h2><p>{node.description}</p></div>
      <button className="icon-button" type="button" onClick={onClose} title="关闭节点"><X /></button>
    </header>
    <div className="creator-node-editor-body">
      {unresolved && <section className="creator-capability-gap"><div><strong>这个想法已经保留</strong><p>{node.resolution?.needed_capability}</p></div><a href={`/developer?goal=${encodeURIComponent(node.resolution?.needed_capability || node.description)}&projectId=${encodeURIComponent(creator.project_id)}&nodeId=${encodeURIComponent(node.id)}`}><Wrench />进入能力卡带工坊</a><small>发布可信能力后，回到这里会在原节点上重新匹配。</small></section>}
      {!unresolved && node.resolution?.capability && <section className="creator-capability-source"><ShieldCheck /><div><strong>{node.resolution.capability.label}</strong><span>{node.resolution.capability.trust_scope === 'workspace' ? '当前工作区可信' : node.resolution.capability.trust_scope === 'organization' ? '组织可信' : '系统可信'} · v{node.resolution.capability.revision}</span></div></section>}
      {!proposal && <>
        <FieldEditor node={node} values={values} onChange={setValues} disabled={isBusy} />
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

export function CreatorStudio({ projectId }: { projectId: string }) {
  const [creator, setCreator] = useState<CreatorProjection | null>(null)
  const [goal, setGoal] = useState('')
  const [selectedId, setSelectedId] = useState('')
  const [possibilities, setPossibilities] = useState<CreatorPossibility[]>([])
  const [packageResult, setPackageResult] = useState<CreatorPackage | null>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [modelSetupOpen, setModelSetupOpen] = useState(false)
  const [pendingAiAction, setPendingAiAction] = useState<'discover' | 'compose' | 'node' | null>(null)
  const composerRef = useRef<HTMLTextAreaElement | null>(null)
  const aiConnectedRef = useRef<boolean | null>(null)
  const resolutionCheckRef = useRef('')

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

  useEffect(() => {
    fetchCreatorAiStatus()
      .then((status) => {
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

  const saveCreator = (next: CreatorProjection) => {
    setCreator(next)
    setPackageResult(null)
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
  const discover = async () => {
    if (goal.trim().length < 3) return
    if (aiConnectedRef.current === false) {
      requestModelConnection('discover')
      return
    }
    setBusy(true)
    try {
      const result = await discoverCreatorPossibilities(goal.trim())
      setPossibilities(result.possibilities)
    } catch (error) {
      if (isModelBlock(error, 'discover')) return
      showToast({ title: '暂时无法打开新方向', description: friendlyError(error, 'discover'), type: 'error' })
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
    setPossibilities([])
    try {
      const result = creator
        ? await recomposeCreatorRecipe(creator.session_id, { goal: nextGoal, expected_revision: creator.revision })
        : await composeCreatorRecipe({ session_id: creatorId(), project_id: projectId, goal: nextGoal })
      if (!result.creator) throw new Error('missing creator')
      saveCreator(result.creator)
      setGoal(result.creator.intent)
      setSelectedId('')
      showToast({ title: creator ? '整体草稿已更新' : '整体草稿已生成', description: '请逐个打开节点进行审核。', type: 'success' })
    } catch (error) {
      if (isModelBlock(error, 'compose')) return
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

  return <main className="creator-workspace">
    <header className="creator-topbar">
      <div><strong>CartridgeFlow</strong><span>Creator Studio</span></div>
      <div className="creator-project-state">
        {creator ? <><span><Check />已自动保存</span><span>{confirmedCount}/{totalCount} 个节点已确认</span>{Boolean(creator.capability_resolution?.unresolved) && <button type="button" disabled={busy} onClick={() => void refreshCapabilities()} title="重新检查可信能力"><RefreshCw />{creator.capability_resolution?.unresolved} 个待补齐</button>}</> : <span>新项目</span>}
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
    </form>}

    {creator && selectedNode && <NodeEditor key={`${selectedNode.id}:${creator.revision}`} creator={creator} node={selectedNode} busy={busy} onCreatorChange={saveCreator} onClose={() => setSelectedId('')} onModelRequired={() => requestModelConnection('node')} />}
    {modelSetupOpen && <ModelConnectionPanel onConnect={connectModel} onClose={() => { setModelSetupOpen(false); setPendingAiAction(null) }} />}
  </main>
}
