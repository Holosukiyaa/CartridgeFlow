import type { FlowEdge, FlowEngineeringRelation, FlowFiles, FlowGraph, FlowNode } from '../../api.ts'
import type { StudioToolResource } from '../../api.types.ts'
import { buildFlowNodeCardView, buildOutcomeNodeCardView, compactNodeValue, getNodePreflightIssues } from './flowNodeView.ts'
import { getProtocolEffect, getProtocolExecutor, getProtocolKind } from './nodeModel.ts'
import type { NodeRunState } from './runState.ts'

export type EngineeringFieldTone = 'input' | 'output' | 'binding' | 'route' | 'policy' | 'neutral'

export type EngineeringField = {
  key: string
  value: string
  meta?: string
  tone: EngineeringFieldTone
}

export type EngineeringSection = {
  id: 'inputs' | 'outputs' | 'bindings' | 'execution' | 'routes' | 'policies'
  label: string
  fields: EngineeringField[]
}

export type EngineeringDataRelation = {
  from: string
  to: string
  fromField: string
  toField: string
  label: string
  expression: string
  source: string
  kind: 'data' | 'dependency'
  type?: string
}

export type EngineeringNodeSource = {
  key: string
  path: string
  line: number
}

export type EngineeringNodeView = ReturnType<typeof buildEngineeringNodeView>

export type EngineeringResourceKind = 'ui' | 'mcp' | 'model' | 'tool' | 'resource'

export type EngineeringResourceView = {
  kind: EngineeringResourceKind
  kindLabel: string
  title: string
  reference: string
  detail: string
  stateLabel: string
  metadata: Array<{ label: string; value: string }>
}

export type EngineeringNodeRenderModel = {
  view: EngineeringNodeView
  resource?: EngineeringResourceView
  connectedFields: ReadonlySet<string>
  connectedInputs: ReadonlySet<string>
  connectedOutputs: ReadonlySet<string>
  dependencyInputs: ReadonlySet<string>
  dependencyOutputs: ReadonlySet<string>
}

export type EngineeringEdgeVisibility = {
  control: boolean
  data: boolean
  dependency: boolean
  branch: boolean
  failure: boolean
}

type ExecutionPlanRelation = FlowEngineeringRelation & {
  executable?: boolean
  plan_edge_id?: string
  plan_edge_kind?: string
  plan_transition?: string
}

export type EngineeringProjectionOptions = {
  executionPlanV1?: boolean
  includeResources?: boolean
}

export function recipeDisplayName(node: FlowNode | undefined, fallback = '') {
  const value = String(node?.display_name || node?.title || fallback).trim()
  return value.toLowerCase() === 'failed' ? '失败结束' : value
}

const ENGINEERING_RESOURCE_PREFIX = '__engineering_resource__:'

export function isEngineeringResourceNode(node: FlowNode) {
  return node.scope === 'engineering_resource' || node.id.startsWith(ENGINEERING_RESOURCE_PREFIX)
}

function resourceNodeId(type: string, id: string) {
  return `${ENGINEERING_RESOURCE_PREFIX}${encodeURIComponent(type)}:${encodeURIComponent(id)}`
}

function dependencyField(kind: string) {
  if (kind === 'model_dependency') return 'model_role'
  if (kind === 'component_dependency') return 'component_ref'
  if (kind === 'mcp_dependency') return 'mcp_binding'
  return 'allowed_tools'
}

function dependencyResourceType(relation: FlowEngineeringRelation) {
  if (relation.kind === 'mcp_dependency') return 'mcp'
  return relation.to?.type || relation.kind.replace(/_dependency$/, '')
}

function dependencyLabel(kind: string, id: string) {
  if (kind === 'model_dependency') return `模型依赖：${id}`
  if (kind === 'component_dependency') return `组件依赖：${id}`
  if (kind === 'mcp_dependency') return `MCP 依赖：${id}`
  return `工具依赖：${id}`
}

function normalizeResourceKind(type: string): EngineeringResourceKind {
  const normalized = type.toLowerCase()
  if (/component|ui|interaction/.test(normalized)) return 'ui'
  if (/mcp|remote/.test(normalized)) return 'mcp'
  if (/model/.test(normalized)) return 'model'
  if (/tool/.test(normalized)) return 'tool'
  return 'resource'
}

function resourceKindLabel(kind: EngineeringResourceKind) {
  if (kind === 'ui') return 'UI 资源'
  if (kind === 'mcp') return 'MCP 资源'
  if (kind === 'model') return '模型资源'
  if (kind === 'tool') return '工具资源'
  return '工程资源'
}

function splitResourceIdentity(reference: string) {
  const slash = reference.lastIndexOf('/')
  if (slash > 0 && slash < reference.length - 1) {
    return { service: reference.slice(0, slash), tool: reference.slice(slash + 1) }
  }
  const colon = reference.lastIndexOf(':')
  if (colon > 0 && colon < reference.length - 1) {
    return { service: reference.slice(0, colon), tool: reference.slice(colon + 1) }
  }
  return { service: '', tool: reference }
}

function buildEngineeringResourceView(node: FlowNode): EngineeringResourceView {
  const reference = String(node.params?.resource_id || node.title || node.id)
  const kind = normalizeResourceKind(String(node.params?.resource_type || 'resource'))
  const references = Array.isArray(node.params?.referenced_by)
    ? node.params.referenced_by.map(String).filter(Boolean)
    : []
  const referenceCount = references.length ? `${references.length} 个节点引用` : '工程投影'
  const identity = splitResourceIdentity(reference)
  if (kind === 'ui') {
    return {
      kind,
      kindLabel: resourceKindLabel(kind),
      title: reference,
      reference,
      detail: 'HTML / 交互预览',
      stateLabel: '只读资源',
      metadata: [
        { label: '组件引用', value: reference },
        { label: '类型', value: '交互组件' },
        { label: '使用情况', value: referenceCount },
      ],
    }
  }
  if (kind === 'mcp') {
    return {
      kind,
      kindLabel: resourceKindLabel(kind),
      title: reference,
      reference,
      detail: identity.service ? `${identity.service} / ${identity.tool}` : identity.tool,
      stateLabel: '待解析连接',
      metadata: [
        { label: '服务', value: identity.service || '未声明' },
        { label: '工具', value: identity.tool || reference },
        { label: '使用情况', value: referenceCount },
      ],
    }
  }
  if (kind === 'model') {
    return {
      kind,
      kindLabel: resourceKindLabel(kind),
      title: reference,
      reference,
      detail: '模型角色绑定',
      stateLabel: '待解析绑定',
      metadata: [
        { label: '模型角色', value: reference },
        { label: '供应方', value: '未绑定' },
        { label: '使用情况', value: referenceCount },
      ],
    }
  }
  return {
    kind,
    kindLabel: resourceKindLabel(kind),
    title: reference,
    reference,
    detail: kind === 'tool' ? '工具依赖' : '工程依赖',
    stateLabel: '只读资源',
    metadata: [
      { label: '资源标识', value: reference },
      { label: '类型', value: kind === 'tool' ? '工具' : '工程资源' },
      { label: '使用情况', value: referenceCount },
    ],
  }
}

function mapAnalyzerRelation(relation: FlowEngineeringRelation): EngineeringDataRelation | null {
  if (relation.kind === 'data') {
    const from = relation.from?.node_id
    const to = relation.to?.node_id
    const fromField = relation.from?.port
    const toField = relation.to?.port
    if (!from || !to || !fromField || !toField) return null
    return {
      from,
      to,
      fromField,
      toField,
      label: `${fromField} -> ${toField}`,
      expression: `${from}.${fromField} -> ${to}.${toField}`,
      source: (relation.derived_from || []).join(', '),
      kind: 'data',
      type: relation.kind,
    }
  }

  if (!relation.kind.endsWith('_dependency')) return null
  const from = relation.from?.node_id
  const targetType = dependencyResourceType(relation)
  const targetId = relation.to?.id
  if (!from || !targetId) return null
  return {
    from,
    to: resourceNodeId(targetType, targetId),
    fromField: dependencyField(relation.kind),
    toField: 'resource',
    label: dependencyLabel(relation.kind, targetId),
    expression: `${from} requires ${targetType}:${targetId}`,
    source: (relation.derived_from || []).join(', '),
    kind: 'dependency',
    type: relation.kind,
  }
}

function buildEngineeringResourceNodes(relations: FlowEngineeringRelation[]): FlowNode[] {
  const resources = new Map<string, FlowNode>()
  relations.forEach((relation) => {
    if (!relation.kind.endsWith('_dependency')) return
    const type = dependencyResourceType(relation)
    const id = relation.to?.id
    if (!id) return
    const nodeId = resourceNodeId(type, id)
    const existing = resources.get(nodeId)
    if (existing) {
      const referencedBy = Array.isArray(existing.params?.referenced_by) ? existing.params.referenced_by : []
      if (relation.from?.node_id && !referencedBy.includes(relation.from.node_id)) referencedBy.push(relation.from.node_id)
      existing.params = { ...(existing.params || {}), referenced_by: referencedBy }
      return
    }
    resources.set(nodeId, {
      id: nodeId,
      title: id,
      display_name: id,
      type: 'engineering_resource',
      kind: 'resource',
      executor: 'base',
      effect: 'none',
      scope: 'engineering_resource',
      locked: true,
      inputs: {
        resource: {
          required: true,
          schema: { type: `${type}_reference` },
        },
      },
      params: {
        engineering_resource: true,
        resource_type: type,
        resource_id: id,
        referenced_by: relation.from?.node_id ? [relation.from.node_id] : [],
      },
      x: 0,
      y: 0,
    })
  })
  return [...resources.values()]
}

function planEdgeScope(kind: string) {
  if (kind === 'failure') return 'failure'
  if (kind === 'fork') return 'branch'
  return 'root'
}

function buildExecutionPlanEdges(relations: FlowEngineeringRelation[]): FlowEdge[] {
  return relations.flatMap((source) => {
    const relation = source as ExecutionPlanRelation
    const from = relation.from?.node_id
    const to = relation.to?.node_id
    const planEdgeId = String(relation.plan_edge_id || '').trim()
    const planEdgeKind = String(relation.plan_edge_kind || '').trim()
    const transition = String(relation.plan_transition || 'transition').trim()
    if (relation.kind !== 'execution_plan_edge' || relation.runtime_effect !== true || relation.executable !== true || !from || !to || !planEdgeId || !planEdgeKind) return []
    return [{
      from,
      to,
      scope: planEdgeScope(planEdgeKind),
      label: transition === 'loop_exit' ? '循环退出' : planEdgeId,
      plan_edge_id: planEdgeId,
      plan_edge_kind: planEdgeKind,
      plan_transition: transition,
    } as FlowEdge]
  })
}

export function buildEngineeringProjection(graph: FlowGraph, options: EngineeringProjectionOptions = {}) {
  const analyzerRelations = graph.engineering_relations || []
  const authoritativeRelations = analyzerRelations.map(mapAnalyzerRelation).filter((relation): relation is EngineeringDataRelation => Boolean(relation))
  const executionPlanEdges = options.executionPlanV1 ? buildExecutionPlanEdges(analyzerRelations) : null
  const projectedGraph = executionPlanEdges ? { ...graph, edges: executionPlanEdges } : graph
  if (!analyzerRelations.length) return {
    graph: projectedGraph,
    relations: options.executionPlanV1 ? [] : buildLegacyEngineeringDataRelations(graph),
    resourceCount: 0,
    controlEdgeCount: executionPlanEdges?.length || 0,
  }
  const includeResources = options.includeResources !== false
  const resourceNodes = includeResources ? buildEngineeringResourceNodes(analyzerRelations) : []
  return {
    graph: resourceNodes.length ? { ...projectedGraph, nodes: [...projectedGraph.nodes, ...resourceNodes] } : projectedGraph,
    relations: includeResources ? authoritativeRelations : authoritativeRelations.filter((relation) => relation.kind === 'data'),
    resourceCount: resourceNodes.length,
    controlEdgeCount: executionPlanEdges?.length ?? projectedGraph.edges.length,
  }
}

function displayValue(value: unknown, fallback = '-') {
  if (value === undefined || value === null || value === '') return fallback
  if (typeof value === 'string') return value
  try { return JSON.stringify(value) } catch { return String(value) }
}

function valueType(value: unknown) {
  if (Array.isArray(value)) return 'array'
  if (value === null) return 'null'
  if (typeof value === 'object') return 'object'
  return typeof value
}

function parseSchema(value: unknown): unknown {
  if (typeof value !== 'string') return value
  const trimmed = value.trim()
  if (!trimmed.startsWith('{') && !trimmed.startsWith('[')) return value
  try { return JSON.parse(trimmed) } catch { return value }
}

function schemaFields(value: unknown, tone: EngineeringFieldTone): EngineeringField[] {
  const schema = parseSchema(value)
  if (!schema) return []
  if (typeof schema === 'string') return [{ key: 'contract', value: schema, meta: 'schema', tone }]
  if (Array.isArray(schema)) return schema.slice(0, 6).map((item, index) => ({
    key: String((item as any)?.name || (item as any)?.id || index),
    value: displayValue((item as any)?.type || item),
    meta: (item as any)?.required === true ? 'required' : undefined,
    tone,
  }))
  if (typeof schema !== 'object') return [{ key: 'value', value: displayValue(schema), meta: valueType(schema), tone }]

  const record = schema as Record<string, any>
  const properties = record.properties && typeof record.properties === 'object' ? record.properties : record
  const required = new Set(Array.isArray(record.required) ? record.required.map(String) : [])
  return Object.entries(properties).slice(0, 8).map(([key, item]) => {
    const itemRecord = item && typeof item === 'object' ? item as Record<string, unknown> : null
    return {
      key,
      value: itemRecord ? displayValue(itemRecord.type || itemRecord.$ref || itemRecord.enum || item) : displayValue(item),
      meta: required.has(key) || itemRecord?.required === true ? 'required' : undefined,
      tone,
    }
  })
}

function recordFields(value: unknown, tone: EngineeringFieldTone): EngineeringField[] {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return []
  return Object.entries(value as Record<string, unknown>).slice(0, 8).map(([key, item]) => ({
    key,
    value: displayValue(item),
    meta: valueType(item),
    tone,
  }))
}

function protocolPortFields(value: unknown, tone: 'input' | 'output'): EngineeringField[] {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return []
  return Object.entries(value as Record<string, unknown>).slice(0, 12).map(([key, descriptor]) => {
    const item = descriptor && typeof descriptor === 'object' && !Array.isArray(descriptor)
      ? descriptor as Record<string, any>
      : {}
    const schema = item.schema && typeof item.schema === 'object' ? item.schema : {}
    const binding = item.binding && typeof item.binding === 'object' ? item.binding : {}
    const target = item.target && typeof item.target === 'object' ? item.target : {}
    const valueLabel = tone === 'input'
      ? [schema.type || item.type || 'any', binding.node_id && binding.output ? `${binding.node_id}.${binding.output}` : ''].filter(Boolean).join(' <- ')
      : [schema.type || item.type || 'any', target.key || target.path || ''].filter(Boolean).join(' -> ')
    return {
      key,
      value: valueLabel,
      meta: tone === 'input' ? item.required === true ? 'required' : binding.source || 'optional' : target.type || 'output',
      tone,
    }
  })
}

function uniqueFields(fields: EngineeringField[]) {
  const seen = new Set<string>()
  return fields.filter((field) => {
    const signature = `${field.key}:${field.value}`
    if (!field.value || field.value === '-' || seen.has(signature)) return false
    seen.add(signature)
    return true
  })
}

function addField(fields: EngineeringField[], key: string, value: unknown, tone: EngineeringFieldTone, meta?: string) {
  if (value === undefined || value === null || value === '') return
  fields.push({ key, value: displayValue(value), tone, meta })
}

function splitNames(value: unknown): string[] {
  if (Array.isArray(value)) return value.flatMap(splitNames)
  if (typeof value !== 'string') return []
  const normalized = value.trim().replace(/^\$\{(.+)\}$/, '$1')
  if (!normalized || normalized.startsWith('{') || normalized.startsWith('[')) return []
  return normalized.split(/[,\n]/).map((item) => item.trim()).filter(Boolean)
}

function fieldNameFromReference(value: unknown) {
  const text = String(value || '').trim().replace(/^store:/, '').replace(/^\$\{(.+)\}$/, '$1')
  if (!text || text.includes(' ') || text.startsWith('{') || text.startsWith('[')) return ''
  return text.split('.').filter(Boolean).at(-1) || ''
}

function fieldCandidatesFromReference(value: unknown) {
  const text = String(value || '').trim().replace(/^store:/, '').replace(/^\$\{(.+)\}$/, '$1')
  if (!text || text.includes(' ') || text.startsWith('{') || text.startsWith('[')) return []
  const parts = text.split('.').filter(Boolean)
  return [...new Set([parts.at(-1), parts[0]].filter((item): item is string => Boolean(item)))]
}

function declaredOutputFields(node: FlowNode) {
  const params = node.params || {}
  const names = new Set<string>([
    ...splitNames(node.output),
    ...splitNames(node.primary_output),
    ...splitNames(params.output),
    ...splitNames(params.output_name),
    ...splitNames(params.save_to),
  ])
  return [...names]
}

function outputContractType(node: FlowNode) {
  const contract = parseSchema(node.output_contract)
  if (contract && typeof contract === 'object' && !Array.isArray(contract)) {
    const type = (contract as Record<string, unknown>).type
    if (typeof type === 'string') return type
  }
  return node.output_contract ? 'contract' : 'declared output'
}

function describeDataFlow(target: FlowNode, sourceField: string, targetField: string) {
  const labels = (target.params?.data_labels || target.params?.field_labels || {}) as Record<string, unknown>
  const declaredLabel = String(labels[targetField] || '').trim()
  if (declaredLabel) return declaredLabel
  const action = String(target.action || '').toLowerCase()
  if (/render|interaction|show_ui/.test(action)) return `提供界面渲染数据：${sourceField} -> ${targetField}`
  if (/tool|mcp|remote/.test(action)) return `提交工具调用参数：${sourceField} -> ${targetField}`
  if (/llm|decision|prompt|agent/.test(action)) return `作为模型上下文：${sourceField} -> ${targetField}`
  if (target.type === 'terminal' || /complete|end/.test(action)) return `传递最终交付结果：${sourceField} -> ${targetField}`
  return `传递数据：${sourceField} -> ${targetField}`
}

function relationKind(target: FlowNode): EngineeringDataRelation['kind'] {
  const action = String(target.action || '').toLowerCase()
  return target.tool_binding || target.mcp_binding || target.allowed_tools?.length || /tool|mcp|remote/.test(action)
    ? 'dependency'
    : 'data'
}

export function engineeringHandleId(direction: 'source' | 'target', field: string) {
  return `engineering-${direction}-${encodeURIComponent(field)}`
}

export function engineeringControlHandleId(direction: 'source' | 'target', side: 'left' | 'right' | 'top' | 'bottom' = 'left') {
  return `engineering-control-${direction}-${side}`
}

function buildLegacyEngineeringDataRelations(graph: FlowGraph): EngineeringDataRelation[] {
  const outputs = new Map<string, Array<{ node: FlowNode; field: string }>>()
  graph.nodes.forEach((node) => declaredOutputFields(node).forEach((field) => {
    const key = field.toLowerCase()
    outputs.set(key, [...(outputs.get(key) || []), { node, field }])
  }))

  const relations: EngineeringDataRelation[] = []
  const seen = new Set<string>()
  graph.nodes.forEach((target) => {
    const bindings = target.input_binding && typeof target.input_binding === 'object' ? target.input_binding : {}
    const params = target.params || {}
    const declarations: Array<{ field: string; reference: unknown; source: string }> = [
      ...Object.entries(bindings).map(([field, reference]) => ({ field, reference, source: `input_binding.${field}` })),
      ...splitNames(target.source || params.source || params.input).map((reference) => ({ field: fieldNameFromReference(reference) || 'input', reference, source: 'source' })),
    ]

    declarations.forEach(({ field, reference, source }) => {
      const referenceFields = fieldCandidatesFromReference(reference)
      if (!referenceFields.length) return
      const candidates = referenceFields.flatMap((fieldName) => outputs.get(fieldName.toLowerCase()) || [])
      candidates.forEach(({ node: sourceNode, field: sourceField }) => {
        if (sourceNode.id === target.id) return
        const signature = `${sourceNode.id}:${sourceField}->${target.id}:${field}`
        if (seen.has(signature)) return
        seen.add(signature)
        relations.push({
          from: sourceNode.id,
          to: target.id,
          fromField: sourceField,
          toField: field,
          label: describeDataFlow(target, sourceField, field),
          expression: `${sourceField} -> ${field}`,
          source,
          kind: relationKind(target),
        })
      })
    })
  })
  return relations
}

export function buildEngineeringDataRelations(graph: FlowGraph): EngineeringDataRelation[] {
  if (graph.engineering_relations?.length) {
    return graph.engineering_relations.map(mapAnalyzerRelation).filter((relation): relation is EngineeringDataRelation => Boolean(relation))
  }
  return buildLegacyEngineeringDataRelations(graph)
}

export function locateNodeSource(files: FlowFiles, nodeId: string) {
  const preferredKeys = ['root_flow', ...Object.keys(files).filter((key) => key !== 'root_flow')]
  for (const key of preferredKeys) {
    const content = files[key]
    if (!content) continue
    const lines = content.split(/\r?\n/)
    const lineIndex = lines.findIndex((line) => line.includes(`"${nodeId}"`) || line.includes(`'${nodeId}'`) || line.includes(`id: ${nodeId}`))
    if (lineIndex >= 0) return { key, path: key === 'root_flow' ? 'root.flow.json' : key, line: lineIndex + 1 }
  }
  return { key: 'root_flow', path: 'root.flow.json', line: 1 }
}

function buildNodeSourceIndex(files: FlowFiles, nodes: FlowNode[]) {
  const nodeIds = new Set(nodes.map((node) => node.id))
  const sourceByNode = new Map<string, EngineeringNodeSource>()
  const preferredKeys = ['root_flow', ...Object.keys(files).filter((key) => key !== 'root_flow')]
  for (const key of preferredKeys) {
    const content = files[key]
    if (!content) continue
    const lines = content.split(/\r?\n/)
    lines.forEach((line, lineIndex) => {
      const candidates = new Set<string>()
      for (const match of line.matchAll(/["']([^"']+)["']/g)) candidates.add(match[1])
      const yamlId = line.match(/\bid\s*:\s*["']?([^\s,"'}]+)/)?.[1]
      if (yamlId) candidates.add(yamlId)
      candidates.forEach((nodeId) => {
        if (!nodeIds.has(nodeId) || sourceByNode.has(nodeId)) return
        sourceByNode.set(nodeId, {
          key,
          path: key === 'root_flow' ? 'root.flow.json' : key,
          line: lineIndex + 1,
        })
      })
    })
  }
  nodes.forEach((node) => {
    if (!sourceByNode.has(node.id)) sourceByNode.set(node.id, isEngineeringResourceNode(node)
      ? { key: 'analysis', path: 'Analyzer projection', line: 0 }
      : { key: 'root_flow', path: 'root.flow.json', line: 1 })
  })
  return sourceByNode
}

export function buildEngineeringSections(node: FlowNode, graph: FlowGraph, indexedEdges?: { incoming: FlowEdge[]; outgoing: FlowEdge[] }): EngineeringSection[] {
  const params = node.params || {}
  const incoming = indexedEdges?.incoming || graph.edges.filter((edge) => edge.to === node.id)
  const outgoing = indexedEdges?.outgoing || graph.edges.filter((edge) => edge.from === node.id)
  const inputs: EngineeringField[] = [
    ...protocolPortFields(node.inputs, 'input'),
    ...schemaFields(node.input_schema, 'input'),
  ]
  recordFields(node.input_binding, 'input').forEach((field) => {
    if (!inputs.some((input) => input.key === field.key)) inputs.push({ ...field, meta: 'binding' })
  })
  const inputSource = node.source || params.source || params.input
  if (!inputs.length) incoming.slice(0, 6).forEach((edge) => addField(inputs, edge.label || 'request', edge.from, 'input', 'node ref'))

  const outputs: EngineeringField[] = [...protocolPortFields(node.outputs, 'output')]
  const declaredOutputs = declaredOutputFields(node)
  declaredOutputs.forEach((name) => addField(outputs, name, outputContractType(node), 'output', node.primary_output === name ? 'primary' : 'output'))
  if (!outputs.length && node.output_contract) outputs.push(...schemaFields(node.output_contract, 'output'))
  if (!outputs.length && outgoing.length) addField(outputs, 'result', outgoing.map((edge) => edge.to).join(', '), 'output', 'object')

  const bindings = recordFields(node.input_binding, 'binding')
  addField(bindings, 'tool_binding', node.tool_binding, 'binding', 'tool')
  addField(bindings, 'allowed_tools', node.allowed_tools, 'binding', 'allowlist')
  addField(bindings, 'mcp_binding', node.mcp_binding, 'binding', 'mcp')
  addField(bindings, 'component_ref', node.component_ref, 'binding', 'component')

  const execution: EngineeringField[] = []
  addField(execution, 'source', inputSource, 'neutral', node.input_kind || 'input')
  addField(execution, 'kind', getProtocolKind(node) || node.kind || node.type, 'neutral', 'protocol')
  addField(execution, 'executor', getProtocolExecutor(node) || node.executor, 'neutral')
  addField(execution, 'action', node.action, 'neutral')
  addField(execution, 'effect', getProtocolEffect(node) || node.effect, 'neutral')
  addField(execution, 'model_role', node.model_role || node.agent, 'neutral')
  addField(execution, 'endpoint', node.endpoint, 'neutral')

  const routes = recordFields(node.action_routes, 'route')
  outgoing.slice(0, 8).forEach((edge) => addField(routes, edge.label || 'onSuccess', edge.to, 'route', edge.scope || 'root'))
  addField(routes, 'next', node.next, 'route')

  const policies: EngineeringField[] = []
  addField(policies, 'timeout_ms', node.timeout_ms || params.timeout_ms, 'policy', 'ms')
  addField(policies, 'failure_policy', node.failure_policy, 'policy')
  addField(policies, 'permission', node.permission, 'policy')
  addField(policies, 'audit_log', node.audit_log, 'policy', 'boolean')

  return [
    { id: 'inputs', label: '输入', fields: uniqueFields(inputs) },
    { id: 'outputs', label: '输出', fields: uniqueFields(outputs) },
    { id: 'bindings', label: '绑定', fields: uniqueFields(bindings) },
    { id: 'execution', label: '执行', fields: uniqueFields(execution) },
    { id: 'routes', label: '流转', fields: uniqueFields(routes) },
    { id: 'policies', label: '策略', fields: uniqueFields(policies) },
  ]
}

export function buildEngineeringNodeView(node: FlowNode, graph: FlowGraph, files: FlowFiles, runState?: NodeRunState) {
  const incomingEdges: FlowEdge[] = graph.edges.filter((edge) => edge.to === node.id)
  const outgoingEdges: FlowEdge[] = graph.edges.filter((edge) => edge.from === node.id)
  return buildEngineeringNodeViewFromParts(node, graph, runState, incomingEdges, outgoingEdges, locateNodeSource(files, node.id), getNodePreflightIssues(graph, node.id))
}

function buildEngineeringNodeViewFromParts(
  node: FlowNode,
  graph: FlowGraph,
  runState: NodeRunState | undefined,
  incomingEdges: FlowEdge[],
  outgoingEdges: FlowEdge[],
  source: EngineeringNodeSource,
  analysisFindings = getNodePreflightIssues(graph, node.id),
  toolCatalog?: Map<string, StudioToolResource>,
) {
  const presentation = buildFlowNodeCardView(node, runState, { incomingEdges, outgoingEdges, analysisFindings })
  const guided = buildOutcomeNodeCardView(node, runState, { incomingEdges, outgoingEdges, analysisFindings })
  // An authored description is the real guidance for users; the template copy
  // is only a fallback so the card never looks empty.
  const authoredDescription = String((node.params as Record<string, unknown> | undefined)?.description || '').trim()
  return {
    ...presentation,
    what: authoredDescription || guided.what,
    beginnerTip: guided.beginnerTip,
    remoteSources: resolveRemoteSources(node, toolCatalog),
    sections: buildEngineeringSections(node, graph, { incoming: incomingEdges, outgoing: outgoingEdges }),
    source,
    raw: JSON.stringify(node, null, 2),
    idLabel: compactNodeValue(node.id, 'unknown', 30),
  }
}

export type EngineeringRemoteSource = {
  name: string
  url: string
}

// Resolve a node's referenced remote tools (server/tool pairs in params.tools or
// mcp_binding) to concrete endpoints from the studio resource catalog, so the
// recipe shows the real addresses instead of opaque tool ids.
function resolveRemoteSources(node: FlowNode, toolCatalog?: Map<string, StudioToolResource>): EngineeringRemoteSource[] {
  if (!toolCatalog || toolCatalog.size === 0) return []
  const found: EngineeringRemoteSource[] = []
  const push = (server: string | undefined, tool: string | undefined) => {
    if (!server || !tool) return
    const resource = toolCatalog.get(`${server}/${tool}`)
    if (resource?.endpoint) {
      found.push({ name: resource.name || tool, url: resource.endpoint })
    }
  }
  const params = (node.params || {}) as Record<string, unknown>
  const tools = params.tools
  if (Array.isArray(tools)) {
    for (const item of tools) {
      if (!item || typeof item !== 'object') continue
      const record = item as Record<string, unknown>
      push(String(record.server || ''), String(record.tool || ''))
    }
  }
  const mcpBinding = node.mcp_binding as { server?: string } | undefined
  if (mcpBinding?.server) {
    const allowed = node.allowed_tools || (node.mcp_binding as Record<string, unknown>).allowed_tools
    if (Array.isArray(allowed)) {
      for (const toolId of allowed) push(mcpBinding.server, String(toolId))
    }
  }
  return found
}

export function buildEngineeringNodeModels(
  graph: FlowGraph,
  files: FlowFiles,
  runStates: Map<string, NodeRunState> | undefined,
  dataRelations: EngineeringDataRelation[],
  toolCatalog?: Map<string, StudioToolResource>,
) {
  const incomingByNode = new Map<string, FlowEdge[]>()
  const outgoingByNode = new Map<string, FlowEdge[]>()
  graph.nodes.forEach((node) => {
    incomingByNode.set(node.id, [])
    outgoingByNode.set(node.id, [])
  })
  graph.edges.forEach((edge) => {
    incomingByNode.get(edge.to)?.push(edge)
    outgoingByNode.get(edge.from)?.push(edge)
  })

  const relationsByNode = new Map<string, EngineeringDataRelation[]>()
  graph.nodes.forEach((node) => relationsByNode.set(node.id, []))
  dataRelations.forEach((relation) => {
    relationsByNode.get(relation.from)?.push(relation)
    if (relation.to !== relation.from) relationsByNode.get(relation.to)?.push(relation)
  })

  const sourceByNode = buildNodeSourceIndex(files, graph.nodes)
  const models = new Map<string, EngineeringNodeRenderModel>()
  graph.nodes.forEach((node) => {
    const relations = relationsByNode.get(node.id) || []
    const connectedInputs = new Set(relations.filter((relation) => relation.to === node.id).map((relation) => relation.toField))
    const connectedOutputs = new Set(relations.filter((relation) => relation.from === node.id).map((relation) => relation.fromField))
    models.set(node.id, {
      view: buildEngineeringNodeViewFromParts(
        node,
        graph,
        runStates?.get(node.id),
        incomingByNode.get(node.id) || [],
        outgoingByNode.get(node.id) || [],
        sourceByNode.get(node.id)!,
        getNodePreflightIssues(graph, node.id),
        toolCatalog,
      ),
      resource: isEngineeringResourceNode(node) ? buildEngineeringResourceView(node) : undefined,
      connectedFields: new Set([...connectedInputs, ...connectedOutputs]),
      connectedInputs,
      connectedOutputs,
      dependencyInputs: new Set(relations.filter((relation) => relation.to === node.id && relation.kind === 'dependency').map((relation) => relation.toField)),
      dependencyOutputs: new Set(relations.filter((relation) => relation.from === node.id && relation.kind === 'dependency').map((relation) => relation.fromField)),
    })
  })
  return models
}

export type EngineeringRecipeItem = {
  label: string
  value: string
  data?: unknown
  mono?: boolean
  /** Long/prose values are summarized on the canvas but remain complete in the inspector. */
  long?: boolean
}

const ENGINEERING_LABELS: Record<string, string> = {
  type: '类型', kind: '处理类别', action: '动作', executor: '执行器', effect: '副作用', scope: '作用范围',
  source: '输入来源', input: '输入', output: '输出', result: '处理结果', endpoint: '服务地址', model_role: '模型角色',
  agent: '代理角色', component_ref: '组件引用', tool_binding: '工具绑定', allowed_tools: '允许的工具', mcp_binding: 'MCP 绑定',
  input_binding: '输入绑定', input_schema: '输入结构', output_contract: '输出契约', primary_output: '主要输出', action_routes: '动作路由',
  next: '下一步', onSuccess: '成功后', onFailure: '失败后', timeout_ms: '超时', failure_policy: '失败策略', permission: '权限',
  audit_log: '审计记录', required: '必填', optional: '可选', schema: '数据结构', contract: '契约', value: '值',
  description: '说明', title: '标题', name: '名称', objects: '对象列表', material: '材质', position: '位置', motion: '运动',
  camera: '镜头', controls: '交互控制', extra: '补充说明', scene_design: '场景设计', summary: '摘要', status: '状态', payload: '结果数据',
  requirements: '场景需求', research: '参考资料', research_bundle: '资料汇总', research_bundle_raw: '原始资料汇总',
  scene_spec: '场景规格', scene_title: '场景标题', scene_code: '场景代码', scene_code_core: '场景核心代码', scene_html: '场景页面',
  scene_spec_out: '场景规格输出契约', scene_code_core_out: '场景代码输出契约', scene_code_core_rev: '场景代码修订契约',
  approval: '审核结论', feedback: '修改意见', design: '设计数据', terrain: '地形', lighting: '光照', interaction: '交互方式', palette: '配色',
  template_file: '模板文件', variables: '变量映射', scene_page: '场景产物',
}

const ENGINEERING_KEY_TOKENS: Record<string, string> = {
  news: '新闻', selection: '选择', fact: '事实', facts: '事实', check: '核查', decision: '决策', daily: '每日', brief: '简报',
  video: '视频', render: '渲染', delivery: '交付', complete: '完成', request: '请求', rss: 'RSS', fetch: '抓取', bundle: '汇总',
  failure: '失败', collect: '收集', selected: '已选择', script: '脚本', review: '审核', result: '结果', raw: '原始',
  scene: '场景', code: '代码', core: '核心', page: '页面', spec: '规格', research: '资料', requirements: '需求', output: '输出', input: '输入',
}

const ENGINEERING_VALUE_LABELS: Record<string, string> = {
  process: '处理节点', terminal: '结束节点', start: '开始节点', root: '主流程', object: '对象', string: '文本',
  number: '数字', integer: '整数', boolean: '布尔值', array: '列表', required: '必填', optional: '可选', store: '存储',
  output: '输出', input: '输入', binding: '绑定', node: '节点', 'node ref': '节点引用', protocol: '协议字段',
  primary: '主要输出', allowlist: '允许列表', mcp: 'MCP 工具', component: '交互组件', ms: '毫秒', schema: '数据结构',
  'declared output': '已声明输出', read_only: '只读', none: '无副作用', true: '是', false: '否',
  llm_prompt: '调用 AI 模型', tool_call: '调用工具', mcp_read: '读取外部数据', remote_call: '调用远程服务',
  collect_inputs: '采集用户输入', collect_artifacts: '整理交付产物', pass_result: '汇总处理结果', confirm_checkpoint: '等待人工确认',
  render_template: '渲染页面模板', render_video_brief: '生成视频简报', ai_decision: 'AI 决策', human_review: '人工审核',
  transform: '数据转换', sub_flow: '子流程', deterministic: '确定性执行', model: '模型执行', base: '基座执行',
  decision: 'AI 决策', llm: '大语言模型', architect: '场景架构师', resolved: '已解析', contract: '契约', artifact: '产物',
}

export function humanizeEngineeringKey(value: string) {
  const key = String(value || '').trim()
  if (!key) return '-'
  if (ENGINEERING_LABELS[key]) return ENGINEERING_LABELS[key]
  return key.split(/[_-]+/).map((token) => ENGINEERING_KEY_TOKENS[token.toLowerCase()] || token).join('')
}

export function humanizeEngineeringValue(value: string) {
  const text = String(value ?? '').trim()
  if (ENGINEERING_VALUE_LABELS[text]) return ENGINEERING_VALUE_LABELS[text]
  const typedReference = text.match(/^([^\s]+)\s*->\s*(.+)$/)
  if (typedReference && ENGINEERING_VALUE_LABELS[typedReference[1]]) {
    return `${ENGINEERING_VALUE_LABELS[typedReference[1]]} -> ${typedReference[2]}`
  }
  return text
}

function recipeValue(value: unknown): string {
  if (value === undefined || value === null) return ''
  if (typeof value === 'string') return value.trim()
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}

export function summarizeEngineeringRecipeItem(item: EngineeringRecipeItem, limit = 92): string {
  if (item.data && typeof item.data === 'object') {
    const count = Array.isArray(item.data) ? item.data.length : Object.keys(item.data as Record<string, unknown>).length
    const keys = Array.isArray(item.data)
      ? []
      : Object.keys(item.data as Record<string, unknown>).slice(0, 3)
    return `${count} 项${keys.length ? ` · ${keys.map(humanizeEngineeringKey).join(' / ')}` : ''}`
  }
  const normalized = item.value.replace(/\s+/g, ' ').trim()
  if (!normalized) return ''
  const prefix = normalized.length > limit ? `${normalized.slice(0, limit)}...` : normalized
  return item.long ? `${normalized.length} 字符 · ${prefix}` : prefix
}

function recipeTools(node: FlowNode): string[] {
  const params = (node.params || {}) as Record<string, unknown>
  const paramsTools = Array.isArray(params.tools) ? params.tools : []
  const declared = [...(node.tools || []), ...paramsTools]
    .filter((tool): tool is { server?: string; tool?: string } => Boolean(tool && typeof tool === 'object'))
  const names = declared.map((tool) => [tool.server, tool.tool].filter(Boolean).join('.'))
  return [...new Set(names)].filter(Boolean)
}

/** Builds the "how this machine works" recipe for a node, by action. */
export function buildEngineeringRecipe(node: FlowNode): EngineeringRecipeItem[] {
  const action = String(node.action || '')
  const params = node.params || {}
  // Prompt/options live on the raw state record (node.data), not on FlowNode.
  const raw = node.data && typeof node.data === 'object' ? node.data as Record<string, unknown> : {}
  const items: EngineeringRecipeItem[] = []
  const push = (label: string, value: unknown, mono = false) => {
    const text = recipeValue(value)
    if (text) items.push({
      label,
      value: text,
      data: typeof value === 'object' && value !== null ? value : undefined,
      mono,
      long: text.length > 80 || text.includes('\n'),
    })
  }

  if (action === 'llm_prompt') {
    push('模型角色', node.model_role || params.model_role, true)
    const llm = (params.llm_options || raw.llm_options) as Record<string, unknown> | undefined
    if (llm && (llm.max_tokens || llm.timeout_seconds)) {
      push('模型参数', `最大输出 ${llm.max_tokens ?? '-'} · 超时 ${llm.timeout_seconds ?? '-'} 秒`, true)
    }
    push('系统指令', raw.system_prompt || params.system_prompt)
    push('处理指令', raw.prompt || params.prompt || params.target || params.format)
    const contract = node.decision_contract as { consume?: { path?: string; as?: string } } | undefined
    if (contract?.consume?.path) {
      push('输出结构', `${contract.consume.path} → ${contract.consume.as || 'output'}`, true)
    }
  } else if (action === 'tool_call' || action === 'remote_call' || action === 'mcp_read') {
    const tools = recipeTools(node)
    if (tools.length) push('调用工具', tools.join('、'), true)
    push('资源角色', params.resource_role || node.tool_binding)
    push('远端地址', node.endpoint || params.endpoint, true)
    if (node.timeout_ms) push('超时', `${node.timeout_ms} ms`, true)
  } else if (action === 'render_video_brief') {
    const preset = params.preset_config as Record<string, unknown> | undefined
    if (preset?.voice) push('语音', preset.voice, true)
    push('输出', params.output, true)
  } else if (action === 'pass_result') {
    push('合并键', params.items || params.input, true)
    push('输出键', params.output, true)
    if (params.max_chars_per_item) push('单条上限', `${params.max_chars_per_item} 字符`, true)
  } else if (action === 'collect_inputs') {
    push('采集字段', Array.isArray(params.fields) ? params.fields.join('、') : params.fields, true)
    const defaults = params.defaults as Record<string, unknown> | undefined
    if (defaults) push('默认值', defaults, true)
  } else if (action === 'confirm_checkpoint') {
    const interaction = params.interaction as { store_key?: string; prompt?: string } | undefined
    push('审核键', interaction?.store_key || params.output, true)
    push('审核提示', params.message || interaction?.prompt || params.title)
  } else if (action === 'collect_artifacts') {
    push('交付输出', params.output, true)
    push('输入来源', params.input, true)
  } else {
    const tools = recipeTools(node)
    if (tools.length) push('绑定工具', tools.join('、'), true)
    if (Object.keys(params).length) push('参数配置', params, true)
  }
  return items
}
