import { useEffect, useMemo, useState } from 'react'
import { fetchLabFlows, fetchStudioPackages, fetchStudioReleasePreflight, packageCartridge, type FlowLabItem, type StudioPackageItem, type StudioReleasePreflight } from '../api.ts'

const AREA_LABELS: Record<string, string> = { compatibility: '兼容性', environment: '环境', dependencies: '依赖', models: '模型', resources: '本地资源', package_hygiene: '发布包卫生' }

function formatBytes(value: number) {
  if (value < 1024) return `${value} B`
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`
  return `${(value / 1024 / 1024).toFixed(1)} MB`
}

function statusLabel(status?: string) {
  if (status === 'ok' || status === 'ready' || status === 'certified') return '通过'
  if (status === 'blocked') return '阻塞'
  if (status === 'warning' || status === 'actionable') return '注意'
  return status || '待检查'
}

export default function ReleasePage() {
  const [flows, setFlows] = useState<FlowLabItem[]>([])
  const [selectedId, setSelectedId] = useState('')
  const [preflight, setPreflight] = useState<StudioReleasePreflight | null>(null)
  const [history, setHistory] = useState<StudioPackageItem[]>([])
  const [packageMode, setPackageMode] = useState<'dev' | 'production'>('dev')
  const [loading, setLoading] = useState(true)
  const [packaging, setPackaging] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState<{ filename: string; url: string; size: number } | null>(null)

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
      const preferred = selectedId || localStorage.getItem('cf.studio.release_project') || items[0]?.id || ''
      if (preferred) await selectCartridge(preferred, items)
    } catch (reason: any) {
      setError(reason?.message || '读取发布状态失败')
    } finally {
      setLoading(false)
    }
  }

  async function selectCartridge(id: string, availableFlows = flows) {
    if (!availableFlows.some((flow) => flow.id === id)) return
    setSelectedId(id)
    setNotice(null)
    localStorage.setItem('cf.studio.release_project', id)
    try {
      setPreflight(await fetchStudioReleasePreflight(id))
    } catch (reason: any) {
      setError(reason?.message || '发布预检失败')
      setPreflight(null)
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
    setLoading(true)
    setError('')
    try {
      setPreflight(await fetchStudioReleasePreflight(selectedId))
      const historyResult = await fetchStudioPackages()
      setHistory(historyResult.items || [])
    } catch (reason: any) {
      setError(reason?.message || '发布预检失败')
    } finally {
      setLoading(false)
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

  return (
    <div className="cf-resource-page cf-release-page">
      <header className="cf-resource-heading">
        <div><span className="cf-resource-kicker">DELIVERY / PACKAGES</span><h1>打包发布</h1><p>卡带交付前的协议、环境、依赖和本地资源预检。</p></div>
        <div className="cf-resource-heading-meta"><b>{history.length}</b><span>个历史包</span></div>
      </header>
      {error && <div className="cf-resource-alert danger">{error}</div>}
      {notice && <div className="cf-release-result"><span><b>{notice.filename}</b><small>{formatBytes(notice.size)}</small></span><a href={notice.url} download>下载产物</a></div>}
      <div className="cf-release-layout">
        <aside className="cf-release-projects">
          <div className="cf-resource-panel-head"><div><span>CARTRIDGES</span><h2>选择卡带</h2></div></div>
          <div className="cf-release-project-list">{flows.map((flow) => <button type="button" key={flow.id} className={selectedId === flow.id ? 'selected' : ''} onClick={() => void selectCartridge(flow.id)}><span><strong>{flow.name}</strong><code>{flow.id}</code></span><i>{flow.version}</i></button>)}{!flows.length && !loading && <div className="cf-resource-empty">还没有可打包的卡带</div>}</div>
        </aside>

        <main className="cf-release-workspace">
          <div className="cf-release-toolbar"><div><span>RELEASE TARGET</span><h2>{selectedFlow?.name || '未选择卡带'}</h2><code>{selectedFlow?.id}</code></div><div className="cf-release-toolbar-actions"><button type="button" className="cf-release-refresh" onClick={() => void refreshPreflight()} disabled={loading || !selectedId}>刷新预检</button><div className="cf-release-mode" role="group" aria-label="打包模式"><button type="button" className={packageMode === 'dev' ? 'active' : ''} onClick={() => setPackageMode('dev')}>开发包</button><button type="button" className={packageMode === 'production' ? 'active' : ''} onClick={() => setPackageMode('production')}>生产包</button></div></div></div>
          {preflight ? <>
            <div className="cf-release-summary"><div><span>版本</span><b>{preflight.cartridge.version}</b></div><div><span>问题</span><b>{preflight.issues.length}</b></div><div><span>认证</span><b>{preflight.certification.label || statusLabel(preflight.certification.status)}</b></div><div className={preflight.production_ready ? 'ready' : 'warning'}><span>生产交付</span><b>{preflight.production_ready ? '可打包' : '未就绪'}</b></div></div>
            <div className="cf-portability-strip" aria-label="卡带迁移报告">
              <div className="portable"><span>随包携带</span><b>{preflight.portability.summary.portable}</b></div>
              <div className="rebind"><span>本机重绑</span><b>{preflight.portability.summary.local_rebind}</b></div>
              <div className={preflight.portability.summary.missing_blockers ? 'blocked' : ''}><span>缺失阻断</span><b>{preflight.portability.summary.missing_blockers}</b></div>
              <div className={preflight.portability.summary.forbidden ? 'blocked' : ''}><span>禁止打包</span><b>{preflight.portability.summary.forbidden}</b></div>
            </div>
            <div className="cf-release-check-grid">{checks.map((check) => <section key={check.id} className={`cf-release-check ${check.status}`}><span className={`cf-check-status ${check.status}`} /><div><strong>{check.label}</strong><small>{check.detail}</small></div><b>{check.count}</b><i>{statusLabel(check.status)}</i></section>)}</div>
            <section className="cf-release-issues"><div className="cf-environment-subhead"><span>PREFLIGHT FINDINGS</span><h3>待处理项</h3><b>{preflight.issues.length}</b></div>{preflight.issues.length ? <div>{preflight.issues.map((issue, index) => <article key={`${issue.area}-${index}`}><span className={`cf-check-status ${issue.severity === 'blocker' ? 'blocked' : 'warning'}`} /><b>{AREA_LABELS[issue.area] || issue.area}</b><p>{issue.message}</p></article>)}</div> : <div className="cf-release-clear">当前预检没有阻塞或警告</div>}</section>
            <div className="cf-release-actionbar"><span><b>{packageMode === 'production' ? '生产包' : '开发包'}</b><small>{packageMode === 'production' ? '要求全部生产预检通过' : '保留诊断信息与本地绑定描述'}</small></span><button type="button" onClick={() => void createPackage()} disabled={!canPackage || packaging}>{packaging ? '正在打包…' : packageMode === 'production' ? '生成生产包' : '生成开发包'}</button></div>
          </> : <div className="cf-resource-empty">{loading ? '正在读取发布预检…' : '选择卡带后查看预检'}</div>}
        </main>
      </div>

      <section className="cf-release-history"><div className="cf-resource-panel-head"><div><span>PACKAGE HISTORY</span><h2>历史产物</h2></div><small>{selectedHistory.length} 项</small></div><div>{selectedHistory.slice(0, 10).map((item) => <article key={`${item.filename}-${item.modified_at}`}><span><strong>{item.filename}</strong><code>{item.cartridge_id || '未知卡带'}</code></span><i>{item.package_mode === 'production' ? '生产包' : '开发包'}</i><time>{new Date(item.modified_at).toLocaleString('zh-CN')}</time><b>{formatBytes(item.size)}</b><a href={item.url} download>下载</a></article>)}{!selectedHistory.length && <div className="cf-resource-empty compact">还没有打包产物</div>}</div></section>
    </div>
  )
}
