import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { Cable, CheckCircle2, CirclePlus, Cloud, Loader2, PlugZap, Save, Trash2, Wrench } from 'lucide-react'
import {
  activateCreatorLlmProvider,
  fetchCreatorStudioResources,
  listCreatorLlmProviders,
  removeCreatorLlmProvider,
  saveCreatorLlmProvider,
  saveCreatorStudioResources,
  testCreatorLlmProvider,
  type CreatorLlmProvider,
  type CreatorStudioResources,
  type CreatorToolResource,
} from '../../api.ts'
import { Button, Dialog, Field, Tabs } from '../../ui/index.ts'

type ModelDraft = {
  id: string
  name: string
  baseUrl: string
  apiKey: string
  model: string
  wireApi: string
  timeout: string
}

type ToolDraft = {
  id: string
  name: string
  kind: string
  description: string
  server: string
  tool: string
  endpoint: string
  command: string
  args: string
  authEnv: string
  packageMode: string
  readOnly: boolean
  enabled: boolean
}

const emptyModel = (): ModelDraft => ({ id: '', name: '', baseUrl: '', apiKey: '', model: '', wireApi: 'chat_completions', timeout: '120' })
const modelDraft = (provider?: CreatorLlmProvider): ModelDraft => ({
  id: provider?.id || '',
  name: provider?.name || '',
  baseUrl: provider?.base_url || '',
  apiKey: '',
  model: provider?.default_model || '',
  wireApi: provider?.wire_api || 'chat_completions',
  timeout: String(provider?.timeout || 120),
})
const emptyTool = (): ToolDraft => ({ id: '', name: '', kind: 'mcp', description: '', server: '', tool: '', endpoint: '', command: '', args: '', authEnv: '', packageMode: 'descriptor', readOnly: false, enabled: true })
const toolDraft = (tool?: CreatorToolResource): ToolDraft => ({
  id: tool?.id || '',
  name: tool?.name || '',
  kind: tool?.kind || 'mcp',
  description: tool?.description || '',
  server: tool?.server || '',
  tool: tool?.tool || '',
  endpoint: tool?.endpoint || '',
  command: tool?.command || '',
  args: tool?.args || '',
  authEnv: tool?.auth_env || '',
  packageMode: tool?.package_mode || 'descriptor',
  readOnly: Boolean(tool?.read_only),
  enabled: tool?.enabled !== false,
})

export function ResourceManagerDialog({ opened, initialTab, projectId, onClose }: {
  opened: boolean
  initialTab: 'models' | 'tools'
  projectId: string
  onClose: () => void
}) {
  const [tab, setTab] = useState<'models' | 'tools'>(initialTab)
  const [providers, setProviders] = useState<CreatorLlmProvider[]>([])
  const [resources, setResources] = useState<CreatorStudioResources | null>(null)
  const [model, setModel] = useState<ModelDraft>(emptyModel)
  const [tool, setTool] = useState<ToolDraft>(emptyTool)
  const [busy, setBusy] = useState('')
  const [message, setMessage] = useState<{ tone: 'success' | 'error' | 'neutral'; text: string } | null>(null)
  const [deleteConfirm, setDeleteConfirm] = useState('')

  const reloadModels = async () => setProviders((await listCreatorLlmProviders()).providers)
  const reloadTools = async () => setResources(await fetchCreatorStudioResources())

  useEffect(() => {
    if (!opened) return
    setTab(initialTab)
    setMessage(null)
    void Promise.all([reloadModels(), reloadTools()]).catch((error) => setMessage({ tone: 'error', text: error instanceof Error ? error.message : '资源配置读取失败' }))
  }, [initialTab, opened])

  const selectedToolIds = useMemo(() => new Set(resources?.bindings.tools?.[projectId] || []), [projectId, resources])

  const saveModel = async (event: FormEvent) => {
    event.preventDefault()
    if (!model.name.trim() || !model.baseUrl.trim() || !model.model.trim()) {
      setMessage({ tone: 'error', text: '名称、服务地址和默认模型不能为空。' })
      return
    }
    setBusy('model-save')
    setMessage(null)
    try {
      const result = await saveCreatorLlmProvider({
        id: model.id,
        name: model.name.trim(),
        api_type: 'openai',
        api_key: model.apiKey,
        base_url: model.baseUrl.trim(),
        default_model: model.model.trim(),
        wire_api: model.wireApi,
        capabilities: ['text_reasoning'],
        adapter_profile: 'standard',
        enabled: providers.length === 0,
        timeout: Math.max(1, Number(model.timeout) || 120),
      })
      await reloadModels()
      setModel(modelDraft(result.provider))
      setMessage({ tone: 'success', text: '模型连接已保存在本机。' })
    } catch (error) {
      setMessage({ tone: 'error', text: error instanceof Error ? error.message : '模型连接保存失败' })
    } finally { setBusy('') }
  }

  const testModel = async () => {
    if (!model.id) return
    setBusy('model-test')
    setMessage(null)
    try {
      await testCreatorLlmProvider(model.id, model.model)
      await reloadModels()
      setMessage({ tone: 'success', text: '模型已返回真实响应，连接可用。' })
    } catch (error) {
      setMessage({ tone: 'error', text: error instanceof Error ? error.message : '模型连接测试失败' })
    } finally { setBusy('') }
  }

  const activateModel = async () => {
    if (!model.id) return
    setBusy('model-activate')
    try {
      await activateCreatorLlmProvider(model.id)
      await reloadModels()
      setMessage({ tone: 'success', text: '当前共创 AI 已切换。' })
    } catch (error) {
      setMessage({ tone: 'error', text: error instanceof Error ? error.message : '模型切换失败' })
    } finally { setBusy('') }
  }

  const deleteModel = async () => {
    if (!model.id) return
    if (deleteConfirm !== `model:${model.id}`) {
      setDeleteConfirm(`model:${model.id}`)
      return
    }
    setBusy('model-delete')
    try {
      await removeCreatorLlmProvider(model.id)
      await reloadModels()
      setModel(emptyModel())
      setDeleteConfirm('')
      setMessage({ tone: 'success', text: '模型连接已删除。' })
    } catch (error) {
      setMessage({ tone: 'error', text: error instanceof Error ? error.message : '模型连接删除失败' })
    } finally { setBusy('') }
  }

  const saveTool = async (event: FormEvent) => {
    event.preventDefault()
    if (!resources || !tool.name.trim() || !tool.id.trim()) {
      setMessage({ tone: 'error', text: '工具 ID 和名称不能为空。' })
      return
    }
    setBusy('tool-save')
    const item: CreatorToolResource = {
      id: tool.id.trim(), name: tool.name.trim(), kind: tool.kind, description: tool.description.trim(),
      server: tool.server.trim(), tool: tool.tool.trim(), endpoint: tool.endpoint.trim(), command: tool.command.trim(),
      args: tool.args.trim(), auth_env: tool.authEnv.trim(), package_mode: tool.packageMode, read_only: tool.readOnly, enabled: tool.enabled,
    }
    const tools = resources.tools.some((entry) => entry.id === item.id) ? resources.tools.map((entry) => entry.id === item.id ? item : entry) : [...resources.tools, item]
    try {
      await saveCreatorStudioResources({ version: resources.version, tools, bindings: resources.bindings })
      await reloadTools()
      setTool(toolDraft(item))
      setMessage({ tone: 'success', text: '工具配置已保存在本机资源池。' })
    } catch (error) {
      setMessage({ tone: 'error', text: error instanceof Error ? error.message : '工具配置保存失败' })
    } finally { setBusy('') }
  }

  const toggleToolBinding = async (toolId: string) => {
    if (!resources) return
    setBusy(`bind:${toolId}`)
    const next = new Set(selectedToolIds)
    if (next.has(toolId)) next.delete(toolId); else next.add(toolId)
    const bindings = { ...resources.bindings, tools: { ...(resources.bindings.tools || {}), [projectId]: [...next] } }
    try {
      await saveCreatorStudioResources({ version: resources.version, tools: resources.tools, bindings })
      await reloadTools()
      setMessage({ tone: 'success', text: next.has(toolId) ? '工具已绑定到当前卡带。' : '工具已从当前卡带解除绑定。' })
    } catch (error) {
      setMessage({ tone: 'error', text: error instanceof Error ? error.message : '工具绑定保存失败' })
    } finally { setBusy('') }
  }

  const deleteTool = async () => {
    if (!resources || !tool.id) return
    if (deleteConfirm !== `tool:${tool.id}`) {
      setDeleteConfirm(`tool:${tool.id}`)
      return
    }
    setBusy('tool-delete')
    const tools = resources.tools.filter((entry) => entry.id !== tool.id)
    const bindings = { ...resources.bindings, tools: Object.fromEntries(Object.entries(resources.bindings.tools || {}).map(([key, ids]) => [key, ids.filter((id) => id !== tool.id)])) }
    try {
      await saveCreatorStudioResources({ version: resources.version, tools, bindings })
      await reloadTools()
      setTool(emptyTool())
      setDeleteConfirm('')
      setMessage({ tone: 'success', text: '工具配置已删除。' })
    } catch (error) {
      setMessage({ tone: 'error', text: error instanceof Error ? error.message : '工具配置删除失败' })
    } finally { setBusy('') }
  }

  const allTools = [...(resources?.builtin_tools || []), ...(resources?.tools || [])]

  return <Dialog opened={opened} onClose={busy ? () => undefined : onClose} size="min(1120px, calc(100vw - 40px))" title="资源配置" aria-label="模型与工具配置">
    <Tabs value={tab} onChange={(value) => value && setTab(value as 'models' | 'tools')} className="resource-manager">
      <Tabs.List><Tabs.Tab value="models" leftSection={<Cloud />}>模型配置</Tabs.Tab><Tabs.Tab value="tools" leftSection={<Wrench />}>工具配置</Tabs.Tab></Tabs.List>
      {message && <div className={`resource-manager-message is-${message.tone}`} role="status">{message.text}</div>}
      <Tabs.Panel value="models">
        <div className="resource-manager-layout">
          <nav className="resource-manager-list" aria-label="模型连接">
            <Button variant="light" onClick={() => { setModel(emptyModel()); setDeleteConfirm('') }} leftSection={<CirclePlus />}>新增连接</Button>
            {providers.map((provider) => <Button key={provider.id} variant={model.id === provider.id ? 'light' : 'subtle'} onClick={() => { setModel(modelDraft(provider)); setDeleteConfirm('') }} className="resource-list-item"><span><i className={provider.tested_ok ? 'is-ready' : ''} /><strong>{provider.name}</strong><small>{provider.default_model || '未设置模型'}</small></span>{provider.enabled && <em>当前</em>}</Button>)}
          </nav>
          <form className="resource-manager-form" onSubmit={saveModel}>
            <header><div><Cable /><strong>{model.id ? '编辑模型连接' : '新增模型连接'}</strong></div>{model.id && <code>{model.id}</code>}</header>
            <div className="resource-form-grid">
              <Field.Text label="名称" value={model.name} onChange={(event) => setModel({ ...model, name: event.currentTarget.value })} />
              <Field.Text label="API Key" type="password" autoComplete="off" value={model.apiKey} placeholder={model.id ? '留空以保留当前 Key' : ''} onChange={(event) => setModel({ ...model, apiKey: event.currentTarget.value })} />
              <Field.Text className="is-wide" label="Base URL / 接口地址" value={model.baseUrl} onChange={(event) => setModel({ ...model, baseUrl: event.currentTarget.value })} />
              <Field.Text label="默认模型" value={model.model} onChange={(event) => setModel({ ...model, model: event.currentTarget.value })} />
              <Field.Select label="调用协议" value={model.wireApi} data={[{ value: 'chat_completions', label: 'Chat Completions' }, { value: 'responses', label: 'Responses' }]} onChange={(value) => setModel({ ...model, wireApi: value || 'chat_completions' })} />
              <Field.Text label="超时（秒）" type="number" min="1" max="900" value={model.timeout} onChange={(event) => setModel({ ...model, timeout: event.currentTarget.value })} />
            </div>
            <footer>
              {model.id && <><Button variant="default" disabled={Boolean(busy)} onClick={() => void testModel()} leftSection={busy === 'model-test' ? <Loader2 className="spinning" /> : <PlugZap />}>测试连接</Button><Button variant="default" disabled={Boolean(busy)} onClick={() => void activateModel()} leftSection={<CheckCircle2 />}>设为当前</Button><Button color="red" variant="subtle" disabled={Boolean(busy)} onClick={() => void deleteModel()} leftSection={<Trash2 />}>{deleteConfirm === `model:${model.id}` ? '再次点击删除' : '删除'}</Button></>}
              <Button type="submit" disabled={Boolean(busy)} leftSection={busy === 'model-save' ? <Loader2 className="spinning" /> : <Save />}>保存连接</Button>
            </footer>
          </form>
        </div>
      </Tabs.Panel>
      <Tabs.Panel value="tools">
        <div className="resource-manager-layout">
          <nav className="resource-manager-list" aria-label="工具资源">
            <Button variant="light" onClick={() => { setTool(emptyTool()); setDeleteConfirm('') }} leftSection={<CirclePlus />}>新增工具</Button>
            {allTools.map((item) => <div className="resource-tool-row" key={item.id}><Button variant={tool.id === item.id ? 'light' : 'subtle'} onClick={() => !item.locked && setTool(toolDraft(item))} disabled={item.locked} className="resource-list-item"><span><i className={item.enabled === false ? '' : 'is-ready'} /><strong>{item.name}</strong><small>{item.kind} · {item.server || item.id}</small></span>{item.locked && <em>内置</em>}</Button><Field.Checkbox aria-label={`${item.name}用于当前卡带`} checked={selectedToolIds.has(item.id)} disabled={Boolean(busy)} onChange={() => void toggleToolBinding(item.id)} /></div>)}
          </nav>
          <form className="resource-manager-form" onSubmit={saveTool}>
            <header><div><Wrench /><strong>{tool.id ? '编辑本机工具' : '新增本机工具'}</strong></div>{tool.id && <code>{tool.id}</code>}</header>
            <div className="resource-form-grid">
              <Field.Text label="工具 ID" value={tool.id} disabled={resources?.tools.some((item) => item.id === tool.id)} onChange={(event) => setTool({ ...tool, id: event.currentTarget.value })} />
              <Field.Text label="名称" value={tool.name} onChange={(event) => setTool({ ...tool, name: event.currentTarget.value })} />
              <Field.Select label="类型" value={tool.kind} data={[{ value: 'mcp', label: 'MCP' }, { value: 'remote_api', label: '远程 API' }, { value: 'plugin', label: '本机插件' }]} onChange={(value) => setTool({ ...tool, kind: value || 'mcp' })} />
              <Field.Select label="打包方式" value={tool.packageMode} data={[{ value: 'descriptor', label: '随描述符声明' }, { value: 'external', label: '外部依赖' }]} onChange={(value) => setTool({ ...tool, packageMode: value || 'descriptor' })} />
              <Field.Text label="服务标识" value={tool.server} onChange={(event) => setTool({ ...tool, server: event.currentTarget.value })} />
              <Field.Text label="工具名称" value={tool.tool} onChange={(event) => setTool({ ...tool, tool: event.currentTarget.value })} />
              <Field.Text className="is-wide" label="Endpoint / 接口地址" value={tool.endpoint} onChange={(event) => setTool({ ...tool, endpoint: event.currentTarget.value })} />
              <Field.Text label="本机命令" value={tool.command} onChange={(event) => setTool({ ...tool, command: event.currentTarget.value })} />
              <Field.Text label="命令参数" value={tool.args} onChange={(event) => setTool({ ...tool, args: event.currentTarget.value })} />
              <Field.Text label="凭据环境变量" value={tool.authEnv} onChange={(event) => setTool({ ...tool, authEnv: event.currentTarget.value })} />
              <Field.Textarea className="is-wide" label="说明" value={tool.description} minRows={2} onChange={(event) => setTool({ ...tool, description: event.currentTarget.value })} />
              <Field.Checkbox label="只读工具" checked={tool.readOnly} onChange={(event) => setTool({ ...tool, readOnly: event.currentTarget.checked })} />
              <Field.Checkbox label="启用" checked={tool.enabled} onChange={(event) => setTool({ ...tool, enabled: event.currentTarget.checked })} />
            </div>
            <footer>{tool.id && resources?.tools.some((item) => item.id === tool.id) && <Button color="red" variant="subtle" disabled={Boolean(busy)} onClick={() => void deleteTool()} leftSection={<Trash2 />}>{deleteConfirm === `tool:${tool.id}` ? '再次点击删除' : '删除'}</Button>}<Button type="submit" disabled={Boolean(busy)} leftSection={busy === 'tool-save' ? <Loader2 className="spinning" /> : <Save />}>保存工具</Button></footer>
          </form>
        </div>
      </Tabs.Panel>
    </Tabs>
  </Dialog>
}
