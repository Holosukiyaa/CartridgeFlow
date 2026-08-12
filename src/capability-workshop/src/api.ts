import { redact, type AnyRecord } from './model'

const base = (import.meta.env?.VITE_API_BASE_URL ?? '').replace(/\/$/, '')
export const publicApiUrl = (path: string) => `${base}${path}`
export class ApiError extends Error { constructor(public status: number, message: string) { super(message) } }

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const queryToken = new URLSearchParams(window.location.search).get('access_token')
  if (queryToken) {
    window.sessionStorage.setItem('cartridgeflow.access-token', queryToken)
    const cleanUrl = new URL(window.location.href)
    cleanUrl.searchParams.delete('access_token')
    window.history.replaceState(null, '', `${cleanUrl.pathname}${cleanUrl.search}${cleanUrl.hash}`)
  }
  const accessToken = queryToken || window.sessionStorage.getItem('cartridgeflow.access-token')
  const response = await fetch(`${base}${path}`, { ...init, headers: { Accept: 'application/json', ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}), ...init?.headers } })
  if (!response.ok) {
    const body = await response.text()
    let message: unknown = body
    try {
      const parsed = redact(JSON.parse(body)) as AnyRecord
      const detail = parsed.detail
      message = typeof detail === 'string'
        ? detail
        : detail && typeof detail === 'object'
          ? String((detail as AnyRecord).message || (detail as AnyRecord).error || JSON.stringify(detail))
          : JSON.stringify(parsed)
    } catch { message = redact(body) }
    throw new ApiError(response.status, String(message || `HTTP ${response.status}`))
  }
  // Redaction belongs at display/log boundaries. Mutating a successful payload here
  // destroys contract values such as runtime verification tokens.
  return await response.json() as T
}

export const capabilityApi = {
  project: (id: string) => request<AnyRecord>(`/api/developer/projects/${encodeURIComponent(id)}`),
  trustedPresets: () => request<{ presets: AnyRecord[] }>('/api/developer/trusted-node-presets'),
  putTrustedPreset: (id: string, preset: AnyRecord, expectedRevision: number) => request<AnyRecord>(`/api/developer/trusted-node-presets/${encodeURIComponent(id)}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ preset, expected_revision: expectedRevision }) }),
  confirmProject: (projectId: string, revision: number) => request<AnyRecord>(`/api/developer/projects/${encodeURIComponent(projectId)}/confirm-materialization`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ expected_revision: revision, author: 'capability-workshop', summary: 'Confirmed trusted preset revisions and capability mappings.' }) }),
  handoffProject: (projectId: string, revision: number, compileCandidate: unknown) => request<AnyRecord>(`/api/developer/projects/${encodeURIComponent(projectId)}/runtime-handoff`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ expected_revision: revision, compile_candidate: compileCandidate }) }),
  flows: () => request<{ items: AnyRecord[] }>('/api/lab/flows'),
  createFlow: (body: { flow_id: string; name: string; description: string }) => request<AnyRecord>('/api/lab/flows', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }),
  flow: (id: string) => request<AnyRecord>(`/api/lab/flows/${encodeURIComponent(id)}`),
  files: (id: string) => request<AnyRecord>(`/api/lab/flows/${encodeURIComponent(id)}/files`),
  assets: (id: string) => request<AnyRecord>(`/api/lab/flows/${encodeURIComponent(id)}/assets`),
  saveDisplayComponent: (id: string, componentId: string, body: AnyRecord) => request<AnyRecord>(`/api/lab/flows/${encodeURIComponent(id)}/display-components/${encodeURIComponent(componentId)}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }),
  resources: (id: string) => request<AnyRecord>(`/api/lab/flows/${encodeURIComponent(id)}/resource-catalog`),
  resourceConnectivity: (id: string, resourceId: string) => request<AnyRecord>(`/api/lab/flows/${encodeURIComponent(id)}/resource-connectivity/${encodeURIComponent(resourceId)}`, { method: 'POST' }),
  mcpTools: (id: string) => request<AnyRecord>(`/api/lab/flows/${encodeURIComponent(id)}/mcp-tools`),
  studioResources: () => request<AnyRecord>('/api/studio/resources'),
  saveStudioResources: (body: AnyRecord) => request<AnyRecord>('/api/studio/resources', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }),
  createMcpTool: (id: string, body: AnyRecord) => request<AnyRecord>(`/api/lab/flows/${encodeURIComponent(id)}/mcp-tools`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }),
  updateMcpTool: (id: string, toolId: string, body: AnyRecord) => request<AnyRecord>(`/api/lab/flows/${encodeURIComponent(id)}/mcp-tools/${encodeURIComponent(toolId)}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }),
  deleteMcpTool: (id: string, toolId: string) => request<AnyRecord>(`/api/lab/flows/${encodeURIComponent(id)}/mcp-tools/${encodeURIComponent(toolId)}`, { method: 'DELETE' }),
  scaffoldDlc: (id: string, body: AnyRecord) => request<AnyRecord>(`/api/developer/flows/${encodeURIComponent(id)}/portable-dlc`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }),
  dlc: (id: string) => request<AnyRecord>(`/api/developer/flows/${encodeURIComponent(id)}/portable-dlc`),
  mcpSource: (id: string, nodeId: string) => request<AnyRecord>(`/api/lab/flows/${encodeURIComponent(id)}/mcp-nodes/${encodeURIComponent(nodeId)}/source`),
  replaceMcpSource: (id: string, nodeId: string, source: string, expectedDigest: string) => request<AnyRecord>(`/api/lab/flows/${encodeURIComponent(id)}/mcp-nodes/${encodeURIComponent(nodeId)}/source`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ source, expected_source_digest: expectedDigest }) }),
  aiSteward: (id: string, body: AnyRecord) => request<AnyRecord>(`/api/lab/flows/${encodeURIComponent(id)}/ai-steward`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }),
  preflight: (id: string) => request<AnyRecord>(`/api/studio/release/${encodeURIComponent(id)}/preflight`),
  conformance: () => request<AnyRecord>('/api/studio/conformance'),
  analyze: (id: string, files: AnyRecord) => request<AnyRecord>(`/api/lab/flows/${encodeURIComponent(id)}/analyze`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ files, target: 'dev' }) }),
  validate: (id: string, files: AnyRecord) => request<AnyRecord>(`/api/lab/flows/${encodeURIComponent(id)}/validate`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ files }) }),
  createNode: (id: string, body: AnyRecord) => request<AnyRecord>(`/api/lab/flows/${encodeURIComponent(id)}/nodes`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }),
  updateNode: (id: string, nodeId: string, body: AnyRecord) => request<AnyRecord>(`/api/lab/flows/${encodeURIComponent(id)}/nodes/${encodeURIComponent(nodeId)}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }),
  deleteNode: (id: string, nodeId: string) => request<AnyRecord>(`/api/lab/flows/${encodeURIComponent(id)}/nodes/${encodeURIComponent(nodeId)}`, { method: 'DELETE', headers: { 'Content-Type': 'application/json' }, body: '{}' }),
  saveEdges: (id: string, edges: AnyRecord[]) => request<AnyRecord>(`/api/lab/flows/${encodeURIComponent(id)}/edges`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ edges }) }),
  saveLayout: (id: string, layout: AnyRecord) => request<AnyRecord>(`/api/lab/flows/${encodeURIComponent(id)}/layout`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ layout }) }),
  capabilityRegistry: () => request<{ capabilities: AnyRecord[]; entries: AnyRecord[] }>('/api/developer/capability-cartridges'),
  capabilityReadiness: (id: string) => request<AnyRecord>(`/api/developer/flows/${encodeURIComponent(id)}/capability-readiness`),
  testRun: (id: string, inputs: AnyRecord) => request<AnyRecord>(`/api/lab/flows/${encodeURIComponent(id)}/test-run`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ inputs }) }),
  run: (runId: string) => request<AnyRecord>(`/api/cartridge-runs/${encodeURIComponent(runId)}`),
  verifyCapability: (id: string, body: { success_run_id: string; failure_run_id: string }) => request<AnyRecord>(`/api/developer/flows/${encodeURIComponent(id)}/capability-verifications`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }),
  currentVerification: (id: string) => request<AnyRecord>(`/api/developer/flows/${encodeURIComponent(id)}/capability-verifications/current`),
  productionCandidate: (id: string) => request<AnyRecord>(`/api/developer/flows/${encodeURIComponent(id)}/production-candidate`, { method: 'POST' }),
  tuning: (id: string) => request<AnyRecord>(`/api/lab/flows/${encodeURIComponent(id)}/tuning`),
  freezeRecipe: (id: string) => request<AnyRecord>(`/api/lab/flows/${encodeURIComponent(id)}/tuning/releases`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ author: 'capability-workshop', message: '冻结当前配方用于签名交付' }) }),
  packageVerifiedRelease: (id: string, verificationToken: string) => request<AnyRecord>(`/api/developer/flows/${encodeURIComponent(id)}/production-release`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ verification_token: verificationToken, requested_by: 'capability-workshop' }) }),
  publishCapability: (id: string, body: AnyRecord) => request<AnyRecord>(`/api/developer/flows/${encodeURIComponent(id)}/capability-cartridges`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }),
  activateCapability: (id: string, active: boolean, revision?: number) => request<AnyRecord>(`/api/developer/capability-cartridges/${encodeURIComponent(id)}/activation`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ active, revision }) }),
}
