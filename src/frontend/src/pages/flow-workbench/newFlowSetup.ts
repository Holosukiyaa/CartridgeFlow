import { readSessionStorageWithMigration } from '../../storage.ts'

const AUTO_LAYOUT_NEW_FLOW_KEY = 'cartridgeflow.auto-layout-new-flow.v1'
const LEGACY_AUTO_LAYOUT_NEW_FLOW_KEY = 'cartridgeflow.lite.auto-layout-new-flow.v1'

export function markNewFlowForAutoLayout(flowId: string) {
  window.sessionStorage.setItem(AUTO_LAYOUT_NEW_FLOW_KEY, flowId)
}

export function shouldAutoLayoutNewFlow(flowId: string) {
  return readSessionStorageWithMigration(AUTO_LAYOUT_NEW_FLOW_KEY, [LEGACY_AUTO_LAYOUT_NEW_FLOW_KEY]) === flowId
}

export function clearNewFlowAutoLayout(flowId: string) {
  if (shouldAutoLayoutNewFlow(flowId)) window.sessionStorage.removeItem(AUTO_LAYOUT_NEW_FLOW_KEY)
}
