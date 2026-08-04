export type FieldContract = { id: string; label: string; value_type: 'string' | 'string_list' | 'boolean' | 'number'; required: boolean; default: unknown }
export type TrustedRecipeNode = { id: string; label: string; preset: { id: string; revision: number; digest: string }; values: Record<string, unknown>; editable_fields: FieldContract[] }
export type TrustedRecipe = { id: string; goal: string; nodes: TrustedRecipeNode[]; relations: { id: string; from_node_id: string; to_node_id: string; relation: string }[] }
export type Finding = { code: string; severity: string; message: string; step_id?: string }
export type Proposal = { proposal_id: string; revision: number; summary: string; changes: { id: string; target_id: string; operation: string }[] }
export type JourneyGraph = { project_id: string; revision: number; nodes: { id: string; kind: string; label: string; level: number; status: string }[]; edges: { id: string; from: string; to: string; relation: string }[] }
export type Creator = {
  project_id: string; session_id: string; revision: number; intent: string
  trusted_recipe: TrustedRecipe
  frozen_steps: string[]; pending_proposals: Proposal[]; history: { id: string; revision: number; summary: string }[]
  blocked_findings: Finding[]; generation_readiness: { ready: boolean; blocked_findings: Finding[] }
  journey_graph: JourneyGraph
}
export type CapabilityGap = { schema: string; goal: string; needed_capabilities: string[]; available_preset_ids: string[] }
export type Impact = { plain_summary?: string; changed_steps?: string[]; changed_sources?: string[] }
export type Preview = { accepted_change_ids: string[]; impact: Impact }
export class ApiError extends Error { constructor(public code: string, message: string, public status: number) { super(message) } }

const base = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')
async function request<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
  const response = await fetch(`${base}${path}`, { method, headers: body ? { 'Content-Type': 'application/json' } : undefined, body: body ? JSON.stringify(body) : undefined })
  const data = await response.json().catch(() => ({}))
  if (!response.ok) { const detail = data.detail || {}; throw new ApiError(detail.code || 'CREATOR_API_ERROR', detail.message || (typeof detail === 'string' ? detail : 'Creator request failed.'), response.status) }
  return data as T
}
const route = (id: string) => `/api/creator/authoring-sessions/${encodeURIComponent(id)}`
export const creatorApi = {
  compose: (body: { session_id: string; project_id: string; goal: string }) => request<{ creator?: Creator; capability_gap?: CapabilityGap }>('/api/creator/compose-recipe', 'POST', body),
  get: (id: string) => request<{ creator: Creator }>(route(id)),
  getProject: (id: string) => request<{ creator: Creator }>(`/api/creator/projects/${encodeURIComponent(id)}`),
  nodeAi: (sessionId: string, nodeId: string, body: unknown) => request<{ proposal: Proposal }>(`${route(sessionId)}/nodes/${encodeURIComponent(nodeId)}/ai-proposals`, 'POST', body),
  propose: (id: string, body: unknown) => request<{ proposal: Proposal }>(`${route(id)}/proposals`, 'POST', body),
  preview: (id: string, proposal: string, body: unknown) => request<Preview>(`${route(id)}/proposals/${proposal}/preview`, 'POST', body),
  accept: (id: string, proposal: string, body: unknown) => request<{ creator: Creator; accepted_change_ids: string[] }>(`${route(id)}/proposals/${proposal}/accept`, 'POST', body),
  reject: (id: string, proposal: string, body: unknown) => request<{ creator: Creator }>(`${route(id)}/proposals/${proposal}/reject`, 'POST', body),
  freeze: (id: string, body: unknown) => request(`${route(id)}/freeze`, 'POST', body),
  reverse: (id: string, acceptance: string, body: unknown) => request<{ creator: Creator }>(`${route(id)}/revisions/${acceptance}/reverse`, 'POST', body),
}
