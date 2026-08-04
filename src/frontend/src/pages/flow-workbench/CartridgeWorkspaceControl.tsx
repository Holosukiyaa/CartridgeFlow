import { useCallback, useEffect, useRef, useState, type ChangeEvent } from 'react'
import { Button, Field, Input, Spinner, Text, Textarea } from '../../ui.tsx'
import { ChevronDown, FilePlus2, FolderOpen, PencilLine, Trash2, Upload, X } from 'lucide-react'
import {
  createDevFlow,
  deleteLabFlow,
  fetchLabFlowFiles,
  fetchLabFlows,
  importCartridgePackage,
  openLabFlowDirectory,
  saveLabFlowFile,
  type FlowLabItem,
} from '../../api.ts'
import ConfigModal from '../../components/ConfigModal.tsx'
import { showToast } from '../../toast.tsx'
import { BrandMark } from './BrandMark.tsx'
import { markNewFlowForAutoLayout } from './newFlowSetup.ts'

type CartridgeSummary = {
  id: string
  name: string
  description?: string
  version: string
  editable?: boolean
  source?: string
}

type Panel = 'current' | 'manage' | 'create' | 'info'

const DEFAULT_DEMO_FLOW = {
  id: 'demo',
  name: 'Demo 卡带',
  description: '用于快速开始设计的 Demo 卡带。',
}

export default function CartridgeWorkspaceControl({ current, empty = false, creatorMode = false, onSwitchFlow, onUpdated }: {
  current?: CartridgeSummary | null
  empty?: boolean
  creatorMode?: boolean
  onSwitchFlow: (flowId: string) => void
  onUpdated?: () => void | Promise<void>
}) {
  const [flows, setFlows] = useState<FlowLabItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [modalOpen, setModalOpen] = useState(false)
  const [panel, setPanel] = useState<Panel>('current')
  const [busy, setBusy] = useState(false)
  const [flowId, setFlowId] = useState('')
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [manifest, setManifest] = useState<Record<string, any> | null>(null)
  const importPickerRef = useRef<HTMLInputElement | null>(null)

  const loadFlows = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const data = await fetchLabFlows()
      setFlows(data.items || [])
      return data.items || []
    } catch (loadError: any) {
      setError(loadError.message || '无法读取本机卡带')
      return []
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { void loadFlows() }, [loadFlows])

  const openPanel = (nextPanel: Panel) => {
    setPanel(nextPanel)
    setModalOpen(true)
    if (nextPanel === 'create') {
      setFlowId(DEFAULT_DEMO_FLOW.id)
      setName(DEFAULT_DEMO_FLOW.name)
      setDescription(DEFAULT_DEMO_FLOW.description)
    }
    void loadFlows()
  }

  const openInfo = async () => {
    if (!current) return
    setPanel('info')
    setModalOpen(true)
    setBusy(true)
    setName(current.name)
    setDescription(current.description || '')
    setManifest(null)
    try {
      const result = await fetchLabFlowFiles(current.id)
      const nextManifest = JSON.parse(result.files.manifest || '{}')
      setManifest(nextManifest)
      setName(nextManifest.name || current.name)
      setDescription(nextManifest.description || '')
    } catch (loadError: any) {
      setModalOpen(false)
      showToast({ title: '无法读取卡带信息', description: loadError.message || current.id, type: 'error' })
    } finally {
      setBusy(false)
    }
  }

  const createFlow = async () => {
    const nextFlowId = flowId.trim() || DEFAULT_DEMO_FLOW.id
    const nextName = name.trim() || DEFAULT_DEMO_FLOW.name
    const nextDescription = description.trim() || DEFAULT_DEMO_FLOW.description
    setBusy(true)
    try {
      const result = await createDevFlow(nextFlowId, nextName, nextDescription)
      showToast({ title: '卡带已创建', description: result.id, type: 'success' })
      setModalOpen(false)
      await loadFlows()
      markNewFlowForAutoLayout(result.id)
      onSwitchFlow(result.id)
    } catch (createError: any) {
      showToast({ title: '创建失败', description: createError.message, type: 'error' })
    } finally {
      setBusy(false)
    }
  }

  const importFlow = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) return
    setBusy(true)
    try {
      let result
      try {
        result = await importCartridgePackage(file, 'keep_existing')
      } catch (importError: any) {
        if (!String(importError.message || '').includes('already installed') || !window.confirm('这个卡带已经存在，是否覆盖更新？')) throw importError
        result = await importCartridgePackage(file, 'replace')
      }
      showToast({ title: result.replaced ? '卡带已更新' : '卡带已导入', description: result.cartridge.id, type: 'success' })
      setModalOpen(false)
      await loadFlows()
      onSwitchFlow(result.cartridge.id)
    } catch (importError: any) {
      showToast({ title: '导入失败', description: importError.message, type: 'error' })
    } finally {
      setBusy(false)
    }
  }

  const saveInfo = async () => {
    if (!current?.editable || !manifest || !name.trim()) return
    setBusy(true)
    try {
      const nextManifest = { ...manifest, name: name.trim(), description: description.trim() }
      await saveLabFlowFile(current.id, 'manifest', `${JSON.stringify(nextManifest, null, 2)}\n`)
      showToast({ title: '卡带信息已更新', description: current.id, type: 'success' })
      setModalOpen(false)
      await Promise.all([loadFlows(), onUpdated?.()])
    } catch (saveError: any) {
      showToast({ title: '保存失败', description: saveError.message || current.id, type: 'error' })
    } finally {
      setBusy(false)
    }
  }

  const openDirectory = async () => {
    if (!current) return
    setBusy(true)
    try {
      const result = await openLabFlowDirectory(current.id)
      showToast({ title: '已打开卡带目录', description: result.path, type: 'success' })
    } catch (openError: any) {
      showToast({ title: '无法打开卡带目录', description: openError.message || current.id, type: 'error' })
    } finally {
      setBusy(false)
    }
  }

  const removeCurrent = async () => {
    if (!current?.editable || !window.confirm(`确定删除卡带“${current.name}”吗？\n\n${current.id}`)) return
    setBusy(true)
    try {
      await deleteLabFlow(current.id)
      const remaining = await loadFlows()
      showToast({ title: '卡带已删除', description: current.id, type: 'success' })
      setModalOpen(false)
      onSwitchFlow(remaining.find((item) => item.id !== current.id)?.id || '')
    } catch (deleteError: any) {
      showToast({ title: '删除失败', description: deleteError.message || current.id, type: 'error' })
    } finally {
      setBusy(false)
    }
  }

  const hiddenPicker = (
    <input ref={importPickerRef} type="file" hidden accept=".cartridge.zip,.zip" onChange={importFlow} />
  )

  const managerContent = (
    <div className="cf-cartridge-manager">
      <div className="cf-cartridge-manager-actions"><Button className="cf-accent-btn" onClick={() => openPanel('create')}><FilePlus2 />新建卡带</Button><Button className="cf-outline-btn" onClick={() => importPickerRef.current?.click()} loading={busy} loadingText="导入中..."><Upload />导入卡带</Button></div>
      {loading ? <div className="cf-cartridge-workspace-loading"><Spinner /></div> : error ? <Text color="fg.error">{error}</Text> : (
        <div className="cf-cartridge-manager-list">
          {flows.map((flow) => <article key={flow.id} className={flow.id === current?.id ? 'current' : ''}><div><strong>{flow.name}</strong><p title={flow.description || '暂无简介'}>{flow.description || '暂无简介'}</p><span>{flow.id} · v{flow.version} · {flow.editable ? '可编辑' : '只读'}</span></div><Button className="cf-outline-btn" disabled={flow.id === current?.id} onClick={() => { setModalOpen(false); onSwitchFlow(flow.id) }}>{flow.id === current?.id ? '当前卡带' : '打开'}</Button></article>)}
        </div>
      )}
    </div>
  )

  const modal = (
    <ConfigModal
      open={modalOpen && panel !== 'current' && panel !== 'manage'}
      title={panel === 'create' ? '新建开发卡带' : '卡带信息'}
      kicker={panel === 'create' ? '新建卡带' : '卡带档案'}
      className="cf-cartridge-workspace-modal"
      onClose={() => { if (!busy) setModalOpen(false) }}
    >
      {panel === 'create' && (
        <div className="cf-cartridge-workspace-form">
          <Field.Root><Field.Label>卡带 ID</Field.Label><Input value={flowId} onChange={(event) => setFlowId(event.target.value)} placeholder="例如：video-intro（自动添加 dev. 前缀）" /></Field.Root>
          <Field.Root><Field.Label>名称</Field.Label><Input value={name} onChange={(event) => setName(event.target.value)} placeholder="卡带名称" /></Field.Root>
          <Field.Root><Field.Label>描述</Field.Label><Textarea value={description} onChange={(event) => setDescription(event.target.value)} rows={3} placeholder="这个卡带解决什么问题" /></Field.Root>
          <div className="cf-cartridge-workspace-form-actions"><Button className="cf-outline-btn" onClick={() => { if (empty) setModalOpen(false); else setPanel('manage') }} disabled={busy}>返回</Button><Button className="cf-accent-btn" onClick={() => void createFlow()} loading={busy} loadingText="创建中...">创建并进入</Button></div>
        </div>
      )}
      {panel === 'info' && (
        busy && !manifest ? <div className="cf-cartridge-workspace-loading"><Spinner /></div> : (
          <div className="cf-cartridge-workspace-form">
            <div className="cf-cartridge-current-summary"><div><span>卡带 ID</span><strong>{current?.id}</strong></div><div><span>版本</span><strong>v{current?.version}</strong></div><div><span>状态</span><strong>{current?.editable ? '可编辑' : '只读'}</strong></div></div>
            <Field.Root><Field.Label>卡带名称</Field.Label>{current?.editable ? <Input value={name} onChange={(event) => setName(event.target.value)} /> : <div className="cf-cartridge-readonly-field">{name}</div>}</Field.Root>
            <Field.Root><Field.Label>卡带描述</Field.Label>{current?.editable ? <Textarea value={description} onChange={(event) => setDescription(event.target.value)} rows={4} /> : <div className="cf-cartridge-readonly-field multiline">{description || '—'}</div>}</Field.Root>
            <div className="cf-cartridge-workspace-form-actions"><Button className="cf-outline-btn" onClick={() => setPanel('current')} disabled={busy}>返回</Button>{current?.editable && <Button className="cf-accent-btn" onClick={() => void saveInfo()} disabled={!name.trim()} loading={busy} loadingText="保存中...">保存修改</Button>}</div>
          </div>
        )
      )}
    </ConfigModal>
  )

  const floatingPanel = modalOpen && panel === 'current' && current ? (
    <aside className="cf-cartridge-floating-panel" aria-label="当前卡带">
      <header><strong>当前卡带</strong><span className={current.editable ? 'editable' : ''}><i />{current.editable ? '开发中，可修改' : '只读卡带'}</span><button type="button" onClick={() => setModalOpen(false)} aria-label="关闭卡带面板"><X /></button></header>
      <div className="cf-cartridge-floating-facts"><div><span>卡带 ID</span><strong>{current.id}</strong></div><div><span>版本</span><strong>v{current.version}</strong></div><div><span>状态</span><strong>{current.editable ? '开发中' : '只读'}</strong></div></div>
      {error && <Text color="fg.error">{error}</Text>}
      <div className="cf-cartridge-floating-actions">
        <Button onClick={() => void openInfo()}><PencilLine />编辑信息</Button>
        <Button onClick={() => void openDirectory()} loading={busy} loadingText="正在打开..."><FolderOpen />打开目录</Button>
        {current.editable && <Button className="danger" onClick={() => void removeCurrent()} disabled={busy}><Trash2 />删除卡带</Button>}
      </div>
      <Button className="cf-open-other-cartridge" onClick={() => openPanel('manage')}>打开其他卡带<ChevronDown aria-hidden="true" /></Button>
    </aside>
  ) : null

  const managerPanel = modalOpen && panel === 'manage' && current ? (
    <aside className="cf-cartridge-floating-panel cf-cartridge-manager-panel" aria-label="打开其他卡带">
      <header><div><span>卡带库</span><strong>打开其他卡带</strong></div><button type="button" onClick={() => setModalOpen(false)} aria-label="关闭卡带库"><X /></button></header>
      {managerContent}
    </aside>
  ) : null

  if (empty) {
    return (
      <div className="cf-page cf-workbench-page cf-empty-workbench-page">
        {hiddenPicker}
        <main className="cf-empty-workbench-canvas">
          <div className="cf-empty-workbench-brand"><BrandMark className="cf-empty-workbench-brand-mark" /><span>CARTRIDGEFLOW</span></div>
          <div className="cf-empty-workbench-visual" aria-hidden="true">
            <i className="cf-empty-dots" />
            <i className="cf-empty-wire wire-top" /><i className="cf-empty-wire wire-bottom" />
            <div className="cf-empty-card-shadow" />
            <div className="cf-empty-card">
              <b>CF</b><span /><span /><span />
              <em /><small />
            </div>
          </div>
          <div className="cf-empty-workbench-copy"><span>DESIGN TO RUNTIME</span><h2>从一张卡带<br />开始设计</h2><i /><p>创建新的开发卡带，或者导入已有卡带文件。进入后所有设计、资源和真实运行能力都在同一个工作台完成。</p><div><Button className="cf-accent-btn" onClick={() => openPanel('create')}>新建开发卡带</Button><Button className="cf-outline-btn" onClick={() => importPickerRef.current?.click()} loading={busy} loadingText="导入中...">导入已有卡带</Button></div></div>
        </main>
        {modal}
      </div>
    )
  }

  return (
    <div className="cf-workbench-cartridge-control">
      {hiddenPicker}
      <button type="button" className="cf-workbench-current-trigger" title={creatorMode ? current?.name : `${current?.name || current?.id || ''} (${current?.id || ''})`} onClick={() => { if (panel === 'current' && modalOpen) setModalOpen(false); else openPanel('current') }}>
        <span className="cf-workbench-live-dot" /><b>{current?.name || current?.id}</b>{!creatorMode && <span>{current?.id} · v{current?.version}</span>}<ChevronDown aria-hidden="true" />
      </button>
      {floatingPanel}
      {managerPanel}
      {modal}
    </div>
  )
}
