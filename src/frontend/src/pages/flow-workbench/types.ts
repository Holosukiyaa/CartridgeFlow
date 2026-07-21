import type { FlowFiles, FlowGraph, FlowLabDetail, FlowNode, ValidationResponse } from '../../api.ts'

export type WorkbenchMode = 'design' | 'run' | 'models'
export type NodeCategoryId = 'input' | 'ui' | 'process' | 'tool' | 'remote' | 'transfer' | 'store' | 'control' | 'custom'

export type NodePreset = {
  id: string
  label: string
  description: string
  fields: Array<{ key: string; label: string; placeholder?: string; multiline?: boolean }>
}

export type NodeCategory = {
  id: NodeCategoryId
  label: string
  shortLabel: string
  templateId: string
  defaultType: string
  defaultAction: string
  defaultTitle: string
  description: string
  examples: string[]
  color: string
  bg: string
}

export type NodeDraft = {
  title: string
  category: NodeCategoryId
  preset: string
  presetConfig: Record<string, string>
  type: string
  action: string
  next: string
  kind: string
  executor: string
  effect: string
  displaySuffix: string
  inputKind: string
  source: string
  inputSchema: string
  outputContract: string
  decisionContract: string
  decisionTestMode: string
  mockDecisionEnvelope: string
  primaryOutput: string
  toolBinding: string
  allowedTools: string
  mcpBinding: string
  failurePolicy: string
  permission: string
  auditLog: boolean
  description: string
  input: string
  output: string
  saveTo: string
  condition: string
  agent: string
  modelRole: string
  tools: string
  params: string
}

export type GraphResult = {
  files: FlowFiles
  graph: FlowGraph
  validation?: ValidationResponse
  node_id?: string
}

export type CreateNodeHandler = (
  sourceNode: FlowNode | null,
  categoryId: NodeCategoryId,
  insertMode: 'insert' | 'branch',
) => Promise<void>

export type WorkbenchDetailProps = {
  detail: FlowLabDetail
  flowId: string
  files: FlowFiles
}
