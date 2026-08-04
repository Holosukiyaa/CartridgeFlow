import { useEffect, useState } from 'react'
import { CheckCircle2, CircleAlert, Plus, Save } from 'lucide-react'
import { developerApi } from './api'
import type { AnyRecord } from './model'
import './TrustedPresetManager.css'

const protocol = { id: 'CF-TUNING', version: '1.4' }
const empty = { id: '', creator_label: '', creator_description: '', match_terms: '', developer_mapping_key: '', fields: '[\n  {"id":"topic","label":"关注主题","value_type":"string","required":true,"default":"AI"}\n]' }

export function TrustedPresetManager() {
  const [presets, setPresets] = useState<AnyRecord[]>([])
  const [form, setForm] = useState(empty)
  const [revision, setRevision] = useState(0)
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')
  const load = () => developerApi.trustedPresets().then(({ presets }) => setPresets(presets)).catch((reason) => setError(reason instanceof Error ? reason.message : 'Unable to load trusted presets.'))
  useEffect(() => { void load() }, [])
  const select = (preset: AnyRecord) => { setRevision(Number(preset.revision)); setForm({ id: String(preset.id), creator_label: String(preset.creator_label), creator_description: String(preset.creator_description), match_terms: (preset.match_terms as unknown[]).join('\n'), developer_mapping_key: String(preset.developer_mapping_key), fields: JSON.stringify(preset.editable_fields, null, 2) }); setNotice(''); setError('') }
  const reset = () => { setRevision(0); setForm(empty); setNotice(''); setError('') }
  const save = async () => {
    setError(''); setNotice('')
    try {
      const fields = JSON.parse(form.fields)
      const preset = { schema: 'cartridgeflow.trusted_node_preset.v1', protocol, id: form.id.trim(), revision: revision + 1, creator_label: form.creator_label.trim(), creator_description: form.creator_description.trim(), match_terms: form.match_terms.split('\n').map((item) => item.trim()).filter(Boolean), editable_fields: fields, developer_mapping_key: form.developer_mapping_key.trim() }
      const result = await developerApi.putTrustedPreset(preset.id, preset, revision)
      await load(); select(result.preset as AnyRecord); setNotice(`Saved ${String((result.preset as AnyRecord).id)} revision ${String((result.preset as AnyRecord).revision)}.`)
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Unable to save trusted preset.') }
  }
  return <section className="preset-manager"><div className="preset-list"><h2>可信节点预设</h2><button onClick={reset}><Plus size={15}/>新增</button>{presets.length ? presets.map((preset) => <button key={String(preset.id)} className={form.id === preset.id ? 'active' : ''} onClick={() => select(preset)}><span>{String(preset.creator_label)}</span><small>{String(preset.id)} · r{String(preset.revision)}</small></button>) : <p>尚未注册可信节点。</p>}</div><div className="preset-editor"><h2>{revision ? `修订 ${form.id}` : '新增可信节点'}</h2>{error && <p className="error"><CircleAlert size={15}/>{error}</p>}{notice && <p className="notice"><CheckCircle2 size={15}/>{notice}</p>}<div className="preset-fields"><label>Preset ID<input value={form.id} disabled={revision > 0} onChange={(event) => setForm({ ...form, id: event.target.value })}/></label><label>Creator 名称<input value={form.creator_label} onChange={(event) => setForm({ ...form, creator_label: event.target.value })}/></label><label>Creator 说明<input value={form.creator_description} onChange={(event) => setForm({ ...form, creator_description: event.target.value })}/></label><label>Developer mapping key<input value={form.developer_mapping_key} onChange={(event) => setForm({ ...form, developer_mapping_key: event.target.value })}/></label><label>匹配词（每行一个）<textarea value={form.match_terms} onChange={(event) => setForm({ ...form, match_terms: event.target.value })}/></label><label>Creator 可编辑字段 JSON<textarea value={form.fields} onChange={(event) => setForm({ ...form, fields: event.target.value })}/></label></div><button onClick={save} disabled={!form.id.trim() || !form.creator_label.trim() || !form.creator_description.trim() || !form.developer_mapping_key.trim()}><Save size={15}/>保存新修订</button></div></section>
}
