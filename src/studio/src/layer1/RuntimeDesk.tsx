import { useEffect, useMemo, useState } from 'react'
import {
  Bot,
  Calendar,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Download,
  ExternalLink,
  Package,
  Play,
  X,
  XCircle,
} from 'lucide-react'
import type { CreatorPackage, CreatorProjection } from '../api/types.ts'
import {
  approveStudioJob,
  fetchStudioRuntime,
  installStudioPackage,
  type StudioCartridge,
  type StudioRunJob,
} from '../api/client.ts'
import { copy } from '../copy.ts'
import { Button, cx } from '../ui/index.ts'
import {
  clearRuntimeToast,
  getRuntimeDeskSnapshot,
  rememberJobs,
  setBlockingRun,
  startRuntimeJob,
  subscribeRuntimeDesk,
} from './runtimeDeskStore.ts'

type WidgetKind = 'text' | 'textarea' | 'date' | 'url' | 'boolean'
type ExperienceField = { id: string; label: string; kind: string; source: string }
type InputSpec = { id: string; label: string; required: boolean; kind: WidgetKind }

function compactTitle(raw: string) {
  const text = raw.replace(/\s+/g, ' ').trim()
  if (!text) return copy.unnamedProject
  return text.slice(0, 16)
}

function presentationFields(creator: CreatorProjection | null): ExperienceField[] {
  const fields: ExperienceField[] = []
  for (const node of creator?.trusted_recipe.nodes || []) {
    for (const slot of node.experience?.slots || []) {
      const selected = slot.components.find((item) => item.id === slot.selected_component_id)
      for (const field of selected?.fields || []) {
        fields.push({
          id: `${node.id}:${field.id}`,
          label: field.label || field.id,
          kind: field.required ? '必填' : '可选',
          source: slot.field_sources[field.id] || `结果.${field.id}`,
        })
      }
    }
  }
  return fields
}

function widgetKind(field: { id?: string; label?: string; type?: string; kind?: string; source?: string; value_type?: string }): WidgetKind {
  if (field.value_type === 'string_list') return 'textarea'
  if (field.value_type === 'boolean') return 'boolean'
  const hay = `${field.id || ''} ${field.label || ''} ${field.type || ''} ${field.kind || ''} ${field.source || ''} ${field.value_type || ''}`.toLowerCase()
  if (/日期|date/.test(hay)) return 'date'
  if (/是\/否|boolean|确认|approved|checkbox/.test(hay)) return 'boolean'
  if (/链接|url|link/.test(hay) && !/来源列表|feed|rss/.test(hay)) return 'url'
  if (/列表|list|textarea|来源|feed|rss|sources/.test(hay)) return 'textarea'
  return 'text'
}

function addSpec(specs: InputSpec[], spec: InputSpec) {
  if (specs.some((item) => item.id === spec.id || item.label === spec.label)) return
  specs.push(spec)
}

function inputSpecs(cartridge: StudioCartridge | null, creator: CreatorProjection | null, fields: ExperienceField[]) {
  const specs: InputSpec[] = []
  const protocol = creator?.studio_runtime?.params || []
  if (protocol.length) {
    for (const field of protocol) {
      addSpec(specs, {
        id: field.id,
        label: field.label || field.id,
        required: Boolean(field.required),
        kind: widgetKind({ ...field, type: field.value_type }),
      })
    }
    return specs
  }
  for (const field of cartridge?.inputs || []) {
    addSpec(specs, {
      id: field.id,
      label: field.label || field.id,
      required: Boolean(field.required),
      kind: widgetKind(field),
    })
  }
  for (const field of fields.filter((item) => item.source.startsWith('运行输入'))) {
    const id = field.source.replace(/^运行输入\./, '') || field.id
    addSpec(specs, {
      id,
      label: id === 'date' || field.label === '日期' ? '试运行日期' : field.label,
      required: false,
      kind: widgetKind(field),
    })
  }
  const rank = (item: InputSpec) => (/来源|source/.test(item.id + item.label) ? 0 : /日期|date/.test(item.id + item.label) ? 1 : 2)
  return specs.sort((a, b) => rank(a) - rank(b))
}

function defaultInputs(cartridge: StudioCartridge | null, creator: CreatorProjection | null, specs: InputSpec[]) {
  const values: Record<string, string> = {}
  const fromProtocol = new Map((creator?.studio_runtime?.params || []).map((field) => [field.id, field.default]))
  const fromCartridge = new Map((cartridge?.inputs || []).map((field) => [field.id, field.default]))
  const fromNodes = new Map<string, unknown>()
  for (const node of creator?.trusted_recipe.nodes || []) {
    for (const field of node.editable_fields || []) fromNodes.set(field.id, node.values?.[field.id] ?? field.default)
  }
  for (const spec of specs) {
    const fallback = fromProtocol.get(spec.id) ?? fromCartridge.get(spec.id) ?? fromNodes.get(spec.id)
    if (fallback === undefined || fallback === null || fallback === '') {
      values[spec.id] = spec.kind === 'date' ? new Date().toISOString().slice(0, 10) : spec.kind === 'boolean' ? 'false' : ''
    } else if (Array.isArray(fallback)) {
      values[spec.id] = fallback.map(String).join('\n')
    } else {
      values[spec.id] = String(fallback)
    }
  }
  return values
}

function runPayload(inputs: Record<string, string>, specs: InputSpec[]) {
  const payload: Record<string, unknown> = {}
  for (const spec of specs) {
    const raw = inputs[spec.id] ?? ''
    if (spec.kind === 'textarea') payload[spec.id] = raw.split(/\n+/).map((item) => item.trim()).filter(Boolean)
    else if (spec.kind === 'boolean') payload[spec.id] = raw === 'true' || raw === '1'
    else payload[spec.id] = raw
  }
  return payload
}

function fingerprint(value: string) {
  const compact = value.replace(/[^a-zA-Z0-9]/g, '')
  return compact.slice(-12) || value.slice(0, 12)
}

function shortRunId(runId: string, prefix = 'T') {
  const tail = runId.replace(/^run[_-]?/i, '').replace(/[^a-zA-Z0-9]/g, '').slice(-4).toUpperCase()
  return tail ? `${prefix}-${tail}` : runId.slice(0, 8)
}

function clock(value?: string) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false })
}

function stamp(value?: string) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  const y = date.getFullYear()
  const m = String(date.getMonth() + 1).padStart(2, '0')
  const d = String(date.getDate()).padStart(2, '0')
  return `${y}-${m}-${d} ${clock(value)}`
}

function durationLabel(job: StudioRunJob) {
  const start = Date.parse(job.created_at || '')
  if (!Number.isFinite(start)) return '—'
  const end = Date.parse(job.updated_at || '') || (job.active || job.status === 'running' ? Date.now() : start)
  const sec = Math.max(0, Math.round((end - start) / 1000))
  return `${Math.floor(sec / 60)}m ${String(sec % 60).padStart(2, '0')}s`
}

function statusLabel(status: string) {
  if (status === 'running') return '试运行中'
  if (status === 'created' || status === 'queued') return '排队中'
  if (status === 'paused' || status === 'paused_waiting_user') return '等待中'
  if (status === 'completed') return '已完成'
  if (status === 'failed') return '失败'
  if (status === 'cancelled') return '已取消'
  return status
}

function isActiveJob(job: StudioRunJob) {
  return job.active || ['created', 'running', 'queued', 'paused', 'paused_waiting_user'].includes(job.status)
}

function deliveryText(job: StudioRunJob) {
  return String(job.delivery?.result || job.delivery?.value || job.delivery?.summary || job.error?.message || '')
}

function jobTitle(job: StudioRunJob, cartridges: StudioCartridge[]) {
  if (job.label && job.label !== job.cartridge_id) return job.label
  return cartridges.find((item) => item.id === job.cartridge_id)?.name || job.label || job.cartridge_id
}

function bindCartridge(cartridges: StudioCartridge[], boundId: string, projectId: string | undefined) {
  return cartridges.find((item) => boundId && item.id === boundId)
    || cartridges.find((item) => projectId && item.id === `studio.${projectId}`)
    || cartridges.find((item) => projectId && item.id.includes(projectId))
    || null
}

function inputKey(projectId?: string) {
  return `cartridgeflow.runtime.inputs.${projectId || 'none'}`
}

export function RuntimeDesk({
  creator,
  packageResult,
  onClose,
  onPackage,
  onOpenGap,
  onToggleSteward,
}: {
  creator: CreatorProjection | null
  packageResult: CreatorPackage | null
  onClose: () => void
  onPackage: () => Promise<CreatorPackage | null>
  onOpenGap?: (nodeId: string) => void
  onToggleSteward?: () => void
}) {
  const [desk, setDesk] = useState(getRuntimeDeskSnapshot())
  const [cartridges, setCartridges] = useState<StudioCartridge[]>([])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [inputs, setInputs] = useState<Record<string, string>>({})
  const [boundId, setBoundId] = useState('')
  const [recordsOpen, setRecordsOpen] = useState(false)
  const [openHistory, setOpenHistory] = useState('')
  const [inputsReady, setInputsReady] = useState(false)
  const fields = useMemo(() => {
    const fromProtocol = (creator?.studio_runtime?.fields || []).map((field) => ({
      id: field.id, label: field.label, kind: field.kind, source: field.source,
    }))
    return fromProtocol.length ? fromProtocol : presentationFields(creator)
  }, [creator])
  const rawName = creator?.short_name || creator?.project_name || creator?.intent || copy.unnamedProject
  const title = creator?.short_name || compactTitle(rawName)
  const gaps = (creator?.trusted_recipe.nodes || []).filter((node) => node.resolution?.status === 'unresolved')
  const cartridge = bindCartridge(cartridges, boundId, creator?.project_id)
  const signed = Boolean(cartridge) || Boolean(packageResult?.filename)
  const specs = useMemo(() => inputSpecs(cartridge, creator, fields), [cartridge, creator, fields])

  useEffect(() => subscribeRuntimeDesk(() => setDesk(getRuntimeDeskSnapshot())), [])
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => { if (event.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  useEffect(() => {
    void (async () => {
      try {
        const snapshot = await fetchStudioRuntime({ project_id: creator?.project_id })
        setCartridges(snapshot.cartridges || [])
        rememberJobs(snapshot.jobs || [])
        let nextBound = boundId
        const matched = bindCartridge(snapshot.cartridges || [], nextBound, creator?.project_id)
        if (matched?.id) {
          nextBound = matched.id
          if (matched.id !== boundId) setBoundId(matched.id)
        }
        if (packageResult?.filename) {
          try {
            const installed = await installStudioPackage(packageResult.filename)
            if (installed.cartridge?.id) {
              setBoundId(installed.cartridge.id)
              setCartridges((current) => current.some((item) => item.id === installed.cartridge.id) ? current : [...current, installed.cartridge])
            }
          } catch {
            /* a restored filename may already have been replaced */
          }
        }
      } catch (reason) {
        setError(reason instanceof Error ? reason.message : '试运行没有就绪')
      }
    })()
  }, [packageResult?.filename, creator?.project_id])

  useEffect(() => {
    const stored = window.localStorage.getItem(inputKey(creator?.project_id))
    const defaults = defaultInputs(cartridge, creator, specs)
    if (stored) {
      try {
        setInputs({ ...defaults, ...JSON.parse(stored) })
        setInputsReady(true)
        return
      } catch { /* keep defaults */ }
    }
    setInputs(defaults)
    setInputsReady(true)
  }, [cartridge?.id, creator?.session_id, specs.map((item) => item.id).join(',')])

  useEffect(() => {
    if (!inputsReady || !creator?.project_id) return
    window.localStorage.setItem(inputKey(creator.project_id), JSON.stringify(inputs))
  }, [creator?.project_id, inputs, inputsReady])

  const queue = desk.jobs.filter(isActiveJob)
  const history = desk.jobs.filter((job) => !isActiveJob(job))
  const runningCount = queue.filter((job) => job.status === 'running').length
  const resultFields = fields

  const runCurrent = async () => {
    setBusy(true)
    setError('')
    try {
      let current = cartridge
      if (!current && packageResult?.filename) {
        const installed = await installStudioPackage(packageResult.filename)
        if (installed.cartridge?.id) {
          setBoundId(installed.cartridge.id)
          setCartridges((items) => items.some((item) => item.id === installed.cartridge.id) ? items : [...items, installed.cartridge])
          current = installed.cartridge
        }
      }
      if (!current) {
        setError('当前方案还没有签发成可试运行的卡带。')
        return
      }
      await startRuntimeJob(current.id, runPayload(inputs, specs), current.name || title, creator?.project_id)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '没有加入试运行队列')
    } finally {
      setBusy(false)
    }
  }

  const issuePackage = async () => {
    setBusy(true)
    setError('')
    try {
      const next = await onPackage()
      if (!next?.filename) {
        setError('签发没有完成。')
        return
      }
      const installed = await installStudioPackage(next.filename)
      if (installed.cartridge?.id) setBoundId(installed.cartridge.id)
      const snapshot = await fetchStudioRuntime({
        project_id: creator?.project_id,
        cartridge_id: installed.cartridge?.id,
      })
      setCartridges(snapshot.cartridges || [])
      rememberJobs(snapshot.jobs || [])
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : copy.packageFail)
    } finally {
      setBusy(false)
    }
  }

  return <div className="overlay runtime-popup" role="presentation" onClick={onClose}>
    <div className="runtime-desk" role="dialog" aria-modal="true" aria-label="试运行" onClick={(event) => event.stopPropagation()}>
      <header className="runtime-desk-bar">
        <div className="runtime-desk-title">
          <strong>试运行</strong>
          <span>按当前方案验证输入与交付</span>
        </div>
        <div className="runtime-bind">
          <span>绑定卡带</span>
          <b title={rawName}>{cartridge?.name || title}</b>
          {cartridge ? <em>v{cartridge.version}</em> : null}
          <i className={signed ? 'is-ok' : 'is-gap'}>{signed ? '已签发' : '未签发'}</i>
        </div>
        <Button
          variant="ghost"
          aria-expanded={recordsOpen}
          aria-controls="runtime-queue runtime-history"
          onClick={() => setRecordsOpen((open) => !open)}
        >
          试运行记录 {queue.length + history.length}
          {recordsOpen ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        </Button>
        {onToggleSteward ? <button type="button" className="btn-steward" onClick={() => { onClose(); onToggleSteward() }}><Bot size={11} />{copy.steward}</button> : null}
        <Button variant="icon" aria-label="关闭试运行" onClick={onClose}><X size={14} /></Button>
      </header>
      {error ? <p className="alert runtime-alert" role="alert">{error}</p> : null}
      <div className="runtime-desk-cols">
        <section className="runtime-col is-run" aria-label="试运行" style={recordsOpen ? undefined : { gridColumn: '1 / -1' }}>
          <h3>试运行</h3>
          <div className="runtime-col-body" style={recordsOpen ? undefined : { width: 'min(100%, 520px)', margin: '0 auto' }}>
            <div className="runtime-cart">
              <small>当前卡带</small>
              <strong title={rawName}>{cartridge?.name || title}</strong>
              <div className="runtime-cart-meta">
                {cartridge ? <em>v{cartridge.version}</em> : <em>草稿</em>}
                <i className={signed ? 'is-ok' : 'is-gap'}>{signed ? '已签发' : '未签发'}</i>
                {cartridge ? <button type="button" className="runtime-text-link" title="复制指纹" onClick={() => { void navigator.clipboard.writeText(packageResult?.fingerprint || fingerprint(cartridge.id)) }}>{packageResult?.fingerprint || fingerprint(cartridge.id)}</button> : null}
              </div>
            </div>
            <p className="runtime-kicker">输入参数</p>
            {specs.map((field) => (
              <label key={field.id} className="runtime-field">
                {field.label}{field.required ? ' *' : ''}
                <FieldControl
                  kind={field.kind}
                  value={inputs[field.id] || ''}
                  disabled={busy}
                  placeholder={field.kind === 'textarea' ? '每行一个来源，例如 https://example.com/ai.rss' : undefined}
                  onChange={(value) => setInputs((current) => ({ ...current, [field.id]: value }))}
                />
              </label>
            ))}
            <button type="button" className="runtime-start" disabled={busy || !signed} onClick={() => void runCurrent()}>
              <Play size={14} fill="currentColor" /> 开始试运行
            </button>
            {!signed ? <p className="runtime-start-hint">先签发发行包，才会按当前方案开始试运行。{gaps[0] ? <button type="button" className="runtime-text-link" onClick={() => onOpenGap?.(gaps[0].id)}>去补齐</button> : null}</p> : null}
            {gaps.length ? <div className="runtime-gap">
              <b>还有 {gaps.length} 步待补齐，暂时不能签发</b>
              <ol>{gaps.map((node) => <li key={node.id}><button type="button" onClick={() => onOpenGap?.(node.id)}>{node.label}</button></li>)}</ol>
            </div> : null}
            <div className="runtime-pack">
              <p className="runtime-kicker">发行包</p>
              {signed ? <>
                <div className="runtime-pack-card">
                  <div><Package size={13} /><b>{cartridge?.name || title}</b>{cartridge ? <em>v{cartridge.version}</em> : null}</div>
                  <span>指纹 <button type="button" className="runtime-text-link" onClick={() => { void navigator.clipboard.writeText(packageResult?.fingerprint || (cartridge ? fingerprint(cartridge.id) : '')) }}>{packageResult?.fingerprint || (cartridge ? fingerprint(cartridge.id) : '')}</button> · 签发于 {packageResult?.issued_at || new Date().toISOString().slice(0, 10)}</span>
                </div>
                {packageResult?.url ? <a className="runtime-download" href={packageResult.url} download={packageResult.filename}>
                  <Download size={14} /> {copy.downloadPackage}
                </a> : <button type="button" className="runtime-download" disabled={busy} onClick={() => void issuePackage()}>
                  {copy.downloadPackage}
                </button>}
              </> : <>
                <div className="runtime-pack-card is-empty">
                  <div><Package size={13} /><b>还没有签发当前方案</b></div>
                  <span>签发后可以下载给客户，也可以在这里直接试运行。</span>
                </div>
                <button type="button" className="runtime-download" disabled={busy || !creator || gaps.length > 0} onClick={() => void issuePackage()}>
                  {busy ? copy.package.packing : '签发发行包'}
                </button>
              </>}
            </div>
          </div>
        </section>
        {recordsOpen ? <>
          <section id="runtime-queue" className="runtime-col is-queue" aria-label="队列">
            <div className="runtime-col-head">
              <div>
                <h3>队列</h3>
                <small>关掉页面，试运行任务仍会继续</small>
              </div>
              <em>{runningCount} 试运行中</em>
            </div>
            <div className="runtime-col-body is-list">
              {queue.length ? queue.map((job) => (
                <button type="button" key={job.run_id} className="runtime-queue-item" onClick={() => setBlockingRun(job.run_id)}>
                  <div className="runtime-queue-top">
                    <div>
                      <strong>{jobTitle(job, cartridges)}</strong>
                      <div className="runtime-queue-meta">
                        <span>{shortRunId(job.run_id)}</span>
                        <i className={job.status === 'running' ? 'is-run' : 'is-wait'}>{statusLabel(job.status)}</i>
                      </div>
                    </div>
                    <div className="runtime-queue-time">
                      <span>{clock(job.created_at)}</span>
                      <b>{job.status === 'queued' || job.status === 'created' ? '—' : durationLabel(job)}</b>
                    </div>
                  </div>
                  <MiniBar job={job} />
                </button>
              )) : <div className="runtime-blank">
                <i className="runtime-blank-mark" aria-hidden="true" />
                <strong>还没有排队的任务</strong>
                <span>开始试运行后会出现在这里。关掉页面也不会停，完成后会提示你。</span>
              </div>}
            </div>
          </section>
          <section id="runtime-history" className="runtime-col is-history" aria-label="历史">
            <div className="runtime-col-head">
              <h3>历史</h3>
              <span>{history.length} 条</span>
            </div>
            <div className="runtime-col-body is-list">
              {history.length ? history.map((job) => {
                const open = openHistory === job.run_id
                const ok = job.status === 'completed'
                return <div key={job.run_id} className="runtime-history-item">
                  <button type="button" onClick={() => setOpenHistory(open ? '' : job.run_id)}>
                    {ok ? <CheckCircle2 size={16} className="is-ok" /> : <XCircle size={16} className="is-bad" />}
                    <div>
                      <strong>{jobTitle(job, cartridges)}</strong>
                      <small>{stamp(job.updated_at || job.created_at)}</small>
                    </div>
                    <div className="runtime-history-side">
                      <b>{durationLabel(job)}</b>
                      <span>{shortRunId(job.run_id, 'RUN')}</span>
                    </div>
                    {open ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                  </button>
                  {open ? <div className="runtime-history-body">
                    <ResultWidgets fields={resultFields} job={job} template={creator?.studio_runtime?.template} />
                    {job.status === 'failed' ? <p className="hint">{jobErrorText(job)}</p> : null}
                    {job.status === 'failed' && (cartridge || signed) ? <button type="button" className="runtime-text-link" onClick={() => void startRuntimeJob((cartridge || bindCartridge(cartridges, boundId, creator?.project_id))!.id, job.inputs || runPayload(inputs, specs), cartridge?.name || title, creator?.project_id)}>重跑</button> : null}
                    <button type="button" className="runtime-text-link" onClick={() => setBlockingRun(job.run_id)}>查看结果</button>
                  </div> : null}
                </div>
              }) : <div className="runtime-blank">
                <i className="runtime-blank-mark" aria-hidden="true" />
                <strong>还没有试运行记录</strong>
                <span>跑完的任务会留在这里，可展开查看第二层字段对应的结果。</span>
              </div>}
            </div>
          </section>
        </> : null}
      </div>
    </div>
  </div>
}

function FieldControl({
  kind,
  value,
  disabled,
  placeholder,
  onChange,
}: {
  kind: WidgetKind
  value: string
  disabled?: boolean
  placeholder?: string
  onChange?: (value: string) => void
}) {
  if (kind === 'boolean') {
    return <span className="runtime-check">
      <input type="checkbox" checked={value === 'true' || value === '1'} disabled={disabled} onChange={(event) => onChange?.(event.target.checked ? 'true' : 'false')} />
      已确认
    </span>
  }
  if (kind === 'textarea') {
    return <textarea rows={3} value={value} disabled={disabled} placeholder={placeholder} onChange={(event) => onChange?.(event.target.value)} />
  }
  if (kind === 'date') {
    return <span className="runtime-date">
      <Calendar size={13} />
      <input type="date" value={value} disabled={disabled} onChange={(event) => onChange?.(event.target.value)} />
    </span>
  }
  return <input type={kind === 'url' ? 'url' : 'text'} value={value} disabled={disabled} placeholder={placeholder} onChange={(event) => onChange?.(event.target.value)} />
}

function MiniBar({ job }: { job: StudioRunJob }) {
  const steps = job.progress.steps.length
    ? job.progress.steps
    : [{ id: 'wait', label: statusLabel(job.status), status: job.status === 'running' ? 'running' : 'pending' }]
  const current = steps.find((step) => step.status === 'running') || steps.find((step) => step.status === 'pending') || steps[steps.length - 1]
  return <div className="runtime-mini" aria-hidden="true">
    {steps.map((step, index) => (
      <span key={step.id} className="runtime-mini-node">
        {index ? <i className={cx('runtime-mini-line', step.status === 'pending' ? '' : 'is-on')} /> : null}
        <b className={cx('is-' + (step.status === 'completed' || step.status === 'done' ? 'done' : step.status === 'running' ? 'run' : step.status === 'failed' || step.status === 'error' ? 'bad' : 'wait'))} />
      </span>
    ))}
    <em>{current?.label || job.progress.current_label || statusLabel(job.status)}</em>
  </div>
}

function resultItems(job: StudioRunJob) {
  const raw = job.delivery?.result_items
  if (Array.isArray(raw) && raw.length) {
    return raw.map((item) => typeof item === 'string' ? item : String(item.title || item.summary || item.url || '')).filter(Boolean)
  }
  const text = deliveryText(job).replace(/\*\*/g, '')
  const lines = text.split('\n').map((line) => line.replace(/^[\s#*\-·\d.]+/, '').trim()).filter((line) => line.length > 4 && !/^https?:/.test(line))
  return lines.slice(0, 8)
}

function resultUrls(job: StudioRunJob) {
  const fromDelivery = (job.delivery?.source_url || []).filter(Boolean)
  if (fromDelivery.length) return fromDelivery
  const fromItems = (job.delivery?.result_items || []).map((item) => typeof item === 'string' ? '' : String(item.url || '')).filter(Boolean)
  if (fromItems.length) return fromItems
  return [...new Set(deliveryText(job).match(/https?:\/\/[^\s)\]>'"]+/g) || [])]
}

function resultDate(job: StudioRunJob) {
  const direct = String(job.delivery?.date || job.inputs?.date || job.inputs?.运行日期 || '')
  if (direct) return direct
  const dated = deliveryText(job).match(/日期[:：]\s*([0-9]{4}[年/-][0-9]{1,2}[月/-][0-9]{1,2}日?)/)
  return dated?.[1] || stamp(job.created_at).slice(0, 10)
}

function jobErrorText(job: StudioRunJob) {
  return String(job.error?.cause_chain?.[0]?.message || job.error?.message || '失败')
}

function ResultWidgets({ fields, job, template = '列表' }: { fields: ExperienceField[]; job: StudioRunJob; template?: string }) {
  if (!fields.length) {
    const text = deliveryText(job)
    return <div className="runtime-result-widgets"><p className="hint">尚未配置结果展示字段</p>{text ? <pre>{text.replace(/\*\*/g, '')}</pre> : null}</div>
  }
  const points = resultItems(job)
  const urls = resultUrls(job)
  const date = resultDate(job)
  return <div className={cx('runtime-result-widgets', template === '数据面板' && 'is-grid')}>
    {fields.map((field) => {
      const kind = widgetKind(field)
      if (kind === 'boolean') {
        const checked = Boolean(job.approved || job.delivery?.approved)
        return <label key={field.id} className="runtime-check">
          <input type="checkbox" checked={checked} onChange={(event) => {
            const next = event.target.checked
            rememberJobs([{ ...job, approved: next, delivery: { ...(job.delivery || {}), approved: next } }])
            void approveStudioJob(job.run_id, next).then((updated) => rememberJobs([updated])).catch(() => {
              rememberJobs([{ ...job, approved: checked, delivery: { ...(job.delivery || {}), approved: checked } }])
            })
          }} /> {field.label}
        </label>
      }
      if (kind === 'url') {
        return <div key={field.id} className="runtime-result-field">
          <span>{field.label}</span>
          {urls.length ? <ul>{urls.slice(0, 8).map((url) => <li key={url}><a href={url} target="_blank" rel="noreferrer">{url}</a></li>)}</ul> : <small>这次交付里没有链接</small>}
        </div>
      }
      if (kind === 'date' || field.label === '日期') {
        return <p key={field.id} className="runtime-result-field"><span>{field.label}</span><small>{date || '—'}</small></p>
      }
      if (field.label === '要点' || field.source.includes('result_items') || field.kind === '列表') {
        return <div key={field.id} className="runtime-result-field">
          <span>{field.label}{template === '列表' ? ' · 列表' : template === '数据面板' ? ' · 面板' : ''}</span>
          {!points.length ? <small>还没有交付内容</small> : template === '摘要' ? <small>{points.slice(0, 3).join('；')}</small> : <ul>{points.map((item) => <li key={item}>{item}</li>)}</ul>}
        </div>
      }
      const extra = job.delivery && (job.delivery as Record<string, unknown>)[field.id]
      return <div key={field.id} className="runtime-result-field">
        <span>{field.label}</span>
        {extra != null && extra !== '' ? <small>{String(extra)}</small> : points.length ? <ul>{points.map((item) => <li key={item}>{item}</li>)}</ul> : <small>还没有交付内容</small>}
      </div>
    })}
  </div>
}

export function RunBlocker() {
  const [desk, setDesk] = useState(getRuntimeDeskSnapshot())
  useEffect(() => subscribeRuntimeDesk(() => setDesk(getRuntimeDeskSnapshot())), [])
  const job = desk.jobs.find((item) => item.run_id === desk.blockingRunId)
  if (!job) return null
  const done = job.status === 'completed' || job.status === 'failed' || job.status === 'cancelled'
  return <div className="run-blocker" role="alertdialog" aria-label={done ? '试运行结果' : '正在试运行'} aria-modal="true">
    <div className="runtime-layer">
      <header>
        <div>
          <h2>{done ? (job.status === 'completed' ? '试运行完成' : '试运行结束') : '正在试运行'}</h2>
          <p>{job.label || job.cartridge_id} · {job.progress.current_label || statusLabel(job.status)}</p>
        </div>
        <Button variant="icon" aria-label={done ? '关闭试运行层' : '最小化试运行层'} onClick={() => setBlockingRun(null)}><X size={14} /></Button>
      </header>
      <div className="runtime-layer-body">
        <MiniBar job={job} />
        <div className="runtime-progress-track" aria-label="试运行进度">
          <span style={{ width: `${Math.max(4, job.progress.percent)}%` }} />
        </div>
        <p className="runtime-layer-percent">{job.progress.percent}%</p>
        {done && job.status === 'completed' ? <ResultWidgets fields={[]} job={job} /> : null}
        {done && job.status !== 'completed' ? <pre className="runtime-fail">{jobErrorText(job)}</pre> : null}
      </div>
      <div className="dialog-foot">
        <span>{shortRunId(job.run_id, 'RUN')}</span>
        {done ? <Button onClick={() => setBlockingRun(null)}>关闭</Button> : <Button variant="ghost" onClick={() => setBlockingRun(null)}>转到后台</Button>}
      </div>
    </div>
  </div>
}

export function RuntimeToasts() {
  const [desk, setDesk] = useState(getRuntimeDeskSnapshot())
  useEffect(() => subscribeRuntimeDesk(() => setDesk(getRuntimeDeskSnapshot())), [])
  if (!desk.toast || desk.blockingRunId === desk.toast.id) return null
  return <div className="runtime-toast" role="status">
    <CheckCircle2 size={17} />
    <div>
      <strong>{desk.toast.title}</strong>
      <span>{desk.toast.detail}</span>
      <button type="button" className="runtime-text-link" onClick={() => setBlockingRun(desk.toast!.id)}>
        查看结果 <ExternalLink size={11} />
      </button>
    </div>
    <button type="button" className="runtime-toast-close" aria-label="关闭提示" onClick={clearRuntimeToast}><X size={13} /></button>
  </div>
}
