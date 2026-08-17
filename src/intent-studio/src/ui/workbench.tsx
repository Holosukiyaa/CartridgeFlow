import type { ReactNode } from 'react'
import { Tabs } from '@mantine/core'
import { useMediaQuery } from '@mantine/hooks'

export type SemanticPanelId = 'canvas' | 'detail' | 'ai'

export function SemanticWorkbench({
  header,
  commandBar,
  canvas,
  detail,
  ai,
  detailOpen,
  aiOpen,
  activePanel,
  onActivePanelChange,
}: {
  header: ReactNode
  commandBar: ReactNode
  canvas: ReactNode
  detail?: ReactNode
  ai?: ReactNode
  detailOpen: boolean
  aiOpen: boolean
  activePanel: SemanticPanelId
  onActivePanelChange: (panel: SemanticPanelId) => void
}) {
  const compact = useMediaQuery('(max-width: 1280px)', false, { getInitialValueInEffect: false })
  const availablePanels: Array<{ id: SemanticPanelId; label: string }> = [
    { id: 'canvas', label: '语义画布' },
    ...(detailOpen && detail ? [{ id: 'detail' as const, label: '详情' }] : []),
    ...(aiOpen && ai ? [{ id: 'ai' as const, label: 'AI 管家' }] : []),
  ]
  const visiblePanel = availablePanels.some((panel) => panel.id === activePanel) ? activePanel : 'canvas'

  return <main className={`creator-workspace semantic-workbench${detailOpen ? ' has-detail' : ''}${aiOpen ? ' has-ai' : ''}`}>
    {header}
    {commandBar}
    {compact && <Tabs value={visiblePanel} onChange={(value) => value && onActivePanelChange(value as SemanticPanelId)} className="semantic-panel-tabs">
      <Tabs.List grow aria-label="工作台面板">
        {availablePanels.map((panel) => <Tabs.Tab key={panel.id} value={panel.id}>{panel.label}</Tabs.Tab>)}
      </Tabs.List>
    </Tabs>}
    <div className="semantic-workbench-body">
      {(!compact || visiblePanel === 'canvas') && <section className="semantic-canvas-region" aria-label="语义画布工作区">{canvas}</section>}
      {detailOpen && detail && (!compact || visiblePanel === 'detail') && <aside className="semantic-side-panel semantic-detail-panel" aria-label="节点详情">{detail}</aside>}
      {aiOpen && ai && (!compact || visiblePanel === 'ai') && <aside className="semantic-side-panel semantic-ai-panel" aria-label="AI 管家">{ai}</aside>}
    </div>
  </main>
}
