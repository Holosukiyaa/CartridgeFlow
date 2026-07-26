// API 工具：封装所有对后端的 fetch 调用，统一走 /api 前缀

// 基础请求方法：所有 API 调用共用
import type { RuntimeErrorEnvelope, CartridgeSummary, CartridgeDetail, RunResult, FlowGraph, FlowEdge, FlowAnnotation, FlowLabItem, FlowLabDetail, FlowEvent, TestProbeRange, FlowFiles, CartridgeAsset, InteractionComponent, CartridgeAssetsResponse, McpTool, BaseImplementationResponse, StudioConformanceResponse, StudioTodoResponse, CompatibilityReport, ProtocolCertificationReport, McpToolsResponse, ValidationResponse, NodeUpdateResult, NodeCreatePayload, LlmProvider, LlmAssignments, LlmConfigBundle, LlmDetectionResult, LlmTestResult, StudioResources, StudioCredential, StudioEnvironmentSnapshot, StudioPackageItem, PortabilityReport, StudioReleasePreflight } from './api.types.ts'
export type * from './api.types.ts'

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
    const detailMessage = typeof detail === 'string' ? detail : detail?.message
    const message = (path.startsWith('/api/llm/') && detailMessage)
      || envelope?.message
      || detailMessage
      || raw
      || `Request failed (${res.status})`
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

export const openLabFlowDirectory = (id: string) =>
  api<{ ok: boolean; id: string; path: string }>(`/api/lab/flows/${encodeURIComponent(id)}/open-directory`, { method: 'POST' })

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

export const saveFlowAnnotations = (id: string, annotations: FlowAnnotation[]) =>
  api<{ status: string; files: FlowFiles; graph: FlowGraph }>(`/api/lab/flows/${id}/annotations`, {
    method: 'PUT',
    body: JSON.stringify({ annotations }),
  })

export const fetchLabFlowRuns = (id: string) =>
  api<{ cartridge_id: string; items: RunResult[]; latest_run_events: FlowEvent[] }>(`/api/lab/flows/${id}/runs`)

export const runFlow = (id: string, inputs?: Record<string, string>, probeRange?: TestProbeRange) =>
  api<{ run: RunResult; events: FlowEvent[] }>(`/api/lab/flows/${id}/test-run`, {
    method: 'POST',
    body: JSON.stringify({
      inputs: inputs || {},
      ...(probeRange ? { probe_range: probeRange } : {}),
      test_mode: { decision: 'live_collaboration' },
    }),
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

export const detectLlmProvider = (payload: { provider_id?: string; base_url: string; api_key?: string; preferred_model?: string }) =>
  api<LlmDetectionResult>('/api/llm/detect', {
    method: 'POST',
    body: JSON.stringify(payload),
  })

export const testLlmProvider = (providerId: string, model = '') =>
  api<LlmTestResult>('/api/llm/test', {
    method: 'POST',
    body: JSON.stringify({
      provider_id: providerId,
      model,
      prompt: 'OK',
    }),
  })

export const exportLlmConfig = () => api<LlmConfigBundle>('/api/llm/config/export')

export const importOpenCodeConfig = (content: string) =>
  api<{ ok: boolean; providers: LlmProvider[]; detections: LlmDetectionResult['detection'][] }>('/api/llm/import/opencode', {
    method: 'POST',
    body: JSON.stringify({ content }),
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
