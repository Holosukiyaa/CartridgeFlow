import type { FlowEdge, FlowNode } from '../../api.ts'
import { resolveNodeSemanticKind } from './flowNodeView.ts'

export type NodeDetailSection =
  | 'contract'
  | 'inputs'
  | 'outputs'
  | 'component'
  | 'model'
  | 'resources'
  | 'routing'
  | 'safety'
  | 'runtime'
  | 'artifacts'
  | 'config'

export type NodeDetailSectionMeta = {
  id: NodeDetailSection
  label: string
  description: string
  width: number
  height: number
  connectorFraction: number
}

export type OpenNodeDetail = {
  nodeId: string
  section: NodeDetailSection
  pinned: boolean
  position?: { x: number; y: number }
}

export const NODE_DETAIL_SECTIONS: NodeDetailSectionMeta[] = [
  { id: 'contract', label: '执行契约', description: 'kind、执行器、副作用与配置健康', width: 356, height: 300, connectorFraction: 0.16 },
  { id: 'inputs', label: '输入与前置条件', description: '输入变量、来源、契约与上游节点', width: 368, height: 300, connectorFraction: 0.26 },
  { id: 'outputs', label: '输出与后续节点', description: '输出变量、契约、主输出与消费方', width: 368, height: 290, connectorFraction: 0.38 },
  { id: 'component', label: '交互组件', description: '卡带 UI、模式、绑定与命名动作', width: 390, height: 314, connectorFraction: 0.46 },
  { id: 'model', label: '模型与决策', description: '模型角色、决策信封与消费投影', width: 402, height: 320, connectorFraction: 0.52 },
  { id: 'resources', label: '资源与工具', description: '本机角色、工具白名单与服务边界', width: 402, height: 320, connectorFraction: 0.6 },
  { id: 'routing', label: '触发与路由', description: '执行条件、动作结果与分支去向', width: 390, height: 320, connectorFraction: 0.68 },
  { id: 'safety', label: '权限与恢复', description: '授权、失败、审计与重放策略', width: 382, height: 314, connectorFraction: 0.76 },
  { id: 'runtime', label: '本次运行', description: '真实状态、输入、输出和错误', width: 424, height: 360, connectorFraction: 0.82 },
  { id: 'artifacts', label: '产物与交付', description: '主输出、格式与保存位置', width: 382, height: 300, connectorFraction: 0.88 },
  { id: 'config', label: '完整配置', description: '编辑这个节点支持的全部协议字段', width: 620, height: 720, connectorFraction: 0.94 },
]

export const NODE_DETAIL_SECTION_BY_ID = new Map(NODE_DETAIL_SECTIONS.map((section) => [section.id, section]))

const LEGACY_SECTION_MAP: Record<string, NodeDetailSection> = {
  basic: 'contract',
  type: 'contract',
  trigger: 'routing',
  io: 'outputs',
  actions: 'contract',
}

export function normalizeNodeDetailSection(value: unknown): NodeDetailSection | null {
  const id = String(value || '')
  if (NODE_DETAIL_SECTION_BY_ID.has(id as NodeDetailSection)) return id as NodeDetailSection
  return LEGACY_SECTION_MAP[id] || null
}

export function nodeDetailId(nodeId: string, section: NodeDetailSection) {
  return `${nodeId}:${section}`
}

function selectedSections(node: FlowNode): NodeDetailSection[] {
  switch (resolveNodeSemanticKind(node)) {
    case 'start': return ['inputs', 'routing']
    case 'terminal': return ['outputs', 'artifacts']
    case 'checkpoint': return ['contract', 'routing']
    case 'input': return ['inputs', 'outputs', 'contract']
    case 'interaction': return ['component', 'inputs', 'outputs', 'routing']
    case 'decision': return ['model', 'inputs', 'outputs', 'routing']
    case 'retrieval': return ['resources', 'inputs', 'outputs']
    case 'mcp_read': return ['resources', 'inputs', 'outputs']
    case 'mcp_execute': return ['resources', 'inputs', 'outputs', 'safety']
    case 'remote_call': return ['resources', 'inputs', 'outputs', 'safety']
    case 'transfer': return ['inputs', 'outputs', 'contract']
    case 'transform': return ['inputs', 'outputs', 'contract']
    case 'validation': return ['contract', 'inputs', 'routing']
    case 'routing': return ['routing', 'inputs', 'outputs']
    case 'gate': return ['contract', 'routing']
    case 'human_gate': return ['component', 'routing', 'safety']
    case 'delivery': return ['outputs', 'artifacts', 'safety']
    default: return ['contract', 'inputs', 'outputs', 'resources', 'safety']
  }
}

function contextualMeta(node: FlowNode, section: NodeDetailSection): NodeDetailSectionMeta {
  const base = NODE_DETAIL_SECTION_BY_ID.get(section)!
  const kind = resolveNodeSemanticKind(node)
  if (section === 'contract' && kind === 'validation') return { ...base, label: '校验契约', description: '被校验数据、规则和失败处理' }
  if (section === 'contract' && kind === 'gate') return { ...base, label: '门禁契约', description: '放行、拒绝和回流判定规则' }
  if (section === 'contract' && kind === 'checkpoint') return { ...base, label: '恢复边界', description: '检查点、持久化和恢复策略' }
  if (section === 'inputs' && kind === 'input') return { ...base, label: '输入契约', description: '真实来源、数据类型和写入约定' }
  if (section === 'outputs' && kind === 'terminal') return { ...base, label: '流程结果', description: '结束状态、最终结果和异常后续连接' }
  if (section === 'outputs' && kind === 'delivery') return { ...base, label: '交付输出', description: '交付变量、主输出和产物消费方' }
  if (section === 'routing' && kind === 'interaction') return { ...base, label: '交互动作路由', description: '用户动作和每个动作的去向' }
  if (section === 'routing' && (kind === 'gate' || kind === 'human_gate')) return { ...base, label: '判定结果路由', description: '通过、拒绝、退回和超时去向' }
  return base
}

export function getAvailableNodeDetailSections(node: FlowNode, options: {
  edges?: FlowEdge[]
  hasRunData?: boolean
  editable?: boolean
} = {}) {
  const sectionIds = selectedSections(node)
  if (options.hasRunData) sectionIds.push('runtime')
  if (options.editable && !node.locked && node.scope !== 'root') sectionIds.push('config')
  return [...new Set(sectionIds)].map((sectionId) => contextualMeta(node, sectionId))
}
