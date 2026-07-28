import { useEffect, useMemo, useState } from 'react'
import { Code2, Eye, FilePlus2, Plus, RefreshCw, Save, Trash2 } from 'lucide-react'
import { fetchCartridgeAssets, saveCartridgeAsset, saveInteractionComponent, type CartridgeAsset, type FlowFiles, type InteractionComponent } from '../../api.ts'
import { showToast } from '../../toast.tsx'
import { passiveHtmlDocument } from './passiveHtml.ts'

type AssetDraft = { id: string; path: string; mediaType: string; content: string }
type ActionDraft = { id: string; label: string; payloadSchema: string }

const defaultSource = `<main>\n  <h1>卡带界面</h1>\n  <p>在这里编写 HTML，运行时会作为交互组件加载。</p>\n</main>\n`

export function InteractionAssetEditor({ flowId, componentRef, onComponentRefChange, onFilesChange }: {
  flowId: string
  componentRef: string
  onComponentRefChange: (componentRef: string) => void
  onFilesChange: (files: FlowFiles) => void
}) {
  const [components, setComponents] = useState<InteractionComponent[]>([])
  const [assets, setAssets] = useState<CartridgeAsset[]>([])
  const [selectedId, setSelectedId] = useState(componentRef)
  const [component, setComponent] = useState<InteractionComponent | null>(null)
  const [asset, setAsset] = useState<AssetDraft | null>(null)
  const [actions, setActions] = useState<ActionDraft[]>([])
  const [assetView, setAssetView] = useState<'source' | 'preview'>('source')
  const [busy, setBusy] = useState(false)

  const load = async (preferredId = componentRef) => {
    setBusy(true)
    try {
      const result = await fetchCartridgeAssets(flowId)
      setComponents(result.components || [])
      setAssets(result.assets || [])
      onFilesChange(result.files || {})
      const nextId = preferredId || result.components?.[0]?.id || ''
      selectComponent(nextId, result.components || [], result.assets || [])
    } catch (error: any) {
      showToast({ title: '读取交互资产失败', description: error.message, type: 'error' })
    } finally {
      setBusy(false)
    }
  }

  useEffect(() => { void load() }, [flowId])

  const selectComponent = (id: string, sourceComponents = components, sourceAssets = assets) => {
    setSelectedId(id)
    const selected = sourceComponents.find((item) => item.id === id) || null
    setComponent(selected ? JSON.parse(JSON.stringify(selected)) : null)
    setActions((selected?.actions || []).map((item) => ({ id: item.id, label: item.label || '', payloadSchema: item.payload_schema ? JSON.stringify(item.payload_schema, null, 2) : '' })))
    const assetRef = selected?.entry?.ref || ''
    const selectedAsset = sourceAssets.find((item) => item.id === assetRef || item.path === assetRef)
    setAsset(selectedAsset ? { id: selectedAsset.id, path: selectedAsset.path, mediaType: selectedAsset.media_type, content: selectedAsset.content || '' } : null)
    if (id) onComponentRefChange(id)
  }

  const createDraft = () => {
    const base = `component_${Date.now().toString(36)}`
    const assetId = `${base}_view`
    const next: InteractionComponent = { id: base, version: '1.0.0', runtime: 'passive', entry: { type: 'asset', ref: assetId }, supported_modes: ['display'], actions: [] }
    setSelectedId(base)
    setComponent(next)
    setActions([])
    setAsset({ id: assetId, path: `assets/${base}.html`, mediaType: 'text/html', content: defaultSource })
    onComponentRefChange(base)
  }

  const save = async () => {
    if (!component || !asset || !component.id.trim() || !asset.id.trim() || !asset.path.trim()) return
    let normalizedActions: InteractionComponent['actions']
    try {
      const ids = actions.map((item) => item.id.trim())
      if (ids.some((id) => !id)) throw new Error('命名动作 ID 不能为空')
      if (new Set(ids).size !== ids.length) throw new Error('命名动作 ID 不能重复')
      normalizedActions = actions.map((item) => ({
        id: item.id.trim(),
        ...(item.label.trim() ? { label: item.label.trim() } : {}),
        ...(item.payloadSchema.trim() ? { payload_schema: JSON.parse(item.payloadSchema) } : {}),
      }))
    } catch (error: any) {
      showToast({ title: '命名动作配置无效', description: error.message, type: 'error' })
      return
    }
    setBusy(true)
    try {
      const assetResult = await saveCartridgeAsset(flowId, asset.id, { id: asset.id, kind: 'interaction_view', path: asset.path, media_type: asset.mediaType, content: asset.content, encoding: 'utf-8' })
      const nextComponent = { ...component, id: component.id.trim(), entry: { type: 'asset' as const, ref: asset.id }, actions: normalizedActions }
      const componentResult = await saveInteractionComponent(flowId, nextComponent.id, nextComponent)
      onFilesChange(componentResult.files || assetResult.files)
      onComponentRefChange(nextComponent.id)
      await load(nextComponent.id)
      showToast({ title: '交互组件与页面资产已保存', type: 'success' })
    } catch (error: any) {
      showToast({ title: '交互资产保存失败', description: error.message, type: 'error' })
    } finally {
      setBusy(false)
    }
  }

  const modes = useMemo(() => new Set(component?.supported_modes || []), [component?.supported_modes])
  const previewDocument = useMemo(() => {
    if (!asset) return ''
    if (asset.mediaType === 'text/html') return passiveHtmlDocument(asset.content)
    const escaped = asset.content.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    return passiveHtmlDocument(`<pre style="white-space:pre-wrap;font:14px/1.6 system-ui,sans-serif;padding:16px;margin:0">${escaped}</pre>`)
  }, [asset])
  const toggleMode = (mode: 'display' | 'collect' | 'review') => {
    if (!component) return
    const next = new Set(modes)
    if (next.has(mode)) next.delete(mode); else next.add(mode)
    if (!next.size) next.add('display')
    setComponent({ ...component, supported_modes: [...next] })
  }

  return <section className="cf-interaction-asset-editor">
    <header><span><Code2 /><b>组件与页面资产</b></span><div><button type="button" onClick={() => void load(selectedId)} title="刷新" disabled={busy}><RefreshCw /></button><button type="button" onClick={createDraft}><FilePlus2 />新建</button></div></header>
    <label className="cf-satellite-field"><span>组件</span><select value={selectedId} onChange={(event) => selectComponent(event.target.value)}><option value="">未选择</option>{components.map((item) => <option key={item.id} value={item.id}>{item.id}</option>)}</select></label>
    {component && asset && <>
      <div className="cf-satellite-field-grid"><label className="cf-satellite-field mono"><span>组件 ID</span><input value={component.id} disabled={components.some((item) => item.id === selectedId)} onChange={(event) => setComponent({ ...component, id: event.target.value })} /></label><label className="cf-satellite-field"><span>运行时</span><select value={component.runtime} onChange={(event) => setComponent({ ...component, runtime: event.target.value as 'passive' | 'sandboxed' })}><option value="passive">Passive</option><option value="sandboxed">Sandboxed</option></select></label></div>
      <div className="cf-interaction-modes">{(['display', 'collect', 'review'] as const).map((mode) => <label key={mode}><input type="checkbox" checked={modes.has(mode)} onChange={() => toggleMode(mode)} /><span>{mode}</span></label>)}</div>
      <div className="cf-satellite-field-grid"><label className="cf-satellite-field mono"><span>资产 ID</span><input value={asset.id} disabled={assets.some((item) => item.id === asset.id)} onChange={(event) => setAsset({ ...asset, id: event.target.value })} /></label><label className="cf-satellite-field mono"><span>文件路径</span><input value={asset.path} onChange={(event) => setAsset({ ...asset, path: event.target.value })} /></label></div>
      <label className="cf-satellite-field"><span>内容类型</span><select value={asset.mediaType} onChange={(event) => setAsset({ ...asset, mediaType: event.target.value })}><option value="text/html">HTML</option><option value="text/markdown">Markdown</option><option value="text/plain">Text</option></select></label>
      <div className="cf-interaction-asset-tabs" role="tablist" aria-label="页面资产视图"><button type="button" className={assetView === 'source' ? 'active' : ''} onClick={() => setAssetView('source')}><Code2 />源码</button><button type="button" className={assetView === 'preview' ? 'active' : ''} onClick={() => setAssetView('preview')}><Eye />预览</button></div>
      {assetView === 'source' ? <label className="cf-satellite-field mono"><span>页面源码</span><textarea className="cf-interaction-source" rows={10} value={asset.content} onChange={(event) => setAsset({ ...asset, content: event.target.value })} /></label> : <iframe className="cf-interaction-asset-preview" title={`${component.id} 页面预览`} sandbox="" srcDoc={previewDocument} />}
      <section className="cf-interaction-actions-editor">
        <header><div><strong>命名动作</strong><small>运行时由 Host 在组件外提交</small></div><button type="button" onClick={() => setActions((current) => [...current, { id: `action_${current.length + 1}`, label: '', payloadSchema: '' }])}><Plus />添加</button></header>
        {actions.map((action, index) => <article key={`${index}-${action.id}`}>
          <div><label className="cf-satellite-field mono"><span>动作 ID</span><input value={action.id} onChange={(event) => setActions((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, id: event.target.value } : item))} /></label><label className="cf-satellite-field"><span>显示名称</span><input value={action.label} onChange={(event) => setActions((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, label: event.target.value } : item))} /></label><button type="button" onClick={() => setActions((current) => current.filter((_, itemIndex) => itemIndex !== index))} title="删除动作"><Trash2 /></button></div>
          <label className="cf-satellite-field mono"><span>Payload Schema JSON（可选）</span><textarea rows={3} value={action.payloadSchema} onChange={(event) => setActions((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, payloadSchema: event.target.value } : item))} placeholder='{"type":"object"}' /></label>
        </article>)}
        {!actions.length && <p>展示模式可以没有动作；收集和审核模式至少声明一个动作。</p>}
      </section>
      <button type="button" className="cf-interaction-asset-save" disabled={busy} onClick={() => void save()}><Save />{busy ? '保存中' : '保存组件与资产'}</button>
    </>}
  </section>
}
