export type Creator = {
  session_id: string; revision: number; intent: string
  semantic_steps: { id: string; intent: string; plain_inputs: string[]; plain_outputs: string[] }[]
  steps: { id: string; intent: string }[]
  relationships: { id: string; from_step_id: string; to_step_id: string; relation: string }[]
  sources: Source[]; pending_proposals: Proposal[]; active_freezes: { id: string; steps: string[]; freeze_revision: { source_freeze_ids: string[]; expected_revision: number } }[]
  frozen_steps: string[]; history: { id: string; revision: number; summary: string }[]
  blocked_findings: Finding[]; design_checks: { findings: Finding[] }; generation_readiness: Readiness
}
export type Source = { id: string; kind: 'source'; digest: string; role?: string; remote_url?: string; rss_url?: string }
export type Proposal = { proposal_id: string; revision: number; summary: string; changes: { id: string; target_id: string; operation: string }[] }
export type Finding = { code: string; severity: string; message: string; step_id?: string }
export type Readiness = { ready: boolean; blocked_findings: Finding[]; compile_candidate: unknown }
export class ApiError extends Error { constructor(public code: string, message: string, public status: number) { super(message) } }

const base = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')
async function request<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
  const response = await fetch(`${base}${path}`, { method, headers: body ? { 'Content-Type': 'application/json' } : undefined, body: body ? JSON.stringify(body) : undefined })
  const data = await response.json().catch(() => ({}))
  if (!response.ok) { const detail = data.detail || {}; throw new ApiError(detail.code || data.error_envelope?.code || 'CREATOR_API_ERROR', detail.message || (typeof detail === 'string' ? detail : 'Creator request failed.'), response.status) }
  return data as T
}
const route = (id: string) => `/api/creator/authoring-sessions/${encodeURIComponent(id)}`
export const creatorApi = {
  create: (body: { session_id: string; recipe_id: string; intent: string; steps: unknown[]; source_references: unknown[]; bindings: Record<string, unknown> }) => request<{ creator: Creator }>('/api/creator/authoring-sessions', 'POST', body),
  get: (id: string) => request<{ creator: Creator }>(route(id)),
  ai: (id: string, body: unknown) => request<{ proposal: Proposal }>(`${route(id)}/ai-proposals`, 'POST', body),
  propose: (id: string, body: unknown) => request<{ proposal: Proposal }>(`${route(id)}/proposals`, 'POST', body),
  preview: (id: string, proposal: string, body: unknown) => request<{ accepted_change_ids: string[] }>(`${route(id)}/proposals/${proposal}/preview`, 'POST', body),
  accept: (id: string, proposal: string, body: unknown) => request<{ creator: Creator; accepted_change_ids: string[] }>(`${route(id)}/proposals/${proposal}/accept`, 'POST', body),
  reject: (id: string, proposal: string, body: unknown) => request<{ creator: Creator }>(`${route(id)}/proposals/${proposal}/reject`, 'POST', body),
  reverse: (id: string, acceptance: string, body: unknown) => request<{ creator: Creator }>(`${route(id)}/revisions/${acceptance}/reverse`, 'POST', body),
  freeze: (id: string, body: unknown) => request(`${route(id)}/freeze`, 'POST', body),
  checks: (id: string) => request<{ design_checks: { findings: Finding[] } }>(`${route(id)}/design-checks`),
  readiness: (id: string, expected_revision: number) => request<{ generation_readiness: Readiness }>(`${route(id)}/generation-readiness`, 'POST', { expected_revision }),
  compile: (id: string, expected_revision: number) => request<{ compile_candidate: unknown }>(`${route(id)}/compile-candidate`, 'POST', { expected_revision }),
}
