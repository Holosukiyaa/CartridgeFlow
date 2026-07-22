import { useEffect, useMemo, useState } from 'react'
import {
  createStudioCredential,
  deleteStudioCredential,
  fetchLlmProviders,
  fetchStudioEnvironment,
  updateStudioCredential,
  type LlmProvider,
  type StudioEnvironmentSnapshot,
} from '../api.ts'
import ConfigModal from '../components/ConfigModal.tsx'

type CredentialDraft = { key: string; label: string; value: string; secret: boolean }
const EMPTY_DRAFT: CredentialDraft = { key: '', label: '', value: '', secret: true }

export default function EnvironmentPage({ embedded = false }: { embedded?: boolean }) {
  const [snapshot, setSnapshot] = useState<StudioEnvironmentSnapshot | null>(null)
  const [providers, setProviders] = useState<LlmProvider[]>([])
  const [selectedKey, setSelectedKey] = useState('')
  const [draft, setDraft] = useState<CredentialDraft>(EMPTY_DRAFT)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [editorOpen, setEditorOpen] = useState(false)

  const selectedCredential = snapshot?.credentials.find((item) => item.key === selectedKey)
  const entries = useMemo(() => {
    if (!snapshot) return []
    const byKey = new Map(snapshot.references.map((reference) => [reference.key, { ...reference, credential: snapshot.credentials.find((item) => item.key === reference.key) }]))
    for (const credential of snapshot.credentials) {
      if (!byKey.has(credential.key)) byKey.set(credential.key, { key: credential.key, label: credential.label, owners: ['本机自定义'], configured: credential.has_value, credential })
    }
    return [...byKey.values()].sort((a, b) => Number(Boolean(b.credential)) - Number(Boolean(a.credential)) || a.key.localeCompare(b.key))
  }, [snapshot])

  async function load(preferredKey = selectedKey) {
    setLoading(true)
    setError('')
    try {
      const [environmentResult, providerResult] = await Promise.all([fetchStudioEnvironment(), fetchLlmProviders()])
      setSnapshot(environmentResult)
      setProviders(providerResult.providers || [])
      if (preferredKey) {
        const credential = environmentResult.credentials.find((item) => item.key === preferredKey)
        const reference = environmentResult.references.find((item) => item.key === preferredKey)
        setSelectedKey(preferredKey)
        setDraft({ key: preferredKey, label: credential?.label || reference?.label || preferredKey, value: '', secret: credential?.secret !== false })
      }
    } catch (reason: any) {
      setError(reason?.message || '读取本机环境失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void load() }, [])

  function startNew() {
    setSelectedKey('')
    setDraft(EMPTY_DRAFT)
    setNotice('')
    setEditorOpen(true)
  }

  function selectEntry(key: string) {
    const credential = snapshot?.credentials.find((item) => item.key === key)
    const reference = snapshot?.references.find((item) => item.key === key)
    setSelectedKey(key)
    setDraft({ key, label: credential?.label || reference?.label || key, value: '', secret: credential?.secret !== false })
    setNotice('')
    setEditorOpen(true)
  }

  async function saveCredential(event: React.FormEvent) {
    event.preventDefault()
    const key = draft.key.trim().toUpperCase()
    if (!key) { setError('请填写变量名'); return }
    if (!draft.value && selectedCredential?.source !== 'local') { setError('请填写变量值'); return }
    setSaving(true)
    setError('')
    try {
      const payload = { ...draft, key, label: draft.label.trim() || key }
      if (selectedKey) await updateStudioCredential(selectedKey, payload)
      else await createStudioCredential(payload)
      setNotice('本机变量已保存并应用到当前底座')
      setSelectedKey(key)
      setEditorOpen(false)
      await load(key)
    } catch (reason: any) {
      setError(reason?.message || '保存本机变量失败')
    } finally {
      setSaving(false)
    }
  }

  async function removeCredential() {
    if (!selectedCredential || selectedCredential.source !== 'local' || !window.confirm(`删除本机变量 ${selectedCredential.key}？`)) return
    try {
      await deleteStudioCredential(selectedCredential.key)
      startNew()
      setEditorOpen(false)
      setNotice('本机变量已删除')
      await load('')
    } catch (reason: any) {
      setError(reason?.message || '删除本机变量失败')
    }
  }

  const configuredCount = snapshot?.references.filter((item) => item.configured).length || 0
  const readyProviders = providers.filter((item) => item.base_url && item.has_key).length

  const content = <>
      {error && <div className="cf-resource-alert danger">{error}</div>}
      {notice && <div className="cf-resource-alert success">{notice}</div>}
      <div className="cf-environment-layout">
        <section className="cf-resource-panel cf-credential-panel">
          <div className="cf-resource-panel-head"><div><span>LOCAL VARIABLES</span><h2>本机变量</h2></div><button type="button" onClick={startNew}>新增</button></div>
          <div className="cf-credential-list">
            {entries.map((entry) => <button type="button" key={entry.key} className={`cf-credential-item ${selectedKey === entry.key ? 'selected' : ''}`} onClick={() => selectEntry(entry.key)}><span className={`cf-credential-state ${entry.configured ? 'ready' : ''}`} /><span><strong>{entry.label}</strong><code>{entry.key}</code></span><i>{entry.credential ? `${entry.credential.source === 'local' ? '本机' : '进程'} ${entry.credential.preview}` : '未配置'}</i></button>)}
            {!entries.length && !loading && <div className="cf-resource-empty">还没有变量引用</div>}
          </div>
          <div className="cf-credential-panel-footer"><span>本机存储</span><code>{snapshot?.paths.credentials || '.data/user/config/studio/credentials.json'}</code><small>明文文件，已忽略版本控制；点击变量即可配置。</small></div>
        </section>

        <section className="cf-resource-panel cf-environment-status-panel">
          <div className="cf-resource-panel-head"><div><span>BASE READINESS</span><h2>底座状态</h2></div><button type="button" className="quiet" onClick={() => void load()} disabled={loading}>刷新</button></div>
          <div className="cf-system-check-list">
            {(snapshot?.checks || []).map((check) => <div className="cf-system-check" key={check.id}><span className={`cf-check-status ${check.status}`} /> <span><strong>{check.label}</strong><small>{check.version}</small></span><code>{check.path}</code></div>)}
          </div>
          <div className="cf-environment-subhead"><span>MODEL CONNECTIONS</span><h3>模型连接</h3><b>{readyProviders}/{providers.length} 就绪</b></div>
          <div className="cf-environment-provider-list">{providers.map((provider) => <div key={provider.id}><span className={`cf-check-status ${provider.base_url && provider.has_key ? 'ok' : 'missing'}`} /><strong>{provider.name}</strong><small>{provider.base_url ? 'URL 已填写' : '缺少 URL'} / {provider.has_key ? 'Key 已填写' : '缺少 Key'}</small></div>)}</div>
          <div className="cf-environment-subhead"><span>REFERENCES</span><h3>变量引用</h3><b>{configuredCount}/{snapshot?.references.length || 0}</b></div>
          <div className="cf-environment-reference-list">{(snapshot?.references || []).map((reference) => <button type="button" key={reference.key} onClick={() => selectEntry(reference.key)}><span className={`cf-check-status ${reference.configured ? 'ok' : 'missing'}`} /><span><strong>{reference.key}</strong><small>{reference.owners.join(' · ')}</small></span><i>{reference.configured ? '已配置' : '待填写'}</i></button>)}</div>
        </section>
      </div>
      <ConfigModal open={editorOpen} title={selectedKey ? `配置 ${selectedKey}` : '新增本机变量'} kicker="LOCAL ENVIRONMENT VARIABLE" onClose={() => setEditorOpen(false)}>
        <form className="cf-resource-editor cf-credential-editor" onSubmit={saveCredential} autoComplete="off">
          <label>变量名<input name="cf-local-variable-key" autoComplete="off" value={draft.key} disabled={Boolean(selectedKey)} onChange={(e) => setDraft({ ...draft, key: e.target.value.toUpperCase() })} placeholder="例如：SEARCH_API_KEY" /></label>
          <label>显示名称<input name="cf-local-variable-label" autoComplete="off" value={draft.label} onChange={(e) => setDraft({ ...draft, label: e.target.value })} placeholder="用于辨认这项配置" /></label>
          <label>变量值<input name="cf-local-variable-value" autoComplete="new-password" type={draft.secret ? 'password' : 'text'} value={draft.value} onChange={(e) => setDraft({ ...draft, value: e.target.value })} placeholder={selectedCredential ? `已保存 ${selectedCredential.preview}，留空保持不变` : '仅保存在本机'} /></label>
          <label className="cf-environment-secret-toggle"><input type="checkbox" checked={draft.secret} onChange={(e) => setDraft({ ...draft, secret: e.target.checked })} /><span>按敏感变量处理</span></label>
          <div className="cf-config-modal-actions"><button type="button" onClick={() => setEditorOpen(false)}>取消</button>{selectedCredential?.source === 'local' && <button type="button" className="danger" onClick={() => void removeCredential()}>删除</button>}<button type="submit" className="primary" disabled={saving}>{saving ? '保存中…' : selectedCredential?.source === 'process' ? '保存本机覆盖' : '保存变量'}</button></div>
          <small className="cf-credential-storage">保存后立即应用到当前底座进程；密钥不会出现在 API 响应或卡带包中。</small>
        </form>
      </ConfigModal>
    </>

  if (embedded) return <section className="cf-settings-environment-section" aria-label="本机环境设置">{content}</section>

  return (
    <div className="cf-resource-page cf-environment-page">
      <header className="cf-resource-heading">
        <div><span className="cf-resource-kicker">BASE / ENVIRONMENT</span><h1>本机环境</h1><p>当前底座进程的本机变量、引用关系和运行依赖。</p></div>
        <div className="cf-resource-heading-meta"><b>{configuredCount}</b><span>项引用已配置</span></div>
      </header>
      {content}
    </div>
  )
}
