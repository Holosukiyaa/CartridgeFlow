import { WORKSPACE_SNAPSHOT_VERSION } from '../config.ts'
import { emptyWorkspaceSnapshot, type WorkspaceSnapshot } from './model.ts'

const keyFor = (projectId: string) => `cartridgeflow.studio.v${WORKSPACE_SNAPSHOT_VERSION}.${projectId}`

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
