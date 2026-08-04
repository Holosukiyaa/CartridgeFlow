import { FormEvent, useEffect, useState } from 'react'
import { ApiError, Creator, FreezeRevision, Handoff, Impact, Possibility, Proposal, Source, creatorApi } from './api'

const idFor = (prefix: string) => `${prefix}-${crypto.randomUUID().slice(0, 8)}`
const sourceUrl = (value: string) => {
  try {
    const url = new URL(value)
    const sensitive = /token|secret|password|credential|api[_-]?key|authorization|cookie|sig|signature|key/i
    return url.protocol === 'https:' && !url.username && !url.password && [...url.searchParams.keys()].every((key) => !sensitive.test(key)) ? url.toString() : null
  } catch { return null }
}
const digest = async (value: unknown) => Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(JSON.stringify(value))))).map((item) => item.toString(16).padStart(2, '0')).join('')
const errorText = (error: unknown) => {
  if (!(error instanceof ApiError)) return '无法连接创作服务。请确认后端正在运行。'
  if (error.code === 'AI_AUTHORING_MODEL_UNBOUND') return 'AI 创作服务尚未连接。请先在 Developer Console 中配置模型。'
  if (error.code === 'AI_AUTHORING_MODEL_TIMEOUT') return 'AI 创作服务没有及时响应，当前设计未发生变化。'
  if (error.code === 'AUTHORING_FROZEN_STEP') return '该步骤已经冻结，请通过冻结修订流程修改。'
  if (error.code === 'AUTHORING_GENERATION_BLOCKED') return '请先解决设计阻塞项并冻结全部步骤。'
  return error.message || '本次创作操作未能完成。'
}
const changeLabel = (operation: string) => ({ add_source: '添加来源', update_source: '更新来源', remove_source: '移除来源', add_step: '添加步骤', set_step_intent: '调整步骤目标', connect_steps: '连接步骤', disconnect_steps: '断开步骤连接' }[operation] || '调整设计')
const routeSessionId = () => {
  return localStorage.getItem('creator-session-id') || ''
}
const routeProjectId = () => {
  const match = window.location.pathname.match(/^\/projects\/([^/]+)\/creator$/)
  return match?.[1] ? decodeURIComponent(match[1]) : localStorage.getItem('creator-project-id') || ''
}

export default function App() {
  const [creator, setCreator] = useState<Creator | null>(null)
  const [intent, setIntent] = useState('')
  const [possibilities, setPossibilities] = useState<Possibility[]>([])
  const [sourceInput, setSourceInput] = useState('')
  const [prompt, setPrompt] = useState('')
  const [newStep, setNewStep] = useState('')
  const [selectedStep, setSelectedStep] = useState('')
  const [stepIntent, setStepIntent] = useState('')
  const [fromStep, setFromStep] = useState('')
  const [toStep, setToStep] = useState('')
  const [proposal, setProposal] = useState<Proposal | null>(null)
  const [selectedChanges, setSelectedChanges] = useState<string[]>([])
  const [impact, setImpact] = useState<Impact | null>(null)
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)
  const [handoff, setHandoff] = useState<Handoff | null>(null)

  const save = (next: Creator) => {
    setCreator(next); localStorage.setItem('creator-project-id', next.project_id)
    const current = next.semantic_steps.find((step) => step.id === selectedStep) || next.semantic_steps[0]
    setSelectedStep(current?.id || ''); setStepIntent(current?.intent || '')
  }
  useEffect(() => {
    const projectId = routeProjectId()
    const sessionId = routeSessionId()
    if (!projectId && !sessionId) return
    const load = projectId ? creatorApi.getProject(projectId) : creatorApi.get(sessionId)
    load.then(({ creator: next }) => { save(next); setIntent(next.intent); setProposal(next.pending_proposals[0] || null) }).catch((error) => { localStorage.removeItem('creator-project-id'); localStorage.removeItem('creator-session-id'); setNotice(errorText(error)) })
  }, [])
  const freezeRevision = (changes: Proposal['changes']): FreezeRevision | undefined => {
    if (!creator) return undefined
    const ids = creator.active_freezes.filter((freeze) => freeze.steps.some((stepId) => changes.some((change) => change.target_id === stepId))).map((freeze) => freeze.id)
    return ids.length ? { source_freeze_ids: ids, expected_revision: creator.revision, reason: '创作者确认修改已冻结的设计步骤。', author: 'creator' } : undefined
  }
  const preview = async (next: Proposal, ids: string[]) => {
    if (!creator) return null
    const revision = freezeRevision(next.changes.filter((change) => ids.includes(change.id)))
    const body = { selected_change_ids: ids, ...(revision ? { freeze_revision: revision } : {}) }
    const result = await creatorApi.preview(creator.session_id, next.proposal_id, body); setImpact(result.impact)
    return body
  }
  const stage = async (next: Proposal, message: string) => { const ids = next.changes.map((change) => change.id); setProposal(next); setSelectedChanges(ids); setImpact(null); setNotice(message); await preview(next, ids) }
  const mutate = async (change: Record<string, unknown>, summary: string) => {
    if (!creator) return
    setBusy(true)
    try { const result = await creatorApi.propose(creator.session_id, { changes: [{ id: idFor('change'), ...change }], author: 'creator', summary, expected_revision: creator.revision }); await stage(result.proposal, '变更已进入审阅，尚未写入设计。') }
    catch (error) { setNotice(errorText(error)) } finally { setBusy(false) }
  }
  const create = async (possibility?: Possibility) => {
    setBusy(true)
    try {
      const id = idFor('authoring')
      const projectId = idFor('project')
      const recipe = possibility?.recipe || { intent, steps: [{ id: 'collect', intent: '收集指定来源', inputs: [], outputs: [] }] }
      const result = await creatorApi.create({ session_id: id, project_id: projectId, recipe_id: idFor('recipe'), intent: recipe.intent, steps: recipe.steps, source_references: [], bindings: {} })
      localStorage.removeItem('creator-session-id'); window.history.replaceState({}, '', `/projects/${encodeURIComponent(projectId)}/creator`); save(result.creator); setNotice('项目创作会话已创建。')
    } catch (error) { setNotice(errorText(error)) } finally { setBusy(false) }
  }
  const discover = async (event: FormEvent) => {
    event.preventDefault(); setBusy(true); setNotice('')
    try { const result = await creatorApi.discover(intent); setPossibilities(result.possibilities); setNotice('请选择一个最接近你当前想法的方向。') }
    catch (error) { setNotice(errorText(error)) } finally { setBusy(false) }
  }
  const addSource = async () => {
    const url = sourceUrl(sourceInput)
    if (!url) { setNotice('请输入不包含凭据或敏感查询参数的 HTTPS 来源地址。'); return }
    const source: Source = { id: idFor('source'), kind: 'source', digest: '', role: '创作者来源', remote_url: url }
    source.digest = await digest(source); await mutate({ target_id: source.id, operation: 'add_source', value: source }, '添加创作来源'); setSourceInput('')
  }
  const askAi = async () => {
    if (!creator || !prompt.trim()) return
    setBusy(true)
    try { const result = await creatorApi.ai(creator.session_id, { prompt, author: 'creator', summary: 'AI 创作建议', expected_revision: creator.revision }); await stage(result.proposal, 'AI 提出了可审阅的设计变更。') }
    catch (error) { setNotice(errorText(error)) } finally { setBusy(false) }
  }
  const accept = async () => {
    if (!creator || !proposal || !impact) return
    setBusy(true)
    try { const body = await preview(proposal, selectedChanges); if (!body) return; const result = await creatorApi.accept(creator.session_id, proposal.proposal_id, body); save(result.creator); setProposal(null); setImpact(null); setNotice(`已接受 ${result.accepted_change_ids.length} 项修改。`) }
    catch (error) { setNotice(errorText(error)) } finally { setBusy(false) }
  }
  const reject = async () => {
    if (!creator || !proposal) return
    try { const result = await creatorApi.reject(creator.session_id, proposal.proposal_id, { reason: '创作者选择不采用这组建议。' }); save(result.creator); setProposal(null); setImpact(null); setNotice('已拒绝这组建议。') }
    catch (error) { setNotice(errorText(error)) }
  }
  const freeze = async (stepId: string) => {
    if (!creator) return
    setBusy(true)
    try { await creatorApi.freeze(creator.session_id, { step_ids: [stepId], author: 'creator', summary: '冻结已确认步骤' }); const result = await creatorApi.get(creator.session_id); save(result.creator); setNotice('步骤已冻结。') }
    catch (error) { setNotice(errorText(error)) } finally { setBusy(false) }
  }
  const undo = async () => {
    const entry = creator?.history.at(-1)
    if (!creator || !entry) return
    try { const result = await creatorApi.reverse(creator.session_id, entry.id, { author: 'creator', summary: '撤销最近接受的修改', expected_revision: creator.revision }); save(result.creator); setNotice('已创建撤销修订。') }
    catch (error) { setNotice(errorText(error)) }
  }
  const check = async () => {
    if (!creator) return
    try { const result = await creatorApi.checks(creator.session_id); setNotice(result.design_checks.findings.length ? `设计检查发现 ${result.design_checks.findings.length} 项需要处理。` : '设计检查通过。') }
    catch (error) { setNotice(errorText(error)) }
  }
  const handoffDesign = async () => {
    if (!creator) return
    setBusy(true)
    try { const candidate = await creatorApi.compile(creator.session_id, creator.revision); const result = await creatorApi.handoff(creator.session_id, creator.revision, candidate.compile_candidate); setHandoff(result); setNotice('已生成并验证签名交付包。') }
    catch (error) { setNotice(errorText(error)) } finally { setBusy(false) }
  }

  if (!creator) return <main><header><h1>CartridgeFlow 创作工作室</h1></header><form onSubmit={discover}><p><label>你最近在关注、困惑或想探索什么？<textarea aria-label="Creative intent" value={intent} onChange={(event) => { setIntent(event.target.value); setPossibilities([]) }} required /></label></p><button type="submit" disabled={busy || intent.trim().length < 3}>帮我打开思路</button></form>{possibilities.length > 0 && <section aria-labelledby="possibilities-heading"><h2 id="possibilities-heading">可以从这里开始</h2>{possibilities.map((possibility) => <article key={possibility.id}><h3>{possibility.title}</h3><p>你将得到：{possibility.outcome}</p><p>适合你的原因：{possibility.why_it_fits}</p><p>第一周：{possibility.first_week_output}</p><p>还需要确认：{possibility.needs_confirmation.join('、')}</p><button onClick={() => void create(possibility)} disabled={busy}>选择这个方向</button></article>)}</section>}{notice && <p role="status">{notice}</p>}</main>

  const current = creator.semantic_steps.find((step) => step.id === selectedStep) || creator.semantic_steps[0]
  const base = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')
  return <main>
    <header><h1>CartridgeFlow 创作工作室</h1><p>{creator.intent}</p><p>设计修订：{creator.revision}</p><button onClick={undo} disabled={!creator.history.length || busy}>撤销最近修改</button><button onClick={check} disabled={busy}>检查设计</button><button onClick={handoffDesign} disabled={busy || !creator.generation_readiness.ready} aria-label="Generate handoff">生成交付包</button>{creator.generation_readiness.ready && <a href={`/projects/${encodeURIComponent(creator.project_id)}/developer`}>进入工程验证</a>}</header>
    {notice && <p role="status">{notice}</p>}
    <section aria-labelledby="sources-heading"><h2 id="sources-heading">来源</h2><ul>{creator.sources.map((source) => <li key={source.id}>{source.role || '创作者来源'}：{source.remote_url || source.rss_url || '需要补充地址'}</li>)}</ul><label>添加来源<input aria-label="Add source URL" value={sourceInput} onChange={(event) => setSourceInput(event.target.value)} /></label><button onClick={() => void addSource()} disabled={busy}>提交来源审阅</button></section>
    <section aria-labelledby="ai-heading"><h2 id="ai-heading">AI 协作</h2><label>希望如何调整设计？<textarea aria-label="Ask AI to modify the design" value={prompt} onChange={(event) => setPrompt(event.target.value)} /></label><button onClick={() => void askAi()} disabled={busy || !prompt.trim()} aria-label="Request AI proposal">请求 AI 建议</button></section>
    <section aria-labelledby="flow-heading"><h2 id="flow-heading">设计流程</h2><ul aria-label="Design steps">{creator.semantic_steps.map((step) => <li key={step.id}><button onClick={() => { setSelectedStep(step.id); setStepIntent(step.intent) }} aria-pressed={current?.id === step.id}>{step.intent}</button>{creator.frozen_steps.includes(step.id) ? '（已冻结）' : <button onClick={() => void freeze(step.id)} disabled={busy}>冻结</button>}</li>)}</ul><label>新增步骤<input aria-label="New step" value={newStep} onChange={(event) => setNewStep(event.target.value)} /></label><button onClick={() => { const id = idFor('step'); void mutate({ target_id: id, operation: 'add_step', value: { id, intent: newStep || '新的创作步骤', inputs: [], outputs: [] } }, '新增设计步骤'); setNewStep('') }} disabled={busy}>提交新增步骤</button><form onSubmit={(event) => { event.preventDefault(); if (fromStep && toStep && fromStep !== toStep) void mutate({ target_id: idFor('relation'), operation: 'connect_steps', value: { id: idFor('relation'), from_step_id: fromStep, to_step_id: toStep, relation: '驱动' } }, '连接设计步骤') }}><label>起始步骤<select aria-label="Connect from" value={fromStep} onChange={(event) => setFromStep(event.target.value)}><option value="" />{creator.semantic_steps.map((step) => <option key={step.id} value={step.id}>{step.intent}</option>)}</select></label><label>目标步骤<select aria-label="Connect to" value={toStep} onChange={(event) => setToStep(event.target.value)}><option value="" />{creator.semantic_steps.map((step) => <option key={step.id} value={step.id}>{step.intent}</option>)}</select></label><button type="submit" disabled={busy || !fromStep || !toStep || fromStep === toStep}>提交连接审阅</button></form><ul aria-label="Design relationships">{creator.relationships.map((relationship) => <li key={relationship.id}>{relationship.from_step_id} 到 {relationship.to_step_id}</li>)}</ul></section>
    <section aria-labelledby="inspector-heading"><h2 id="inspector-heading">步骤详情</h2>{current ? <><p>输入：{current.plain_inputs.join('、') || '尚未定义'}</p><p>输出：{current.plain_outputs.join('、') || '尚未定义'}</p><label>步骤目标<input aria-label="Selected step intent" value={stepIntent} onChange={(event) => setStepIntent(event.target.value)} /></label><button onClick={() => void mutate({ target_id: current.id, operation: 'set_step_intent', value: stepIntent }, '调整步骤目标')} disabled={busy || !stepIntent.trim() || stepIntent === current.intent}>提交步骤调整审阅</button></> : <p>尚未选择步骤。</p>}</section>
    <section aria-labelledby="review-heading"><h2 id="review-heading">变更审阅</h2>{proposal ? <><p>{proposal.summary}</p><ul>{proposal.changes.map((change) => <li key={change.id}><label><input type="checkbox" checked={selectedChanges.includes(change.id)} onChange={() => { setSelectedChanges((items) => items.includes(change.id) ? items.filter((id) => id !== change.id) : [...items, change.id]); setImpact(null) }} />{changeLabel(change.operation)}</label></li>)}</ul>{impact ? <p>{impact.plain_summary || '已计算变更影响。'}</p> : <button onClick={() => void preview(proposal, selectedChanges).catch((error) => setNotice(errorText(error)))} disabled={!selectedChanges.length}>检查影响</button>}<button onClick={() => void reject()} disabled={busy}>拒绝建议</button><button onClick={() => void accept()} disabled={busy || !impact || !selectedChanges.length}>接受选中的修改</button></> : <p>没有待审阅的变更。</p>}</section>
    <section aria-labelledby="delivery-heading"><h2 id="delivery-heading">交付</h2>{creator.blocked_findings.length ? <ul>{creator.blocked_findings.map((finding) => <li key={`${finding.code}:${finding.step_id || ''}`}>{finding.message}</li>)}</ul> : <p>当前没有设计阻塞项。</p>}{handoff && <p>交付包：{handoff.release_id}，签名已验证。<a href={`${base}${handoff.url}`}>下载 CF-CRE</a></p>}</section>
  </main>
}
