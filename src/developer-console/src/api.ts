import { redact, type AnyRecord } from './model'

const base = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '')
export class ApiError extends Error { constructor(public status: number, message: string) { super(message) } }

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${base}${path}`, { ...init, headers: { Accept: 'application/json', ...init?.headers } })
  if (!response.ok) {
    const body = await response.text()
    let message: unknown = body
    try { message = JSON.stringify(redact(JSON.parse(body))) } catch { message = redact(body) }
    throw new ApiError(response.status, String(message || `HTTP ${response.status}`))
  }
  return redact(await response.json()) as T
}

export const developerApi = {
  project: (id: string) => request<AnyRecord>(`/api/developer/projects/${encodeURIComponent(id)}`),
  trustedPresets: () => request<{ presets: AnyRecord[] }>('/api/developer/trusted-node-presets'),
  putTrustedPreset: (id: string, preset: AnyRecord, expectedRevision: number) => request<AnyRecord>(`/api/developer/trusted-node-presets/${encodeURIComponent(id)}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ preset, expected_revision: expectedRevision }) }),
  confirmProject: (projectId: string, revision: number) => request<AnyRecord>(`/api/developer/projects/${encodeURIComponent(projectId)}/confirm-materialization`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ expected_revision: revision, author: 'developer-console', summary: 'Confirmed trusted preset revisions and Developer mappings.' }) }),
  handoffProject: (projectId: string, revision: number, compileCandidate: unknown) => request<AnyRecord>(`/api/developer/projects/${encodeURIComponent(projectId)}/runtime-handoff`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ expected_revision: revision, compile_candidate: compileCandidate }) }),
  flows: () => request<{ items: AnyRecord[] }>('/api/lab/flows'),
  flow: (id: string) => request<AnyRecord>(`/api/lab/flows/${encodeURIComponent(id)}`),
  files: (id: string) => request<AnyRecord>(`/api/lab/flows/${encodeURIComponent(id)}/files`),
  tuning: (id: string) => request<AnyRecord>(`/api/lab/flows/${encodeURIComponent(id)}/tuning`),
  resources: (id: string) => request<AnyRecord>(`/api/lab/flows/${encodeURIComponent(id)}/resource-catalog`),
  preflight: (id: string) => request<AnyRecord>(`/api/studio/release/${encodeURIComponent(id)}/preflight`),
  conformance: () => request<AnyRecord>('/api/studio/conformance'),
  analyze: (id: string, files: AnyRecord) => request<AnyRecord>(`/api/lab/flows/${encodeURIComponent(id)}/analyze`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ files, target: 'dev' }) }),
  validate: (id: string, files: AnyRecord) => request<AnyRecord>(`/api/lab/flows/${encodeURIComponent(id)}/validate`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ files }) }),
  createRevision: (id: string, nodeId: string, body: { patch: AnyRecord; expected_head?: string; author?: string; message?: string }) => request<AnyRecord>(`/api/lab/flows/${encodeURIComponent(id)}/tuning/nodes/${encodeURIComponent(nodeId)}/revisions`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }),
  publishRelease: (id: string, body: { author?: string; message?: string }) => request<AnyRecord>(`/api/lab/flows/${encodeURIComponent(id)}/tuning/releases`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }),
  activateRelease: (id: string, releaseId: string) => request<AnyRecord>(`/api/lab/flows/${encodeURIComponent(id)}/tuning/releases/${encodeURIComponent(releaseId)}/activate`, { method: 'POST' }),
}
