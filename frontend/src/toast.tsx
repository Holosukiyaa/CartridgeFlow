// Toast 工具：纯 React 实现
import { useState, useCallback, useEffect, type ReactNode } from 'react'

interface ToastItem {
  id: number
  title: string
  description?: string
  type: 'success' | 'error' | 'info' | 'warning' | 'loading'
}

let _nextId = 0

// ── 全局 toast 函数（各页面直接调用，不依赖 Context） ──
type ToastFn = (t: Omit<ToastItem, 'id'>) => void
let _globalAdd: ToastFn | null = null
export function showToast(options: { title: string; description?: string; type?: 'success' | 'error' | 'info' | 'warning' | 'loading' }) {
  _globalAdd?.({ title: options.title, description: options.description, type: options.type || 'info' })
}

// ── ToastProvider ──
export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([])

  const addToast = useCallback((t: Omit<ToastItem, 'id'>) => {
    const id = ++_nextId
    setToasts((prev) => [...prev, { ...t, id }])
  }, [])

  const removeToast = useCallback((id: number) => {
    setToasts((prev) => prev.filter((x) => x.id !== id))
  }, [])

  useEffect(() => {
    _globalAdd = addToast
    return () => { _globalAdd = null }
  }, [addToast])

  // 自动移除过期 toast
  useEffect(() => {
    if (toasts.length === 0) return
    const latest = toasts[toasts.length - 1]
    const timer = setTimeout(() => removeToast(latest.id), 3000)
    return () => clearTimeout(timer)
  }, [toasts, removeToast])

  const colorMap: Record<string, string> = {
    success: '#eef7ef', error: '#fff4ee', info: '#fffaf5', warning: '#fef9f0', loading: '#fffaf5',
  }
  const borderMap: Record<string, string> = {
    success: '#cde3d2', error: '#d58f76', info: '#e5dbcf', warning: '#e8d5b0', loading: '#e5dbcf',
  }
  const textMap: Record<string, string> = {
    success: '#34533d', error: '#7b331f', info: '#5b534b', warning: '#8a6d3b', loading: '#81776c',
  }

  return (
    <>
      {children}
      <div style={{
        position: 'fixed', top: '1rem', right: '1rem', zIndex: 9999,
        display: 'flex', flexDirection: 'column', gap: '8px', maxWidth: '360px',
      }}>
        {toasts.map((t) => (
          <div
            key={t.id}
            onClick={() => removeToast(t.id)}
            style={{
              padding: '14px 18px', borderRadius: '14px',
              border: `1px solid ${borderMap[t.type] || '#e5dbcf'}`,
              background: colorMap[t.type] || '#fffaf5',
              color: textMap[t.type] || '#302a24',
              fontSize: '13px', fontWeight: 600,
              boxShadow: '0 8px 24px rgba(75,55,40,.08)',
              cursor: 'pointer', animation: 'fadeUp .2s ease',
              display: 'flex', flexDirection: 'column', gap: '3px',
            }}
          >
            <div style={{ fontWeight: 800 }}>{t.title}</div>
            {t.description && <div style={{ fontSize: '12px', opacity: .75 }}>{t.description}</div>}
          </div>
        ))}
      </div>
    </>
  )
}
