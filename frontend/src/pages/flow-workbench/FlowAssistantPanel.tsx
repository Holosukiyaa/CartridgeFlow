import { useEffect, useId, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import mermaid from 'mermaid'
import ReactMarkdown from 'react-markdown'
import { askFlowAssistant } from '../../api.ts'
import { Button } from '../../ui.tsx'
import type { FlowFiles, FlowGraph } from '../../api.ts'
import type { NodeCategoryId } from './types.ts'
import { getProtocolKind } from './nodeModel.ts'

type DraftNode = {
  id: string
  title: string
  category: NodeCategoryId
  preset: string
  type?: string
  action?: string
  kind?: string
  executor?: string
  effect?: string
  decision_contract?: any
  decision_test_mode?: string
  mock_decision_envelope?: any
  tool_binding?: string
  allowed_tools?: string[]
  mcp_binding?: any
  failure_policy?: string
  permission?: string
  audit_log?: boolean
  description?: string
  input?: string
  output?: string
  preset_config?: Record<string, string>
}

type DraftEdge = {
  from: string
  to: string
  label?: string
}

export type FlowAssistantDraft = {
  summary: string
  understanding: string
  thinking_steps?: string[]
  validation?: { ok: boolean; issues: string[]; repairs: string[]; metrics?: { max_edge_length?: number; edge_count?: number; node_count?: number } }
  mermaid: string
  nodes: DraftNode[]
  edges: DraftEdge[]
}

export type FlowAssistantApplyResult = {
  createdNodeIds: string[]
  deletedNodeIds?: string[]
  snapshotFiles?: FlowFiles
}

export type FlowAssistantGraphOps = {
  summary: string
  understanding: string
  thinking_steps?: string[]
  operations: Array<{ op: string; target?: string; node_ids?: string[] }>
}

type AssistantMessage =
  | { id: string; role: 'assistant'; kind: 'welcome'; text: string }
  | { id: string; role: 'user'; kind: 'text'; text: string }
  | { id: string; role: 'assistant'; kind: 'text'; text: string; thinkingSteps?: string[] }
  | { id: string; role: 'assistant'; kind: 'feasibility'; result: FeasibilityResult }
  | { id: string; role: 'assistant'; kind: 'mutter'; steps: string[] }
  | { id: string; role: 'assistant'; kind: 'loading'; text: string; thinkingSteps: string[] }
  | { id: string; role: 'assistant'; kind: 'ops'; ops: FlowAssistantGraphOps; applied?: FlowAssistantApplyResult; undone?: boolean }
  | { id: string; role: 'assistant'; kind: 'draft'; draft: FlowAssistantDraft; applied?: FlowAssistantApplyResult; undone?: boolean }

type FeasibilityResult = {
  status: 'blocked' | 'ok' | 'fixed'
  nodeCount: number
  edgeCount: number
  mcpCount: number
  issueCount: number
  issues: string[]
  hiddenIssueCount: number
  warnings: string[]
  note: string
  recommendations: FeasibilityRecommendation[]
  fixedCount?: number
}

type FeasibilityRecommendation = {
  sourceNodeId: string
  sourceTitle: string
  reason: string
  draft: FlowAssistantDraft
}

function MermaidPreview({ chart }: { chart: string }) {
  const id = useId().replace(/:/g, '')
  const [svg, setSvg] = useState('')

  useEffect(() => {
    let active = true
    mermaid.initialize({ startOnLoad: false, theme: 'base', securityLevel: 'strict' })
    mermaid.render(`cf_mermaid_${id}`, chart)
      .then((result) => { if (active) setSvg(result.svg) })
      .catch(() => { if (active) setSvg('') })
    return () => { active = false }
  }, [chart, id])

  return svg ? <div className="cf-assistant-mermaid" dangerouslySetInnerHTML={{ __html: svg }} /> : <pre className="cf-assistant-diagram-text">{chart}</pre>
}

function ThinkingSteps({ steps }: { steps?: string[] }) {
  if (!steps?.length) return null
  return (
    <div className="cf-assistant-thinking">
      <span>管家碎碎念</span>
      {steps.map((step, index) => <p key={`${step}-${index}`}>{step}</p>)}
    </div>
  )
}

function AssistantReplyFrame({ title = '执行者', children }: { title?: string; children: ReactNode }) {
  return (
    <div className="cf-assistant-reply-frame">
      <div className="cf-assistant-reply-head">
        <span className="cf-assistant-reply-mark" aria-hidden="true">
          <svg viewBox="0 0 24 24" focusable="false">
            <path d="M12 3.8 19 7v5.2c0 4-2.8 6.8-7 8-4.2-1.2-7-4-7-8V7l7-3.2Z" />
            <path d="M9 12l2 2 4-5" />
          </svg>
        </span>
        <strong>{title}</strong>
      </div>
      <div className="cf-assistant-reply-body">{children}</div>
    </div>
  )
}

function AssistantMarkdown({ text }: { text: string }) {
  return (
    <div className="cf-assistant-main-text cf-assistant-markdown">
      <ReactMarkdown>{text}</ReactMarkdown>
    </div>
  )
}

function FeasibilityResultCard({ result }: { result: FeasibilityResult }) {
  return (
    <div className={`cf-feasibility-result ${result.status}`}>
      <div className="cf-feasibility-status">
        <strong>{result.status === 'fixed' ? '已自动补齐' : result.status === 'blocked' ? '不可直接执行' : '暂未发现阻塞'}</strong>
        <span>{result.fixedCount ? `${result.fixedCount} 个工具节点` : result.issueCount ? `${result.issueCount} 项阻塞` : '0 项阻塞'}</span>
      </div>
      <div className="cf-feasibility-metrics">
        <span><b>{result.nodeCount}</b>节点</span>
        <span><b>{result.edgeCount}</b>链路</span>
        <span><b>{result.mcpCount}</b>MCP</span>
      </div>
      {result.issues.length ? (
        <div className="cf-feasibility-blockers">
          <span>关键阻塞</span>
          {result.issues.map((issue, index) => <p key={`${issue}-${index}`}>{issue}</p>)}
          {result.hiddenIssueCount ? <p>还有 {result.hiddenIssueCount} 项同类问题，建议优先补齐节点工具声明。</p> : null}
        </div>
      ) : null}
      {result.warnings.length ? (
        <div className="cf-feasibility-warnings">
          <span>提醒</span>
          {result.warnings.map((warning, index) => <p key={`${warning}-${index}`}>{warning}</p>)}
        </div>
      ) : null}
      {result.recommendations.length ? (
        <div className="cf-feasibility-recommendations">
          <span>{result.status === 'fixed' ? '已补齐后置工具节点' : '建议补齐工具节点'}</span>
          {result.recommendations.map((recommendation) => (
            <div key={`${recommendation.sourceNodeId}-${recommendation.draft.nodes[0]?.id}`} className="cf-feasibility-recommendation">
              <p><b>{recommendation.sourceTitle}</b> 后方：{recommendation.reason}</p>
            </div>
          ))}
        </div>
      ) : null}
      <div className="cf-feasibility-tags">
        <code>{result.mcpCount ? 'MCP 已声明' : 'MCP 未声明'}</code>
        <code>静态检查</code>
      </div>
      <p className="cf-feasibility-note">{result.note}</p>
    </div>
  )
}

function ValidationReport({ validation }: { validation?: { ok: boolean; issues: string[]; repairs: string[]; metrics?: { max_edge_length?: number; edge_count?: number; node_count?: number } } }) {
  if (!validation) return null
  const metricLines = validation.metrics ? [`最长线段约 ${validation.metrics.max_edge_length || 0}px`] : []
  const lines = [...metricLines, ...(validation.issues || []), ...(validation.repairs || [])]
  if (!lines.length) return null
  return (
    <div className={`cf-assistant-validation ${validation.ok ? 'ok' : 'warn'}`}>
      <span>{validation.ok ? '结构自检通过' : '结构自检'}</span>
      {lines.map((line, index) => <p key={`${line}-${index}`}>{line}</p>)}
    </div>
  )
}

function AssistantAvatar({ role }: { role: 'assistant' | 'user' }) {
  return (
    <span className={`cf-assistant-avatar ${role}`} aria-hidden="true">
      {role === 'assistant' ? (
        <svg viewBox="0 0 24 24" focusable="false">
          <path d="M8 5.5h8a3 3 0 0 1 3 3v5.8a3 3 0 0 1-3 3H8a3 3 0 0 1-3-3V8.5a3 3 0 0 1 3-3Z" />
          <path d="M9 10.2h.1M15 10.2h.1M9.4 14c1.6 1 3.6 1 5.2 0M12 3v2.5" />
        </svg>
      ) : (
        <svg viewBox="0 0 24 24" focusable="false">
          <path d="M12 12.2a4 4 0 1 0 0-8 4 4 0 0 0 0 8Z" />
          <path d="M4.8 20a7.2 7.2 0 0 1 14.4 0" />
        </svg>
      )}
    </span>
  )
}

const welcomeText = '我是 Flow 管家。直接告诉我想怎么改图。'

export function FlowAssistantPanel({ flowId, graph, files, onApplyDraft, onApplyGraphOps, onUndoApply }: {
  flowId: string
  graph: FlowGraph
  files: FlowFiles
  onApplyDraft: (draft: FlowAssistantDraft, sourceNode?: FlowGraph['nodes'][number] | null) => Promise<FlowAssistantApplyResult>
  onApplyGraphOps: (ops: FlowAssistantGraphOps) => Promise<FlowAssistantApplyResult>
  onUndoApply: (result: FlowAssistantApplyResult) => Promise<void>
}) {
  const [collapsed, setCollapsed] = useState(true)
  const [input, setInput] = useState('')
  const [applyingId, setApplyingId] = useState<string | null>(null)
  const [checkingFeasibility, setCheckingFeasibility] = useState(false)
  const [undoingId, setUndoingId] = useState<string | null>(null)
  const [sessionKey, setSessionKey] = useState(0)
  const threadRef = useRef<HTMLDivElement | null>(null)
  const [messages, setMessages] = useState<AssistantMessage[]>([
    { id: 'welcome', role: 'assistant', kind: 'welcome', text: welcomeText },
  ])

  const buildToolRecommendation = (node: FlowGraph['nodes'][number]): FeasibilityRecommendation | null => {
    const params = node.params || {}
    const kind = getProtocolKind(node as any)
    if (params.node_category !== 'process' && !['decision', 'retrieval', 'transform', 'validation', 'routing'].includes(kind)) return null
    const hasToolSuccessor = graph.edges.some((edge) => {
      if (edge.from !== node.id) return false
      const target = graph.nodes.find((candidate) => candidate.id === edge.to)
      const targetKind = getProtocolKind(target as any)
      return target?.params?.node_category === 'tool'
        || target?.params?.node_category === 'remote'
        || targetKind === 'mcp_read'
        || targetKind === 'mcp_execute'
        || targetKind === 'remote_call'
        || target?.action === 'tool_call'
        || target?.action === 'remote_call'
    })
    if (hasToolSuccessor) return null
    const text = `${node.title} ${node.action || ''} ${JSON.stringify(params)}`.toLowerCase()
    const outputKey = params.output || params.preset_config?.output_name || `${node.id}_result`
    const pathMatch = text.match(/[\w./\\-]+\.(md|txt|json|csv|log|ts|tsx|js|py)/)
    const hasFileIntent = ['文件', '写入', '读取', '保存为文件', '导出', 'read file', 'write file', 'filesystem'].some((keyword) => text.includes(keyword)) || Boolean(pathMatch)
    const hasExternalIntent = ['联网', '素材', '视频', '剪辑', '合成', '发布', '下载', '搜索', '爬取', '调用', 'api', 'video', 'search', 'web', 'download', 'fetch', 'render', 'upload'].some((keyword) => text.includes(keyword))
    if (!hasFileIntent && !hasExternalIntent) return null
    if (!hasFileIntent) {
      const toolNodeId = `${node.id}_external_tool`
      const toolOutput = `${node.id}_tool_result`
      return {
        sourceNodeId: node.id,
        sourceTitle: node.title,
        reason: '该处理节点需要外部能力，管家已先补一个待配置 MCP 占位工具节点。',
        draft: {
          summary: `为「${node.title}」补齐外部工具占位节点`,
          understanding: `我会在「${node.title}」后面插入一个待配置的 MCP 工具节点，先把外部能力从处理节点里拆出来。`,
          thinking_steps: ['识别处理节点中的外部能力需求', '无法确定具体 MCP 服务时先创建占位工具节点', '保持工具节点只消费上游处理节点输出'],
          validation: { ok: true, issues: [], repairs: [] },
          mermaid: `flowchart LR\n  ${node.id}[${node.title}] --> ${toolNodeId}[外部工具占位]`,
          nodes: [{
            id: toolNodeId,
            title: '外部工具占位',
            category: 'tool',
            preset: 'mcp_call',
            type: 'process',
            action: 'tool_call',
            kind: 'mcp_execute',
            executor: 'mcp',
            effect: 'external_side_effect',
            tool_binding: 'static_params',
            failure_policy: 'fail_closed',
            permission: 'external_service_call',
            audit_log: true,
            description: '待配置的后置 MCP 工具节点。请在确认具体外部能力后填写 server/tool。',
            input: outputKey,
            output: toolOutput,
            preset_config: { server: '待配置', tool: '待配置', output_name: toolOutput },
          }],
          edges: [{ from: node.id, to: toolNodeId }],
        },
      }
    }
    const wantsRead = ['读取', '读文件', 'read file', '导入'].some((keyword) => text.includes(keyword))
    const preset = wantsRead ? 'filesystem_read' : 'filesystem_write'
    const path = pathMatch?.[0] || (wantsRead ? 'input.txt' : `test_output/${node.id}.txt`)
    const toolNodeId = `${node.id}_${wantsRead ? 'read_file' : 'write_file'}_tool`
    const toolOutput = `${node.id}_${wantsRead ? 'file_content' : 'file_written'}`
    return {
      sourceNodeId: node.id,
      sourceTitle: node.title,
      reason: wantsRead ? '该处理节点需要读取文件，建议把读取动作拆成独立工具节点。' : '该处理节点需要写入或导出文件，建议把文件操作拆成独立工具节点。',
      draft: {
        summary: `为「${node.title}」补齐后置工具节点`,
        understanding: `我会在「${node.title}」后面插入一个专属工具节点，让处理节点继续只负责 AI 判断，外部文件能力由工具节点完成。`,
        thinking_steps: ['识别处理节点中的外部文件能力需求', '按解耦规则选择后置工具节点', '保持工具节点只消费上游处理节点输出'],
        validation: { ok: true, issues: [], repairs: [] },
        mermaid: `flowchart LR\n  ${node.id}[${node.title}] --> ${toolNodeId}[${wantsRead ? '读取文件' : '写入文件'}]`,
        nodes: [{
          id: toolNodeId,
          title: wantsRead ? '读取文件' : '写入文件',
          category: 'tool',
          preset,
          type: 'process',
          action: 'tool_call',
          kind: wantsRead ? 'mcp_read' : 'mcp_execute',
          executor: 'mcp',
          effect: wantsRead ? 'read_only' : 'writes_files',
          tool_binding: wantsRead ? undefined : 'static_params',
          mcp_binding: wantsRead ? { mode: 'read_only', allowed_tools: ['filesystem_read'] } : undefined,
          allowed_tools: [wantsRead ? 'filesystem_read' : 'filesystem_write'],
          failure_policy: wantsRead ? undefined : 'fail_closed',
          permission: wantsRead ? undefined : 'write_workspace_files',
          audit_log: !wantsRead,
          description: wantsRead ? '后置工具节点读取文件内容。' : '后置工具节点将上游处理结果写入文件。',
          input: outputKey,
          output: toolOutput,
          preset_config: wantsRead ? { path, output_name: toolOutput } : { path, source: outputKey, output_name: toolOutput },
        }],
        edges: [{ from: node.id, to: toolNodeId }],
      },
    }
  }

  useEffect(() => {
    if (collapsed) return
    const scrollToBottom = () => {
      const thread = threadRef.current
      if (!thread) return
      thread.scrollTo({ top: thread.scrollHeight, behavior: 'smooth' })
    }
    const frame = window.requestAnimationFrame(scrollToBottom)
    const timeout = window.setTimeout(scrollToBottom, 80)
    return () => {
      window.cancelAnimationFrame(frame)
      window.clearTimeout(timeout)
    }
  }, [messages, collapsed])

  const newSession = () => {
    setSessionKey((value) => value + 1)
    setMessages([{ id: `welcome_${Date.now().toString(36)}`, role: 'assistant', kind: 'welcome', text: welcomeText }])
    setInput('')
  }

  const runFeasibilityCheck = async () => {
    if (checkingFeasibility) return
    setCheckingFeasibility(true)
    try {
      const issues: string[] = []
      const warnings: string[] = []
      const mcpSlots: string[] = []
      const recommendations: FeasibilityRecommendation[] = []
      graph.nodes.forEach((node) => {
        const tools = Array.isArray(node.tools) ? node.tools : []
        tools.forEach((tool) => {
          if (!tool || typeof tool !== 'object') return
          if (tool.type === 'mcp') {
            const label = `${node.title}：${tool.server || '未声明 server'}/${tool.tool || '未声明 tool'}`
            mcpSlots.push(label)
            if (!tool.server || !tool.tool) issues.push(`${node.title} 的 MCP 工具槽未完整声明 server/tool。`)
            if (tool.enabled === false) warnings.push(`${node.title} 的 MCP 工具槽已禁用。`)
          }
        })
        const text = `${node.title} ${node.action || ''} ${JSON.stringify(node.params || {})}`.toLowerCase()
        const needsNetwork = ['联网', '素材', '视频', 'video', 'search', 'web', 'download', 'fetch'].some((keyword) => text.includes(keyword))
        const hasExternalTool = tools.some((tool) => tool?.type === 'mcp' || tool?.type === 'builtin')
        const recommendation = hasExternalTool ? null : buildToolRecommendation(node)
        if (recommendation) {
          recommendations.push(recommendation)
        issues.push(`${node.title} 看起来需要外部能力，管家已准备在它后面补一个占位工具节点。`)
      } else if (needsNetwork && !hasExternalTool) {
        issues.push(`${node.title} 看起来需要外部能力，但没有声明 MCP 或内置工具。`)
        }
      })
      const issuePreview = issues.slice(0, 4)
      const hiddenIssueCount = Math.max(0, issues.length - issuePreview.length)
      const warningPreview = warnings.slice(0, 2)
      const appliedResults: FlowAssistantApplyResult[] = []
      for (const recommendation of recommendations) {
        const sourceNode = graph.nodes.find((node) => node.id === recommendation.sourceNodeId) || null
        if (!sourceNode) continue
        const result = await onApplyDraft(recommendation.draft, sourceNode)
        appliedResults.push(result)
      }
      const fixedCount = appliedResults.reduce((count, result) => count + result.createdNodeIds.length, 0)
      const result: FeasibilityResult = {
        status: fixedCount ? 'fixed' : issues.length ? 'blocked' : 'ok',
        nodeCount: graph.nodes.length,
        edgeCount: graph.edges.length,
        mcpCount: mcpSlots.length,
        issueCount: issues.length,
        issues: issuePreview,
        hiddenIssueCount,
        warnings: warningPreview,
        recommendations,
        fixedCount,
        note: fixedCount ? '管家已自动把外部能力拆成处理节点后方的专属占位工具节点。' : '当前只做本地静态检查，真实可用性还需要接入 MCP 注册表。',
      }
      setMessages((current) => [
        ...current,
        { id: `feasibility_${Date.now().toString(36)}`, role: 'assistant', kind: 'feasibility', result },
      ])
    } finally {
      setCheckingFeasibility(false)
    }
  }

  const submit = async () => {
    const text = input.trim()
    if (!text) return
    const stamp = `${sessionKey}_${Date.now().toString(36)}`
    const loadingId = `loading_${stamp}`
    setMessages((current) => [
      ...current,
      { id: `user_${stamp}`, role: 'user', kind: 'text', text },
      {
        id: loadingId,
        role: 'assistant',
        kind: 'loading',
        text: '处理中...',
        thinkingSteps: ['读取当前图', '判断操作'],
      },
    ])
    setInput('')
    try {
      const response = await askFlowAssistant(flowId, text, graph, files)
      setMessages((current) => current.flatMap((message) => {
        if (message.id !== loadingId) return [message]
        if (response.message.type === 'flow_draft') {
          const draft = response.message as FlowAssistantDraft
          return [{ id: `draft_${stamp}`, role: 'assistant', kind: 'draft', draft }]
        }
        if (response.message.type === 'graph_ops') {
          const ops = response.message as FlowAssistantGraphOps
          return [{ id: `ops_${stamp}`, role: 'assistant', kind: 'ops', ops }]
        }
        return [{
          id: `ask_${stamp}`,
          role: 'assistant',
          kind: 'text',
          text: response.message.message,
        }]
      }))
    } catch (error) {
      setMessages((current) => current.map((message) => (
        message.id === loadingId
          ? { id: `error_${stamp}`, role: 'assistant', kind: 'text', text: error instanceof Error ? error.message : 'LLM 调用失败，请检查 LLM 设置。' }
          : message
      )))
    }
  }

  const apply = async (messageId: string, draft: FlowAssistantDraft) => {
    setApplyingId(messageId)
    try {
      const result = await onApplyDraft(draft)
      setMessages((current) => current.map((message) => (
        message.id === messageId && message.kind === 'draft'
          ? { ...message, applied: result, undone: false }
          : message
      )))
    } finally {
      setApplyingId(null)
    }
  }

  const applyOps = async (messageId: string, ops: FlowAssistantGraphOps) => {
    setApplyingId(messageId)
    try {
      const result = await onApplyGraphOps(ops)
      setMessages((current) => current.map((message) => (
        message.id === messageId && message.kind === 'ops'
          ? { ...message, applied: result, undone: false }
          : message
      )))
    } finally {
      setApplyingId(null)
    }
  }

  const undo = async (messageId: string, result: FlowAssistantApplyResult) => {
    setUndoingId(messageId)
    try {
      await onUndoApply(result)
      setMessages((current) => current.map((message) => (
        message.id === messageId && (message.kind === 'draft' || message.kind === 'ops')
          ? { ...message, undone: true }
          : message
      )))
    } finally {
      setUndoingId(null)
    }
  }

  return (
    <aside className={`cf-flow-assistant ${collapsed ? 'collapsed' : ''}`}>
      <div className="cf-assistant-head">
        <div className="cf-assistant-titlemark">
          <span className="cf-assistant-orb" aria-hidden="true">CF</span>
          <div>
            <h2>创作管家</h2>
            {!collapsed && <p>整理想法与链路。</p>}
          </div>
        </div>
        {collapsed && (
          <div className="cf-assistant-rail-info">
            <span><b>{graph.nodes.length}</b> 节点</span>
            <span><b>{graph.edges.length}</b> 链路</span>
            <i />
            <button type="button" onClick={runFeasibilityCheck} disabled={checkingFeasibility}>{checkingFeasibility ? '补' : '验'}</button>
          </div>
        )}
        <div className="cf-assistant-head-actions">
          {!collapsed && <button type="button" onClick={newSession}>新会话</button>}
          <button type="button" onClick={() => setCollapsed((value) => !value)}>{collapsed ? '›' : '‹'}</button>
        </div>
      </div>

      {!collapsed && (
        <>
          <div className="cf-assistant-thread" ref={threadRef}>
            {messages.map((message) => (
              <div key={message.id} className={`cf-assistant-message ${message.role} ${message.kind}`}>
                <AssistantAvatar role={message.role} />
                <div className={`cf-assistant-bubble ${message.role} ${message.kind}`}>
                  {message.kind === 'ops' ? (
                    <AssistantReplyFrame>
                      <strong className="cf-assistant-reply-summary">{message.ops.summary}</strong>
                      <AssistantMarkdown text={message.ops.understanding} />
                      <div className="cf-assistant-confirm">
                        <div>
                          <strong>{message.applied && !message.undone ? '已执行' : '确认后执行'}</strong>
                          <span>{message.ops.operations.length} 个操作 · 当前已有 {graph.nodes.length} 个节点</span>
                        </div>
                        {message.applied && !message.undone ? (
                          <Button className="cf-outline-btn" onClick={() => undo(message.id, message.applied!)} disabled={undoingId === message.id}>
                            {undoingId === message.id ? '撤销中' : '撤销本次操作'}
                          </Button>
                        ) : message.undone ? (
                          <span className="cf-assistant-undone">已撤销</span>
                        ) : (
                          <Button className="cf-accent-btn" onClick={() => applyOps(message.id, message.ops)} disabled={applyingId === message.id}>
                            {applyingId === message.id ? '执行中' : '确认执行'}
                          </Button>
                        )}
                      </div>
                    </AssistantReplyFrame>
                  ) : message.kind === 'draft' ? (
                    <AssistantReplyFrame>
                      <strong className="cf-assistant-reply-summary">{message.draft.summary}</strong>
                      <ValidationReport validation={message.draft.validation} />
                      <AssistantMarkdown text={message.draft.understanding} />
                      <MermaidPreview chart={message.draft.mermaid} />
                      <div className="cf-assistant-confirm">
                        <div>
                          <strong>{message.applied && !message.undone ? '已应用到当前链路图' : '确认后我会画到当前链路图'}</strong>
                          <span>{message.draft.nodes.length} 个节点 · {message.draft.edges.length} 条链路 · 当前已有 {graph.nodes.length} 个节点</span>
                        </div>
                        {message.applied && !message.undone ? (
                          <Button className="cf-outline-btn" onClick={() => undo(message.id, message.applied!)} disabled={undoingId === message.id}>
                            {undoingId === message.id ? '撤销中' : '撤销本次应用'}
                          </Button>
                        ) : message.undone ? (
                          <span className="cf-assistant-undone">已撤销</span>
                        ) : (
                          <Button className="cf-accent-btn" onClick={() => apply(message.id, message.draft)} disabled={applyingId === message.id}>
                            {applyingId === message.id ? '应用中' : '确认应用'}
                          </Button>
                        )}
                      </div>
                    </AssistantReplyFrame>
                  ) : message.kind === 'loading' ? (
                    <AssistantReplyFrame>
                      <AssistantMarkdown text={message.text} />
                      <ThinkingSteps steps={message.thinkingSteps} />
                    </AssistantReplyFrame>
                  ) : message.kind === 'feasibility' ? (
                    <AssistantReplyFrame title="检测结果">
                      <FeasibilityResultCard result={message.result} />
                    </AssistantReplyFrame>
                  ) : message.kind === 'mutter' ? (
                    <ThinkingSteps steps={message.steps} />
                  ) : message.role === 'assistant' ? (
                    <AssistantReplyFrame>
                      <AssistantMarkdown text={message.text} />
                    </AssistantReplyFrame>
                  ) : (
                    <p className="cf-assistant-main-text">{message.text}</p>
                  )}
                </div>
              </div>
            ))}
          </div>

          <div className="cf-assistant-inputbar">
            <textarea
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' && !event.shiftKey) {
                  event.preventDefault()
                  submit()
                }
              }}
              placeholder="例如：增加一个确认节点，或重新整理当前流程"
            />
            <div className="cf-assistant-actions">
              <button type="button" className="cf-assistant-tool-btn" onClick={runFeasibilityCheck} title="可行性检测" aria-label="可行性检测" disabled={checkingFeasibility}>
                <svg viewBox="0 0 24 24" focusable="false">
                  <path d="M9 12l2 2 4-5" />
                  <path d="M12 3.8 19 7v5.2c0 4-2.8 6.8-7 8-4.2-1.2-7-4-7-8V7l7-3.2Z" />
                </svg>
                <span>{checkingFeasibility ? '补齐中' : '可行性验证'}</span>
              </button>
              <Button className="cf-accent-btn" onClick={submit}>发送</Button>
            </div>
          </div>
        </>
      )}
    </aside>
  )
}
