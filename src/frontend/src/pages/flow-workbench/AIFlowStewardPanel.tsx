import { useEffect, useMemo, useRef, useState } from 'react'
import { AlertTriangle, Bot, CheckCircle2, MousePointer2, Scan, Send, X } from 'lucide-react'
import { askAIFlowSteward, type AIFlowStewardContext, type AIFlowStewardMessage, type AIFlowStewardMode } from '../../api.ts'

type StewardTool = 'none' | 'pointer' | 'lasso'

type ThreadMessage =
  | { id: string; role: 'assistant'; kind: 'welcome'; text: string }
  | { id: string; role: 'user'; kind: 'text'; text: string }
  | { id: string; role: 'assistant'; kind: 'response'; response: AIFlowStewardMessage }
  | { id: string; role: 'assistant'; kind: 'error'; text: string }

const WELCOME: ThreadMessage = {
  id: 'welcome',
  role: 'assistant',
  kind: 'welcome',
  text: '告诉我你想理解或完成什么。说不清专业名称时，直接用指针或框选告诉我“就是这里”。',
}

function selectionSummary(context: AIFlowStewardContext) {
  const nodes = context.selection.node_ids.length
  const edges = context.selection.edge_ids.length
  const fields = context.selection.field_paths.length
  if (!nodes && !edges && !fields) return '尚未指向工程内容'
  return [nodes ? `${nodes} 个节点` : '', edges ? `${edges} 条连线` : '', fields ? `${fields} 个字段` : ''].filter(Boolean).join(' · ')
}

export function AIFlowStewardPanel({
  flowId,
  context,
  tool,
  onToolChange,
  onClearSelection,
  onClose,
}: {
  flowId: string
  context: AIFlowStewardContext
  tool: StewardTool
  onToolChange: (tool: StewardTool) => void
  onClearSelection: () => void
  onClose: () => void
}) {
  const [mode, setMode] = useState<AIFlowStewardMode>('guided')
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [messages, setMessages] = useState<ThreadMessage[]>([WELCOME])
  const threadRef = useRef<HTMLDivElement | null>(null)
  const summary = useMemo(() => selectionSummary(context), [context])

  useEffect(() => {
    threadRef.current?.scrollTo({ top: threadRef.current.scrollHeight, behavior: 'smooth' })
  }, [busy, messages])

  const submit = async () => {
    const message = input.trim()
    if (!message || busy || !context.revision) return
    setInput('')
    setBusy(true)
    setMessages((current) => [...current, { id: `user_${Date.now()}`, role: 'user', kind: 'text', text: message }])
    try {
      const result = await askAIFlowSteward(flowId, message, mode, context)
      setMessages((current) => [...current, { id: `answer_${Date.now()}`, role: 'assistant', kind: 'response', response: result.message }])
    } catch (error: any) {
      setMessages((current) => [...current, {
        id: `error_${Date.now()}`,
        role: 'assistant',
        kind: 'error',
        text: error?.message || String(error),
      }])
    } finally {
      setBusy(false)
    }
  }

  const engineering = context.view === 'engineering'
  return (
    <aside className="cf-ai-steward" aria-label="AI 管家">
      <header className="cf-ai-steward-head">
        <span><Bot aria-hidden="true" /></span>
        <div><strong>AI 管家</strong><small>{mode === 'guided' ? '带着我完成' : '这件事交给你'}</small></div>
        <button type="button" className="cf-ai-steward-close" onClick={onClose} title="收起 AI 管家" aria-label="收起 AI 管家"><X aria-hidden="true" /></button>
      </header>

      <div className="cf-ai-steward-modes" role="tablist" aria-label="AI 管家责任模式">
        <button type="button" className={mode === 'guided' ? 'active' : ''} onClick={() => setMode('guided')} role="tab" aria-selected={mode === 'guided'}>引导模式</button>
        <button type="button" className={mode === 'delegated' ? 'active' : ''} onClick={() => setMode('delegated')} role="tab" aria-selected={mode === 'delegated'}>委托模式</button>
      </div>

      <section className="cf-ai-steward-tools" aria-label="工程语义定位工具">
        <div>
          <button
            type="button"
            className={tool === 'pointer' ? 'active' : ''}
            onClick={() => onToolChange(tool === 'pointer' ? 'none' : 'pointer')}
            draggable={engineering}
            onDragStart={(event) => {
              event.dataTransfer.effectAllowed = 'copy'
              event.dataTransfer.setData('application/x-cf-steward-tool', 'pointer')
              onToolChange('pointer')
            }}
            disabled={!engineering}
            title={engineering ? '拖到节点或连线上，或启用后直接点击' : ''}
          >
            <MousePointer2 aria-hidden="true" /><span>拖拽指针</span>
          </button>
          <button
            type="button"
            className={tool === 'lasso' ? 'active' : ''}
            onClick={() => onToolChange(tool === 'lasso' ? 'none' : 'lasso')}
            disabled={!engineering}
            title={engineering ? '在画布空白处拖动，框选一段流程' : ''}
          >
            <Scan aria-hidden="true" /><span>框选工具</span>
          </button>
        </div>
        <p>{engineering ? '把专业对象直接指出来，管家会读取节点、连线和字段关系。' : '在画布空白处拖动，框选一段流程。'}</p>
      </section>

      <div className={`cf-ai-steward-selection ${context.selection.node_ids.length || context.selection.edge_ids.length || context.selection.field_paths.length ? 'has-selection' : ''}`}>
        <span>{context.tool === 'lasso' ? '框选范围' : context.tool === 'pointer' ? '当前指向' : '当前上下文'}</span>
        <strong title={summary}>{summary}</strong>
        {(context.selection.node_ids.length || context.selection.edge_ids.length || context.selection.field_paths.length) > 0 && (
          <button type="button" onClick={onClearSelection} title="清除管家选区" aria-label="清除管家选区"><X aria-hidden="true" /></button>
        )}
      </div>

      <div className="cf-ai-steward-thread" ref={threadRef} aria-live="polite">
        {messages.map((message) => (
          <article key={message.id} className={`cf-ai-steward-message ${message.role} ${message.kind}`}>
            {message.role === 'assistant' && <span className="cf-ai-steward-avatar"><Bot aria-hidden="true" /></span>}
            <div>
              {message.kind === 'welcome' || message.kind === 'text' || message.kind === 'error' ? <p>{message.text}</p> : null}
              {message.kind === 'response' && (
                <>
                  {message.response.understanding && <small>{message.response.understanding}</small>}
                  <p>{message.response.answer}</p>
                  {message.response.operations.length > 0 && (
                    <section className="cf-ai-steward-proposal">
                      <strong>{message.response.mode === 'delegated' ? '建议变更' : '建议操作'}</strong>
                      {message.response.operations.map((operation, index) => (
                        <div key={`${operation.op}:${index}`}><b>{operation.op}</b><span>{operation.description || operation.target}</span></div>
                      ))}
                    </section>
                  )}
                  {message.response.confirmation_required && (
                    <div className="cf-ai-steward-risk"><AlertTriangle aria-hidden="true" />应用前需要确认影响范围</div>
                  )}
                  {message.response.next_step && (
                    <div className="cf-ai-steward-next"><CheckCircle2 aria-hidden="true" /><span>{message.response.next_step}</span></div>
                  )}
                </>
              )}
            </div>
          </article>
        ))}
        {busy && <div className="cf-ai-steward-loading"><i /><i /><i /><span>正在读取工作台上下文</span></div>}
      </div>

      <footer className="cf-ai-steward-composer">
        <textarea
          value={input}
          onChange={(event) => setInput(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && !event.shiftKey) {
              event.preventDefault()
              void submit()
            }
          }}
          placeholder={mode === 'guided' ? '问这部分是什么，或让我带你完成下一步' : '说明目标，并用框选限定修改范围'}
          rows={3}
        />
        <button type="button" onClick={() => void submit()} disabled={!input.trim() || busy || !context.revision} title="发送给 AI 管家" aria-label="发送给 AI 管家"><Send aria-hidden="true" /></button>
      </footer>
      <p className="cf-ai-steward-footnote">AI 建议需经确定性校验；委托模式不会绕过确认与工程锁。</p>
    </aside>
  )
}
