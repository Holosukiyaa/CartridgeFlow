const AUTO_LAYOUT_NEW_FLOW_KEY = 'cartridgeflow.lite.auto-layout-new-flow.v1'

export function markNewFlowForAutoLayout(flowId: string) {
  window.sessionStorage.setItem(AUTO_LAYOUT_NEW_FLOW_KEY, flowId)
}

export function shouldAutoLayoutNewFlow(flowId: string) {
  return window.sessionStorage.getItem(AUTO_LAYOUT_NEW_FLOW_KEY) === flowId
}

export function clearNewFlowAutoLayout(flowId: string) {
  if (shouldAutoLayoutNewFlow(flowId)) window.sessionStorage.removeItem(AUTO_LAYOUT_NEW_FLOW_KEY)
}
