// API 工具：封装所有对后端的 fetch 调用，统一走 /api 前缀

// 基础请求方法：所有 API 调用共用
export interface RuntimeErrorEnvelope {
  schema: 'runtime_error_envelope.v1' | string
  error_id: string
  code: string
  category: string
  message: string
  run_id: string
  node_id: string
  source: string
  missing_inputs: string[]
  retryable: boolean
  recoverable: boolean
  recovery_actions: string[]
  cause_chain: Array<{ type: string; message: string }>
  context?: Record<string, any>
  created_at?: string
}

export class ApiError extends Error {
  status: number
  envelope?: RuntimeErrorEnvelope
  detail?: any

  constructor(message: string, status: number, envelope?: RuntimeErrorEnvelope, detail?: any) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.envelope = envelope
    this.detail = detail
  }
}

export async function api<T = any>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json', ...(options.headers as Record<string, string>) },
    ...options,
  })
  if (!res.ok) {
    const raw = await res.text()
    let payload: any = null
    try { payload = JSON.parse(raw) } catch { /* retain plain-text server errors */ }
    const envelope = payload?.error_envelope as RuntimeErrorEnvelope | undefined
    const detail = payload?.detail
    const message = envelope?.message || (typeof detail === 'string' ? detail : detail?.message || raw || `Request failed (${res.status})`)
    throw new ApiError(message, res.status, envelope, detail)
  }
  return res.json() as Promise<T>
}

export async function apiText(path: string, options: RequestInit = {}): Promise<string> {
  const res = await fetch(path, {
    headers: { ...(options.headers as Record<string, string>) },
    ...options,
  })
  if (!res.ok) throw new Error(await res.text())
  return res.text()
}

// ── 卡带相关类型 ──────────────────────────────────────────────
export interface CartridgeSummary {
  id: string
  name: string
  version: string
  kind?: string
  category?: string
  description?: string
  publisher?: any
  branding?: any
  runtime?: { type?: string; adapter?: string; config?: any }
  base_contract?: any
  runtime_contract?: any
  delivery_readiness?: any
  protocol_certification?: any
  workspace?: any
  inputs?: CartridgeInput[]
  outputs?: any[]
  mcp_tools?: McpTool[]
  resource_requirements?: ResourceRequirement[]
  llm_recipe?: any
  portable_dlc?: any
  source?: string
  editable?: boolean
}

export interface ResourceRequirement {
  role: string
  kinds: string[]
  required?: boolean
  capabilities?: string[]
  constraints?: Record<string, any>
}

export interface CartridgeInput {
  id: string
  label?: string
  type: 'text' | 'textarea' | 'select' | string
  required?: boolean
  default?: string
  placeholder?: string
  options?: { value: string; label: string }[]
}

export interface CartridgeDetail extends CartridgeSummary {
  manifest?: any
  root_flow?: any
  package_path?: string
  welcome_content?: string
  welcome_html_content?: string
}

export interface RunResult {
  run_id: string
  cartridge_id: string
  cartridge_version?: string
  status: string
  current_state: string
  inputs?: Record<string, any>
  test_mode?: Record<string, any>
  run_mode?: string
  probe_range?: TestProbeRange & { node_count?: number }
  artifacts?: ArtifactItem[]
  delivery?: {
    summary?: string
    artifacts?: ArtifactItem[]
    actions?: { label: string; url: string }[]
  }
  created_at?: string
  updated_at?: string
  data_chain?: DataChainReport
  pending_interaction?: any
  base?: any
  protocol?: any
  compatibility?: CompatibilityReport
  error?: RuntimeErrorEnvelope
  errors?: RuntimeErrorEnvelope[]
}

export interface DataChainBreak {
  node: string
  title?: string
  key: string
  detail?: string
  seeded_by_probe?: boolean
}

export interface DataChainReport {
  passed: boolean
  summary?: string
  breaks: DataChainBreak[]
  probe_seeded?: string[] | null
}

export interface ArtifactItem {
  artifact_id?: string
  name: string
  type: string
  url: string
  path?: string
  display_path?: string
  mime_type?: string
  source?: any
}

// ── Flow 实验室相关类型 ──────────────────────────────────────────────
export interface FlowGraph {
  id?: string
  name?: string
  mode?: string
  cartridge_id?: string
  nodes: FlowNode[]
  edges: FlowEdge[]
  sub_flows?: any[]
}

export interface FlowNode {
  id: string
  title: string
  type: string
  action?: string
  next?: string
  kind?: string
  executor?: string
  effect?: string
  display_name?: string
  component_ref?: string
  interaction_mode?: 'display' | 'collect' | 'review' | string
  input_binding?: Record<string, string>
  action_routes?: Record<string, string>
  output?: string
  display?: { label?: string; suffix?: string; [key: string]: any }
  input_kind?: string
  source?: string
  input_schema?: any
  output_contract?: string
  decision_contract?: any
  decision_test_mode?: string
  mock_decision_envelope?: any
  primary_output?: string
  tool_binding?: string
  allowed_tools?: string[]
  mcp_binding?: any
  failure_policy?: string
  permission?: string
  audit_log?: boolean
  endpoint?: string
  timeout_ms?: number
  x: number
  y: number
  scope?: string
  locked?: boolean
  entry_kind?: string
  template_id?: string
  agent?: string
  tools?: any[]
  tool_summary?: { mcp?: string; builtin?: string }
  params?: Record<string, any>
  model_role?: string
  data?: any
}

export interface FlowEdge {
  from: string
  to: string
  scope?: string
  label?: string
}

export interface FlowLabItem extends CartridgeSummary {
  flow_kind?: string
}

export interface FlowLabDetail {
  cartridge: CartridgeDetail
  graph: FlowGraph
  runs: RunResult[]
  latest_run_events: FlowEvent[]
  compatibility?: CompatibilityReport
  steward: {
    status?: string
    role?: string
    message?: string
    context_keys?: string[]
  }
}

export interface FlowEvent {
  state?: string
  type?: string
  message?: string
  data?: {
    action?: string
    output?: string
    input?: string
    skipped?: boolean
    tool_results?: any[]
    [key: string]: any
  }
  error_envelope?: RuntimeErrorEnvelope
  timestamp?: string
  created_at?: string
}

export interface TestProbeRange {
  start_node_id: string
  end_node_id: string
  node_ids: string[]
}

export interface FlowFiles {
  manifest?: string
  root_flow?: string
  welcome?: string
  [key: string]: string | undefined
}

export interface CartridgeAsset {
  id: string
  kind: string
  path: string
  media_type: string
  sha256: string
  size: number
  executable: false
  content?: string
  encoding?: string
}

export interface InteractionComponent {
  id: string
  version: string
  runtime: 'passive' | 'sandboxed'
  entry: { type: 'asset'; ref: string }
  supported_modes: Array<'display' | 'collect' | 'review'>
  input_schema?: Record<string, any> | string
  actions: Array<{ id: string; label?: string; payload_schema?: Record<string, any> | string }>
  host_capabilities?: string[]
}

export interface CartridgeAssetsResponse {
  cartridge_id: string
  assets: CartridgeAsset[]
  components: InteractionComponent[]
  files: FlowFiles
}

export interface McpTool {
  id: string
  name: string
  type: 'builtin' | 'mcp' | string
  server: string
  tool: string
  description?: string
  default_params?: Record<string, any>
  params_schema?: Record<string, any>
  required?: boolean
  contract?: Record<string, any>
  enabled?: boolean
}

export interface BaseImplementationResponse {
  ok: boolean
  base: any
}

export interface StudioConformanceResponse {
  available: boolean
  report_path?: string
  command?: string
  report?: {
    schema: string
    status: string
    generated_at: string
    tests: { status: string; total: number; counts: Record<string, number> }
    capabilities: { status: string; declared: number; counts: Record<string, number>; items?: any[] }
  }
}

export interface StudioTodoItem {
  id: string
  text: string
  raw: string
  checked: boolean
  section: string
  priority: string
  line: number
}

export interface StudioTodoResponse {
  title: string
  total: number
  open: number
  completed: number
  items: StudioTodoItem[]
  source: string
  file_url: string
  template_url: string
}

export interface CompatibilityFinding {
  severity: 'blocker' | 'warning' | 'info' | string
  code: string
  message: string
}

export interface CompatibilityReport {
  ok: boolean
  status: string
  legacy?: boolean
  base?: any
  cartridge?: any
  protocol?: any
  profiles?: any
  capabilities?: any
  tools?: any
  delivery_readiness?: any
  summary?: { blocker?: number; warning?: number; info?: number }
  findings?: CompatibilityFinding[]
}

export interface ProtocolCertificationReport {
  ok: boolean
  status: string
  label?: string
  protocol?: any
  base?: any
  cartridge?: any
  compatibility?: CompatibilityReport
  summary?: { blocker?: number; warning?: number; info?: number }
  findings?: CompatibilityFinding[]
}

export interface McpToolsResponse {
  cartridge_id: string
  mcp_tools: McpTool[]
  files: FlowFiles
}

export interface ValidationResponse {
  valid: boolean
  errors: string[]
  warnings: string[]
  summary?: string
}

export interface StewardSuggestion {
  status: string
  summary?: string
  steps: string[]
  patches: any[]
}

export interface NodeUpdateResult {
  status: string
  node_id: string
  files: FlowFiles
  validation: ValidationResponse
  graph: FlowGraph
}

export interface NodeCreatePayload {
  files: FlowFiles
  template_id: string
  node_id: string
  title?: string
  after_node_id?: string
  insert_mode?: 'insert' | 'branch'
}

export interface FlowAssistantDraftNode {
  id: string
  title: string
  category: string
  preset: string
  type?: string
  action?: string
  kind?: string
  executor?: string
  effect?: string
  display?: any
  output_contract?: string
  decision_contract?: any
  decision_test_mode?: string
  mock_decision_envelope?: any
  tool_binding?: string
  allowed_tools?: string[]
  mcp_binding?: any
  failure_policy?: string
  permission?: string
  audit_log?: boolean
  tools?: any[]
  params?: Record<string, any>
  description?: string
  preset_config?: Record<string, string>
}

export interface FlowAssistantDraftEdge {
  from: string
  to: string
  label?: string
}

export type FlowAssistantMessage =
  | { type: 'clarify' | 'node_guidance'; message: string; thinking_steps?: string[] }
  | {
    type: 'graph_ops'
    summary: string
    understanding: string
    thinking_steps?: string[]
    operations: Array<{ op: string; node_ids?: string[]; target?: string }>
  }
  | {
    type: 'flow_draft'
    summary: string
    understanding: string
    thinking_steps?: string[]
    validation?: { ok: boolean; issues: string[]; repairs: string[]; metrics?: { max_edge_length?: number; edge_count?: number; node_count?: number } }
    mermaid: string
    nodes: FlowAssistantDraftNode[]
    edges: FlowAssistantDraftEdge[]
  }

export interface FlowAssistantResponse {
  ok: boolean
  message: FlowAssistantMessage
  meta?: any
}

// ── LLM Provider 相关类型 ──────────────────────────────────────────────
export interface LlmProvider {
  id: string
  name: string
  api_type: string
  base_url?: string
  default_model?: string
  wire_api?: string
  enabled?: boolean
  timeout?: number
  has_key?: boolean
  key_preview?: string
  tested_ok?: boolean
  source?: string
}

export interface LlmAssignment {
  provider_id?: string
  model?: string
}

export interface LlmAssignments {
  version: number
  defaults: Record<string, LlmAssignment>
  cartridges: Record<string, Record<string, LlmAssignment>>
  nodes: Record<string, Record<string, LlmAssignment>>
}

export interface LlmTestResult {
  ok: boolean
  provider_id?: string
  model?: string
  content?: string
  capability?: string
  error?: string
  status_code?: number
  retryable?: boolean
}

export interface StudioToolResource {
  id: string
  name: string
  kind: 'builtin' | 'mcp' | 'remote_api' | 'plugin' | string
  description?: string
  endpoint?: string
  command?: string
  args?: string
  openapi_url?: string
  http_method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE' | string
  auth_env?: string
  auth_header?: string
  auth_scheme?: string
  capabilities?: string[]
  read_only?: boolean
  package_mode?: 'base' | 'descriptor' | 'external' | string
  enabled?: boolean
  locked?: boolean
  server?: string
  tool?: string
}

export interface StudioResources {
  version: number
  tools: StudioToolResource[]
  bindings: {
    roles?: Record<string, Record<string, string>>
    tools?: Record<string, string[]>
  }
  builtin_tools: StudioToolResource[]
}

export interface StudioCredential {
  key: string
  label: string
  secret: boolean
  source: 'local' | 'process' | string
  has_value: boolean
  preview: string
  updated_at?: string
}

export interface StudioEnvironmentReference {
  key: string
  label: string
  owners: string[]
  configured: boolean
}

export interface StudioSystemCheck {
  id: string
  label: string
  status: 'ok' | 'warning' | 'missing' | 'blocked' | string
  version: string
  path: string
}

export interface StudioEnvironmentSnapshot {
  credentials: StudioCredential[]
  references: StudioEnvironmentReference[]
  checks: StudioSystemCheck[]
  paths: Record<string, string>
}

export interface StudioPackageItem {
  filename: string
  url: string
  size: number
  modified_at: string
  cartridge_id: string
  name: string
  version: string
  package_mode: string
}

export interface PortabilityReport {
  schema: 'cartridgeflow.portability_report.v1' | string
  status: 'ok' | 'blocked' | string
  summary: {
    portable: number
    local_rebind: number
    missing_blockers: number
    forbidden: number
    scanned_files: number
  }
  portable: any[]
  local_rebind: any[]
  missing_blockers: any[]
  forbidden: any[]
}

export interface StudioReleasePreflight {
  cartridge: { id: string; name: string; version: string; source: string; editable: boolean }
  compatibility: CompatibilityReport
  certification: ProtocolCertificationReport
  environment: { status: string; summary?: string; items: any[] }
  dependencies: { status: string; summary?: string; items: any[] }
  models: { status: string; items: any[] }
  resources: { status: string; items: any[]; descriptor?: any }
  package_hygiene: { status: string; items: any[]; scanned_files?: number }
  portability: PortabilityReport
  issues: { area: string; severity: string; message: string }[]
  dev_ready: boolean
  production_ready: boolean
}

// ── 卡带 API ──────────────────────────────────────────────
export const fetchCartridges = () => api<{ items: CartridgeSummary[] }>('/api/cartridges')

export const fetchCartridgeRuns = () => api<{ items: RunResult[] }>('/api/cartridge-runs')

export const fetchCartridge = (id: string) => api<CartridgeDetail>(`/api/cartridges/${id}`)

export const fetchBaseImplementation = () => api<BaseImplementationResponse>('/api/base')

export const fetchStudioConformance = () => api<StudioConformanceResponse>('/api/studio/conformance')

export const fetchStudioTodo = () => api<StudioTodoResponse>('/api/studio/todo')

export const fetchStudioTodoFile = () => apiText('/api/studio/todo/file')

export const fetchStudioTodoTemplate = () => apiText('/api/studio/todo/template')

export const fetchCartridgeCompatibility = (id: string) =>
  api<CompatibilityReport>(`/api/cartridges/${id}/compatibility`)

export const fetchCartridgeCertification = (id: string) =>
  api<ProtocolCertificationReport>(`/api/cartridges/${id}/certification`)

export const createCartridgeRun = (cartridgeId: string, inputs: Record<string, any>, testMode?: Record<string, any>) =>
  api<RunResult>('/api/cartridge-runs', {
    method: 'POST',
    body: JSON.stringify({ cartridge_id: cartridgeId, inputs, ...(testMode ? { test_mode: testMode } : {}) }),
  })

export const fetchCartridgeRun = (runId: string) =>
  api<RunResult>(`/api/cartridge-runs/${runId}`)

export const deleteCartridgeRun = (runId: string) =>
  api<{ run_id: string; deleted: boolean }>(`/api/cartridge-runs/${encodeURIComponent(runId)}`, { method: 'DELETE' })

export interface RunDiagnosticBundle {
  schema: string
  generated_at?: string
  run_id: string
  cartridge_id: string
  summary: {
    status?: string
    current_state?: string
    error_code?: string | null
    error_category?: string | null
    event_count: number
    checkpoint_count: number
    artifact_count: number
  }
  run: RunResult
  events: FlowEvent[]
  checkpoints: any[]
}

export const fetchCartridgeRunDiagnostics = (runId: string) =>
  api<RunDiagnosticBundle>(`/api/cartridge-runs/${encodeURIComponent(runId)}/diagnostics`)

export const fetchCartridgeRunEvents = (runId: string) =>
  api<{ items: FlowEvent[] }>(`/api/cartridge-runs/${runId}/events`)

export const controlCartridgeRun = (
  runId: string,
  action: 'cancel' | 'pause' | 'resume' | 'retry_current_node' | 'resume_checkpoint' | 'rollback_to_node' | 'restart_run',
  options: { target_node?: string; confirm_side_effect?: boolean; feedback?: Record<string, any> } = {},
) => api<RunResult>(`/api/cartridge-runs/${runId}/control`, {
  method: 'POST',
  body: JSON.stringify({ action, ...options }),
})

export const fetchCartridgeRunCheckpoints = (runId: string) =>
  api<{ run_id: string; items: any[] }>(`/api/cartridge-runs/${runId}/checkpoints`)

export const answerPendingInteraction = (
  runId: string,
  values: Record<string, any> | string,
  options: { action_id?: string; input_revision?: string | number; idempotency_key?: string; draft_hash?: string } = {},
) =>
  api<{ run: RunResult; events: FlowEvent[] }>(`/api/cartridge-runs/${runId}/pending-interaction/answer`, {
    method: 'POST',
    body: JSON.stringify({ ...(typeof values === 'string' ? { answer: values } : { values }), ...options }),
  })

export interface InteractionSandboxSession {
  schema: string
  run_id: string
  cartridge_id: string
  node_id: string
  component_id: string
  interaction_id: string
  channel_id: string
  nonce: string
  url: string
  origin: string
  host_capabilities: string[]
  input_revision: number | string
  input: Record<string, any>
  policy: Record<string, any>
}

export const fetchInteractionSandbox = (runId: string, interactionId: string) =>
  api<InteractionSandboxSession>(`/api/cartridge-runs/${encodeURIComponent(runId)}/interaction/${encodeURIComponent(interactionId)}/sandbox`)

export const revokeInteractionSandbox = (runId: string, interactionId: string) =>
  api<{ ok: boolean }>(`/api/cartridge-runs/${encodeURIComponent(runId)}/interaction/${encodeURIComponent(interactionId)}/sandbox`, { method: 'DELETE' })

export const sendInteractionHostRequest = (runId: string, interactionId: string, message: Record<string, any>) =>
  api<Record<string, any>>(`/api/cartridge-runs/${encodeURIComponent(runId)}/interaction/${encodeURIComponent(interactionId)}/host-request`, {
    method: 'POST',
    body: JSON.stringify(message),
  })

export const fetchDlcRunContext = (runId: string) =>
  api<{ schema: string; run_id: string; cartridge_id: string; frontend_url: string; context: Record<string, any>; artifacts?: Array<Record<string, any>>; pending_interaction?: any }>(`/api/cartridge-runs/${runId}/dlc-context`)

export const packageCartridge = (id: string, packageMode: 'dev' | 'production' = 'dev') =>
  api<{ ok: boolean; cartridge_id: string; filename: string; package_mode: string; url: string; size: number; mcp_tool_count: number; compatibility?: any; portability?: PortabilityReport }>(`/api/cartridges/${id}/package`, {
    method: 'POST',
    body: JSON.stringify({ package_mode: packageMode }),
  })

export async function importCartridgePackage(file: File, installMode: 'keep_existing' | 'replace' = 'keep_existing') {
  const contentBase64 = await new Promise<string>((resolve, reject) => {
    const reader = new FileReader()
    reader.onerror = () => reject(reader.error || new Error('Failed to read cartridge file'))
    reader.onload = () => {
      const result = String(reader.result || '')
      resolve(result.includes(',') ? result.split(',')[1] : result)
    }
    reader.readAsDataURL(file)
  })
  return api<{ ok: boolean; cartridge: CartridgeDetail; installed_path: string; replaced: boolean }>('/api/cartridges/import', {
    method: 'POST',
    body: JSON.stringify({ filename: file.name, content_base64: contentBase64, install_mode: installMode }),
  })
}

export const uninstallInstalledCartridge = (id: string) =>
  api<{ ok: boolean; cartridge_id: string }>(`/api/cartridges/${id}/installed`, { method: 'DELETE' })

export const cloneCartridgeToDev = (id: string, newId: string, name: string, description = '') =>
  api<{ ok: boolean; cartridge: CartridgeDetail; id: string; path: string }>(`/api/cartridges/${id}/clone-to-dev`, {
    method: 'POST',
    body: JSON.stringify({ new_id: newId, name, description }),
  })

export interface UploadedFileResult {
  ok: boolean
  filename: string
  path: string
  size: number
}

export async function uploadWorkspaceFile(file: File): Promise<UploadedFileResult> {
  const content = await file.text()
  return api<UploadedFileResult>('/api/uploads/file', {
    method: 'POST',
    body: JSON.stringify({ filename: file.name, content }),
  })
}

// ── Flow 实验室 API ──────────────────────────────────────────────
export const fetchLabFlows = () => api<{ items: FlowLabItem[] }>('/api/lab/flows')

export const createDevFlow = (flowId: string, name: string, description: string) =>
  api<{ id: string; path: string; manifest: any; root_flow: any }>('/api/lab/flows', {
    method: 'POST',
    body: JSON.stringify({ flow_id: flowId, name, description }),
  })

export const deleteLabFlow = (id: string) =>
  api<{ ok: boolean; id: string }>(`/api/lab/flows/${id}`, { method: 'DELETE' })

export const fetchLabFlow = (id: string) => api<FlowLabDetail>(`/api/lab/flows/${id}`)

export const fetchLabFlowFiles = (id: string) =>
  api<{ cartridge_id: string; files: FlowFiles }>(`/api/lab/flows/${id}/files`)

export const fetchCartridgeAssets = (id: string) =>
  api<CartridgeAssetsResponse>(`/api/lab/flows/${id}/assets`)

export const saveCartridgeAsset = (id: string, assetId: string, asset: Omit<CartridgeAsset, 'sha256' | 'size' | 'executable'> & { encoding?: string }) =>
  api<{ status: string; asset: CartridgeAsset; files: FlowFiles }>(`/api/lab/flows/${id}/assets/${assetId}`, {
    method: 'PUT',
    body: JSON.stringify(asset),
  })

export const deleteCartridgeAsset = (id: string, assetId: string) =>
  api<{ status: string; asset_id: string; files: FlowFiles }>(`/api/lab/flows/${id}/assets/${assetId}`, { method: 'DELETE' })

export const saveInteractionComponent = (id: string, componentId: string, component: InteractionComponent) =>
  api<{ status: string; component: InteractionComponent; files: FlowFiles }>(`/api/lab/flows/${id}/interaction-components/${componentId}`, {
    method: 'PUT',
    body: JSON.stringify({ component }),
  })

export const deleteInteractionComponent = (id: string, componentId: string) =>
  api<{ status: string; component_id: string; files: FlowFiles }>(`/api/lab/flows/${id}/interaction-components/${componentId}`, { method: 'DELETE' })

export const fetchMcpTools = (id: string) =>
  api<McpToolsResponse>(`/api/lab/flows/${id}/mcp-tools`)

export const createMcpTool = (id: string, tool: Partial<McpTool>) =>
  api<{ status: string; tool: McpTool; mcp_tools: McpTool[]; files: FlowFiles }>(`/api/lab/flows/${id}/mcp-tools`, {
    method: 'POST',
    body: JSON.stringify(tool),
  })

export const updateMcpTool = (id: string, toolId: string, tool: Partial<McpTool>) =>
  api<{ status: string; tool: McpTool; mcp_tools: McpTool[]; files: FlowFiles }>(`/api/lab/flows/${id}/mcp-tools/${toolId}`, {
    method: 'PUT',
    body: JSON.stringify(tool),
  })

export const deleteMcpTool = (id: string, toolId: string) =>
  api<{ status: string; tool_id: string; mcp_tools: McpTool[]; files: FlowFiles }>(`/api/lab/flows/${id}/mcp-tools/${toolId}`, {
    method: 'DELETE',
  })

export const saveLabFlowFile = (id: string, fileType: string, content: string) =>
  api<{ file_type: string; saved: boolean }>(`/api/lab/flows/${id}/files/${fileType}`, {
    method: 'PUT',
    body: JSON.stringify({ content }),
  })

export const validateLabFlow = (id: string, files: FlowFiles) =>
  api<ValidationResponse>(`/api/lab/flows/${id}/validate`, {
    method: 'POST',
    body: JSON.stringify({ files }),
  })

export const fetchLabFlowCompatibility = (id: string, files: FlowFiles) =>
  api<CompatibilityReport>(`/api/lab/flows/${id}/compatibility`, {
    method: 'POST',
    body: JSON.stringify({ files }),
  })

export const fetchLabFlowCertification = (id: string, files: FlowFiles) =>
  api<ProtocolCertificationReport>(`/api/lab/flows/${id}/certification`, {
    method: 'POST',
    body: JSON.stringify({ files }),
  })

export const applyLabFlowCertification = (id: string, files: FlowFiles) =>
  api<{ ok: boolean; cartridge_id: string; label: string; report: ProtocolCertificationReport; files: FlowFiles; manifest: any }>(`/api/lab/flows/${id}/certification/apply`, {
    method: 'POST',
    body: JSON.stringify({ files }),
  })

export const previewLabFlowGraph = (id: string, files: FlowFiles) =>
  api<{ graph: FlowGraph }>(`/api/lab/flows/${id}/preview-graph`, {
    method: 'POST',
    body: JSON.stringify({ files }),
  })

export const suggestFlowChanges = (id: string, intent: string, files: FlowFiles, selectedNode: any, useLlm: boolean) =>
  api<StewardSuggestion>(`/api/lab/flows/${id}/steward/suggest`, {
    method: 'POST',
    body: JSON.stringify({ intent, files, selected_node: selectedNode, use_llm: useLlm }),
  })

export const applyStewardPatches = (id: string, files: FlowFiles, patches: any[], selectedNode: any) =>
  api<any>(`/api/lab/flows/${id}/steward/apply`, {
    method: 'POST',
    body: JSON.stringify({ files, patches, selected_node: selectedNode }),
  })

export const updateFlowNode = (id: string, nodeId: string, payload: any) =>
  api<NodeUpdateResult>(`/api/lab/flows/${id}/nodes/${nodeId}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  })

export const createFlowNode = (id: string, payload: NodeCreatePayload) =>
  api<NodeUpdateResult>(`/api/lab/flows/${id}/nodes`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })

export const deleteFlowNode = (id: string, nodeId: string, files: FlowFiles) =>
  api<NodeUpdateResult>(`/api/lab/flows/${id}/nodes/${nodeId}`, {
    method: 'DELETE',
    body: JSON.stringify({ files }),
  })

export const saveFlowLayout = (id: string, _files: FlowFiles, layout: Record<string, { x: number; y: number }>) =>
  api<{ status: string; files: FlowFiles; graph: FlowGraph }>(`/api/lab/flows/${id}/layout`, {
    method: 'PUT',
    body: JSON.stringify({ layout }),
  })

export const saveFlowEdges = (id: string, files: FlowFiles, edges: FlowEdge[]) =>
  api<{ status: string; files: FlowFiles; graph: FlowGraph; validation: ValidationResponse }>(`/api/lab/flows/${id}/edges`, {
    method: 'PUT',
    body: JSON.stringify({ files, edges }),
  })

export const askFlowAssistant = (id: string, message: string, graph: FlowGraph, files: FlowFiles) =>
  api<FlowAssistantResponse>(`/api/lab/flows/${id}/assistant`, {
    method: 'POST',
    body: JSON.stringify({ message, graph, files }),
  })

export const fetchLabFlowRuns = (id: string) =>
  api<{ cartridge_id: string; items: RunResult[]; latest_run_events: FlowEvent[] }>(`/api/lab/flows/${id}/runs`)

export const testRunFlow = (id: string, inputs?: Record<string, string>, probeRange?: TestProbeRange, testMode?: Record<string, any>) =>
  api<{ run: RunResult; events: FlowEvent[] }>(`/api/lab/flows/${id}/test-run`, {
    method: 'POST',
    body: JSON.stringify({ inputs: inputs || {}, ...(probeRange ? { probe_range: probeRange } : {}), ...(testMode ? { test_mode: testMode } : {}) }),
  })

// ── LLM Provider API ──────────────────────────────────────────────
export const fetchLlmProviders = () => api<{ providers: LlmProvider[]; paths: any }>('/api/llm/providers')

export const fetchLlmAssignments = () => api<LlmAssignments>('/api/llm/assignments')

export const saveLlmAssignments = (assignments: LlmAssignments) =>
  api<{ ok: boolean; assignments: LlmAssignments }>('/api/llm/assignments', {
    method: 'PUT',
    body: JSON.stringify(assignments),
  })

export const createLlmProvider = (provider: Record<string, any>) =>
  api<{ ok: boolean; provider: LlmProvider }>('/api/llm/providers', {
    method: 'POST',
    body: JSON.stringify(provider),
  })

export const updateLlmProvider = (providerId: string, provider: Record<string, any>) =>
  api<{ ok: boolean; provider: LlmProvider }>(`/api/llm/providers/${encodeURIComponent(providerId)}`, {
    method: 'PUT',
    body: JSON.stringify(provider),
  })

export const deleteLlmProvider = (providerId: string) =>
  api<{ ok: boolean }>(`/api/llm/providers/${encodeURIComponent(providerId)}`, { method: 'DELETE' })

export const activateLlmProvider = (providerId: string) =>
  api<{ ok: boolean; provider: LlmProvider }>(`/api/llm/providers/${encodeURIComponent(providerId)}/activate`, { method: 'POST' })

export const testLlmProvider = (providerId: string, model = '') =>
  api<LlmTestResult>('/api/llm/test', {
    method: 'POST',
    body: JSON.stringify({ provider_id: providerId, model, prompt: 'OK' }),
  })

export const fetchStudioResources = () => api<StudioResources>('/api/studio/resources')

export const saveStudioResources = (resources: Omit<StudioResources, 'builtin_tools'> | StudioResources) =>
  api<{ ok: boolean; resources: Omit<StudioResources, 'builtin_tools'> }>('/api/studio/resources', {
    method: 'PUT',
    body: JSON.stringify(resources),
  })

export const fetchStudioEnvironment = () => api<StudioEnvironmentSnapshot>('/api/studio/environment')

export const createStudioCredential = (credential: Record<string, any>) =>
  api<{ ok: boolean; credential: StudioCredential }>('/api/studio/environment/credentials', {
    method: 'POST',
    body: JSON.stringify(credential),
  })

export const updateStudioCredential = (key: string, credential: Record<string, any>) =>
  api<{ ok: boolean; credential: StudioCredential }>(`/api/studio/environment/credentials/${encodeURIComponent(key)}`, {
    method: 'PUT',
    body: JSON.stringify(credential),
  })

export const deleteStudioCredential = (key: string) =>
  api<{ ok: boolean }>(`/api/studio/environment/credentials/${encodeURIComponent(key)}`, { method: 'DELETE' })

export const fetchStudioPackages = () => api<{ items: StudioPackageItem[] }>('/api/studio/packages')

export const fetchStudioReleasePreflight = (cartridgeId: string) =>
  api<StudioReleasePreflight>(`/api/studio/release/${encodeURIComponent(cartridgeId)}/preflight`)
