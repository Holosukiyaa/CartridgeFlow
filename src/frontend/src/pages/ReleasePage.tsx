import { useEffect, useMemo, useRef, useState } from 'react'
import { fetchLabFlows, fetchStudioPackages, fetchStudioReleasePreflight, packageCartridge, type FlowLabItem, type StudioPackageItem, type StudioReleasePreflight } from '../api.ts'
import PrimaryPageHeader from '../components/PrimaryPageHeader.tsx'

const AREA_LABELS: Record<string, string> = { compatibility: '兼容性', environment: '环境', dependencies: '依赖', models: '模型', resources: '本地资源', package_hygiene: '发布包卫生' }

function formatBytes(value: number) {
  if (value < 1024) return `${value} B`
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`
  return `${(value / 1024 / 1024).toFixed(1)} MB`
}

function statusLabel(status?: string) {
  if (status === 'ok' || status === 'ready' || status === 'certified' || status === 'compatible') return '通过'
  if (status === 'blocked') return '阻塞'
  if (status === 'warning' || status === 'actionable') return '注意'
  if (status === 'not_certified') return '未认证'
  return status || '待检查'
}

function statusTone(status?: string) {
  if (status === 'ok' || status === 'ready' || status === 'certified' || status === 'compatible') return 'ok'
  if (status === 'blocked') return 'blocked'
  if (status === 'warning' || status === 'actionable') return 'warning'
  return 'pending'
}

function formatDate(value: string) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false }).format(date)
}

export default function ReleasePage() {
  const [flows, setFlows] = useState<FlowLabItem[]>([])
  const [selectedId, setSelectedId] = useState('')
  const [preflight, setPreflight] = useState<StudioReleasePreflight | null>(null)
  const [history, setHistory] = useState<StudioPackageItem[]>([])
  const [packageMode, setPackageMode] = useState<'dev' | 'production'>('dev')
  const [loading, setLoading] = useState(true)
  const [preflightLoading, setPreflightLoading] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const [packaging, setPackaging] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState<{ filename: string; url: string; size: number } | null>(null)
  const selectionRequest = useRef(0)

  const selectedFlow = flows.find((flow) => flow.id === selectedId)
  const selectedHistory = useMemo(() => history.filter((item) => !selectedId || item.cartridge_id === selectedId), [history, selectedId])

  async function load() {
    setLoading(true)
    setError('')
    try {
      const [flowResult, historyResult] = await Promise.all([fetchLabFlows(), fetchStudioPackages()])
      const items = flowResult.items || []
      setFlows(items)
      setHistory(historyResult.items || [])
      const stored = selectedId || localStorage.getItem('cf.studio.release_project') || ''
      const preferred = items.some((item) => item.id === stored) ? stored : items[0]?.id || ''
      if (preferred) await selectCartridge(preferred, items)
    } catch (reason: any) {
      setError(reason?.message || '读取发布状态失败')
    } finally {
      setLoading(false)
    }
  }

  async function selectCartridge(id: string, availableFlows = flows) {
    if (!availableFlows.some((flow) => flow.id === id)) return
    const requestId = ++selectionRequest.current
    setSelectedId(id)
    setNotice(null)
    setError('')
    setPreflight(null)
    setPreflightLoading(true)
    localStorage.setItem('cf.studio.release_project', id)
    try {
      const result = await fetchStudioReleasePreflight(id)
      if (selectionRequest.current === requestId) setPreflight(result)
    } catch (reason: any) {
      if (selectionRequest.current === requestId) {
        setError(reason?.message || '发布预检失败')
        setPreflight(null)
      }
    } finally {
      if (selectionRequest.current === requestId) setPreflightLoading(false)
    }
  }

  useEffect(() => { void load() }, [])

  async function createPackage() {
    if (!selectedId) return
    setPackaging(true)
    setError('')
    try {
      const result = await packageCartridge(selectedId, packageMode)
      setNotice({ filename: result.filename, url: result.url, size: result.size })
      const historyResult = await fetchStudioPackages()
      setHistory(historyResult.items || [])
      setPreflight(await fetchStudioReleasePreflight(selectedId))
    } catch (reason: any) {
      setError(reason?.message || '卡带打包失败')
    } finally {
      setPackaging(false)
    }
  }

  async function refreshPreflight() {
    if (!selectedId) return
    setRefreshing(true)
    setError('')
    try {
      setPreflight(await fetchStudioReleasePreflight(selectedId))
      const historyResult = await fetchStudioPackages()
      setHistory(historyResult.items || [])
    } catch (reason: any) {
      setError(reason?.message || '发布预检失败')
    } finally {
      setRefreshing(false)
    }
  }

  const checks = preflight ? [
    { id: 'compatibility', label: '协议兼容', status: preflight.compatibility.status, count: preflight.compatibility.summary?.blocker || 0, detail: `${preflight.compatibility.summary?.warning || 0} 项警告` },
    { id: 'environment', label: '运行环境', status: preflight.environment.status, count: preflight.environment.items?.length || 0, detail: preflight.environment.summary || '环境检查' },
    { id: 'dependencies', label: '卡带依赖', status: preflight.dependencies.status, count: preflight.dependencies.items?.length || 0, detail: preflight.dependencies.summary || '依赖检查' },
    { id: 'models', label: '模型配方', status: preflight.models.status, count: preflight.models.items?.length || 0, detail: '本机连接状态' },
    { id: 'resources', label: '本地工具', status: preflight.resources.status, count: preflight.resources.items?.length || 0, detail: 'MCP、远程 API 与插件' },
    { id: 'package_hygiene', label: '发布包卫生', status: preflight.package_hygiene.status, count: preflight.package_hygiene.items?.length || 0, detail: `${preflight.package_hygiene.scanned_files || 0} 个文件已扫描` },
  ] : []
  const canPackage = packageMode === 'production' ? preflight?.production_ready : preflight?.dev_ready
  const blockerCount = preflight?.issues.filter((issue) => issue.severity === 'blocker').length || 0
  const warningCount = Math.max(0, (preflight?.issues.length || 0) - blockerCount)
  const passedChecks = checks.filter((check) => statusTone(check.status) === 'ok').length
  const packageModeTitle = packageMode === 'production' ? '生产包' : '开发包'
  const packageModeDescription = packageMode === 'production' ? '用于正式交付，必须通过全部生产预检。' : '用于联调与验收，保留诊断信息和本地重绑描述。'

  return (
    <div className="cf-page cf-primary-page-surface cf-release-page">
      <div className="cf-page-inner cf-release-page-inner">
        <PrimaryPageHeader
          eyebrow="Delivery Pipeline"
          title="打包发布"
          description="完成交付预检、迁移检查并生成可下载的卡带包。"
          actions={(
            <div className="cf-release-page-actions">
              <span className="cf-release-history-count"><strong>{history.length}</strong><small>全部产物</small></span>
              <button type="button" onClick={() => void load()} disabled={loading}>{loading ? '同步中…' : '同步状态'}</button>
            </div>
          )}
        />

        {error && <div className="cf-resource-alert danger cf-release-alert"><span>{error}</span><button type="button" aria-label="关闭错误提示" onClick={() => setError('')}>×</button></div>}

        <div className="cf-release-shell">
          <aside className="cf-release-rail">
            <section className="cf-release-rail-panel cf-release-flow-panel">
              <header className="cf-release-panel-head"><div><span>FLOW TARGETS</span><h2>选择 Flow</h2></div><b>{flows.length}</b></header>
              <div className="cf-release-project-list">
                {flows.map((flow) => (
                  <button type="button" key={flow.id} className={selectedId === flow.id ? 'selected' : ''} disabled={packaging} onClick={() => void selectCartridge(flow.id)}>
                    <span><strong>{flow.name}</strong><code>{flow.id}</code></span>
                    <i><b>{flow.version}</b><small>{flow.editable ? 'DEV' : 'PACKAGE'}</small></i>
                  </button>
                ))}
                {!flows.length && !loading && <div className="cf-release-empty compact">还没有可打包的 Flow</div>}
              </div>
            </section>

            <section className="cf-release-rail-panel cf-release-history-panel">
              <header className="cf-release-panel-head"><div><span>PACKAGE HISTORY</span><h2>历史产物</h2></div><b>{selectedHistory.length}</b></header>
              <div className="cf-release-history-list">
                {selectedHistory.slice(0, 8).map((item) => (
                  <article key={`${item.filename}-${item.modified_at}`}>
                    <span><strong>{item.filename}</strong><small>{formatDate(item.modified_at)} · {formatBytes(item.size)}</small></span>
                    <i>{item.package_mode === 'production' ? '生产' : '开发'}</i>
                    <a href={item.url} download>下载</a>
                  </article>
                ))}
                {!selectedHistory.length && <div className="cf-release-empty compact">当前 Flow 还没有打包产物</div>}
              </div>
            </section>
          </aside>

          <main className="cf-release-stage">
            <header className="cf-release-target-head">
              <div className="cf-release-target-copy">
                <span>RELEASE TARGET</span>
                <h2>{selectedFlow?.name || '未选择 Flow'}</h2>
                {selectedFlow && <div><code>{selectedFlow.id}</code><b>v{selectedFlow.version}</b><i>{selectedFlow.editable ? '开发卡带' : '已安装卡带'}</i></div>}
              </div>
              <div className="cf-release-target-actions">
                <button type="button" className="cf-release-refresh" onClick={() => void refreshPreflight()} disabled={refreshing || preflightLoading || !selectedId}>{refreshing ? '刷新中…' : '刷新预检'}</button>
                <div className="cf-release-mode" role="group" aria-label="打包模式">
                  <button type="button" className={packageMode === 'dev' ? 'active' : ''} onClick={() => { setPackageMode('dev'); setNotice(null) }}>开发包</button>
                  <button type="button" className={packageMode === 'production' ? 'active' : ''} onClick={() => { setPackageMode('production'); setNotice(null) }}>生产包</button>
                </div>
              </div>
            </header>

            {notice && <div className="cf-release-result"><span><b>打包完成</b><strong>{notice.filename}</strong><small>{formatBytes(notice.size)}</small></span><a href={notice.url} download>下载产物</a></div>}

            {preflightLoading && <div className="cf-release-loading"><i /><strong>正在检查交付条件</strong><span>读取协议、依赖、本机绑定与发布包内容…</span></div>}

            {!preflightLoading && preflight && <>
              <section className="cf-release-readiness" aria-label="发布就绪概况">
                <div><span>预检通过</span><strong>{passedChecks}<small> / {checks.length}</small></strong><em>检查项</em></div>
                <div className={blockerCount ? 'blocked' : ''}><span>阻塞问题</span><strong>{blockerCount}</strong><em>{warningCount} 项提醒</em></div>
                <div><span>迁移内容</span><strong>{preflight.portability.summary.portable}</strong><em>{preflight.portability.summary.local_rebind} 项需重绑</em></div>
                <div className={canPackage ? 'ready' : 'warning'}><span>{packageModeTitle}</span><strong>{canPackage ? '可生成' : '未就绪'}</strong><em>{preflight.certification.label || statusLabel(preflight.certification.status)}</em></div>
              </section>

              <div className="cf-release-content">
                <section className="cf-release-preflight">
                  <header className="cf-release-section-head"><div><span>DELIVERY PREFLIGHT</span><h3>交付预检</h3></div><b className={blockerCount ? 'blocked' : 'ok'}>{blockerCount ? `${blockerCount} 项阻塞` : '门禁正常'}</b></header>
                  <div className="cf-release-check-grid">
                    {checks.map((check) => {
                      const tone = statusTone(check.status)
                      return <article key={check.id} className={`cf-release-check ${tone}`}><span className={`cf-check-status ${tone}`} /><div><strong>{check.label}</strong><small>{check.detail}</small></div><b>{check.count}</b><i>{statusLabel(check.status)}</i></article>
                    })}
                  </div>
                  <section className="cf-release-issues">
                    <header className="cf-release-subhead"><div><span>PREFLIGHT FINDINGS</span><h4>待处理项</h4></div><b>{preflight.issues.length}</b></header>
                    <div className="cf-release-issue-list">
                      {preflight.issues.map((issue, index) => <article key={`${issue.area}-${index}`}><span className={`cf-check-status ${issue.severity === 'blocker' ? 'blocked' : 'warning'}`} /><b>{AREA_LABELS[issue.area] || issue.area}</b><p>{issue.message}</p></article>)}
                      {!preflight.issues.length && <div className="cf-release-clear"><i /><strong>没有阻塞或提醒</strong><span>当前 Flow 已通过全部交付预检。</span></div>}
                    </div>
                  </section>
                </section>

                <aside className="cf-release-delivery">
                  <section className="cf-release-portability">
                    <header className="cf-release-section-head"><div><span>PORTABILITY</span><h3>迁移检查</h3></div><b className={preflight.portability.status === 'ok' ? 'ok' : 'blocked'}>{preflight.portability.status === 'ok' ? '可迁移' : '需处理'}</b></header>
                    <div>
                      <span className="portable"><small>随包携带</small><strong>{preflight.portability.summary.portable}</strong></span>
                      <span className="rebind"><small>本机重绑</small><strong>{preflight.portability.summary.local_rebind}</strong></span>
                      <span className={preflight.portability.summary.missing_blockers ? 'blocked' : ''}><small>缺失阻断</small><strong>{preflight.portability.summary.missing_blockers}</strong></span>
                      <span className={preflight.portability.summary.forbidden ? 'blocked' : ''}><small>禁止打包</small><strong>{preflight.portability.summary.forbidden}</strong></span>
                    </div>
                  </section>
                  <section className={`cf-release-policy ${canPackage ? 'ready' : 'blocked'}`}>
                    <span>PACKAGE POLICY</span>
                    <h3>{packageModeTitle}</h3>
                    <p>{packageModeDescription}</p>
                    <dl>
                      <div><dt>协议认证</dt><dd>{preflight.certification.label || statusLabel(preflight.certification.status)}</dd></div>
                      <div><dt>当前版本</dt><dd>{preflight.cartridge.version}</dd></div>
                      <div><dt>生成状态</dt><dd>{canPackage ? '允许生成' : '等待处理'}</dd></div>
                    </dl>
                  </section>
                </aside>
              </div>

              <footer className="cf-release-actionbar">
                <span><b>{canPackage ? `${packageModeTitle}已就绪` : `${packageModeTitle}暂不可生成`}</b><small>{canPackage ? '生成后会自动加入左侧历史产物。' : blockerCount ? `先处理 ${blockerCount} 项阻塞问题，再刷新预检。` : '当前模式的交付门禁尚未全部通过。'}</small></span>
                <button type="button" onClick={() => void createPackage()} disabled={!canPackage || packaging}>{packaging ? '正在生成…' : `生成${packageModeTitle}`}</button>
              </footer>
            </>}

            {!selectedId && !loading && <div className="cf-release-empty"><strong>选择一个 Flow 开始发布</strong><span>预检结果与历史产物会在这里汇总。</span></div>}
            {selectedId && !preflightLoading && !preflight && !error && <div className="cf-release-empty"><strong>没有可用的预检结果</strong><span>请刷新预检后重试。</span></div>}
          </main>
        </div>
      </div>
    </div>
  )
}
