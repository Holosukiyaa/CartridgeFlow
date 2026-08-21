import { WORKSPACE_SNAPSHOT_VERSION } from '../config.ts'
import { emptyWorkspaceSnapshot, type WorkspaceSnapshot } from './model.ts'

const keyFor = (projectId: string) => `cartridgeflow.studio.v${WORKSPACE_SNAPSHOT_VERSION}.${projectId}`
const RECENT_PROJECT_KEY = 'cartridgeflow.studio-project'

export function readRecentProjectId() {
  return localStorage.getItem(RECENT_PROJECT_KEY) || ''
}

export function rememberProjectId(projectId: string) {
  if (projectId) localStorage.setItem(RECENT_PROJECT_KEY, projectId)
  else localStorage.removeItem(RECENT_PROJECT_KEY)
}

export function createDraftProjectId() {
  return `project.${crypto.randomUUID()}`
}

export function projectStudioPath(projectId: string) {
  return `/projects/${encodeURIComponent(projectId)}/studio`
}

export function readSnapshot(projectId: string): WorkspaceSnapshot | null {
  try {
    const value = JSON.parse(localStorage.getItem(keyFor(projectId)) || 'null') as WorkspaceSnapshot | null
    if (!value || value.version !== WORKSPACE_SNAPSHOT_VERSION) return null
    return { ...emptyWorkspaceSnapshot(), ...value }
  } catch {
    return null
  }
}

export function writeSnapshot(projectId: string, snapshot: WorkspaceSnapshot) {
  localStorage.setItem(keyFor(projectId), JSON.stringify(snapshot))
}
