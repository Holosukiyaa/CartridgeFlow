import { useEffect, useMemo, useState } from 'react'

type EvidenceStatus = 'all' | 'verified' | 'partial' | 'unverified' | 'failing'

const STATUS_LABELS: Record<string, string> = {
  verified: '已验证',
  partial: '部分支持',
  unverified: '未验证',
  failing: '验证失败',
}

function referenceLabel(item: any) {
  return String(item?.ref || item?.id || '未命名证据')
}

function EvidenceReferences({ title, items, emptyText }: { title: string; items: any[]; emptyText: string }) {
  return (
    <section className="cf-evidence-reference-section">
      <div className="cf-evidence-detail-subhead"><h3>{title}</h3><span>{items.length}</span></div>
      {items.length ? <div className="cf-evidence-reference-list">{items.map((item, index) => (
        <div key={`${referenceLabel(item)}-${index}`} className={item.status === 'failed' || item.exists === false ? 'failed' : ''}>
          <span>{referenceLabel(item)}</span>
          <b>{item.status || (item.exists === false ? '缺失' : '存在')}</b>
          {typeof item.duration_ms === 'number' && <small>{item.duration_ms.toFixed(1)} ms</small>}
        </div>
      ))}</div> : <p className="cf-evidence-empty-line">{emptyText}</p>}
    </section>
  )
}

export default function CapabilityEvidenceViewer({
  open,
  report,
  onClose,
}: {
  open: boolean
  report?: any
  onClose: () => void
}) {
  const items = report?.capabilities?.items || []
  const counts = report?.capabilities?.counts || {}
  const [filter, setFilter] = useState<EvidenceStatus>('all')
  const [query, setQuery] = useState('')
  const [selectedId, setSelectedId] = useState('')

  const filteredItems = useMemo(() => {
    const needle = query.trim().toLowerCase()
    return items.filter((item: any) => {
      if (filter !== 'all' && item.status !== filter) return false
      if (!needle) return true
      return `${item.id} ${item.evidence_set} ${item.notes} ${(item.gaps || []).join(' ')}`.toLowerCase().includes(needle)
    })
  }, [filter, items, query])

  const selected = filteredItems.find((item: any) => item.id === selectedId) || filteredItems[0]

  useEffect(() => {
    if (!open) return
    setFilter('all')
    setQuery('')
    setSelectedId(String(items[0]?.id || ''))
  }, [open])

  useEffect(() => {
    if (selected && selected.id !== selectedId) setSelectedId(selected.id)
  }, [selected?.id])

  if (!open) return null

  const filters: Array<{ id: EvidenceStatus; label: string; count: number }> = [
    { id: 'all', label: '全部', count: Number(report?.capabilities?.declared || items.length) },
    { id: 'verified', label: '已验证', count: Number(counts.verified || 0) },
    { id: 'partial', label: '部分支持', count: Number(counts.partial || 0) },
    { id: 'unverified', label: '未验证', count: Number(counts.unverified || 0) },
    { id: 'failing', label: '失败', count: Number(counts.failing || 0) },
  ]

  return (
    <div className="cf-modal-backdrop" role="presentation" onClick={onClose}>
      <section className="cf-evidence-viewer" role="dialog" aria-modal="true" aria-label="底座能力证据列表" onClick={(event) => event.stopPropagation()}>
        <header className="cf-modal-head">
          <div><span className="cf-modal-kicker">Capability evidence</span><h2>底座能力证据</h2></div>
          <div className="cf-evidence-head-summary"><span>自动测试 {report?.tests?.counts?.passed || 0}/{report?.tests?.total || 0}</span><b>{items.length} 项能力</b><button type="button" className="cf-modal-close" onClick={onClose}>关闭</button></div>
        </header>

        <div className="cf-evidence-toolbar">
          <div className="cf-evidence-filters" role="group" aria-label="按验证状态筛选">
            {filters.map((item) => <button key={item.id} type="button" className={filter === item.id ? 'active' : ''} onClick={() => setFilter(item.id)}><span>{item.label}</span><b>{item.count}</b></button>)}
          </div>
          <label className="cf-evidence-search"><span>搜索</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="能力 ID、证据组或缺口" /></label>
        </div>

        <div className="cf-evidence-layout">
          <aside className="cf-evidence-list" aria-label="能力列表">
            <div className="cf-evidence-list-meta"><span>{filteredItems.length} 项结果</span><code>{report?.generated_at ? new Date(report.generated_at).toLocaleString('zh-CN') : '尚无报告时间'}</code></div>
            <div>{filteredItems.map((item: any) => (
              <button key={item.id} type="button" className={selected?.id === item.id ? 'selected' : ''} onClick={() => setSelectedId(item.id)}>
                <i className={item.status} />
                <span><strong>{item.id}</strong><small>{item.evidence_set || '未分组'}</small></span>
                <b className={item.status}>{STATUS_LABELS[item.status] || item.status}</b>
              </button>
            ))}{!filteredItems.length && <div className="cf-evidence-list-empty">没有符合条件的能力</div>}</div>
          </aside>

          <main className="cf-evidence-detail">
            {selected ? <>
              <div className="cf-evidence-detail-head">
                <div><span>CAPABILITY</span><h2>{selected.id}</h2><code>证据组 · {selected.evidence_set || '未分组'}</code></div>
                <b className={selected.status}>{STATUS_LABELS[selected.status] || selected.status}</b>
              </div>

              {(selected.notes || selected.gaps?.length) && <section className="cf-evidence-notes">
                {selected.notes && <p>{selected.notes}</p>}
                {(selected.gaps || []).map((gap: string) => <div key={gap}><i />{gap}</div>)}
              </section>}

              <div className="cf-evidence-detail-scroll">
                <EvidenceReferences title="实现位置" items={selected.implementation || []} emptyText="没有登记实现位置" />
                <EvidenceReferences title="正向测试" items={selected.positive_tests || []} emptyText="没有登记正向测试" />
                <EvidenceReferences title="失败路径测试" items={selected.failure_tests || []} emptyText="尚未登记失败路径测试" />
                <EvidenceReferences title="前端入口" items={selected.ui?.entries || []} emptyText={selected.ui?.status === 'not_applicable' ? '这项能力没有独立前端入口' : '尚未登记前端入口'} />
              </div>
            </> : <div className="cf-evidence-detail-empty">选择一项能力查看证据</div>}
          </main>
        </div>
      </section>
    </div>
  )
}
