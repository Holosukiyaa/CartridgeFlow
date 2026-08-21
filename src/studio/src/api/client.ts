import type {
  CreatorDiscoveryResult,
  CreatorLlmProvider,
  CreatorPackage,
  CreatorProjection,
  CreatorProposal,
  CreatorProposalPreview,
  CreatorRecipePreview,
  CreatorSourceCandidate,
  CreatorStudioResources,
} from './types.ts'

export type * from './types.ts'

export class ApiError extends Error {
  status: number
  code: string

  constructor(
    message: string,
    status: number,
    code = 'CREATOR_REQUEST_FAILED',
  ) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
  }
}

async function api<T>(path: string, options: RequestInit & { timeoutMs?: number } = {}): Promise<T> {
  const { timeoutMs = 60_000, ...request } = options
  const controller = new AbortController()
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs)
  const headers = new Headers(request.headers)
  const queryToken = new URLSearchParams(window.location.search).get('access_token')
  if (queryToken) {
    window.sessionStorage.setItem('cartridgeflow.access-token', queryToken)
    const cleanUrl = new URL(window.location.href)
    cleanUrl.searchParams.delete('access_token')
    window.history.replaceState(null, '', `${cleanUrl.pathname}${cleanUrl.search}${cleanUrl.hash}`)
  }
  const accessToken = queryToken || window.sessionStorage.getItem('cartridgeflow.access-token')
  if (accessToken) headers.set('Authorization', `Bearer ${accessToken}`)
  if (request.body) headers.set('Content-Type', 'application/json')
  try {
    const response = await fetch(path, { ...request, headers, signal: controller.signal })
    const payload = await response.json().catch(() => ({}))
    if (!response.ok) {
      const detail = payload?.detail
      throw new ApiError(
        typeof detail === 'string' ? detail : detail?.message || `Request failed (${response.status})`,
        response.status,
        detail?.code || 'CREATOR_REQUEST_FAILED',
      )
    }
    return payload as T
  } catch (error) {
    if (error instanceof ApiError) throw error
    if ((error as Error)?.name === 'AbortError') throw new ApiError('Request timed out.', 408, 'CREATOR_REQUEST_TIMEOUT')
    throw new ApiError('Creator service is unavailable.', 503)
  } finally {
    window.clearTimeout(timeout)
  }
}

const sessionRoute = (sessionId: string) => `/api/creator/authoring-sessions/${encodeURIComponent(sessionId)}`

export type CreatorWorkspaceRecord<T> = {
  schema: 'cartridgeflow.creator_workspace.v1'
  project_id: string
  revision: number
  updated_at: string
  snapshot: T
}

export type DesktopRunnerStatus = {
  schema: 'cartridgeflow.desktop_runner_status.v1'
  available: boolean
  url: string
  version: string
  busy: boolean
  cartridge: { id: string; name: string; version: string } | null
  message?: string
}

export type CreatorRunnerDelivery = {
  schema: 'cartridgeflow.creator_runner_delivery.v1'
  status: 'installed' | 'trust_required'
  package: CreatorPackage
  delivery: {
    schema: 'cartridgeflow.desktop_runner_delivery.v1'
    status: 'installed' | 'trust_required'
    runner_url: string
    approval_id?: string
    publisher?: { id: string; key_id: string; fingerprint: string }
    cartridge: { id: string; name: string; version: string }
  }
}

export const fetchCreatorProject = (projectId: string) =>
  api<{ creator: CreatorProjection | null }>(`/api/creator/projects/${encodeURIComponent(projectId)}?optional=true`)

export const fetchCreatorWorkspace = <T>(projectId: string) =>
  api<{ workspace: CreatorWorkspaceRecord<T> | null }>(`/api/creator/projects/${encodeURIComponent(projectId)}/workspace`)

export const saveCreatorWorkspace = <T>(projectId: string, snapshot: T, expectedRevision: number) =>
  api<{ workspace: CreatorWorkspaceRecord<T> }>(`/api/creator/projects/${encodeURIComponent(projectId)}/workspace`, {
    method: 'PUT', body: JSON.stringify({ snapshot, expected_revision: expectedRevision }),
  })

export const listCreatorProjects = () =>
  api<{ projects: Array<{ project_id: string; session_id: string; name: string; intent: string; revision: number }> }>('/api/creator/projects')

export const renameCreatorProject = (projectId: string, name: string) =>
  api<{ creator: CreatorProjection }>(`/api/creator/projects/${encodeURIComponent(projectId)}`, { method: 'PATCH', body: JSON.stringify({ name }) })

export const deleteCreatorProject = (projectId: string) =>
  api<{ deleted: boolean }>(`/api/creator/projects/${encodeURIComponent(projectId)}`, { method: 'DELETE' })

export const fetchCreatorSession = (sessionId: string) =>
  api<{ creator: CreatorProjection }>(sessionRoute(sessionId))

export const fetchCreatorAiStatus = () =>
  api<{ provider: string; has_key: boolean; base_url: string; model: string }>('/api/settings')

export async function connectCreatorAi(body: { base_url: string; api_key: string; model: string }) {
  const detected = await api<{
    provider: { name: string; api_type: string; base_url: string; default_model: string; wire_api: string; capabilities: string[]; timeout: number }
    detection: { models: string[] }
  }>('/api/llm/detect', {
    method: 'POST',
    body: JSON.stringify({ base_url: body.base_url, api_key: body.api_key, preferred_model: body.model }),
    timeoutMs: 45_000,
  })
  const selectedModel = body.model.trim() || detected.provider.default_model
  const saved = await api<{ provider: { id: string } }>('/api/llm/providers', {
    method: 'POST',
    body: JSON.stringify({
      ...detected.provider,
      id: 'creator-ai',
      name: 'Creator AI',
      api_key: body.api_key,
      default_model: selectedModel,
      available_models: detected.detection.models,
      enabled: true,
      adapter_profile: 'standard',
    }),
  })
  await api('/api/llm/test', {
    method: 'POST',
    body: JSON.stringify({ provider_id: saved.provider.id, model: selectedModel, prompt: 'Reply with OK.', vision: false }),
    timeoutMs: 45_000,
  })
  return { ready: true as const }
}

export const detectCreatorLlm = (body: { base_url: string; api_key: string; preferred_model?: string }) =>
  api<{
    provider: { name: string; api_type: string; base_url: string; default_model: string; wire_api: string; capabilities: string[]; timeout: number }
    detection: { models: string[] }
  }>('/api/llm/detect', {
    method: 'POST',
    body: JSON.stringify({ base_url: body.base_url, api_key: body.api_key, preferred_model: body.preferred_model || '' }),
    timeoutMs: 45_000,
  })

export const listCreatorLlmProviders = () =>
  api<{ providers: CreatorLlmProvider[] }>('/api/llm/providers')

export const saveCreatorLlmProvider = (provider: Record<string, unknown>) =>
  api<{ ok: boolean; provider: CreatorLlmProvider }>(provider.id ? `/api/llm/providers/${encodeURIComponent(String(provider.id))}` : '/api/llm/providers', {
    method: provider.id ? 'PUT' : 'POST', body: JSON.stringify(provider),
  })

export const removeCreatorLlmProvider = (providerId: string) =>
  api<{ ok: boolean }>(`/api/llm/providers/${encodeURIComponent(providerId)}`, { method: 'DELETE' })

export const activateCreatorLlmProvider = (providerId: string) =>
  api<{ ok: boolean; provider: CreatorLlmProvider }>(`/api/llm/providers/${encodeURIComponent(providerId)}/activate`, { method: 'POST' })

export const testCreatorLlmProvider = (providerId: string, model: string) =>
  api<{ ok: boolean; content?: string }>('/api/llm/test', {
    method: 'POST', body: JSON.stringify({ provider_id: providerId, model, prompt: 'Reply with OK.', vision: false }), timeoutMs: 45_000,
  })

export const fetchCreatorStudioResources = () => api<CreatorStudioResources>('/api/studio/resources')

export const saveCreatorStudioResources = (resources: Omit<CreatorStudioResources, 'builtin_tools'>) =>
  api<{ ok: boolean; resources: Omit<CreatorStudioResources, 'builtin_tools'> }>('/api/studio/resources', {
    method: 'PUT', body: JSON.stringify(resources),
  })

export const discoverCreatorPossibilities = (context: string) =>
  api<CreatorDiscoveryResult>('/api/creator/possibilities', {
    method: 'POST', body: JSON.stringify({ context, output_locale: 'zh-CN' }), timeoutMs: 135_000,
  })

export const composeCreatorRecipe = (body: { session_id: string; project_id: string; goal: string }) =>
  api<{ creator: CreatorProjection }>('/api/creator/compose-recipe', {
    method: 'POST', body: JSON.stringify(body), timeoutMs: 135_000,
  })

export const recomposeCreatorRecipe = (sessionId: string, body: { goal: string; expected_revision: number }) =>
  api<{ creator: CreatorProjection }>(`${sessionRoute(sessionId)}/recompose`, {
    method: 'POST', body: JSON.stringify(body), timeoutMs: 135_000,
  })

export const previewCreatorRecompose = (sessionId: string, body: { goal: string; expected_revision: number }) =>
  api<CreatorRecipePreview>(`${sessionRoute(sessionId)}/recompose-preview`, {
    method: 'POST', body: JSON.stringify(body), timeoutMs: 135_000,
  })

export const acceptCreatorRecompose = (sessionId: string, proposalId: string, expectedRevision: number) =>
  api<{ creator: CreatorProjection }>(`${sessionRoute(sessionId)}/recompose-proposals/${encodeURIComponent(proposalId)}/accept`, {
    method: 'POST', body: JSON.stringify({ proposal_id: proposalId, expected_revision: expectedRevision }),
  })

export const discoverCreatorSources = (sessionId: string, request: string) =>
  api<{ candidates: CreatorSourceCandidate[] }>(`${sessionRoute(sessionId)}/source-candidates`, {
    method: 'POST', body: JSON.stringify({ request }), timeoutMs: 135_000,
  })

export const inspectCreatorSource = (url: string) =>
  api<{ status: string; url: string; content_type: string; bytes: number; sample: string; content_digest: string }>('/api/creator/source-inspections', {
    method: 'POST', body: JSON.stringify({ url }), timeoutMs: 30_000,
  })

export type TrialFeed = { id: string; name: string; url: string; status?: number; item_count?: number }
export type TrialItem = { title: string; link: string; published: string; summary: string; source: string; feed_url: string }
export type TrialDigest = { date: string; headline: string; body: string; used_model: boolean; model: string; item_count: number }
export type TrialFetchResult = { schema: string; fetched_at: string; feeds: TrialFeed[]; warnings: string[]; items: TrialItem[] }
export type TrialRunResult = {
  schema: string
  steps: Array<{ id: string; label: string; status: string; detail: string }>
  fetch: { fetched_at: string; feeds: TrialFeed[]; warnings: string[] }
  items: TrialItem[]
  digest: TrialDigest
  package?: {
    filename: string
    url: string
    release_id: string
    signature_verified: boolean
    unpack?: { consumer: string; activation_allowed: boolean; status: string }
  }
  runtime?: { id: string; cartridge?: { id: string; name: string; version: string } }
  run?: { run_id?: string; status?: string }
}

export const fetchTrialSources = (feedUrl?: string) =>
  api<TrialFetchResult>('/api/creator/trial-run/fetch', {
    method: 'POST', body: JSON.stringify({ feed_url: feedUrl || null }), timeoutMs: 45_000,
  })

export const composeTrialDigest = (items: TrialItem[]) =>
  api<{ digest: TrialDigest }>('/api/creator/trial-run/compose', {
    method: 'POST', body: JSON.stringify({ items }), timeoutMs: 120_000,
  })

export type StudioCartridge = {
  id: string
  name: string
  version: string
  source?: string
  inputs: Array<{ id: string; label: string; type: string; required?: boolean; default?: unknown }>
}

export type StudioRunJob = {
  schema: 'cartridgeflow.studio_run_job.v1'
  run_id: string
  cartridge_id: string
  label: string
  status: string
  current_state: string
  created_at?: string
  updated_at?: string
  active?: boolean
  project_id?: string
  cartridge_version?: string
  approved?: boolean
  inputs?: Record<string, unknown>
  delivery?: {
    result?: string
    value?: string
    summary?: string
    date?: string
    result_items?: Array<{ title?: string; url?: string; summary?: string } | string>
    source_url?: string[]
    approved?: boolean
  }
  error?: { message?: string; cause_chain?: Array<{ message?: string }> }
  progress: {
    status: string
    percent: number
    current_label: string
    steps: Array<{ id: string; label: string; status: string }>
  }
}

export type StudioRuntimeStatus = {
  schema: 'cartridgeflow.studio_run_desk.v1'
  available: boolean
  runtime: 'studio'
  cartridges: StudioCartridge[]
  jobs: StudioRunJob[]
}

export const fetchStudioRuntime = (query: { project_id?: string; cartridge_id?: string } = {}) => {
  const params = new URLSearchParams()
  if (query.project_id) params.set('project_id', query.project_id)
  if (query.cartridge_id) params.set('cartridge_id', query.cartridge_id)
  const suffix = params.toString() ? `?${params}` : ''
  return api<StudioRuntimeStatus>(`/api/studio/runtime${suffix}`, { timeoutMs: 8_000 })
}

export const installStudioPackage = (filename: string) =>
  api<{ filename: string; url: string; signature_verified: boolean; cartridge: StudioCartridge }>(
    '/api/studio/runtime/install-package',
    { method: 'POST', body: JSON.stringify({ filename }), timeoutMs: 60_000 },
  )

export const enqueueStudioJob = (body: { cartridge_id: string; inputs: Record<string, unknown>; label?: string; project_id?: string }) =>
  api<StudioRunJob>('/api/studio/runtime/jobs', {
    method: 'POST', body: JSON.stringify(body), timeoutMs: 30_000,
  })

export const approveStudioJob = (runId: string, approved = true) =>
  api<StudioRunJob>(`/api/studio/runtime/jobs/${encodeURIComponent(runId)}/approve`, {
    method: 'POST', body: JSON.stringify({ approved }), timeoutMs: 8_000,
  })

export const fetchStudioJob = (runId: string) =>
  api<StudioRunJob>(`/api/studio/runtime/jobs/${encodeURIComponent(runId)}`, { timeoutMs: 8_000 })

export const installDailyBrief = () =>
  api<{ filename: string; url: string; signature_verified: boolean; cartridge: { id: string; name: string; version: string } }>(
    '/api/studio/runtime/install-daily-brief',
    { method: 'POST', body: JSON.stringify({}), timeoutMs: 60_000 },
  )

export const runStudioCartridge = (cartridgeId: string, inputs: Record<string, unknown>) =>
  api<{ run_id: string; status: string; delivery?: { result?: string; value?: string; summary?: string } }>(
    '/api/studio/runtime/run',
    { method: 'POST', body: JSON.stringify({ cartridge_id: cartridgeId, inputs }), timeoutMs: 180_000 },
  )

export const runDailyBriefRelease = (feedUrl?: string) =>
  api<TrialRunResult>('/api/studio/runtime/run-daily-brief', {
    method: 'POST', body: JSON.stringify({ feed_url: feedUrl || null }), timeoutMs: 180_000,
  })

export const proposeCreatorNodeValues = (sessionId: string, body: unknown) =>
  api<{ proposal: CreatorProposal }>(`${sessionRoute(sessionId)}/proposals`, {
    method: 'POST', body: JSON.stringify(body),
  })

export const refineCreatorNodeWithAi = (sessionId: string, nodeId: string, body: unknown) =>
  api<{ proposal: CreatorProposal }>(`${sessionRoute(sessionId)}/nodes/${encodeURIComponent(nodeId)}/ai-proposals`, {
    method: 'POST', body: JSON.stringify(body), timeoutMs: 135_000,
  })

export const previewCreatorProposal = (sessionId: string, proposalId: string, freezeRevision?: unknown) =>
  api<CreatorProposalPreview>(`${sessionRoute(sessionId)}/proposals/${encodeURIComponent(proposalId)}/preview`, {
    method: 'POST', body: JSON.stringify(freezeRevision ? { freeze_revision: freezeRevision } : {}),
  })

export const acceptCreatorProposal = (sessionId: string, proposalId: string, freezeRevision?: unknown) =>
  api<{ creator: CreatorProjection; accepted_change_ids: string[] }>(`${sessionRoute(sessionId)}/proposals/${encodeURIComponent(proposalId)}/accept`, {
    method: 'POST', body: JSON.stringify(freezeRevision ? { freeze_revision: freezeRevision } : {}),
  })

export const rejectCreatorProposal = (sessionId: string, proposalId: string) =>
  api<{ creator: CreatorProjection }>(`${sessionRoute(sessionId)}/proposals/${encodeURIComponent(proposalId)}/reject`, {
    method: 'POST', body: JSON.stringify({ reason: 'Creator declined this suggestion.' }),
  })

export const confirmCreatorNode = (sessionId: string, nodeId: string) =>
  api(`${sessionRoute(sessionId)}/freeze`, {
    method: 'POST',
    body: JSON.stringify({ step_ids: [nodeId], author: 'creator', summary: 'Creator reviewed this node.' }),
  })

export const resolveCreatorCapabilities = (sessionId: string, expectedRevision: number) =>
  api<{ creator: CreatorProjection; resolved_node_ids: string[] }>(`${sessionRoute(sessionId)}/resolve-capabilities`, {
    method: 'POST', body: JSON.stringify({ expected_revision: expectedRevision }),
  })

export const rejectCreatorCapability = (sessionId: string, nodeId: string, expectedRevision: number) =>
  api<{ creator: CreatorProjection }>(`${sessionRoute(sessionId)}/nodes/${encodeURIComponent(nodeId)}/reject-capability`, {
    method: 'POST', body: JSON.stringify({ expected_revision: expectedRevision }),
  })

export const saveStudioLayer2 = (sessionId: string, nodeId: string, expectedRevision: number, layer: Record<string, unknown>) =>
  api<{ creator: CreatorProjection }>(`${sessionRoute(sessionId)}/nodes/${encodeURIComponent(nodeId)}/studio-layer2`, {
    method: 'PUT', body: JSON.stringify({ expected_revision: expectedRevision, layer }),
  })

export const proveStudioLayer2 = (sessionId: string, nodeId: string, expectedRevision: number, mode: string, inputs: Record<string, unknown>) =>
  api<{ creator: CreatorProjection; proof: Record<string, unknown> }>(
    `${sessionRoute(sessionId)}/nodes/${encodeURIComponent(nodeId)}/studio-layer2/prove`,
    { method: 'POST', body: JSON.stringify({ expected_revision: expectedRevision, mode, inputs }), timeoutMs: 60_000 },
  )

export const publishStudioLayer2 = (sessionId: string, nodeId: string, expectedRevision: number) =>
  api<{ creator: CreatorProjection }>(`${sessionRoute(sessionId)}/nodes/${encodeURIComponent(nodeId)}/studio-layer2/publish`, {
    method: 'POST', body: JSON.stringify({ expected_revision: expectedRevision, layer: {} }),
  })

export const setCreatorExperience = (
  sessionId: string,
  nodeId: string,
  body: {
    expected_revision: number
    expected_experience_revision: number
    slot_id: string
    component_id: string
    field_sources: Record<string, string>
  },
) => api<{ creator: CreatorProjection }>(`${sessionRoute(sessionId)}/nodes/${encodeURIComponent(nodeId)}/experience`, {
  method: 'PUT', body: JSON.stringify(body),
})

export const packageCreatorProject = (sessionId: string, expectedRevision: number) =>
  api<CreatorPackage>(`${sessionRoute(sessionId)}/package`, {
    method: 'POST', body: JSON.stringify({ expected_revision: expectedRevision }), timeoutMs: 90_000,
  })

export const fetchDesktopRunnerStatus = () =>
  api<DesktopRunnerStatus>('/api/creator/desktop-runner', { timeoutMs: 5_000 })

export const deliverCreatorProject = (sessionId: string, expectedRevision: number) =>
  api<CreatorRunnerDelivery>(`${sessionRoute(sessionId)}/desktop-runner`, {
    method: 'POST', body: JSON.stringify({ expected_revision: expectedRevision }), timeoutMs: 30_000,
  })
