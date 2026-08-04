// API 工具：封装所有对后端的 fetch 调用，统一走 /api 前缀

// 基础请求方法：所有 API 调用共用
import type { RuntimeErrorEnvelope, CartridgeDetail, RunResult, FlowGraph, FlowEdge, FlowAnnotation, FlowLabItem, FlowLabDetail, FlowEvent, TestProbeRange, FlowFiles, CartridgeAsset, InteractionComponent, CartridgeAssetsResponse, McpSourceResponse, McpSourceEditResponse, BaseImplementationResponse, StudioConformanceResponse, McpToolsResponse, ValidationResponse, NodeUpdateResult, NodeCreatePayload, LlmProvider, LlmAssignments, LlmConfigBundle, LlmDetectionResult, LlmTestResult, StudioResources, FlowResourceCatalog, FlowResourceDetail, FlowResourceConnectivityResult, StudioCredential, StudioEnvironmentSnapshot, StudioPackageItem, PortabilityReport, StudioReleasePreflight, AIFlowStewardContext, AIFlowStewardMessage, AIFlowStewardMode, AuthoringReadiness, TuningResponse, TuningRevisionResult, RecipeReleaseResult, CreatorCapabilityGap, CreatorProjection, CreatorProposal, CreatorProposalPreview, DeveloperTrustedNodePublication } from './api.types.ts'
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

type ApiRequestInit = RequestInit & { timeoutMs?: number }

export async function api<T = unknown>(path: string, options: ApiRequestInit = {}): Promise<T> {
  const { timeoutMs = 60_000, signal: externalSignal, ...requestOptions } = options
  const controller = new AbortController()
  let timedOut = false
  const abortFromCaller = () => controller.abort(externalSignal?.reason)
  if (externalSignal?.aborted) abortFromCaller()
  else externalSignal?.addEventListener('abort', abortFromCaller, { once: true })
  const timeout = timeoutMs > 0 ? window.setTimeout(() => {
    timedOut = true
    controller.abort()
  }, timeoutMs) : null
  const headers = new Headers(requestOptions.headers)
  if (!headers.has('Content-Type')) headers.set('Content-Type', 'application/json')

  try {
    const res = await fetch(path, { ...requestOptions, headers, signal: controller.signal })
    if (!res.ok) {
      const raw = await res.text()
      let payload: any = null
      try { payload = JSON.parse(raw) } catch { /* retain plain-text server errors */ }
      const envelope = payload?.error_envelope as RuntimeErrorEnvelope | undefined
      const detail = payload?.detail
      const detailMessage = typeof detail === 'string' ? detail : detail?.message
      const message = detailMessage
        || envelope?.message
        || raw
        || `Request failed (${res.status})`
      throw new ApiError(message, res.status, envelope, detail)
    }
    return res.json() as Promise<T>
  } catch (error) {
    if (error instanceof ApiError) throw error
    if ((error as Error)?.name === 'AbortError') {
      throw new ApiError(timedOut ? `Request timed out after ${timeoutMs} ms` : 'Request was cancelled', timedOut ? 408 : 499)
    }
    throw error
  } finally {
    if (timeout !== null) window.clearTimeout(timeout)
    externalSignal?.removeEventListener('abort', abortFromCaller)
  }
}

// ── 卡带相关类型 ──────────────────────────────────────────────
export const fetchBaseImplementation = () => api<BaseImplementationResponse>('/api/base')

export const fetchStudioConformance = () => api<StudioConformanceResponse>('/api/studio/conformance')

const creatorSessionRoute = (sessionId: string) => `/api/creator/authoring-sessions/${encodeURIComponent(sessionId)}`

export const fetchCreatorProject = (projectId: string) =>
  api<{ creator: CreatorProjection | null }>(`/api/creator/projects/${encodeURIComponent(projectId)}?optional=true`)

export const fetchCreatorSession = (sessionId: string) =>
  api<{ creator: CreatorProjection }>(creatorSessionRoute(sessionId))

export const composeCreatorRecipe = (body: { session_id: string; project_id: string; goal: string }) =>
  api<{ creator?: CreatorProjection; capability_gap?: CreatorCapabilityGap }>('/api/creator/compose-recipe', {
    method: 'POST', body: JSON.stringify(body), timeoutMs: 45_000,
  })

export const fetchDeveloperTrustedNodePublications = () =>
  api<{ publications: DeveloperTrustedNodePublication[] }>('/api/developer/trusted-node-presets')

export const publishDeveloperFlowNode = (flowId: string, nodeId: string, body: unknown) =>
  api<{ publication: DeveloperTrustedNodePublication }>(`/api/developer/flows/${encodeURIComponent(flowId)}/nodes/${encodeURIComponent(nodeId)}/trusted-node-preset`, {
    method: 'POST', body: JSON.stringify(body),
  })

export const proposeCreatorNodeValues = (sessionId: string, body: unknown) =>
  api<{ proposal: CreatorProposal }>(`${creatorSessionRoute(sessionId)}/proposals`, { method: 'POST', body: JSON.stringify(body) })

export const refineCreatorNodeWithAi = (sessionId: string, nodeId: string, body: unknown) =>
  api<{ proposal: CreatorProposal }>(`${creatorSessionRoute(sessionId)}/nodes/${encodeURIComponent(nodeId)}/ai-proposals`, {
    method: 'POST', body: JSON.stringify(body), timeoutMs: 45_000,
  })

export const previewCreatorProposal = (sessionId: string, proposalId: string) =>
  api<CreatorProposalPreview>(`${creatorSessionRoute(sessionId)}/proposals/${encodeURIComponent(proposalId)}/preview`, { method: 'POST', body: '{}' })

export const acceptCreatorProposal = (sessionId: string, proposalId: string) =>
  api<{ creator: CreatorProjection; accepted_change_ids: string[] }>(`${creatorSessionRoute(sessionId)}/proposals/${encodeURIComponent(proposalId)}/accept`, { method: 'POST', body: '{}' })

export const rejectCreatorProposal = (sessionId: string, proposalId: string) =>
  api<{ creator: CreatorProjection }>(`${creatorSessionRoute(sessionId)}/proposals/${encodeURIComponent(proposalId)}/reject`, {
    method: 'POST', body: JSON.stringify({ reason: 'Creator rejected the suggestion.' }),
  })

export const freezeCreatorNode = (sessionId: string, nodeId: string) =>
  api(`${creatorSessionRoute(sessionId)}/freeze`, {
    method: 'POST', body: JSON.stringify({ step_ids: [nodeId], author: 'creator-workbench', summary: 'Creator confirmed this trusted node instance.' }),
  })

export const fetchCartridgeRun = (runId: string) =>
  api<RunResult>(`/api/cartridge-runs/${runId}`)

export const fetchCartridgeRunEvents = (runId: string) =>
  api<{ items: FlowEvent[] }>(`/api/cartridge-runs/${runId}/events`)

export const openCartridgeRunArtifactsDirectory = (runId: string) =>
  api<{ ok: boolean; run_id: string; path: string }>(`/api/cartridge-runs/${encodeURIComponent(runId)}/artifacts/open-directory`, {
    method: 'POST',
  })

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
  api<{ ok: boolean; cartridge_id: string; filename: string; package_mode: string; protocol?: string; release_id?: string; activation_allowed?: boolean; url: string; size: number; mcp_tool_count: number; compatibility?: any; portability?: PortabilityReport }>(`/api/cartridges/${encodeURIComponent(id)}/package`, {
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

export const analyzeLabFlow = <T = unknown>(id: string, files: FlowFiles, target = 'dev') =>
  api<T>(`/api/lab/flows/${encodeURIComponent(id)}/analyze`, {
    method: 'POST',
    body: JSON.stringify({ files, target }),
  })

export const askAIFlowSteward = (
  id: string,
  message: string,
  mode: AIFlowStewardMode,
  context: AIFlowStewardContext,
) => api<{ ok: boolean; message: AIFlowStewardMessage; meta?: Record<string, any> }>(`/api/lab/flows/${id}/ai-steward`, {
  method: 'POST',
  body: JSON.stringify({ message, mode, ...context }),
})

export const fetchCartridgeAssets = (id: string) =>
  api<CartridgeAssetsResponse>(`/api/lab/flows/${id}/assets`)

export const saveCartridgeAsset = (id: string, assetId: string, asset: Omit<CartridgeAsset, 'sha256' | 'size' | 'executable'> & { encoding?: string }) =>
  api<{ status: string; asset: CartridgeAsset; files: FlowFiles }>(`/api/lab/flows/${id}/assets/${assetId}`, {
    method: 'PUT',
    body: JSON.stringify(asset),
  })

export const saveInteractionComponent = (id: string, componentId: string, component: InteractionComponent) =>
  api<{ status: string; component: InteractionComponent; files: FlowFiles }>(`/api/lab/flows/${id}/interaction-components/${componentId}`, {
    method: 'PUT',
    body: JSON.stringify({ component }),
  })

export const fetchMcpTools = (id: string) =>
  api<McpToolsResponse>(`/api/lab/flows/${id}/mcp-tools`)

export const fetchFlowResourceCatalog = (id: string) =>
  api<FlowResourceCatalog>(`/api/lab/flows/${id}/resource-catalog`)

export const fetchFlowResourceDetail = (id: string, resourceId: string) =>
  api<FlowResourceDetail>(`/api/lab/flows/${id}/resource-details/${encodeURIComponent(resourceId)}`)

export const checkFlowResourceConnectivity = (id: string, resourceId: string) =>
  api<FlowResourceConnectivityResult>(`/api/lab/flows/${id}/resource-connectivity/${encodeURIComponent(resourceId)}`, { method: 'POST' })

export const fetchMcpSource = (id: string, nodeId: string) =>
  api<McpSourceResponse>(`/api/lab/flows/${id}/mcp-nodes/${encodeURIComponent(nodeId)}/source`)

export const replaceMcpSource = (id: string, nodeId: string, expectedSourceDigest: string, source: string) =>
  api<McpSourceEditResponse>(`/api/lab/flows/${id}/mcp-nodes/${encodeURIComponent(nodeId)}/source`, {
    method: 'PUT',
    body: JSON.stringify({ expected_source_digest: expectedSourceDigest, source }),
  })

export const patchMcpOperationGraph = (id: string, nodeId: string, expectedSourceDigest: string, graph: Record<string, any>) =>
  api<McpSourceEditResponse>(`/api/lab/flows/${id}/mcp-nodes/${encodeURIComponent(nodeId)}/operation-graph`, {
    method: 'PATCH',
    body: JSON.stringify({ expected_source_digest: expectedSourceDigest, graph }),
  })

export const addMcpOperation = (id: string, nodeId: string, expectedSourceDigest: string, operation: Record<string, any>) =>
  api<McpSourceEditResponse>(`/api/lab/flows/${id}/mcp-nodes/${encodeURIComponent(nodeId)}/operations`, {
    method: 'POST',
    body: JSON.stringify({ expected_source_digest: expectedSourceDigest, operation }),
  })

export const saveLabFlowFile = (id: string, fileType: string, content: string) =>
  api<{ file_type: string; saved: boolean }>(`/api/lab/flows/${id}/files/${fileType}`, {
    method: 'PUT',
    body: JSON.stringify({ content }),
  })

export const updateFlowNode = (id: string, nodeId: string, payload: any) =>
  api<NodeUpdateResult>(`/api/lab/flows/${id}/nodes/${nodeId}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  })

export const fetchFlowTuning = (id: string) =>
  api<TuningResponse>(`/api/lab/flows/${id}/tuning`)

export const createNodeTuningRevision = (id: string, nodeId: string, payload: {
  patch: Record<string, any>
  expected_head?: string | null
  author?: string
  message?: string
}) => api<TuningRevisionResult>(`/api/lab/flows/${id}/tuning/nodes/${nodeId}/revisions`, {
  method: 'POST',
  body: JSON.stringify(payload),
})

export const publishRecipeRelease = (id: string, payload: { author?: string; message?: string } = {}) =>
  api<RecipeReleaseResult>(`/api/lab/flows/${id}/tuning/releases`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })

export const activateRecipeRelease = (id: string, releaseId: string) =>
  api<RecipeReleaseResult>(`/api/lab/flows/${id}/tuning/releases/${encodeURIComponent(releaseId)}/activate`, {
    method: 'POST',
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

export const fetchFlowReadiness = (id: string, files: FlowFiles = {}) =>
  api<AuthoringReadiness>(`/api/lab/flows/${id}/readiness`, {
    method: 'POST',
    body: JSON.stringify({ files }),
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

export const fetchStudioPackages = () => api<{ items: StudioPackageItem[] }>('/api/studio/packages')

export const fetchStudioReleasePreflight = (cartridgeId: string) =>
  api<StudioReleasePreflight>(`/api/studio/release/${encodeURIComponent(cartridgeId)}/preflight`)
