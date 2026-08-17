import { useCallback, type ReactNode } from 'react'
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
  contextBar?: ReactNode
  panes: WorkbenchPaneDefinition[]
  visiblePaneIds?: WorkbenchPaneId[]
  activePane: WorkbenchPaneId
  onActivePaneChange: (pane: WorkbenchPaneId) => void
  storageKey: string
  className?: string
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

export function WorkbenchShell({ header, contextBar, panes, visiblePaneIds, activePane, onActivePaneChange, storageKey, className = '' }: WorkbenchShellProps) {
  const compact = useMediaQuery('(max-width: 1280px)', false, { getInitialValueInEffect: false })
  const visiblePanes = visiblePaneIds?.length ? panes.filter((pane) => visiblePaneIds.includes(pane.id)) : panes
  const paneKey = visiblePanes.map((pane) => pane.id).join('.')
  const layoutKey = `${storageKey}:${paneKey}`

  const saveSizes = useCallback((next: number[]) => {
    if (next.length !== visiblePanes.length || next.some((size) => !Number.isFinite(size) || size <= 0)) return
    localStorage.setItem(storageKey, JSON.stringify(next))
  }, [visiblePanes.length, storageKey])

  const defaultSizes = readSizes(storageKey, visiblePanes) || visiblePanes.map((pane) => pane.preferredSize || pane.minSize)
  const compactPane = visiblePanes.find((pane) => pane.id === activePane) || visiblePanes[0]

  return <main className={`creator-workspace creator-workbench ${className}`.trim()}>
    {header}
    {contextBar}
    {compact && compactPane && <Tabs value={compactPane.id} onChange={(value) => value && onActivePaneChange(value as WorkbenchPaneId)} className="workbench-pane-tabs">
      <Tabs.List grow aria-label="工作区视图">
        {visiblePanes.map(({ id, label, icon: Icon }) => <Tabs.Tab key={id} value={id} leftSection={<Icon size={16} />}>{label}</Tabs.Tab>)}
      </Tabs.List>
    </Tabs>}
    <div className="workbench-panes">
      {compact ? compactPane && <WorkbenchPane id={compactPane.id}>{compactPane.content}</WorkbenchPane> : <Allotment key={layoutKey} defaultSizes={defaultSizes} onDragEnd={saveSizes} separator>
        {visiblePanes.map((pane) => <Allotment.Pane key={pane.id} minSize={pane.minSize} preferredSize={pane.preferredSize} snap>
          <WorkbenchPane id={pane.id}>{pane.content}</WorkbenchPane>
        </Allotment.Pane>)}
      </Allotment>}
    </div>
  </main>
}

export function StageRail({ stages, activeId }: { stages: Array<{ id: string; label: string }>; activeId: string }) {
  const activeIndex = Math.max(0, stages.findIndex((stage) => stage.id === activeId))
  return <nav className="creator-stage-rail" aria-label="卡带创作阶段">
    <ol>{stages.map((stage, index) => {
      const state = index < activeIndex ? 'completed' : index === activeIndex ? 'current' : 'upcoming'
      return <li key={stage.id} data-state={state} aria-current={state === 'current' ? 'step' : undefined}>{stage.label}</li>
    })}</ol>
  </nav>
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
