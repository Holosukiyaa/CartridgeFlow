import { useEffect, useRef, useState } from 'react'

import { fetchDlcRunContext } from '../api.ts'

function unwrapDlcPayload(value: any): any {
  if (!value || typeof value !== 'object') return null
  if (value.project && typeof value.project === 'object') return value.project
  if (value.payload && typeof value.payload === 'object') return value.payload
  if (value.bundle && typeof value.bundle === 'object') return unwrapDlcPayload(value.bundle)
  return value
}

function selectDlcPayload(context: Record<string, any>): any {
  const entries = Object.entries(context).filter(([, value]) => value != null)
  for (const [, value] of entries.reverse()) {
    const payload = unwrapDlcPayload(value)
    if (payload) return payload
  }
  return context
}

export function DlcSandboxFrame({
  cartridgeId,
  runId,
  onSubmit,
  mode = 'interaction',
}: {
  cartridgeId: string
  runId: string
  onSubmit?: (values: Record<string, any>) => Promise<void> | void
  mode?: 'interaction' | 'result'
}) {
  const frameRef = useRef<HTMLIFrameElement | null>(null)
  const [context, setContext] = useState<Record<string, any>>({})
  const [payload, setPayload] = useState<any>(null)
  const [artifacts, setArtifacts] = useState<any[]>([])
  const [ready, setReady] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    setReady(false)
    setError('')
    fetchDlcRunContext(runId)
      .then((result) => {
        const nextContext = result.context || {}
        setContext(nextContext)
        setPayload(selectDlcPayload(nextContext))
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
    if (!ready) return
    frameRef.current?.contentWindow?.postMessage({
      schema: 'cartridgeflow.dlc_ui_host.v1',
      // v0.1.0 keeps these message names for existing DLC compatibility.
      type: mode === 'result' ? 'load_result' : 'load_storyboard',
      run_id: runId,
      context,
      project: payload,
      artifacts,
    }, '*')
  }, [artifacts, context, mode, payload, ready, runId])

  if (error) return <div className="cf-dlc-frame-error">{error}</div>
  return (
    <iframe
      ref={frameRef}
      className={`cf-dlc-sandbox-frame ${mode === 'result' ? 'cf-dlc-result-frame' : ''}`}
      title={`${cartridgeId} ${mode === 'result' ? 'extension result' : 'extension interaction'}`}
      src={`/api/cartridges/${encodeURIComponent(cartridgeId)}/dlc/frontend`}
      sandbox="allow-scripts"
    />
  )
}
