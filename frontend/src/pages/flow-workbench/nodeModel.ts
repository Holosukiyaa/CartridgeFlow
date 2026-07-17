import dagre from '@dagrejs/dagre'
import type { FlowGraph, FlowNode } from '../../api.ts'
import type { NodeCategory, NodeDraft, NodePreset, NodeCategoryId } from './types.ts'

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
    description: '负责收集要用的信息，例如用户需求、项目文件、日志或网页内容。',
    examples: ['用户输入', '项目扫描', '文件读取', '日志导入'],
    color: '#3f7f62',
    bg: '#edf8ef',
  },
  {
    id: 'ui',
    label: '展示节点',
    shortLabel: '展示',
    templateId: 'welcome',
    defaultType: 'process',
    defaultAction: 'show_ui',
    defaultTitle: '展示节点',
    description: '负责展示欢迎页、结果页、HTML/Markdown 预览或中间交互界面，不承担数据存储职责。',
    examples: ['欢迎页', '结果展示', 'HTML 预览', 'Markdown 报告'],
    color: '#8b4fb3',
    bg: '#f7efff',
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
    description: '负责按协议调用文件、网络、MCP 或外部系统；读取类能力会标记为 MCP读取节点，副作用能力会标记为 MCP执行节点。',
    examples: ['读取文件', '写入文件', '调用 MCP', '执行外部能力'],
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
    description: '负责调用不能随卡带离线打包的远端服务，例如另一台 GPU 机器上的 ComfyUI、Krea、Runway 或专用渲染服务。',
    examples: ['ComfyUI', '远端 GPU', '云渲染', '外部生成服务'],
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
    description: '负责把结果送到需要它的地方，也可以拆分、合并、筛选和分发。',
    examples: ['传递结果', '拆分内容', '合并内容', '分发结果'],
    color: '#2f7f77',
    bg: '#eefaf8',
  },
  {
    id: 'store',
    label: '交付节点',
    shortLabel: '交付',
    templateId: 'runtime',
    defaultType: 'process',
    defaultAction: 'save_context',
    defaultTitle: '交付节点',
    description: '负责保存中间结果、上下文、草稿、运行记录或最终产物。',
    examples: ['上下文存放', '结果缓存', '项目摘要', '产物保存'],
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
    description: '负责决定下一步怎么走，例如确认、检查、分支、重试或结束。',
    examples: ['人工确认', '条件判断', '结果检查', '错误回流'],
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
  ui: 'ui',
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
  ui: {
    type: 'process',
    kind: 'ui',
    executor: 'deterministic',
    effect: 'writes_store',
    action: 'show_ui',
    displaySuffix: '展示',
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
    { id: 'scan_project', label: '扫描项目', description: '生成项目结构或上下文。', fields: [{ key: 'scope', label: '扫描范围', placeholder: 'frontend/src' }, { key: 'output_name', label: '输出名称', placeholder: 'project_map' }] },
    { id: 'import_log', label: '导入日志', description: '导入错误日志或运行输出。', fields: [{ key: 'source', label: '日志来源', placeholder: '终端输出 / 文件路径', multiline: true }, { key: 'output_name', label: '输出名称', placeholder: 'error_log' }] },
  ],
  ui: [
    { id: 'welcome', label: '欢迎页', description: '展示卡带启动时的欢迎 HTML。', fields: [{ key: 'path', label: 'HTML 路径', placeholder: 'assets/welcome.html' }, { key: 'output_name', label: '输出名称', placeholder: 'welcome_ui' }] },
    { id: 'html_view', label: 'HTML 展示', description: '在流程中展示指定 HTML 文件或内联 HTML。', fields: [{ key: 'path', label: 'HTML 路径', placeholder: 'assets/result.html' }, { key: 'output_name', label: '输出名称', placeholder: 'html_view' }] },
    { id: 'markdown_view', label: 'Markdown 结果', description: '读取上游结果并以 Markdown 方式展示。', fields: [{ key: 'source', label: '展示数据来源', placeholder: 'final_summary' }, { key: 'output_name', label: '输出名称', placeholder: 'result_ui' }] },
  ],
  process: [
    { id: 'analyze', label: '分析信息', description: '分析输入内容并给出结构化结论。', fields: [{ key: 'goal', label: '分析目标', placeholder: '分析用户需求和风险', multiline: true }, { key: 'output_name', label: '输出名称', placeholder: 'requirement_analysis' }] },
    { id: 'generate', label: '生成内容', description: '根据输入生成文本、方案或代码。', fields: [{ key: 'target', label: '生成什么？', placeholder: '实现计划 / 文档 / 代码草案' }, { key: 'format', label: '格式要求', placeholder: 'Markdown / JSON / patch' }] },
    { id: 'modify', label: '修改内容', description: '根据要求修改已有内容。', fields: [{ key: 'change_goal', label: '修改目标', placeholder: '优化文案、调整代码、补充说明', multiline: true }, { key: 'output_name', label: '输出名称', placeholder: 'modified_result' }] },
    { id: 'convert', label: '转换格式', description: '把一种格式转换为另一种格式。', fields: [{ key: 'from_to', label: '转换规则', placeholder: 'raw_text -> structured_json' }, { key: 'output_name', label: '输出名称', placeholder: 'structured_result' }] },
    { id: 'summarize', label: '总结内容', description: '压缩长内容，提取重点。', fields: [{ key: 'focus', label: '总结重点', placeholder: '结论、风险、待办', multiline: true }, { key: 'output_name', label: '输出名称', placeholder: 'summary' }] },
  ],
  tool: [
    { id: 'filesystem_read', label: '读取文件', description: '读取工作区内指定文件，把内容写入 context.store。', fields: [{ key: 'path', label: '文件路径', placeholder: 'test_output/analysis.txt' }, { key: 'output_name', label: '输出名称', placeholder: 'file_content' }] },
    { id: 'filesystem_write', label: '写入文件', description: '把上游内容或固定内容写入工作区文件。', fields: [{ key: 'path', label: '文件路径', placeholder: 'test_output/analysis.txt' }, { key: 'source', label: '写入内容来源', placeholder: 'analysis_result' }, { key: 'output_name', label: '输出名称', placeholder: 'file_write_result' }] },
    { id: 'filesystem_list', label: '列出目录', description: '列出工作区内指定目录。', fields: [{ key: 'path', label: '目录路径', placeholder: '.' }, { key: 'output_name', label: '输出名称', placeholder: 'dir_entries' }] },
    { id: 'mcp_call', label: 'MCP 调用', description: '声明一个 MCP 或内置工具调用。', fields: [{ key: 'server', label: '服务', placeholder: 'filesystem' }, { key: 'tool', label: '工具', placeholder: 'read_file' }, { key: 'output_name', label: '输出名称', placeholder: 'tool_result' }] },
  ],
  remote: [
    { id: 'comfyui_keyframe_upgrade', label: 'ComfyUI 升级', description: '把 Godot 渲染包送入远端 ComfyUI，生成关键帧升级包和 QC 报告。', fields: [{ key: 'service', label: '远程服务', placeholder: 'comfyui' }, { key: 'server', label: 'MCP 服务', placeholder: 'media' }, { key: 'tool', label: '工具模板', placeholder: 'remote_upgrade_keyframes' }, { key: 'output_name', label: '输出名称', placeholder: 'comfy_upgrade_bundle' }] },
    { id: 'remote_mcp_call', label: '远程 MCP 调用', description: '声明一个需要网络或专用远端机器的 MCP 调用。', fields: [{ key: 'service', label: '远程服务', placeholder: 'comfyui / krea / runway' }, { key: 'server', label: 'MCP 服务', placeholder: 'media' }, { key: 'tool', label: '工具模板', placeholder: 'remote_upgrade_keyframes' }, { key: 'output_name', label: '输出名称', placeholder: 'remote_result' }] },
  ],
  transfer: [
    { id: 'pass', label: '直接传递', description: '把上游结果直接交给下游。', fields: [{ key: 'from', label: '来源', placeholder: 'analysis' }, { key: 'to', label: '目标', placeholder: 'planner.input' }] },
    { id: 'map', label: '字段对应', description: '把字段重新对应到下游需要的名字。', fields: [{ key: 'mapping', label: '对应关系', placeholder: 'files -> target_files\nreason -> change_reason', multiline: true }] },
    { id: 'merge', label: '合并结果', description: '把多个结果合成一个上下文包。', fields: [{ key: 'items', label: '要合并的内容', placeholder: 'analysis, project_map, user_request', multiline: true }, { key: 'output_name', label: '输出名称', placeholder: 'context_pack' }] },
    { id: 'split', label: '拆分结果', description: '把一个结果拆成多个部分。', fields: [{ key: 'rule', label: '拆分规则', placeholder: '按章节 / 字段 / 类型拆分', multiline: true }] },
  ],
  store: [
    { id: 'context', label: '保存到上下文', description: '保存为后续节点可读取的上下文。', fields: [{ key: 'key', label: '保存名称', placeholder: 'context.plan' }, { key: 'source', label: '保存对象', placeholder: 'implementation_plan' }] },
    { id: 'artifact', label: '保存为文件', description: '生成可预览或交付的文件。', fields: [{ key: 'path', label: '文件名', placeholder: 'plan.md' }, { key: 'format', label: '格式', placeholder: 'markdown / html / json' }] },
    { id: 'cache', label: '临时缓存', description: '暂存中间结果，供本次运行使用。', fields: [{ key: 'key', label: '缓存名称', placeholder: 'cache.project_map' }, { key: 'ttl', label: '保留方式', placeholder: '本次运行 / 长期' }] },
    { id: 'draft', label: '保存草稿', description: '保存尚未最终确认的内容。', fields: [{ key: 'name', label: '草稿名称', placeholder: 'draft.plan' }, { key: 'source', label: '草稿内容', placeholder: 'generated_plan' }] },
  ],
  control: [
    { id: 'confirm', label: '人工确认', description: '暂停流程，等待用户确认。', fields: [{ key: 'message', label: '确认文案', placeholder: '是否继续执行下一步？', multiline: true }, { key: 'on_cancel', label: '取消后去哪里', placeholder: 'stop / revise' }] },
    { id: 'condition', label: '条件判断', description: '根据条件决定下一步。', fields: [{ key: 'condition', label: '判断条件', placeholder: 'test_result.status == passed' }, { key: 'on_fail', label: '不满足时去哪里', placeholder: 'debug_node' }] },
    { id: 'test_check', label: '测试判定', description: '根据测试结果决定通过或回流。', fields: [{ key: 'pass_to', label: '通过后', placeholder: 'artifact_node' }, { key: 'fail_to', label: '失败后', placeholder: 'fix_node' }] },
    { id: 'risk_check', label: '风险检查', description: '根据风险等级决定是否需要人工确认。', fields: [{ key: 'risk_rule', label: '风险规则', placeholder: '涉及写文件或运行命令时需要确认', multiline: true }] },
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
  if (node?.action === 'show_welcome' || node?.action === 'show_ui' || node?.action === 'render_ui' || node?.action === 'show_result') return CATEGORY_BY_ID.get('ui')!
  if (node?.template_id === 'input' || node?.action === 'collect_inputs') return CATEGORY_BY_ID.get('input')!
  if (node?.action === 'remote_call' || node?.params?.node_category === 'remote') return CATEGORY_BY_ID.get('remote')!
  if (node?.action === 'tool_call' || node?.params?.node_category === 'tool') return CATEGORY_BY_ID.get('tool')!
  if (node?.template_id === 'checkpoint' || node?.type === 'user_gate' || node?.action?.includes('confirm')) return CATEGORY_BY_ID.get('control')!
  if (node?.action?.includes('save') || node?.action?.includes('artifact') || node?.action?.includes('cache')) return CATEGORY_BY_ID.get('store')!
  if (node?.action?.includes('pass') || node?.action?.includes('route') || node?.action?.includes('merge') || node?.action?.includes('split')) return CATEGORY_BY_ID.get('transfer')!
  return CATEGORY_BY_ID.get('process')!
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
    output: params.output || params.target || '',
    saveTo: params.save_to || params.store_key || params.artifact_name || '',
    condition: params.condition || params.message || '',
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
  const mockDecisionEnvelope = parseJsonOrEmpty(draft.mockDecisionEnvelope, null)
  return {
    type: 'process',
    action: draft.action || defaults.action,
    kind,
    executor: draft.executor || defaults.executor,
    effect: draft.effect || defaults.effect,
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
    decision_test_mode: draft.decisionTestMode || '',
    mock_decision_envelope: kind === 'decision' && (draft.executor || defaults.executor) === 'llm'
      ? (mockDecisionEnvelope && typeof mockDecisionEnvelope === 'object' ? mockDecisionEnvelope : {})
      : null,
    primary_output: draft.primaryOutput || draft.output || draft.presetConfig.output_name || null,
    tool_binding: draft.toolBinding || defaults.toolBinding || null,
    allowed_tools: allowedTools.length ? allowedTools : null,
    mcp_binding: Object.keys(mcpBinding || {}).length ? mcpBinding : null,
    failure_policy: draft.failurePolicy || defaults.failurePolicy || null,
    permission: draft.permission || defaults.permission || null,
    audit_log: draft.auditLog || defaults.auditLog || null,
  }
}

export function isStartNode(node?: FlowNode, nodeId?: string) {
  return nodeId === 'start' || node?.id === 'start' || node?.action === 'start' || node?.data?.action === 'start'
}

function resolveLayoutCollisions(layout: Record<string, { x: number; y: number }>, options: { rowGap?: number; xTolerance?: number } = {}) {
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
        if (layout[nodeId].y - layout[previous].y < rowGap) {
          layout[nodeId] = { ...layout[nodeId], y: layout[previous].y + rowGap }
        }
      })
  })
  return layout
}

function getExecutionOrder(graph: FlowGraph): FlowNode[] {
  const nodes = graph.nodes || []
  const byId = new Map(nodes.map((node) => [node.id, node]))
  const nextBySource = new Map<string, string>()

  ;(graph.edges || []).forEach((edge) => {
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

export function buildBalancedLayout(graph: FlowGraph): Record<string, { x: number; y: number }> {
  const layout: Record<string, { x: number; y: number }> = {}
  graph.nodes.forEach((node, index) => {
    const saved = node.data?.layout || node.params?.layout
    layout[node.id] = saved && typeof saved.x === 'number' && typeof saved.y === 'number'
      ? { x: saved.x, y: saved.y }
      : { x: 60 + index * 260, y: 120 }
  })
  return resolveLayoutCollisions(layout)
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
  ;(graph.edges || []).forEach((edge) => {
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

export function buildAutoAlignLayout(graph: FlowGraph): Record<string, { x: number; y: number }> {
  const layoutGraph = new dagre.graphlib.Graph()
  layoutGraph.setDefaultEdgeLabel(() => ({}))
  layoutGraph.setGraph({
    rankdir: 'LR',
    align: 'UL',
    nodesep: 80,
    ranksep: 86,
    edgesep: 36,
    marginx: 60,
    marginy: 120,
  })

  const nodeWidth = 220
  const nodeHeight = 104
  const nodes = graph.nodes || []
  const nodeIds = new Set(nodes.map((node) => node.id))

  nodes.forEach((node) => {
    layoutGraph.setNode(node.id, { width: nodeWidth, height: nodeHeight })
  })

  ;(graph.edges || []).forEach((edge) => {
    if (!edge.from || !edge.to || edge.from === edge.to) return
    if (!nodeIds.has(edge.from) || !nodeIds.has(edge.to)) return
    layoutGraph.setEdge(edge.from, edge.to)
  })

  dagre.layout(layoutGraph)

  const layout: Record<string, { x: number; y: number }> = {}
  nodes.forEach((node) => {
    const point = layoutGraph.node(node.id)
    layout[node.id] = point
      ? { x: Math.round(point.x - nodeWidth / 2), y: Math.round(point.y - nodeHeight / 2) }
      : { x: node.x, y: node.y }
  })

  return resolveLayoutCollisions(layout, { rowGap: 180, xTolerance: 210 })
}
