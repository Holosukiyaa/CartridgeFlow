import { useEffect, useMemo, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { Activity, Boxes, Braces, CheckCircle2, CircleAlert, FileSearch, GitCompareArrows, Network, RefreshCw, ShieldCheck, SlidersHorizontal } from 'lucide-react'
import { developerApi } from './api'
import { json, pathDiff, semanticProjection, type AnyRecord } from './model'
import './styles.css'

type Data = Record<string, AnyRecord | null>
const value = (item: unknown) => typeof item === 'string' ? item : json(item)
const array = (value: unknown) => Array.isArray(value) ? value as AnyRecord[] : []
const status = (good: unknown) => good === true || good === 'ok' || good === 'ready' || good === 'passed'

function Panel({ title, icon, children, className = '' }: { title: string; icon: React.ReactNode; children: React.ReactNode; className?: string }) { return <section className={`panel ${className}`}><h2>{icon}{title}</h2>{children}</section> }
function App() {
  const [flows, setFlows] = useState<AnyRecord[]>([]); const [id, setId] = useState(''); const [data, setData] = useState<Data>({}); const [loading, setLoading] = useState(false); const [error, setError] = useState(''); const [view, setView] = useState<'semantic' | 'source'>('semantic')
  const load = async (flowId = id) => { if (!flowId) return; setLoading(true); setError(''); try {
    const detail = await developerApi.flow(flowId); const editable = Boolean((detail.cartridge as AnyRecord)?.editable)
    const files = editable ? await developerApi.files(flowId) : { files: {} }
    const [resources, tuning, preflight, conformance] = await Promise.all([developerApi.resources(flowId), editable ? developerApi.tuning(flowId) : Promise.resolve(null), developerApi.preflight(flowId), developerApi.conformance()])
    const analysis = editable ? await developerApi.analyze(flowId, (files.files as AnyRecord) ?? {}) : null
    const validation = editable ? await developerApi.validate(flowId, (files.files as AnyRecord) ?? {}) : null
    setData({ detail, files, resources, tuning, preflight, conformance, analysis, validation })
  } catch (e) { setError(e instanceof Error ? e.message : 'Unable to reach the declared API') } finally { setLoading(false) } }
  useEffect(() => { developerApi.flows().then(({ items }) => { setFlows(items); const next = new URLSearchParams(location.search).get('flowId') || String(items[0]?.id || ''); setId(next); if (next) load(next) }).catch((e) => setError(e.message)) }, [])
  const semantic = useMemo(() => semanticProjection(data.detail ?? {}, data.analysis, data.resources), [data])
  const graph = (semantic.topology as AnyRecord | undefined) ?? {}; const nodes = array(graph.nodes); const edges = array(graph.edges)
  const revisions = array((data.tuning?.repository as AnyRecord | undefined)?.revisions); const raw = data.files?.files ?? {}; const materialized = (data.tuning?.tuning_context as AnyRecord | undefined) ?? {}; const diff = pathDiff(raw, materialized)
  return <main>
    <header><div><b>CARTRIDGEFLOW</b><span>Developer Console</span><small>declaration API only / development diagnostics</small></div><div className="header-actions"><select aria-label="Flow" value={id} onChange={(e) => { setId(e.target.value); load(e.target.value) }}>{flows.map((flow) => <option key={String(flow.id)} value={String(flow.id)}>{String(flow.name || flow.id)}</option>)}</select><button title="Refresh all declared projections" onClick={() => load()} disabled={loading}><RefreshCw size={16} />{loading ? 'Loading' : 'Refresh'}</button></div></header>
    {error && <div className="error"><CircleAlert size={16}/>{error}</div>}
    <nav><button className={view === 'semantic' ? 'active' : ''} onClick={() => setView('semantic')}><Network size={15}/>Semantic projection</button><button className={view === 'source' ? 'active' : ''} onClick={() => setView('source')}><Braces size={15}/>Raw declarations</button><span>Secrets are redacted at the client boundary.</span></nav>
    <div className="summary"><span><b>{Number(graph.node_count ?? nodes.length)}</b> nodes</span><span><b>{Number(graph.edge_count ?? edges.length)}</b> edges</span><span><b>{array((data.resources?.tools)).length}</b> tools</span><span className={status((data.validation as AnyRecord)?.valid) ? 'good' : 'warn'}>{status((data.validation as AnyRecord)?.valid) ? <CheckCircle2 size={15}/> : <CircleAlert size={15}/>} validation {String((data.validation as AnyRecord)?.valid ?? 'pending')}</span></div>
    {view === 'source' ? <Panel title="Raw declaration bundle" icon={<Braces size={17}/>} className="source"><pre>{json(raw)}</pre></Panel> : <div className="grid">
      <Panel title="Root Flow topology" icon={<Network size={17}/>} className="topology"><div className="flowmap">{nodes.map((node, index) => <div className="node" key={String(node.id)}><em>{index + 1}</em><strong>{String(node.title || node.label || node.id)}</strong><small>{String(node.type || node.kind || 'state')}</small></div>)}</div><div className="edges">{edges.map((edge, index) => <code key={index}>{String(edge.from || edge.source)} <span>--{String(edge.kind || edge.scope || 'sequence')}--&gt;</span> {String(edge.to || edge.target)}</code>)}</div></Panel>
      <Panel title="Protocol identity & typed contracts" icon={<ShieldCheck size={17}/>}><dl><dt>Protocol</dt><dd>{value((semantic.identity as AnyRecord)?.protocol)}</dd><dt>Flow</dt><dd>{String((semantic.identity as AnyRecord)?.id || 'unresolved')}</dd><dt>Contracts</dt><dd>{value(semantic.contracts)}</dd></dl></Panel>
      <Panel title="Prompts, recipes & materialization" icon={<SlidersHorizontal size={17}/>}><dl><dt>Recipe revision</dt><dd>{String((data.tuning?.repository as AnyRecord)?.repository_revision ?? 'not declared')}</dd><dt>Active release</dt><dd>{String((data.tuning?.repository as AnyRecord)?.active_release_id ?? 'draft')}</dd><dt>Materialization digest</dt><dd className="mono">{String(materialized.materialization_digest ?? 'pending')}</dd></dl><div className="revision-list">{revisions.slice(-4).reverse().map((revision) => <div key={String(revision.id)}><b>{String(revision.node_id)}</b><span>{String(revision.message || revision.id)}</span><code>{value(revision.patch)}</code></div>)}</div></Panel>
      <Panel title="Model, tool & source bindings" icon={<Boxes size={17}/>}><pre>{json(semantic.bindings)}</pre><div className="tool-list">{array(data.resources?.tools).map((tool) => <span key={String(tool.id || tool.name)}>{String(tool.name || tool.id)} <i>{String(tool.status || tool.type || 'declared')}</i></span>)}</div></Panel>
      <Panel title="Precise declaration diff" icon={<GitCompareArrows size={17}/>}><p className="muted">Raw declarations versus the declared tuning materialization.</p>{diff.length ? <div className="diff">{diff.slice(0, 12).map((change) => <div key={change.path}><code>{change.path}</code><del>{value(change.before)}</del><ins>{value(change.after)}</ins></div>)}</div> : <p className="muted">No materialized delta is declared.</p>}</Panel>
      <Panel title="Validation, package preflight & probes" icon={<FileSearch size={17}/>}><div className="checks">{['compatibility', 'certification', 'environment', 'dependencies', 'models', 'resources', 'package_hygiene', 'portability'].map((key) => { const item = data.preflight?.[key] as AnyRecord | undefined; const state = item?.status ?? item?.ok; return <div key={key} className={status(state) ? 'ok' : 'attention'}>{status(state) ? <CheckCircle2 size={15}/> : <CircleAlert size={15}/>}<span>{key.replace('_', ' ')}</span><b>{String(state ?? 'unavailable')}</b></div> })}</div><h3><Activity size={15}/>Development probes</h3><pre>{json({ validation: data.validation, analysis_findings: data.analysis?.findings, conformance: data.conformance?.report })}</pre></Panel>
    </div>}
  </main>
}
createRoot(document.getElementById('root')!).render(<App />)
