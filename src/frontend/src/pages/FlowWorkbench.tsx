import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from 'react'
import { Box, Button, Spinner, Text } from '../ui.tsx'
import {
  cloneCartridgeToDev,
  answerPendingInteraction,
  controlCartridgeRun,
  createFlowNode,
  deleteFlowNode,
  fetchLabFlow,
  fetchBaseImplementation,
  fetchLabFlowFiles,
  fetchLabFlowRuns,
  fetchMcpTools,
  fetchCartridgeRun,
  fetchCartridgeRunEvents,
  openCartridgeRunArtifactsDirectory,
  saveFlowEdges,
  saveFlowAnnotations,
  saveFlowLayout,
  runFlow,
  updateFlowNode,
  type FlowEvent,
  type FlowAnnotation,
  type FlowFiles,
  type FlowLabDetail,
  type ProtocolReleaseCatalog,
  type FlowNode,
  type McpTool,
  type RunResult,
  type TestProbeRange,
} from '../api.ts'
import { showToast } from '../toast.tsx'
import { DesignView, RunHistoryPanel, RunLogDialog, WorkbenchHeader } from './flow-workbench/views.tsx'
import { CATEGORY_BY_ID, getPreset } from './flow-workbench/nodeModel.ts'
import type { CreateNodeOptions, GraphResult, NodeCategoryId } from './flow-workbench/types.ts'
import { buildPresetConfig, buildProtocolPatch, buildToolSpecs, firstText } from './flow-workbench/nodeBuilder.ts'
import { ModelManagementPanel, PackagingPanel, ToolManagementPanel } from './flow-workbench/ResourceManagementPanels.tsx'
import CartridgeWorkspaceControl from './flow-workbench/CartridgeWorkspaceControl.tsx'
import { CartridgeDefinitionPanel } from './flow-workbench/CartridgeDefinitionPanel.tsx'
import { RunInputDialog } from './flow-workbench/RunInputDialog.tsx'
import { PendingInteractionForm } from './flow-workbench/TestBenchView.tsx'
import { DlcSandboxFrame } from '../components/DlcSandboxFrame.tsx'
import { buildNodeRunStates, extractUiHtml } from './flow-workbench/runState.ts'
import { passiveHtmlDocument } from './flow-workbench/passiveHtml.ts'
import { NODE_DETAIL_SECTION_BY_ID, nodeDetailId, normalizeNodeDetailSection, type NodeDetailSection, type OpenNodeDetail } from './flow-workbench/nodeDetails.ts'
import { clearNewFlowAutoLayout, shouldAutoLayoutNewFlow } from './flow-workbench/newFlowSetup.ts'
import './flow-workbench/TestBench.css'

const sleep = (ms: number) => new Promise((resolve) => window.setTimeout(resolve, ms))
const pinnedNodeDetailsStorageKey = (flowId: string) => `cartridgeflow.pinned-node-details.v1:${flowId}`
const engineeringResourceLayoutStorageKey = (flowId: string) => `cartridgeflow.engineering-resource-layout.v1:${flowId}`
const RUN_COMPLETION_NOTICE_MS = 8000

type OptimisticRunTransition = {
  runId: string
  from: string
  to: string
}

function protocolLabel(runtimeContract?: any, rootProtocol?: any) {
  const protocol = String(runtimeContract?.protocol || rootProtocol?.id || 'CF-FARP').trim()
  const version = String(runtimeContract?.protocol_version || rootProtocol?.version || '').trim()
  return version ? `${protocol}@${version}` : `${protocol}@unknown`
}

function resolveInteractionTransition(pendingInteraction: any, graph: FlowLabDetail['graph'], actionId: string): Omit<OptimisticRunTransition, 'runId'> | null {
  const from = String(pendingInteraction?.node_id || '').trim()
  if (!from) return null
  const configuredRoute = pendingInteraction?.resume?.action_routes?.[actionId]
  const configuredTarget = typeof configuredRoute === 'string'
    ? configuredRoute
    : configuredRoute?.target_node || configuredRoute?.node_id || configuredRoute?.target
  const outgoing = graph.edges.filter((edge) => edge.from === from)
  const to = String(configuredTarget || (outgoing.length === 1 ? outgoing[0].to : '')).trim()
  return to ? { from, to } : null
}

function findRunResultHtml(runEvents: FlowEvent[]) {
  for (let index = runEvents.length - 1; index >= 0; index -= 1) {
    const event = runEvents[index]
    const action = (event.data as any)?.action
    if (!['show_ui', 'show_result', 'render_ui'].includes(action)) continue
    const html = extractUiHtml(event.data)
    if (html) return html
  }
  return ''
}

async function openRunArtifactsDirectory(run: RunResult) {
  try {
    const result = await openCartridgeRunArtifactsDirectory(run.run_id)
    showToast({ title: '已打开产物文件夹', description: result.path, type: 'success' })
  } catch (error: any) {
    showToast({ title: '打开产物文件夹失败', description: error?.message || String(error), type: 'error' })
  }
}

export default function FlowWorkbench({ flowId, onSwitchFlow }: {
  flowId: string
  onSwitchFlow: (flowId: string) => void
}) {
  const [detail, setDetail] = useState<FlowLabDetail | null>(null)
  const [files, setFiles] = useState<FlowFiles>({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [selectedNode, setSelectedNode] = useState<FlowNode | null>(null)
  const [focusNodeId, setFocusNodeId] = useState<string | null>(null)
  const [openNodeEditors, setOpenNodeEditors] = useState<OpenNodeDetail[]>([])
  const [restoredNodeDetailsFlowId, setRestoredNodeDetailsFlowId] = useState('')
  const [engineeringResourceLayout, setEngineeringResourceLayout] = useState<Record<string, { x: number; y: number }>>({})
  const engineeringResourceLayoutRef = useRef<Record<string, { x: number; y: number }>>({})
  const [runs, setRuns] = useState<RunResult[]>([])
  const [events, setEvents] = useState<FlowEvent[]>([])
  const [mcpTools, setMcpTools] = useState<McpTool[]>([])
  const [flowResourceTools, setFlowResourceTools] = useState<McpTool[]>([])
  const [cloningToDev, setCloningToDev] = useState(false)
  const [runInputOpen, setRunInputOpen] = useState(false)
  const [runControlBusy, setRunControlBusy] = useState(false)
  const [interactionSubmitting, setInteractionSubmitting] = useState(false)
  const [optimisticRunTransition, setOptimisticRunTransition] = useState<OptimisticRunTransition | null>(null)
  const [dismissedInteractionId, setDismissedInteractionId] = useState('')
  const [interactionPresentationSize, setInteractionPresentationSize] = useState<{ width: number; height: number } | null>(null)
  const pollGenerationRef = useRef(0)
  const [historyOpen, setHistoryOpen] = useState(false)
  const [selectedHistoryRunId, setSelectedHistoryRunId] = useState('')
  const [runLog, setRunLog] = useState<{ run: RunResult; events: FlowEvent[] } | null>(null)
  const [runCompletionNotice, setRunCompletionNotice] = useState<{ runId: string; shownAt: number } | null>(null)
  const [resultModal, setResultModal] = useState<{ runId: string; html: string } | null>(null)
  const [protocolCatalog, setProtocolCatalog] = useState<ProtocolReleaseCatalog | null>(null)
  const latestRun = runs[0]
  const pendingInteraction = latestRun?.status === 'paused_waiting_user' ? latestRun.pending_interaction : null
  const pendingInteractionId = String(pendingInteraction?.interaction_id || '')
  const visiblePendingInteraction = pendingInteraction && pendingInteractionId !== dismissedInteractionId ? pendingInteraction : null
  const latestResultHtml = useMemo(() => findRunResultHtml(events), [events])
  const activeRuntimeRun = latestRun && ['created', 'running', 'retrying', 'recovering', 'rolling_back', 'paused', 'paused_waiting_user'].includes(latestRun.status)
    ? latestRun
    : undefined
  const selectedRunId = selectedHistoryRunId || runs[0]?.run_id || ''
  // Follow an active run continuously, including runs started outside this page
  // (e.g. the API or another tab). Without this the canvas freezes on the last
  // polled state and looks stuck even though the run is progressing.
  useEffect(() => {
    const runId = activeRuntimeRun?.run_id
    if (!runId) return
    let cancelled = false
    const tick = async () => {
      if (cancelled) return
      try {
        const [runData, eventData] = await Promise.all([
          fetchCartridgeRun(runId),
          fetchCartridgeRunEvents(runId),
        ])
        if (cancelled) return
        setRuns((current) => [runData, ...current.filter((item) => item.run_id !== runId)])
        setEvents(eventData.items || [])
        if (['completed', 'failed', 'cancelled', 'interrupted'].includes(runData.status)) {
          setRunCompletionNotice((current) => current?.runId === runId
            ? current
            : { runId, shownAt: Date.now() })
        }
      } catch {
        // transient network error: keep polling
      }
    }
    void tick()
    const timer = window.setInterval(tick, 2500)
    return () => { cancelled = true; window.clearInterval(timer) }
  }, [activeRuntimeRun?.run_id])
  const visualRuntimeRun = activeRuntimeRun
    || (runCompletionNotice ? runs.find((run) => run.run_id === runCompletionNotice.runId) : undefined)
  const designRunEvents = useMemo(() => {
    if (!optimisticRunTransition || optimisticRunTransition.runId !== visualRuntimeRun?.run_id) return events
    return [...events, {
      type: 'flow_edge_traversed',
      state: optimisticRunTransition.to,
      message: `Flow edge traversing: ${optimisticRunTransition.from} -> ${optimisticRunTransition.to}`,
      data: { from: optimisticRunTransition.from, to: optimisticRunTransition.to, reason: 'interaction_resume_pending' },
    } satisfies FlowEvent]
  }, [events, optimisticRunTransition, visualRuntimeRun?.run_id])
  const designNodeRunStates = useMemo(() => {
    if (!detail || !visualRuntimeRun) return undefined
    const states = buildNodeRunStates(detail.graph, designRunEvents)
    if (optimisticRunTransition?.runId === visualRuntimeRun.run_id) {
      const sourceState = states.get(optimisticRunTransition.from)
      const targetState = states.get(optimisticRunTransition.to)
      if (sourceState && sourceState.status !== 'failed') sourceState.status = 'completed'
      if (targetState) {
        targetState.status = 'running'
        targetState.pendingInteraction = undefined
        targetState.errorMsg = undefined
      }
    }
    return states
  }, [designRunEvents, detail, optimisticRunTransition, visualRuntimeRun])
  const availableMcpTools = useMemo(() => {
    const merged = new Map<string, McpTool>()
    for (const tool of flowResourceTools) merged.set(tool.id, tool)
    const selectedEntries = new Set(flowResourceTools.map((tool) => `${tool.server}/${tool.tool}`))
    for (const tool of mcpTools) {
      if (merged.has(tool.id) || selectedEntries.has(`${tool.server}/${tool.tool}`)) merged.set(tool.id, tool)
    }
    return [...merged.values()]
  }, [flowResourceTools, mcpTools])
  const protocolInfo = useMemo(() => {
    const currentProtocolLabel = protocolLabel(detail?.cartridge.runtime_contract, detail?.cartridge.root_flow?.protocol)
    const target = protocolCatalog?.default_for_new_flows
    const targetProtocolLabel = target?.label || '协议发布清单未读取'
    const baseContract = protocolCatalog?.base_contract
    return {
      baseContractLabel: baseContract ? `${baseContract.id}@${baseContract.version}` : 'Base Contract 未读取',
      targetProtocolLabel,
      currentProtocolLabel,
      currentProtocolStatus: currentProtocolLabel === targetProtocolLabel ? '当前发布协议' : '兼容运行协议',
    }
  }, [detail, protocolCatalog])
  const openRunLog = useCallback(async (run: RunResult) => {
    try {
      const [selectedRun, selectedEvents] = await Promise.all([
        fetchCartridgeRun(run.run_id),
        fetchCartridgeRunEvents(run.run_id),
      ])
      setRunLog({ run: selectedRun, events: selectedEvents.items || [] })
    } catch (e: any) {
      showToast({ title: '读取运行日志失败', description: e.message, type: 'error' })
    }
  }, [])

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    setRunCompletionNotice(null)
    try {
      const [data, baseResponse] = await Promise.all([fetchLabFlow(flowId), fetchBaseImplementation()])
      setProtocolCatalog(baseResponse.protocol_catalog || null)
      setDetail(data)
      setRuns(data.runs || [])
      setSelectedHistoryRunId(data.runs?.[0]?.run_id || '')
      setEvents(data.latest_run_events || [])
      setSelectedNode((current) => {
        const stillExists = current ? data.graph.nodes.find((node) => node.id === current.id) : null
        return stillExists || data.graph.nodes.find((node) => !node.locked) || data.graph.nodes[0] || null
      })
      if (data.cartridge.editable) {
        try {
          const fileData = await fetchLabFlowFiles(flowId)
          setFiles(fileData.files || {})
          const toolData = await fetchMcpTools(flowId)
          setMcpTools(toolData.mcp_tools || [])
          if (toolData.files) setFiles(toolData.files || fileData.files || {})
        } catch {
          setFiles({})
          setMcpTools([])
        }
      }
    } catch (e: any) {
      setError(e.message || '加载失败')
    } finally {
      setLoading(false)
    }
  }, [flowId])

  useEffect(() => { load() }, [load])
  useEffect(() => {
    if (!runCompletionNotice) return
    const noticeRun = runs.find((run) => run.run_id === runCompletionNotice.runId)
    if (noticeRun?.status === 'paused' || noticeRun?.status === 'paused_waiting_user') return
    const remaining = Math.max(0, RUN_COMPLETION_NOTICE_MS - (Date.now() - runCompletionNotice.shownAt))
    const timer = window.setTimeout(() => {
      setRunCompletionNotice((current) => current?.runId === runCompletionNotice.runId ? null : current)
    }, remaining)
    return () => window.clearTimeout(timer)
  }, [runCompletionNotice, runs])
  useEffect(() => {
    if (latestRun?.status === 'completed' && latestResultHtml) setResultModal({ runId: latestRun.run_id, html: latestResultHtml })
  }, [latestResultHtml, latestRun?.run_id, latestRun?.status])
  useEffect(() => {
    setDismissedInteractionId('')
    setInteractionPresentationSize(null)
  }, [pendingInteractionId])
  useEffect(() => {
    setRestoredNodeDetailsFlowId('')
    try {
      const stored = JSON.parse(localStorage.getItem(pinnedNodeDetailsStorageKey(flowId)) || '[]')
      const restored = Array.isArray(stored) ? stored.reduce<OpenNodeDetail[]>((result, item) => {
        const nodeId = typeof item?.nodeId === 'string' ? item.nodeId : ''
        const section = normalizeNodeDetailSection(item?.section)
        if (!nodeId || !section || !NODE_DETAIL_SECTION_BY_ID.has(section) || item?.pinned !== true) return result
        if (result.some((entry) => entry.nodeId === nodeId && entry.section === section)) return result
        const x = Number(item?.position?.x)
        const y = Number(item?.position?.y)
        result.push({
          nodeId,
          section,
          pinned: true,
          ...(Number.isFinite(x) && Number.isFinite(y) ? { position: { x, y } } : {}),
        })
        return result
      }, []) : []
      setOpenNodeEditors(restored)
    } catch {
      setOpenNodeEditors([])
    } finally {
      setRestoredNodeDetailsFlowId(flowId)
    }
  }, [flowId])

  useEffect(() => {
    let restored: Record<string, { x: number; y: number }> = {}
    try {
      const stored = JSON.parse(localStorage.getItem(engineeringResourceLayoutStorageKey(flowId)) || '{}')
      if (stored && typeof stored === 'object' && !Array.isArray(stored)) {
        restored = Object.entries(stored).reduce<Record<string, { x: number; y: number }>>((result, [nodeId, position]) => {
          const x = Number((position as any)?.x)
          const y = Number((position as any)?.y)
          if (nodeId && Number.isFinite(x) && Number.isFinite(y)) result[nodeId] = { x, y }
          return result
        }, {})
      }
    } catch {
      // Invalid local metadata must not affect the Flow or its runtime graph.
    }
    engineeringResourceLayoutRef.current = restored
    setEngineeringResourceLayout(restored)
  }, [flowId])

  const saveEngineeringResourceLayout = useCallback((layout: Record<string, { x: number; y: number }>) => {
    const next = { ...engineeringResourceLayoutRef.current, ...layout }
    const unchanged = Object.keys(next).length === Object.keys(engineeringResourceLayoutRef.current).length
      && Object.entries(next).every(([nodeId, position]) => engineeringResourceLayoutRef.current[nodeId]?.x === position.x && engineeringResourceLayoutRef.current[nodeId]?.y === position.y)
    if (unchanged) return
    engineeringResourceLayoutRef.current = next
    setEngineeringResourceLayout(next)
    try {
      window.localStorage.setItem(engineeringResourceLayoutStorageKey(flowId), JSON.stringify(next))
    } catch {
      // Local storage can be unavailable; keep the current-session engineering layout.
    }
  }, [flowId])

  useEffect(() => {
    if (restoredNodeDetailsFlowId !== flowId) return
    const pinned = openNodeEditors.filter((editor) => editor.pinned)
    const key = pinnedNodeDetailsStorageKey(flowId)
    if (pinned.length) window.localStorage.setItem(key, JSON.stringify(pinned))
    else window.localStorage.removeItem(key)
  }, [flowId, openNodeEditors, restoredNodeDetailsFlowId])

  useEffect(() => {
    if (!detail) return
    const nodeIds = new Set(detail.graph.nodes.map((node) => node.id))
    setOpenNodeEditors((current) => current.filter((editor) => nodeIds.has(editor.nodeId)))
  }, [detail])

  const editable = Boolean(detail?.cartridge.editable)

  useEffect(() => () => {
    pollGenerationRef.current += 1
  }, [flowId])

  const pollRunUntilStable = useCallback(async (runId: string, maxAttempts = 900) => {
    const generation = ++pollGenerationRef.current
    let latest: RunResult | null = null
    for (let attempt = 0; attempt < maxAttempts; attempt++) {
      await sleep(800)
      if (generation !== pollGenerationRef.current) return latest
      let runData: RunResult
      let eventData: { items: FlowEvent[] }
      try {
        ;[runData, eventData] = await Promise.all([
          fetchCartridgeRun(runId),
          fetchCartridgeRunEvents(runId),
        ])
      } catch (pollError) {
        if (generation !== pollGenerationRef.current) return latest
        if (attempt < 10) continue
        throw pollError
      }
      if (generation !== pollGenerationRef.current) return latest
      latest = runData
      setRuns((current) => [runData, ...current.filter((item) => item.run_id !== runData.run_id)])
      setEvents(eventData.items || [])
      if (['completed', 'failed', 'cancelled', 'interrupted', 'paused', 'paused_waiting_user'].includes(runData.status)) {
        setRunCompletionNotice((current) => current?.runId === runData.run_id
          ? current
          : { runId: runData.run_id, shownAt: Date.now() })
      }
      if (['completed', 'failed', 'cancelled', 'interrupted', 'paused', 'paused_waiting_user'].includes(runData.status)) break
    }
    if (latest && ['created', 'running', 'retrying', 'recovering', 'rolling_back'].includes(latest.status)) {
      throw new Error(`运行 ${runId} 在等待时限内没有结束，请在运行历史中继续查看状态`)
    }
    return latest
  }, [])

  const startFlowRun = useCallback(async (inputs: Record<string, string>, probeRange?: TestProbeRange) => {
    setRunInputOpen(false)
    setOptimisticRunTransition(null)
    setRunCompletionNotice(null)
    setResultModal(null)
    setEvents([])
    setRunControlBusy(true)
    try {
      const result = await runFlow(flowId, inputs, probeRange)
      setRuns((current) => [result.run, ...current.filter((item) => item.run_id !== result.run.run_id)])
      setSelectedHistoryRunId(result.run.run_id)
      setEvents(result.events || [])
      setRunControlBusy(false)
      const latest = await pollRunUntilStable(result.run.run_id) || result.run
      if (['completed', 'failed', 'cancelled', 'interrupted', 'paused', 'paused_waiting_user'].includes(latest.status)) {
        setRunCompletionNotice((current) => current?.runId === latest.run_id
          ? current
          : { runId: latest.run_id, shownAt: Date.now() })
      }
    } catch (e: any) {
      showToast({ title: '运行失败', description: e.message, type: 'error' })
    } finally {
      setRunControlBusy(false)
    }
  }, [flowId, pollRunUntilStable])

  const controlActiveRun = useCallback(async (action: 'pause' | 'resume' | 'cancel') => {
    const activeRun = activeRuntimeRun
    if (!activeRun?.run_id || runControlBusy) return
    setRunControlBusy(true)
    try {
      const updated = await controlCartridgeRun(activeRun.run_id, action, {
        feedback: { source: 'workbench_header' },
      })
      const eventData = await fetchCartridgeRunEvents(activeRun.run_id).catch(() => ({ items: events }))
      setRuns((current) => [updated, ...current.filter((item) => item.run_id !== updated.run_id)])
      setEvents(eventData.items || [])
      if (['completed', 'failed', 'cancelled', 'interrupted', 'paused', 'paused_waiting_user'].includes(updated.status)) {
        setRunCompletionNotice({ runId: updated.run_id, shownAt: Date.now() })
      }
    } catch (e: any) {
      showToast({ title: '运行控制失败', description: e.message, type: 'error' })
    } finally {
      setRunControlBusy(false)
    }
  }, [activeRuntimeRun, events, runControlBusy])

  const submitPendingInteraction = useCallback(async (values: Record<string, any>, options?: Record<string, any>) => {
    if (!latestRun?.run_id || !pendingInteraction || interactionSubmitting) return
    const runId = latestRun.run_id
    const firstAction = pendingInteraction.allowed_actions?.[0]
    const actionId = String(options?.action_id || (typeof firstAction === 'string' ? firstAction : firstAction?.id || ''))
    const transition = detail ? resolveInteractionTransition(pendingInteraction, detail.graph, actionId) : null
    setInteractionSubmitting(true)
    setRunCompletionNotice(null)
    setOptimisticRunTransition(transition ? { runId, ...transition } : null)
    setRuns((current) => current.map((run) => run.run_id === runId ? { ...run, status: 'running' } : run))
    try {
      const result = await answerPendingInteraction(runId, values, options)
      setRuns((current) => [result.run, ...current.filter((item) => item.run_id !== result.run.run_id)])
      setEvents(result.events || [])
      setOptimisticRunTransition(null)
      setRunCompletionNotice(null)
      if (['created', 'running', 'retrying', 'recovering', 'rolling_back'].includes(result.run.status)) {
        await pollRunUntilStable(result.run.run_id)
      } else if (['completed', 'failed', 'cancelled', 'interrupted', 'paused', 'paused_waiting_user'].includes(result.run.status)) {
        setRunCompletionNotice({ runId: result.run.run_id, shownAt: Date.now() })
      }
    } catch (e: any) {
      setOptimisticRunTransition(null)
      showToast({ title: '提交交互失败', description: e.message, type: 'error' })
      try {
        const [restoredRun, restoredEvents] = await Promise.all([fetchCartridgeRun(runId), fetchCartridgeRunEvents(runId)])
        setRuns((current) => [restoredRun, ...current.filter((item) => item.run_id !== restoredRun.run_id)])
        setEvents(restoredEvents.items || [])
      } catch {
        // Keep the original submission error visible.
      }
    } finally {
      setInteractionSubmitting(false)
    }
  }, [detail, interactionSubmitting, latestRun?.run_id, pendingInteraction, pollRunUntilStable])

  const cloneReadonlyToDev = useCallback(async () => {
    if (!detail?.cartridge || detail.cartridge.editable) return
    const base = detail.cartridge.id.replace(/^dev\./, '').replace(/[^a-zA-Z0-9._-]+/g, '.')
    const defaultId = `dev.${base}.copy`
    const newId = window.prompt('请输入新的 dev flow ID', defaultId)
    if (!newId) return
    const defaultName = `${detail.cartridge.name || detail.cartridge.id} Copy`
    const name = window.prompt('请输入新卡带名称', defaultName)
    if (!name) return
    setCloningToDev(true)
    try {
      const result = await cloneCartridgeToDev(detail.cartridge.id, newId, name, detail.cartridge.description || '')
      showToast({ title: '已复制为可编辑版本', description: result.id, type: 'success' })
      onSwitchFlow(result.id)
    } catch (e: any) {
      showToast({ title: '复制失败', description: e.message, type: 'error' })
    } finally {
      setCloningToDev(false)
    }
  }, [detail?.cartridge, onSwitchFlow])

  const selectNode = useCallback((node: FlowNode) => {
    setSelectedNode(node)
    setFocusNodeId(node.id)
    setOpenNodeEditors((current) => current.filter((editor) => editor.pinned || editor.nodeId === node.id))
  }, [])

  const openGuidedNodeEditor = useCallback((node: FlowNode, section: NodeDetailSection) => {
    setSelectedNode(node)
    setOpenNodeEditors((current) => {
      const retained = current.filter((editor) => editor.pinned)
      const editorId = nodeDetailId(node.id, section)
      if (retained.some((editor) => nodeDetailId(editor.nodeId, editor.section) === editorId)) return retained
      return [...retained, { nodeId: node.id, section, pinned: false }]
    })
  }, [])

  const closeNodeEditor = useCallback((editorId: string) => {
    setOpenNodeEditors((current) => current.filter((editor) => nodeDetailId(editor.nodeId, editor.section) !== editorId))
  }, [])

  const toggleNodeEditorPin = useCallback((editorId: string) => {
    setOpenNodeEditors((current) => current.map((editor) => (
      nodeDetailId(editor.nodeId, editor.section) === editorId ? { ...editor, pinned: !editor.pinned } : editor
    )))
  }, [])

  const updateNodeEditorPosition = useCallback((editorId: string, position: { x: number; y: number }) => {
    setOpenNodeEditors((current) => current.map((editor) => (
      nodeDetailId(editor.nodeId, editor.section) === editorId ? { ...editor, position } : editor
    )))
  }, [])

  const closeUnpinnedNodeEditors = useCallback(() => {
    setOpenNodeEditors((current) => current.filter((editor) => editor.pinned))
  }, [])

  const updateGraphResult = useCallback((result: GraphResult) => {
    setFiles(result.files)
    setDetail((prev) => prev ? { ...prev, graph: result.graph } : prev)
  }, [])

  const createCategoryNode = useCallback(async (sourceNode: FlowNode | null, categoryId: NodeCategoryId, insertMode: 'insert' | 'branch', options?: CreateNodeOptions) => {
    const category = CATEGORY_BY_ID.get(categoryId)!
    const nodeId = `${categoryId}_${Date.now().toString(36)}`
    try {
      const created = await createFlowNode(flowId, {
        files,
        template_id: category.templateId,
        node_id: nodeId,
        title: category.defaultTitle,
        after_node_id: sourceNode?.id,
        insert_mode: insertMode,
      })
      const createdNode = created.graph.nodes.find((node) => node.id === created.node_id)
      const presetId = options?.presetId || (category.id === 'custom' ? 'blank' : getPreset(category.id).id)
      const presetConfig = buildPresetConfig({ preset_config: options?.presetConfig || {} }, category.id, presetId, nodeId, 0)
      const outputText = firstText(presetConfig.output_name, presetConfig.path, presetConfig.key)
      const toolSpecs = buildToolSpecs(category.id, presetId, presetConfig, '', outputText, undefined, availableMcpTools, {})
      const protocolPatch = buildProtocolPatch(category.id, presetId, presetConfig, toolSpecs, availableMcpTools, {}, outputText)
      const updated = await updateFlowNode(flowId, created.node_id, {
        files: created.files,
        title: category.defaultTitle,
        ...protocolPatch,
        next: createdNode?.next || '',
        agent: null,
        model_role: null,
        tools: toolSpecs,
        params: {
          ...(createdNode?.params || {}),
          node_category: category.id,
          preset: presetId,
          preset_config: presetConfig,
          description: category.description,
          output: outputText,
        },
      })
      let finalResult: GraphResult = updated
      if (options?.position) {
        const nextLayout = Object.fromEntries(updated.graph.nodes.map((item) => {
          const raw = (item as any).layout || item.params?.layout || item.data?.params?.layout || {}
          return [item.id, {
            x: Math.round(Number(raw.x ?? item.x ?? 0) / 10) * 10,
            y: Math.round(Number(raw.y ?? item.y ?? 0) / 10) * 10,
          }]
        }))
        nextLayout[updated.node_id] = {
          x: Math.round(options.position.x / 10) * 10,
          y: Math.round(options.position.y / 10) * 10,
        }
        finalResult = await saveFlowLayout(flowId, updated.files, nextLayout)
      }
      updateGraphResult(finalResult)
      const node = finalResult.graph.nodes.find((item) => item.id === updated.node_id)
      if (node) selectNode(node)
      showToast({ title: `${category.shortLabel}节点已新增`, type: 'success' })
      return node
    } catch (e: any) {
      showToast({ title: '新增失败', description: e.message, type: 'error' })
      return undefined
    }
  }, [availableMcpTools, files, flowId, selectNode, updateGraphResult])

  if (loading) return <Box p={6}><Spinner /></Box>
  if (error) {
    return (
      <Box p={6}>
        <Text color="fg.error">{error}</Text>
        <Button className="cf-outline-btn" mt={4} onClick={() => onSwitchFlow('')}>选择其他卡带</Button>
      </Box>
    )
  }
  if (!detail) return null

  return (
    <Box className="cf-page cf-workbench-page">
      <Box className="cf-page-inner cf-workbench-inner">
        <WorkbenchHeader
          detail={detail}
          protocolInfo={protocolInfo}
          cartridgeControls={<CartridgeWorkspaceControl current={detail.cartridge} onSwitchFlow={onSwitchFlow} onUpdated={load} />}
          runStatus={activeRuntimeRun?.status}
          runBusy={runControlBusy}
          historyOpen={historyOpen}
          onHistory={() => {
            setHistoryOpen((current) => !current)
          }}
          onRun={() => {
            if ((detail.cartridge.inputs || []).length) setRunInputOpen(true)
            else void startFlowRun({})
          }}
          onPause={() => {
            if (activeRuntimeRun?.status === 'paused_waiting_user') setDismissedInteractionId('')
            else void controlActiveRun(activeRuntimeRun?.status === 'paused' ? 'resume' : 'pause')
          }}
          onStop={() => void controlActiveRun('cancel')}
          onCloneToDev={cloneReadonlyToDev}
          cloningToDev={cloningToDev}
        />

        {runInputOpen && (
          <RunInputDialog
            inputs={detail.cartridge.inputs || []}
            disabled={runControlBusy}
            onSubmit={(inputs) => void startFlowRun(inputs)}
            onCancel={() => setRunInputOpen(false)}
          />
        )}

        {visiblePendingInteraction && latestRun && (
          <div className="cf-pending-modal-backdrop cf-workbench-interaction-backdrop" onClick={() => setDismissedInteractionId(pendingInteractionId)}>
            <div
              className={`cf-pending-modal cf-workbench-interaction-modal ${visiblePendingInteraction.ui_extension === 'portable_dlc' ? 'cf-pending-modal-dlc' : ''}`}
              role="dialog"
              aria-modal="true"
              aria-label="等待用户交互"
              style={interactionPresentationSize ? {
                '--cf-interaction-content-width': `${interactionPresentationSize.width}px`,
                '--cf-interaction-content-height': `${interactionPresentationSize.height}px`,
              } as CSSProperties : undefined}
              onClick={(event) => event.stopPropagation()}
            >
              <div className="cf-pending-modal-head">
                <strong>{visiblePendingInteraction.question?.prompt || '当前节点需要你的输入'}</strong>
                <span>提交后流程将自动继续</span>
                <button type="button" onClick={() => setDismissedInteractionId(pendingInteractionId)} title="关闭并保持暂停" aria-label="关闭并保持暂停">×</button>
              </div>
              {visiblePendingInteraction.ui_extension === 'portable_dlc' && detail.cartridge.portable_dlc ? (
                <DlcSandboxFrame cartridgeId={detail.cartridge.id} runId={latestRun.run_id} onSubmit={submitPendingInteraction} />
              ) : (
                <PendingInteractionForm pending={visiblePendingInteraction} disabled={interactionSubmitting} onSubmit={submitPendingInteraction} onPresentationSize={setInteractionPresentationSize} />
              )}
            </div>
          </div>
        )}

        {resultModal && (
          <div className="cf-pending-modal-backdrop" onClick={() => setResultModal(null)}>
            <div className="cf-pending-modal cf-run-result-modal" role="dialog" aria-modal="true" aria-label="运行结果" onClick={(event) => event.stopPropagation()}>
              <div className="cf-pending-modal-head">
                <strong>运行结果</strong>
                <button type="button" onClick={() => setResultModal(null)} title="关闭结果" aria-label="关闭结果">×</button>
              </div>
              <iframe className="cf-run-result-frame" title="运行结果页面" sandbox="" srcDoc={passiveHtmlDocument(resultModal.html)} />
            </div>
          </div>
        )}

        <div className="cf-workbench-design-shell">
            <DesignView
            graph={detail.graph}
            protocolInfo={protocolInfo}
            editable={editable}
            files={files}
            flowId={flowId}
            selectedNode={selectedNode}
            focusNodeId={focusNodeId}
            openNodeEditors={openNodeEditors}
            onSelectNode={selectNode}
            onGuideNodeEditor={openGuidedNodeEditor}
            onCloseNodeEditor={closeNodeEditor}
            onToggleNodeEditorPin={toggleNodeEditorPin}
            onNodeEditorPositionChange={updateNodeEditorPosition}
            onCloseUnpinnedNodeEditors={closeUnpinnedNodeEditors}
            autoLayoutOnMount={shouldAutoLayoutNewFlow(flowId)}
            onAutoLayoutComplete={() => clearNewFlowAutoLayout(flowId)}
            onLayoutSave={async (layout) => {
              const result = await saveFlowLayout(flowId, files, layout)
              setFiles(result.files)
              setDetail((prev) => prev ? { ...prev, graph: result.graph } : prev)
            }}
            onEdgesSave={async (edges) => {
              const result = await saveFlowEdges(flowId, files, edges)
              updateGraphResult(result)
            }}
            onAnnotationsSave={async (annotations: FlowAnnotation[]) => {
              const result = await saveFlowAnnotations(flowId, annotations)
              updateGraphResult(result)
            }}
            onCreateNode={createCategoryNode}
            onFilesChange={setFiles}
            engineeringResourceLayout={engineeringResourceLayout}
            onEngineeringResourceLayoutSave={saveEngineeringResourceLayout}
            runStatus={visualRuntimeRun?.status}
            nodeRunStates={designNodeRunStates}
            runEvents={designRunEvents}
            runCompletionVisible={Boolean(runCompletionNotice)}
            runCompletion={runCompletionNotice ? runs.find((run) => run.run_id === runCompletionNotice.runId) : undefined}
            onDismissRunCompletion={() => setRunCompletionNotice(null)}
            onOpenRunLog={openRunLog}
            onOpenRunResult={(run) => void openRunArtifactsDirectory(run)}
            onOpenPendingInteraction={() => setDismissedInteractionId('')}
            modelPanel={<ModelManagementPanel flowId={flowId} cartridge={detail.cartridge} graph={detail.graph} />}
            toolPanel={<ToolManagementPanel flowId={flowId} onFlowToolsChange={setFlowResourceTools} />}
            packagePanel={<PackagingPanel flowId={flowId} />}
            cartridgePanel={<CartridgeDefinitionPanel
              flowId={flowId}
              files={files}
              onFilesChange={setFiles}
              onManifestChange={(manifest) => setDetail((current) => current ? {
                ...current,
                cartridge: {
                  ...current.cartridge,
                  manifest,
                  inputs: manifest.inputs || [],
                  outputs: manifest.outputs || [],
                  mcp_tools: manifest.mcp_tools || [],
                  llm_recipe: manifest.llm_recipe,
                },
              } : current)}
            />}
            onDeleteNode={async (node) => {
              const result = await deleteFlowNode(flowId, node.id, files)
              updateGraphResult(result)
              setSelectedNode(null)
              setOpenNodeEditors((current) => current.filter((editor) => editor.nodeId !== node.id))
              showToast({ title: '节点已删除', type: 'success' })
            }}
            onSaved={(result) => {
              updateGraphResult(result)
              const node = result.graph.nodes.find((item) => item.id === result.node_id)
              if (node) {
                setSelectedNode(node)
                setFocusNodeId(node.id)
              }
              showToast({ title: '节点已保存', type: 'success' })
            }}
          />
          {historyOpen && (
            <RunHistoryPanel
              runs={runs}
              graph={detail.graph}
              selectedRunId={selectedRunId}
              busy={runControlBusy}
              onClose={() => setHistoryOpen(false)}
              onSelect={async (runId) => {
                setSelectedHistoryRunId(runId)
              }}
              onOpenLog={async (run) => {
                try {
                  const [selectedRun, selectedEvents] = await Promise.all([
                    fetchCartridgeRun(run.run_id),
                    fetchCartridgeRunEvents(run.run_id),
                  ])
                  setRunLog({ run: selectedRun, events: selectedEvents.items || [] })
                } catch (e: any) {
                  showToast({ title: '读取运行日志失败', description: e.message, type: 'error' })
                }
              }}
              onOpenArtifacts={async (run) => {
                await openRunArtifactsDirectory(run)
              }}
              onRefresh={async () => {
                try {
                  const data = await fetchLabFlowRuns(flowId)
                  setRuns(data.items || [])
                  setSelectedHistoryRunId((current) => current || data.items?.[0]?.run_id || '')
                } catch (e: any) {
                  showToast({ title: '刷新失败', description: e.message, type: 'error' })
                }
              }}
            />
          )}
        </div>
        {runLog && <RunLogDialog run={runLog.run} events={runLog.events} onClose={() => setRunLog(null)} />}

      </Box>
    </Box>
  )
}
