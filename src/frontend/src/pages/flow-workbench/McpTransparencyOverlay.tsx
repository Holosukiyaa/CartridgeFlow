import { useEffect, useMemo, useState } from 'react'
import { Braces, Code2, FileCode2, Save, X } from 'lucide-react'
import { replaceMcpSource, type McpSourceEditResponse, type McpSourceResponse, type StudioToolResource } from '../../api.ts'

function operationKindLabel(kind: unknown) {
  const labels: Record<string, string> = { transform: '数据处理', network: '网络访问', io: '输入输出', decision: '判断', operation: '操作' }
  return labels[String(kind || 'operation')] || String(kind || '操作')
}

function parseStatusLabel(source: McpSourceResponse | null, tool: StudioToolResource) {
  if (source?.source_model.ok) return '已解析'
  if (tool.parse_status === 'opaque') return '不可解析'
  if (tool.parse_status === 'parsed') return '已解析'
  return tool.parse_status || '未知'
}

export function McpTransparencyOverlay({ flowId, tool, source, loading, error, initialTab = 'graph', onClose, onSaved }: {
  flowId: string
  tool: StudioToolResource
  source: McpSourceResponse | null
  loading: boolean
  error: string
  initialTab?: 'graph' | 'source'
  onClose: () => void
  onSaved: (result: McpSourceEditResponse) => void | Promise<void>
}) {
  const [tab, setTab] = useState<'graph' | 'source'>(initialTab)
  const [sourceText, setSourceText] = useState('')
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState('')
  useEffect(() => { setTab(initialTab) }, [initialTab])
  useEffect(() => { setSourceText(source?.source || ''); setSaveError('') }, [source?.source, tool.node_id])
  const graph = useMemo(() => ({
    operations: source?.source_model.operations || tool.operation_graph?.operations || [],
    edges: source?.source_model.edges || tool.operation_graph?.edges || [],
    fallbacks: source?.source_model.fallbacks || tool.operation_graph?.fallbacks || [],
  }), [source, tool])
  const sourceMap = source?.source_model.source_map || {}
  const sourceChanged = Boolean(source && sourceText !== source.source)
  const saveSource = async () => {
    if (!source || !tool.node_id || !sourceChanged) return
    setSaving(true)
    setSaveError('')
    try {
      const result = await replaceMcpSource(flowId, tool.node_id, source.source_digest, sourceText)
      setSourceText(result.source)
      await onSaved(result)
    } catch (saveFailure: any) {
      setSaveError(saveFailure?.message || '源码保存失败')
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className="cf-mcp-transparency-overlay" aria-label="MCP 内部流程">
      <header>
        <div><Braces aria-hidden="true" /><div><strong>{tool.name || 'MCP 工具'}</strong><code>{tool.transparency || 'unknown'}</code></div></div>
        <button type="button" onClick={onClose} title="收起内部流程"><X aria-hidden="true" /></button>
      </header>
      <nav aria-label="MCP 透明度内容">
        <button type="button" className={tab === 'graph' ? 'active' : ''} onClick={() => setTab('graph')}><Braces aria-hidden="true" />内部流程</button>
        <button type="button" className={tab === 'source' ? 'active' : ''} onClick={() => setTab('source')}><FileCode2 aria-hidden="true" />源码</button>
        <span>{source?.path || source?.source_model.source.path || '未加载源码'}</span>
      </nav>
      {loading ? <div className="cf-mcp-transparency-empty">正在解析 MCP Python 源码...</div> : error ? <div className="cf-mcp-transparency-empty error">{error}</div> : tab === 'source' ? (
        source ? <div className="cf-mcp-source-editor"><textarea className="cf-mcp-transparency-source" value={sourceText} onChange={(event) => setSourceText(event.target.value)} spellCheck={false} aria-label="MCP Python 源码" /><div><span>{saveError}</span><button type="button" disabled={!sourceChanged || saving} onClick={() => void saveSource()}><Save aria-hidden="true" />{saving ? '保存中...' : '保存源码'}</button></div></div> : <div className="cf-mcp-transparency-empty">该工具未提供可读取的源码。</div>
      ) : graph.operations.length ? (
        <div className="cf-mcp-operation-canvas">
          {graph.operations.map((operation: any, index: number) => {
            const id = String(operation.id || `operation_${index + 1}`)
            const next = graph.edges.filter((edge: any) => String(edge.from || '') === id).map((edge: any) => String(edge.to || '')).filter(Boolean)
            const location = sourceMap[`operation:${id}`]
            return <article key={id}>
              <span>{String(index + 1).padStart(2, '0')}</span><strong>{id}</strong><small>{operationKindLabel(operation.kind)}</small>
              {operation.capability && <code>{String(operation.capability)}</code>}
              {location?.line && <em>{location.path}:{location.line}</em>}
              {next.length > 0 && <footer>下一步：{next.join(', ')}</footer>}
            </article>
          })}
          {graph.fallbacks.map((fallback: any, index: number) => <aside key={`${fallback.id || index}`}><b>备用路径 {index + 1}</b>{String(fallback.id || 'fallback')}</aside>)}
        </div>
      ) : <div className="cf-mcp-transparency-empty"><Code2 aria-hidden="true" />该 MCP 未声明可展示的 operation graph。</div>}
      <footer><span>解析：<b>{parseStatusLabel(source, tool)}</b></span><span>{graph.operations.length} 个操作</span><span>{graph.edges.length} 条连线</span><span>{graph.fallbacks.length} 条备用路径</span></footer>
    </section>
  )
}
