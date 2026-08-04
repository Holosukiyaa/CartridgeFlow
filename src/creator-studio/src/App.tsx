import { FormEvent, useEffect, useMemo, useState } from 'react'
import { ApiError, creatorApi, type CapabilityGap, type Creator, type Proposal, type TrustedRecipeNode } from './api'
import './App.css'

const id = (prefix: string) => `${prefix}.${crypto.randomUUID()}`
const errorText = (error: unknown) => {
  if (error instanceof ApiError) {
    if (error.code === 'AI_CREATOR_FLOW_MODEL_UNBOUND') return '整体编排模型尚未配置，请先在 Developer Console 配置模型。'
    if (error.code === 'AI_CREATOR_NODE_MODEL_UNBOUND') return '节点深化模型尚未配置，请先在 Developer Console 配置模型。'
    return error.message
  }
  return error instanceof Error ? error.message : '请求失败。'
}

function JourneyCanvas({ creator, onNode }: { creator?: Creator; onNode?: (id: string) => void }) {
  const nodes = creator?.trusted_recipe.nodes ?? []
  const relations = creator?.trusted_recipe.relations ?? []
  const width = Math.max(520, nodes.length * 210 + 40)
  const positions = new Map(nodes.map((node, index) => [node.id, { x: 24 + index * 210, y: 44 }]))
  return <section className="journey-panel" aria-labelledby="journey-heading">
    <div className="section-heading"><h2 id="journey-heading">项目链路图</h2><p>{creator ? `${nodes.length} 个可信能力实例` : '等待创作目标'}</p></div>
    <svg aria-label="Project journey graph" className="journey-canvas" viewBox={`0 0 ${width} 150`} role="img">
      {relations.map((edge) => { const from = positions.get(edge.from_node_id); const to = positions.get(edge.to_node_id); return from && to ? <line key={edge.id} x1={from.x + 168} y1={80} x2={to.x} y2={80}><title>{edge.relation}</title></line> : null })}
      {nodes.length ? nodes.map((node) => { const point = positions.get(node.id)!; const frozen = creator!.frozen_steps.includes(node.id); return <g key={node.id} className={`journey-node status-${frozen ? 'trusted' : 'untrusted'}`} transform={`translate(${point.x} ${point.y})`} role="button" tabIndex={0} onClick={() => onNode?.(node.id)} onKeyDown={(event) => { if (event.key === 'Enter') onNode?.(node.id) }}><rect width="168" height="72" rx="4"/><text className="journey-node-label" x="10" y="28">{node.label.slice(0, 18)}</text><text className="journey-node-meta" x="10" y="52">{frozen ? '可信' : '待确认'} · r{node.preset.revision}</text></g> }) : <g className="journey-node status-empty" transform="translate(24 44)"><rect width="168" height="72" rx="4"/><text className="journey-node-label" x="10" y="28">开始创作</text><text className="journey-node-meta" x="10" y="52">start · empty</text></g>}
    </svg>
  </section>
}

function FieldEditor({ node, values, onChange }: { node: TrustedRecipeNode; values: Record<string, unknown>; onChange: (values: Record<string, unknown>) => void }) {
  return <div className="field-list">{node.editable_fields.map((field) => {
    const value = values[field.id] ?? field.default ?? ''
    if (field.value_type === 'boolean') return <label key={field.id} className="check-field"><input type="checkbox" checked={Boolean(value)} onChange={(event) => onChange({ ...values, [field.id]: event.target.checked })}/>{field.label}</label>
    if (field.value_type === 'number') return <label key={field.id}>{field.label}<input type="number" value={Number(value)} onChange={(event) => onChange({ ...values, [field.id]: Number(event.target.value) })}/></label>
    if (field.value_type === 'string_list') return <label key={field.id}>{field.label}<textarea value={Array.isArray(value) ? value.join('\n') : ''} onChange={(event) => onChange({ ...values, [field.id]: event.target.value.split('\n').map((item) => item.trim()).filter(Boolean) })}/></label>
    return <label key={field.id}>{field.label}<input value={String(value)} onChange={(event) => onChange({ ...values, [field.id]: event.target.value })}/></label>
  })}</div>
}

export default function App() {
  const projectPath = window.location.pathname.match(/^\/projects\/([^/]+)\/creator$/)
  const [creator, setCreator] = useState<Creator | null>(null)
  const [goal, setGoal] = useState('')
  const [gap, setGap] = useState<CapabilityGap | null>(null)
  const [selectedId, setSelectedId] = useState('')
  const [draftValues, setDraftValues] = useState<Record<string, unknown>>({})
  const [prompt, setPrompt] = useState('')
  const [proposal, setProposal] = useState<Proposal | null>(null)
  const [impact, setImpact] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    const projectId = projectPath?.[1] ? decodeURIComponent(projectPath[1]) : ''
    const sessionId = localStorage.getItem('creator-session-id') || ''
    const load = projectId ? creatorApi.getProject(projectId) : sessionId ? creatorApi.get(sessionId) : null
    load?.then(({ creator }) => setCreator(creator)).catch(() => localStorage.removeItem('creator-session-id'))
  }, [])

  const selected = useMemo(() => creator?.trusted_recipe.nodes.find((node) => node.id === selectedId) ?? null, [creator, selectedId])
  const save = (next: Creator) => { setCreator(next); localStorage.setItem('creator-session-id', next.session_id) }
  const openNode = (nodeId: string) => { const node = creator?.trusted_recipe.nodes.find((item) => item.id === nodeId); if (!node) return; setSelectedId(nodeId); setDraftValues(node.values); setProposal(null); setImpact('') }

  const compose = async (event: FormEvent) => {
    event.preventDefault(); setBusy(true); setNotice(''); setGap(null)
    try {
      const sessionId = id('creator'); const projectId = id('project')
      const result = await creatorApi.compose({ session_id: sessionId, project_id: projectId, goal })
      if (result.capability_gap) { setGap(result.capability_gap); return }
      if (!result.creator) throw new Error('整体草稿没有返回。')
      history.replaceState({}, '', `/projects/${encodeURIComponent(projectId)}/creator`); save(result.creator); setNotice('整体草稿已生成，请逐个审核节点。')
    } catch (error) { setNotice(errorText(error)) } finally { setBusy(false) }
  }

  const stageValues = async () => {
    if (!creator || !selected) return
    setBusy(true)
    try {
      const result = await creatorApi.propose(creator.session_id, { expected_revision: creator.revision, author: 'creator', summary: `调整节点：${selected.label}`, changes: [{ id: `edit.${selected.id}.${creator.revision}`, target_id: selected.id, operation: 'set_creator_binding', value: draftValues }] })
      setProposal(result.proposal); setImpact(''); setNotice('节点修改已进入审阅。')
    } catch (error) { setNotice(errorText(error)) } finally { setBusy(false) }
  }

  const askAi = async () => {
    if (!creator || !selected || !prompt.trim()) return
    setBusy(true)
    try { const result = await creatorApi.nodeAi(creator.session_id, selected.id, { prompt, expected_revision: creator.revision }); setProposal(result.proposal); setImpact(''); setNotice('AI 节点建议已进入审阅。') }
    catch (error) { setNotice(errorText(error)) } finally { setBusy(false) }
  }

  const preview = async () => {
    if (!creator || !proposal) return
    try { const result = await creatorApi.preview(creator.session_id, proposal.proposal_id, {}); setImpact(result.impact.plain_summary || '该修改只影响当前节点。') }
    catch (error) { setNotice(errorText(error)) }
  }

  const accept = async () => {
    if (!creator || !proposal) return
    setBusy(true)
    try { const result = await creatorApi.accept(creator.session_id, proposal.proposal_id, {}); save(result.creator); const node = result.creator.trusted_recipe.nodes.find((item) => item.id === selectedId); if (node) setDraftValues(node.values); setProposal(null); setImpact(''); setNotice('节点修改已接受。') }
    catch (error) { setNotice(errorText(error)) } finally { setBusy(false) }
  }

  const reject = async () => {
    if (!creator || !proposal) return
    try { const result = await creatorApi.reject(creator.session_id, proposal.proposal_id, { reason: 'Creator rejected the suggestion.' }); save(result.creator); setProposal(null); setImpact(''); setNotice('已拒绝该建议。') }
    catch (error) { setNotice(errorText(error)) }
  }

  const trust = async () => {
    if (!creator || !selected) return
    setBusy(true)
    try { await creatorApi.freeze(creator.session_id, { step_ids: [selected.id], author: 'creator', summary: 'Creator confirmed this trusted node instance.' }); const result = await creatorApi.get(creator.session_id); save(result.creator); setNotice('该节点已确认可信。') }
    catch (error) { setNotice(errorText(error)) } finally { setBusy(false) }
  }

  if (!creator) return <main className="app-shell"><header className="app-header"><p className="eyebrow">Creator Studio</p><h1>CartridgeFlow 创作工作室</h1><p>从空画布开始，把想法变成可审核的动态链路。</p></header><JourneyCanvas/><form className="intent-form" onSubmit={compose}><label>想在这张画布上完成什么？<textarea aria-label="Creative intent" value={goal} onChange={(event) => setGoal(event.target.value)} required/></label><button type="submit" disabled={busy || goal.trim().length < 3}>生成整体草稿</button></form>{gap && <section className="gap" aria-labelledby="gap-title"><h2 id="gap-title">还缺少可信能力</h2><ul>{gap.needed_capabilities.map((item) => <li key={item}>{item}</li>)}</ul><p>请先由 Developer 新增或审核对应节点预设，再重新生成。</p></section>}{notice && <p role="status">{notice}</p>}</main>

  return <main className="app-shell"><header className="app-header"><p className="eyebrow">Creator Studio</p><h1>{creator.intent}</h1><div className="header-actions"><span className="revision">修订 {creator.revision}</span>{creator.generation_readiness.ready ? <a href={`/projects/${encodeURIComponent(creator.project_id)}/developer`}>进入工程确认</a> : <span>逐个确认节点后进入工程</span>}</div></header>{notice && <p role="status">{notice}</p>}<JourneyCanvas creator={creator} onNode={openNode}/>
    {!selected ? <section aria-labelledby="draft-title"><h2 id="draft-title">整体草稿</h2><p>链路由 AI 动态组合，每个节点都来自 Developer 提供的可信预设。现在逐个打开节点审核。</p><ul className="node-list">{creator.trusted_recipe.nodes.map((node) => <li key={node.id}><button className="node-row" onClick={() => openNode(node.id)}><strong>{node.label}</strong><span>{creator.frozen_steps.includes(node.id) ? '已可信' : '待确认'}</span></button></li>)}</ul></section> : <section aria-labelledby="node-title"><div className="section-heading"><h2 id="node-title">节点深化：{selected.label}</h2><button className="secondary" onClick={() => setSelectedId('')}>返回整体草稿</button></div><p>预设 {selected.preset.id} · 修订 {selected.preset.revision}</p><FieldEditor node={selected} values={draftValues} onChange={setDraftValues}/><button onClick={stageValues} disabled={busy}>提交字段修改审阅</button><label className="ai-request">继续和 AI 对齐这个节点<textarea aria-label="Node refinement request" value={prompt} onChange={(event) => setPrompt(event.target.value)}/></label><button aria-label="Request node AI proposal" onClick={askAi} disabled={busy || !prompt.trim()}>请求 AI 节点建议</button>{!creator.frozen_steps.includes(selected.id) && <button className="trust" onClick={trust} disabled={busy || Boolean(proposal)}>确认节点可信</button>}</section>}
    <section aria-labelledby="review-title"><h2 id="review-title">变更审阅</h2>{proposal ? <><p>{proposal.summary}</p>{impact ? <p>{impact}</p> : <button onClick={preview}>检查影响</button>}<button className="secondary" onClick={reject} disabled={busy}>拒绝</button><button onClick={accept} disabled={busy || !impact}>接受修改</button></> : <p>没有待审阅的变更。</p>}</section>
    <section aria-labelledby="readiness-title"><h2 id="readiness-title">工程准备</h2>{creator.blocked_findings.length ? <ul>{creator.blocked_findings.map((finding) => <li key={`${finding.code}:${finding.step_id || ''}`}>{finding.message}</li>)}</ul> : <p>Creator 设计已完成，可以进入 Developer 确认映射并物化。</p>}</section>
  </main>
}
