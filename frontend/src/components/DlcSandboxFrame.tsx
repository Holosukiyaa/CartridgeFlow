import { useEffect, useRef, useState } from 'react'

import { fetchDlcRunContext } from '../api.ts'

export function DlcSandboxFrame({
  cartridgeId,
  runId,
  onSubmit,
}: {
  cartridgeId: string
  runId: string
  onSubmit: (values: Record<string, any>) => Promise<void> | void
}) {
  const frameRef = useRef<HTMLIFrameElement | null>(null)
  const [project, setProject] = useState<any>(null)
  const [ready, setReady] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    setReady(false)
    setError('')
    fetchDlcRunContext(runId)
      .then((result) => setProject(result.context?.storyboard_project || result.context?.storyboard_frame_bundle?.project || null))
      .catch((reason) => setError(reason?.message || 'DLC context failed'))
  }, [runId])

  useEffect(() => {
    const receive = (event: MessageEvent) => {
      if (event.source !== frameRef.current?.contentWindow) return
      const message = event.data || {}
      if (message.schema !== 'cartridgeflow.dlc_ui_message.v1') return
      if (message.type === 'ready') setReady(true)
      if (message.type === 'submit_interaction' && message.values && typeof message.values === 'object') {
        void onSubmit(message.values)
      }
    }
    window.addEventListener('message', receive)
    return () => window.removeEventListener('message', receive)
  }, [onSubmit])

  useEffect(() => {
    if (!ready || !project) return
    frameRef.current?.contentWindow?.postMessage({
      schema: 'cartridgeflow.dlc_ui_host.v1',
      type: 'load_storyboard',
      run_id: runId,
      project,
    }, '*')
  }, [ready, project, runId])

  if (error) return <div className="cf-dlc-frame-error">{error}</div>
  return (
    <iframe
      ref={frameRef}
      className="cf-dlc-sandbox-frame"
      title={`${cartridgeId} director console`}
      src={`/api/cartridges/${encodeURIComponent(cartridgeId)}/dlc/frontend`}
      sandbox="allow-scripts"
    />
  )
}
