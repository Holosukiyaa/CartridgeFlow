import type { McpTool } from '../../api.ts'
import { PROCESS_KIND_LABELS, formatProcessDisplayLabel, getPreset, getProtocolDefaults } from './nodeModel.ts'
import type { NodeCategoryId } from './types.ts'

export const firstText = (...values: any[]) => values.find((value) => typeof value === 'string' && value.trim())?.trim() || ''
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

export function buildPresetConfig(draftNode: any, categoryId: NodeCategoryId, presetId: string, baseId: string, index: number) {
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

export function buildToolSpecs(categoryId: NodeCategoryId, presetId: string, presetConfig: Record<string, string>, inputText: string, outputText: string, draftTools?: any, mcpTools: McpTool[] = [], draftNode?: any) {
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

export function buildProtocolPatch(categoryId: NodeCategoryId, presetId: string, presetConfig: Record<string, string>, toolSpecs: any, mcpTools: McpTool[], draftNode: any = {}, outputText = '') {
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


