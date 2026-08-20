import { useState, type FormEvent } from 'react'
import { Loader2 } from 'lucide-react'
import { ApiError } from '../api/client.ts'
import { LLM_PRESETS } from '../config.ts'
import { copy } from '../copy.ts'
import { visualFrame } from '../visualFixture.ts'
import { Alert, Button, Dialog, Field, SegmentedControl, TextInput } from '../ui/index.ts'

export function ConnectDialog({
  current,
  onConnect,
  onClose,
}: {
  current: { provider: string; has_key: boolean; base_url: string; model: string } | null
  onConnect: (connection: { base_url: string; api_key: string; model: string }) => Promise<void>
  onClose: () => void
}) {
  const initial = LLM_PRESETS.find((item) => current?.base_url.startsWith(item.baseUrl) && item.baseUrl) || LLM_PRESETS[0]
  const [presetId, setPresetId] = useState(initial.id)
  const [baseUrl, setBaseUrl] = useState(current?.base_url || initial.baseUrl)
  const [apiKey, setApiKey] = useState('')
  const [model, setModel] = useState(current?.model || initial.model)
  const [working, setWorking] = useState(false)
  const [error, setError] = useState('')

  const choose = (id: string) => {
    if (working) return
    const next = LLM_PRESETS.find((item) => item.id === id) || LLM_PRESETS[LLM_PRESETS.length - 1]
    setPresetId(next.id)
    if (next.baseUrl) setBaseUrl(next.baseUrl)
    setModel(next.model)
  }

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (!baseUrl.trim() || !apiKey.trim() || working) return
    setWorking(true)
    setError('')
    try {
      await onConnect({ base_url: baseUrl.trim(), api_key: apiKey.trim(), model: model.trim() })
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : copy.connectFail)
    } finally {
      setWorking(false)
    }
  }

  return <Dialog title={copy.connectTitle} description={copy.connectHint} locked={working} align={visualFrame() === 'frame2' ? 'start' : 'center'} onClose={onClose}>
    <form onSubmit={submit}>
      <SegmentedControl label={copy.provider} value={presetId} options={LLM_PRESETS} disabled={working} onChange={choose} />
      <Field label={copy.baseUrl}><TextInput value={baseUrl} disabled={working} onChange={(event) => setBaseUrl(event.currentTarget.value)} /></Field>
      <Field label={copy.apiKey}><TextInput type="password" autoComplete="off" value={apiKey} disabled={working} placeholder={copy.keyPlaceholder} onChange={(event) => setApiKey(event.currentTarget.value)} /></Field>
      <Field label={copy.model}><TextInput value={model} disabled={working} onChange={(event) => setModel(event.currentTarget.value)} /></Field>
      {error ? <Alert>{error}</Alert> : null}
      <div className="dialog-foot">
        <span>{copy.connectFooter}</span>
        <Button variant="ghost" disabled={working} onClick={onClose}>{copy.cancel}</Button>
        <Button type="submit" disabled={working || !baseUrl.trim() || !apiKey.trim()}>
          {working ? <Loader2 className="spinning" /> : null}
          {working ? copy.testing : copy.testConnect}
        </Button>
      </div>
    </form>
  </Dialog>
}
