import type {
  CreatorDiscoveryResult,
  CreatorPackage,
  CreatorProjection,
  CreatorProposal,
  CreatorProposalPreview,
  CreatorRecipePreview,
  CreatorSourceCandidate,
} from './api.types.ts'

export type * from './api.types.ts'

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

export const fetchCreatorProject = (projectId: string) =>
  api<{ creator: CreatorProjection | null }>(`/api/creator/projects/${encodeURIComponent(projectId)}?optional=true`)

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
