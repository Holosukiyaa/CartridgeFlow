import { useEffect, useState, type FormEvent } from 'react'
import { Check, Loader2 } from 'lucide-react'
import { ApiError } from '../../api.ts'
import { Button, Dialog, Field } from '../../ui/index.ts'

const presets = [
  { id: 'deepseek', label: 'DeepSeek', baseUrl: 'https://api.deepseek.com', model: 'deepseek-chat' },
  { id: 'openai', label: 'OpenAI', baseUrl: 'https://api.openai.com/v1', model: 'gpt-5-mini' },
  { id: 'local', label: '本机兼容服务', baseUrl: 'http://127.0.0.1:11434/v1', model: '' },
  { id: 'custom', label: '其他兼容服务', baseUrl: '', model: '' },
]

export function ModelConnectionDialog({ opened, current, onConnect, onClose }: {
  opened: boolean
  current: { provider: string; has_key: boolean; base_url: string; model: string } | null
  onConnect: (connection: { base_url: string; api_key: string; model: string }) => Promise<void>
  onClose: () => void
}) {
  const initialPreset = presets.find((item) => current?.base_url.startsWith(item.baseUrl) && item.baseUrl) || presets[0]
  const [presetId, setPresetId] = useState(initialPreset.id)
  const [baseUrl, setBaseUrl] = useState(current?.base_url || initialPreset.baseUrl)
  const [apiKey, setApiKey] = useState('')
  const [model, setModel] = useState(current?.model || initialPreset.model)
  const [working, setWorking] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!opened) return
    const next = presets.find((item) => current?.base_url.startsWith(item.baseUrl) && item.baseUrl) || presets[0]
    setPresetId(next.id)
    setBaseUrl(current?.base_url || next.baseUrl)
    setModel(current?.model || next.model)
    setApiKey('')
    setError('')
  }, [current, opened])

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (!baseUrl.trim() || !apiKey.trim()) return
    setWorking(true)
    setError('')
    try {
      await onConnect({ base_url: baseUrl.trim(), api_key: apiKey.trim(), model: model.trim() })
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : '连接没有通过测试，请检查后重试。')
    } finally {
      setWorking(false)
    }
  }

  return <Dialog opened={opened} onClose={working ? () => undefined : onClose} title={current?.has_key ? '更新 AI 连接' : '连接 AI'} aria-label="连接 AI 共创">
    <form className="model-connection-form" onSubmit={submit}>
      <Field.Select label="服务" value={presetId} disabled={working} data={presets.map((preset) => ({ value: preset.id, label: preset.label }))} onChange={(value) => {
        const next = presets.find((item) => item.id === value) || presets[3]
        setPresetId(next.id)
        if (next.baseUrl) setBaseUrl(next.baseUrl)
        setModel(next.model)
      }} />
      <Field.Text label="服务地址" value={baseUrl} disabled={working} onChange={(event) => setBaseUrl(event.currentTarget.value)} />
      <Field.Text label="API Key" type="password" autoComplete="off" value={apiKey} disabled={working} onChange={(event) => setApiKey(event.currentTarget.value)} />
      <Field.Text label="模型" value={model} disabled={working} onChange={(event) => setModel(event.currentTarget.value)} />
      {error && <div className="creator-connection-error" role="alert">{error}</div>}
      <div className="dialog-actions">
        <Button variant="default" disabled={working} onClick={onClose}>取消</Button>
        <Button type="submit" disabled={working || !baseUrl.trim() || !apiKey.trim()} leftSection={working ? <Loader2 className="spinning" /> : <Check />}>{current?.has_key ? '测试并更新' : '连接并继续'}</Button>
      </div>
    </form>
  </Dialog>
}
