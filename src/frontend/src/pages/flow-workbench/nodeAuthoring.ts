import type { FlowFiles, FlowGraph, FlowNode, InteractionComponent } from '../../api.ts'
import { resolveNodeSemanticKind } from './flowNodeView.ts'
import type { NodeDetailSection } from './nodeDetails.ts'

export type NodeAuthoringStep = {
  section: NodeDetailSection
  label: string
  hint: string
  complete: boolean
}

export type NodeAuthoringPath = {
  steps: NodeAuthoringStep[]
  completed: number
  total: number
  next: NodeAuthoringStep | null
  complete: boolean
}

function nonEmpty(value: unknown) {
  return Array.isArray(value) ? value.length > 0 : Boolean(String(value || '').trim())
}

function recordValue(value: unknown) {
  if (value && typeof value === 'object' && !Array.isArray(value)) return value as Record<string, unknown>
  if (typeof value !== 'string') return null
  try {
    const parsed = JSON.parse(value || '{}')
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed as Record<string, unknown> : null
  } catch {
    return null
  }
}

function readComponents(files: FlowFiles) {
  try {
    const document = JSON.parse(files.interaction_components || '{}')
    return Array.isArray(document.components) ? document.components as InteractionComponent[] : []
  } catch {
    return []
  }
}

function hasOutput(node: FlowNode) {
  return nonEmpty(node.output) || nonEmpty(node.primary_output) || nonEmpty(node.params?.output) || nonEmpty(node.params?.save_to)
}

function hasInput(node: FlowNode) {
  return nonEmpty(node.params?.input) || nonEmpty(node.source) || nonEmpty(node.params?.source) || Boolean(Object.keys(node.input_binding || {}).length)
}

function hasOutgoing(node: FlowNode, graph: FlowGraph) {
  return graph.edges.some((edge) => edge.from === node.id) || nonEmpty(node.next)
}

function step(section: NodeDetailSection, label: string, hint: string, complete: boolean): NodeAuthoringStep {
  return { section, label, hint, complete }
}

export function buildNodeAuthoringPath(node: FlowNode, graph: FlowGraph, files: FlowFiles): NodeAuthoringPath | null {
  if (node.locked || node.scope === 'root') return null
  const kind = resolveNodeSemanticKind(node)
  if (kind === 'start' || kind === 'terminal') return null
  const params = node.params || {}
  let steps: NodeAuthoringStep[]

  if (kind === 'interaction') {
    const component = readComponents(files).find((item) => item.id === node.component_ref)
    const mode = String(node.interaction_mode || '')
    const waitsForUser = mode === 'collect' || mode === 'review'
    const componentReady = Boolean(component && component.supported_modes?.includes(mode as any))
      && (waitsForUser ? ['user', 'human'].includes(String(node.executor || '')) && node.effect === 'writes_store' : node.executor === 'deterministic' && node.effect === 'none')
    const bindings = recordValue(node.input_binding || {})
    const bindingsReady = Boolean(bindings && Object.values(bindings).every((value) => String(value || '').startsWith('store:') || String(value || '').startsWith('artifact:')))
    const routes = recordValue(node.action_routes || {})
    const actionIds = new Set((component?.actions || []).map((item) => item.id))
    const routesReady = !waitsForUser || Boolean(routes && Object.keys(routes).length && Object.entries(routes).every(([actionId, target]) => actionIds.has(actionId) && graph.nodes.some((item) => item.id === target)))
    steps = [
      step('component', '选择交互组件', '创建或选择页面，并确认展示、收集或审核模式', componentReady),
      step('inputs', '绑定输入数据', '把上游 Store 或 Artifact 映射到组件字段', bindingsReady),
      ...(waitsForUser ? [step('routing', '连接命名动作', '为组件开放的动作选择静态目标节点', routesReady)] : []),
      ...(waitsForUser ? [step('outputs', '声明交互输出', '保存用户提交的标准答案', hasOutput(node))] : []),
    ]
  } else if (kind === 'input') {
    steps = [
      step('inputs', '定义输入来源', '声明运行输入的来源、类型和契约', nonEmpty(node.source) && nonEmpty(node.input_schema)),
      step('outputs', '声明写入变量', '输入结果写入后续节点可引用的 Store 键', hasOutput(node)),
    ]
  } else if (kind === 'decision') {
    steps = [
      step('inputs', '选择决策输入', '选择需要交给模型判断的上游数据', hasInput(node)),
      step('model', '绑定模型角色', '使用清单中声明的模型角色和决策契约', nonEmpty(node.model_role) && Boolean(node.decision_contract)),
      step('outputs', '声明决策结果', '保存稳定的决策信封或消费投影', hasOutput(node)),
      step('routing', '连接决策去向', '把决策结果连接到后续节点', hasOutgoing(node, graph)),
    ]
  } else if (['mcp_read', 'mcp_execute', 'retrieval'].includes(kind)) {
    steps = [
      step('resources', '绑定执行工具', '选择清单中的工具并限制允许调用范围', nonEmpty(node.tool_binding) || nonEmpty(node.mcp_binding) || Boolean(node.allowed_tools?.length)),
      step('inputs', '映射调用输入', '指定工具调用所需的上游变量', hasInput(node)),
      step('outputs', '保存工具结果', '声明工具结果在 Store 中的键', hasOutput(node)),
    ]
  } else if (kind === 'remote_call') {
    steps = [
      step('resources', '配置远程适配器', '声明远端地址、权限和超时边界', nonEmpty(node.endpoint) || nonEmpty(params.endpoint)),
      step('inputs', '映射请求输入', '指定发送给远端适配器的数据', hasInput(node)),
      step('outputs', '保存远端结果', '声明远端结果在 Store 中的键', hasOutput(node)),
    ]
  } else if (['transfer', 'transform'].includes(kind)) {
    steps = [
      step('inputs', '选择处理输入', '选择需要传递或转换的上游变量', hasInput(node)),
      step('outputs', '声明处理输出', '保存处理后的结果变量', hasOutput(node)),
    ]
  } else if (kind === 'delivery') {
    steps = [
      step('outputs', '选择交付内容', '指定作为最终交付结果的主输出', hasOutput(node)),
      step('artifacts', '配置交付产物', '声明产物类型和保存位置', nonEmpty(params.artifact_type) || nonEmpty(params.delivery_path)),
    ]
  } else if (['routing', 'validation', 'gate', 'human_gate'].includes(kind)) {
    steps = [
      step('inputs', '选择判定输入', '选择需要校验或分流的数据', hasInput(node)),
      step('routing', '连接结果去向', '为判定结果配置后续节点', hasOutgoing(node, graph)),
    ]
  } else {
    steps = [
      step('contract', '确认执行契约', '确认节点类型、执行器和副作用', nonEmpty(node.kind) && nonEmpty(node.executor) && nonEmpty(node.effect)),
      step('inputs', '选择节点输入', '选择当前节点消费的上游变量', hasInput(node)),
      step('outputs', '声明节点输出', '声明后续节点可以引用的结果变量', hasOutput(node)),
    ]
  }

  const completed = steps.filter((item) => item.complete).length
  return { steps, completed, total: steps.length, next: steps.find((item) => !item.complete) || null, complete: completed === steps.length }
}
