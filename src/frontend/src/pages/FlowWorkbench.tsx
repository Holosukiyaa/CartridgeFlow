import { useCallback, useEffect, useMemo, useState } from 'react'
import { Box, Button, Spinner, Text } from '../ui.tsx'
import {
  cloneCartridgeToDev,
  controlCartridgeRun,
  createFlowNode,
  deleteFlowNode,
  fetchLabFlow,
  fetchLabFlowFiles,
  fetchLabFlowRuns,
  fetchMcpTools,
  fetchCartridgeRun,
  fetchCartridgeRunEvents,
  saveFlowEdges,
  saveFlowAnnotations,
  saveFlowLayout,
  runFlow,
  updateFlowNode,
  type FlowEvent,
  type FlowAnnotation,
  type FlowFiles,
  type FlowLabDetail,
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
import { ModelManagementPanel, ToolManagementPanel } from './flow-workbench/ResourceManagementPanels.tsx'
import CartridgeWorkspaceControl from './flow-workbench/CartridgeWorkspaceControl.tsx'
import { RunInputDialog } from './flow-workbench/RunInputDialog.tsx'
import { buildNodeRunStates } from './flow-workbench/runState.ts'
import { NODE_DETAIL_SECTION_BY_ID, nodeDetailId, normalizeNodeDetailSection, type NodeDetailSection, type OpenNodeDetail } from './flow-workbench/nodeDetails.ts'
import './flow-workbench/TestBench.css'

const sleep = (ms: number) => new Promise((resolve) => window.setTimeout(resolve, ms))
const pinnedNodeDetailsStorageKey = (flowId: string) => `cartridgeflow.lite.pinned-node-details.v1:${flowId}`
const RUN_COMPLETION_NOTICE_MS = 2600

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
  const [runs, setRuns] = useState<RunResult[]>([])
  const [events, setEvents] = useState<FlowEvent[]>([])
  const [mcpTools, setMcpTools] = useState<McpTool[]>([])
  const [flowResourceTools, setFlowResourceTools] = useState<McpTool[]>([])
  const [cloningToDev, setCloningToDev] = useState(false)
  const [runInputOpen, setRunInputOpen] = useState(false)
  const [runControlBusy, setRunControlBusy] = useState(false)
  const [historyOpen, setHistoryOpen] = useState(false)
  const [selectedHistoryRunId, setSelectedHistoryRunId] = useState('')
  const [runLog, setRunLog] = useState<{ run: RunResult; events: FlowEvent[] } | null>(null)
  const [runCompletionNotice, setRunCompletionNotice] = useState<{ runId: string; shownAt: number } | null>(null)
  const activeRuntimeRun = runs.find((run) => ['created', 'running', 'retrying', 'recovering', 'rolling_back', 'paused', 'paused_waiting_user'].includes(run.status))
  const visualRuntimeRun = activeRuntimeRun || (runCompletionNotice ? runs.find((run) => run.run_id === runCompletionNotice.runId) : undefined)
  const selectedRunId = selectedHistoryRunId || runs[0]?.run_id || ''
  const designNodeRunStates = useMemo(
    () => detail && visualRuntimeRun ? buildNodeRunStates(detail.graph, events) : undefined,
    [detail, events, visualRuntimeRun],
  )
  const availableMcpTools = useMemo(() => {
    const merged = new Map<string, McpTool>()
    for (const tool of flowResourceTools) merged.set(tool.id, tool)
    for (const tool of mcpTools) merged.set(tool.id, tool)
    return [...merged.values()]
  }, [flowResourceTools, mcpTools])

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    setRunCompletionNotice(null)
    try {
      const data = await fetchLabFlow(flowId)
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
    const remaining = Math.max(0, RUN_COMPLETION_NOTICE_MS - (Date.now() - runCompletionNotice.shownAt))
    const timer = window.setTimeout(() => {
      setRunCompletionNotice((current) => current?.runId === runCompletionNotice.runId ? null : current)
    }, remaining)
    return () => window.clearTimeout(timer)
  }, [runCompletionNotice])
  useEffect(() => {
    setRestoredNodeDetailsFlowId('')
    try {
      const stored = JSON.parse(window.localStorage.getItem(pinnedNodeDetailsStorageKey(flowId)) || '[]')
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

  const pollRunUntilStable = useCallback(async (runId: string, maxAttempts = 900) => {
    let latest: RunResult | null = null
    for (let attempt = 0; attempt < maxAttempts; attempt++) {
      await sleep(800)
      let runData: RunResult
      let eventData: { items: FlowEvent[] }
      try {
        ;[runData, eventData] = await Promise.all([
          fetchCartridgeRun(runId),
          fetchCartridgeRunEvents(runId),
        ])
      } catch (pollError) {
        if (attempt < 10) continue
        throw pollError
      }
      latest = runData
      setRuns((current) => [runData, ...current.filter((item) => item.run_id !== runData.run_id)])
      setEvents(eventData.items || [])
      if (runData.status === 'completed') {
        setRunCompletionNotice((current) => current?.runId === runData.run_id
          ? current
          : { runId: runData.run_id, shownAt: Date.now() })
      }
      if (['completed', 'failed', 'cancelled', 'interrupted', 'paused', 'paused_waiting_user'].includes(runData.status)) break
    }
    return latest
  }, [])

  const startFlowRun = useCallback(async (inputs: Record<string, string>, probeRange?: TestProbeRange) => {
    setRunInputOpen(false)
    setRunCompletionNotice(null)
    setEvents([])
    setRunControlBusy(true)
    try {
      const result = await runFlow(flowId, inputs, probeRange)
      setRuns((current) => [result.run, ...current.filter((item) => item.run_id !== result.run.run_id)])
      setSelectedHistoryRunId(result.run.run_id)
      setEvents(result.events || [])
      setRunControlBusy(false)
      const latest = await pollRunUntilStable(result.run.run_id) || result.run
      if (latest.status === 'completed') {
        setRunCompletionNotice((current) => current?.runId === latest.run_id
          ? current
          : { runId: latest.run_id, shownAt: Date.now() })
      } else {
        showToast({
          title: latest.status === 'paused_waiting_user'
            ? '运行已暂停，等待用户补充信息'
            : latest.status === 'paused'
              ? '运行已在节点边界暂停'
              : latest.status === 'interrupted'
                ? '运行被底座中断，可从检查点恢复'
                : latest.status === 'failed'
                  ? '运行发现失败节点'
                  : '运行已停止',
          type: ['failed', 'interrupted'].includes(latest.status) ? 'error' : 'success',
        })
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
      showToast({
        title: action === 'pause' ? '已请求暂停' : action === 'resume' ? '已继续运行' : '已停止运行',
        description: action === 'pause' ? '当前节点结束后会停在可恢复检查点。' : undefined,
        type: 'success',
      })
    } catch (e: any) {
      showToast({ title: '运行控制失败', description: e.message, type: 'error' })
    } finally {
      setRunControlBusy(false)
    }
  }, [activeRuntimeRun, events, runControlBusy])

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

  const openNodeEditor = useCallback((node: FlowNode, section: NodeDetailSection) => {
    setSelectedNode(node)
    setFocusNodeId(node.id)
    setOpenNodeEditors((current) => {
      const retained = current.filter((editor) => editor.pinned || editor.nodeId === node.id)
      const editorId = nodeDetailId(node.id, section)
      const existing = retained.find((editor) => nodeDetailId(editor.nodeId, editor.section) === editorId)
      return existing ? retained : [...retained, { nodeId: node.id, section, pinned: true }]
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
    } catch (e: any) {
      showToast({ title: '新增失败', description: e.message, type: 'error' })
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
          onPause={() => void controlActiveRun(activeRuntimeRun?.status === 'paused' ? 'resume' : 'pause')}
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

        <div className="cf-workbench-design-shell">
            <DesignView
            graph={detail.graph}
            editable={editable}
            files={files}
            flowId={flowId}
            selectedNode={selectedNode}
            focusNodeId={focusNodeId}
            openNodeEditors={openNodeEditors}
            onSelectNode={selectNode}
            onOpenNodeEditor={openNodeEditor}
            onCloseNodeEditor={closeNodeEditor}
            onToggleNodeEditorPin={toggleNodeEditorPin}
            onNodeEditorPositionChange={updateNodeEditorPosition}
            onCloseUnpinnedNodeEditors={closeUnpinnedNodeEditors}
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
            runStatus={visualRuntimeRun?.status}
            nodeRunStates={designNodeRunStates}
            runEvents={events}
            runCompletionVisible={Boolean(runCompletionNotice)}
            onDismissRunCompletion={() => setRunCompletionNotice(null)}
            modelPanel={<ModelManagementPanel flowId={flowId} cartridge={detail.cartridge} />}
            toolPanel={<ToolManagementPanel flowId={flowId} onFlowToolsChange={setFlowResourceTools} />}
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
