import type { PointerEvent as ReactPointerEvent } from 'react'
import { ChevronDown, ChevronUp, GripVertical, Link2, Trash2 } from 'lucide-react'
import type { FlowAnnotation } from '../../api.ts'

export function CanvasAnnotationCard({
  annotation,
  active,
  editable,
  anchorLabel,
  onSelect,
  onPatch,
  onCommit,
  onDelete,
  onToggleCollapsed,
  onPointerDown,
  onPointerMove,
  onPointerUp,
  onResizePointerDown,
}: {
  annotation: FlowAnnotation
  active: boolean
  editable: boolean
  anchorLabel?: string
  onSelect: () => void
  onPatch: (patch: Partial<FlowAnnotation>) => void
  onCommit: () => void
  onDelete: () => void
  onToggleCollapsed: () => void
  onPointerDown: (event: ReactPointerEvent<HTMLDivElement>) => void
  onPointerMove: (event: ReactPointerEvent<HTMLDivElement>) => void
  onPointerUp: (event: ReactPointerEvent<HTMLDivElement>) => void
  onResizePointerDown: (event: ReactPointerEvent<HTMLButtonElement>) => void
}) {
  return (
    <div
      className={`cf-canvas-annotation-shell nodrag nopan nowheel ${active ? 'active' : ''} tone-${annotation.tone} ${annotation.collapsed ? 'collapsed' : ''}`}
      data-annotation-id={annotation.id}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={onPointerUp}
      onClick={onSelect}
    >
      <article className="cf-canvas-annotation-card">
        <header className="cf-canvas-annotation-head">
          <GripVertical aria-hidden="true" />
          <input
            value={annotation.title}
            readOnly={!editable}
            maxLength={160}
            aria-label="注释标题"
            onPointerDown={(event) => event.stopPropagation()}
            onChange={(event) => onPatch({ title: event.target.value })}
            onBlur={onCommit}
          />
          <div className="cf-canvas-annotation-actions">
            <button type="button" onClick={(event) => { event.stopPropagation(); onToggleCollapsed() }} title={annotation.collapsed ? '展开注释' : '折叠注释'}>
              {annotation.collapsed ? <ChevronDown /> : <ChevronUp />}
            </button>
            {editable && <button type="button" className="danger" onClick={(event) => { event.stopPropagation(); onDelete() }} title="删除注释"><Trash2 /></button>}
          </div>
        </header>
        {!annotation.collapsed && (
          <>
            <textarea
              value={annotation.body}
              readOnly={!editable}
              maxLength={10000}
              placeholder="记录设计原因、约束或待处理事项"
              aria-label="注释正文"
              onPointerDown={(event) => event.stopPropagation()}
              onChange={(event) => onPatch({ body: event.target.value })}
              onBlur={onCommit}
            />
            <footer>
              <div className="cf-canvas-annotation-tones" role="group" aria-label="注释样式">
                <button type="button" className={`neutral ${annotation.tone === 'neutral' ? 'active' : ''}`} onClick={(event) => { event.stopPropagation(); onPatch({ tone: 'neutral' }); window.setTimeout(onCommit, 0) }} title="普通注释" aria-label="普通注释" />
                <button type="button" className={`warning ${annotation.tone === 'warning' ? 'active' : ''}`} onClick={(event) => { event.stopPropagation(); onPatch({ tone: 'warning' }); window.setTimeout(onCommit, 0) }} title="提醒注释" aria-label="提醒注释" />
              </div>
              {anchorLabel && <span className="cf-canvas-annotation-anchor" title={`关联节点：${anchorLabel}`}><Link2 />{anchorLabel}</span>}
            </footer>
            {editable && <button type="button" className="cf-canvas-annotation-resize" onPointerDown={onResizePointerDown} title="调整大小" aria-label="调整注释大小" />}
          </>
        )}
      </article>
    </div>
  )
}
