// Flow 实验室页面：展示 Flow 列表、创建 dev flow、进入工作台
import { useEffect, useRef, useState } from 'react'
import {
  Box, Heading, Text, SimpleGrid, Card, Button, Badge, HStack, VStack,
  Spinner, Input, Textarea, Field, Collapsible,
} from '../ui.tsx'
import { fetchLabFlows, createDevFlow, deleteLabFlow, importCartridgePackage, type FlowLabItem } from '../api.ts'
import { showToast } from '../toast.tsx'
import FlowWorkbench from './FlowWorkbench.tsx'

const TEMPLATE_ORDER = [
  'dev.file_summary',
  'dev.log_diagnosis',
  'dev.csv_report',
  'dev.readme_generator',
  'dev.multi_file_summary',
  'dev.short_video_generator',
]

function isTemplateFlow(item: FlowLabItem) {
  const tags = item.branding?.tags || []
  return item.category === 'template' || tags.includes('template')
}

function sortTemplateFlows(items: FlowLabItem[]) {
  return [...items].sort((a, b) => {
    const aIndex = TEMPLATE_ORDER.indexOf(a.id)
    const bIndex = TEMPLATE_ORDER.indexOf(b.id)
    if (aIndex >= 0 || bIndex >= 0) {
      return (aIndex >= 0 ? aIndex : 999) - (bIndex >= 0 ? bIndex : 999)
    }
    return a.name.localeCompare(b.name, 'zh-CN')
  })
}

export default function LabPage() {
  const [items, setItems] = useState<FlowLabItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [activeId, setActiveId] = useState<string | null>(null)
  const [showCreate, setShowCreate] = useState(false)
  const importPickerRef = useRef<HTMLInputElement | null>(null)
  const [importing, setImporting] = useState(false)

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
      setActiveId(result.cartridge.id)
    } catch (e: any) {
      const message = e.message || ''
      if (message.includes('already installed') && window.confirm('这个卡带已经安装。要覆盖更新吗？')) {
        try {
          const result = await importCartridgePackage(file, 'replace')
          showToast({ title: '卡带已覆盖更新', description: result.cartridge.id, type: 'success' })
          await load()
          setActiveId(result.cartridge.id)
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

  if (activeId) {
    return <FlowWorkbench flowId={activeId} onBack={() => { setActiveId(null); load() }} onSwitchFlow={setActiveId} />
  }

  const templateItems = sortTemplateFlows(items.filter(isTemplateFlow))
  const otherItems = items.filter((item) => !isTemplateFlow(item))
  const renderFlowCard = (flow: FlowLabItem) => (
    <Card.Root key={flow.id} className="cf-cartridge-card cf-flow-card">
      <Card.Body p={0}>
        <HStack className="cf-card-top" justify="space-between" align="start" mb={3}>
          <Box>
            <Text className="cf-kicker" mb={1}>
              {flow.category === 'template' ? 'template' : flow.source || 'flow'}
            </Text>
            <Heading className="cf-card-title" mb={0}>{flow.name}</Heading>
          </Box>
          <Box className="cf-card-icon">LAB</Box>
        </HStack>
        <Text className="cf-card-desc" minH="3.2em">{flow.description || ''}</Text>
        <HStack mt={3} gap={2} flexWrap="wrap">
          <Badge className="cf-badge">{flow.id}</Badge>
          <Badge className="cf-badge">{flow.runtime?.type || 'none'}</Badge>
          {flow.source && <Badge className="cf-badge">{flow.source}</Badge>}
          <Badge className="cf-badge">
            {flow.editable ? 'editable' : 'readonly'}
          </Badge>
        </HStack>
      </Card.Body>
      <Card.Footer p={0} pt={0}>
        <VStack gap={1} align="stretch" className="cf-card-actions cf-flow-actions">
          <Button className="cf-accent-btn" w="100%" onClick={() => setActiveId(flow.id)}>进入工作台</Button>
          {flow.editable && (
            <Button className="cf-delete-link-btn" onClick={() => handleDelete(flow)}>删除 flow</Button>
          )}
        </VStack>
      </Card.Footer>
    </Card.Root>
  )

  return (
    <Box className="cf-page">
      <Box className="cf-page-inner">
      <HStack justify="space-between" className="cf-page-header">
        <VStack align="start" gap={1}>
          <Text className="cf-kicker">Flow Lab</Text>
          <Heading size="lg" className="cf-page-title">Flow 实验室</Heading>
          <Text className="cf-page-subtitle">开发与调试 Flow 链路</Text>
        </VStack>
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
          <Button className="cf-accent-btn" onClick={() => setShowCreate((v) => !v)}>新建 dev flow</Button>
        </HStack>
      </HStack>

      <Collapsible.Root open={showCreate}>
        <Collapsible.Content>
          <CreateFlowForm
            onCreate={async (flowId, name, desc) => {
              try {
                const result = await createDevFlow(flowId, name, desc)
                showToast({ title: '创建成功', type: 'success' })
                setShowCreate(false)
                await load()
                setActiveId(result.id)
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

      {!loading && !error && items.length === 0 && (
        <Card.Root className="cf-soft-panel">
          <Card.Body p={5}>
            <Heading size="md">还没有 Flow</Heading>
            <Text color="fg.muted" mt={2}>点击「新建 dev flow」创建第一个 Flow。</Text>
          </Card.Body>
        </Card.Root>
      )}

      {!loading && !error && templateItems.length > 0 && (
        <Box className="cf-library-section">
          <HStack className="cf-section-header" justify="space-between" align="end">
            <Box>
              <Text className="cf-kicker">Template Library</Text>
              <Heading size="md" className="cf-section-title">模板卡带库</Heading>
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
          <HStack className="cf-section-header" justify="space-between" align="end">
            <Box>
              <Text className="cf-kicker">Dev Flows</Text>
              <Heading size="md" className="cf-section-title">开发中的 Flow</Heading>
            </Box>
            <Badge className="cf-badge">{otherItems.length} 个</Badge>
          </HStack>
          <SimpleGrid className="cf-shelf-grid cf-flow-list">
            {otherItems.map(renderFlowCard)}
          </SimpleGrid>
        </Box>
      )}
      </Box>
    </Box>
  )
}

// 创建 dev flow 表单
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
        <Heading size="sm" mb={4}>创建 dev flow</Heading>
        <VStack align="stretch" gap={4}>
          <Field.Root>
            <Field.Label>Flow ID</Field.Label>
            <Input
              value={flowId}
              onChange={(e) => setFlowId(e.target.value)}
              placeholder="例如：my-flow（自动加 dev. 前缀）"
            />
          </Field.Root>
          <Field.Root>
            <Field.Label>名称</Field.Label>
            <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Flow 名称" />
          </Field.Root>
          <Field.Root>
            <Field.Label>描述</Field.Label>
            <Textarea value={desc} onChange={(e) => setDesc(e.target.value)} rows={2} placeholder="Flow 描述（可选）" />
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
