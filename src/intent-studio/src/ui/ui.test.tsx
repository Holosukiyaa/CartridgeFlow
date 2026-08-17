import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { AppThemeProvider, Button, Dialog, SemanticWorkbench, useAppTheme } from './index.ts'

beforeAll(() => {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  })
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
})

beforeEach(() => localStorage.clear())

function renderWithTheme(content: React.ReactNode) {
  return render(<AppThemeProvider>{content}</AppThemeProvider>)
}

describe('UI boundary', () => {
  it('keeps disabled buttons inert while preserving keyboard activation', async () => {
    const user = userEvent.setup()
    const enabled = vi.fn()
    const disabled = vi.fn()
    renderWithTheme(<>
      <Button onClick={enabled}>继续</Button>
      <Button disabled onClick={disabled}>不可用</Button>
    </>)

    await user.tab()
    await user.keyboard('{Enter}')
    expect(enabled).toHaveBeenCalledOnce()
    await user.click(screen.getByRole('button', { name: '不可用' }))
    expect(disabled).not.toHaveBeenCalled()
  })

  it('closes dialogs with Escape and exposes an accessible name', async () => {
    const user = userEvent.setup()
    const onClose = vi.fn()
    renderWithTheme(<Dialog opened onClose={onClose} title="连接 AI"><p>连接设置</p></Dialog>)

    expect(screen.getByRole('dialog', { name: '连接 AI' })).toBeTruthy()
    await user.keyboard('{Escape}')
    expect(onClose).toHaveBeenCalledOnce()
  })

  it('persists theme changes behind the provider API', async () => {
    const user = userEvent.setup()
    function ThemeHarness() {
      const { theme, setTheme } = useAppTheme()
      return <Button onClick={() => setTheme({ id: 'test', label: '测试主题', accent: '#123456', focus: '#234567', page: '#ffffff' })}>{theme.label}</Button>
    }
    renderWithTheme(<ThemeHarness />)

    await user.click(screen.getByRole('button', { name: '浅色主题' }))
    expect(screen.getByRole('button', { name: '测试主题' })).toBeTruthy()
    expect(JSON.parse(localStorage.getItem('cartridgeflow.creator-theme') || '{}').accent).toBe('#123456')
  })

  it('keeps the canvas primary while detail and AI panels can open together', () => {
    renderWithTheme(<SemanticWorkbench
      header={<div>header</div>}
      commandBar={<div>commands</div>}
      canvas={<div>canvas content</div>}
      detail={<div>detail content</div>}
      ai={<div>ai content</div>}
      detailOpen
      aiOpen
      activePanel="canvas"
      onActivePanelChange={() => undefined}
    />)

    expect(screen.getByRole('region', { name: '语义画布工作区' })).toBeTruthy()
    const panels = screen.getAllByRole('complementary')
    expect(panels.map((panel) => panel.getAttribute('aria-label'))).toEqual(['节点详情', 'AI 管家'])
  })
})
