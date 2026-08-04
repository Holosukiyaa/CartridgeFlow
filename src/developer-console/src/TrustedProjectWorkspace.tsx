import { useEffect, useState } from 'react'
import { CheckCircle2, CircleAlert, Download, ShieldCheck } from 'lucide-react'
import { developerApi } from './api'
import type { AnyRecord } from './model'

const list = (value: unknown) => Array.isArray(value) ? value as AnyRecord[] : []

function ChainGraph({ nodes, relations }: { nodes: AnyRecord[]; relations: AnyRecord[] }) {
  const width = Math.max(520, nodes.length * 210 + 40)
  const points = new Map(nodes.map((node, index) => [String(node.id), { x: 24 + index * 210, y: 36 }]))
  return <svg aria-label="Project journey graph" viewBox={`0 0 ${width} 140`} width={width} height="140" role="img">
    {relations.map((edge) => { const from = points.get(String(edge.from_node_id)); const to = points.get(String(edge.to_node_id)); return from && to ? <line key={String(edge.id)} x1={from.x + 168} y1="72" x2={to.x} y2="72" stroke="currentColor"/> : null })}
    {nodes.map((node) => { const point = points.get(String(node.id))!; return <g key={String(node.id)} transform={`translate(${point.x} ${point.y})`}><rect width="168" height="72" fill="white" stroke="currentColor"/><text x="10" y="28">{String(node.label).slice(0, 18)}</text><text x="10" y="52">{String(node.preset_id)}@{String(node.preset_revision)}</text></g> })}
  </svg>
}

export function TrustedProjectWorkspace({ projectId }: { projectId: string }) {
  const [project, setProject] = useState<AnyRecord | null>(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)
  const [handoff, setHandoff] = useState<AnyRecord | null>(null)
  const load = async () => { const result = await developerApi.project(projectId); setProject(result.developer as AnyRecord) }
  useEffect(() => { load().catch((reason) => setError(reason instanceof Error ? reason.message : 'Unable to load this project.')) }, [projectId])
  if (!project) return <main><header><div><b>CARTRIDGEFLOW</b><span>Developer Console</span></div></header><div className="error">{error || 'Loading project...'}</div></main>

  const recipe = project.recipe as AnyRecord
  const readiness = project.generation_readiness as AnyRecord
  const trusted = project.trusted_recipe as AnyRecord | undefined
  const nodes = list(trusted?.nodes)
  const relations = list(trusted?.relations)
  const confirmation = trusted?.developer_confirmation as AnyRecord | null
  const candidate = (readiness?.compile_candidate as AnyRecord | undefined)?.reference

  const confirm = async () => {
    setBusy(true); setError('')
    try { await developerApi.confirmProject(String(project.project_id), Number(recipe.revision)); await load(); setNotice('当前预设修订和 Developer 映射已确认。') }
    catch (reason) { setError(reason instanceof Error ? reason.message : '确认失败。') } finally { setBusy(false) }
  }
  const createHandoff = async () => {
    if (!candidate) return
    setBusy(true); setError('')
    try { const result = await developerApi.handoffProject(String(project.project_id), Number(recipe.revision), candidate); setHandoff(result); setNotice('CF-FARP@1.5 已物化，签名 CF-CRE 已验证。') }
    catch (reason) { setError(reason instanceof Error ? reason.message : '交接失败。') } finally { setBusy(false) }
  }

  return <main><header><div><b>CARTRIDGEFLOW</b><span>Developer Console</span><small>trusted recipe materialization</small></div></header>{error && <div className="error"><CircleAlert size={16}/>{error}</div>}{notice && <div className="notice"><CheckCircle2 size={16}/>{notice}</div>}<div className="grid">
    <section className="panel topology"><h2><ShieldCheck size={17}/>同一项目链路</h2><dl><dt>项目</dt><dd>{String(project.project_id)}</dd><dt>Creator 修订</dt><dd>{String(recipe.revision)}</dd><dt>状态</dt><dd>{readiness.ready ? '可确认工程映射' : '等待 Creator 完成节点审核'}</dd></dl><div className="flowmap"><ChainGraph nodes={nodes} relations={relations}/></div></section>
    <section className="panel"><h2>可信节点映射</h2><div className="revision-list">{nodes.map((node) => <div key={String(node.id)}><b>{String(node.label)}</b><span>{String(node.preset_id)}@{String(node.preset_revision)}</span><code>{String(node.developer_mapping_key)}</code><small>{node.mapping_current ? 'revision current' : 'revision stale'}</small></div>)}</div></section>
    <section className="panel"><h2>物化与交接</h2><dl><dt>协议链</dt><dd>CF-TUNING@1.4 → CF-FARP@1.5 → CF-CRE@1</dd><dt>Developer 确认</dt><dd>{confirmation ? String(confirmation.digest) : 'pending'}</dd></dl><div className="tuning-actions">{!confirmation && <button onClick={confirm} disabled={busy || !readiness.ready}><CheckCircle2 size={15}/>确认映射</button>}{confirmation && !handoff && <button onClick={createHandoff} disabled={busy || !candidate}><Download size={15}/>生成签名交接</button>}{handoff && <a href={String(handoff.url)}>下载 {String(handoff.filename)}</a>}<a href={String(project.creator_url)}>返回 Creator Studio</a></div></section>
  </div></main>
}
