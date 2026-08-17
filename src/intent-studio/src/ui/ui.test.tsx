import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Circle } from 'lucide-react'
import { AppThemeProvider, Button, Dialog, StageRail, useAppTheme, WorkbenchShell } from './index.ts'

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

  it('shows only panes relevant to the current authoring stage', () => {
    const panes = [
      { id: 'collaboration' as const, label: '目标', icon: Circle, minSize: 320, content: <div>goal content</div> },
      { id: 'outline' as const, label: '方向', icon: Circle, minSize: 320, content: <div>direction content</div> },
      { id: 'canvas' as const, label: '画布', icon: Circle, minSize: 320, content: <div>canvas content</div> },
    ]
    renderWithTheme(<WorkbenchShell
      header={<div>header</div>}
      contextBar={<StageRail stages={[{ id: 'goal', label: '目标' }, { id: 'outline', label: '大纲' }]} activeId="goal" />}
      panes={panes}
      visiblePaneIds={['collaboration', 'outline']}
      activePane="canvas"
      onActivePaneChange={() => undefined}
      storageKey="test.stage-layout"
    />)

    expect(screen.getByRole('navigation', { name: '卡带创作阶段' })).toBeTruthy()
    expect(screen.getByText('goal content')).toBeTruthy()
    expect(screen.getByText('direction content')).toBeTruthy()
    expect(screen.queryByText('canvas content')).toBeNull()
  })
})
