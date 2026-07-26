import { useEffect, useId, useRef, type KeyboardEvent as ReactKeyboardEvent, type ReactNode } from 'react'

const openModalStack: symbol[] = []

export default function ConfigModal({ open, title, kicker, onClose, children, className = '', initialFocus = 'control' }: {
  open: boolean
  title: string
  kicker: string
  onClose: () => void
  children: ReactNode
  className?: string
  initialFocus?: 'control' | 'dialog'
}) {
  const titleId = useId()
  const dialogRef = useRef<HTMLElement>(null)
  const modalToken = useRef(Symbol('config-modal')).current
  const onCloseRef = useRef(onClose)

  useEffect(() => {
    onCloseRef.current = onClose
  }, [onClose])

  useEffect(() => {
    if (!open) return
    openModalStack.push(modalToken)
    const previousFocus = document.activeElement as HTMLElement | null
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key !== 'Escape' || openModalStack.at(-1) !== modalToken) return
      event.stopImmediatePropagation()
      onCloseRef.current()
    }
    window.addEventListener('keydown', closeOnEscape)
    const focusTimer = window.setTimeout(() => {
      if (initialFocus === 'dialog') dialogRef.current?.focus({ preventScroll: true })
      else {
        const bodyControl = dialogRef.current?.querySelector<HTMLElement>('.cf-config-modal-body input:not([disabled]):not([type="hidden"]):not([hidden]), .cf-config-modal-body select:not([disabled]), .cf-config-modal-body textarea:not([disabled]), .cf-config-modal-body button:not([disabled])')
        const fallbackControl = dialogRef.current?.querySelector<HTMLElement>('input:not([disabled]):not([type="hidden"]):not([hidden]), select:not([disabled]), textarea:not([disabled]), button:not([disabled])')
        const initialControl = bodyControl || fallbackControl
        initialControl?.focus({ preventScroll: true })
      }
    })
    return () => {
      const stackIndex = openModalStack.lastIndexOf(modalToken)
      if (stackIndex >= 0) openModalStack.splice(stackIndex, 1)
      window.removeEventListener('keydown', closeOnEscape)
      window.clearTimeout(focusTimer)
      previousFocus?.focus()
    }
  }, [initialFocus, modalToken, open])

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
      <section ref={dialogRef} tabIndex={-1} className={`cf-modal cf-config-modal ${className}`} role="dialog" aria-modal="true" aria-labelledby={titleId} onKeyDown={keepFocusInside}>
        <header className="cf-modal-head">
          <div><span className="cf-modal-kicker">{kicker}</span><h2 id={titleId}>{title}</h2></div>
          <button type="button" className="cf-modal-close cf-config-modal-close" onClick={onClose} aria-label="关闭">×</button>
        </header>
        <div className="cf-config-modal-body">{children}</div>
      </section>
    </div>
  )
}
