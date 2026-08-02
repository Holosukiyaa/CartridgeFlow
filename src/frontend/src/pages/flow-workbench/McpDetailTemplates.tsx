import type { ReactNode } from 'react'
import { CircleAlert, KeyRound, RadioTower, ShieldCheck, TimerReset, Workflow, type LucideIcon } from 'lucide-react'
import type { McpConnectionHealth, McpPresentationMode, StudioToolResource } from '../../api.ts'

export type ExternalMcpDetailTab = 'connection' | 'contract' | 'runs'

export function getMcpPresentationMode(tool: StudioToolResource): McpPresentationMode {
  if (tool.presentation_mode === 'local_parsable' || tool.presentation_mode === 'external_connector' || tool.presentation_mode === 'unauditable') {
    return tool.presentation_mode
  }
  if (tool.source === 'cartridge_dlc' && tool.parse_status === 'parsed') return 'local_parsable'
  if (tool.connector && tool.contract) return 'external_connector'
  return 'unauditable'
}

export function mcpPresentationLabel(tool: StudioToolResource) {
  const mode = getMcpPresentationMode(tool)
  if (mode === 'local_parsable') return '本地可解析 MCP'
  if (mode === 'external_connector') return '外部 MCP'
  return '不可审计 MCP'
}

export function connectionStatusLabel(status?: string) {
  const labels: Record<string, string> = {
    healthy: '连接正常',
    unhealthy: '连接异常',
    not_checked: '尚未检查',
    not_applicable: '不适用',
  }
  return labels[String(status || '')] || '状态未知'
}

function authenticationStatusLabel(status?: string) {
  const labels: Record<string, string> = {
    configured: '已配置',
    missing: '缺少凭据',
    not_required: '无需认证',
  }
  return labels[String(status || '')] || '状态未知'
}

function runStatusLabel(status?: string) {
  return String(status || '') === 'not_observed' ? '未观测到运行轨迹' : '状态未知'
}

function idempotencyLabel(status?: string) {
  const labels: Record<string, string> = {
    idempotent: '已声明幂等',
    non_idempotent: '未声明幂等',
    unknown: '幂等性未知',
  }
  return labels[String(status || '')] || '幂等性未知'
}

function formatTime(value?: string | null) {
  if (!value) return '暂无记录'
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return '时间格式未知'
  return new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium', timeStyle: 'medium' }).format(parsed)
}

function knownContractReason(tool: StudioToolResource) {
  if (tool.source === 'cartridge_dlc') return '该 DLC MCP 的源码无法静态解析，内部实现不可观测。'
  if (tool.source === 'local_resource') return '该外部连接器未提供可验证的调用契约，内部实现不可观测。'
  return '未提供可读取实现或可验证连接契约，内部实现不可观测。'
}

function hasContractValue(value: unknown): boolean {
  if (!value || typeof value !== 'object') return false
  return Object.keys(value as Record<string, unknown>).length > 0
}

function JsonContract({ label, value }: { label: string; value: unknown }) {
  if (!hasContractValue(value)) return null
  const text = JSON.stringify(value, null, 2)
  return (
    <section className="cf-engineering-inspector-section cf-mcp-schema-contract">
      <header><Workflow aria-hidden="true" /><strong>{label}</strong></header>
      <pre className="cf-engineering-json" aria-label={label}>{text}</pre>
    </section>
  )
}

function DetailSummary({ title, icon: Icon, children }: { title: string; icon: LucideIcon; children: ReactNode }) {
  return (
    <section className="cf-engineering-mcp-summary cf-mcp-detail-card">
      <header><Icon aria-hidden="true" /><strong>{title}</strong></header>
      {children}
    </section>
  )
}

function DetailValue({ label, value }: { label: string; value: ReactNode }) {
  return <div><span>{label}</span><code title={typeof value === 'string' ? value : undefined}>{value}</code></div>
}

export function ExternalMcpDetailTemplate({
  tool,
  tab,
  connectionHealth,
  checking,
  onCheckConnectivity,
  notice,
}: {
  tool: StudioToolResource
  tab: ExternalMcpDetailTab
  connectionHealth?: McpConnectionHealth
  checking: boolean
  onCheckConnectivity: () => void
  notice?: string
}) {
  const connector = tool.connector
  const contract = tool.contract
  const health = connectionHealth || tool.health?.connection
  const run = tool.health?.run
  const serverTool = [contract?.server || tool.server, contract?.tool || tool.tool].filter(Boolean).join(' / ') || '未声明'
  const hasInputSchema = hasContractValue(contract?.input_schema)
  const hasOutputSchema = hasContractValue(contract?.output_schema)
  const connectionObserved = Boolean(health?.checked_at || (health?.status && !['not_checked', 'not_applicable'].includes(health.status)))
  const runObserved = Boolean(run?.last_run_at || (run?.status && run.status !== 'not_observed'))

  if (tab === 'contract') {
    return (
      <div className="cf-mcp-detail-template contract" aria-label="调用契约">
        {notice && <p role="alert">{notice}</p>}
        <DetailSummary title="调用契约" icon={ShieldCheck}>
          <DetailValue label="服务 / 工具" value={serverTool} />
          <DetailValue label="权限范围" value={(contract?.permissions || []).join(', ') || '未声明'} />
          <DetailValue label="副作用" value={contract?.read_only ? '只读' : contract?.side_effect || '未知'} />
          <DetailValue label="超时" value={`${contract?.timeout_ms ?? '未声明'} ms`} />
          <DetailValue label="重试" value={contract?.retry ? JSON.stringify(contract.retry) : '未声明'} />
          <DetailValue label="幂等性" value={idempotencyLabel(contract?.idempotency?.status)} />
        </DetailSummary>
        <JsonContract label="输入参数 Schema" value={contract?.input_schema} />
        <JsonContract label="输出 Schema" value={contract?.output_schema} />
        {!hasInputSchema && !hasOutputSchema && <section className="cf-mcp-contract-empty">
          <Workflow aria-hidden="true" />
          <strong>未声明输入/输出 Schema</strong>
          <span>当前调用仍受服务、权限、超时与副作用约束。</span>
        </section>}
      </div>
    )
  }

  if (tab === 'runs') {
    return (
      <div className="cf-mcp-detail-template runs" aria-label="检查记录">
        {notice && <p role="alert">{notice}</p>}
        {!connectionObserved && !runObserved ? <section className="cf-mcp-check-empty">
          <RadioTower aria-hidden="true" />
          <strong>尚未检查连接</strong>
          <span>先验证当前端点与认证配置是否可用。</span>
          <button type="button" disabled={checking} onClick={onCheckConnectivity}><TimerReset aria-hidden="true" />{checking ? '检查中...' : '测试连接'}</button>
        </section> : <>
          {connectionObserved && <DetailSummary title="连接检查" icon={RadioTower}>
            <DetailValue label="状态" value={connectionStatusLabel(health?.status)} />
            <DetailValue label="最近检查" value={formatTime(health?.checked_at)} />
            {health?.adapter && <DetailValue label="检查器" value={health.adapter} />}
            {health?.retryable !== undefined && <DetailValue label="可重试" value={health.retryable ? '可以' : '不可以'} />}
            {health?.code && <DetailValue label="错误代码" value={health.code} />}
            <footer><button type="button" disabled={checking} onClick={onCheckConnectivity}><TimerReset aria-hidden="true" />{checking ? '检查中...' : '重新检查'}</button></footer>
          </DetailSummary>}
          {runObserved ? <DetailSummary title="运行记录" icon={Workflow}>
            <DetailValue label="状态" value={runStatusLabel(run?.status)} />
            <DetailValue label="最近调用" value={formatTime(run?.last_run_at)} />
            {run?.code && <DetailValue label="轨迹代码" value={run.code} />}
          </DetailSummary> : <section className="cf-mcp-run-empty"><Workflow aria-hidden="true" /><span>尚无工具运行记录</span></section>}
        </>}
      </div>
    )
  }

  return (
    <div className="cf-mcp-detail-template connection" aria-label="连接详情">
      {notice && <p role="alert">{notice}</p>}
      <DetailSummary title="连接详情" icon={RadioTower}>
        <DetailValue label="连接器身份" value={connector?.identity || tool.resource_id || tool.id} />
        <DetailValue label="服务 / 工具" value={serverTool} />
        {connector?.endpoint?.reference && <DetailValue label="端点引用" value={connector.endpoint.reference} />}
        {connector?.openapi?.reference && <DetailValue label="OpenAPI 引用" value={connector.openapi.reference} />}
        {(connector?.endpoint?.transport || connector?.command?.transport) && <DetailValue label="传输方式" value={connector?.endpoint?.transport || connector?.command?.transport} />}
        {connector?.command?.reference && <DetailValue label="命令引用" value={connector.command.reference} />}
        <DetailValue label="连接状态" value={connectionStatusLabel(connectionHealth?.status || tool.health?.connection?.status)} />
      </DetailSummary>
      <DetailSummary title="认证与访问" icon={KeyRound}>
        {connector?.authentication?.reference && <DetailValue label="认证引用" value={connector.authentication.reference} />}
        <DetailValue label="认证状态" value={authenticationStatusLabel(connector?.authentication?.status)} />
        {Boolean(contract?.permissions?.length) && <DetailValue label="权限范围" value={(contract?.permissions || []).join(', ')} />}
        <DetailValue label="透明度" value={tool.transparency || 'unknown'} />
      </DetailSummary>
    </div>
  )
}

export function UnauditableMcpDetailTemplate({ tool, notice }: { tool: StudioToolResource; notice?: string }) {
  const contract = tool.contract
  const serverTool = [contract?.server || tool.server, contract?.tool || tool.tool].filter(Boolean).join(' / ') || '未声明'
  const hasInputSchema = hasContractValue(contract?.input_schema)
  const hasOutputSchema = hasContractValue(contract?.output_schema)
  return (
    <div className="cf-mcp-detail-template contract unauditable" aria-label="已知契约">
      {notice && <p role="alert">{notice}</p>}
      <DetailSummary title="已知契约" icon={ShieldCheck}>
        <DetailValue label="服务 / 工具" value={serverTool} />
        <DetailValue label="透明度" value={tool.transparency || 'unknown'} />
        <DetailValue label="权限范围" value={(contract?.permissions || []).join(', ') || '未声明'} />
        <DetailValue label="副作用" value={contract?.read_only ? '只读' : contract?.side_effect || '未知'} />
        <DetailValue label="不可观测原因" value={knownContractReason(tool)} />
      </DetailSummary>
      <JsonContract label="已知输入 Schema" value={contract?.input_schema} />
      <JsonContract label="已知输出 Schema" value={contract?.output_schema} />
      {!hasInputSchema && !hasOutputSchema && <section className="cf-mcp-contract-empty"><Workflow aria-hidden="true" /><strong>未声明输入/输出 Schema</strong><span>当前只能核对已知调用边界。</span></section>}
      <section className="cf-mcp-transparency-empty"><CircleAlert aria-hidden="true" />当前 MCP 不可审计，不显示源码编辑器或内部操作图。</section>
    </div>
  )
}
