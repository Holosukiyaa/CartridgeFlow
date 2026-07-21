import { useEffect, useId, useRef, type KeyboardEvent as ReactKeyboardEvent, type ReactNode } from 'react'

export default function ConfigModal({ open, title, kicker, onClose, children, className = '' }: {
  open: boolean
  title: string
  kicker: string
  onClose: () => void
  children: ReactNode
  className?: string
}) {
  const titleId = useId()
  const dialogRef = useRef<HTMLElement>(null)

  useEffect(() => {
    if (!open) return
    const previousFocus = document.activeElement as HTMLElement | null
    const closeOnEscape = (event: KeyboardEvent) => { if (event.key === 'Escape') onClose() }
    window.addEventListener('keydown', closeOnEscape)
    const focusTimer = window.setTimeout(() => {
      dialogRef.current?.querySelector<HTMLElement>('input:not([disabled]), select:not([disabled]), textarea:not([disabled]), button:not([disabled])')?.focus()
    })
    return () => {
      window.removeEventListener('keydown', closeOnEscape)
      window.clearTimeout(focusTimer)
      previousFocus?.focus()
    }
  }, [open, onClose])

  function keepFocusInside(event: ReactKeyboardEvent<HTMLElement>) {
    if (event.key !== 'Tab') return
    const controls = [...(dialogRef.current?.querySelectorAll<HTMLElement>('button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])') || [])]
    if (!controls.length) return
    const first = controls[0]
    const last = controls[controls.length - 1]
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus() }
    if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
  }

  if (!open) return null
  return (
    <div className="cf-modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose() }}>
      <section ref={dialogRef} className={`cf-modal cf-config-modal ${className}`} role="dialog" aria-modal="true" aria-labelledby={titleId} onKeyDown={keepFocusInside}>
        <header className="cf-modal-head">
          <div><span className="cf-modal-kicker">{kicker}</span><h2 id={titleId}>{title}</h2></div>
          <button type="button" className="cf-modal-close cf-config-modal-close" onClick={onClose} aria-label="关闭">×</button>
        </header>
        <div className="cf-config-modal-body">{children}</div>
      </section>
    </div>
  )
}
