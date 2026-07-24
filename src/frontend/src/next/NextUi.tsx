import type { ReactNode } from 'react'
import { AlertCircle, CheckCircle2, Info, X } from 'lucide-react'
import './next-ui.css'

export function NextPage({ page, title, description, right, children }: { page: string; title: string; description: string; right?: ReactNode; children: ReactNode }) {
  return <main className={`cf-next-ui-page cf-next-ui-${page}`}><header className="cf-next-ui-header"><div><h1>{title}</h1><p>{description}</p></div><div className="cf-next-ui-header-right">{right}</div></header><div className="cf-next-ui-body">{children}</div></main>
}

export function NextPanel({ className = '', title, kicker, action, children }: { className?: string; title?: string; kicker?: string; action?: ReactNode; children: ReactNode }) {
  return <section className={`cf-next-ui-panel ${className}`}><>{(title || kicker || action) && <header className="cf-next-ui-panel-header"><div>{kicker && <span>{kicker}</span>}{title && <h2>{title}</h2>}</div>{action}</header>}</><div className="cf-next-ui-panel-body">{children}</div></section>
}

export function NextMetricStrip({ metrics }: { metrics: Array<{ label: string; value: ReactNode; tone?: 'default' | 'accent' | 'success' | 'danger' | 'info' }> }) {
  return <div className="cf-next-ui-metrics">{metrics.map((metric) => <div className={`cf-next-ui-metric ${metric.tone || 'default'}`} key={metric.label}><span>{metric.label}</span><strong>{metric.value}</strong></div>)}</div>
}

export function NextButton({ children, variant = 'quiet', className = '', ...props }: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: 'quiet' | 'primary' | 'danger' | 'link' }) {
  return <button type="button" className={`cf-next-ui-button ${variant} ${className}`} {...props}>{children}</button>
}

export function NextStatus({ tone, children }: { tone: 'success' | 'danger' | 'warning' | 'info' | 'neutral'; children: ReactNode }) {
  return <span className={`cf-next-ui-status ${tone}`}><i />{children}</span>
}

export function NextEmpty({ icon, title, description, action }: { icon?: ReactNode; title: string; description?: string; action?: ReactNode }) {
  return <div className="cf-next-ui-empty">{icon && <div className="cf-next-ui-empty-icon">{icon}</div>}<strong>{title}</strong>{description && <span>{description}</span>}{action}</div>
}

export function NextNotice({ tone = 'info', children, onClose }: { tone?: 'info' | 'success' | 'danger' | 'warning'; children: ReactNode; onClose?: () => void }) {
  const Icon = tone === 'danger' ? AlertCircle : tone === 'success' ? CheckCircle2 : tone === 'warning' ? AlertCircle : Info
  return <div className={`cf-next-ui-notice ${tone}`} role="status"><Icon size={16} aria-hidden="true" /><span>{children}</span>{onClose && <button type="button" onClick={onClose} aria-label="关闭提示"><X size={15} /></button>}</div>
}

export function NextDialog({ title, eyebrow, open, onClose, wide = false, children }: { title: string; eyebrow?: string; open: boolean; onClose: () => void; wide?: boolean; children: ReactNode }) {
  if (!open) return null
  return <div className="cf-next-ui-dialog-backdrop" role="presentation" onClick={onClose}><section className={`cf-next-ui-dialog ${wide ? 'wide' : ''}`} role="dialog" aria-modal="true" aria-label={title} onClick={(event) => event.stopPropagation()}><header><div>{eyebrow && <span>{eyebrow}</span>}<h2>{title}</h2></div><button type="button" onClick={onClose} aria-label="关闭"><X size={18} /></button></header><div className="cf-next-ui-dialog-body">{children}</div></section></div>
}

export function NextLoading({ label = '正在加载' }: { label?: string }) {
  return <div className="cf-next-ui-loading"><span className="cf-next-ui-spinner" />{label}</div>
}

export function formatNextDate(value?: string | number) {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '—' : date.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

export function formatNextBytes(value?: number) {
  if (!value) return '0 B'
  if (value < 1024) return `${value} B`
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`
  return `${(value / 1024 / 1024).toFixed(1)} MB`
}
