import { updateFlowNode, type FlowFiles, type FlowNode } from '../../api.ts'
import { CATEGORY_BY_ID, buildProtocolNodePayload } from './nodeModel.ts'
import type { GraphResult, NodeDraft } from './types.ts'

function parseJsonField(value: string, label: string, fallback: unknown) {
  const text = String(value || '').trim()
  if (!text) return fallback
  try {
    return JSON.parse(text)
  } catch (error: any) {
    throw new Error(`${label}不是合法 JSON：${error.message}`)
  }
}

function setOptionalParam(params: Record<string, any>, key: string, value: unknown) {
  if (value === '' || value === undefined || value === null || value === false) delete params[key]
  else params[key] = value
}

export async function saveNodeDraft(flowId: string, files: FlowFiles, node: FlowNode, draft: NodeDraft): Promise<GraphResult> {
  const category = CATEGORY_BY_ID.get(draft.category)
  if (!category) throw new Error(`未知节点类型：${draft.category}`)

  const tools = parseJsonField(draft.tools, 'Tools', null)
  if (tools !== null && !Array.isArray(tools)) throw new Error('Tools JSON 必须是数组')
  const params = parseJsonField(draft.params, 'Params', {})
  if (!params || Array.isArray(params) || typeof params !== 'object') throw new Error('Params JSON 必须是对象')
  parseJsonField(draft.inputBinding, '输入绑定', {})
  parseJsonField(draft.actionRoutes, '动作路由', {})
  parseJsonField(draft.mcpBinding, 'MCP 绑定', {})
  if (draft.decisionContract.trim()) parseJsonField(draft.decisionContract, '决策契约', {})
  if (draft.timeoutMs && (!Number.isFinite(Number(draft.timeoutMs)) || Number(draft.timeoutMs) <= 0)) throw new Error('超时时间必须是大于 0 的数字')

  const nextParams = { ...params }
  Object.assign(nextParams, {
    node_category: draft.category,
    preset: draft.preset,
    preset_config: draft.presetConfig,
    description: draft.description,
    input: draft.input,
    output: draft.output,
    save_to: draft.saveTo,
    condition: draft.condition,
  })
  setOptionalParam(nextParams, 'optional_input', draft.optionalInput)
  setOptionalParam(nextParams, 'replay_policy', draft.replayPolicy)
  setOptionalParam(nextParams, 'idempotency', draft.idempotency)
  setOptionalParam(nextParams, 'artifact_type', draft.artifactType)
  setOptionalParam(nextParams, 'delivery_path', draft.deliveryPath)
  setOptionalParam(nextParams, 'model_role', draft.modelRole)

  return updateFlowNode(flowId, node.id, {
    files,
    title: draft.title,
    ...buildProtocolNodePayload(draft, category),
    next: draft.next,
    agent: draft.agent || null,
    model_role: draft.modelRole || null,
    tools,
    params: nextParams,
  })
}
