import type { FlowAnalysisFinding, FlowEdge, FlowGraph, FlowNode } from '../../api.ts'
import { getNodeCategory, getProcessDisplayLabel, getProtocolEffect, getProtocolExecutor, getProtocolKind, isStartNode } from './nodeModel.ts'
import type { NodeRunState } from './runState.ts'

type AnyRecord = Record<string, any>

export type FlowNodeField = {
  label: string
  value: string
  mono?: boolean
  tone?: 'default' | 'success' | 'warning' | 'danger'
}

export type FlowNodeSection = {
  title: string
  fields: FlowNodeField[]
}

export type OutcomeNodeRow = {
  label: string
  value: string
}

export type OutcomeNodeCardView = ReturnType<typeof buildOutcomeNodeCardView>

export type OutcomeNodeRenderModel = {
  view: OutcomeNodeCardView
}

export type NodeSemanticKind =
  | 'start'
  | 'terminal'
  | 'checkpoint'
  | 'input'
  | 'interaction'
  | 'decision'
  | 'retrieval'
  | 'mcp_read'
  | 'mcp_execute'
  | 'remote_call'
  | 'transfer'
  | 'transform'
  | 'validation'
  | 'routing'
  | 'gate'
  | 'human_gate'
  | 'delivery'
  | 'extension'

export type NodeIconKey =
  | 'start'
  | 'terminal'
  | 'checkpoint'
  | 'input'
  | 'interaction'
  | 'decision'
  | 'retrieval'
  | 'mcp_read'
  | 'mcp_execute'
  | 'remote'
  | 'transfer'
  | 'transform'
  | 'validation'
  | 'routing'
  | 'gate'
  | 'human_gate'
  | 'delivery'
  | 'extension'

export type NodeConfigIssue = {
  severity: 'blocker' | 'warning'
  code: string
  message: string
  origin: 'runtime_preflight' | 'authoring_hint'
}

export type NodePresentationContext = {
  incomingNodes?: FlowNode[]
  outgoingNodes?: FlowNode[]
  incomingEdges?: FlowEdge[]
  outgoingEdges?: FlowEdge[]
  analysisFindings?: FlowAnalysisFinding[]
}

const KIND_LABELS: Record<NodeSemanticKind, string> = {
  start: '开始节点',
  terminal: '结束节点',
  checkpoint: '系统检查点',
  input: '输入节点',
  interaction: '交互节点',
  decision: 'AI 决策节点',
  retrieval: '检索节点',
  mcp_read: '读取节点',
  mcp_execute: '工具节点',
  remote_call: '远程工具节点',
  transfer: '传递节点',
  transform: '转换节点',
  validation: '校验节点',
  routing: '路由节点',
  gate: '自动检查节点',
  human_gate: '人工确认节点',
  delivery: '保存节点',
  extension: '扩展节点',
}

const ICON_KEYS: Record<NodeSemanticKind, NodeIconKey> = {
  start: 'start',
  terminal: 'terminal',
  checkpoint: 'checkpoint',
  input: 'input',
  interaction: 'interaction',
  decision: 'decision',
  retrieval: 'retrieval',
  mcp_read: 'mcp_read',
  mcp_execute: 'mcp_execute',
  remote_call: 'remote',
  transfer: 'transfer',
  transform: 'transform',
  validation: 'validation',
  routing: 'routing',
  gate: 'gate',
  human_gate: 'human_gate',
  delivery: 'delivery',
  extension: 'extension',
}

export function compactNodeValue(value: unknown, fallback = '未声明', limit = 42) {
  if (value === undefined || value === null || value === '') return fallback
  const text = typeof value === 'string' ? value : JSON.stringify(value)
  return text.length > limit ? `${text.slice(0, limit)}...` : text
}

function sourceRecords(node: FlowNode): AnyRecord[] {
  const params = (node.params || {}) as AnyRecord
  const data = (node.data || {}) as AnyRecord
  const dataParams = (data.params || {}) as AnyRecord
  return [
    node as unknown as AnyRecord,
    params,
    (params.preset_config || {}) as AnyRecord,
    data,
    dataParams,
    (dataParams.preset_config || {}) as AnyRecord,
  ]
}

function readPath(source: AnyRecord, path: string) {
  return path.split('.').reduce<any>((value, key) => value?.[key], source)
}

export function readNodeValue(node: FlowNode, ...keys: string[]) {
  for (const key of keys) {
    for (const source of sourceRecords(node)) {
      const value = readPath(source, key)
      if (value !== undefined && value !== null && value !== '') return value
    }
  }
  return undefined
}

function configured(value: unknown) {
  if (value === undefined || value === null || value === '') return false
  if (Array.isArray(value)) return value.length > 0
  if (typeof value === 'object') return Object.keys(value as object).length > 0
  return true
}

function asList(value: unknown): string[] {
  if (Array.isArray(value)) return value.map(String).map((item) => item.trim()).filter(Boolean)
  if (typeof value === 'string') return value.split(/[,\n]/).map((item) => item.trim()).filter(Boolean)
  return []
}

function countMap(value: unknown) {
  return value && typeof value === 'object' && !Array.isArray(value) ? Object.keys(value as object).length : 0
}

function field(label: string, value: unknown, options: Pick<FlowNodeField, 'mono' | 'tone'> = {}): FlowNodeField {
  return { label, value: compactNodeValue(value), ...options }
}

function getToolSpecs(node: FlowNode) {
  const specs = Array.isArray(node.tools) ? [...node.tools] : []
  const preset = (node.params?.preset_config || {}) as AnyRecord
  if (preset.server || preset.tool || preset.mcp_tool_id) {
    specs.push({ type: 'builtin', server: preset.server, tool: preset.tool, mcp_tool_id: preset.mcp_tool_id })
  }
  return specs.filter((item) => item && typeof item === 'object') as AnyRecord[]
}

function getToolIds(node: FlowNode) {
  const declared = asList(readNodeValue(node, 'allowed_tools'))
  const bound = asList(readNodeValue(node, 'tool_binding'))
  const specs = getToolSpecs(node).map((item) => String(item.mcp_tool_id || item.tool || item.id || '')).filter(Boolean)
  return [...new Set([...declared, ...bound, ...specs])]
}

export function resolveNodeSemanticKind(node: FlowNode): NodeSemanticKind {
  if (isStartNode(node, node.id)) return 'start'
  if (node.type === 'terminal' || node.entry_kind === 'terminal') return 'terminal'

  const protocolKind = getProtocolKind(node)
  const action = String(node.action || readNodeValue(node, 'action') || '').toLowerCase()
  const type = String(node.type || '').toLowerCase()
  if ((type === 'system' || node.locked) && /checkpoint|resume|persist/.test(action)) return 'checkpoint'

  const normalized = protocolKind === 'ui' ? 'interaction' : protocolKind
  if (normalized in KIND_LABELS && normalized !== 'start' && normalized !== 'terminal' && normalized !== 'checkpoint') {
    return normalized as NodeSemanticKind
  }
  if (/collect_input|collect_brief|read_input/.test(action)) return 'input'
  if (/render|show_ui|interaction|review/.test(action)) return 'interaction'
  if (/llm|decision|prompt|agent/.test(action)) return 'decision'
  if (/retriev|search|query/.test(action)) return 'retrieval'
  if (/remote/.test(action)) return 'remote_call'
  if (/validate|check_result/.test(action)) return 'validation'
  if (/route|branch/.test(action)) return 'routing'
  if (/confirm|approve/.test(action)) return getProtocolExecutor(node) === 'human' ? 'human_gate' : 'gate'
  if (/deliver|artifact|save_result/.test(action)) return 'delivery'
  if (/transform|convert|format/.test(action)) return 'transform'
  if (/pass|transfer|map_result/.test(action)) return 'transfer'
  if (/tool|mcp|file_|filesystem/.test(action)) return getProtocolEffect(node) === 'read_only' ? 'mcp_read' : 'mcp_execute'

  const category = getNodeCategory(node).id
  if (category === 'input') return 'input'
  if (category === 'interaction') return 'interaction'
  if (category === 'process') return 'decision'
  if (category === 'tool') return getProtocolEffect(node) === 'read_only' ? 'mcp_read' : 'mcp_execute'
  if (category === 'remote') return 'remote_call'
  if (category === 'transfer') return 'transfer'
  if (category === 'store') return 'delivery'
  if (category === 'control') return 'gate'
  return 'extension'
}

function defaultPurpose(node: FlowNode, kind: NodeSemanticKind) {
  const input = readNodeValue(node, 'input', 'input_key', 'source')
  const output = readNodeValue(node, 'output', 'output_name', 'save_to', 'primary_output')
  const tool = getToolIds(node)[0]
  const purposes: Record<NodeSemanticKind, string> = {
    start: '接收本次运行的启动输入，并把控制权交给第一个可执行节点。',
    terminal: `收束当前流程，并确认${output ? `“${output}”` : '最终结果'}是否可以作为本次运行结果。`,
    checkpoint: '保存可恢复的运行边界，供暂停、重试或断点恢复使用。',
    input: `从${compactNodeValue(readNodeValue(node, 'source'), '指定来源')}收集信息，并写入${output ? `“${output}”` : '流程上下文'}。`,
    interaction: '展示卡带界面、收集用户操作，并通过命名动作继续流程。',
    decision: `使用模型把${input ? `“${input}”` : '上游信息'}转换为受契约约束的决策结果。`,
    retrieval: `根据${input ? `“${input}”` : '查询条件'}检索资料，并输出可追溯的候选结果。`,
    mcp_read: `通过${tool || '已绑定工具'}读取外部信息，不产生外部副作用。`,
    mcp_execute: `通过${tool || '已绑定工具'}执行外部操作，并记录权限、失败与审计信息。`,
    remote_call: '调用本机绑定的远程服务角色，并按超时与重放策略处理结果。',
    transfer: `把${input ? `“${input}”` : '上游结果'}映射到${output ? `“${output}”` : '下游变量'}。`,
    transform: `把${input ? `“${input}”` : '输入数据'}按声明规则转换为${output ? `“${output}”` : '目标格式'}。`,
    validation: `校验${input ? `“${input}”` : '上游结果'}是否满足声明契约，并输出可路由的检查结论。`,
    routing: '根据条件或命名结果选择唯一的后续分支。',
    gate: '依据机器可判定的规则决定放行、拒绝或回流。',
    human_gate: '暂停自动流程，等待指定人员审核后继续或退回。',
    delivery: `把${input ? `“${input}”` : '最终结果'}整理为可交付产物，并声明主输出。`,
    extension: '执行卡带声明的自定义能力；具体边界由扩展契约决定。',
  }
  return purposes[kind]
}

function buildConfigIssues(node: FlowNode, kind: NodeSemanticKind, context: NodePresentationContext): NodeConfigIssue[] {
  if (context.analysisFindings !== undefined) {
    return context.analysisFindings
      .filter((finding) => finding.severity === 'blocker' || finding.severity === 'warning')
      .map((finding) => ({
        severity: finding.severity === 'blocker' ? 'blocker' : 'warning',
        code: finding.code,
        message: finding.message,
        origin: 'runtime_preflight',
      }))
  }
  const issues: NodeConfigIssue[] = []
  const blocker = (code: string, message: string) => issues.push({ severity: 'blocker', code, message, origin: 'authoring_hint' })
  const warning = (code: string, message: string) => issues.push({ severity: 'warning', code, message, origin: 'authoring_hint' })
  const requireValue = (value: unknown, code: string, message: string) => { if (!configured(value)) blocker(code, message) }
  const input = readNodeValue(node, 'input', 'input_key')
  const output = readNodeValue(node, 'output', 'output_name', 'save_to')
  const outgoingCount = context.outgoingEdges?.length ?? context.outgoingNodes?.length ?? 0

  if (node.type === 'process') {
    requireValue(getProtocolKind(node), 'kind_missing', '缺少协议 kind，底座无法确认节点语义。')
    requireValue(getProtocolExecutor(node), 'executor_missing', '缺少 executor，底座无法选择执行器。')
    requireValue(getProtocolEffect(node), 'effect_missing', '缺少 effect，无法判断副作用和重放安全。')
  }

  switch (kind) {
    case 'start':
      if (outgoingCount === 0) blocker('start_without_target', '流程入口没有连接可执行节点。')
      break
    case 'terminal':
      if (outgoingCount > 0 || configured(node.next)) blocker('terminal_has_next', '结束节点仍声明后续节点，流程无法正确收束。')
      break
    case 'input':
      requireValue(node.input_kind || readNodeValue(node, 'input_kind'), 'input_kind_missing', '输入节点缺少 input_kind。')
      requireValue(node.source || readNodeValue(node, 'source'), 'input_source_missing', '输入节点缺少来源 source。')
      requireValue(node.input_schema || readNodeValue(node, 'input_schema'), 'input_schema_missing', '输入节点缺少输入契约 input_schema。')
      requireValue(output, 'input_output_missing', '输入节点缺少写入流程的数据键。')
      break
    case 'interaction':
      requireValue(node.component_ref || readNodeValue(node, 'component_ref'), 'component_missing', '交互节点尚未绑定卡带 UI 组件。')
      requireValue(node.interaction_mode || readNodeValue(node, 'interaction_mode'), 'interaction_mode_missing', '交互节点缺少 display、collect 或 review 模式。')
      if (readNodeValue(node, 'interaction_mode') !== 'display' && !countMap(node.action_routes)) warning('interaction_routes_missing', '收集或审核界面尚未声明提交动作路由。')
      break
    case 'decision':
      requireValue(node.model_role || readNodeValue(node, 'model_role'), 'model_role_missing', 'AI 决策节点尚未声明模型角色。')
      requireValue(node.output_contract || readNodeValue(node, 'output_contract'), 'decision_contract_missing', 'AI 决策节点缺少结构化输出契约。')
      if (!configured(input)) warning('decision_input_missing', '尚未明确模型消费的输入变量。')
      break
    case 'retrieval':
      requireValue(input, 'retrieval_query_missing', '检索节点缺少查询输入。')
      requireValue(output, 'retrieval_output_missing', '检索节点缺少结果输出。')
      if (!getToolIds(node).length && !configured(readNodeValue(node, 'resource_role', 'source'))) warning('retrieval_source_missing', '尚未声明检索来源或工具。')
      break
    case 'mcp_read':
    case 'mcp_execute':
      if (!getToolIds(node).length) blocker('tool_binding_missing', 'MCP 节点尚未绑定允许使用的工具。')
      requireValue(node.mcp_binding || node.tool_binding || readNodeValue(node, 'mcp_binding', 'tool_binding'), 'mcp_binding_missing', 'MCP 节点缺少调用绑定。')
      if (kind === 'mcp_read' && getProtocolEffect(node) && getProtocolEffect(node) !== 'read_only') blocker('mcp_read_effect_invalid', 'MCP 读取节点必须声明 read_only。')
      if (kind === 'mcp_execute') {
        requireValue(node.permission || readNodeValue(node, 'permission'), 'permission_missing', '副作用工具缺少权限策略。')
        requireValue(node.failure_policy || readNodeValue(node, 'failure_policy'), 'failure_policy_missing', '副作用工具缺少失败策略。')
        if (!configured(node.audit_log ?? readNodeValue(node, 'audit_log'))) warning('audit_missing', '建议开启审计日志，便于定位外部操作。')
      }
      break
    case 'remote_call':
      requireValue(readNodeValue(node, 'resource_role'), 'resource_role_missing', '远程节点缺少可迁移的 resource_role。')
      if (!getToolIds(node).length) blocker('remote_allowlist_missing', '远程节点没有声明允许调用的操作。')
      requireValue(node.timeout_ms || readNodeValue(node, 'timeout_ms'), 'remote_timeout_missing', '远程调用缺少超时时间。')
      requireValue(node.failure_policy || readNodeValue(node, 'failure_policy'), 'remote_failure_policy_missing', '远程调用缺少失败策略。')
      if (getProtocolEffect(node) && getProtocolEffect(node) !== 'none' && getProtocolEffect(node) !== 'read_only') {
        requireValue(readNodeValue(node, 'replay_policy'), 'replay_policy_missing', '有副作用的远程调用缺少重放策略。')
      }
      break
    case 'transfer':
    case 'transform':
      requireValue(input, `${kind}_input_missing`, '缺少要消费的输入变量。')
      requireValue(output, `${kind}_output_missing`, '缺少要写入的输出变量。')
      break
    case 'validation':
      requireValue(input, 'validation_input_missing', '校验节点缺少被校验输入。')
      requireValue(readNodeValue(node, 'validation_contract', 'output_contract', 'contract'), 'validation_contract_missing', '校验节点缺少判定契约。')
      break
    case 'routing':
      if (!countMap(readNodeValue(node, 'routes', 'action_routes')) && outgoingCount < 2) blocker('routes_missing', '路由节点没有声明可选择的分支。')
      break
    case 'gate':
    case 'human_gate':
      requireValue(readNodeValue(node, 'gate_contract', 'decision_contract', 'condition'), 'gate_contract_missing', '门禁节点缺少放行与拒绝规则。')
      if (!countMap(readNodeValue(node, 'routes', 'action_routes')) && outgoingCount < 2) warning('gate_routes_missing', '门禁尚未明确通过与拒绝的去向。')
      break
    case 'delivery':
      requireValue(input, 'delivery_input_missing', '交付节点缺少产物来源 input。')
      requireValue(output, 'delivery_output_missing', '交付节点缺少输出变量 output。')
      requireValue(node.primary_output || readNodeValue(node, 'primary_output'), 'primary_output_missing', '交付节点缺少主输出 primary_output。')
      break
    case 'checkpoint':
    case 'extension':
      break
  }
  return issues
}

function buildSemanticSections(node: FlowNode, kind: NodeSemanticKind, context: NodePresentationContext): { info: FlowNodeSection; flow: FlowNodeSection } {
  const input = readNodeValue(node, 'input', 'input_key', 'source')
  const output = readNodeValue(node, 'output', 'output_name', 'save_to', 'primary_output')
  const routeMap = readNodeValue(node, 'routes', 'action_routes')
  const routeCount = Math.max(countMap(routeMap), context.outgoingEdges?.length || context.outgoingNodes?.length || 0)
  const tools = getToolIds(node)
  const downstream = context.outgoingNodes?.map((item) => item.display_name || item.title || item.id) || []
  const nextLabel = downstream.length ? downstream.join(', ') : node.next
  const commonFlow = (outputLabel = '输出变量'): FlowNodeSection => ({
    title: '输出 / 连接',
    fields: [field(outputLabel, output, { mono: true }), field('后续节点', nextLabel || '当前没有下游节点')],
  })

  switch (kind) {
    case 'start':
      return {
        info: { title: '启动约定', fields: [field('入口类型', node.entry_kind || readNodeValue(node, 'entry_kind') || 'root'), field('启动输入', node.input_schema || readNodeValue(node, 'input_schema') || '由运行表单提供', { mono: true })] },
        flow: { title: '流程入口', fields: [field('首个节点', nextLabel), field('出口数量', context.outgoingEdges?.length || context.outgoingNodes?.length || 0)] },
      }
    case 'terminal':
      return {
        info: { title: '收束结果', fields: [field('结果来源', input || node.primary_output, { mono: true }), field('结束状态', readNodeValue(node, 'outcome', 'result_status') || 'completed')] },
        flow: { title: '流程出口', fields: [field('主输出', node.primary_output || output, { mono: true }), field('后续连接', routeCount ? `${routeCount} 条（异常）` : '无')] },
      }
    case 'checkpoint':
      return {
        info: { title: '恢复边界', fields: [field('检查点键', readNodeValue(node, 'checkpoint_key', 'output'), { mono: true }), field('持久化', readNodeValue(node, 'persist', 'persistence') || 'runtime')] },
        flow: { title: '恢复 / 连接', fields: [field('恢复策略', readNodeValue(node, 'recovery_policy', 'replay_policy')), field('后续节点', nextLabel)] },
      }
    case 'input':
      return {
        info: { title: '输入契约', fields: [field('输入来源', node.source || readNodeValue(node, 'source')), field('数据类型', node.input_kind || readNodeValue(node, 'input_kind'), { mono: true }), field('输入格式', readNodeValue(node, 'data_format', 'input_schema.type') || 'schema'), field('写入变量', output, { mono: true })] },
        flow: commonFlow('写入变量'),
      }
    case 'interaction':
      return {
        info: { title: '交互约定', fields: [field('组件', node.component_ref || readNodeValue(node, 'component_ref'), { mono: true }), field('交互模式', node.interaction_mode || readNodeValue(node, 'interaction_mode')), field('提交动作', countMap(node.action_routes) ? `${countMap(node.action_routes)} 个命名动作` : node.action), field('结果变量', output, { mono: true })] },
        flow: { title: '动作 / 连接', fields: [field('可用动作', Object.keys(node.action_routes || {}).join(', ') || '未声明'), field('后续节点', nextLabel)] },
      }
    case 'decision':
      return {
        info: { title: '决策契约', fields: [field('模型角色', node.model_role || readNodeValue(node, 'model_role'), { mono: true }), field('消费输入', input, { mono: true }), field('输出契约', node.output_contract || readNodeValue(node, 'output_contract'), { mono: true }), field('结果投影', readNodeValue(node, 'decision_contract.consume.path', 'consume.path', 'decision_consume.path') || output, { mono: true })] },
        flow: commonFlow('决策结果'),
      }
    case 'retrieval':
      return {
        info: { title: '检索约定', fields: [field('查询输入', input, { mono: true }), field('检索来源', readNodeValue(node, 'resource_role', 'source') || tools[0]), field('返回数量', readNodeValue(node, 'top_k', 'limit') || '由工具决定'), field('结果变量', output, { mono: true })] },
        flow: commonFlow('检索结果'),
      }
    case 'mcp_read':
    case 'mcp_execute':
      return {
        info: { title: kind === 'mcp_read' ? '读取调用' : '执行调用', fields: [field('绑定工具', tools[0]), field('允许工具', tools.length ? `${tools.length} 个` : ''), field('副作用', getProtocolEffect(node), { mono: true }), field('失败策略', node.failure_policy || readNodeValue(node, 'failure_policy'))] },
        flow: commonFlow('工具结果'),
      }
    case 'remote_call':
      return {
        info: { title: '远程调用', fields: [field('资源角色', readNodeValue(node, 'resource_role'), { mono: true }), field('允许操作', tools.length ? `${tools.length} 个` : ''), field('超时时间', configured(node.timeout_ms) ? `${node.timeout_ms} ms` : ''), field('重放策略', readNodeValue(node, 'replay_policy'))] },
        flow: commonFlow('远程结果'),
      }
    case 'transfer':
      return {
        info: { title: '变量映射', fields: [field('来源变量', input, { mono: true }), field('目标变量', output, { mono: true }), field('映射方式', readNodeValue(node, 'mapping_mode', 'mode') || 'copy'), field('缺失策略', readNodeValue(node, 'missing_policy') || 'stop')] },
        flow: commonFlow('目标变量'),
      }
    case 'transform':
      return {
        info: { title: '转换规则', fields: [field('输入变量', input, { mono: true }), field('转换方式', readNodeValue(node, 'transform_contract', 'rule', 'format')), field('输出变量', output, { mono: true }), field('副作用', getProtocolEffect(node), { mono: true })] },
        flow: commonFlow('转换结果'),
      }
    case 'validation':
      return {
        info: { title: '校验契约', fields: [field('校验输入', input, { mono: true }), field('规则契约', readNodeValue(node, 'validation_contract', 'output_contract', 'contract'), { mono: true }), field('通过结果', readNodeValue(node, 'pass_output', 'output'), { mono: true }), field('失败策略', node.failure_policy || readNodeValue(node, 'failure_policy'))] },
        flow: { title: '结果 / 连接', fields: [field('检查结果', output, { mono: true }), field('分支去向', routeCount ? `${routeCount} 条` : nextLabel)] },
      }
    case 'routing':
      return {
        info: { title: '路由规则', fields: [field('判定输入', input, { mono: true }), field('条件表达式', readNodeValue(node, 'condition', 'route_expression'), { mono: true }), field('分支数量', routeCount), field('默认分支', readNodeValue(node, 'default_route', 'default'))] },
        flow: { title: '分支 / 连接', fields: [field('分支名称', routeMap ? Object.keys(routeMap as object).join(', ') : ''), field('后续节点', nextLabel)] },
      }
    case 'gate':
    case 'human_gate':
      return {
        info: { title: kind === 'human_gate' ? '审核约定' : '门禁规则', fields: [field('判定契约', readNodeValue(node, 'gate_contract', 'decision_contract', 'condition'), { mono: true }), field(kind === 'human_gate' ? '审核人' : '执行器', readNodeValue(node, 'reviewer_role') || getProtocolExecutor(node)), field('超时时间', readNodeValue(node, 'timeout_ms', 'timeout')), field('结果变量', output, { mono: true })] },
        flow: { title: '结果 / 连接', fields: [field('可选结果', routeMap ? Object.keys(routeMap as object).join(', ') : '通过 / 拒绝'), field('分支去向', routeCount ? `${routeCount} 条` : nextLabel)] },
      }
    case 'delivery':
      return {
        info: { title: '交付约定', fields: [field('产物来源', input, { mono: true }), field('主输出', node.primary_output || readNodeValue(node, 'primary_output'), { mono: true }), field('交付格式', readNodeValue(node, 'artifact_type', 'format', 'output_contract')), field('保存位置', readNodeValue(node, 'delivery_path', 'path', 'save_to'))] },
        flow: { title: '产物 / 完成', fields: [field('交付变量', output, { mono: true }), field('完成后', nextLabel || '结束本次流程')] },
      }
    case 'extension':
    default:
      return {
        info: { title: '扩展契约', fields: [field('协议 kind', getProtocolKind(node), { mono: true }), field('执行器', getProtocolExecutor(node), { mono: true }), field('副作用', getProtocolEffect(node), { mono: true }), field('输出变量', output, { mono: true })] },
        flow: commonFlow(),
      }
  }
}

function buildRuntimeSection(runState?: NodeRunState): FlowNodeSection | null {
  if (!runState || runState.status === 'idle') return null
  const statusLabel = runState.status === 'running' ? '运行中' : runState.status === 'completed' ? '已完成' : runState.status === 'failed' ? '失败' : '已暂停'
  return {
    title: '本次运行',
    fields: [
      field('运行状态', statusLabel, { tone: runState.status === 'failed' ? 'danger' : runState.status === 'completed' ? 'success' : 'default' }),
      field('执行动作', runState.action, { mono: true }),
      field('输入键', runState.inputKey, { mono: true }),
      field(runState.errorMsg ? '失败原因' : '输出键', runState.errorMsg || runState.outputKey, { mono: !runState.errorMsg, tone: runState.errorMsg ? 'danger' : 'default' }),
    ],
  }
}

export function getRemoteServiceLabel(node: FlowNode) {
  if (resolveNodeSemanticKind(node) !== 'remote_call') return ''
  return compactNodeValue(readNodeValue(node, 'resource_role', 'remote_service', 'service') || getToolIds(node)[0], 'Remote')
}

export function buildFlowNodeCardView(node: FlowNode, runState?: NodeRunState, context: NodePresentationContext = {}) {
  const category = getNodeCategory(node)
  const semanticKind = resolveNodeSemanticKind(node)
  const kindLabel = KIND_LABELS[semanticKind]
  const protocolLabel = getProcessDisplayLabel(node) || kindLabel
  const params = node.params || {}
  const configuredPurpose = String(readNodeValue(node, 'purpose', 'summary', 'description') || '').trim()
  const description = configuredPurpose || defaultPurpose(node, semanticKind)
  const isImportantNode = Boolean(params.important_node || node.data?.params?.important_node)
  const remoteServiceLabel = getRemoteServiceLabel(node)
  const milestoneLabel = String(params.milestone_label || node.data?.params?.milestone_label || '').trim()
  const moduleLabel = String(params.module_label || node.data?.params?.module_label || '').trim()
  const issues = buildConfigIssues(node, semanticKind, context)
  const blockers = issues.filter((item) => item.severity === 'blocker')
  const warnings = issues.filter((item) => item.severity === 'warning')
  const configHealth = blockers.length ? 'blocked' : warnings.length ? 'draft' : 'ready'
  const configHealthLabel = configHealth === 'blocked' ? '配置阻断' : configHealth === 'draft' ? '待补充' : '可运行'
  const caps: string[] = []
  if (node.agent) caps.push(`AI:${node.agent}`)
  if (getToolIds(node).length) caps.push(`工具:${getToolIds(node).length}`)
  if (remoteServiceLabel) caps.push(`远端:${remoteServiceLabel}`)
  if (!isImportantNode && moduleLabel) caps.push(moduleLabel)

  const runStatusLabel = runState?.status === 'running'
    ? '运行中'
    : runState?.status === 'completed'
      ? '已完成'
      : runState?.status === 'failed'
        ? '失败'
        : runState?.status === 'paused'
          ? '已暂停'
          : runState?.status === 'idle'
            ? '未执行'
            : configHealthLabel

  const semanticSections = buildSemanticSections(node, semanticKind, context)
  const runtimeSection = buildRuntimeSection(runState)
  return {
    category,
    semanticKind,
    kindLabel,
    iconKey: ICON_KEYS[semanticKind],
    protocolLabel,
    description,
    purposeTitle: '节点职责',
    isImportantNode,
    remoteServiceLabel,
    milestoneLabel,
    caps,
    issues,
    primaryIssue: blockers[0] || warnings[0],
    configHealth,
    configHealthLabel,
    infoSection: runtimeSection || semanticSections.info,
    designInfoSection: semanticSections.info,
    flowSection: semanticSections.flow,
    inputName: compactNodeValue(runState?.inputKey || readNodeValue(node, 'input', 'input_key', 'source')),
    outputName: compactNodeValue(runState?.outputKey || readNodeValue(node, 'output', 'output_name', 'save_to', 'primary_output')),
    executorName: compactNodeValue(getProtocolExecutor(node), node.scope === 'root' ? 'base runtime' : 'builtin'),
    effectName: compactNodeValue(getProtocolEffect(node), 'none'),
    scopeName: compactNodeValue(node.scope, 'root'),
    runStatusLabel,
    runClass: runState ? `node-run-${runState.status}` : '',
    hasRunData: Boolean(runState && runState.status !== 'idle'),
  }
}

const PLAIN_FIELD_LABELS: Record<string, string> = {
  query: '用户说的话',
  session: '当前会话',
  session_id: '会话信息',
  request: '用户请求',
  user_request: '用户提供的信息',
  user_input: '用户提供的信息',
  user_form: '用户填写的内容',
  intent: '用户想做的事',
  intent_envelope: '判断结果',
  entities: '关键信息',
  products: '商品信息',
  product_total: '商品数量',
  orders: '订单信息',
  order_total: '订单数量',
  payload: '整理后的结果',
  reply: '给用户的回复',
  reply_envelope: '回复结果',
  references: '参考资料',
  recovery_result: '失败处理说明',
  release_summary: '发布摘要',
  generated_content: '生成的内容',
  modified_result: '修改后的内容',
  structured_result: '整理后的内容',
  summary: '摘要',
  file_content: '文件内容',
  file_write_result: '写入结果',
  dir_entries: '目录内容',
  tool_result: '工具处理结果',
  context_pack: '合并后的内容',
  error: '出错信息',
  context: '当时的流程信息',
  result: '处理结果',
}

const PLAIN_FIELD_DESCRIPTIONS: Record<string, string> = {
  query: '一句话或一段话',
  session: '帮助 AI 接着聊',
  session_id: '帮助系统记住这次对话',
  request: '整理好的请求内容',
  user_request: '用户在运行前填写的内容',
  user_input: '用户在运行前填写的内容',
  user_form: '用户在运行前填写的内容',
  intent: '是查订单还是查商品',
  intent_envelope: '下一步应该做什么',
  entities: '订单号、商品名等线索',
  products: '从商品库查到的内容',
  product_total: '一共找到多少件商品',
  orders: '从订单系统查到的内容',
  order_total: '一共找到多少条订单',
  payload: '统一格式的查询结果',
  reply: '可以直接展示给用户',
  reply_envelope: '已经组织好的回答',
  references: '结果来自哪里',
  recovery_result: '告诉用户哪里出了问题',
  release_summary: '可以继续修改或直接交付',
  generated_content: '可以交给后续步骤继续使用',
  modified_result: '按要求修改后的结果',
  structured_result: '已经转换成目标格式',
  summary: '提炼后的重点内容',
  file_content: '从所选文件读取的内容',
  file_write_result: '文件保存状态和位置',
  dir_entries: '所选目录中的文件和文件夹',
  tool_result: '工具返回的处理结果',
  context_pack: '多个来源合并后的统一内容',
  error: '前面节点的失败原因',
  context: '出错时已经处理到哪里',
  result: '交给下一个节点使用',
}

function plainFieldKey(value: unknown) {
  return String(value || '')
    .trim()
    .replace(/^store:/, '')
    .replace(/^\$\{(.+)\}$/, '$1')
    .split('.')
    .filter(Boolean)
    .at(-1) || ''
}

export function plainOutcomeFieldLabel(value: unknown) {
  const key = plainFieldKey(value)
  if (/^input_\d+$/i.test(key)) return `输入 ${Number(key.split('_').at(-1)) || ''}`.trim()
  return PLAIN_FIELD_LABELS[key] || (key ? '流程信息' : '上一步的内容')
}

function plainOutcomeFieldDescription(value: unknown) {
  const key = plainFieldKey(value)
  return PLAIN_FIELD_DESCRIPTIONS[key] || '给后续节点继续使用'
}

function outcomeTitle(node: FlowNode, kind: NodeSemanticKind) {
  const title = String(node.display_name || node.title || '').trim()
  const searchable = `${node.id} ${title} ${node.action || ''}`.toLowerCase()
  if (kind === 'start') return '开始'
  if (kind === 'terminal' && /fail|error|失败|错误/.test(searchable)) return '处理失败并结束'
  if (kind === 'terminal') return '把结果交给用户'
  if (kind === 'input') return /用户|request|collect/.test(searchable) ? '先收集用户说了什么' : '先收集需要的信息'
  if (kind === 'decision' && /意图|intent|router/.test(searchable)) return '先判断用户想做什么'
  if (kind === 'decision' && /回复|reply|answer|response/.test(searchable)) return '让 AI 写好最终回复'
  const target = String((node.params?.preset_config as AnyRecord | undefined)?.target || '').trim()
  if (kind === 'decision' && target) return `让 AI ${target}`
  if (kind === 'decision') return '让 AI 判断下一步怎么做'
  if ((kind === 'mcp_read' || kind === 'retrieval') && /订单|order/.test(searchable)) return '去订单系统查订单'
  if ((kind === 'mcp_read' || kind === 'retrieval') && /商品|产品|product|catalog/.test(searchable)) return '去商品库查商品'
  if (kind === 'mcp_read' || kind === 'retrieval') return `去外部资料库查${title || '信息'}`
  if (kind === 'transform') return '把查询结果整理好'
  if (kind === 'transfer' && /失败|错误|error|fail/.test(searchable)) return '遇到问题时统一处理'
  if (kind === 'delivery') return '整理并保存最终成果'
  return title || '处理这一步'
}

export function outcomeCopy(node: FlowNode, kind: NodeSemanticKind) {
  const searchable = `${node.id} ${node.display_name || node.title || ''} ${node.action || ''}`.toLowerCase()
  if (kind === 'start') return ['流程从这里开始，接收用户输入。', '这是整个流程的起点。']
  if (kind === 'terminal' && /fail|error|失败|错误/.test(searchable)) return ['记录失败原因并结束当前路径。', '只有前面的步骤无法继续时才会到这里。']
  if (kind === 'terminal') return ['把整理好的回复交给用户，然后结束本次流程。', '用户最终看到的内容从这里交付。']
  if (kind === 'input') return ['把用户原话整理好，方便后续步骤使用。', '先把用户输入变成统一格式。']
  if (kind === 'decision' && /意图|intent|router/.test(searchable)) return ['识别用户想做什么，决定接下来走哪条流程。', '判断这是查订单、查商品，还是需要补充信息。']
  if (kind === 'decision' && /回复|reply|answer|response/.test(searchable)) return ['根据查询结果，写成用户容易理解的回复。', 'AI 会在这里组织最终说法。']
  const target = String((node.params?.preset_config as AnyRecord | undefined)?.target || '').trim()
  if (kind === 'decision' && target) return [`让 AI ${target}。`, '生成结果会自动交给下一步。']
  if (kind === 'decision') return ['让 AI 根据已有信息做出判断。', '判断结果会决定下一步怎么走。']
  if ((kind === 'mcp_read' || kind === 'retrieval') && /订单|order/.test(searchable)) return ['根据用户请求查询订单系统，获取订单信息。', '这里只读取订单，不会修改订单。']
  if ((kind === 'mcp_read' || kind === 'retrieval') && /商品|产品|product|catalog/.test(searchable)) return ['根据用户请求查询商品库，获取商品信息。', '这里只读取商品资料，不会修改商品。']
  if (kind === 'mcp_read' || kind === 'retrieval') return ['根据上一步的要求，到外部资料库查找信息。', '这里只负责查询，不会修改外部数据。']
  if (kind === 'transform') return ['把不同来源的结果整理成统一格式。', '这样后面的 AI 不用理解多种数据格式。']
  if (kind === 'transfer' && /失败|错误|error|fail/.test(searchable)) return ['当前面步骤失败时，整理原因并给出可交付的说明。', '任何查询失败都会统一走到这里。']
  if (kind === 'delivery') return ['把流程生成的内容整理成可以交付的成果。', '这是成果保存和交付的位置。']
  const technical = buildFlowNodeCardView(node)
  return [technical.description, '完成这一小步后，流程会自动继续。']
}

function schemaInputRows(node: FlowNode): OutcomeNodeRow[] {
  const schema = node.input_schema && typeof node.input_schema === 'object' ? node.input_schema as AnyRecord : null
  const properties = schema?.properties && typeof schema.properties === 'object' ? schema.properties as AnyRecord : null
  if (!properties) return []
  return Object.keys(properties).slice(0, 3).map((key) => ({
    label: plainOutcomeFieldLabel(key),
    value: plainOutcomeFieldDescription(key),
  }))
}

function configuredInputRows(node: FlowNode): OutcomeNodeRow[] {
  const preset = node.params?.preset_config as AnyRecord | undefined
  const configuredFields = preset?.fields
  const labels = Array.isArray(configuredFields)
    ? configuredFields.map(String)
    : typeof configuredFields === 'string'
      ? configuredFields.split(/[，、,;；\n]/)
      : []
  return labels.map((label) => label.trim()).filter(Boolean).slice(0, 3).map((label) => ({
    label,
    value: '用户在运行前填写',
  }))
}

function bindingInputRows(node: FlowNode): OutcomeNodeRow[] {
  if (!node.input_binding || typeof node.input_binding !== 'object') return []
  const labels = (node.params?.data_labels || node.params?.field_labels || {}) as Record<string, unknown>
  return Object.entries(node.input_binding).slice(0, 3).map(([key, reference]) => ({
    label: plainOutcomeFieldLabel(key),
    value: compactNodeValue(labels[key] || plainOutcomeFieldDescription(reference || key), '上一步提供的内容', 32),
  }))
}

function outputRows(node: FlowNode): OutcomeNodeRow[] {
  const params = node.params || {}
  const names = [...new Set([
    ...asList(node.output),
    ...asList(node.primary_output),
    ...asList(params.output),
    ...asList(params.save_to),
  ])]
  return names.slice(0, 3).map((name) => ({
    label: plainOutcomeFieldLabel(name),
    value: plainOutcomeFieldDescription(name),
  }))
}

export function buildOutcomeNodeCardView(node: FlowNode, runState?: NodeRunState, context: NodePresentationContext = {}) {
  const technical = buildFlowNodeCardView(node, runState, context)
  const [what, beginnerTip] = outcomeCopy(node, technical.semanticKind)
  const configuredRows = technical.semanticKind === 'input' ? configuredInputRows(node) : []
  const bindingRows = bindingInputRows(node)
  const inputs = configuredRows.length ? configuredRows : bindingRows.length ? bindingRows : schemaInputRows(node)
  if (!inputs.length && technical.semanticKind === 'start') {
    inputs.push({ label: '用户输入', value: '用户在运行前填写的内容' })
  } else if (!inputs.length) {
    inputs.push({ label: plainOutcomeFieldLabel(readNodeValue(node, 'input', 'input_key', 'source')), value: '由上一步自动提供' })
  }
  const outputs = outputRows(node)
  if (!outputs.length) {
    outputs.push({
      label: technical.semanticKind === 'start' ? '交给下一步' : technical.semanticKind === 'terminal' ? '最终结果' : '处理结果',
      value: technical.semanticKind === 'start' ? '用户刚刚填写的内容' : technical.semanticKind === 'terminal' ? '直接交给用户' : '交给下一步继续使用',
    })
  }
  return {
    ...technical,
    title: outcomeTitle(node, technical.semanticKind),
    what,
    beginnerTip,
    inputs: inputs.slice(0, 3),
    outputs: outputs.slice(0, 3),
  }
}

export function buildOutcomeNodeModels(graph: FlowGraph, runStates?: Map<string, NodeRunState>) {
  const nodeById = new Map(graph.nodes.map((node) => [node.id, node]))
  const incomingByNode = new Map(graph.nodes.map((node) => [node.id, [] as FlowNode[]]))
  const outgoingByNode = new Map(graph.nodes.map((node) => [node.id, [] as FlowNode[]]))
  const incomingEdgesByNode = new Map(graph.nodes.map((node) => [node.id, [] as FlowEdge[]]))
  const outgoingEdgesByNode = new Map(graph.nodes.map((node) => [node.id, [] as FlowEdge[]]))
  graph.edges.forEach((edge) => {
    const source = nodeById.get(edge.from)
    const target = nodeById.get(edge.to)
    if (source) incomingByNode.get(edge.to)?.push(source)
    if (target) outgoingByNode.get(edge.from)?.push(target)
    incomingEdgesByNode.get(edge.to)?.push(edge)
    outgoingEdgesByNode.get(edge.from)?.push(edge)
  })
  return new Map(graph.nodes.map((node) => [node.id, {
    view: buildOutcomeNodeCardView(node, runStates?.get(node.id), {
      incomingNodes: incomingByNode.get(node.id),
      outgoingNodes: outgoingByNode.get(node.id),
      incomingEdges: incomingEdgesByNode.get(node.id),
      outgoingEdges: outgoingEdgesByNode.get(node.id),
      analysisFindings: getNodePreflightIssues(graph, node.id),
    }),
  } satisfies OutcomeNodeRenderModel]))
}

export function getNodePreflightIssues(graph: FlowGraph, nodeId: string): FlowAnalysisFinding[] | undefined {
  const findings = graph.analysis?.findings
  if (!Array.isArray(findings)) return undefined
  return findings.filter((finding) => finding?.node_id === nodeId)
}

export function buildNodeDetailFacts(node: FlowNode, section: string, options: {
  edges?: FlowEdge[]
  runState?: NodeRunState
  runEvents?: Array<{ type?: string; message?: string; data?: AnyRecord }>
  analysisFindings?: FlowAnalysisFinding[]
} = {}): { title: string; description: string; fields: FlowNodeField[] } {
  const edges = options.edges || []
  const incomingEdges = edges.filter((edge) => edge.to === node.id)
  const outgoingEdges = edges.filter((edge) => edge.from === node.id)
  const context: NodePresentationContext = { incomingEdges, outgoingEdges, analysisFindings: options.analysisFindings }
  const view = buildFlowNodeCardView(node, options.runState, context)
  const input = readNodeValue(node, 'input', 'input_key', 'source')
  const output = readNodeValue(node, 'output', 'output_name', 'save_to', 'primary_output')
  const tools = getToolIds(node)
  const routes = readNodeValue(node, 'routes', 'action_routes')
  const latestEvent = options.runEvents?.[options.runEvents.length - 1]
  const result = (title: string, description: string, fields: FlowNodeField[]) => ({ title, description, fields })

  switch (section) {
    case 'contract':
      return result(`${view.kindLabel}契约`, '底座据此选择执行方式并判断节点是否可运行。', [
        field('协议 kind', getProtocolKind(node) || view.semanticKind, { mono: true }),
        field('执行器', getProtocolExecutor(node), { mono: true }),
        field('作用域', node.scope || 'root', { mono: true }),
        field('副作用', getProtocolEffect(node), { mono: true }),
        field('配置健康', view.configHealthLabel, { tone: view.configHealth === 'blocked' ? 'danger' : view.configHealth === 'draft' ? 'warning' : 'success' }),
        field('首要问题', view.primaryIssue?.message || '未发现协议阻断'),
        field('节点 ID', node.id, { mono: true }),
      ])
    case 'inputs':
      return result('输入与前置条件', '这个节点执行前必须拿到的数据和上游来源。', [
        field('输入变量', input, { mono: true }),
        field('输入来源', node.source || readNodeValue(node, 'source')),
        field('输入类型', node.input_kind || readNodeValue(node, 'input_kind'), { mono: true }),
        field('输入契约', node.input_schema || readNodeValue(node, 'input_schema'), { mono: true }),
        field('上游节点', incomingEdges.map((edge) => edge.from).join(', ') || '无', { mono: true }),
        field('可选输入', readNodeValue(node, 'optional_input', 'optional_inputs'), { mono: true }),
      ])
    case 'outputs':
      return result('输出与后续节点', '节点成功后写入的数据、输出契约和消费方。', [
        field('输出变量', output, { mono: true }),
        field('主输出', node.primary_output || readNodeValue(node, 'primary_output'), { mono: true }),
        field('输出契约', node.output_contract || readNodeValue(node, 'output_contract'), { mono: true }),
        field('后续节点', outgoingEdges.map((edge) => edge.to).join(', ') || node.next || '无', { mono: true }),
        field('分支标签', outgoingEdges.map((edge) => edge.label).filter(Boolean).join(', ')),
      ])
    case 'component':
      return result('交互组件', '卡带 UI、交互模式、输入绑定和可提交动作。', [
        field('组件引用', node.component_ref || readNodeValue(node, 'component_ref'), { mono: true }),
        field('交互模式', node.interaction_mode || readNodeValue(node, 'interaction_mode')),
        field('输入绑定', node.input_binding || readNodeValue(node, 'input_binding'), { mono: true }),
        field('命名动作', Object.keys(node.action_routes || {}).join(', ')),
        field('动作路由', node.action_routes, { mono: true }),
        field('展示运行时', readNodeValue(node, 'component_runtime', 'runtime') || '由组件清单声明'),
      ])
    case 'model':
      return result('模型与决策', '模型角色、决策信封、消费投影和不可决策时的处理。', [
        field('模型角色', node.model_role || readNodeValue(node, 'model_role'), { mono: true }),
        field('模型配方', readNodeValue(node, 'model_recipe', 'recipe', 'provider_id'), { mono: true }),
        field('输入变量', input, { mono: true }),
        field('输出契约', node.output_contract || readNodeValue(node, 'output_contract'), { mono: true }),
        field('决策契约', node.decision_contract || readNodeValue(node, 'decision_contract'), { mono: true }),
        field('结果投影', readNodeValue(node, 'decision_contract.consume.path', 'consume.path', 'decision_consume.path'), { mono: true }),
      ])
    case 'resources':
      return result('资源与工具', '运行时真正需要绑定的本机角色、工具白名单和服务边界。', [
        field('资源角色', readNodeValue(node, 'resource_role'), { mono: true }),
        field('工具绑定', node.tool_binding || readNodeValue(node, 'tool_binding'), { mono: true }),
        field('MCP 绑定', node.mcp_binding || readNodeValue(node, 'mcp_binding'), { mono: true }),
        field('允许工具', tools.join(', '), { mono: true }),
        field('远端地址', node.endpoint || readNodeValue(node, 'endpoint'), { mono: true }),
        field('超时时间', configured(node.timeout_ms) ? `${node.timeout_ms} ms` : readNodeValue(node, 'timeout_ms')),
      ])
    case 'routing':
      return result('触发与路由', '节点何时执行，以及每一种结果将流向哪里。', [
        field('触发动作', node.action || readNodeValue(node, 'action'), { mono: true }),
        field('条件表达式', readNodeValue(node, 'condition', 'route_expression'), { mono: true }),
        field('命名路由', routes, { mono: true }),
        field('默认路由', readNodeValue(node, 'default_route', 'default')),
        field('上游连接', incomingEdges.map((edge) => edge.from).join(', ') || '无', { mono: true }),
        field('下游连接', outgoingEdges.map((edge) => `${edge.label ? `${edge.label}:` : ''}${edge.to}`).join(', ') || '无', { mono: true }),
      ])
    case 'safety':
      return result('权限与恢复', '副作用、授权、失败、审计和重放边界。', [
        field('副作用', getProtocolEffect(node), { mono: true }),
        field('权限策略', node.permission || readNodeValue(node, 'permission'), { mono: true }),
        field('失败策略', node.failure_policy || readNodeValue(node, 'failure_policy'), { mono: true }),
        field('重放策略', readNodeValue(node, 'replay_policy'), { mono: true }),
        field('幂等策略', readNodeValue(node, 'idempotency', 'idempotency_key'), { mono: true }),
        field('审计日志', configured(node.audit_log ?? readNodeValue(node, 'audit_log')) ? String(node.audit_log ?? readNodeValue(node, 'audit_log')) : ''),
      ])
    case 'runtime':
      return result('本次运行', '当前 Run 在这个节点上的真实状态、输入、输出和错误。', [
        field('节点状态', view.runStatusLabel, { tone: options.runState?.status === 'failed' ? 'danger' : options.runState?.status === 'completed' ? 'success' : 'default' }),
        field('关联事件', `${options.runEvents?.length || options.runState?.events.length || 0} 条`),
        field('执行动作', options.runState?.action, { mono: true }),
        field('输入键', options.runState?.inputKey, { mono: true }),
        field('输入摘要', options.runState?.inputValue),
        field('输出键', options.runState?.outputKey, { mono: true }),
        field('输出摘要', options.runState?.outputValue),
        field('最新事件', latestEvent?.message || latestEvent?.type),
        field('错误信息', options.runState?.errorMsg, { tone: options.runState?.errorMsg ? 'danger' : 'default' }),
      ])
    case 'artifacts':
      return result('产物与交付', '最终产物的来源、主输出、格式和保存位置。', [
        field('产物来源', input, { mono: true }),
        field('交付变量', output, { mono: true }),
        field('主输出', node.primary_output || readNodeValue(node, 'primary_output'), { mono: true }),
        field('产物类型', readNodeValue(node, 'artifact_type', 'format')),
        field('输出契约', node.output_contract || readNodeValue(node, 'output_contract'), { mono: true }),
        field('保存位置', readNodeValue(node, 'delivery_path', 'path', 'save_to'), { mono: true }),
      ])
    default:
      return result(view.infoSection.title, view.description, view.infoSection.fields)
  }
}
