import { useEffect, useMemo, useState } from 'react'
import { Braces, Code2, FileCode2, Save, ShieldCheck, X } from 'lucide-react'
import { checkFlowResourceConnectivity, fetchFlowResourceDetail, replaceMcpSource, type McpConnectionHealth, type McpSourceEditResponse, type McpSourceResponse, type StudioToolResource } from '../../api.ts'
import { ExternalMcpDetailTemplate, getMcpPresentationMode, mcpPresentationLabel, UnauditableMcpDetailTemplate, type ExternalMcpDetailTab } from './McpDetailTemplates.tsx'

function operationKindLabel(kind: unknown) {
  const labels: Record<string, string> = { transform: '数据处理', network: '网络访问', io: '输入输出', decision: '判断', operation: '操作' }
  return labels[String(kind || 'operation')] || String(kind || '操作')
}

function parseStatusLabel(source: McpSourceResponse | null, tool: StudioToolResource) {
  if (source?.source_model.ok) return '已解析'
  if (tool.parse_status === 'opaque') return '不可解析'
  if (tool.parse_status === 'parsed') return '已解析'
  if (tool.parse_status === 'not_applicable') return '不适用'
  return '状态未知'
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
  const presentationMode = getMcpPresentationMode(tool)
  const localParsable = presentationMode === 'local_parsable'
  const externalConnector = presentationMode === 'external_connector'
  const [tab, setTab] = useState<'graph' | 'source'>(initialTab)
  const [externalTab, setExternalTab] = useState<ExternalMcpDetailTab>('connection')
  const [sourceText, setSourceText] = useState('')
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState('')
  const [resourceDetail, setResourceDetail] = useState<StudioToolResource | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailError, setDetailError] = useState('')
  const [connectionHealth, setConnectionHealth] = useState<McpConnectionHealth | undefined>()
  const [checkingConnectivity, setCheckingConnectivity] = useState(false)
  const [connectivityError, setConnectivityError] = useState('')
  useEffect(() => { setTab(initialTab) }, [initialTab])
  useEffect(() => { setSourceText(source?.source || ''); setSaveError('') }, [source?.source, tool.node_id])
  useEffect(() => {
    let active = true
    setResourceDetail(null)
    setDetailError('')
    setConnectionHealth(undefined)
    setConnectivityError('')
    setExternalTab('connection')
    const resourceId = String(tool.resource_id || tool.id || '').trim()
    if (localParsable || !resourceId) return () => { active = false }
    setDetailLoading(true)
    void fetchFlowResourceDetail(flowId, resourceId)
      .then((result) => {
        if (active) setResourceDetail(result.resource)
      })
      .catch(() => {
        if (active) setDetailError('资源详情读取失败，正在显示工程目录中的已知信息。')
      })
      .finally(() => {
        if (active) setDetailLoading(false)
      })
    return () => { active = false }
  }, [flowId, localParsable, tool.id, tool.resource_id])
  const graph = useMemo(() => ({
    operations: source?.source_model.operations || tool.operation_graph?.operations || [],
    edges: source?.source_model.edges || tool.operation_graph?.edges || [],
    fallbacks: source?.source_model.fallbacks || tool.operation_graph?.fallbacks || [],
  }), [source, tool])
  const sourceMap = source?.source_model.source_map || {}
  const sourceChanged = Boolean(source && sourceText !== source.source)
  const displayedTool = resourceDetail || tool
  const displayedConnectionHealth = connectionHealth || displayedTool.health?.connection
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

  const testConnectivity = async () => {
    const resourceId = String(displayedTool.resource_id || displayedTool.id || '').trim()
    if (!resourceId) return
    setCheckingConnectivity(true)
    setConnectivityError('')
    try {
      const result = await checkFlowResourceConnectivity(flowId, resourceId)
      setConnectionHealth(result.connection_health)
    } catch (failure: any) {
      const health = failure?.detail?.connection_health
      if (health && typeof health === 'object') setConnectionHealth(health as McpConnectionHealth)
      setConnectivityError('连接测试未完成。请核对连接配置、认证引用和服务可用性后重试。')
    } finally {
      setCheckingConnectivity(false)
    }
  }

  return (
    <section className="cf-mcp-transparency-overlay" aria-label={localParsable ? 'MCP 内部流程' : externalConnector ? '外部 MCP 连接详情' : '不可审计 MCP 已知契约'}>
      <header>
        <div><Braces aria-hidden="true" /><div><strong>{displayedTool.name || 'MCP 工具'}</strong><code>{localParsable ? displayedTool.transparency || 'unknown' : mcpPresentationLabel(displayedTool)}</code></div></div>
        <button type="button" onClick={onClose} title={localParsable ? '收起内部流程' : '关闭详情'}><X aria-hidden="true" /></button>
      </header>
      {localParsable ? <>
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
        ) : <div className="cf-mcp-transparency-empty"><Code2 aria-hidden="true" />该 MCP 未声明可展示的操作图。</div>}
        <footer><span>解析：<b>{parseStatusLabel(source, tool)}</b></span><span>{graph.operations.length} 个操作</span><span>{graph.edges.length} 条连线</span><span>{graph.fallbacks.length} 条备用路径</span></footer>
      </> : <>
        {externalConnector ? <nav aria-label="外部 MCP 详情内容">
          <button type="button" className={externalTab === 'connection' ? 'active' : ''} onClick={() => setExternalTab('connection')}><Braces aria-hidden="true" />连接详情</button>
          <button type="button" className={externalTab === 'contract' ? 'active' : ''} onClick={() => setExternalTab('contract')}><FileCode2 aria-hidden="true" />调用契约</button>
          <button type="button" className={externalTab === 'runs' ? 'active' : ''} onClick={() => setExternalTab('runs')}><Code2 aria-hidden="true" />运行轨迹</button>
          <span>{[displayedTool.server, displayedTool.tool].filter(Boolean).join(' / ') || '未声明服务与工具'}</span>
        </nav> : <nav aria-label="不可审计 MCP 详情内容"><button type="button" className="active"><ShieldCheck aria-hidden="true" />已知契约</button><span>{[displayedTool.server, displayedTool.tool].filter(Boolean).join(' / ') || '未声明服务与工具'}</span></nav>}
        {detailLoading ? <div className="cf-mcp-transparency-empty">正在读取已脱敏的资源详情...</div> : <div className="cf-mcp-operation-canvas">{externalConnector ? <ExternalMcpDetailTemplate tool={displayedTool} tab={externalTab} connectionHealth={displayedConnectionHealth} checking={checkingConnectivity} onCheckConnectivity={() => void testConnectivity()} notice={[detailError, connectivityError].filter(Boolean).join(' ')} /> : <UnauditableMcpDetailTemplate tool={displayedTool} notice={detailError} />}</div>}
        <footer>{externalConnector ? <><span>连接：<b>{displayedConnectionHealth?.status === 'healthy' ? '连接正常' : displayedConnectionHealth?.status === 'unhealthy' ? '连接异常' : '尚未检查'}</b></span><span>运行：<b>未观测</b></span></> : <><span>透明度：<b>{displayedTool.transparency || 'unknown'}</b></span><span>内部实现不可观测</span></>}</footer>
      </>}
    </section>
  )
}
