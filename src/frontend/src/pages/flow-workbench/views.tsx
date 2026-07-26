import { useMemo, useState, type ReactNode } from 'react'
import { Box, Button } from '../../ui.tsx'
import { AlertTriangle, ChevronDown, ChevronUp, ClipboardCopy, Copy, Download, FileOutput, History, Pause, PlayCircle, RefreshCw, Square, SquarePen, X } from 'lucide-react'
import type { FlowEdge, FlowEvent, FlowFiles, FlowGraph, FlowLabDetail, FlowNode, RunResult } from '../../api.ts'
import type { CreateNodeHandler, GraphResult } from './types.ts'
import { FlowGraphView } from './FlowGraphView.tsx'
import { NodeDetailCard } from './NodeDetailCard.tsx'
import { NodeDrawer } from './NodeDrawer.tsx'
import { NODE_DETAIL_SECTION_BY_ID, nodeDetailId, type NodeDetailSection, type OpenNodeDetail } from './nodeDetails.ts'
import type { NodeRunState } from './runState.ts'

export function WorkbenchHeader({
  detail,
  cartridgeControls,
  runStatus,
  runBusy = false,
  historyOpen = false,
  onHistory,
  onRun,
  onPause,
  onStop,
  onCloneToDev,
  cloningToDev = false,
}: {
  detail: FlowLabDetail
  cartridgeControls?: ReactNode
  runStatus?: string
  runBusy?: boolean
  historyOpen?: boolean
  onHistory: () => void
  onRun: () => void
  onPause: () => void
  onStop: () => void
  onCloneToDev?: () => void
  cloningToDev?: boolean
}) {
  const running = ['created', 'running', 'retrying', 'recovering', 'rolling_back'].includes(runStatus || '')
  const paused = runStatus === 'paused'
  const stoppable = running || paused || runStatus === 'paused_waiting_user'
  return (
    <header className="cf-workbench-header">
      <div className="cf-workbench-brand">
        <span className="cf-workbench-brand-mark" aria-hidden="true">C</span>
        <strong>CARTRIDGE WORKSPACE <i>/</i> 卡带工作区</strong>
      </div>
      <div className="cf-workbench-header-spacer" />
      <div className="cf-workbench-actions">
        {!detail.cartridge.editable && onCloneToDev && (
          <Button className="cf-outline-btn" onClick={onCloneToDev} loading={cloningToDev} loadingText="复制中...">
            <Copy aria-hidden="true" />复制为可编辑版本
          </Button>
        )}
        <nav className="cf-workbench-mode-switch" aria-label="工作台模式">
          <Button className="active" aria-current="page"><SquarePen aria-hidden="true" />设计</Button>
          <div className="cf-workbench-runtime-controls" aria-label="运行控制">
            <button type="button" onClick={onRun} disabled={running || paused || runBusy} title="使用真实模型与真实工具运行当前流程">
              <PlayCircle aria-hidden="true" />运行
            </button>
            <button type="button" onClick={onPause} disabled={(!running && !paused) || runBusy} title={paused ? '从最近检查点继续运行' : '在当前节点完成后暂停'}>
              {paused ? <PlayCircle aria-hidden="true" /> : <Pause aria-hidden="true" />}{paused ? '继续' : '暂停'}
            </button>
            <button type="button" onClick={onStop} disabled={!stoppable || runBusy} title="停止当前运行">
              <Square aria-hidden="true" />停止
            </button>
            <button type="button" className={historyOpen ? 'active' : ''} onClick={onHistory} title="在画布右侧查看运行历史">
              <History aria-hidden="true" />历史
            </button>
          </div>
        </nav>
        {cartridgeControls}
      </div>
    </header>
  )
}

export function DesignView({
  graph, editable, files, flowId, selectedNode, focusNodeId, openNodeEditors,
  onSelectNode, onOpenNodeEditor, onCloseNodeEditor, onToggleNodeEditorPin, onNodeEditorPositionChange, onCloseUnpinnedNodeEditors, onLayoutSave, onEdgesSave, onCreateNode, onDeleteNode, onSaved,
  modelPanel, toolPanel, nodeRunStates, runEvents,
}: {
  graph: FlowGraph
  editable: boolean
  files: FlowFiles
  flowId: string
  selectedNode: FlowNode | null
  focusNodeId: string | null
  openNodeEditors: OpenNodeDetail[]
  onSelectNode: (node: FlowNode) => void
  onOpenNodeEditor: (node: FlowNode, section: NodeDetailSection) => void
  onCloseNodeEditor: (editorId: string) => void
  onToggleNodeEditorPin: (editorId: string) => void
  onNodeEditorPositionChange: (editorId: string, position: { x: number; y: number }) => void
  onCloseUnpinnedNodeEditors: () => void
  onLayoutSave: (layout: Record<string, { x: number; y: number }>) => Promise<void>
  onEdgesSave: (edges: FlowEdge[]) => Promise<void>
  onCreateNode: CreateNodeHandler
  onDeleteNode: (node: FlowNode) => Promise<void>
  onSaved: (result: GraphResult) => void
  modelPanel?: ReactNode
  toolPanel?: ReactNode
  nodeRunStates?: Map<string, NodeRunState>
  runEvents?: FlowEvent[]
}) {
  const nodeEditors = openNodeEditors.flatMap((editor) => {
    const node = graph.nodes.find((item) => item.id === editor.nodeId)
    const meta = NODE_DETAIL_SECTION_BY_ID.get(editor.section)
    if (!node || !meta) return []
    const editorId = nodeDetailId(node.id, editor.section)
    const nodeEvents = (runEvents || []).filter((event) => event.state === node.id)
    return [{
      editorId,
      nodeId: node.id,
      section: editor.section,
      width: meta.width,
      height: meta.height,
      connectorFraction: meta.connectorFraction,
      position: editor.position,
      content: editor.section === 'config' ? (
        <NodeDrawer
          node={node}
          graphEdges={graph.edges || []}
          flowId={flowId}
          files={files}
          editable={editable}
          open
          showSummary={false}
          pinned={editor.pinned}
          runState={nodeRunStates?.get(node.id)}
          runEvents={nodeEvents}
          onTogglePin={() => onToggleNodeEditorPin(editorId)}
          onClose={() => onCloseNodeEditor(editorId)}
          onDelete={() => onDeleteNode(node)}
          onSaved={onSaved}
        />
      ) : (
        <NodeDetailCard
          node={node}
          section={editor.section}
          graphEdges={graph.edges || []}
          pinned={editor.pinned}
          runState={nodeRunStates?.get(node.id)}
          runEvents={nodeEvents}
          onTogglePin={() => onToggleNodeEditorPin(editorId)}
          onClose={() => onCloseNodeEditor(editorId)}
        />
      ),
    }]
  })

  return (
    <div className={`cf-design-studio ${nodeEditors.length ? 'drawer-open' : ''}`}>
      <Box className="cf-flow-panel cf-flow-overview cf-flow-overview-studio" overflow="hidden">
        <FlowGraphView
          graph={graph}
          selectedNode={selectedNode}
          focusNodeId={focusNodeId}
          onSelectNode={onSelectNode}
          onOpenNodeEditor={onOpenNodeEditor}
          onNodeEditorPositionChange={onNodeEditorPositionChange}
          onLayoutSave={editable ? onLayoutSave : undefined}
          onEdgesSave={editable ? onEdgesSave : undefined}
          onCreateNode={editable ? onCreateNode : undefined}
          onDeleteNode={editable ? onDeleteNode : undefined}
          modelPanel={editable ? modelPanel : undefined}
          toolPanel={editable ? toolPanel : undefined}
          nodeEditors={nodeEditors}
          activeNodeEditorId={selectedNode?.id || null}
          onCloseNodeEditor={onCloseUnpinnedNodeEditors}
          nodeRunStates={nodeRunStates}
          runEvents={runEvents}
        />
      </Box>
    </div>
  )
}

const RUN_STATUS_LABELS: Record<string, string> = {
  completed: '已完成',
  failed: '失败',
  running: '运行中',
  created: '准备中',
  paused: '已暂停',
  paused_waiting_user: '等待交互',
  cancelled: '已停止',
  interrupted: '已中断',
  recovering: '恢复中',
  retrying: '重试中',
}

export function RunHistoryPanel({ runs, selectedRunId, busy = false, onSelect, onOpenLog, onRefresh, onClose }: {
  runs: RunResult[]
  selectedRunId?: string
  busy?: boolean
  onSelect: (runId: string) => void
  onOpenLog: (run: RunResult) => void
  onRefresh: () => void
  onClose: () => void
}) {
  const [expandedRunId, setExpandedRunId] = useState(selectedRunId || runs[0]?.run_id || '')
  return (
    <aside className="cf-canvas-history-panel">
      <header>
        <div><span>RUN HISTORY</span><strong>运行历史</strong><small>{runs.length} 条真实运行记录</small></div>
        <button type="button" onClick={onClose} title="关闭运行历史"><X aria-hidden="true" /></button>
      </header>
      <div className="cf-canvas-history-tools">
        <p>选择记录后，画布会同步显示该次运行的节点状态。</p>
        <button type="button" onClick={onRefresh} disabled={busy}><RefreshCw aria-hidden="true" />刷新</button>
      </div>
      <div className="cf-canvas-history-list">
        {runs.length ? runs.map((run) => {
          const error = run.error?.message || run.errors?.[run.errors.length - 1]?.message || ''
          const hasFailureLog = ['failed', 'interrupted'].includes(run.status) || Boolean(error)
          const expanded = expandedRunId === run.run_id
          const inputCount = Object.keys(run.inputs || {}).length
          const artifactCount = (run.delivery?.artifacts?.length || run.artifacts?.length || 0)
          const summary = error || run.data_chain?.summary || (inputCount ? `已收集 ${inputCount} 项运行输入，流程已完整执行。` : '运行已完成，未发现需要处理的异常。')
          return (
            <article key={run.run_id} className={`${run.run_id === selectedRunId ? 'active' : ''}${expanded ? ' expanded' : ''}`}>
              <button type="button" className="cf-canvas-history-select" onClick={() => { setExpandedRunId(run.run_id); onSelect(run.run_id) }}>
                <span className="cf-canvas-history-status"><i className={run.status} />{RUN_STATUS_LABELS[run.status] || run.status}<time>{String(run.updated_at || run.created_at || '').replace('T', ' ').slice(5, 16) || '时间未知'}</time></span>
                <strong>{run.current_state || '尚未进入节点'}</strong>
                <code>{run.run_id}</code>
                <span className="cf-canvas-history-chevron" aria-hidden="true">{expanded ? <ChevronUp /> : <ChevronDown />}</span>
              </button>
              {expanded && <div className="cf-canvas-history-expanded">
                <div className="cf-canvas-history-summary"><span>摘要</span><p>{summary}</p></div>
                <div className="cf-canvas-history-actions">
                  <button type="button" className={hasFailureLog ? 'is-error' : ''} onClick={() => onOpenLog(run)}>{hasFailureLog ? <AlertTriangle aria-hidden="true" /> : <History aria-hidden="true" />}{hasFailureLog ? '查看错误日志' : '查看日志'}</button>
                  <button type="button" disabled={!artifactCount} title={artifactCount ? `打开 ${artifactCount} 个运行产物` : '本次运行没有可打开的产物'}><FileOutput aria-hidden="true" />打开产物</button>
                </div>
              </div>}
            </article>
          )
        }) : <div className="cf-canvas-history-empty"><History aria-hidden="true" /><strong>还没有运行记录</strong><span>从顶部“运行”开始第一次真实测试。</span></div>}
      </div>
    </aside>
  )
}

function eventTimestamp(event: FlowEvent) {
  return String((event as any).created_at || '').replace('T', ' ').replace('Z', '') || '时间未知'
}

function eventTone(event: FlowEvent) {
  const type = String(event.type || '')
  if (type.includes('failed') || type.includes('blocked') || type.includes('cancelled')) return 'error'
  if (type.includes('paused') || type.includes('recovery') || type.includes('retry')) return 'warning'
  if (type.includes('completed') || type.includes('executed') || type.includes('delivery_ready')) return 'success'
  if (type.includes('started') || type.includes('entered') || type.includes('traversed')) return 'active'
  return 'info'
}

function eventLabel(event: FlowEvent) {
  const type = String(event.type || '')
  if (type.includes('failed')) return '错误'
  if (type.includes('completed')) return '完成'
  if (type.includes('executed')) return '已执行'
  if (type.includes('started')) return '开始'
  if (type.includes('entered')) return '进入节点'
  if (type.includes('traversed')) return '流程转移'
  if (type.includes('paused')) return '已暂停'
  if (type.includes('delivery')) return '交付'
  return '运行事件'
}

function buildFailureSummary(run: RunResult, events: FlowEvent[]) {
  const errors = [run.error, ...(run.errors || [])].filter(Boolean) as any[]
  const failedEvents = events.filter((event) => event.type === 'lab_node_failed' || event.type === 'run_failed')
  const lines = [
    `Run: ${run.run_id}`,
    `Status: ${run.status}`,
    `Node: ${run.current_state || errors[0]?.node_id || 'unknown'}`,
  ]
  errors.forEach((error) => lines.push(`[${error.code || 'RUNTIME_ERROR'}] ${error.message || '运行失败'}`))
  failedEvents.forEach((event) => {
    const data = (event.data || {}) as any
    const envelope = data.error_envelope || {}
    const message = envelope.message || data.error || data.reason || event.message
    if (message) lines.push(`${event.state || 'runtime'}: ${message}`)
  })
  return [...new Set(lines)].join('\n')
}

async function writeClipboardText(value: string) {
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(value)
      return
    } catch {
      // Fall through for local HTTP pages and restricted browser profiles.
    }
  }
  const field = document.createElement('textarea')
  field.value = value
  field.setAttribute('readonly', '')
  field.style.position = 'fixed'
  field.style.opacity = '0'
  document.body.appendChild(field)
  field.select()
  const copied = document.execCommand('copy')
  field.remove()
  if (!copied) throw new Error('Clipboard access is unavailable')
}

export function RunLogDialog({ run, events, onClose }: { run: RunResult; events: FlowEvent[]; onClose: () => void }) {
  const [copied, setCopied] = useState(false)
  const logLines = useMemo(() => events.map((event, index) => {
    const severity = eventTone(event).toUpperCase()
    const detail = event.data && Object.keys(event.data).length ? `\n    ${JSON.stringify(event.data)}` : ''
    return `${String(index + 1).padStart(2, '0')}  [${eventTimestamp(event)}] [${severity}] ${event.message || event.type || 'runtime event'}${detail}`
  }), [events])
  const failureSummary = useMemo(() => buildFailureSummary(run, events), [events, run])
  const isFailure = ['failed', 'interrupted'].includes(run.status) || Boolean(run.error) || Boolean(run.errors?.length)
  const copySummary = async () => {
    const summary = isFailure ? failureSummary : [`Run: ${run.run_id}`, `Status: ${run.status}`, `Last node: ${run.current_state || 'completed'}`, `Events: ${events.length}`].join('\n')
    await writeClipboardText(summary)
    setCopied(true)
    window.setTimeout(() => setCopied(false), 2000)
  }
  const exportLog = () => {
    const blob = new Blob([logLines.join('\n')], { type: 'text/plain;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = `${run.run_id}.log.txt`
    anchor.click()
    URL.revokeObjectURL(url)
  }
  return (
    <div className="cf-run-log-backdrop" onClick={onClose}>
      <section className="cf-run-log-dialog" role="dialog" aria-modal="true" aria-label="运行详细日志" onClick={(event) => event.stopPropagation()}>
        <header><div><span>{isFailure ? 'FAILED RUN' : 'RUN DETAIL'}</span><strong>运行详细日志</strong><small>{run.run_id} · {RUN_STATUS_LABELS[run.status] || run.status}</small></div><button type="button" onClick={onClose} title="关闭日志"><X aria-hidden="true" /></button></header>
        <div className="cf-run-log-actions">
          <button type="button" onClick={() => void copySummary()}><ClipboardCopy aria-hidden="true" />{copied ? '已复制' : isFailure ? '复制错误信息' : '复制运行摘要'}</button>
          <button type="button" onClick={exportLog}><Download aria-hidden="true" />导出日志</button>
        </div>
        <div className="cf-run-log-events" role="log" aria-label="运行事件列表">
          {events.length ? events.map((event, index) => {
            const tone = eventTone(event)
            const data = event.data && Object.keys(event.data).length ? event.data : null
            return <article className={`cf-run-log-event ${tone}`} key={`${event.created_at || event.timestamp || ''}-${index}`}>
              <div className="cf-run-log-event-rail"><i /><span>{String(index + 1).padStart(2, '0')}</span></div>
              <div className="cf-run-log-event-main">
                <header><span className="cf-run-log-event-label">{eventLabel(event)}</span><time>{eventTimestamp(event)}</time></header>
                <strong>{event.message || event.type || '运行事件'}</strong>
                <div className="cf-run-log-event-meta"><code>{event.state || 'runtime'}</code>{event.type && <span>{event.type}</span>}</div>
                {data && <details><summary>查看事件数据</summary><pre>{JSON.stringify(data, null, 2)}</pre></details>}
              </div>
            </article>
          }) : <div className="cf-run-log-empty">这次运行没有留下可读取的事件日志。</div>}
        </div>
      </section>
    </div>
  )
}
