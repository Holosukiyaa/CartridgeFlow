import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'

import {
  controlCartridgeRun,
  deleteCartridgeRun,
  fetchCartridgeRunDiagnostics,
  fetchCartridgeRuns,
  fetchLabFlows,
  type FlowEvent,
  type FlowLabItem,
  type RunDiagnosticBundle,
  type RunResult,
} from '../api.ts'

const STATUS_LABELS: Record<string, string> = {
  completed: '已完成',
  failed: '失败',
  interrupted: '已中断',
  cancelled: '已取消',
  paused_waiting_user: '等待输入',
  paused: '已暂停',
  running: '运行中',
  retrying: '重试中',
  recovering: '恢复中',
  rolling_back: '回滚中',
  created: '已创建',
}

const STATUS_FILTERS = [
  { value: 'all', label: '全部' },
  { value: 'attention', label: '异常' },
  { value: 'active', label: '运行中' },
  { value: 'completed', label: '已完成' },
] as const

type StatusFilter = (typeof STATUS_FILTERS)[number]['value']

function initialStatusFilter(value: string | null): StatusFilter {
  if (value === 'failed' || value === 'interrupted') return 'attention'
  return STATUS_FILTERS.some((item) => item.value === value) ? value as StatusFilter : 'all'
}

function localDateKey(value?: string) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
}

function formatTime(value?: string) {
  if (!value) return '时间未知'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false }).format(date)
}

function formatLongTime(value?: string) {
  if (!value) return '时间未知'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }).format(date)
}

function isActiveStatus(status: string) {
  return ['running', 'retrying', 'recovering', 'rolling_back', 'created'].includes(status)
}

function statusClass(status: string) {
  if (status === 'completed') return 'ok'
  if (status === 'failed' || status === 'cancelled') return 'danger'
  if (isActiveStatus(status)) return 'active'
  return 'muted'
}

function eventLabel(event: FlowEvent) {
  if (event.type === 'lab_node_failed' || event.type === 'run_failed') return '失败'
  if (event.type?.includes('checkpoint')) return '检查点'
  if (event.type?.includes('retry') || event.type?.includes('recover')) return '恢复'
  if (event.type?.includes('interaction')) return '交互'
  return '事件'
}

function eventMessage(event: FlowEvent) {
  const data = event.data as any
  const envelope = data?.error_envelope || data?.error
  if (envelope?.code) return `[${envelope.code}] ${envelope.message || event.message || '运行错误'}`
  return event.message || data?.output || data?.action || '状态已更新'
}

function collectArtifacts(run: RunResult) {
  return [...(run.delivery?.artifacts || []), ...(run.artifacts || [])].filter((item, index, items) => {
    const key = item.artifact_id || item.path || item.name
    return items.findIndex((candidate) => (candidate.artifact_id || candidate.path || candidate.name) === key) === index
  })
}

function artifactKind(item: any) {
  const mime = String(item?.mime_type || '').toLowerCase()
  const name = String(item?.name || '').toLowerCase()
  if (mime.includes('html') || name.endsWith('.html')) return 'html'
  if (mime.startsWith('image/') || /\.(png|jpe?g|gif|webp)$/i.test(name)) return 'image'
  if (mime.startsWith('video/') || /\.(mp4|webm|mov)$/i.test(name)) return 'video'
  return 'file'
}

function buildLatestDiagnosticPayload(diagnostic: RunDiagnosticBundle) {
  const run = diagnostic.run
  const latestEvent = diagnostic.events.at(-1) || null
  const latestCheckpoint = diagnostic.checkpoints.at(-1) || null
  const error = run.error || run.errors?.at(-1) || null
  return {
    schema: 'cartridgeflow.latest_diagnostic.v1',
    generated_at: diagnostic.generated_at,
    run_id: diagnostic.run_id,
    cartridge_id: diagnostic.cartridge_id,
    status: run.status,
    current_state: run.current_state,
    error,
    latest_event: latestEvent,
    latest_checkpoint: latestCheckpoint,
    summary: diagnostic.summary,
  }
}

export default function RunDiagnosticsPage() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const [runs, setRuns] = useState<RunResult[]>([])
  const [flows, setFlows] = useState<FlowLabItem[]>([])
  const [selectedId, setSelectedId] = useState('')
  const [diagnostic, setDiagnostic] = useState<RunDiagnosticBundle | null>(null)
  const [filter, setFilter] = useState<StatusFilter>(() => initialStatusFilter(searchParams.get('status')))
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(true)
  const [detailLoading, setDetailLoading] = useState(false)
  const [busy, setBusy] = useState('')
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')
  const dateFilter = searchParams.get('date') || ''
  const rangeFilter = searchParams.get('range') === '7d' ? '7d' : ''

  const flowNames = useMemo(() => new Map(flows.map((flow) => [flow.id, flow.name])), [flows])
  const sortedRuns = useMemo(() => [...runs].sort((a, b) => String(b.updated_at || b.created_at || '').localeCompare(String(a.updated_at || a.created_at || ''))), [runs])
  const visibleRuns = useMemo(() => {
    const needle = query.trim().toLowerCase()
    const rangeStart = new Date()
    rangeStart.setHours(0, 0, 0, 0)
    rangeStart.setDate(rangeStart.getDate() - 6)
    return sortedRuns.filter((run) => {
      const statusMatch = filter === 'all'
        || (filter === 'attention' ? ['failed', 'interrupted', 'cancelled'].includes(run.status) : filter === 'active' ? isActiveStatus(run.status) : run.status === filter)
      if (!statusMatch) return false
      const timestamp = new Date(run.created_at || run.updated_at || '').getTime()
      if (dateFilter && localDateKey(run.created_at || run.updated_at) !== dateFilter) return false
      if (rangeFilter && (!timestamp || timestamp < rangeStart.getTime())) return false
      if (!needle) return true
      return [run.run_id, run.cartridge_id, flowNames.get(run.cartridge_id), run.error?.code, run.current_state].some((value) => String(value || '').toLowerCase().includes(needle))
    })
  }, [dateFilter, filter, flowNames, query, rangeFilter, sortedRuns])
  const selectedRun = runs.find((run) => run.run_id === selectedId) || null
  const detailRun = diagnostic?.run || selectedRun
  const errorEnvelope = detailRun?.error || detailRun?.errors?.[detailRun.errors.length - 1]
  const artifacts = detailRun ? collectArtifacts(detailRun) : []
  const canRecoverCurrent = Boolean(detailRun && ['failed', 'interrupted', 'paused'].includes(detailRun.status))
  const canRetryCurrent = canRecoverCurrent && Boolean(
    errorEnvelope?.retryable
    || errorEnvelope?.recovery_actions?.some((action) => ['retry_node', 'retry_current_node', 'retry_source_node'].includes(action))
    || detailRun?.status === 'interrupted',
  )
  const canResumeCheckpoint = canRecoverCurrent && Boolean(diagnostic?.checkpoints?.some((item) => item.phase === 'after' && item.outcome === 'completed'))
  const counts = useMemo(() => ({
    total: runs.length,
    failed: runs.filter((run) => run.status === 'failed').length,
    active: runs.filter((run) => isActiveStatus(run.status)).length,
    completed: runs.filter((run) => run.status === 'completed').length,
  }), [runs])

  async function loadRuns(keepSelection = true) {
    setLoading(true)
    setError('')
    try {
      const [runResult, flowResult] = await Promise.all([fetchCartridgeRuns(), fetchLabFlows()])
      const nextRuns = runResult.items || []
      setRuns(nextRuns)
      setFlows(flowResult.items || [])
      if (!keepSelection || !nextRuns.some((run) => run.run_id === selectedId)) setSelectedId(nextRuns[0]?.run_id || '')
    } catch (reason: any) {
      setError(reason?.message || '运行记录读取失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void loadRuns(false) }, [])

  useEffect(() => {
    setFilter(initialStatusFilter(searchParams.get('status')))
  }, [searchParams])

  useEffect(() => {
    if (loading) return
    if (!visibleRuns.length) {
      if (selectedId) setSelectedId('')
      return
    }
    if (!visibleRuns.some((run) => run.run_id === selectedId)) setSelectedId(visibleRuns[0].run_id)
  }, [loading, selectedId, visibleRuns])

  useEffect(() => {
    if (!selectedId) { setDiagnostic(null); return }
    let active = true
    setDetailLoading(true)
    setError('')
    void fetchCartridgeRunDiagnostics(selectedId)
      .then((result) => { if (active) setDiagnostic(result) })
      .catch((reason: any) => { if (active) setError(reason?.message || '诊断证据读取失败') })
      .finally(() => { if (active) setDetailLoading(false) })
    return () => { active = false }
  }, [selectedId])

  async function recover(action: 'retry_current_node' | 'resume_checkpoint' | 'restart_run') {
    if (!selectedId) return
    if (action === 'restart_run' && !window.confirm('将使用原始输入重新开始一轮运行，确定继续？')) return
    setBusy(action)
    setNotice('')
    setError('')
    try {
      const next = await controlCartridgeRun(selectedId, action)
      setRuns((current) => [next, ...current.filter((run) => run.run_id !== next.run_id)])
      setSelectedId(next.run_id)
      setDiagnostic(await fetchCartridgeRunDiagnostics(next.run_id))
      setNotice(action === 'restart_run' ? '已创建新的运行' : '恢复动作已提交')
    } catch (reason: any) {
      setError(reason?.message || '恢复动作失败')
    } finally {
      setBusy('')
    }
  }

  async function copyDiagnostics() {
    if (!diagnostic) return
    try {
      await navigator.clipboard.writeText(JSON.stringify(buildLatestDiagnosticPayload(diagnostic), null, 2))
      setNotice('最近一次脱敏诊断已复制，可直接交给 AI 分析')
    } catch {
      setError('浏览器拒绝访问剪贴板，请使用导出按钮或检查页面权限')
    }
  }

  async function deleteSelectedRun() {
    if (!detailRun || !selectedId || isActiveStatus(detailRun.status) || detailRun.status === 'paused_waiting_user') return
    const flowName = flowNames.get(detailRun.cartridge_id) || detailRun.cartridge_id
    if (!window.confirm(`确定删除「${flowName}」的这条运行记录吗？\n\n将删除运行目录、事件、检查点和本次产物记录，不能恢复；不会删除 Flow 或全局配置。`)) return
    setBusy('delete')
    setError('')
    setNotice('')
    try {
      await deleteCartridgeRun(selectedId)
      const deletedId = selectedId
      setRuns((current) => current.filter((run) => run.run_id !== deletedId))
      setSelectedId('')
      setDiagnostic(null)
      setNotice('运行记录已删除')
    } catch (reason: any) {
      setError(reason?.message || '运行记录删除失败')
    } finally {
      setBusy('')
    }
  }

  function downloadDiagnostics() {
    if (!diagnostic) return
    const blob = new Blob([JSON.stringify(diagnostic, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `diagnostic-${diagnostic.run_id}.json`
    link.click()
    URL.revokeObjectURL(url)
    setNotice('诊断包已导出')
  }

  function applyStatusFilter(value: StatusFilter) {
    setFilter(value)
    const next = new URLSearchParams(searchParams)
    if (value === 'all') next.delete('status')
    else next.set('status', value)
    setSearchParams(next, { replace: true })
  }

  function clearScopeFilter() {
    const next = new URLSearchParams(searchParams)
    next.delete('date')
    next.delete('range')
    setSearchParams(next, { replace: true })
  }

  return (
    <main className="cf-diagnostics-page">
      <header className="cf-diagnostics-heading">
        <div>
          <span className="cf-resource-kicker">RUNTIME / DIAGNOSTICS</span>
          <h1>运行诊断</h1>
          <p>集中查看所有 Flow 的运行证据、失败原因和可安全执行的恢复动作。</p>
        </div>
        <div className="cf-diagnostics-heading-actions">
          <button type="button" onClick={() => void loadRuns()} disabled={loading}>刷新记录</button>
        </div>
      </header>

      {error && <div className="cf-diagnostics-alert danger">{error}</div>}
      {notice && <div className="cf-diagnostics-alert">{notice}</div>}

      <div className="cf-diagnostics-metrics" aria-label="运行统计">
        <div><span>全部运行</span><strong>{counts.total}</strong><small>跨所有 Flow</small></div>
        <div className={counts.failed ? 'warning' : ''}><span>失败</span><strong>{counts.failed}</strong><small>需要定位或恢复</small></div>
        <div className={counts.active ? 'active' : ''}><span>进行中</span><strong>{counts.active}</strong><small>正在执行或恢复</small></div>
        <div className="ok"><span>已完成</span><strong>{counts.completed}</strong><small>有交付结果</small></div>
      </div>

      <div className="cf-diagnostics-layout">
        <aside className="cf-diagnostics-list-panel">
          <div className="cf-diagnostics-list-head"><div><span>RUN LEDGER</span><h2>运行记录</h2></div><b>{visibleRuns.length}</b></div>
          <label className="cf-diagnostics-search"><span>搜索运行、Flow 或错误</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="run_... / Flow 名称 / 错误码" /></label>
          <div className="cf-diagnostics-filters" role="group" aria-label="运行状态筛选">
            {STATUS_FILTERS.map((item) => <button type="button" key={item.value} className={filter === item.value ? 'selected' : ''} onClick={() => applyStatusFilter(item.value)}>{item.label}</button>)}
          </div>
          <div className={`cf-diagnostics-scope ${dateFilter || rangeFilter ? '' : 'empty'}`}>
            {dateFilter || rangeFilter ? <><span>{dateFilter ? `${dateFilter} 当天` : '最近 7 天'}</span><button type="button" onClick={clearScopeFilter}>清除时间</button></> : <span>显示全部时间</span>}
          </div>
          <div className="cf-diagnostics-run-list">
            {loading ? <div className="cf-diagnostics-empty">正在读取运行记录...</div> : !visibleRuns.length ? <div className="cf-diagnostics-empty">没有符合条件的运行</div> : visibleRuns.map((run) => (
              <button type="button" key={run.run_id} className={`cf-diagnostics-run-item ${selectedId === run.run_id ? 'selected' : ''}`} onClick={() => setSelectedId(run.run_id)}>
                <i className={statusClass(run.status)} />
                <span><strong>{flowNames.get(run.cartridge_id) || run.cartridge_id}</strong><small>{run.run_id} · {run.current_state || '未知节点'}</small></span>
                <time>{formatTime(run.updated_at || run.created_at)}</time>
                <b>{STATUS_LABELS[run.status] || run.status}</b>
              </button>
            ))}
          </div>
        </aside>

        <section className="cf-diagnostics-detail cf-diagnostics-detail-card">
          {!detailRun ? <div className="cf-diagnostics-detail-empty"><strong>选择一条运行记录</strong><span>这里会显示错误证据、事件时间线、检查点和恢复入口。</span></div> : <>
            <header className="cf-diagnostics-detail-head">
              <div><span>SELECTED RUN</span><h2>{flowNames.get(detailRun.cartridge_id) || detailRun.cartridge_id}</h2><code>{detailRun.run_id}</code></div>
              <div className="cf-diagnostics-detail-actions">
                <span className={`cf-diagnostics-status ${statusClass(detailRun.status)}`}>{STATUS_LABELS[detailRun.status] || detailRun.status}</span>
                <button type="button" onClick={() => navigate(`/projects/${encodeURIComponent(detailRun.cartridge_id)}/test`)}>打开测试台</button>
                <button type="button" className="primary" onClick={copyDiagnostics} disabled={!diagnostic}>复制最近诊断</button>
                <button type="button" onClick={downloadDiagnostics} disabled={!diagnostic}>导出 JSON</button>
                <button type="button" className="danger" onClick={() => void deleteSelectedRun()} disabled={Boolean(busy) || isActiveStatus(detailRun.status) || detailRun.status === 'paused_waiting_user'}>{busy === 'delete' ? '删除中...' : '删除记录'}</button>
              </div>
            </header>

            <div className="cf-diagnostics-evidence-grid">
              <section className={`cf-diagnostics-evidence ${errorEnvelope ? 'has-error' : 'clear'}`}>
                <div className="cf-diagnostics-section-head"><div><span>ROOT CAUSE</span><h3>{errorEnvelope ? '发现结构化错误' : '没有失败错误'}</h3></div>{errorEnvelope?.code && <b>{errorEnvelope.code}</b>}</div>
                {errorEnvelope ? <>
                  <p className="cf-diagnostics-error-message">{errorEnvelope.message || '运行失败，但没有提供错误说明。'}</p>
                  <div className="cf-diagnostics-error-facts"><span>分类 <b>{errorEnvelope.category || '未知'}</b></span><span>节点 <b>{errorEnvelope.node_id || detailRun.current_state || '未知'}</b></span><span>可重试 <b>{errorEnvelope.retryable ? '是' : '否'}</b></span></div>
                  {errorEnvelope.cause_chain?.length ? <div className="cf-diagnostics-cause"><small>原因链</small>{errorEnvelope.cause_chain.slice(0, 3).map((cause, index) => <p key={`${cause.type}-${index}`}><b>{cause.type}</b>{cause.message}</p>)}</div> : null}
                </> : <p className="cf-diagnostics-clear-copy">当前运行没有错误信封，可以从事件和检查点确认完整执行路径。</p>}
              </section>

              <section className="cf-diagnostics-evidence">
                <div className="cf-diagnostics-section-head"><div><span>RECOVERY</span><h3>恢复动作</h3></div><b>{errorEnvelope?.recoverable ? '允许' : '按策略'}</b></div>
                <p className="cf-diagnostics-recovery-copy">底座会根据节点副作用和检查点决定哪些动作可以安全执行。</p>
                <div className="cf-diagnostics-recovery-actions">
                  <button type="button" disabled={Boolean(busy) || !canRetryCurrent} onClick={() => void recover('retry_current_node')}>{busy === 'retry_current_node' ? '提交中...' : '重试当前节点'}</button>
                  <button type="button" disabled={Boolean(busy) || !canResumeCheckpoint} onClick={() => void recover('resume_checkpoint')}>{busy === 'resume_checkpoint' ? '提交中...' : '从检查点继续'}</button>
                  <button type="button" className="quiet" disabled={Boolean(busy)} onClick={() => void recover('restart_run')}>{busy === 'restart_run' ? '提交中...' : '使用原始输入重开'}</button>
                </div>
              </section>
            </div>

            <div className="cf-diagnostics-detail-grid">
              <section className="cf-diagnostics-evidence">
                <div className="cf-diagnostics-section-head"><div><span>EVENT TIMELINE</span><h3>事件时间线</h3></div><b>{diagnostic?.summary.event_count || 0}</b></div>
                <div className="cf-diagnostics-event-list">{detailLoading ? <div className="cf-diagnostics-empty">正在读取诊断证据...</div> : !(diagnostic?.events || []).length ? <div className="cf-diagnostics-empty">没有事件记录</div> : diagnostic?.events.map((event, index) => <div className="cf-diagnostics-event" key={`${event.created_at || event.timestamp || 'event'}-${index}`}><time>{formatLongTime(event.created_at || event.timestamp)}</time><i className={event.type?.includes('failed') ? 'danger' : event.type?.includes('completed') ? 'ok' : ''} /><span><b>{eventLabel(event)}</b><strong>{event.state || event.type || 'system'}</strong><p>{eventMessage(event)}</p></span></div>)}</div>
              </section>

              <section className="cf-diagnostics-evidence">
                <div className="cf-diagnostics-section-head"><div><span>CHECKPOINTS</span><h3>检查点</h3></div><b>{diagnostic?.summary.checkpoint_count || 0}</b></div>
                <div className="cf-diagnostics-checkpoint-list">{(diagnostic?.checkpoints || []).slice().reverse().map((checkpoint: any) => <div className="cf-diagnostics-checkpoint" key={checkpoint.checkpoint_id}><i className={checkpoint.outcome === 'completed' ? 'ok' : 'warning'} /><span><strong>{checkpoint.node_id || '未知节点'}</strong><small>{checkpoint.phase} · {checkpoint.outcome}</small></span><time>{formatTime(checkpoint.created_at)}</time></div>)}{!detailLoading && !(diagnostic?.checkpoints || []).length && <div className="cf-diagnostics-empty">这个运行还没有持久化检查点</div>}</div>
              </section>
            </div>

            <section className="cf-diagnostics-evidence cf-diagnostics-artifacts">
              <div className="cf-diagnostics-section-head"><div><span>DELIVERY</span><h3>产物与交付</h3></div><b>{artifacts.length}</b></div>
              {detailRun.delivery?.summary && <p className="cf-diagnostics-delivery-summary">{detailRun.delivery.summary}</p>}
              {!artifacts.length ? <div className="cf-diagnostics-empty">这个运行还没有可预览的产物</div> : <div className="cf-diagnostics-artifact-list">{artifacts.map((item: any, index) => { const kind = artifactKind(item); return <article key={`${item.artifact_id || item.name}-${index}`}><div><strong>{item.name}</strong><small>{item.mime_type || item.type || kind}</small></div>{kind === 'html' && item.url ? <iframe title={item.name} src={item.url} /> : kind === 'image' && item.url ? <img src={item.url} alt={item.name} /> : kind === 'video' && item.url ? <video controls src={item.url} /> : <code>{item.display_path || item.path || '可下载文件'}</code>}</article> })}</div>}
            </section>
          </>}
        </section>
      </div>
    </main>
  )
}
