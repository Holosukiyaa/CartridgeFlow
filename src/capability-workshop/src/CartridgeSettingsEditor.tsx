import { useEffect, useState } from 'react'
import { Settings2 } from 'lucide-react'
import { parseSettingOptions, type NodeSettingDraft } from './settingsPresentation'
import type { AnyRecord } from './model'

const typeLabels: Record<NodeSettingDraft['type'], string> = {
  string: '文本', integer: '整数', number: '数字', enum: '选项', boolean: '开关', file: '文件路径', array: '列表', object: '结构化数据',
}

function previewValue(draft: NodeSettingDraft, params: AnyRecord) {
  const value = params[draft.param]
  if (draft.sensitive) return ''
  return value === undefined || value === null ? '' : value
}

function PreviewControl({ draft, params }: { draft: NodeSettingDraft; params: AnyRecord }) {
  const initial = previewValue(draft, params)
  const initialKey = JSON.stringify(initial)
  const [value, setValue] = useState<unknown>(initial)
  useEffect(() => setValue(initial), [draft.param, draft.type, draft.sensitive, initialKey])
  if (draft.type === 'enum') return <select value={String(value)} onChange={(event) => setValue(event.currentTarget.value)} aria-label={draft.label}>{parseSettingOptions(draft.optionsText).map((option) => <option key={`${typeof option.value}:${String(option.value)}`} value={String(option.value)}>{option.label}</option>)}</select>
  if (draft.type === 'boolean') return <label className="settings-preview-toggle"><input type="checkbox" checked={Boolean(value)} onChange={(event) => setValue(event.currentTarget.checked)} /><span>{value ? '已开启' : '已关闭'}</span></label>
  if (draft.type === 'array' || draft.type === 'object') return <textarea value={typeof value === 'string' ? value : JSON.stringify(value, null, 2)} onChange={(event) => setValue(event.currentTarget.value)} rows={3} aria-label={draft.label} />
  return <input type={draft.sensitive ? 'password' : draft.type === 'integer' || draft.type === 'number' ? 'number' : 'text'} value={String(value)} onChange={(event) => setValue(event.currentTarget.value)} step={draft.type === 'integer' ? 1 : draft.type === 'number' ? 'any' : undefined} aria-label={draft.label} autoComplete={draft.sensitive ? 'new-password' : 'off'} />
}

export function CartridgeSettingsEditor({ drafts, params, errors, onChange }: {
  drafts: NodeSettingDraft[]
  params: AnyRecord
  errors: string[]
  onChange: (drafts: NodeSettingDraft[]) => void
}) {
  const update = (param: string, patch: Partial<NodeSettingDraft>) => onChange(drafts.map((item) => item.param === param ? { ...item, ...patch } : item))
  const exposed = drafts.filter((item) => item.exposed)
  return <section className="node-settings" aria-label="Desktop Runner 运行设置">
    <header><div><Settings2 /><strong>DR 运行设置</strong></div><small>{exposed.length} 个控件</small></header>
    {errors.map((error) => <p className="settings-contract-error" key={error}>{error}</p>)}
    {!errors.length && drafts.length === 0 && <p className="settings-empty">当前节点没有可公开的顶层参数。</p>}
    {!errors.length && drafts.map((draft) => <div className={`node-setting-row ${draft.exposed ? 'is-exposed' : ''}`} key={draft.param}>
      <label className="setting-exposure"><input type="checkbox" checked={draft.exposed} onChange={(event) => update(draft.param, { exposed: event.currentTarget.checked })} /><span><strong>{draft.param}</strong><small>{typeLabels[draft.type]}</small></span></label>
      {draft.exposed && <div className="setting-definition">
        <label><span>显示名称</span><input value={draft.label} onChange={(event) => update(draft.param, { label: event.currentTarget.value })} /></label>
        <label><span>控件类型</span><select value={draft.type} onChange={(event) => update(draft.param, { type: event.currentTarget.value as NodeSettingDraft['type'] })}>{Object.entries(typeLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        <label className="setting-description"><span>说明</span><input value={draft.description} onChange={(event) => update(draft.param, { description: event.currentTarget.value })} /></label>
        {draft.type === 'enum' && <label className="setting-options"><span>选项（每行“值 | 名称”）</span><textarea value={draft.optionsText} onChange={(event) => update(draft.param, { optionsText: event.currentTarget.value })} rows={3} /></label>}
        <div className="setting-flags"><label><input type="checkbox" checked={draft.required} onChange={(event) => update(draft.param, { required: event.currentTarget.checked })} />必填</label><label><input type="checkbox" checked={draft.sensitive} onChange={(event) => update(draft.param, { sensitive: event.currentTarget.checked })} />敏感值</label></div>
      </div>}
    </div>)}
    {exposed.length > 0 && <section className="settings-preview" data-settings-preview="dr-v1">
      <header><strong>Desktop Runner 预览</strong><span>cartridge_settings.v1</span></header>
      {exposed.map((draft) => <label className="settings-preview-field" key={draft.id}><span><strong>{draft.label || draft.param}</strong>{draft.description && <small>{draft.description}</small>}</span><PreviewControl draft={draft} params={params} /></label>)}
    </section>}
  </section>
}
