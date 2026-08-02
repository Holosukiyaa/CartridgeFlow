import dagre from '@dagrejs/dagre'
import type { FlowEdge, FlowGraph, FlowNode } from '../../api.ts'
import type { NodeCategory, NodeDraft, NodePreset, NodeCategoryId } from './types.ts'

export type FlowNodeViewMode = 'engineering' | 'detailed' | 'compact'

export const FLOW_NODE_DIMENSIONS: Record<FlowNodeViewMode, { width: number; height: number }> = {
  engineering: { width: 334, height: 600 },
  detailed: { width: 440, height: 436 },
  compact: { width: 280, height: 146 },
}

export type FlowNodeDimensions = { width: number; height: number }

type FlowLayoutOptions = {
  viewMode?: FlowNodeViewMode
  nodeDimensions?: Record<string, FlowNodeDimensions>
  force?: boolean
}

function countEntries(value: unknown) {
  return value && typeof value === 'object' && !Array.isArray(value) ? Object.keys(value).length : 0
}

const ENGINEERING_RESOURCE_PREFIX = '__engineering_resource__:'

function isEngineeringResource(node: FlowNode) {
  return node.scope === 'engineering_resource' || node.id.startsWith(ENGINEERING_RESOURCE_PREFIX)
}

function isBoundaryNodeForDimensions(node: FlowNode) {
  return node.id === 'start'
    || node.id === 'complete'
    || node.action === 'complete'
    || node.action === 'end'
}

function resourceDimensions(node: FlowNode): FlowNodeDimensions {
  const resourceType = String(node.params?.resource_type || '').toLowerCase()
  const resourceId = String(node.params?.resource_id || node.id || '')
  const titleAllowance = resourceId.length > 28 ? 20 : 0
  if (/component|ui|interaction/.test(resourceType)) return { width: 320, height: 282 + titleAllowance }
  if (/mcp|remote/.test(resourceType)) return { width: 316, height: 234 + titleAllowance }
  if (/model/.test(resourceType)) return { width: 306, height: 218 + titleAllowance }
  if (/tool/.test(resourceType)) return { width: 306, height: 224 + titleAllowance }
  return { width: 300, height: 206 + titleAllowance }
}

/**
 * Estimates the height (px) of the recipe block rendered by EngineeringNodeCard
 * (buildEngineeringRecipe). Kept local to nodeModel to avoid an import cycle
 * (engineeringNode imports nodeModel). Rules mirror buildEngineeringRecipe:
 * each item is one row (~17px) plus a title/padding base; long values wrap.
 */
function estimateEngineeringRecipeHeight(node: FlowNode): number {
  if (node.scope === 'engineering_resource') return 0
  const action = String(node.action || '')
  const params = (node.params || {}) as Record<string, unknown>
  const raw = (node.data && typeof node.data === 'object' ? node.data : {}) as Record<string, unknown>
  const wrapRows = (value: unknown) => {
    if (value == null) return 0
    const text = typeof value === 'string' ? value : JSON.stringify(value)
    // Canvas recipe values are summaries, not full prompt/source documents.
    const lines = text.split('\n').slice(0, 4)
    const rows = lines.reduce((sum, line) => sum + Math.max(1, Math.ceil(line.length / 20)), 0)
    return Math.min(4, rows)
  }
  let rows = 0
  if (action === 'llm_prompt') {
    rows += 2 // 模型角色 + 模型参数
    const system = raw.system_prompt || params.system_prompt
    const prompt = raw.prompt || params.prompt || params.target || params.format
    if (system) rows += 2
    if (prompt) rows += 3
    const contract = node.decision_contract as { consume?: { path?: string } } | undefined
    if (contract?.consume?.path) rows += 1 // 输出结构
  } else if (action === 'tool_call' || action === 'remote_call' || action === 'mcp_read') {
    const tools = [node.tool_binding, node.mcp_binding, node.allowed_tools].filter(Boolean)
    rows += 1 // 调用工具
    if (tools.length) rows += Math.ceil(String(tools[0]).length / 24)
    // 信源在节点卡上只显示数量和名称摘要，完整 URL 位于详情面板。
    const toolList = Array.isArray(params.tools) ? params.tools : []
    if (toolList.length) rows += 2
    if (params.resource_role || node.tool_binding) rows += 1 // 资源角色
    if (node.endpoint || params.endpoint) rows += 1 // 远端地址
    if (node.timeout_ms) rows += 1 // 超时
  } else if (action === 'render_video_brief') {
    rows += 2 // 语音 + 输出
  } else if (action === 'pass_result') {
    rows += 2 + wrapRows(params.items || params.input) // 合并键(可能长) + 输出键
  } else if (action === 'collect_inputs') {
    rows += 1 + wrapRows(params.fields)
    if (params.defaults) rows += 1 + wrapRows(params.defaults)
  } else if (action === 'confirm_checkpoint') {
    const interaction = params.interaction as { prompt?: string } | undefined
    rows += 1 + wrapRows(interaction?.prompt || params.message || params.title) // 审核键 + 审核提示(可长)
  } else if (action === 'collect_artifacts') {
    rows += 1 + wrapRows(params.input) + 1 // 输入来源(可长) + 交付输出
  } else {
    if (Object.keys(params).length) rows += 1 + wrapRows(params) // 参数摘要
  }
  if (rows <= 0) return 0
  return 36 + rows * 19 // title/padding base + row height (dd 11px/1.5 + dl gap)
}

export function getFlowNodeDimensions(
  node: FlowNode,
  viewMode: FlowNodeViewMode,
  _context: { incoming?: number; outgoing?: number } = {},
): FlowNodeDimensions {
  if (viewMode === 'compact') return FLOW_NODE_DIMENSIONS.compact
  if (viewMode === 'engineering' && isEngineeringResource(node)) return resourceDimensions(node)

  const inputs = countEntries(node.inputs) + countEntries(node.input_binding) + (node.input_schema ? 1 : 0)
  const outputs = countEntries(node.outputs) + (node.output || node.primary_output || node.output_contract ? 1 : 0)
  // Only input/output sections render on the engineering card (data-chain
  // ports); bindings/execution/routes/policies live in the detail panel.
  const sections = [inputs, outputs].filter(Boolean)
  const boundary = isBoundaryNodeForDimensions(node)
  // Every section and every field is shown (no hidden info) — estimate them all.
  const visibleSections = sections
  const fieldRows = visibleSections.reduce((total, count) => total + count, 0)
  const moreRows = 0

  if (viewMode === 'engineering') {
    const recipeHeight = estimateEngineeringRecipeHeight(node)
    // Guided copy block (recipe strip + what + tip) absorbed from the outcome view.
    const guidedHeight = 78
    // Conservative estimate: recipe rows wrap long values (see .cf-engineering-recipe dd),
    // sections render up to 3 field rows each. The wrapper height must fit all content.
    const height = 106 + visibleSections.length * 27 + fieldRows * 17 + moreRows * 16 + recipeHeight + guidedHeight
    return {
      width: boundary ? 292 : 334,
      height: Math.max(boundary ? 196 : 246, height),
    }
  }

  const height = 356 + (node.params?.description || node.params?.purpose ? 24 : 0)
  return {
    width: boundary ? 368 : 440,
    height: Math.max(boundary ? 240 : 388, Math.min(440, height)),
  }
}

function getFlowLayoutMetrics(options: FlowLayoutOptions = {}) {
  const viewMode = options.viewMode || 'detailed'
  const dimensions = FLOW_NODE_DIMENSIONS[viewMode]
  return {
    viewMode,
    ...dimensions,
    nodesep: viewMode === 'engineering' ? 86 : viewMode === 'detailed' ? 140 : 72,
    ranksep: viewMode === 'engineering' ? 132 : viewMode === 'detailed' ? 120 : 112,
  }
}

export const FILE_TABS = [
  { key: 'manifest', label: 'manifest.json' },
  { key: 'root_flow', label: 'root.flow.json' },
  { key: 'welcome', label: 'welcome.md' },
]

export const NODE_CATEGORIES: NodeCategory[] = [
  {
    id: 'input',
    label: '输入节点',
    shortLabel: '输入',
    templateId: 'input',
    defaultType: 'process',
    defaultAction: 'collect_inputs',
    defaultTitle: '输入节点',
    description: '负责收集用户填写的信息，或读取一个指定文件。',
    examples: ['用户填写', '文件读取'],
    color: '#c66837',
    bg: '#fff7f1',
  },
  {
    id: 'interaction',
    label: '交互节点',
    shortLabel: '交互',
    templateId: 'interaction',
    defaultType: 'process',
    defaultAction: 'render_interaction',
    defaultTitle: '交互节点',
    description: '承载卡带自己的展示、填写和审核界面。界面来自卡带资产，提交动作由底座控制。',
    examples: ['欢迎面板', '结果展示', '信息填写', '人工审核'],
    color: '#3f7f62',
    bg: '#edf8ef',
  },
  {
    id: 'process',
    label: 'AI决策节点',
    shortLabel: 'AI决策',
    templateId: 'prompt',
    defaultType: 'process',
    defaultAction: 'llm_prompt',
    defaultTitle: 'AI决策节点',
    description: '负责把已有信息变成下一步需要的结果，例如分析、总结、生成或转换。',
    examples: ['需求分析', '计划生成', '代码生成', '格式转换'],
    color: '#b8563a',
    bg: '#fff1e8',
  },
  {
    id: 'tool',
    label: 'MCP执行节点',
    shortLabel: 'MCP执行',
    templateId: 'runtime',
    defaultType: 'process',
    defaultAction: 'tool_call',
    defaultTitle: 'MCP执行节点',
    description: '负责通过工具协议读取、写入或列出工作区文件。',
    examples: ['读取文件', '写入文件', '列出目录'],
    color: '#275fae',
    bg: '#eef5ff',
  },
  {
    id: 'remote',
    label: '远程执行节点',
    shortLabel: '远程执行',
    templateId: 'remote_call',
    defaultType: 'process',
    defaultAction: 'remote_call',
    defaultTitle: '远程执行节点',
    description: '负责调用不能随卡带离线打包的远端服务，连接信息来自本机工具配置，调用配方来自卡带。',
    examples: ['远端 GPU', '内部服务', '云端 API', '外部生成服务'],
    color: '#9a3b4f',
    bg: '#fff0f3',
  },
  {
    id: 'transfer',
    label: '传递节点',
    shortLabel: '传递',
    templateId: 'runtime',
    defaultType: 'process',
    defaultAction: 'pass_result',
    defaultTitle: '传递节点',
    description: '负责直接传递、重命名或合并上游结果。',
    examples: ['直接传递', '字段对应', '合并结果'],
    color: '#2f7f77',
    bg: '#eefaf8',
  },
  {
    id: 'store',
    label: '保存节点',
    shortLabel: '保存',
    templateId: 'runtime',
    defaultType: 'process',
    defaultAction: 'save_context',
    defaultTitle: '保存节点',
    description: '把上一步结果保存到本次运行上下文，供后续节点读取。',
    examples: ['保存结果', '保存上下文'],
    color: '#7d633d',
    bg: '#fff6df',
  },
  {
    id: 'control',
    label: '门禁节点',
    shortLabel: '门禁',
    templateId: 'checkpoint',
    defaultType: 'process',
    defaultAction: 'confirm_checkpoint',
    defaultTitle: '门禁节点',
    description: '暂停流程并等待人工确认，确认后继续执行。',
    examples: ['人工确认', '交付审核'],
    color: '#77659d',
    bg: '#f3efff',
  },
  {
    id: 'custom',
    label: '自定义节点',
    shortLabel: '自定义',
    templateId: 'runtime',
    defaultType: 'process',
    defaultAction: 'custom_action',
    defaultTitle: '自定义节点',
    description: '自由度最高，适合标准预设无法表达的节点行为。',
    examples: ['完全自定义', '自定义 AI', '自定义工具', '自定义 JSON'],
    color: '#52545a',
    bg: '#f2f2f2',
  },
]

export const CATEGORY_BY_ID = new Map(NODE_CATEGORIES.map((item) => [item.id, item]))

export type ProcessKind =
  | 'input'
  | 'ui'
  | 'interaction'
  | 'decision'
  | 'retrieval'
  | 'transform'
  | 'validation'
  | 'routing'
  | 'transfer'
  | 'mcp_read'
  | 'mcp_execute'
  | 'remote_call'
  | 'gate'
  | 'human_gate'
  | 'delivery'

export type ProcessProtocolDefaults = {
  type: 'process'
  kind: ProcessKind
  executor: string
  effect: string
  action: string
  displaySuffix: string
  outputContract?: string
  decisionContract?: Record<string, any>
  inputKind?: string
  source?: string
  inputSchema?: string
  toolBinding?: string
  failurePolicy?: string
  permission?: string
  auditLog?: boolean
}

export const PROCESS_KIND_LABELS: Record<string, string> = {
  input: '输入',
  ui: '展示',
  interaction: '交互',
  decision: 'AI决策',
  retrieval: '检索',
  transform: '转换',
  validation: '校验',
  routing: '路由',
  transfer: '传递',
  mcp_read: 'MCP读取',
  mcp_execute: 'MCP执行',
  remote_call: '远程执行',
  gate: '门禁',
  human_gate: '人工确认',
  delivery: '交付',
}

const PROCESS_KIND_CATEGORY: Record<string, NodeCategoryId> = {
  input: 'input',
  ui: 'interaction',
  interaction: 'interaction',
  decision: 'process',
  retrieval: 'process',
  transform: 'process',
  validation: 'control',
  routing: 'control',
  transfer: 'transfer',
  mcp_read: 'tool',
  mcp_execute: 'tool',
  remote_call: 'remote',
  gate: 'control',
  human_gate: 'control',
  delivery: 'store',
}

const CATEGORY_PROTOCOL_DEFAULTS: Record<NodeCategoryId, ProcessProtocolDefaults> = {
  input: {
    type: 'process',
    kind: 'input',
    executor: 'user',
    effect: 'writes_store',
    action: 'collect_inputs',
    displaySuffix: '输入',
    inputKind: 'initial',
    source: 'user_form',
    inputSchema: 'input.v1',
  },
  interaction: {
    type: 'process',
    kind: 'interaction',
    executor: 'deterministic',
    effect: 'none',
    action: 'render_interaction',
    displaySuffix: '交互',
  },
  process: {
    type: 'process',
    kind: 'decision',
    executor: 'llm',
    effect: 'none',
    action: 'llm_prompt',
    displaySuffix: 'AI决策',
    outputContract: 'decision_envelope.v1',
    decisionContract: {
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
    },
  },
  tool: {
    type: 'process',
    kind: 'mcp_execute',
    executor: 'mcp',
    effect: 'writes_files',
    action: 'tool_call',
    displaySuffix: 'MCP执行',
    toolBinding: 'static_params',
    failurePolicy: 'fail_closed',
    permission: 'write_run_artifacts',
    auditLog: true,
  },
  remote: {
    type: 'process',
    kind: 'remote_call',
    executor: 'remote',
    effect: 'external_side_effect',
    action: 'remote_call',
    displaySuffix: '远程执行',
    toolBinding: 'static_params',
    failurePolicy: 'fail_closed',
    permission: 'external_service_call',
    auditLog: true,
  },
  transfer: {
    type: 'process',
    kind: 'transfer',
    executor: 'deterministic',
    effect: 'writes_store',
    action: 'pass_result',
    displaySuffix: '传递',
  },
  store: {
    type: 'process',
    kind: 'delivery',
    executor: 'deterministic',
    effect: 'writes_store',
    action: 'save_context',
    displaySuffix: '交付',
  },
  control: {
    type: 'process',
    kind: 'gate',
    executor: 'rules',
    effect: 'none',
    action: 'confirm_checkpoint',
    displaySuffix: '门禁',
    outputContract: 'gate_result.v1',
  },
  custom: {
    type: 'process',
    kind: 'transform',
    executor: 'deterministic',
    effect: 'writes_store',
    action: 'custom_action',
    displaySuffix: '自定义',
  },
}

export function getProtocolDefaults(categoryId: NodeCategoryId, presetId?: string): ProcessProtocolDefaults {
  const defaults = { ...CATEGORY_PROTOCOL_DEFAULTS[categoryId] }
  if (categoryId === 'input' && presetId === 'read_file') {
    defaults.kind = 'mcp_read'
    defaults.executor = 'mcp'
    defaults.effect = 'read_only'
    defaults.action = 'tool_call'
    defaults.displaySuffix = 'MCP读取'
    defaults.toolBinding = undefined
    defaults.permission = undefined
    defaults.failurePolicy = undefined
    defaults.auditLog = undefined
  }
  if (categoryId === 'tool' && presetId === 'filesystem_read') {
    defaults.kind = 'mcp_read'
    defaults.effect = 'read_only'
    defaults.displaySuffix = 'MCP读取'
    defaults.toolBinding = undefined
    defaults.permission = undefined
    defaults.failurePolicy = undefined
    defaults.auditLog = undefined
  }
  if (categoryId === 'tool' && presetId === 'filesystem_list') {
    defaults.kind = 'mcp_read'
    defaults.effect = 'read_only'
    defaults.displaySuffix = 'MCP读取'
    defaults.toolBinding = undefined
    defaults.permission = undefined
    defaults.failurePolicy = undefined
    defaults.auditLog = undefined
  }
  if (categoryId === 'control' && presetId === 'confirm') {
    defaults.kind = 'human_gate'
    defaults.executor = 'human'
    defaults.effect = 'writes_store'
    defaults.displaySuffix = '人工确认'
  }
  return defaults
}

function stringifyContractValue(value: any) {
  if (value === undefined || value === null) return ''
  if (typeof value === 'string') return value
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}

export function getProtocolKind(node?: FlowNode | null) {
  return String(node?.kind || node?.data?.kind || node?.params?.kind || node?.data?.params?.kind || '').trim()
}

export function getProtocolExecutor(node?: FlowNode | null) {
  return String(node?.executor || node?.data?.executor || node?.params?.executor || node?.data?.params?.executor || '').trim()
}

export function getProtocolEffect(node?: FlowNode | null) {
  return String(node?.effect || node?.data?.effect || node?.params?.effect || node?.data?.params?.effect || '').trim()
}

export function formatProcessDisplayLabel(suffix?: string) {
  const clean = String(suffix || '')
    .trim()
    .replace(/^处理节点\s*[-:：]\s*/, '')
    .replace(/^处理节点\s+/, '')
  if (!clean) return ''
  return clean.endsWith('节点') ? clean : `${clean}节点`
}

export function getProcessDisplayLabel(node?: FlowNode | null) {
  const display = node?.display || node?.data?.display || {}
  const explicit = String(display.label || '').trim()
  if (explicit) return formatProcessDisplayLabel(explicit)
  const suffix = String(display.suffix || PROCESS_KIND_LABELS[getProtocolKind(node)] || '').trim()
  if (suffix) return formatProcessDisplayLabel(suffix)
  return ''
}

export const NODE_PRESETS: Record<NodeCategoryId, NodePreset[]> = {
  input: [
    { id: 'user_form', label: '用户填写', description: '让用户提供需求、目标或约束。', fields: [{ key: 'fields', label: '需要填写什么？', placeholder: '例如：需求描述、目标用户、限制条件', multiline: true }, { key: 'output_name', label: '输出名称', placeholder: 'user_request' }] },
    { id: 'read_file', label: '读取文件', description: '读取指定文件内容。', fields: [{ key: 'path', label: '文件路径', placeholder: 'src/App.tsx' }, { key: 'output_name', label: '输出名称', placeholder: 'file_content' }] },
  ],
  interaction: [
    { id: 'display', label: '展示界面', description: '展示被动 HTML 组件，不写入运行数据。', fields: [] },
    { id: 'collect', label: '收集信息', description: '由底座表单收集输入，通过命名动作继续。', fields: [] },
    { id: 'review', label: '审核结果', description: '展示当前结果，并由底座提供通过、退回等动作。', fields: [] },
  ],
  process: [
    { id: 'analyze', label: '分析信息', description: '分析输入内容并给出结构化结论。', fields: [{ key: 'goal', label: '分析目标', placeholder: '分析用户需求和风险', multiline: true }, { key: 'output_name', label: '输出名称', placeholder: 'requirement_analysis' }] },
    { id: 'generate', label: '生成内容', description: '根据输入生成文本、方案或代码。', fields: [{ key: 'target', label: '生成什么？', placeholder: '实现计划 / 文档 / 代码草案' }, { key: 'format', label: '格式要求', placeholder: 'Markdown / JSON / patch' }, { key: 'output_name', label: '输出名称', placeholder: 'generated_content' }] },
    { id: 'modify', label: '修改内容', description: '根据要求修改已有内容。', fields: [{ key: 'change_goal', label: '修改目标', placeholder: '优化文案、调整代码、补充说明', multiline: true }, { key: 'output_name', label: '输出名称', placeholder: 'modified_result' }] },
    { id: 'convert', label: '转换格式', description: '把一种格式转换为另一种格式。', fields: [{ key: 'from_to', label: '转换规则', placeholder: 'raw_text -> structured_json' }, { key: 'output_name', label: '输出名称', placeholder: 'structured_result' }] },
    { id: 'summarize', label: '总结内容', description: '压缩长内容，提取重点。', fields: [{ key: 'focus', label: '总结重点', placeholder: '结论、风险、待办', multiline: true }, { key: 'output_name', label: '输出名称', placeholder: 'summary' }] },
  ],
  tool: [
    { id: 'filesystem_read', label: '读取文件', description: '读取工作区内指定文件，把内容写入 context.store。', fields: [{ key: 'path', label: '文件路径', placeholder: 'test_output/analysis.txt' }, { key: 'output_name', label: '输出名称', placeholder: 'file_content' }] },
    { id: 'filesystem_write', label: '写入文件', description: '把上游内容或固定内容写入工作区文件。', fields: [{ key: 'path', label: '文件路径', placeholder: 'test_output/analysis.txt' }, { key: 'source', label: '写入内容来源', placeholder: 'analysis_result' }, { key: 'output_name', label: '输出名称', placeholder: 'file_write_result' }] },
    { id: 'filesystem_list', label: '列出目录', description: '列出工作区内指定目录。', fields: [{ key: 'path', label: '目录路径', placeholder: '.' }, { key: 'output_name', label: '输出名称', placeholder: 'dir_entries' }] },
  ],
  remote: [
    { id: 'remote_mcp_call', label: '远程工具调用', description: '调用卡带 DLC 注册的远程工具；本地地址与凭据由工具配置提供。', fields: [{ key: 'service', label: '资源名称', placeholder: '例如：远程生成服务' }, { key: 'server', label: 'MCP 服务', placeholder: '由卡带 DLC 注册' }, { key: 'tool', label: '工具名称', placeholder: 'tool_name' }, { key: 'output_name', label: '输出名称', placeholder: 'remote_result' }] },
  ],
  transfer: [
    { id: 'pass', label: '直接传递', description: '把上游结果直接交给下游。', fields: [{ key: 'from', label: '来源', placeholder: 'analysis' }, { key: 'to', label: '目标', placeholder: 'planner.input' }] },
    { id: 'map', label: '字段对应', description: '把字段重新对应到下游需要的名字。', fields: [{ key: 'mapping', label: '对应关系', placeholder: 'files -> target_files\nreason -> change_reason', multiline: true }] },
    { id: 'merge', label: '合并结果', description: '把多个结果合成一个上下文包。', fields: [{ key: 'items', label: '要合并的内容', placeholder: 'analysis, project_map, user_request', multiline: true }, { key: 'output_name', label: '输出名称', placeholder: 'context_pack' }] },
  ],
  store: [
    { id: 'context', label: '保存结果', description: '保存为本次运行中后续节点可读取的内容。', fields: [{ key: 'key', label: '保存名称', placeholder: 'plan_result' }, { key: 'source', label: '保存对象', placeholder: 'implementation_plan' }] },
  ],
  control: [
    { id: 'confirm', label: '人工确认', description: '暂停流程并展示上一步结果，确认通过后继续。', fields: [{ key: 'message', label: '审核要求', placeholder: '请检查内容是否准确、完整，可以交付。', multiline: true }] },
  ],
  custom: [
    { id: 'blank', label: '完全自定义', description: '不套用标准预设，手动定义节点行为。', fields: [] },
  ],
}

export function getPresets(categoryId: NodeCategoryId) {
  return NODE_PRESETS[categoryId] || NODE_PRESETS.custom
}

export function getPreset(categoryId: NodeCategoryId, presetId?: string) {
  const presets = getPresets(categoryId)
  return presets.find((item) => item.id === presetId) || presets[0]
}

export function getNodeCategory(node?: FlowNode | null): NodeCategory {
  const kind = getProtocolKind(node)
  if (kind && PROCESS_KIND_CATEGORY[kind]) return CATEGORY_BY_ID.get(PROCESS_KIND_CATEGORY[kind])!
  const explicit = node?.params?.node_category || node?.data?.params?.node_category
  if (explicit && CATEGORY_BY_ID.has(explicit)) return CATEGORY_BY_ID.get(explicit)!
  if (node?.action === 'render_interaction' || node?.action === 'show_welcome' || node?.action === 'show_ui' || node?.action === 'render_ui' || node?.action === 'show_result') return CATEGORY_BY_ID.get('interaction')!
  if (node?.template_id === 'input' || node?.action === 'collect_inputs') return CATEGORY_BY_ID.get('input')!
  if (node?.action === 'remote_call' || node?.params?.node_category === 'remote') return CATEGORY_BY_ID.get('remote')!
  if (node?.action === 'tool_call' || node?.params?.node_category === 'tool') return CATEGORY_BY_ID.get('tool')!
  if (node?.template_id === 'checkpoint' || node?.type === 'user_gate' || node?.action?.includes('confirm')) return CATEGORY_BY_ID.get('control')!
  if (node?.action?.includes('save') || node?.action?.includes('artifact') || node?.action?.includes('cache')) return CATEGORY_BY_ID.get('store')!
  if (node?.action?.includes('pass') || node?.action?.includes('route') || node?.action?.includes('merge') || node?.action?.includes('split')) return CATEGORY_BY_ID.get('transfer')!
  return CATEGORY_BY_ID.get('process')!
}

export function isBoundaryNode(node?: FlowNode | null) {
  return Boolean(node && (
    node.id === 'start'
    || node.id === 'complete'
    || node.action === 'complete'
    || node.action === 'end'
  ))
}

export function getNodePalette(node?: FlowNode | null) {
  if (isBoundaryNode(node)) return { color: '#74818c', bg: '#f2f5f7' }
  const category = getNodeCategory(node)
  return { color: category.color, bg: category.bg }
}

export function makeNodeDraft(node: FlowNode): NodeDraft {
  const category = getNodeCategory(node)
  const params = node.params || {}
  const defaults = getProtocolDefaults(category.id, params.preset || getPreset(category.id).id)
  const kind = getProtocolKind(node) || defaults.kind
  const executor = getProtocolExecutor(node) || defaults.executor
  const effect = getProtocolEffect(node) || defaults.effect
  const display = node.display || node.data?.display || {}
  return {
    title: node.title || '',
    category: category.id,
    preset: params.preset || getPreset(category.id).id,
    presetConfig: params.preset_config || {},
    type: node.type || defaults.type,
    action: node.action || defaults.action,
    next: node.next || '',
    kind,
    executor,
    effect,
    displayName: String(node.display_name || node.title || ''),
    componentRef: String(node.component_ref || ''),
    interactionMode: String(node.interaction_mode || (category.id === 'interaction' ? 'display' : '')),
    inputBinding: stringifyContractValue(node.input_binding || {}),
    actionRoutes: stringifyContractValue(node.action_routes || {}),
    displaySuffix: String(display.suffix || PROCESS_KIND_LABELS[kind] || defaults.displaySuffix || ''),
    inputKind: String(node.input_kind || node.data?.input_kind || defaults.inputKind || ''),
    source: String(node.source || node.data?.source || defaults.source || ''),
    inputSchema: stringifyContractValue(node.input_schema || node.data?.input_schema || defaults.inputSchema || ''),
    outputContract: String(node.output_contract || node.data?.output_contract || defaults.outputContract || ''),
    decisionContract: stringifyContractValue(node.decision_contract || node.data?.decision_contract || defaults.decisionContract || ''),
    decisionTestMode: String(node.decision_test_mode || node.data?.decision_test_mode || params.decision_test_mode || ''),
    mockDecisionEnvelope: stringifyContractValue(node.mock_decision_envelope || node.data?.mock_decision_envelope || params.mock_decision_envelope || ''),
    primaryOutput: String(node.primary_output || node.data?.primary_output || params.output || params.preset_config?.output_name || ''),
    toolBinding: String(node.tool_binding || node.data?.tool_binding || defaults.toolBinding || ''),
    allowedTools: stringifyContractValue(node.allowed_tools || node.data?.allowed_tools || []),
    mcpBinding: stringifyContractValue(node.mcp_binding || node.data?.mcp_binding || {}),
    failurePolicy: String(node.failure_policy || node.data?.failure_policy || defaults.failurePolicy || ''),
    permission: String(node.permission || node.data?.permission || defaults.permission || ''),
    auditLog: Boolean(node.audit_log ?? node.data?.audit_log ?? defaults.auditLog ?? false),
    description: params.description || params.message || params.prompt || '',
    input: params.input || params.source || '',
    optionalInput: params.optional_input || params.optional_inputs || '',
    output: params.output || params.target || '',
    saveTo: params.save_to || params.store_key || params.artifact_name || '',
    condition: params.condition || params.message || '',
    endpoint: String(node.endpoint || params.endpoint || ''),
    timeoutMs: String(node.timeout_ms || params.timeout_ms || ''),
    replayPolicy: String(params.replay_policy || ''),
    idempotency: String(params.idempotency || params.idempotency_key || ''),
    artifactType: String(params.artifact_type || params.format || ''),
    deliveryPath: String(params.delivery_path || params.path || params.save_to || ''),
    agent: node.agent || '',
    modelRole: node.model_role || '',
    tools: node.tools?.length ? JSON.stringify(node.tools, null, 2) : '',
    params: Object.keys(params).length ? JSON.stringify(params, null, 2) : '',
  }
}

function parseJsonOrEmpty(value: string, fallback: any) {
  const text = String(value || '').trim()
  if (!text) return fallback
  try {
    return JSON.parse(text)
  } catch {
    return fallback
  }
}

function parseMaybeJson(value: string) {
  const text = String(value || '').trim()
  if (!text) return ''
  if (!text.startsWith('{') && !text.startsWith('[')) return text
  try {
    return JSON.parse(text)
  } catch {
    return text
  }
}

function parseAllowedTools(value: string) {
  const parsed = parseJsonOrEmpty(value, null)
  if (Array.isArray(parsed)) return parsed.map((item) => String(item)).filter(Boolean)
  return String(value || '')
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean)
}

export function buildProtocolNodePayload(draft: NodeDraft, category: NodeCategory) {
  const defaults = getProtocolDefaults(category.id, draft.preset)
  const kind = draft.kind || defaults.kind
  const displaySuffix = draft.displaySuffix || PROCESS_KIND_LABELS[kind] || defaults.displaySuffix
  const displayLabel = formatProcessDisplayLabel(displaySuffix)
  const allowedTools = parseAllowedTools(draft.allowedTools)
  const mcpBinding = parseJsonOrEmpty(draft.mcpBinding, {})
  const decisionContract = parseJsonOrEmpty(draft.decisionContract, defaults.decisionContract || null)
  const inputBinding = parseJsonOrEmpty(draft.inputBinding, {})
  const actionRoutes = parseJsonOrEmpty(draft.actionRoutes, {})
  return {
    type: 'process',
    action: draft.action || defaults.action,
    kind,
    executor: draft.executor || defaults.executor,
    effect: draft.effect || defaults.effect,
    display_name: draft.displayName || draft.title || null,
    component_ref: kind === 'interaction' ? draft.componentRef || null : null,
    interaction_mode: kind === 'interaction' ? draft.interactionMode || 'display' : null,
    input_binding: kind === 'interaction' ? inputBinding : null,
    action_routes: kind === 'interaction' ? actionRoutes : null,
    output: kind === 'interaction' && draft.interactionMode !== 'display' ? draft.output || null : null,
    display: {
      suffix: displaySuffix,
      label: displayLabel,
    },
    input_kind: draft.inputKind || defaults.inputKind || null,
    source: draft.source || defaults.source || null,
    input_schema: parseMaybeJson(draft.inputSchema || defaults.inputSchema || ''),
    output_contract: draft.outputContract || defaults.outputContract || null,
    decision_contract: kind === 'decision' && (draft.executor || defaults.executor) === 'llm'
      ? decisionContract || defaults.decisionContract || null
      : null,
    decision_test_mode: '',
    mock_decision_envelope: null,
    primary_output: draft.primaryOutput || draft.output || draft.presetConfig.output_name || null,
    tool_binding: draft.toolBinding || defaults.toolBinding || null,
    allowed_tools: allowedTools.length ? allowedTools : null,
    mcp_binding: Object.keys(mcpBinding || {}).length ? mcpBinding : null,
    failure_policy: draft.failurePolicy || defaults.failurePolicy || null,
    permission: draft.permission || defaults.permission || null,
    audit_log: draft.auditLog || defaults.auditLog || null,
    endpoint: category.id === 'remote' ? draft.endpoint || null : null,
    timeout_ms: draft.timeoutMs ? Number(draft.timeoutMs) : null,
  }
}

export function isStartNode(node?: FlowNode, nodeId?: string) {
  return nodeId === 'start' || node?.id === 'start' || node?.action === 'start' || node?.data?.action === 'start'
}

function resolveLayoutCollisions(layout: Record<string, { x: number; y: number }>, options: { rowGap?: number; xTolerance?: number; nodeDimensions?: Record<string, FlowNodeDimensions> } = {}) {
  const rowGap = options.rowGap || 170
  const xTolerance = options.xTolerance || 180
  const columns: Array<{ centerX: number; nodeIds: string[] }> = []
  Object.entries(layout)
    .sort((a, b) => a[1].x - b[1].x)
    .forEach(([nodeId, point]) => {
      const column = columns.find((item) => Math.abs(point.x - item.centerX) <= xTolerance)
      if (!column) {
        columns.push({ centerX: point.x, nodeIds: [nodeId] })
        return
      }
      column.nodeIds.push(nodeId)
      column.centerX = column.nodeIds.reduce((total, id) => total + layout[id].x, 0) / column.nodeIds.length
    })
  columns.forEach(({ nodeIds }) => {
    nodeIds
      .sort((a, b) => layout[a].y - layout[b].y)
      .forEach((nodeId, index, ordered) => {
        if (index === 0) return
        const previous = ordered[index - 1]
        const requiredGap = options.nodeDimensions
          ? (options.nodeDimensions[previous]?.height || 0) + rowGap
          : rowGap
        if (layout[nodeId].y - layout[previous].y < requiredGap) {
          layout[nodeId] = { ...layout[nodeId], y: layout[previous].y + requiredGap }
        }
      })
  })
  return layout
}

function isStructuralEdge(edge?: FlowEdge) {
  return String(edge?.scope || 'root') !== 'branch'
}

function getExecutionOrder(graph: FlowGraph): FlowNode[] {
  const nodes = graph.nodes || []
  const byId = new Map(nodes.map((node) => [node.id, node]))
  const nextBySource = new Map<string, string>()

  ;(graph.edges || []).filter(isStructuralEdge).forEach((edge) => {
    if (!edge.from || !edge.to || edge.from === edge.to) return
    if (!byId.has(edge.from) || !byId.has(edge.to)) return
    if (!nextBySource.has(edge.from)) nextBySource.set(edge.from, edge.to)
  })

  const ordered: FlowNode[] = []
  const seen = new Set<string>()
  let cursor = byId.has('start') ? 'start' : nodes[0]?.id
  while (cursor && byId.has(cursor) && !seen.has(cursor)) {
    const node = byId.get(cursor)!
    ordered.push(node)
    seen.add(cursor)
    cursor = nextBySource.get(cursor) || ''
  }

  nodes.forEach((node) => {
    if (seen.has(node.id)) return
    ordered.push(node)
  })

  return ordered
}

export function buildBalancedLayout(graph: FlowGraph, options: FlowLayoutOptions = {}): Record<string, { x: number; y: number }> {
  const metrics = getFlowLayoutMetrics(options)
  const layout: Record<string, { x: number; y: number }> = {}
  let hasCompleteSavedLayout = graph.nodes.length > 0
  graph.nodes.forEach((node) => {
    const saved = node.data?.layout || node.params?.layout
    const hasSavedPosition = Boolean(saved && typeof saved.x === 'number' && typeof saved.y === 'number')
    if (!hasSavedPosition) hasCompleteSavedLayout = false
    if (hasSavedPosition) layout[node.id] = { x: saved!.x, y: saved!.y }
  })
  if (hasCompleteSavedLayout && !options.force) {
    // Saved positions may predate node-size changes (e.g. taller recipe blocks);
    // re-resolve collisions with the current estimated sizes so stacked nodes
    // don't overlap, without rewriting the user's saved coordinates.
    return resolveLayoutCollisions(layout, {
      rowGap: metrics.viewMode === 'detailed' ? 84 : 60,
      xTolerance: metrics.width + 16,
      nodeDimensions: options.nodeDimensions,
    })
  }
  const automatic = buildAutoAlignLayout(graph, options)
  if (options.force) return automatic
  graph.nodes.forEach((node) => {
    if (!layout[node.id]) layout[node.id] = automatic[node.id] || { x: node.x, y: node.y }
  })
  return resolveLayoutCollisions(layout, {
    rowGap: metrics.viewMode === 'detailed' ? 84 : 60,
    xTolerance: metrics.width + 16,
    nodeDimensions: options.nodeDimensions,
  })
}

export function buildZigzagLayout(graph: FlowGraph, options: { columns?: number } = {}): Record<string, { x: number; y: number }> {
  const columns = Math.max(3, options.columns || 7)
  const columnGap = 300
  const rowGap = 220
  const originX = 60
  const originY = 120
  const layout: Record<string, { x: number; y: number }> = {}

  getExecutionOrder(graph).forEach((node, index) => {
    const row = Math.floor(index / columns)
    const columnInRow = index % columns
    const column = row % 2 === 0 ? columnInRow : columns - columnInRow - 1
    layout[node.id] = {
      x: originX + column * columnGap,
      y: originY + row * rowGap,
    }
  })

  return resolveLayoutCollisions(layout, { rowGap: 180, xTolerance: 210 })
}

export function buildFactoryLayout(graph: FlowGraph): Record<string, { x: number; y: number }> {
  const layout: Record<string, { x: number; y: number }> = {}
  const ordered = getExecutionOrder(graph)
  const nodeById = new Map((graph.nodes || []).map((node) => [node.id, node]))
  const anchors = ordered
    .filter((node) => Boolean(node.params?.important_node || node.data?.params?.important_node))
    .sort((a, b) => Number(a.params?.milestone_order || 999) - Number(b.params?.milestone_order || 999))

  if (!anchors.length) return buildZigzagLayout(graph)

  const columnX = 260
  const columnTopY = 120
  const columnGap = 700
  const rowGap = 180
  const laneOffsets = [-70, 70, -35, 35, 0, -95, 95]
  const fanoutOffsetX = 360
  const fanoutRowGap = 190
  const compactContinueGap = 180

  const moduleByAnchor = new Map<string, FlowNode[]>()
  const outgoingBySource = new Map<string, string[]>()
  const incomingByTarget = new Map<string, string[]>()
  ordered.forEach((node) => {
    const anchorId = node.params?.module_anchor || node.data?.params?.module_anchor
    if (!anchorId || !nodeById.has(anchorId)) return
    moduleByAnchor.set(anchorId, [...(moduleByAnchor.get(anchorId) || []), node])
  })
  ;(graph.edges || []).filter(isStructuralEdge).forEach((edge) => {
    if (!edge.from || !edge.to || edge.from === edge.to) return
    outgoingBySource.set(edge.from, [...(outgoingBySource.get(edge.from) || []), edge.to])
    incomingByTarget.set(edge.to, [...(incomingByTarget.get(edge.to) || []), edge.from])
  })

  const maxModuleSize = Math.max(1, ...anchors.map((anchor) => (moduleByAnchor.get(anchor.id) || [anchor]).length))
  const columnBottomY = columnTopY + (maxModuleSize - 1) * rowGap
  const placed = new Set<string>()
  anchors.forEach((anchor, anchorIndex) => {
    const x = columnX + anchorIndex * columnGap
    const moduleNodes = moduleByAnchor.get(anchor.id) || [anchor]
    const moduleNodeIds = new Set(moduleNodes.map((node) => node.id))
    const directFanoutNodes = moduleNodes.filter((node) => node.id !== anchor.id && (outgoingBySource.get(anchor.id) || []).includes(node.id))
    if (directFanoutNodes.length >= 4) {
      const centerY = Math.round((columnTopY + columnBottomY) / 2)
      const fanoutTopY = Math.round(centerY - ((directFanoutNodes.length - 1) * fanoutRowGap) / 2)
      const fanoutBottomY = fanoutTopY + (directFanoutNodes.length - 1) * fanoutRowGap
      layout[anchor.id] = { x, y: centerY }
      placed.add(anchor.id)
      directFanoutNodes.forEach((node, nodeIndex) => {
        layout[node.id] = { x: x + fanoutOffsetX, y: fanoutTopY + nodeIndex * fanoutRowGap }
        placed.add(node.id)
      })
      const fanoutTargets = new Map<string, number>()
      directFanoutNodes.forEach((node) => {
        ;(outgoingBySource.get(node.id) || []).forEach((targetId) => {
          fanoutTargets.set(targetId, (fanoutTargets.get(targetId) || 0) + 1)
        })
      })
      const commonTargetId = [...fanoutTargets.entries()]
        .filter(([targetId, count]) => count >= 2 && !moduleNodeIds.has(targetId) && nodeById.has(targetId))
        .sort((a, b) => b[1] - a[1])[0]?.[0]
      if (commonTargetId && !placed.has(commonTargetId)) {
        layout[commonTargetId] = { x: x + columnGap, y: centerY }
        placed.add(commonTargetId)
      }
      moduleNodes
        .filter((node) => !placed.has(node.id))
        .forEach((node, nodeIndex) => {
          const laneOffset = laneOffsets[nodeIndex % laneOffsets.length]
          layout[node.id] = { x: x + fanoutOffsetX + laneOffset, y: fanoutBottomY + (nodeIndex + 1) * compactContinueGap }
          placed.add(node.id)
        })
      return
    }

    const preplacedNodes = moduleNodes.filter((node) => placed.has(node.id))
    if (preplacedNodes.length) {
      const baseNode = preplacedNodes[preplacedNodes.length - 1]
      const base = layout[baseNode.id]
      moduleNodes
        .filter((node) => !placed.has(node.id))
        .forEach((node, nodeIndex) => {
          const isImportantNode = Boolean(node.params?.important_node || node.data?.params?.important_node)
          const laneOffset = isImportantNode ? 0 : laneOffsets[(nodeIndex + 1) % laneOffsets.length]
          layout[node.id] = { x: base.x + laneOffset, y: base.y + (nodeIndex + 1) * compactContinueGap }
          placed.add(node.id)
        })
      return
    }

    const moduleStep = moduleNodes.length > 1 ? (columnBottomY - columnTopY) / (moduleNodes.length - 1) : 0
    const direction = anchorIndex % 2 === 0 ? 1 : -1
    moduleNodes.forEach((node, nodeIndex) => {
      const isBoundaryNode = nodeIndex === 0 || nodeIndex === moduleNodes.length - 1
      const isImportantNode = Boolean(node.params?.important_node || node.data?.params?.important_node)
      const laneOffset = isBoundaryNode || isImportantNode ? 0 : laneOffsets[nodeIndex % laneOffsets.length]
      const y = direction > 0
        ? columnTopY + nodeIndex * moduleStep
        : columnBottomY - nodeIndex * moduleStep
      layout[node.id] = { x: x + laneOffset, y: Math.round(y) }
      placed.add(node.id)
    })
  })

  const overflow = ordered.filter((node) => !placed.has(node.id))
  overflow.forEach((node, index) => {
    const laneOffset = laneOffsets[index % laneOffsets.length]
    layout[node.id] = { x: columnX + anchors.length * columnGap + laneOffset, y: columnTopY + index * rowGap }
  })

  return resolveLayoutCollisions(layout, { rowGap: 180, xTolerance: 210 })
}

export function buildAutoAlignLayout(graph: FlowGraph, options: FlowLayoutOptions = {}): Record<string, { x: number; y: number }> {
  const metrics = getFlowLayoutMetrics(options)
  const layoutGraph = new dagre.graphlib.Graph()
  layoutGraph.setDefaultEdgeLabel(() => ({}))
  layoutGraph.setGraph({
    rankdir: 'LR',
    align: 'UL',
    acyclicer: 'greedy',
    ranker: 'network-simplex',
    nodesep: metrics.nodesep,
    ranksep: metrics.ranksep,
    edgesep: 42,
    marginx: 60,
    marginy: 120,
  })

  const nodes = graph.nodes || []
  const nodeIds = new Set(nodes.map((node) => node.id))

  nodes.forEach((node) => {
    const dimensions = options.nodeDimensions?.[node.id] || FLOW_NODE_DIMENSIONS[metrics.viewMode]
    layoutGraph.setNode(node.id, dimensions)
  })

  ;(graph.edges || []).forEach((edge) => {
    if (!edge.from || !edge.to || edge.from === edge.to) return
    if (!nodeIds.has(edge.from) || !nodeIds.has(edge.to)) return
    const branch = !isStructuralEdge(edge)
    layoutGraph.setEdge(edge.from, edge.to, {
      minlen: 1,
      weight: branch ? 1 : 4,
    })
  })

  dagre.layout(layoutGraph)

  const layout: Record<string, { x: number; y: number }> = {}
  nodes.forEach((node) => {
    const point = layoutGraph.node(node.id)
    const dimensions = options.nodeDimensions?.[node.id] || FLOW_NODE_DIMENSIONS[metrics.viewMode]
    layout[node.id] = point
      ? { x: Math.round(point.x - dimensions.width / 2), y: Math.round(point.y - dimensions.height / 2) }
      : { x: node.x, y: node.y }
  })

  return resolveLayoutCollisions(layout, {
    rowGap: metrics.viewMode === 'detailed' ? 84 : 60,
    xTolerance: metrics.width - 30,
    nodeDimensions: options.nodeDimensions,
  })
}
