import { useEffect, useRef, useState } from 'react'

import { fetchDlcRunContext } from '../api.ts'

export function DlcSandboxFrame({
  cartridgeId,
  runId,
  onSubmit,
  mode = 'director',
}: {
  cartridgeId: string
  runId: string
  onSubmit?: (values: Record<string, any>) => Promise<void> | void
  mode?: 'director' | 'result'
}) {
  const frameRef = useRef<HTMLIFrameElement | null>(null)
  const [project, setProject] = useState<any>(null)
  const [artifacts, setArtifacts] = useState<any[]>([])
  const [ready, setReady] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    setReady(false)
    setError('')
    fetchDlcRunContext(runId)
      .then((result) => {
        const context = result.context || {}
        const nextProject = mode === 'result'
          ? context.approved_frame_bundle?.project || context.approved_storyboard_project?.project || context.approved_storyboard_project || context.storyboard_frame_bundle?.project || context.storyboard_project?.project || context.storyboard_project
          : context.storyboard_frame_bundle?.project || context.storyboard_project?.project || context.storyboard_project
        setProject(nextProject || null)
        setArtifacts(result.artifacts || [])
      })
      .catch((reason) => setError(reason?.message || 'DLC context failed'))
  }, [mode, runId])

  useEffect(() => {
    const receive = (event: MessageEvent) => {
      if (event.source !== frameRef.current?.contentWindow) return
      const message = event.data || {}
      if (message.schema !== 'cartridgeflow.dlc_ui_message.v1') return
      if (message.type === 'ready') setReady(true)
      if (message.type === 'submit_interaction' && message.values && typeof message.values === 'object') {
        void onSubmit?.(message.values)
      }
    }
    window.addEventListener('message', receive)
    return () => window.removeEventListener('message', receive)
  }, [onSubmit])

  useEffect(() => {
    if (!ready || !project) return
    frameRef.current?.contentWindow?.postMessage({
      schema: 'cartridgeflow.dlc_ui_host.v1',
      type: mode === 'result' ? 'load_result' : 'load_storyboard',
      run_id: runId,
      project,
      artifacts,
    }, '*')
  }, [artifacts, mode, ready, project, runId])

  if (error) return <div className="cf-dlc-frame-error">{error}</div>
  return (
    <iframe
      ref={frameRef}
      className={`cf-dlc-sandbox-frame ${mode === 'result' ? 'cf-dlc-result-frame' : ''}`}
      title={`${cartridgeId} ${mode === 'result' ? 'storyboard result' : 'director console'}`}
      src={`/api/cartridges/${encodeURIComponent(cartridgeId)}/dlc/frontend`}
      sandbox="allow-scripts"
    />
  )
}
