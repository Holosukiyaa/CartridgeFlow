import type { FlowEvent, FlowGraph, TestProbeRange } from '../../api.ts'

export type NodeRunState = {
  status: 'idle' | 'running' | 'completed' | 'failed' | 'paused'
  inputKey?: string
  inputValue?: string
  outputKey?: string
  outputValue?: string
  action?: string
  errorMsg?: string
  pendingInteraction?: any
  decisionConsume?: any
  decisionValidationErrors?: any[]
  toolResults?: any[]
  uiHtml?: string
  uiMarkdown?: string
  events: FlowEvent[]
}

export function extractUiHtml(data: any) {
  if (typeof data?.ui_html === 'string' && data.ui_html.trim()) return data.ui_html
  const output = data?.output_value
  if (output && typeof output === 'object' && typeof output.html === 'string') return output.html
  if (typeof output !== 'string') return ''
  const text = output.trim()
  if (!text) return ''
  if (text.startsWith('<!doctype') || text.startsWith('<html') || text.includes('<body')) return output
  try {
    const parsed = JSON.parse(text)
    return typeof parsed?.html === 'string' ? parsed.html : ''
  } catch {
    return ''
  }
}

function extractUiMarkdown(data: any) {
  if (typeof data?.ui_markdown === 'string' && data.ui_markdown.trim()) return data.ui_markdown
  const output = data?.output_value
  if (output && typeof output === 'object' && typeof output.markdown === 'string') return output.markdown
  if (typeof output !== 'string') return ''
  try {
    const parsed = JSON.parse(output)
    return typeof parsed?.markdown === 'string' ? parsed.markdown : ''
  } catch {
    return ''
  }
}

export function buildNodeRunStates(graph: FlowGraph, events: FlowEvent[]) {
  const map = new Map<string, NodeRunState>()
  graph.nodes.forEach((node) => {
    map.set(node.id, { status: 'idle', events: [] })
  })

  events.forEach((event) => {
    const eventData = (event.data || {}) as any
    if (event.type === 'flow_edge_traversed') {
      const sourceId = String(eventData.from || '')
      const sourceState = map.get(sourceId)
      if (sourceState && sourceState.status !== 'failed') sourceState.status = 'completed'
      return
    }
    const nodeId = event.state
    if (!nodeId || !map.has(nodeId)) return
    const state = map.get(nodeId)!
    state.events.push(event)
    const data = eventData
    if (event.type === 'state_entered') {
      state.status = 'running'
      state.pendingInteraction = undefined
      state.errorMsg = undefined
      state.action = data.action || state.action
      return
    }
    if (event.type === 'lab_node_executed'
      || event.type === 'lab_node_skipped'
      || event.type === 'run_completed'
      || (String(event.type || '').startsWith('state_') && event.type !== 'state_entered')) {
      state.status = 'completed'
      state.pendingInteraction = undefined
    } else if (event.type === 'pending_interaction_answered') {
      state.status = 'completed'
      state.pendingInteraction = undefined
      state.errorMsg = undefined
    } else if (event.type === 'lab_node_failed' || event.type === 'run_failed') {
      state.status = 'failed'
      state.errorMsg = data.error_envelope?.message || data.error || data.reason || 'Node failed.'
      state.pendingInteraction = undefined
    } else if (event.type === 'lab_node_paused') {
      state.status = 'paused'
      state.pendingInteraction = data.pending_interaction
    } else {
      return
    }
    state.action = data.action || state.action
    state.inputKey = data.input_key || data.input || state.inputKey
    state.inputValue = data.input_value ?? state.inputValue
    state.outputKey = data.output || state.outputKey
    state.outputValue = data.output_value ?? state.outputValue
    state.toolResults = data.tool_results || state.toolResults
    state.decisionConsume = data.decision_consume || state.decisionConsume
    state.decisionValidationErrors = data.decision_validation_errors || state.decisionValidationErrors
    if (data.action === 'show_ui' || data.action === 'show_welcome' || data.action === 'render_ui' || data.action === 'show_result') {
      state.uiHtml = extractUiHtml(data) || state.uiHtml
      state.uiMarkdown = extractUiMarkdown(data) || state.uiMarkdown
    }
  })
  return map
}

export function getProbePayload(graph: FlowGraph, startId: string, endId: string): TestProbeRange | null {
  const nodes = graph.nodes
  const startIndex = nodes.findIndex((node) => node.id === startId)
  const endIndex = nodes.findIndex((node) => node.id === endId)
  if (startIndex < 0 || endIndex < 0) return null
  const from = Math.min(startIndex, endIndex)
  const to = Math.max(startIndex, endIndex)
  return {
    start_node_id: nodes[from].id,
    end_node_id: nodes[to].id,
    node_ids: nodes.slice(from, to + 1).map((node) => node.id),
  }
}

