import { useEffect, useMemo, useState } from 'react'
import {
  deleteCartridgeAsset,
  deleteInteractionComponent,
  fetchCartridgeAssets,
  saveCartridgeAsset,
  saveInteractionComponent,
  type CartridgeAsset,
  type FlowFiles,
  type InteractionComponent,
} from '../../api.ts'
import { showToast } from '../../toast.tsx'
import { passiveHtmlDocument } from './passiveHtml.ts'

const ASSET_KINDS = [
  'interaction_template', 'prompt', 'model_recipe', 'flow', 'schema',
  'motion_template', 'style', 'media', 'fixture',
]

const KIND_LABELS: Record<string, string> = {
  interaction_template: '交互界面',
  prompt: '提示词',
  model_recipe: '模型配方',
  flow: '子流程',
  schema: '数据结构',
  motion_template: '动效模板',
  style: '样式',
  media: '媒体素材',
  fixture: '测试样本',
}

type AssetDraft = Pick<CartridgeAsset, 'id' | 'kind' | 'path' | 'media_type'> & { content: string; encoding: string }

function draftFromAsset(asset: CartridgeAsset): AssetDraft {
  return {
    id: asset.id,
    kind: asset.kind,
    path: asset.path,
    media_type: asset.media_type,
    content: asset.content || '',
    encoding: asset.encoding || 'utf-8',
  }
}

function newAssetDraft(): AssetDraft {
  return {
    id: 'asset.new',
    kind: 'prompt',
    path: 'assets/new.md',
    media_type: 'text/markdown',
    content: '# New asset\n',
    encoding: 'utf-8',
  }
}

function newComponent(): InteractionComponent {
  return {
    id: 'component.new',
    version: '1.0.0',
    runtime: 'passive',
    entry: { type: 'asset', ref: 'asset:ui.welcome' },
    supported_modes: ['display'],
    input_schema: { type: 'object' },
    actions: [],
    host_capabilities: [],
  }
}

function materializeAssetRefs(content: string, assets: CartridgeAsset[]) {
  return content.replace(/asset:([a-zA-Z0-9._-]+)/g, (reference, assetId) => {
    const asset = assets.find((item) => item.id === assetId)
    if (!asset?.content) return reference
    const encoded = asset.encoding === 'base64'
      ? asset.content
      : window.btoa(unescape(encodeURIComponent(asset.content)))
    return `data:${asset.media_type};base64,${encoded}`
  })
}

export function AssetWorkbench({ flowId, editable, available = true, onFilesChange }: {
  flowId: string
  editable: boolean
  available?: boolean
  onFilesChange: (files: FlowFiles) => void
}) {
  const [assets, setAssets] = useState<CartridgeAsset[]>([])
  const [components, setComponents] = useState<InteractionComponent[]>([])
  const [tab, setTab] = useState<'assets' | 'components'>('assets')
  const [selectedAssetId, setSelectedAssetId] = useState('')
  const [assetDraft, setAssetDraft] = useState<AssetDraft | null>(null)
  const [selectedComponentId, setSelectedComponentId] = useState('')
  const [componentText, setComponentText] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  const load = async (preferredAsset = '', preferredComponent = '') => {
    setLoading(true)
    try {
      const result = await fetchCartridgeAssets(flowId)
      setAssets(result.assets)
      setComponents(result.components)
      onFilesChange(result.files)
      const asset = result.assets.find((item) => item.id === preferredAsset)
        || result.assets.find((item) => item.id === selectedAssetId)
        || result.assets[0]
      setSelectedAssetId(asset?.id || '')
      setAssetDraft(asset ? draftFromAsset(asset) : null)
      const component = result.components.find((item) => item.id === preferredComponent)
        || result.components.find((item) => item.id === selectedComponentId)
        || result.components[0]
      setSelectedComponentId(component?.id || '')
      setComponentText(component ? JSON.stringify(component, null, 2) : '')
    } catch (error: any) {
      showToast({ title: '读取卡带资产失败', description: error.message, type: 'error' })
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { if (available) void load() }, [flowId, available])

  const selectedAsset = useMemo(
    () => assets.find((item) => item.id === selectedAssetId),
    [assets, selectedAssetId],
  )

  if (!available) {
    return (
      <section className="cf-assets-workbench cf-assets-unavailable">
        <div className="cf-assets-unavailable-copy">
          <span className="cf-kicker">Cartridge Assets</span>
          <h2>这个 Flow 还没有 v0.7 资产区</h2>
          <p>旧协议继续保留原有运行方式。要使用交互组件、稳定资产 ID 和 Host 动作控制，请先把 Flow 迁移到 CF-FARP@0.7。</p>
          <code>当前工作区只读 · 不会自动改写旧协议</code>
        </div>
      </section>
    )
  }

  const chooseAsset = (asset: CartridgeAsset) => {
    setSelectedAssetId(asset.id)
    setAssetDraft(draftFromAsset(asset))
  }

  const chooseComponent = (component: InteractionComponent) => {
    setSelectedComponentId(component.id)
    setComponentText(JSON.stringify(component, null, 2))
  }

  const saveAsset = async () => {
    if (!assetDraft || !editable) return
    setSaving(true)
    try {
      const result = await saveCartridgeAsset(flowId, assetDraft.id, assetDraft)
      onFilesChange(result.files)
      await load(assetDraft.id)
      showToast({ title: '资产已保存', type: 'success' })
    } catch (error: any) {
      showToast({ title: '资产保存失败', description: error.message, type: 'error' })
    } finally {
      setSaving(false)
    }
  }

  const pickMedia = (file?: File) => {
    if (!file || !assetDraft) return
    const reader = new FileReader()
    reader.onload = () => {
      const value = String(reader.result || '')
      const content = value.includes(',') ? value.split(',')[1] : value
      setAssetDraft({
        ...assetDraft,
        kind: 'media',
        path: `assets/${file.name}`,
        media_type: file.type || 'application/octet-stream',
        content,
        encoding: 'base64',
      })
    }
    reader.readAsDataURL(file)
  }

  const removeAsset = async () => {
    if (!selectedAsset || !editable || !window.confirm(`删除资产 ${selectedAsset.id}？`)) return
    try {
      const result = await deleteCartridgeAsset(flowId, selectedAsset.id)
      onFilesChange(result.files)
      await load()
      showToast({ title: '资产已删除', type: 'success' })
    } catch (error: any) {
      showToast({ title: '无法删除资产', description: error.message, type: 'error' })
    }
  }

  const saveComponent = async () => {
    if (!editable) return
    setSaving(true)
    try {
      const component = JSON.parse(componentText) as InteractionComponent
      if (!component.id) throw new Error('组件 id 不能为空')
      const result = await saveInteractionComponent(flowId, component.id, component)
      onFilesChange(result.files)
      await load('', component.id)
      showToast({ title: '交互组件已保存', type: 'success' })
    } catch (error: any) {
      showToast({ title: '组件保存失败', description: error.message, type: 'error' })
    } finally {
      setSaving(false)
    }
  }

  const removeComponent = async () => {
    if (!selectedComponentId || !editable || !window.confirm(`删除组件 ${selectedComponentId}？`)) return
    try {
      const result = await deleteInteractionComponent(flowId, selectedComponentId)
      onFilesChange(result.files)
      await load()
      showToast({ title: '交互组件已删除', type: 'success' })
    } catch (error: any) {
      showToast({ title: '无法删除组件', description: error.message, type: 'error' })
    }
  }

  if (loading) return <div className="cf-assets-loading">正在读取卡带资产...</div>

  return (
    <section className="cf-assets-workbench">
      <header className="cf-assets-summary">
        <div>
          <span className="cf-kicker">Cartridge Assets</span>
          <h2>卡带资产</h2>
          <p>Flow 通过稳定 ID 使用提示词、配方、动效、媒体和交互界面；这些内容跟随卡带一起迁移。</p>
        </div>
        <div className="cf-assets-counters">
          <span><b>{assets.length}</b> 份资产</span>
          <span><b>{components.length}</b> 个组件</span>
          <span className="safe">被动 HTML 已启用</span>
        </div>
      </header>

      <div className="cf-assets-tabs" role="tablist">
        <button className={tab === 'assets' ? 'active' : ''} onClick={() => setTab('assets')}>资产库</button>
        <button className={tab === 'components' ? 'active' : ''} onClick={() => setTab('components')}>交互组件</button>
      </div>

      {tab === 'assets' ? (
        <div className="cf-assets-layout">
          <aside className="cf-assets-list">
            <div className="cf-assets-list-head">
              <strong>卡带内容</strong>
              {editable && <button onClick={() => { const draft = newAssetDraft(); setSelectedAssetId(''); setAssetDraft(draft) }}>新建</button>}
            </div>
            <div className="cf-assets-scroll">
              {assets.map((asset) => (
                <button key={asset.id} className={selectedAssetId === asset.id ? 'active' : ''} onClick={() => chooseAsset(asset)}>
                  <span>{KIND_LABELS[asset.kind] || asset.kind}</span>
                  <strong>{asset.id}</strong>
                  <small>{asset.path}</small>
                </button>
              ))}
            </div>
          </aside>

          {assetDraft ? (
            <div className="cf-asset-editor">
              <div className="cf-asset-fields">
                <label><span>稳定 ID</span><input disabled={Boolean(selectedAssetId)} value={assetDraft.id} onChange={(event) => setAssetDraft({ ...assetDraft, id: event.target.value })} /></label>
                <label><span>类型</span><select value={assetDraft.kind} onChange={(event) => setAssetDraft({ ...assetDraft, kind: event.target.value })}>{ASSET_KINDS.map((kind) => <option key={kind} value={kind}>{KIND_LABELS[kind] || kind}</option>)}</select></label>
                <label><span>包内路径</span><input value={assetDraft.path} onChange={(event) => setAssetDraft({ ...assetDraft, path: event.target.value })} /></label>
                <label><span>媒体类型</span><input value={assetDraft.media_type} onChange={(event) => setAssetDraft({ ...assetDraft, media_type: event.target.value })} /></label>
                {assetDraft.kind === 'media' && <label className="cf-asset-file-field"><span>选择媒体文件</span><input type="file" onChange={(event) => pickMedia(event.target.files?.[0])} /></label>}
              </div>
              <textarea className="cf-asset-code" spellCheck={false} value={assetDraft.content} onChange={(event) => setAssetDraft({ ...assetDraft, content: event.target.value, encoding: 'utf-8' })} />
              <div className="cf-asset-actions">
                <span>{selectedAsset ? `${selectedAsset.size} bytes · ${selectedAsset.sha256.slice(0, 12)}` : '尚未写入卡带'}</span>
                {selectedAsset && editable && <button className="danger" onClick={removeAsset}>删除</button>}
                {editable && <button className="primary" disabled={saving} onClick={saveAsset}>{saving ? '保存中...' : '保存资产'}</button>}
              </div>
            </div>
          ) : <div className="cf-assets-empty">卡带内还没有资产</div>}

          <aside className="cf-asset-preview">
            <div className="cf-asset-preview-head"><strong>安全预览</strong><span>脚本禁用</span></div>
            {assetDraft?.media_type === 'text/html' ? (
              <iframe title="asset preview" sandbox="" srcDoc={passiveHtmlDocument(materializeAssetRefs(assetDraft.content, assets))} />
            ) : assetDraft?.media_type.startsWith('image/') && assetDraft.encoding === 'base64' ? (
              <img src={`data:${assetDraft.media_type};base64,${assetDraft.content}`} alt={assetDraft.id} />
            ) : (
              <pre>{assetDraft?.content || '选择资产后在这里预览'}</pre>
            )}
          </aside>
        </div>
      ) : (
        <div className="cf-components-layout">
          <aside className="cf-assets-list">
            <div className="cf-assets-list-head"><strong>组件注册表</strong>{editable && <button onClick={() => { const item = newComponent(); setSelectedComponentId(''); setComponentText(JSON.stringify(item, null, 2)) }}>新建</button>}</div>
            <div className="cf-assets-scroll">
              {components.map((component) => (
                <button key={component.id} className={selectedComponentId === component.id ? 'active' : ''} onClick={() => chooseComponent(component)}>
                  <span>{component.supported_modes.join(' / ')}</span>
                  <strong>{component.id}</strong>
                  <small>{component.runtime} · v{component.version}</small>
                </button>
              ))}
            </div>
          </aside>
          <div className="cf-component-editor">
            <div className="cf-component-note"><strong>Host 控制动作</strong><p>组件描述界面与动作，但最终按钮、Schema 校验和 Flow 路由都由底座执行。</p></div>
            <textarea spellCheck={false} value={componentText} onChange={(event) => setComponentText(event.target.value)} />
            <div className="cf-asset-actions">
              <span>当前底座只接受 runtime=passive</span>
              {selectedComponentId && editable && <button className="danger" onClick={removeComponent}>删除</button>}
              {editable && <button className="primary" disabled={saving} onClick={saveComponent}>{saving ? '保存中...' : '保存组件'}</button>}
            </div>
          </div>
          <aside className="cf-component-map">
            <strong>组件怎样进入 Flow</strong>
            <ol>
              <li>界面文件登记为交互界面资产</li>
              <li>组件引用资产稳定 ID</li>
              <li>交互节点引用组件 ID</li>
              <li>底座按命名动作恢复 Flow</li>
            </ol>
          </aside>
        </div>
      )}
    </section>
  )
}
