import { useCallback, useEffect, useMemo, useState } from 'react'
import { Box, Button, Spinner, Text } from '../ui.tsx'
import {
  answerPendingInteraction,
  cloneCartridgeToDev,
  createFlowNode,
  createMcpTool,
  deleteMcpTool,
  deleteFlowNode,
  fetchLabFlow,
  fetchLabFlowFiles,
  fetchLabFlowRuns,
  fetchMcpTools,
  fetchCartridgeRun,
  fetchCartridgeRunEvents,
  saveLabFlowFile,
  saveFlowEdges,
  saveFlowLayout,
  testRunFlow,
  updateMcpTool,
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
import { DesignView, RunView, WorkbenchHeader } from './flow-workbench/views.tsx'
import { CATEGORY_BY_ID, PROCESS_KIND_LABELS, buildAutoAlignLayout, formatProcessDisplayLabel, getPreset, getProtocolDefaults } from './flow-workbench/nodeModel.ts'
import type { FlowAssistantApplyResult, FlowAssistantDraft, FlowAssistantGraphOps } from './flow-workbench/FlowAssistantPanel.tsx'
import type { GraphResult, NodeCategoryId, WorkbenchMode } from './flow-workbench/types.ts'
import { McpLibraryPanel } from './flow-workbench/McpLibraryPanel.tsx'

const firstText = (...values: any[]) => values.find((value) => typeof value === 'string' && value.trim())?.trim() || ''
const sleep = (ms: number) => new Promise((resolve) => window.setTimeout(resolve, ms))

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
    decision_test_mode: firstText(draftNode.decision_test_mode, draftNode.decisionTestMode, draftNode.params?.decision_test_mode),
    mock_decision_envelope: kind === 'decision' && executor === 'llm'
      ? (draftNode.mock_decision_envelope || draftNode.mockDecisionEnvelope || draftNode.params?.mock_decision_envelope || {})
      : undefined,
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

export default function FlowWorkbench({ flowId, onBack, onSwitchFlow }: { flowId: string; onBack: () => void; onSwitchFlow?: (flowId: string) => void }) {
  const [detail, setDetail] = useState<FlowLabDetail | null>(null)
  const [files, setFiles] = useState<FlowFiles>({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [mode, setMode] = useState<WorkbenchMode>('design')
  const [selectedNode, setSelectedNode] = useState<FlowNode | null>(null)
  const [focusNodeId, setFocusNodeId] = useState<string | null>(null)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [runs, setRuns] = useState<RunResult[]>([])
  const [events, setEvents] = useState<FlowEvent[]>([])
  const [mcpTools, setMcpTools] = useState<McpTool[]>([])
  const [mcpLibraryOpen, setMcpLibraryOpen] = useState(false)
  const [cloningToDev, setCloningToDev] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const data = await fetchLabFlow(flowId)
      setDetail(data)
      setRuns(data.runs || [])
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

  const editable = Boolean(detail?.cartridge.editable)

  const changeMode = useCallback((nextMode: WorkbenchMode) => {
    setMode(nextMode)
    if (nextMode === 'run') {
      setRuns([])
      setEvents([])
    }
  }, [])

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
      setRuns([runData])
      setEvents(eventData.items || [])
      if (['completed', 'failed', 'cancelled', 'paused_waiting_user'].includes(runData.status)) break
    }
    return latest
  }, [])

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
      onSwitchFlow?.(result.id)
    } catch (e: any) {
      showToast({ title: '复制失败', description: e.message, type: 'error' })
    } finally {
      setCloningToDev(false)
    }
  }, [detail?.cartridge, onSwitchFlow])

  const tags = useMemo(() => {
    if (!detail) return []
    return [
      ...((detail.cartridge as any).tags || []),
      ...((detail.cartridge.manifest as any)?.tags || []),
      ...((detail.cartridge.manifest as any)?.metadata?.tags || []),
    ].filter(Boolean).slice(0, 8)
  }, [detail])

  const selectNode = useCallback((node: FlowNode) => {
    setSelectedNode(node)
    setFocusNodeId(node.id)
    setDrawerOpen(!node.locked)
  }, [])

  const updateGraphResult = useCallback((result: GraphResult) => {
    setFiles(result.files)
    setDetail((prev) => prev ? { ...prev, graph: result.graph } : prev)
  }, [])

  const autoAlignResult = useCallback(async (result: GraphResult) => {
    const layout = buildAutoAlignLayout(result.graph)
    const aligned = await saveFlowLayout(flowId, result.files, layout)
    updateGraphResult(aligned)
    return aligned
  }, [flowId, updateGraphResult])

  const applyAssistantDraft = useCallback(async (draft: FlowAssistantDraft, sourceNode: FlowNode | null = selectedNode): Promise<FlowAssistantApplyResult> => {
    const draftData = draft as any
    const draftNodes = Array.isArray(draftData.nodes)
      ? draftData.nodes
      : Array.isArray(draftData.steps)
        ? draftData.steps
        : []

    if (!draftNodes.length) {
      showToast({ title: '草稿中没有可应用的节点', type: 'error' })
      throw new Error('草稿中没有可应用的节点')
    }

    let workingFiles = files
    let workingGraph = detail?.graph
    let previousNode = sourceNode
      || detail?.graph.nodes.find((node) => node.id === 'start' || node.type === 'start')
      || detail?.graph.nodes[0]
      || null
    let lastResult: GraphResult | null = null
    const idMap = new Map<string, string>()
    const createdNodeIds: string[] = []

    try {
      for (const [index, draftNode] of draftNodes.entries()) {
        const requestedCategory = draftNode.categoryId || draftNode.category_id || draftNode.node_category || draftNode.category || 'custom'
        const category = CATEGORY_BY_ID.get(requestedCategory as NodeCategoryId) || CATEGORY_BY_ID.get('custom' as NodeCategoryId)!
        const draftNodeId = String(draftNode.id || draftNode.node_id || `${requestedCategory}_${index}`)
        const safeBaseId = draftNodeId.replace(/[^a-zA-Z0-9_-]/g, '_')
        const nodeId = `${safeBaseId}_${Date.now().toString(36)}_${index}`
        const presetId = draftNode.preset ?? (category.id === 'custom' ? 'blank' : getPreset(category.id).id)
        const presetConfig = buildPresetConfig(draftNode, category.id, presetId, safeBaseId, index)
        const inputText = firstText(draftNode.input, draftNode.params?.input, presetConfig.from, presetConfig.source, presetConfig.items)
        const outputText = firstText(draftNode.output, draftNode.params?.output, presetConfig.output_name, presetConfig.to, presetConfig.path, presetConfig.key)
        const saveTo = firstText(draftNode.save_to, draftNode.saveTo, draftNode.params?.save_to, presetConfig.key, presetConfig.path, presetConfig.name)
        const condition = firstText(draftNode.condition, draftNode.params?.condition, presetConfig.condition, presetConfig.risk_rule, presetConfig.message)
        const toolSpecs = buildToolSpecs(category.id, presetId, presetConfig, inputText, outputText, draftNode.tools, mcpTools, draftNode)
        const protocolPatch = buildProtocolPatch(category.id, presetId, presetConfig, toolSpecs, mcpTools, draftNode, outputText)

        const created = await createFlowNode(flowId, {
          files: workingFiles,
          template_id: category.templateId,
          node_id: nodeId,
          title: draftNode.title || draftNode.label || category.defaultTitle,
          after_node_id: previousNode?.id,
          insert_mode: 'insert',
        })
        idMap.set(draftNodeId, created.node_id)
        createdNodeIds.push(created.node_id)

        const createdNode = created.graph.nodes.find((node) => node.id === created.node_id)
        const updated = await updateFlowNode(flowId, created.node_id, {
          files: created.files,
          title: draftNode.title || draftNode.label || category.defaultTitle,
          ...protocolPatch,
          next: createdNode?.next || '',
          agent: draftNode.agent ?? null,
          model_role: draftNode.model_role ?? draftNode.modelRole ?? null,
          tools: toolSpecs,
          params: {
            ...(createdNode?.params || {}),
            ...(draftNode.params || {}),
            node_category: category.id,
            preset: presetId,
            preset_config: presetConfig,
            description: draftNode.description || category.description,
            input: inputText,
            output: outputText,
            save_to: saveTo,
            condition,
          },
        })

        workingFiles = updated.files
        workingGraph = updated.graph
        lastResult = updated
        previousNode = updated.graph.nodes.find((node) => node.id === updated.node_id) || previousNode
      }

      const draftEdges = Array.isArray(draftData.edges) ? draftData.edges : []
      const resolveEdgeNode = (value: any) => {
        const key = String(value || '')
        return idMap.get(key) || (workingGraph?.nodes.find((node) => node.id === key)?.id ?? '')
      }
      const mappedEdges = draftEdges
        .map((edge: any) => {
          const source = resolveEdgeNode(edge.source || edge.from || edge.source_id || edge.sourceId)
          const target = resolveEdgeNode(edge.target || edge.to || edge.target_id || edge.targetId)
          if (!source || !target || source === target) return null
          return {
            source,
            target,
            label: edge.label || edge.condition || edge.name || '',
          }
        })
        .filter(Boolean) as Array<{ source: string; target: string; label: string }>

      if (mappedEdges.length && workingGraph) {
        const createdSet = new Set(createdNodeIds)
        const existingEdges = Array.isArray((workingGraph as any).edges) ? [...(workingGraph as any).edges] : []
        const mergedEdges = existingEdges.filter((edge: any) => {
          const source = edge.source || edge.from
          const target = edge.target || edge.to
          return !(createdSet.has(source) && createdSet.has(target))
        })
        mappedEdges.forEach((edge) => {
          const exists = mergedEdges.some((item: any) => (
            (item.source || item.from) === edge.source
            && (item.target || item.to) === edge.target
            && (item.label || '') === edge.label
          ))
          if (!exists) mergedEdges.push({ from: edge.source, to: edge.target, scope: edge.label ? 'branch' : 'root', ...(edge.label ? { label: edge.label } : {}) })
        })
        lastResult = await saveFlowEdges(flowId, workingFiles, mergedEdges as any)
        workingFiles = lastResult.files
      }

      if (lastResult) {
        lastResult = await autoAlignResult(lastResult)
        const node = lastResult.graph.nodes.find((item) => item.id === lastResult?.node_id) || previousNode
        if (node) selectNode(node)
      }
      showToast({ title: 'AI 草稿已应用', type: 'success' })
      return { createdNodeIds }
    } catch (e: any) {
      showToast({ title: '应用草稿失败', description: e.message, type: 'error' })
      throw e
    }
  }, [autoAlignResult, detail?.graph, files, flowId, mcpTools, selectedNode, selectNode])

  const applyAssistantGraphOps = useCallback(async (ops: FlowAssistantGraphOps): Promise<FlowAssistantApplyResult> => {
    const deleteIds = new Set<string>()
    ops.operations.forEach((operation) => {
      if (operation.op !== 'delete_nodes') return
      if (operation.target === 'unlocked') {
        detail?.graph.nodes.forEach((node) => {
          if (!node.locked) deleteIds.add(node.id)
        })
      }
      operation.node_ids?.forEach((nodeId) => {
        const node = detail?.graph.nodes.find((item) => item.id === nodeId)
        if (node && !node.locked) deleteIds.add(node.id)
      })
    })

    const nodeIds = [...deleteIds]
    if (!nodeIds.length) {
      showToast({ title: '没有可删除的节点', type: 'info' })
      return { createdNodeIds: [], deletedNodeIds: [] }
    }

    let workingFiles = files
    let lastResult: GraphResult | null = null
    const snapshotFiles = { ...files }
    try {
      for (const nodeId of nodeIds) {
        lastResult = await deleteFlowNode(flowId, nodeId, workingFiles)
        workingFiles = lastResult.files
      }
      if (lastResult) {
        lastResult = await autoAlignResult(lastResult)
        setSelectedNode(null)
        setDrawerOpen(false)
      }
      showToast({ title: `已删除 ${nodeIds.length} 个节点`, type: 'success' })
      return { createdNodeIds: [], deletedNodeIds: nodeIds, snapshotFiles }
    } catch (e: any) {
      showToast({ title: '执行操作失败', description: e.message, type: 'error' })
      throw e
    }
  }, [autoAlignResult, detail?.graph.nodes, files, flowId])

  const undoAssistantDraft = useCallback(async (result: FlowAssistantApplyResult) => {
    if (result.snapshotFiles) {
      try {
        await Promise.all(Object.entries(result.snapshotFiles).map(([fileType, content]) => saveLabFlowFile(flowId, fileType, String(content ?? ''))))
        await load()
        showToast({ title: '已撤销本次操作', type: 'success' })
      } catch (e: any) {
        showToast({ title: '撤销失败', description: e.message, type: 'error' })
        throw e
      }
      return
    }

    if (!result.createdNodeIds.length) return
    let workingFiles = files
    let lastResult: GraphResult | null = null
    try {
      for (const nodeId of [...result.createdNodeIds].reverse()) {
        lastResult = await deleteFlowNode(flowId, nodeId, workingFiles)
        workingFiles = lastResult.files
      }
      if (lastResult) {
        updateGraphResult(lastResult)
        setSelectedNode(null)
        setDrawerOpen(false)
      }
      showToast({ title: '已撤销本次 AI 应用', type: 'success' })
    } catch (e: any) {
      showToast({ title: '撤销失败', description: e.message, type: 'error' })
      throw e
    }
  }, [files, flowId, load, updateGraphResult])

  const createCategoryNode = useCallback(async (sourceNode: FlowNode | null, categoryId: NodeCategoryId, insertMode: 'insert' | 'branch') => {
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
      const presetId = category.id === 'custom' ? 'blank' : getPreset(category.id).id
      const presetConfig = buildPresetConfig({}, category.id, presetId, nodeId, 0)
      const outputText = firstText(presetConfig.output_name, presetConfig.path, presetConfig.key)
      const toolSpecs = buildToolSpecs(category.id, presetId, presetConfig, '', outputText, undefined, mcpTools, {})
      const protocolPatch = buildProtocolPatch(category.id, presetId, presetConfig, toolSpecs, mcpTools, {}, outputText)
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
      updateGraphResult(updated)
      const node = updated.graph.nodes.find((item) => item.id === updated.node_id)
      if (node) selectNode(node)
      showToast({ title: `${category.shortLabel}节点已新增`, type: 'success' })
    } catch (e: any) {
      showToast({ title: '新增失败', description: e.message, type: 'error' })
    }
  }, [files, flowId, mcpTools, selectNode, updateGraphResult])

  const syncMcpResult = useCallback((result: { mcp_tools: McpTool[]; files: FlowFiles }) => {
    setMcpTools(result.mcp_tools || [])
    setFiles(result.files || {})
    setDetail((prev) => prev ? {
      ...prev,
      cartridge: {
        ...prev.cartridge,
        mcp_tools: result.mcp_tools || [],
        manifest: {
          ...(prev.cartridge.manifest || {}),
          mcp_tools: result.mcp_tools || [],
        },
      },
    } : prev)
  }, [])

  const bindMcpToolToSelectedNode = useCallback(async (tool: McpTool) => {
    if (!selectedNode) return
    const params = selectedNode.params || {}
    const output = params.output || params.preset_config?.output_name || `${selectedNode.id}_tool_result`
    const presetConfig = {
      ...(params.preset_config || {}),
      mcp_tool_id: tool.id,
      server: tool.server,
      tool: tool.tool,
      output_name: output,
    }
    const toolSpecs = [{
      type: tool.type || 'builtin',
      server: tool.server,
      tool: tool.tool,
      params: tool.default_params || {},
      enabled: tool.enabled !== false,
      output,
      mcp_tool_id: tool.id,
    }]
    const protocolPatch = buildProtocolPatch('tool', 'mcp_call', presetConfig, toolSpecs, [tool], {}, output)
    const updated = await updateFlowNode(flowId, selectedNode.id, {
      files,
      ...protocolPatch,
      tools: toolSpecs,
      params: {
        ...params,
        node_category: 'tool',
        preset: 'mcp_call',
        preset_config: presetConfig,
        input: params.input || '',
        output,
      },
    })
    updateGraphResult(updated)
    const node = updated.graph.nodes.find((item) => item.id === updated.node_id)
    if (node) selectNode(node)
    showToast({ title: `已绑定 ${tool.name || tool.id}`, type: 'success' })
  }, [files, flowId, selectedNode, selectNode, updateGraphResult])

  if (loading) return <Box p={6}><Spinner /></Box>
  if (error) {
    return (
      <Box p={6}>
        <Text color="fg.error">{error}</Text>
        <Button className="cf-outline-btn" mt={4} onClick={onBack}>返回</Button>
      </Box>
    )
  }
  if (!detail) return null

  return (
    <Box className={`cf-page cf-workbench-page ${mode === 'run' ? 'cf-node-mode cf-testbench-mode' : ''}`}>
      <Box className="cf-page-inner cf-workbench-inner">
        <WorkbenchHeader
          detail={detail}
          tags={tags}
          mode={mode}
          onBack={onBack}
          onModeChange={changeMode}
          onCloneToDev={cloneReadonlyToDev}
          cloningToDev={cloningToDev}
        />

        {mode === 'design' && (
          <div className="cf-workbench-design-shell">
            {editable && (
              <>
                <button type="button" className="cf-mcp-floating-trigger" onClick={() => setMcpLibraryOpen(true)}>
                  <span>MCP 工具库</span>
                  <b>{mcpTools.length}</b>
                </button>
                {mcpLibraryOpen && (
                  <div className="cf-mcp-drawer-backdrop" onClick={() => setMcpLibraryOpen(false)}>
                    <aside className="cf-mcp-drawer" onClick={(event) => event.stopPropagation()}>
                      <div className="cf-mcp-drawer-top">
                        <div>
                          <Text className="cf-kicker">MCP Library</Text>
                          <strong>MCP 工具库</strong>
                        </div>
                        <button type="button" onClick={() => setMcpLibraryOpen(false)}>关闭</button>
                      </div>
                      <McpLibraryPanel
                        tools={mcpTools}
                        selectedNode={selectedNode}
                        files={files}
                        onCreate={async (tool) => {
                          const result = await createMcpTool(flowId, tool)
                          syncMcpResult(result)
                          showToast({ title: 'MCP 工具已新增', type: 'success' })
                        }}
                        onUpdate={async (toolId, tool) => {
                          const result = await updateMcpTool(flowId, toolId, tool)
                          syncMcpResult(result)
                          showToast({ title: 'MCP 工具已保存', type: 'success' })
                        }}
                        onDelete={async (toolId) => {
                          const result = await deleteMcpTool(flowId, toolId)
                          syncMcpResult(result)
                          showToast({ title: 'MCP 工具已删除', type: 'success' })
                        }}
                        onBindToNode={bindMcpToolToSelectedNode}
                      />
                    </aside>
                  </div>
                )}
              </>
            )}
            <DesignView
            graph={detail.graph}
            editable={editable}
            files={files}
            flowId={flowId}
            selectedNode={selectedNode}
            focusNodeId={focusNodeId}
            drawerOpen={drawerOpen}
            onSelectNode={selectNode}
            onCloseDrawer={() => setDrawerOpen(false)}
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
            onApplyAssistantDraft={applyAssistantDraft}
            onApplyAssistantGraphOps={applyAssistantGraphOps}
            onUndoAssistantDraft={undoAssistantDraft}
            onDeleteNode={async (node) => {
              const result = await deleteFlowNode(flowId, node.id, files)
              updateGraphResult(result)
              setSelectedNode(null)
              setDrawerOpen(false)
              showToast({ title: '节点已删除', type: 'success' })
            }}
            onSaved={(result) => {
              updateGraphResult(result)
              const node = result.graph.nodes.find((item) => item.id === result.node_id)
              if (node) selectNode(node)
              showToast({ title: '节点已保存', type: 'success' })
            }}
          />
          </div>
        )}

        {mode === 'run' && (
          <RunView
            detail={detail}
            runs={runs}
            events={events}
            onManageMcp={() => {
              setMode('design')
              setMcpLibraryOpen(true)
            }}
            onTestRun={async (inputs: Record<string, string>, probeRange?: TestProbeRange, _mode?: 'full' | 'probe', testMode?: Record<string, any>) => {
              setRuns([])
              setEvents([])
              try {
                const result = await testRunFlow(flowId, inputs, probeRange, testMode)
                setRuns([result.run])
                setEvents(result.events || [])
                let latest = result.run
                for (let attempt = 0; attempt < 900; attempt++) {
                  await sleep(800)
                  let runData: RunResult
                  let eventData: { items: FlowEvent[] }
                  try {
                    ;[runData, eventData] = await Promise.all([
                      fetchCartridgeRun(result.run.run_id),
                      fetchCartridgeRunEvents(result.run.run_id),
                    ])
                  } catch (pollError) {
                    if (attempt < 10) continue
                    throw pollError
                  }
                  latest = runData
                  setRuns([runData])
                  setEvents(eventData.items || [])
                  if (['completed', 'failed', 'cancelled', 'paused_waiting_user'].includes(runData.status)) break
                }
                showToast({
                  title: latest.status === 'paused_waiting_user'
                    ? '运行暂停，等待用户补充信息'
                    : latest.status === 'failed'
                      ? '测试运行发现失败节点'
                      : '测试运行完成',
                  type: latest.status === 'failed' ? 'error' : 'success',
                })
              } catch (e: any) {
                showToast({ title: '测试失败', description: e.message, type: 'error' })
              }
            }}
            onAnswerPendingInteraction={async (runId: string, values: Record<string, any>) => {
              try {
                let answerSettled = false
                let liveLatest: RunResult | null = null
                const answerPromise = answerPendingInteraction(runId, values)
                  .finally(() => {
                    answerSettled = true
                  })
                while (!answerSettled) {
                  await sleep(800)
                  try {
                    const [runData, eventData] = await Promise.all([
                      fetchCartridgeRun(runId),
                      fetchCartridgeRunEvents(runId),
                    ])
                    liveLatest = runData
                    setRuns([runData])
                    setEvents(eventData.items || [])
                  } catch {
                    // The answer request may still be updating run files.
                  }
                }
                const result = await answerPromise
                setRuns([result.run])
                setEvents(result.events || [])
                const latest = await pollRunUntilStable(runId) || liveLatest || result.run
                showToast({
                  title: latest.status === 'paused_waiting_user'
                    ? '流程再次暂停，等待补充信息'
                    : latest.status === 'failed'
                      ? '恢复运行后发现失败节点'
                      : '已提交信息并继续运行',
                  type: latest.status === 'failed' ? 'error' : 'success',
                })
              } catch (e: any) {
                showToast({ title: '提交补充信息失败', description: e.message, type: 'error' })
              }
            }}
            onRefresh={async () => {
              try {
                const data = await fetchLabFlowRuns(flowId)
                setRuns(data.items || [])
                setEvents(data.latest_run_events || [])
              } catch (e: any) {
                showToast({ title: '刷新失败', description: e.message, type: 'error' })
              }
            }}
          />
        )}
      </Box>
    </Box>
  )
}
