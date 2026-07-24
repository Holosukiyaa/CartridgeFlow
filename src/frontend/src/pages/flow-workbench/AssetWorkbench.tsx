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

const MODE_LABELS: Record<InteractionComponent['supported_modes'][number], string> = {
  display: '展示',
  collect: '收集',
  review: '审核',
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
  const [tab, setTab] = useState<'assets' | 'components'>('components')
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
  const componentDraft = useMemo(() => {
    try {
      return JSON.parse(componentText) as InteractionComponent
    } catch {
      return null
    }
  }, [componentText])
  const componentEntryAsset = useMemo(() => {
    const ref = componentDraft?.entry?.ref || ''
    return assets.find((item) => `asset:${item.id}` === ref)
  }, [assets, componentDraft])

  const updateComponent = (patch: Partial<InteractionComponent>) => {
    if (!componentDraft || !editable) return
    setComponentText(JSON.stringify({ ...componentDraft, ...patch }, null, 2))
  }

  if (!available) {
    return (
      <section className="cf-assets-workbench cf-assets-unavailable">
        <div className="cf-assets-unavailable-copy">
          <span className="cf-kicker">Interaction Nodes</span>
          <h2>这个 Flow 还没有交互节点能力</h2>
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
          <span className="cf-kicker">Interaction Nodes</span>
          <h2>交互节点</h2>
          <p>配置卡带里的交互组件，以及组件依赖的界面、提示词和媒体素材。它们会随卡带一起迁移。</p>
        </div>
        <div className="cf-assets-counters">
          <span><b>{components.length}</b> 个组件</span>
          <span><b>{assets.length}</b> 份节点素材</span>
          <span className="safe">被动运行</span>
        </div>
      </header>

      <div className="cf-assets-tabs" role="tablist">
        <button className={tab === 'components' ? 'active' : ''} onClick={() => setTab('components')}>交互组件</button>
        <button className={tab === 'assets' ? 'active' : ''} onClick={() => setTab('assets')}>节点素材</button>
      </div>

      {tab === 'assets' ? (
        <div className="cf-assets-layout">
          <aside className="cf-assets-list">
            <div className="cf-assets-list-head">
              <strong>节点素材</strong>
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
          {componentDraft ? (
            <div className="cf-component-editor">
              <div className="cf-component-form-scroll">
                <div className="cf-component-note">
                  <div><strong>组件由底座托管</strong><p>界面只负责展示和发出命名动作，数据校验与 Flow 路由仍由底座执行。</p></div>
                  <span>runtime · passive</span>
                </div>

                <section className="cf-component-section">
                  <div className="cf-component-section-head"><span>基础信息</span><small>用于节点引用的稳定身份</small></div>
                  <div className="cf-component-fields">
                    <label><span>组件 ID</span><input disabled={Boolean(selectedComponentId) || !editable} value={componentDraft.id || ''} onChange={(event) => updateComponent({ id: event.target.value })} /></label>
                    <label><span>版本</span><input disabled={!editable} value={componentDraft.version || ''} onChange={(event) => updateComponent({ version: event.target.value })} /></label>
                    <label className="wide"><span>入口界面</span><select disabled={!editable} value={componentDraft.entry?.ref || ''} onChange={(event) => updateComponent({ entry: { type: 'asset', ref: event.target.value } })}>
                      <option value="">请选择交互界面素材</option>
                      {assets.map((asset) => <option key={asset.id} value={`asset:${asset.id}`}>{asset.id} · {KIND_LABELS[asset.kind] || asset.kind}</option>)}
                    </select></label>
                  </div>
                </section>

                <section className="cf-component-section">
                  <div className="cf-component-section-head"><span>交互模式</span><small>决定节点可以怎样使用这个组件</small></div>
                  <div className="cf-component-mode-grid">
                    {(Object.keys(MODE_LABELS) as Array<InteractionComponent['supported_modes'][number]>).map((mode) => {
                      const checked = componentDraft.supported_modes?.includes(mode)
                      return <label key={mode} className={checked ? 'active' : ''}>
                        <input
                          type="checkbox"
                          disabled={!editable}
                          checked={Boolean(checked)}
                          onChange={() => updateComponent({
                            supported_modes: checked
                              ? componentDraft.supported_modes.filter((item) => item !== mode)
                              : [...(componentDraft.supported_modes || []), mode],
                          })}
                        />
                        <b>{MODE_LABELS[mode]}</b>
                        <span>{mode === 'display' ? '只展示内容' : mode === 'collect' ? '接收用户输入' : '提交审核结论'}</span>
                      </label>
                    })}
                  </div>
                </section>

                <section className="cf-component-section">
                  <div className="cf-component-section-head">
                    <span>命名动作</span>
                    {editable && <button type="button" onClick={() => updateComponent({ actions: [...(componentDraft.actions || []), { id: `action_${(componentDraft.actions || []).length + 1}`, label: '新动作' }] })}>添加动作</button>}
                  </div>
                  <div className="cf-component-actions-list">
                    {(componentDraft.actions || []).map((action, index) => (
                      <div key={`${action.id}-${index}`}>
                        <input aria-label="动作 ID" disabled={!editable} value={action.id} placeholder="action_id" onChange={(event) => updateComponent({ actions: componentDraft.actions.map((item, itemIndex) => itemIndex === index ? { ...item, id: event.target.value } : item) })} />
                        <input aria-label="动作名称" disabled={!editable} value={action.label || ''} placeholder="按钮名称" onChange={(event) => updateComponent({ actions: componentDraft.actions.map((item, itemIndex) => itemIndex === index ? { ...item, label: event.target.value } : item) })} />
                        {editable && <button type="button" aria-label="删除动作" title="删除动作" onClick={() => updateComponent({ actions: componentDraft.actions.filter((_, itemIndex) => itemIndex !== index) })}>×</button>}
                      </div>
                    ))}
                    {!componentDraft.actions?.length && <p>展示型组件可以不配置动作；需要继续 Flow 时再添加。</p>}
                  </div>
                </section>

                <details className="cf-component-advanced">
                  <summary><span>高级配置</span><small>输入 Schema、Host 能力与原始 JSON</small></summary>
                  <div className="cf-component-advanced-body">
                    <label><span>输入 Schema JSON</span><textarea
                      key={`${componentDraft.id}-${selectedComponentId}-schema`}
                      spellCheck={false}
                      defaultValue={JSON.stringify(componentDraft.input_schema || { type: 'object' }, null, 2)}
                      onBlur={(event) => {
                        try {
                          updateComponent({ input_schema: JSON.parse(event.target.value) })
                        } catch (error: any) {
                          showToast({ title: '输入 Schema 无法解析', description: error.message, type: 'error' })
                        }
                      }}
                    /></label>
                    <label><span>Host 能力（逗号分隔）</span><input disabled={!editable} value={(componentDraft.host_capabilities || []).join(', ')} onChange={(event) => updateComponent({ host_capabilities: event.target.value.split(',').map((item) => item.trim()).filter(Boolean) })} /></label>
                    <label><span>完整组件 JSON</span><textarea className="raw" spellCheck={false} disabled={!editable} value={componentText} onChange={(event) => setComponentText(event.target.value)} /></label>
                  </div>
                </details>
              </div>
              <div className="cf-asset-actions">
                <span>{selectedComponentId ? `已登记 · ${componentDraft.id}` : '尚未写入卡带'}</span>
                {selectedComponentId && editable && <button className="danger" onClick={removeComponent}>删除组件</button>}
                {editable && <button className="primary" disabled={saving} onClick={saveComponent}>{saving ? '保存中...' : '保存组件'}</button>}
              </div>
            </div>
          ) : <div className="cf-component-invalid-editor">
            <div><strong>组件 JSON 无法解析</strong><span>修正下面的内容后，表单会自动恢复。</span></div>
            <textarea spellCheck={false} value={componentText} onChange={(event) => setComponentText(event.target.value)} />
            <div className="cf-asset-actions"><span>当前内容尚未保存</span><button onClick={() => selectedComponentId ? chooseComponent(components.find((item) => item.id === selectedComponentId)!) : setComponentText(JSON.stringify(newComponent(), null, 2))}>还原</button></div>
          </div>}
          <aside className="cf-component-inspector">
            <div className="cf-asset-preview-head"><strong>组件预览</strong><span>脚本禁用</span></div>
            <div className="cf-component-preview-stage">
              {componentEntryAsset?.media_type === 'text/html' ? (
                <iframe title="component preview" sandbox="" srcDoc={passiveHtmlDocument(materializeAssetRefs(componentEntryAsset.content || '', assets))} />
              ) : componentEntryAsset?.media_type.startsWith('image/') && componentEntryAsset.encoding === 'base64' ? (
                <img src={`data:${componentEntryAsset.media_type};base64,${componentEntryAsset.content}`} alt={componentEntryAsset.id} />
              ) : (
                <div className="cf-component-preview-empty"><b>{componentEntryAsset ? '当前素材不支持画面预览' : '还没有绑定入口界面'}</b><span>{componentEntryAsset?.id || '请在中间选择一份节点素材'}</span></div>
              )}
            </div>
            <div className="cf-component-health">
              <span>依赖状态</span>
              <div className={componentEntryAsset ? 'ok' : 'warn'}><b>{componentEntryAsset ? '入口素材可用' : '缺少入口素材'}</b><small>{componentEntryAsset?.path || componentDraft?.entry?.ref || '未绑定'}</small></div>
              <div className="ok"><b>被动运行</b><small>脚本不会直接控制 Flow</small></div>
              <div><b>{componentDraft?.supported_modes?.length || 0} 种模式 · {componentDraft?.actions?.length || 0} 个动作</b><small>由节点选择具体运行方式</small></div>
            </div>
          </aside>
        </div>
      )}
    </section>
  )
}
