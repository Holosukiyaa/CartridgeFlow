// Flow 实验室页面：展示 Flow 列表、创建 dev flow、进入工作台
import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import {
  Box, Heading, Text, SimpleGrid, Card, Button, Badge, HStack, VStack,
  Spinner, Input, Textarea, Field, Collapsible,
} from '../ui.tsx'
import {
  fetchLabFlows, createDevFlow, deleteLabFlow, importCartridgePackage,
  openLabFlowDirectory, fetchLabFlowFiles, saveLabFlowFile, type FlowLabItem,
} from '../api.ts'
import { showToast } from '../toast.tsx'
import PrimaryPageHeader from '../components/PrimaryPageHeader.tsx'
import ConfigModal from '../components/ConfigModal.tsx'

function isTemplateFlow(item: FlowLabItem) {
  const tags = item.branding?.tags || []
  return item.category === 'template' || tags.includes('template')
}

function sortTemplateFlows(items: FlowLabItem[]) {
  return [...items].sort((a, b) => a.name.localeCompare(b.name, 'zh-CN'))
}

function projectPath(flowId: string, mode: 'design' | 'test' = 'design') {
  return `/projects/${encodeURIComponent(flowId)}/${mode}`
}

export default function LabPage() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const [items, setItems] = useState<FlowLabItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [showCreate, setShowCreate] = useState(searchParams.get('create') === '1')
  const importPickerRef = useRef<HTMLInputElement | null>(null)
  const importPromptedRef = useRef(false)
  const [importing, setImporting] = useState(false)
  const [openingDirectoryId, setOpeningDirectoryId] = useState('')
  const [editingFlow, setEditingFlow] = useState<FlowLabItem | null>(null)
  const [editingManifest, setEditingManifest] = useState<Record<string, any> | null>(null)
  const [editingName, setEditingName] = useState('')
  const [editingDescription, setEditingDescription] = useState('')
  const [loadingFlowInfo, setLoadingFlowInfo] = useState(false)
  const [savingFlowInfo, setSavingFlowInfo] = useState(false)

  const openCreateForm = () => setShowCreate(true)

  const load = async () => {
    setLoading(true)
    setError('')
    try {
      const data = await fetchLabFlows()
      setItems(data.items || [])
    } catch (e: any) {
      setError(e.message || '加载失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  useEffect(() => {
    if (searchParams.get('import') !== '1' || importPromptedRef.current) return
    importPromptedRef.current = true
    const timer = window.setTimeout(() => importPickerRef.current?.click(), 0)
    return () => window.clearTimeout(timer)
  }, [searchParams])

  const handleDelete = async (flow: FlowLabItem) => {
    if (!flow.editable) return
    const confirmed = window.confirm(`确定删除 dev flow「${flow.name}」吗？\n\n${flow.id}`)
    if (!confirmed) return
    try {
      await deleteLabFlow(flow.id)
      showToast({ title: '删除成功', description: flow.id, type: 'success' })
      await load()
    } catch (e: any) {
      showToast({ title: '删除失败', description: e.message, type: 'error' })
    }
  }

  const handleImportFile = async (event: any) => {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) return
    setImporting(true)
    try {
      const result = await importCartridgePackage(file, 'keep_existing')
      showToast({ title: result.replaced ? '卡带已更新' : '卡带已导入', description: result.cartridge.id, type: 'success' })
      await load()
      navigate(projectPath(result.cartridge.id))
    } catch (e: any) {
      const message = e.message || ''
      if (message.includes('already installed') && window.confirm('这个卡带已经安装。要覆盖更新吗？')) {
        try {
          const result = await importCartridgePackage(file, 'replace')
          showToast({ title: '卡带已覆盖更新', description: result.cartridge.id, type: 'success' })
          await load()
          navigate(projectPath(result.cartridge.id))
        } catch (replaceError: any) {
          showToast({ title: '导入失败', description: replaceError.message, type: 'error' })
        }
      } else {
        showToast({ title: '导入失败', description: message, type: 'error' })
      }
    } finally {
      setImporting(false)
    }
  }

  const handleOpenDirectory = async (flow: FlowLabItem) => {
    setOpeningDirectoryId(flow.id)
    try {
      const result = await openLabFlowDirectory(flow.id)
      showToast({ title: '已打开卡带目录', description: result.path, type: 'success' })
    } catch (e: any) {
      showToast({ title: '无法打开卡带目录', description: e.message || flow.id, type: 'error' })
    } finally {
      setOpeningDirectoryId('')
    }
  }

  const handleOpenFlowInfo = async (flow: FlowLabItem) => {
    setEditingFlow(flow)
    setEditingManifest(null)
    setEditingName(flow.name)
    setEditingDescription(flow.description || '')
    setLoadingFlowInfo(true)
    try {
      const result = await fetchLabFlowFiles(flow.id)
      const manifest = JSON.parse(result.files.manifest || '{}')
      setEditingManifest(manifest)
      setEditingName(manifest.name || flow.name)
      setEditingDescription(manifest.description || '')
    } catch (e: any) {
      setEditingFlow(null)
      showToast({ title: '无法读取卡带信息', description: e.message || flow.id, type: 'error' })
    } finally {
      setLoadingFlowInfo(false)
    }
  }

  const handleSaveFlowInfo = async () => {
    if (!editingFlow?.editable || !editingManifest) return
    const name = editingName.trim()
    if (!name) {
      showToast({ title: '卡带名称不能为空', type: 'error' })
      return
    }
    setSavingFlowInfo(true)
    try {
      const nextManifest = {
        ...editingManifest,
        name,
        description: editingDescription.trim(),
      }
      await saveLabFlowFile(editingFlow.id, 'manifest', `${JSON.stringify(nextManifest, null, 2)}\n`)
      showToast({ title: '卡带信息已更新', description: editingFlow.id, type: 'success' })
      setEditingFlow(null)
      setEditingManifest(null)
      await load()
    } catch (e: any) {
      showToast({ title: '保存失败', description: e.message || editingFlow.id, type: 'error' })
    } finally {
      setSavingFlowInfo(false)
    }
  }

  const templateItems = sortTemplateFlows(items.filter(isTemplateFlow))
  const otherItems = items.filter((item) => !isTemplateFlow(item))
  const renderFlowCard = (flow: FlowLabItem) => {
    const protocolVersion = flow.runtime_contract?.protocol_version
    const readiness = flow.delivery_readiness?.level
    return (
    <Card.Root key={flow.id} className="cf-cartridge-card cf-flow-card">
      <Link
        className="cf-flow-card-hitarea"
        to={projectPath(flow.id)}
        aria-label={`打开 ${flow.name} 工作台`}
        title="打开工作台"
      />
      <Card.Body p={0}>
        <div className="cf-flow-card-content">
        <HStack className="cf-card-top" justify="space-between" align="start" mb={3}>
          <Box>
            <Text className="cf-kicker" mb={1}>
              {flow.category === 'template' ? 'template' : flow.source || 'flow'}
              <span className="cf-flow-inline-state"> · {flow.editable ? '开发中可修改' : '只读'}</span>
            </Text>
            <Heading className="cf-card-title" mb={0}>{flow.name}</Heading>
          </Box>
          <span className="cf-flow-card-entry-hint" aria-hidden="true">进入工作台 →</span>
        </HStack>
        <Text className="cf-card-desc" minH="3.2em">{flow.description || ''}</Text>
        <HStack mt={3} gap={2} flexWrap="wrap" className="cf-flow-meta">
          <Badge className="cf-badge">{flow.id}</Badge>
          <Badge className="cf-badge">v{flow.version}</Badge>
          {protocolVersion && <Badge className="cf-badge">CF-FARP@{protocolVersion}</Badge>}
          {readiness && <Badge className="cf-badge">{readiness}</Badge>}
          <Badge className="cf-badge">{flow.runtime?.type || 'none'}</Badge>
        </HStack>
        </div>
      </Card.Body>
      <div className="cf-flow-card-footer">
        <div className={`cf-flow-action-strip ${flow.editable ? 'editable' : 'readonly'}`}>
          <button type="button" className="primary" onClick={() => void handleOpenFlowInfo(flow)}>编辑信息</button>
          <Link to={`/projects/${encodeURIComponent(flow.id)}/resources`}>绑定资源</Link>
          <button type="button" disabled={openingDirectoryId === flow.id} onClick={() => void handleOpenDirectory(flow)}>{openingDirectoryId === flow.id ? '正在打开…' : '打开目录'}</button>
          {flow.editable && <button type="button" className="danger" onClick={() => void handleDelete(flow)}>删除卡带</button>}
        </div>
      </div>
    </Card.Root>
    )
  }

  return (
    <Box className="cf-page cf-primary-page-surface cf-lab-page">
      <Box className="cf-page-inner cf-lab-page-inner">
      <PrimaryPageHeader
        eyebrow="Cartridge Library"
        title="卡带管理"
        description="设计、验证和打包专属服务卡带"
        actions={(
          <HStack gap={2}>
            <input
              ref={importPickerRef}
              type="file"
              style={{ display: 'none' }}
              accept=".cartridge.zip,.zip"
              onChange={handleImportFile}
            />
            <Button className="cf-outline-btn" onClick={() => importPickerRef.current?.click()} loading={importing} loadingText="导入中...">
              导入卡带文件
            </Button>
            <Button className="cf-outline-btn" onClick={load}>刷新</Button>
            <Button className="cf-accent-btn" onClick={() => setShowCreate((v) => !v)}>新建开发卡带</Button>
          </HStack>
        )}
      />

      <Collapsible.Root open={showCreate}>
        <Collapsible.Content>
          <CreateFlowForm
            onCreate={async (flowId, name, desc) => {
              try {
                const result = await createDevFlow(flowId, name, desc)
                showToast({ title: '创建成功', type: 'success' })
                setShowCreate(false)
                await load()
                navigate(projectPath(result.id))
              } catch (e: any) {
                showToast({ title: '创建失败', description: e.message, type: 'error' })
              }
            }}
            onCancel={() => setShowCreate(false)}
          />
        </Collapsible.Content>
      </Collapsible.Root>

      {loading && <Spinner />}
      {error && <Text color="fg.error">{error}</Text>}

      {!loading && !error && items.length === 0 && !showCreate && (
        <section className="cf-flow-empty-stage" aria-labelledby="cf-flow-empty-title">
          <div className="cf-flow-empty-visual" aria-hidden="true">
            <div className="cf-flow-empty-cartridge">
              <span>CF</span>
              <div><i /><i /><i /></div>
              <small>NO CARTRIDGE LOADED</small>
            </div>
          </div>
          <div className="cf-flow-empty-copy">
            <span className="cf-flow-empty-kicker">EMPTY CARTRIDGE LIBRARY</span>
            <h2 id="cf-flow-empty-title">从第一张卡带开始</h2>
            <p>把一个专属服务的流程、模型配方和交付方式整理成可运行、可迁移的卡带。</p>
            <div className="cf-flow-empty-actions">
              <Button className="cf-accent-btn" onClick={openCreateForm}>创建开发卡带</Button>
              <Button className="cf-outline-btn" onClick={() => importPickerRef.current?.click()} loading={importing} loadingText="导入中...">导入已有卡带</Button>
            </div>
            <div className="cf-flow-empty-facts">
              <div><span>LOCAL-FIRST</span><strong>凭据留在本机</strong></div>
              <div><span>PORTABLE RECIPE</span><strong>流程与配方随卡带迁移</strong></div>
            </div>
          </div>
        </section>
      )}

      {!loading && !error && templateItems.length > 0 && (
        <Box className="cf-library-section">
          <HStack className="cf-section-header cf-flow-section-header" justify="space-between" align="end">
            <Box>
              <Text className="cf-flow-group-label">模板</Text>
              <Text className="cf-section-subtitle">从模板进入工作台，可以查看 Flow 结构、复制并改造成自己的卡带。</Text>
            </Box>
            <Badge className="cf-badge">{templateItems.length} 张模板</Badge>
          </HStack>
          <SimpleGrid className="cf-shelf-grid cf-flow-list">
            {templateItems.map(renderFlowCard)}
          </SimpleGrid>
        </Box>
      )}

      {!loading && !error && otherItems.length > 0 && (
        <Box className="cf-library-section">
          <HStack className="cf-section-header cf-flow-section-header" justify="space-between" align="center">
            <Text className="cf-flow-group-label">开发 Flow</Text>
            <Badge className="cf-badge">{otherItems.length} 个</Badge>
          </HStack>
          <SimpleGrid className="cf-shelf-grid cf-flow-list">
            {otherItems.map(renderFlowCard)}
          </SimpleGrid>
        </Box>
      )}
      </Box>

      <ConfigModal
        open={Boolean(editingFlow)}
        title={editingFlow?.editable ? '编辑卡带信息' : '卡带信息'}
        kicker="Cartridge Profile"
        className="cf-flow-info-modal"
        onClose={() => { if (!savingFlowInfo) setEditingFlow(null) }}
      >
        {editingFlow && loadingFlowInfo && <div className="cf-flow-info-loading"><Spinner /></div>}
        {editingFlow && !loadingFlowInfo && editingManifest && (
          <div className="cf-flow-info-form">
            <div className="cf-flow-info-facts">
              <div><span>Flow ID</span><strong>{editingFlow.id}</strong></div>
              <div><span>版本</span><strong>v{editingFlow.version}</strong></div>
              <div><span>协议</span><strong>CF-FARP@{editingFlow.runtime_contract?.protocol_version || '—'}</strong></div>
            </div>
            <Field.Root>
              <Field.Label>卡带名称</Field.Label>
              {editingFlow.editable
                ? <Input value={editingName} onChange={(event) => setEditingName(event.target.value)} />
                : <div className="cf-flow-info-readonly">{editingName}</div>}
            </Field.Root>
            <Field.Root>
              <Field.Label>卡带描述</Field.Label>
              {editingFlow.editable
                ? <Textarea value={editingDescription} onChange={(event) => setEditingDescription(event.target.value)} rows={4} />
                : <div className="cf-flow-info-readonly multiline">{editingDescription || '—'}</div>}
            </Field.Root>
            <div className="cf-flow-info-actions">
              <Button className="cf-outline-btn" onClick={() => setEditingFlow(null)} disabled={savingFlowInfo}>取消</Button>
              {editingFlow.editable && <Button className="cf-accent-btn" onClick={() => void handleSaveFlowInfo()} loading={savingFlowInfo} loadingText="保存中...">保存修改</Button>}
            </div>
          </div>
        )}
      </ConfigModal>
    </Box>
  )
}

// 创建开发卡带表单
function CreateFlowForm({ onCreate, onCancel }: {
  onCreate: (flowId: string, name: string, desc: string) => void
  onCancel: () => void
}) {
  const [flowId, setFlowId] = useState('')
  const [name, setName] = useState('')
  const [desc, setDesc] = useState('')

  return (
    <Card.Root className="cf-soft-panel" style={{ padding: 20, marginBottom: 24 }}>
      <Card.Body>
        <Heading size="sm" mb={4}>创建开发卡带</Heading>
        <VStack align="stretch" gap={4}>
          <Field.Root>
            <Field.Label>卡带 ID</Field.Label>
            <Input
              value={flowId}
              onChange={(e) => setFlowId(e.target.value)}
              placeholder="例如：image-generator（自动加 dev. 前缀）"
            />
          </Field.Root>
          <Field.Root>
            <Field.Label>名称</Field.Label>
            <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="卡带名称" />
          </Field.Root>
          <Field.Root>
            <Field.Label>描述</Field.Label>
            <Textarea value={desc} onChange={(e) => setDesc(e.target.value)} rows={2} placeholder="卡带描述（可选）" />
          </Field.Root>
          <HStack gap={2}>
            <Button
              className="cf-accent-btn"
              onClick={() => onCreate(flowId, name, desc)}
              disabled={!flowId.trim() || !name.trim()}
            >
              创建
            </Button>
            <Button onClick={onCancel}>取消</Button>
          </HStack>
        </VStack>
      </Card.Body>
    </Card.Root>
  )
}
