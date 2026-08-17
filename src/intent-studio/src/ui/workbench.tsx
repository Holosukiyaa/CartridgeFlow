import { useCallback, useEffect, useState, type ReactNode } from 'react'
import { useMediaQuery } from '@mantine/hooks'
import { Tabs } from '@mantine/core'
import { Allotment } from 'allotment'
import type { LucideIcon } from 'lucide-react'

export type WorkbenchPaneId = 'collaboration' | 'outline' | 'canvas'

export type WorkbenchPaneDefinition = {
  id: WorkbenchPaneId
  label: string
  icon: LucideIcon
  minSize: number
  preferredSize?: number
  content: ReactNode
}

type WorkbenchShellProps = {
  header: ReactNode
  panes: WorkbenchPaneDefinition[]
  activePane: WorkbenchPaneId
  onActivePaneChange: (pane: WorkbenchPaneId) => void
  storageKey: string
}

function readSizes(storageKey: string, panes: WorkbenchPaneDefinition[]) {
  try {
    const value = JSON.parse(localStorage.getItem(storageKey) || 'null')
    if (Array.isArray(value) && value.length === panes.length && value.every((size) => typeof size === 'number' && size > 0)) return value as number[]
  } catch {
    // Ignore stale layout preferences.
  }
  return undefined
}

export function WorkbenchShell({ header, panes, activePane, onActivePaneChange, storageKey }: WorkbenchShellProps) {
  const compact = useMediaQuery('(max-width: 1120px)', false, { getInitialValueInEffect: false })
  const [sizes, setSizes] = useState(() => readSizes(storageKey, panes))

  useEffect(() => {
    setSizes(readSizes(storageKey, panes))
  }, [storageKey, panes.length])

  const saveSizes = useCallback((next: number[]) => {
    if (next.length !== panes.length || next.some((size) => !Number.isFinite(size) || size <= 0)) return
    setSizes(next)
    localStorage.setItem(storageKey, JSON.stringify(next))
  }, [panes.length, storageKey])

  const defaultSizes = sizes || (() => {
    const available = window.innerWidth
    const collaboration = panes[0]?.preferredSize || 320
    const canvasMinimum = panes[2]?.minSize || 420
    const outline = Math.min(panes[1]?.preferredSize || 416, Math.max(panes[1]?.minSize || 368, available - collaboration - canvasMinimum))
    return [collaboration, outline, Math.max(canvasMinimum, available - collaboration - outline)]
  })()
  const compactPane = panes.find((pane) => pane.id === activePane) || panes[0]

  return <main className="creator-workspace creator-workbench">
    {header}
    {compact && <Tabs value={activePane} onChange={(value) => value && onActivePaneChange(value as WorkbenchPaneId)} className="workbench-pane-tabs">
      <Tabs.List grow aria-label="工作区视图">
        {panes.map(({ id, label, icon: Icon }) => <Tabs.Tab key={id} value={id} leftSection={<Icon size={16} />}>{label}</Tabs.Tab>)}
      </Tabs.List>
    </Tabs>}
    <div className="workbench-panes">
      {compact ? compactPane && <WorkbenchPane id={compactPane.id}>{compactPane.content}</WorkbenchPane> : <Allotment defaultSizes={defaultSizes} onDragEnd={saveSizes} separator>
        {panes.map((pane) => <Allotment.Pane key={pane.id} minSize={pane.minSize} preferredSize={pane.preferredSize} snap>
          <WorkbenchPane id={pane.id}>{pane.content}</WorkbenchPane>
        </Allotment.Pane>)}
      </Allotment>}
    </div>
  </main>
}

export function WorkbenchPane({ id, hidden = false, children }: { id: WorkbenchPaneId; hidden?: boolean; children: ReactNode }) {
  return <section className="workbench-pane" data-pane={id} hidden={hidden}>{children}</section>
}

export function PaneHeader({ icon: Icon, title, detail, actions }: { icon?: LucideIcon; title: string; detail?: ReactNode; actions?: ReactNode }) {
  return <header className="ui-pane-header">
    <div>{Icon && <Icon size={16} />}<strong>{title}</strong>{detail && <span>{detail}</span>}</div>
    {actions && <div className="ui-pane-actions">{actions}</div>}
  </header>
}

export function Section({ title, children, actions }: { title?: string; children: ReactNode; actions?: ReactNode }) {
  return <section className="ui-section">
    {(title || actions) && <header>{title && <strong>{title}</strong>}{actions}</header>}
    {children}
  </section>
}

export function StatusIndicator({ state, children }: { state: 'loading' | 'disabled' | 'error' | 'selected' | 'confirmed' | 'unresolved' | 'neutral'; children: ReactNode }) {
  return <span className={`ui-status is-${state}`}><i />{children}</span>
}

export function EmptyState({ icon: Icon, title, description, action }: { icon?: LucideIcon; title: string; description?: string; action?: ReactNode }) {
  return <div className="ui-empty-state">{Icon && <Icon size={28} />}<strong>{title}</strong>{description && <p>{description}</p>}{action}</div>
}
