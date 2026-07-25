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
  saveFlowLayout,
  runFlow,
  updateFlowNode,
  type FlowEvent,
  type FlowFiles,
  type FlowLabDetail,
  type FlowNode,
  type McpTool,
  type RunResult,
  type TestProbeRange,
} from '../api.ts'
import { showToast } from '../toast.tsx'
import { DesignView, RunHistoryPanel, RunLogDialog, WorkbenchHeader } from './flow-workbench/views.tsx'
import { CATEGORY_BY_ID, PROCESS_KIND_LABELS, formatProcessDisplayLabel, getPreset, getProtocolDefaults } from './flow-workbench/nodeModel.ts'
import type { CreateNodeOptions, GraphResult, NodeCategoryId } from './flow-workbench/types.ts'
import { ModelManagementPanel, ToolManagementPanel } from './flow-workbench/ResourceManagementPanels.tsx'
import CartridgeWorkspaceControl from './flow-workbench/CartridgeWorkspaceControl.tsx'
import { RunInputDialog, buildNodeRunStates } from './flow-workbench/TestBenchView.tsx'
import { NODE_DETAIL_SECTION_BY_ID, nodeDetailId, normalizeNodeDetailSection, type NodeDetailSection, type OpenNodeDetail } from './flow-workbench/nodeDetails.ts'

const firstText = (...values: any[]) => values.find((value) => typeof value === 'string' && value.trim())?.trim() || ''
const sleep = (ms: number) => new Promise((resolve) => window.setTimeout(resolve, ms))
const pinnedNodeDetailsStorageKey = (flowId: string) => `cartridgeflow.lite.pinned-node-details.v1:${flowId}`

const TOOL_PRESET_TARGETS: Record<string, { server: string; tool: string; idHints: string[] }> = {
  filesystem_read: { server: 'filesystem', tool: 'read_file', idHints: ['filesystem_read', 'fs_read', 'read_file'] },
  filesystem_write: { server: 'filesystem', tool: 'write_file', idHints: ['filesystem_write', 'fs_write', 'write_file'] },
  filesystem_list: { server: 'filesystem', tool: 'list_dir', idHints: ['filesystem_list', 'fs_list', 'list_dir'] },
}

const lowerText = (value: any) => String(value || '').trim().toLowerCase()

function findMcpToolById(mcpTools: McpTool[], id: string) {
  const target = lowerText(id)
  if (!target) return null
  return mcpTools.find((tool) => lowerText(tool.id) === target) || null
}

function findMcpToolByServerTool(mcpTools: McpTool[], server: string, toolName: string) {
  const targetServer = lowerText(server)
  const targetTool = lowerText(toolName)
  if (!targetServer || !targetTool) return null
  return mcpTools.find((tool) => lowerText(tool.server) === targetServer && lowerText(tool.tool) === targetTool) || null
}

function resolveMcpLibraryTool(
  categoryId: NodeCategoryId,
  presetId: string,
  presetConfig: Record<string, any>,
  draftNode: any,
  mcpTools: McpTool[] = [],
) {
  const protocolKind = lowerText(draftNode?.kind || draftNode?.params?.kind)
  const isMcpProcess = protocolKind === 'mcp_read' || protocolKind === 'mcp_execute'
  if (categoryId !== 'tool' && !isMcpProcess) return null
  if (!mcpTools.length) return null
  const explicitId = firstText(
    presetConfig.mcp_tool_id,
    presetConfig.tool_id,
    presetConfig.mcpToolId,
    draftNode?.mcp_tool_id,
    draftNode?.tool_id,
    draftNode?.mcpToolId,
    draftNode?.mcp_tool?.id,
    draftNode?.params?.mcp_tool_id,
    draftNode?.params?.tool_id,
  )
  const byId = explicitId ? findMcpToolById(mcpTools, explicitId) : null
  if (byId) return byId

  const server = firstText(presetConfig.server, draftNode?.server, draftNode?.params?.server, draftNode?.mcp_server)
  const toolName = firstText(presetConfig.tool, draftNode?.tool, draftNode?.params?.tool, draftNode?.mcp_tool_name)
  const byServerTool = findMcpToolByServerTool(mcpTools, server, toolName)
  if (byServerTool) return byServerTool

  const target = TOOL_PRESET_TARGETS[presetId]
  if (target) {
    for (const hint of target.idHints) {
      const hinted = findMcpToolById(mcpTools, hint)
      if (hinted) return hinted
    }
    const byPresetServerTool = findMcpToolByServerTool(mcpTools, target.server, target.tool)
    if (byPresetServerTool) return byPresetServerTool
  }

  const intentText = lowerText([
    presetId,
    draftNode?.title,
    draftNode?.label,
    draftNode?.description,
    draftNode?.goal,
    draftNode?.prompt,
    presetConfig.action,
    presetConfig.intent,
  ].filter(Boolean).join(' '))
  if (!intentText.includes('filesystem') && !intentText.includes('file') && !intentText.includes('文件')) return null
  if (intentText.includes('write') || intentText.includes('save') || intentText.includes('写') || intentText.includes('保存')) {
    return findMcpToolByServerTool(mcpTools, 'filesystem', 'write_file') || findMcpToolById(mcpTools, 'filesystem_write')
  }
  if (intentText.includes('list') || intentText.includes('目录') || intentText.includes('列出')) {
    return findMcpToolByServerTool(mcpTools, 'filesystem', 'list_dir') || findMcpToolById(mcpTools, 'filesystem_list')
  }
  if (intentText.includes('read') || intentText.includes('读取') || intentText.includes('读')) {
    return findMcpToolByServerTool(mcpTools, 'filesystem', 'read_file') || findMcpToolById(mcpTools, 'filesystem_read')
  }
  return null
}

function bindMcpToolToPresetConfig(presetConfig: Record<string, string>, libraryTool: McpTool | null) {
  if (!libraryTool) return presetConfig
  presetConfig.mcp_tool_id = libraryTool.id
  presetConfig.server = libraryTool.server
  presetConfig.tool = libraryTool.tool
  return presetConfig
}

function buildLibraryToolParams(libraryTool: McpTool, presetId: string, presetConfig: Record<string, string>, inputText: string) {
  const params: Record<string, any> = { ...(libraryTool.default_params || {}) }
  if (presetConfig.path) params.path = presetConfig.path
  if (presetConfig.content) params.content = presetConfig.content
  if (libraryTool.server === 'filesystem' && libraryTool.tool === 'write_file') {
    const source = firstText(presetConfig.source, inputText)
    if (source) params.content = `store:${source}`
  }
  if (libraryTool.server === 'filesystem' && libraryTool.tool === 'read_file' && presetConfig.path) {
    params.path = presetConfig.path
  }
  if (libraryTool.server === 'filesystem' && libraryTool.tool === 'list_dir' && presetConfig.path) {
    params.path = presetConfig.path
  }
  if (presetId === 'mcp_call') {
    Object.entries(presetConfig).forEach(([key, value]) => {
      if (!value || ['mcp_tool_id', 'tool_id', 'server', 'tool', 'output_name', 'source'].includes(key)) return
      params[key] = value
    })
  }
  return params
}

function buildPresetConfig(draftNode: any, categoryId: NodeCategoryId, presetId: string, baseId: string, index: number) {
  const preset = getPreset(categoryId, presetId)
  const config = { ...((draftNode.preset_config || draftNode.presetConfig || {}) as Record<string, string>) }
  const title = firstText(draftNode.title, draftNode.label, baseId)
  const description = firstText(draftNode.description, draftNode.goal, draftNode.prompt, title)
  const outputName = firstText(draftNode.output_name, draftNode.outputName, draftNode.output, `${baseId || categoryId}_${index + 1}_result`)
  preset.fields.forEach((field) => {
    if (config[field.key]) return
    if (field.key === 'output_name') config[field.key] = outputName
    else if (field.key === 'fields') config[field.key] = firstText(draftNode.input, draftNode.fields, '用户需求、目标、限制条件')
    else if (field.key === 'goal') config[field.key] = description
    else if (field.key === 'target') config[field.key] = firstText(draftNode.target, draftNode.output, title)
    else if (field.key === 'format') config[field.key] = firstText(draftNode.format, '结构化文本')
    else if (field.key === 'change_goal') config[field.key] = description
    else if (field.key === 'from_to') config[field.key] = firstText(draftNode.from_to, `${firstText(draftNode.input, '上游结果')} -> ${outputName}`)
    else if (field.key === 'focus') config[field.key] = description
    else if (field.key === 'from') config[field.key] = firstText(draftNode.from, draftNode.input, '上游结果')
    else if (field.key === 'to') config[field.key] = firstText(draftNode.to, draftNode.output, `${baseId}.input`)
    else if (field.key === 'mapping') config[field.key] = firstText(draftNode.mapping, `${firstText(draftNode.input, 'source')} -> ${outputName}`)
    else if (field.key === 'items') config[field.key] = firstText(draftNode.items, draftNode.input, '上游结果')
    else if (field.key === 'rule') config[field.key] = firstText(draftNode.rule, description)
    else if (field.key === 'key') config[field.key] = firstText(draftNode.key, draftNode.save_to, `context.${baseId}`)
    else if (field.key === 'source') config[field.key] = firstText(draftNode.source, draftNode.input, outputName)
    else if (field.key === 'path') config[field.key] = firstText(draftNode.path, `${baseId}.md`)
    else if (field.key === 'ttl') config[field.key] = firstText(draftNode.ttl, '本次运行')
    else if (field.key === 'name') config[field.key] = firstText(draftNode.name, `draft.${baseId}`)
    else if (field.key === 'message') config[field.key] = firstText(draftNode.message, description)
    else if (field.key === 'condition') config[field.key] = firstText(draftNode.condition, '根据上游结果判断是否继续')
    else if (field.key === 'on_cancel') config[field.key] = firstText(draftNode.on_cancel, 'stop')
    else if (field.key === 'on_fail') config[field.key] = firstText(draftNode.on_fail, '人工确认或回流修正')
    else if (field.key === 'pass_to') config[field.key] = firstText(draftNode.pass_to, '下一节点')
    else if (field.key === 'fail_to') config[field.key] = firstText(draftNode.fail_to, '修正节点')
    else if (field.key === 'risk_rule') config[field.key] = firstText(draftNode.risk_rule, description)
  })
  return config
}

function buildToolSpecs(categoryId: NodeCategoryId, presetId: string, presetConfig: Record<string, string>, inputText: string, outputText: string, draftTools?: any, mcpTools: McpTool[] = [], draftNode?: any) {
  if (Array.isArray(draftTools)) return draftTools
  const protocolKind = lowerText(draftNode?.kind || draftNode?.params?.kind)
  const isMcpProcess = protocolKind === 'mcp_read' || protocolKind === 'mcp_execute'
  if (categoryId !== 'tool' && !isMcpProcess) return draftTools ?? null
  const output = outputText || presetConfig.output_name || 'tool_result'
  const libraryTool = resolveMcpLibraryTool(categoryId, presetId, presetConfig, draftNode, mcpTools)
  if (libraryTool) {
    bindMcpToolToPresetConfig(presetConfig, libraryTool)
    return [{
      type: libraryTool.type || 'builtin',
      server: libraryTool.server,
      tool: libraryTool.tool,
      params: buildLibraryToolParams(libraryTool, presetId, presetConfig, inputText),
      enabled: libraryTool.enabled !== false,
      output,
      mcp_tool_id: libraryTool.id,
    }]
  }
  if (presetId === 'filesystem_read') {
    return [{ type: 'builtin', server: 'filesystem', tool: 'read_file', params: { path: presetConfig.path || '' }, enabled: true, output }]
  }
  if (presetId === 'filesystem_write') {
    return [{ type: 'builtin', server: 'filesystem', tool: 'write_file', params: { path: presetConfig.path || '', content: `store:${presetConfig.source || inputText}` }, enabled: true, output }]
  }
  if (presetId === 'filesystem_list') {
    return [{ type: 'builtin', server: 'filesystem', tool: 'list_dir', params: { path: presetConfig.path || '.' }, enabled: true, output }]
  }
  if (presetId === 'mcp_call') {
    return [{ type: 'builtin', server: presetConfig.server || '', tool: presetConfig.tool || '', params: {}, enabled: true, output }]
  }
  return []
}

function normalizeToolIdList(values: any[]) {
  return [...new Set(values.map((value) => String(value || '').trim()).filter(Boolean))]
}

function collectAllowedTools(toolSpecs: any, presetConfig: Record<string, string>, draftNode?: any) {
  const fromSpecs = Array.isArray(toolSpecs)
    ? toolSpecs.map((tool) => tool?.mcp_tool_id || tool?.tool_id || tool?.id)
    : []
  const explicit = Array.isArray(draftNode?.allowed_tools)
    ? draftNode.allowed_tools
    : Array.isArray(draftNode?.allowedTools)
      ? draftNode.allowedTools
      : []
  return normalizeToolIdList([
    ...explicit,
    presetConfig.mcp_tool_id,
    presetConfig.tool_id,
    draftNode?.mcp_tool_id,
    draftNode?.tool_id,
    ...fromSpecs,
  ])
}

function getMcpToolSideEffect(tool?: McpTool | null) {
  return lowerText(tool?.contract?.side_effect || tool?.contract?.effect || '')
}

function isReadOnlyMcpTool(tool?: McpTool | null) {
  if (!tool) return false
  const sideEffect = getMcpToolSideEffect(tool)
  return !sideEffect || sideEffect === 'none' || sideEffect === 'read_only' || sideEffect === 'environment_probe'
}

function effectForMcpTool(tool?: McpTool | null, fallback = 'writes_files') {
  if (!tool) return fallback
  const sideEffect = getMcpToolSideEffect(tool)
  if (!sideEffect || sideEffect === 'none' || sideEffect === 'read_only' || sideEffect === 'environment_probe') return 'read_only'
  if (sideEffect.includes('world_state') || sideEffect.includes('state')) return 'mutates_state'
  if (sideEffect.includes('remote') || sideEffect.includes('external')) return 'external_side_effect'
  if (sideEffect.includes('artifact') || sideEffect.includes('preview') || sideEffect.includes('frame')) return 'writes_artifacts'
  if (sideEffect.includes('file') || sideEffect.includes('asset') || sideEffect.includes('manifest')) return 'writes_files'
  return fallback
}

function permissionForEffect(effect: string) {
  if (effect === 'mutates_state') return 'write_world_state'
  if (effect === 'external_side_effect') return 'external_service_call'
  if (effect === 'writes_files') return 'write_workspace_files'
  if (effect === 'writes_artifacts') return 'write_run_artifacts'
  return ''
}

function buildProtocolPatch(categoryId: NodeCategoryId, presetId: string, presetConfig: Record<string, string>, toolSpecs: any, mcpTools: McpTool[], draftNode: any = {}, outputText = '') {
  const defaults = getProtocolDefaults(categoryId, presetId)
  const allowedTools = collectAllowedTools(toolSpecs, presetConfig, draftNode)
  const firstTool = allowedTools.length ? findMcpToolById(mcpTools, allowedTools[0]) : null
  const explicitKind = firstText(draftNode.kind, draftNode.params?.kind)
  const explicitExecutor = firstText(draftNode.executor, draftNode.params?.executor)
  const explicitEffect = firstText(draftNode.effect, draftNode.params?.effect)
  let kind = explicitKind || defaults.kind
  let executor = explicitExecutor || defaults.executor
  let effect = explicitEffect || defaults.effect
  let toolBinding = firstText(draftNode.tool_binding, draftNode.toolBinding, defaults.toolBinding)
  let mcpBinding: any = draftNode.mcp_binding || draftNode.mcpBinding || {}
  let failurePolicy = firstText(draftNode.failure_policy, draftNode.failurePolicy, defaults.failurePolicy)
  let permission = firstText(draftNode.permission, defaults.permission)
  let auditLog = draftNode.audit_log ?? draftNode.auditLog ?? defaults.auditLog ?? false

  if (categoryId === 'tool' || kind === 'mcp_read' || kind === 'mcp_execute') {
    effect = explicitEffect || effectForMcpTool(firstTool, defaults.effect)
    kind = firstTool
      ? isReadOnlyMcpTool(firstTool) ? 'mcp_read' : 'mcp_execute'
      : defaults.kind === 'mcp_read' || defaults.effect === 'read_only' ? 'mcp_read' : 'mcp_execute'
    executor = 'mcp'
    if (kind === 'mcp_read') {
      effect = 'read_only'
      toolBinding = ''
      failurePolicy = ''
      permission = ''
      auditLog = false
      mcpBinding = { mode: 'read_only', allowed_tools: allowedTools }
    } else {
      toolBinding = toolBinding || 'static_params'
      failurePolicy = failurePolicy || 'fail_closed'
      permission = permission || permissionForEffect(effect)
      auditLog = true
      mcpBinding = {}
    }
  }

  if (categoryId === 'remote' || kind === 'remote_call') {
    kind = 'remote_call'
    executor = 'remote'
    effect = effect === 'read_only' || effect === 'none' ? 'external_side_effect' : effect
    toolBinding = toolBinding || 'static_params'
    failurePolicy = failurePolicy || 'fail_closed'
    permission = permission || permissionForEffect(effect)
    auditLog = true
  }

  const suffix = firstText(draftNode.display?.suffix, PROCESS_KIND_LABELS[kind], defaults.displaySuffix)
  const label = formatProcessDisplayLabel(suffix)
  const outputContract = firstText(
    draftNode.output_contract,
    draftNode.outputContract,
    defaults.outputContract,
    kind === 'decision' && executor === 'llm' ? 'decision_envelope.v1' : '',
  )
  const decisionContract = kind === 'decision' && executor === 'llm'
    ? (draftNode.decision_contract || draftNode.decisionContract || defaults.decisionContract || {
      schema: 'decision_envelope.v1',
      allowed_statuses: ['resolved', 'needs_user_input', 'blocked'],
      on_needs_user_input: 'pause',
      interaction: {
        store_key: 'decision_user_reply',
        input_schema: 'decision_reply.v1',
        resume_policy: 'resume_same_node',
      },
      consume: {
        mode: 'payload_path',
        path: 'payload.decision',
        as: 'decision_payload',
        required: true,
        on_missing: 'fail_closed',
      },
    })
    : undefined
  return {
    type: 'process',
    action: firstText(draftNode.action, defaults.action),
    kind,
    executor,
    effect,
    display: { suffix, label },
    input_kind: firstText(draftNode.input_kind, draftNode.inputKind, defaults.inputKind),
    source: firstText(draftNode.source, defaults.source),
    input_schema: draftNode.input_schema || draftNode.inputSchema || defaults.inputSchema || '',
    output_contract: outputContract,
    decision_contract: decisionContract,
    decision_test_mode: '',
    mock_decision_envelope: null,
    primary_output: firstText(draftNode.primary_output, draftNode.primaryOutput, outputText, presetConfig.output_name),
    tool_binding: toolBinding,
    allowed_tools: allowedTools,
    mcp_binding: mcpBinding,
    failure_policy: failurePolicy,
    permission,
    audit_log: Boolean(auditLog),
    endpoint: firstText(draftNode.endpoint, draftNode.params?.endpoint, presetConfig.endpoint, presetConfig.service, presetConfig.server, categoryId === 'remote' ? 'remote://pending' : ''),
    timeout_ms: Number(draftNode.timeout_ms || draftNode.timeoutMs || presetConfig.timeout_ms || presetConfig.timeoutMs || (categoryId === 'remote' ? 120000 : 0)) || undefined,
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
  const activeRuntimeRun = runs.find((run) => ['created', 'running', 'retrying', 'recovering', 'rolling_back', 'paused', 'paused_waiting_user'].includes(run.status))
  const selectedRunId = selectedHistoryRunId || runs[0]?.run_id || ''
  const designNodeRunStates = useMemo(
    () => detail && activeRuntimeRun && events.length ? buildNodeRunStates(detail.graph, events) : undefined,
    [activeRuntimeRun, detail, events],
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
      if (['completed', 'failed', 'cancelled', 'interrupted', 'paused', 'paused_waiting_user'].includes(runData.status)) break
    }
    return latest
  }, [])

  const startFlowRun = useCallback(async (inputs: Record<string, string>, probeRange?: TestProbeRange) => {
    setRunInputOpen(false)
    setEvents([])
    setRunControlBusy(true)
    try {
      const result = await runFlow(flowId, inputs, probeRange)
      setRuns((current) => [result.run, ...current.filter((item) => item.run_id !== result.run.run_id)])
      setSelectedHistoryRunId(result.run.run_id)
      setEvents(result.events || [])
      setRunControlBusy(false)
      const latest = await pollRunUntilStable(result.run.run_id) || result.run
      showToast({
        title: latest.status === 'paused_waiting_user'
          ? '运行已暂停，等待用户补充信息'
          : latest.status === 'paused'
            ? '运行已在节点边界暂停'
            : latest.status === 'interrupted'
              ? '运行被底座中断，可从检查点恢复'
              : latest.status === 'failed'
                ? '运行发现失败节点'
                : latest.status === 'cancelled'
                  ? '运行已停止'
                  : '运行完成',
        type: ['failed', 'interrupted'].includes(latest.status) ? 'error' : 'success',
      })
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
            onCreateNode={createCategoryNode}
            nodeRunStates={designNodeRunStates}
            runEvents={events}
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
