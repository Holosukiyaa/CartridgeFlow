import type {
  CreatorCapabilityGap,
  CreatorPackage,
  CreatorPossibility,
  CreatorProjection,
  CreatorProposal,
  CreatorProposalPreview,
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

export const fetchCreatorSession = (sessionId: string) =>
  api<{ creator: CreatorProjection }>(sessionRoute(sessionId))

export const fetchCreatorAiStatus = () =>
  api<{ has_key: boolean; base_url: string; model: string }>('/api/settings')

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
  return api<{ ready: true; capability: { id: string; label: string } }>('/api/creator/starter-capabilities', {
    method: 'POST',
    timeoutMs: 45_000,
  })
}

export const ensureCreatorStarterCapabilities = () =>
  api<{ ready: true }>('/api/creator/starter-capabilities', { method: 'POST', timeoutMs: 45_000 })

export const discoverCreatorPossibilities = (context: string) =>
  api<{ possibilities: CreatorPossibility[] }>('/api/creator/possibilities', {
    method: 'POST', body: JSON.stringify({ context }), timeoutMs: 45_000,
  })

export const composeCreatorRecipe = (body: { session_id: string; project_id: string; goal: string }) =>
  api<{ creator?: CreatorProjection; capability_gap?: CreatorCapabilityGap }>('/api/creator/compose-recipe', {
    method: 'POST', body: JSON.stringify(body), timeoutMs: 45_000,
  })

export const recomposeCreatorRecipe = (sessionId: string, body: { goal: string; expected_revision: number }) =>
  api<{ creator?: CreatorProjection; capability_gap?: CreatorCapabilityGap }>(`${sessionRoute(sessionId)}/recompose`, {
    method: 'POST', body: JSON.stringify(body), timeoutMs: 45_000,
  })

export const proposeCreatorNodeValues = (sessionId: string, body: unknown) =>
  api<{ proposal: CreatorProposal }>(`${sessionRoute(sessionId)}/proposals`, {
    method: 'POST', body: JSON.stringify(body),
  })

export const refineCreatorNodeWithAi = (sessionId: string, nodeId: string, body: unknown) =>
  api<{ proposal: CreatorProposal }>(`${sessionRoute(sessionId)}/nodes/${encodeURIComponent(nodeId)}/ai-proposals`, {
    method: 'POST', body: JSON.stringify(body), timeoutMs: 45_000,
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

export const packageCreatorProject = (sessionId: string, expectedRevision: number) =>
  api<CreatorPackage>(`${sessionRoute(sessionId)}/package`, {
    method: 'POST', body: JSON.stringify({ expected_revision: expectedRevision }), timeoutMs: 90_000,
  })
