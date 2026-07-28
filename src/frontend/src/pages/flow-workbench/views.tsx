import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { Box, Button } from '../../ui.tsx'
import { AlertTriangle, Bot, Braces, ChevronDown, ChevronUp, ClipboardCopy, Copy, Download, FileOutput, History, PanelRight, Pause, PlayCircle, RefreshCw, Square, SquarePen, X } from 'lucide-react'
import type { AIFlowSelection, AIFlowStewardContext, FlowAnnotation, FlowEdge, FlowEvent, FlowFiles, FlowGraph, FlowLabDetail, FlowNode, RunResult } from '../../api.ts'
import type { CreateNodeHandler, DesignDisplayMode, GraphResult, NodeDraft } from './types.ts'
import { FlowGraphView, type CanvasTool } from './FlowGraphView.tsx'
import { NodeDetailCard } from './NodeDetailCard.tsx'
import { BrandMark } from './BrandMark.tsx'
import { NODE_DETAIL_SECTION_BY_ID, nodeDetailId, type NodeDetailSection, type OpenNodeDetail } from './nodeDetails.ts'
import type { NodeRunState } from './runState.ts'
import { makeNodeDraft } from './nodeModel.ts'
import { saveNodeDraft } from './nodeEditing.ts'
import { showToast } from '../../toast.tsx'
import { buildNodeAuthoringPath } from './nodeAuthoring.ts'
import { EngineeringInspector } from './EngineeringInspector.tsx'
import { buildEngineeringDataRelations, buildEngineeringNodeModels, type EngineeringEdgeVisibility } from './engineeringNode.ts'
import { AIFlowStewardPanel } from './AIFlowStewardPanel.tsx'

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
  const paused = ['paused', 'paused_waiting_user'].includes(runStatus || '')
  const stoppable = running || paused
  return (
    <header className="cf-workbench-header">
      <div className="cf-workbench-brand">
        <BrandMark className="cf-workbench-brand-mark" />
        <strong>CARTRIDGE WORKSPACE <i>/</i> 卡带工作台</strong>
        <div className="cf-workbench-protocol-tags" aria-label="协议支持"><span>基座协议 v0.7</span><span>Flow Graph v0.7</span><span>LLM Binding v0.7</span><span>MCP v0.7</span></div>
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
            <button type="button" className={paused ? 'active' : ''} onClick={onPause} disabled={(!running && !paused) || runBusy} title={paused ? '从最近检查点继续运行' : '在当前节点完成后暂停'}>
              {paused ? <PlayCircle aria-hidden="true" /> : <Pause aria-hidden="true" />}{paused ? '继续' : '暂停'}
            </button>
            <button type="button" className={stoppable ? 'active' : ''} onClick={onStop} disabled={!stoppable || runBusy} title="停止当前运行">
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
  onSelectNode, onGuideNodeEditor, onCloseNodeEditor, onToggleNodeEditorPin, onNodeEditorPositionChange, onCloseUnpinnedNodeEditors, onLayoutSave, autoLayoutOnMount, onAutoLayoutComplete, onEdgesSave, onAnnotationsSave, onCreateNode, onDeleteNode, onFilesChange, onSaved,
  modelPanel, toolPanel, packagePanel, cartridgePanel, runStatus, nodeRunStates, runEvents, runCompletionVisible, runCompletion, onDismissRunCompletion, onOpenRunLog, onOpenPendingInteraction,
}: {
  graph: FlowGraph
  editable: boolean
  files: FlowFiles
  flowId: string
  selectedNode: FlowNode | null
  focusNodeId: string | null
  openNodeEditors: OpenNodeDetail[]
  onSelectNode: (node: FlowNode) => void
  onGuideNodeEditor: (node: FlowNode, section: NodeDetailSection) => void
  onCloseNodeEditor: (editorId: string) => void
  onToggleNodeEditorPin: (editorId: string) => void
  onNodeEditorPositionChange: (editorId: string, position: { x: number; y: number }) => void
  onCloseUnpinnedNodeEditors: () => void
  onLayoutSave: (layout: Record<string, { x: number; y: number }>) => Promise<void>
  autoLayoutOnMount?: boolean
  onAutoLayoutComplete?: () => void
  onEdgesSave: (edges: FlowEdge[]) => Promise<void>
  onAnnotationsSave: (annotations: FlowAnnotation[]) => Promise<void>
  onCreateNode: CreateNodeHandler
  onDeleteNode: (node: FlowNode) => Promise<void>
  onFilesChange: (files: FlowFiles) => void
  onSaved: (result: GraphResult) => void
  modelPanel?: ReactNode
  toolPanel?: ReactNode
  packagePanel?: ReactNode
  cartridgePanel?: ReactNode
  runStatus?: string
  nodeRunStates?: Map<string, NodeRunState>
  runEvents?: FlowEvent[]
  runCompletionVisible?: boolean
  runCompletion?: RunResult
  onDismissRunCompletion?: () => void
  onOpenRunLog?: (run: RunResult) => void
  onOpenPendingInteraction?: () => void
}) {
  const [engineeringInspectorOpen, setEngineeringInspectorOpen] = useState(false)
  const [stewardOpen, setStewardOpen] = useState(false)
  const [displayMode, setDisplayMode] = useState<DesignDisplayMode>('engineering')
  const [canvasTool, setCanvasTool] = useState<CanvasTool>('select')
  const [stewardRevision, setStewardRevision] = useState('')
  const [stewardSelection, setStewardSelection] = useState<AIFlowSelection>({ node_ids: [], edge_ids: [], field_paths: [] })
  const [engineeringUnlocked, setEngineeringUnlocked] = useState(false)
  const [edgeVisibility, setEdgeVisibility] = useState<EngineeringEdgeVisibility>({ control: true, data: true, dependency: true, branch: true, failure: true })
  const [nodeDrafts, setNodeDrafts] = useState<Record<string, NodeDraft>>({})
  const [savingNodeIds, setSavingNodeIds] = useState<Set<string>>(() => new Set())
  const engineeringDataRelations = useMemo(() => buildEngineeringDataRelations(graph), [graph])
  const engineeringRelationCounts = useMemo(() => {
    const relations = engineeringDataRelations
    return {
      data: relations.filter((relation) => relation.kind === 'data').length,
      dependency: relations.filter((relation) => relation.kind === 'dependency').length,
    }
  }, [engineeringDataRelations])
  const authoringPaths = useMemo(() => new Map(graph.nodes.flatMap((node) => {
    const path = editable ? buildNodeAuthoringPath(node, graph, files) : null
    return path ? [[node.id, path] as const] : []
  })), [editable, files, graph])
  const updateStewardSelection = useCallback((next: AIFlowSelection) => {
    setStewardSelection((current) => (
      current.node_ids.join('\u0000') === next.node_ids.join('\u0000')
      && current.edge_ids.join('\u0000') === next.edge_ids.join('\u0000')
      && current.field_paths.join('\u0000') === next.field_paths.join('\u0000')
        ? current
        : next
    ))
  }, [])

  useEffect(() => {
    let active = true
    const bytes = new TextEncoder().encode(files.root_flow || JSON.stringify(graph))
    crypto.subtle.digest('SHA-256', bytes).then((buffer) => {
      if (!active) return
      const next = [...new Uint8Array(buffer)].slice(0, 8).map((value) => value.toString(16).padStart(2, '0')).join('')
      setStewardRevision((current) => {
        if (current && current !== next) setStewardSelection({ node_ids: [], edge_ids: [], field_paths: [] })
        return next
      })
    })
    return () => { active = false }
  }, [files.root_flow, graph])

  const updateNodeDraft = useCallback((node: FlowNode, patch: Partial<NodeDraft>) => {
    setNodeDrafts((current) => ({
      ...current,
      [node.id]: { ...(current[node.id] || makeNodeDraft(node)), ...patch },
    }))
  }, [])

  const resetNodeDraft = useCallback((nodeId: string) => {
    setNodeDrafts((current) => {
      const next = { ...current }
      delete next[nodeId]
      return next
    })
  }, [])

  const persistNodeDraft = useCallback(async (node: FlowNode) => {
    const draft = nodeDrafts[node.id] || makeNodeDraft(node)
    setSavingNodeIds((current) => new Set(current).add(node.id))
    try {
      const result = await saveNodeDraft(flowId, files, node, draft)
      resetNodeDraft(node.id)
      onSaved(result)
      return result
    } catch (error: any) {
      showToast({ title: '节点保存失败', description: error?.message || String(error), type: 'error' })
      return null
    } finally {
      setSavingNodeIds((current) => {
        const next = new Set(current)
        next.delete(node.id)
        return next
      })
    }
  }, [files, flowId, nodeDrafts, onSaved, resetNodeDraft])

  const nodeEditors = openNodeEditors.flatMap((editor) => {
    const node = graph.nodes.find((item) => item.id === editor.nodeId)
    const meta = NODE_DETAIL_SECTION_BY_ID.get(editor.section)
    if (!node || !meta) return []
    const editorId = nodeDetailId(node.id, editor.section)
    const nodeEvents = (runEvents || []).filter((event) => event.state === node.id)
    const authoringPath = authoringPaths.get(node.id) || null
    const authoringIndex = authoringPath?.steps.findIndex((item) => item.section === editor.section) ?? -1
    const nextAuthoringStep = authoringPath && authoringIndex >= 0 ? authoringPath.steps[authoringIndex + 1] : null
    const continueAuthoring = (targetNode: FlowNode) => {
      onCloseNodeEditor(editorId)
      if (nextAuthoringStep) onGuideNodeEditor(targetNode, nextAuthoringStep.section)
    }
    return [{
      editorId,
      nodeId: node.id,
      section: editor.section,
      width: meta.width,
      height: meta.height,
      connectorFraction: meta.connectorFraction,
      position: editor.position,
      content: <NodeDetailCard
        node={node}
        section={editor.section}
        graphNodes={graph.nodes}
        graphEdges={graph.edges || []}
        files={files}
        flowId={flowId}
        pinned={editor.pinned}
        runState={nodeRunStates?.get(node.id)}
        runEvents={nodeEvents}
        editable={editable && !node.locked && node.scope !== 'root' && editor.section !== 'runtime'}
        draft={nodeDrafts[node.id] || makeNodeDraft(node)}
        dirty={Boolean(nodeDrafts[node.id] && JSON.stringify(nodeDrafts[node.id]) !== JSON.stringify(makeNodeDraft(node)))}
        saving={savingNodeIds.has(node.id)}
        authoringPath={authoringPath}
        onFilesChange={onFilesChange}
        onDraftChange={(patch) => updateNodeDraft(node, patch)}
        onReset={() => resetNodeDraft(node.id)}
        onSave={async () => { await persistNodeDraft(node) }}
        onContinue={() => continueAuthoring(node)}
        onSaveAndContinue={async () => {
          const result = await persistNodeDraft(node)
          if (!result) return
          continueAuthoring(result.graph.nodes.find((item) => item.id === node.id) || node)
        }}
        onTogglePin={() => onToggleNodeEditorPin(editorId)}
        onClose={() => onCloseNodeEditor(editorId)}
      />,
    }]
  })

  const engineering = displayMode === 'engineering'
  const stewardTool = canvasTool === 'steward-pointer' ? 'pointer' : canvasTool === 'steward-lasso' ? 'lasso' : 'none'
  const stewardContext = useMemo<AIFlowStewardContext>(() => ({
    tool: stewardTool,
    view: displayMode,
    revision: stewardRevision,
    selection: stewardSelection,
    scope_policy: stewardTool === 'pointer' ? 'single_anchor' : 'selected_and_direct_edges',
  }), [displayMode, stewardRevision, stewardSelection, stewardTool])
  useEffect(() => { setEngineeringUnlocked(false) }, [engineering, selectedNode?.id])
  const canMutateGraph = editable
  const canEditSelectedNode = Boolean(editable && selectedNode && !selectedNode.locked && selectedNode.scope !== 'root')
  const visibleEngineeringRelations = useMemo(() => engineeringDataRelations.filter((relation) => (
    relation.kind === 'dependency' ? edgeVisibility.dependency : edgeVisibility.data
  )), [edgeVisibility.data, edgeVisibility.dependency, engineeringDataRelations])
  const engineeringNodeModels = useMemo(
    () => engineering ? buildEngineeringNodeModels(graph, files, nodeRunStates, visibleEngineeringRelations) : new Map(),
    [engineering, files, graph, nodeRunStates, visibleEngineeringRelations],
  )
  const emptyNodeEditors = useMemo(() => [], [])
  return (
    <div className={`cf-design-studio ${engineering ? 'engineering-mode' : 'outcome-mode'} ${engineeringInspectorOpen && engineering ? 'inspector-open' : ''} ${stewardOpen ? 'ai-steward-open' : ''} ${nodeEditors.length ? 'drawer-open' : ''}`}>
      <div className="cf-design-main">
        <div className="cf-design-modebar">
          <div className={`cf-design-canvas-status ${canvasTool === 'connect' ? 'active' : ''}`} aria-live="polite"><i />{canvasTool === 'connect' ? '连线模式' : '选择模式'}</div>
          <div className="cf-design-view-switch" role="tablist" aria-label="设计视图">
            <button type="button" className={engineering ? 'active' : ''} onClick={() => setDisplayMode('engineering')} role="tab" aria-selected={engineering}><Braces aria-hidden="true" />工程视图</button>
            <button type="button" className={!engineering ? 'active' : ''} onClick={() => setDisplayMode('outcome')} role="tab" aria-selected={!engineering}><span className="cf-view-dot" />引导视图</button>
          </div>
          {engineering && <div className="cf-engineering-legend" aria-label="工程关系筛选">
            {([
              ['control', '主流程'],
              ['data', '数据流'],
              ['dependency', '资源依赖'],
              ['branch', '条件分支'],
              ['failure', '失败处理'],
            ] as Array<[keyof EngineeringEdgeVisibility, string]>).map(([kind, label]) => (
              <label key={kind}><input type="checkbox" checked={edgeVisibility[kind]} onChange={() => setEdgeVisibility((current) => ({ ...current, [kind]: !current[kind] }))} /><i className={kind} />{label}</label>
            ))}
            <b>{graph.nodes.length} 节点 · {graph.edges.length} 控制 · {engineeringRelationCounts.data} 数据 · {engineeringRelationCounts.dependency} 依赖</b>
          </div>}
          <div className="cf-design-panel-toggles">
            {engineering && <button type="button" className={engineeringInspectorOpen ? 'active' : ''} onClick={() => setEngineeringInspectorOpen((current) => !current)} title={engineeringInspectorOpen ? '收起节点详情' : '展开节点详情'} aria-pressed={engineeringInspectorOpen}><PanelRight aria-hidden="true" /><span>详情</span></button>}
            <button type="button" className={stewardOpen ? 'active' : ''} onClick={() => setStewardOpen((current) => !current)} title={stewardOpen ? '收起 AI 管家' : '展开 AI 管家'} aria-pressed={stewardOpen}><Bot aria-hidden="true" /><span>AI 管家</span></button>
          </div>
        </div>
        <Box className="cf-flow-panel cf-flow-overview cf-flow-overview-studio" overflow="hidden">
        <FlowGraphView
          graph={graph}
          files={files}
          displayMode={displayMode}
          engineeringEdgeVisibility={edgeVisibility}
          engineeringDataRelations={engineeringDataRelations}
          engineeringNodeModels={engineeringNodeModels}
          selectedNode={selectedNode}
          focusNodeId={focusNodeId}
          onSelectNode={onSelectNode}
          onNodeEditorPositionChange={onNodeEditorPositionChange}
          onLayoutSave={editable ? onLayoutSave : undefined}
          autoLayoutOnMount={editable && autoLayoutOnMount}
          onAutoLayoutComplete={onAutoLayoutComplete}
          onEdgesSave={canMutateGraph ? onEdgesSave : undefined}
          onAnnotationsSave={editable ? onAnnotationsSave : undefined}
          onCreateNode={canMutateGraph ? onCreateNode : undefined}
          onDeleteNode={canMutateGraph ? onDeleteNode : undefined}
          modelPanel={editable ? modelPanel : undefined}
          toolPanel={editable ? toolPanel : undefined}
          packagePanel={editable ? packagePanel : undefined}
          cartridgePanel={editable ? cartridgePanel : undefined}
          nodeEditors={engineering ? emptyNodeEditors : nodeEditors}
          activeNodeEditorId={selectedNode?.id || null}
          onCloseNodeEditor={onCloseUnpinnedNodeEditors}
          onCanvasToolChange={setCanvasTool}
          requestedCanvasTool={canvasTool}
          onStewardSelectionChange={updateStewardSelection}
          runStatus={runStatus}
          nodeRunStates={nodeRunStates}
          runEvents={runEvents}
          runCompletionVisible={runCompletionVisible}
          runCompletion={runCompletion}
          onDismissRunCompletion={onDismissRunCompletion}
          onOpenRunLog={onOpenRunLog}
          onOpenPendingInteraction={onOpenPendingInteraction}
        />
        </Box>
      </div>
      {engineering && engineeringInspectorOpen && <EngineeringInspector
        node={selectedNode}
        graph={graph}
        view={selectedNode ? engineeringNodeModels.get(selectedNode.id)?.view || null : null}
        unlocked={engineeringUnlocked}
        canEdit={canEditSelectedNode}
        onToggleLock={() => {
          setEngineeringUnlocked((current) => {
            if (current) onCloseUnpinnedNodeEditors()
            return !current
          })
        }}
        draft={selectedNode ? nodeDrafts[selectedNode.id] || makeNodeDraft(selectedNode) : undefined}
        dirty={Boolean(selectedNode && nodeDrafts[selectedNode.id] && JSON.stringify(nodeDrafts[selectedNode.id]) !== JSON.stringify(makeNodeDraft(selectedNode)))}
        saving={Boolean(selectedNode && savingNodeIds.has(selectedNode.id))}
        onDraftChange={(patch) => selectedNode && updateNodeDraft(selectedNode, patch)}
        onResetDraft={() => selectedNode && resetNodeDraft(selectedNode.id)}
        onSaveDraft={() => selectedNode ? void persistNodeDraft(selectedNode) : undefined}
        stewardTool={stewardTool}
        onStewardFieldSelect={(fieldPath) => setStewardSelection({ node_ids: [selectedNode!.id], edge_ids: [], field_paths: [fieldPath] })}
      />}
      {stewardOpen && <AIFlowStewardPanel
        flowId={flowId}
        context={stewardContext}
        tool={stewardTool}
        onToolChange={(tool) => setCanvasTool(tool === 'pointer' ? 'steward-pointer' : tool === 'lasso' ? 'steward-lasso' : 'select')}
        onClearSelection={() => setStewardSelection({ node_ids: [], edge_ids: [], field_paths: [] })}
        onClose={() => setStewardOpen(false)}
      />}
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

export function RunHistoryPanel({ runs, selectedRunId, busy = false, onSelect, onOpenLog, onOpenArtifacts, onRefresh, onClose }: {
  runs: RunResult[]
  selectedRunId?: string
  busy?: boolean
  onSelect: (runId: string) => void
  onOpenLog: (run: RunResult) => void
  onOpenArtifacts: (run: RunResult) => void
  onRefresh: () => void | Promise<void>
  onClose: () => void
}) {
  const [expandedRunId, setExpandedRunId] = useState(selectedRunId || runs[0]?.run_id || '')
  const [refreshing, setRefreshing] = useState(false)
  const refresh = async () => {
    if (refreshing) return
    setRefreshing(true)
    try { await onRefresh() } finally { setRefreshing(false) }
  }
  return (
    <aside className="cf-canvas-history-panel">
      <header>
        <div><span>RUN HISTORY</span><strong>运行历史</strong><small>{runs.length} 条真实运行记录</small></div>
        <button type="button" onClick={onClose} title="关闭运行历史"><X aria-hidden="true" /></button>
      </header>
      <div className="cf-canvas-history-tools">
        <p>选择记录后，画布会同步显示该次运行的节点状态。</p>
        <button type="button" onClick={() => void refresh()} disabled={busy || refreshing}><RefreshCw className={refreshing ? 'spinning' : ''} aria-hidden="true" /><span>{refreshing ? '刷新中' : '刷新'}</span></button>
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
                  <button type="button" disabled={run.status !== 'completed' && !artifactCount} title={artifactCount ? `打开 ${artifactCount} 个运行产物` : run.status === 'completed' ? '打开本次运行的页面结果' : '本次运行没有可打开的产物'} onClick={() => onOpenArtifacts(run)}><FileOutput aria-hidden="true" />打开产物</button>
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
  const primaryError = errors[0] || (failedEvents[0]?.data as any)?.error_envelope
  const lines = [
    `Run: ${run.run_id}`,
    `Status: ${run.status}`,
    `Node: ${primaryError?.node_id || run.current_state || 'unknown'}`,
  ]
  const seenErrorIds = new Set<string>()
  errors.forEach((error) => {
    const identity = String(error.error_id || `${error.node_id || ''}:${error.code || ''}:${error.message || ''}`)
    if (seenErrorIds.has(identity)) return
    seenErrorIds.add(identity)
    const detail = error.cause_chain?.[0]?.message || error.message || '运行失败'
    lines.push(`[${error.code || 'RUNTIME_ERROR'}] ${error.node_id ? `${error.node_id}: ` : ''}${detail}`)
  })
  failedEvents.forEach((event) => {
    const data = (event.data || {}) as any
    const envelope = data.error_envelope || {}
    const identity = String(envelope.error_id || '')
    if (identity && seenErrorIds.has(identity)) return
    if (identity) seenErrorIds.add(identity)
    const message = envelope.cause_chain?.[0]?.message || envelope.message || data.error || data.reason || event.message
    if (message) lines.push(`${envelope.node_id || event.state || 'runtime'}: ${message}`)
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
