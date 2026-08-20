import { useEffect, useState, type FormEvent } from 'react'
import { Loader2, Trash2 } from 'lucide-react'
import {
  ApiError,
  activateCreatorLlmProvider,
  detectCreatorLlm,
  fetchCreatorStudioResources,
  listCreatorLlmProviders,
  removeCreatorLlmProvider,
  saveCreatorLlmProvider,
  saveCreatorStudioResources,
  testCreatorLlmProvider,
  type CreatorLlmProvider,
  type CreatorStudioResources,
  type CreatorToolResource,
} from '../api/client.ts'
import { AUTHORING_PROVIDER_ID, LLM_PRESETS, TOOL_KINDS } from '../config.ts'
import { visualFrame } from '../visualFixture.ts'
import { copy } from '../copy.ts'
import { Alert, Button, Dialog, Field, SegmentedControl, TextInput, cx } from '../ui/index.ts'

function slug(value: string) {
  const compact = value.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 24)
  return compact || crypto.randomUUID().slice(0, 8)
}

export function ResourcePool({ onClose }: { onClose: () => void }) {
  const [providers, setProviders] = useState<CreatorLlmProvider[]>([])
  const [resources, setResources] = useState<CreatorStudioResources | null>(null)
  const [error, setError] = useState('')
  const [working, setWorking] = useState(false)
  const [addingApi, setAddingApi] = useState(visualFrame() === 'frame3')
  const [addingTool, setAddingTool] = useState(visualFrame() === 'frame3')

  const reload = async () => {
    const [nextProviders, nextResources] = await Promise.all([listCreatorLlmProviders(), fetchCreatorStudioResources()])
    setProviders(nextProviders.providers)
    setResources(nextResources)
  }

  useEffect(() => {
    reload().catch((reason) => setError(reason instanceof ApiError ? reason.message : copy.connectFail))
  }, [])

  const tools = [...(resources?.builtin_tools || []), ...(resources?.tools || [])]

  return <Dialog size="wide" title={copy.settingsTitle} description={copy.settingsHint} locked={working} onClose={onClose}>
    <div className="pool">
      {error ? <Alert>{error}</Alert> : null}
      <div className="pool-grid">
        <div className="pool-col">
          <h3>{copy.settingsApis}<button type="button" className="pool-add" onClick={() => setAddingApi(true)}>+ {copy.addApi}</button></h3>
          <ApiList
            providers={providers}
            adding={addingApi}
            working={working}
            onToggleAdd={() => setAddingApi((open) => !open)}
            onBusy={setWorking}
            onError={setError}
            onReload={reload}
          />
        </div>
        <div className="pool-col">
          <h3>{copy.settingsTools}<button type="button" className="pool-add" onClick={() => setAddingTool(true)}>+ {copy.addTool}</button></h3>
          <ToolList
            tools={tools}
            resources={resources}
            adding={addingTool}
            working={working}
            onToggleAdd={() => setAddingTool((open) => !open)}
            onBusy={setWorking}
            onError={setError}
            onReload={reload}
          />
        </div>
      </div>
      <div className="pool-footer">
        <p className="pool-foot">{copy.poolFoot}</p>
        <Button variant="ghost" onClick={onClose}>关闭</Button>
      </div>
    </div>
  </Dialog>
}

function ApiList({
  providers,
  adding,
  working,
  onToggleAdd,
  onBusy,
  onError,
  onReload,
}: {
  providers: CreatorLlmProvider[]
  adding: boolean
  working: boolean
  onToggleAdd: () => void
  onBusy: (value: boolean) => void
  onError: (value: string) => void
  onReload: () => Promise<void>
}) {
  const run = async (task: () => Promise<void>) => {
    onBusy(true)
    onError('')
    try {
      await task()
      await onReload()
    } catch (reason) {
      onError(reason instanceof ApiError ? reason.message : copy.connectFail)
    } finally { onBusy(false) }
  }

  return <div className="pool-list">
    {!providers.length && !adding ? <p className="pool-empty">{copy.settingsEmptyApis}</p> : null}
    {providers.map((provider) => <article className="pool-card" key={provider.id}>
      <div>
        <strong>{provider.name || provider.id}</strong>
        {provider.id === AUTHORING_PROVIDER_ID ? <em>{copy.authoringBadge}</em> : null}
        <small>{provider.default_model || provider.base_url || provider.id}</small>
      </div>
      <div className="pool-card-actions">
        <Button variant="ghost" disabled={working || !provider.has_key} onClick={() => void run(() => testCreatorLlmProvider(provider.id, provider.default_model || '').then(() => undefined))}>{copy.testItem}</Button>
        {provider.id !== AUTHORING_PROVIDER_ID ? <Button variant="ghost" disabled={working} onClick={() => void run(() => activateCreatorLlmProvider(provider.id).then(() => undefined))}>{copy.activateAuthoring}</Button> : null}
        {provider.id !== AUTHORING_PROVIDER_ID ? <Button variant="icon" aria-label={copy.deleteItem} disabled={working} onClick={() => void run(() => removeCreatorLlmProvider(provider.id).then(() => undefined))}><Trash2 size={14} /></Button> : null}
      </div>
    </article>)}
    {adding ? <ApiForm working={working} onCancel={onToggleAdd} onSave={(body) => void run(async () => { await addProvider(body); onToggleAdd() })} /> : <Button variant="ghost" disabled={working} onClick={onToggleAdd}>{copy.addApi}</Button>}
  </div>
}

function ApiForm({
  working,
  onCancel,
  onSave,
}: {
  working: boolean
  onCancel: () => void
  onSave: (body: { name: string; base_url: string; api_key: string; model: string }) => void
}) {
  const [presetId, setPresetId] = useState(LLM_PRESETS[0].id)
  const [name, setName] = useState(LLM_PRESETS[0].label)
  const [baseUrl, setBaseUrl] = useState(LLM_PRESETS[0].baseUrl)
  const [apiKey, setApiKey] = useState('')
  const [model, setModel] = useState(LLM_PRESETS[0].model)

  const choose = (id: string) => {
    const next = LLM_PRESETS.find((item) => item.id === id) || LLM_PRESETS[LLM_PRESETS.length - 1]
    setPresetId(next.id)
    setName(next.label)
    if (next.baseUrl) setBaseUrl(next.baseUrl)
    setModel(next.model)
  }

  const submit = (event: FormEvent) => {
    event.preventDefault()
    if (!baseUrl.trim() || !apiKey.trim()) return
    onSave({ name: name.trim() || copy.settingsApis, base_url: baseUrl.trim(), api_key: apiKey.trim(), model: model.trim() })
  }

  return <form className="pool-form" onSubmit={submit}>
    <SegmentedControl label={copy.provider} value={presetId} options={LLM_PRESETS} disabled={working} onChange={choose} />
    <Field label={copy.toolName}><TextInput value={name} disabled={working} onChange={(event) => setName(event.currentTarget.value)} /></Field>
    <Field label={copy.baseUrl}><TextInput value={baseUrl} disabled={working} onChange={(event) => setBaseUrl(event.currentTarget.value)} /></Field>
    <Field label={copy.apiKey}><TextInput type="password" autoComplete="off" value={apiKey} disabled={working} placeholder={copy.keyPlaceholder} onChange={(event) => setApiKey(event.currentTarget.value)} /></Field>
    <Field label={copy.model}><TextInput value={model} disabled={working} onChange={(event) => setModel(event.currentTarget.value)} /></Field>
    <div className="dialog-foot">
      <Button variant="ghost" disabled={working} onClick={onCancel}>{copy.cancel}</Button>
      <Button type="submit" disabled={working || !baseUrl.trim() || !apiKey.trim()}>
        {working ? <Loader2 className="spinning" /> : null}
        {working ? copy.testing : copy.testConnect}
      </Button>
    </div>
  </form>
}

async function addProvider(body: { name: string; base_url: string; api_key: string; model: string }) {
  const detected = await detectCreatorLlm({ base_url: body.base_url, api_key: body.api_key, preferred_model: body.model })
  const model = body.model.trim() || detected.provider.default_model
  const saved = await saveCreatorLlmProvider({
    ...detected.provider,
    id: `pool.${slug(body.name)}`,
    name: body.name,
    api_key: body.api_key,
    default_model: model,
    available_models: detected.detection.models,
    enabled: true,
    adapter_profile: 'standard',
  })
  await testCreatorLlmProvider(saved.provider.id, model)
}

function ToolList({
  tools,
  resources,
  adding,
  working,
  onToggleAdd,
  onBusy,
  onError,
  onReload,
}: {
  tools: CreatorToolResource[]
  resources: CreatorStudioResources | null
  adding: boolean
  working: boolean
  onToggleAdd: () => void
  onBusy: (value: boolean) => void
  onError: (value: string) => void
  onReload: () => Promise<void>
}) {
  const persist = async (nextTools: CreatorToolResource[]) => {
    if (!resources) return
    onBusy(true)
    onError('')
    try {
      await saveCreatorStudioResources({ version: resources.version, tools: nextTools, bindings: resources.bindings })
      await onReload()
    } catch (reason) {
      onError(reason instanceof ApiError ? reason.message : copy.connectFail)
    } finally { onBusy(false) }
  }

  return <div className="pool-list">
    {!tools.length && !adding ? <p className="pool-empty">{copy.settingsEmptyTools}</p> : null}
    {tools.map((tool) => <article className={cx('pool-card', tool.enabled === false && 'is-off')} key={tool.id}>
      <div>
        <strong>{tool.name}</strong>
        {tool.kind === 'builtin' || tool.locked ? <em>{copy.builtinBadge}</em> : <em>{tool.kind}</em>}
        <small>{tool.description || tool.endpoint || tool.command || `${tool.server || ''}/${tool.tool || ''}`}</small>
      </div>
      {tool.locked || tool.kind === 'builtin' ? null : <div className="pool-card-actions">
        <Button variant="ghost" disabled={working} onClick={() => void persist((resources?.tools || []).map((item) => item.id === tool.id ? { ...item, enabled: item.enabled === false } : item))}>
          {tool.enabled === false ? copy.enableItem : copy.disableItem}
        </Button>
        <Button variant="icon" aria-label={copy.deleteItem} disabled={working} onClick={() => void persist((resources?.tools || []).filter((item) => item.id !== tool.id))}><Trash2 size={14} /></Button>
      </div>}
    </article>)}
    {adding ? <ToolForm working={working} onCancel={onToggleAdd} onSave={(tool) => void persist([...(resources?.tools || []), tool]).then(onToggleAdd)} /> : <Button variant="ghost" disabled={working} onClick={onToggleAdd}>{copy.addTool}</Button>}
  </div>
}

function ToolForm({
  working,
  onCancel,
  onSave,
}: {
  working: boolean
  onCancel: () => void
  onSave: (tool: CreatorToolResource) => void
}) {
  const [name, setName] = useState('')
  const [kind, setKind] = useState<(typeof TOOL_KINDS)[number]['id']>('mcp')
  const [endpoint, setEndpoint] = useState('')
  const [server, setServer] = useState('')
  const [action, setAction] = useState('')

  const submit = (event: FormEvent) => {
    event.preventDefault()
    if (!name.trim()) return
    const id = `tool.${slug(name)}`
    onSave({
      id,
      name: name.trim(),
      kind,
      description: '',
      endpoint: kind === 'remote_api' ? endpoint.trim() : '',
      command: kind !== 'remote_api' ? endpoint.trim() : '',
      server: server.trim() || id,
      tool: action.trim() || id,
      enabled: true,
    })
  }

  return <form className="pool-form" onSubmit={submit}>
    <SegmentedControl label={copy.toolKind} value={kind} options={[...TOOL_KINDS]} disabled={working} onChange={setKind} />
    <Field label={copy.toolName}><TextInput value={name} disabled={working} onChange={(event) => setName(event.currentTarget.value)} /></Field>
    <Field label={copy.toolEndpoint}><TextInput value={endpoint} disabled={working} onChange={(event) => setEndpoint(event.currentTarget.value)} /></Field>
    {kind === 'mcp' ? <>
      <Field label={copy.toolServer}><TextInput value={server} disabled={working} onChange={(event) => setServer(event.currentTarget.value)} /></Field>
      <Field label={copy.toolAction}><TextInput value={action} disabled={working} onChange={(event) => setAction(event.currentTarget.value)} /></Field>
    </> : null}
    <div className="dialog-foot">
      <Button variant="ghost" disabled={working} onClick={onCancel}>{copy.cancel}</Button>
      <Button type="submit" disabled={working || !name.trim()}>{copy.saveTool}</Button>
    </div>
  </form>
}
