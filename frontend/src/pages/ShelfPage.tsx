// 卡带货架页面：展示卡带列表，点击打开卡带详情并运行
import { useEffect, useRef, useState } from 'react'
import {
  Box, Heading, Text, SimpleGrid, Card, Button, Badge, HStack, VStack,
  Spinner, Input, Textarea, Field, NativeSelect, Separator, Link,
} from '../ui.tsx'
import ReactMarkdown from 'react-markdown'
import {
  fetchCartridges, fetchCartridge, cloneCartridgeToDev, createCartridgeRun, importCartridgePackage, packageCartridge,
  uninstallInstalledCartridge, uploadWorkspaceFile,
  type CartridgeSummary, type CartridgeDetail, type RunResult, type CartridgeInput, type McpTool,
} from '../api.ts'
import { showToast } from '../toast.tsx'

const TEMPLATE_ORDER = [
  'dev.file_summary',
  'dev.log_diagnosis',
  'dev.csv_report',
  'dev.readme_generator',
  'dev.multi_file_summary',
  'dev.short_video_generator',
]

function isTemplateCartridge(item: CartridgeSummary) {
  const tags = item.branding?.tags || []
  return item.category === 'template' || tags.includes('template')
}

function sortTemplateCartridges(items: CartridgeSummary[]) {
  return [...items].sort((a, b) => {
    const aIndex = TEMPLATE_ORDER.indexOf(a.id)
    const bIndex = TEMPLATE_ORDER.indexOf(b.id)
    if (aIndex >= 0 || bIndex >= 0) {
      return (aIndex >= 0 ? aIndex : 999) - (bIndex >= 0 ? bIndex : 999)
    }
    return a.name.localeCompare(b.name, 'zh-CN')
  })
}

export default function ShelfPage() {
  const [items, setItems] = useState<CartridgeSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [active, setActive] = useState<CartridgeDetail | null>(null)
  const importPickerRef = useRef<HTMLInputElement | null>(null)
  const [importing, setImporting] = useState(false)

  const load = async () => {
    setLoading(true)
    setError('')
    try {
      const data = await fetchCartridges()
      setItems(data.items || [])
    } catch (e: any) {
      setError(e.message || '加载失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const openCartridge = async (id: string) => {
    try {
      const detail = await fetchCartridge(id)
      setActive(detail)
    } catch (e: any) {
      setError(e.message || '打开失败')
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
      setActive(result.cartridge)
    } catch (e: any) {
      const message = e.message || ''
      if (message.includes('already installed') && window.confirm('这个卡带已经安装。要覆盖更新吗？')) {
        try {
          const result = await importCartridgePackage(file, 'replace')
          showToast({ title: '卡带已覆盖更新', description: result.cartridge.id, type: 'success' })
          await load()
          setActive(result.cartridge)
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

  if (active) {
    return (
      <CartridgePlayer
        cartridge={active}
        onBack={() => { setActive(null); load() }}
        onOpen={async (id) => {
          const detail = await fetchCartridge(id)
          await load()
          setActive(detail)
        }}
      />
    )
  }

  const templateItems = sortTemplateCartridges(items.filter(isTemplateCartridge))
  const otherItems = items.filter((item) => !isTemplateCartridge(item))
  const renderCartridgeCard = (c: CartridgeSummary) => (
    <Card.Root key={c.id} className="cf-cartridge-card cf-shelf-card">
      <Card.Body p={0}>
        <HStack className="cf-card-top" justify="space-between" align="start" mb={3}>
          <Box>
            <Text className="cf-kicker" mb={1}>
              {c.category || 'cartridge'}
            </Text>
            <Heading className="cf-card-title" mb={0}>{c.name}</Heading>
          </Box>
          <Box className="cf-card-icon">CF</Box>
        </HStack>
        <Text className="cf-card-desc" minH="3.2em">{c.description || ''}</Text>
        <HStack mt={3} gap={2} flexWrap="wrap">
          <Badge className="cf-badge">{c.id}</Badge>
          <Badge className="cf-badge">v{c.version}</Badge>
          <Badge className="cf-badge">{c.runtime?.type || 'none'}</Badge>
          {c.source && <Badge className="cf-badge">{c.source}</Badge>}
        </HStack>
      </Card.Body>
      <Card.Footer p={0} pt={0}>
        <Button className="cf-accent-btn" w="100%" onClick={() => openCartridge(c.id)}>打开卡带</Button>
      </Card.Footer>
    </Card.Root>
  )

  return (
    <Box className="cf-page">
      <Box className="cf-page-inner">
      <HStack justify="space-between" className="cf-page-header">
        <VStack align="start" gap={1}>
          <Text className="cf-kicker">Cartridge Shelf</Text>
          <Heading size="lg" className="cf-page-title">卡带货架</Heading>
          <Text className="cf-page-subtitle">选择一张卡带开始运行</Text>
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
        </HStack>
      </HStack>

      {loading && <Spinner />}
      {error && <Text color="fg.error">{error}</Text>}
      {!loading && !error && items.length === 0 && (
        <Text color="fg.muted">暂无卡带。</Text>
      )}

      {!loading && !error && templateItems.length > 0 && (
        <Box className="cf-library-section">
          <HStack className="cf-section-header" justify="space-between" align="end">
            <Box>
              <Text className="cf-kicker">Template Library</Text>
              <Heading size="md" className="cf-section-title">模板卡带库</Heading>
              <Text className="cf-section-subtitle">打开就能跑的常用卡带，从文件总结、日志诊断到报告生成。</Text>
            </Box>
            <Badge className="cf-badge">{templateItems.length} 张模板</Badge>
          </HStack>
          <SimpleGrid className="cf-shelf-grid cf-cartridge-grid">
            {templateItems.map(renderCartridgeCard)}
          </SimpleGrid>
        </Box>
      )}

      {!loading && !error && otherItems.length > 0 && (
        <Box className="cf-library-section">
          <HStack className="cf-section-header" justify="space-between" align="end">
            <Box>
              <Text className="cf-kicker">Cartridges</Text>
              <Heading size="md" className="cf-section-title">其他卡带</Heading>
            </Box>
            <Badge className="cf-badge">{otherItems.length} 张</Badge>
          </HStack>
          <SimpleGrid className="cf-shelf-grid cf-cartridge-grid">
            {otherItems.map(renderCartridgeCard)}
          </SimpleGrid>
        </Box>
      )}
      </Box>
    </Box>
  )
}

// 卡带详情与运行播放器
function CartridgePlayer({ cartridge, onBack, onOpen }: { cartridge: CartridgeDetail; onBack: () => void; onOpen: (id: string) => Promise<void> }) {
  const [running, setRunning] = useState(false)
  const [runResult, setRunResult] = useState<RunResult | null>(null)
  const [runError, setRunError] = useState('')
  const [inputs, setInputs] = useState<Record<string, string>>({})
  const [packageResult, setPackageResult] = useState<{ url: string; filename: string; size: number; mcp_tool_count: number } | null>(null)
  const [packaging, setPackaging] = useState(false)
  const [uninstalling, setUninstalling] = useState(false)
  const [cloning, setCloning] = useState(false)
  const filePickerRef = useRef<HTMLInputElement | null>(null)
  const [uploadFieldId, setUploadFieldId] = useState('')
  const [uploadingFile, setUploadingFile] = useState(false)
  const [uploadInfo, setUploadInfo] = useState<{ fieldId: string; filename: string; path: string } | null>(null)

  const handleInput = (id: string, value: string) => {
    setInputs((prev) => ({ ...prev, [id]: value }))
  }

  const pickUploadFile = (id: string) => {
    setUploadFieldId(id)
    filePickerRef.current?.click()
  }

  const handleUploadFile = async (event: any) => {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file || !uploadFieldId) return
    setUploadingFile(true)
    try {
      const result = await uploadWorkspaceFile(file)
      handleInput(uploadFieldId, result.path)
      setUploadInfo({ fieldId: uploadFieldId, filename: result.filename, path: result.path })
      showToast({ title: '上传成功', description: result.path, type: 'success' })
    } catch (e: any) {
      showToast({ title: '上传失败', description: e.message, type: 'error' })
    } finally {
      setUploadingFile(false)
    }
  }

  const handleRun = async () => {
    setRunning(true)
    setRunError('')
    setRunResult(null)
    try {
      const result = await createCartridgeRun(cartridge.id, inputs)
      setRunResult(result)
      showToast({ title: '运行完成', type: 'success' })
    } catch (e: any) {
      setRunError(e.message || '运行失败')
    } finally {
      setRunning(false)
    }
  }

  const handlePackage = async () => {
    setPackaging(true)
    try {
      const result = await packageCartridge(cartridge.id)
      setPackageResult(result)
      showToast({ title: '卡带文件已生成', type: 'success' })
    } catch (e: any) {
      showToast({ title: '打包失败', description: e.message, type: 'error' })
    } finally {
      setPackaging(false)
    }
  }

  const handleUninstall = async () => {
    if (!window.confirm(`确定卸载这张已安装卡带吗？\n\n${cartridge.id}`)) return
    setUninstalling(true)
    try {
      await uninstallInstalledCartridge(cartridge.id)
      showToast({ title: '卡带已卸载', description: cartridge.id, type: 'success' })
      onBack()
    } catch (e: any) {
      showToast({ title: '卸载失败', description: e.message, type: 'error' })
    } finally {
      setUninstalling(false)
    }
  }

  const handleCloneToDev = async () => {
    const base = cartridge.id.replace(/^dev\./, '').replace(/[^a-zA-Z0-9._-]+/g, '.')
    const defaultId = `dev.${base}.copy`
    const newId = window.prompt('请输入新的 dev flow ID', defaultId)
    if (!newId) return
    const defaultName = `${cartridge.name || cartridge.id} Copy`
    const name = window.prompt('请输入新卡带名称', defaultName)
    if (!name) return
    setCloning(true)
    try {
      const result = await cloneCartridgeToDev(cartridge.id, newId, name, cartridge.description || '')
      showToast({ title: '已复制为可编辑版本', description: result.id, type: 'success' })
      await onOpen(result.id)
    } catch (e: any) {
      showToast({ title: '复制失败', description: e.message, type: 'error' })
    } finally {
      setCloning(false)
    }
  }

  const inputDefs: CartridgeInput[] = cartridge.inputs || cartridge.manifest?.inputs || []
  const mcpTools: McpTool[] = cartridge.mcp_tools || cartridge.manifest?.mcp_tools || []

  useEffect(() => {
    const defaults: Record<string, string> = {}
    ;(cartridge.inputs || cartridge.manifest?.inputs || []).forEach((input: CartridgeInput) => {
      const value = (input as any).default
      if (typeof value === 'string' && value) defaults[input.id] = value
    })
    setInputs(defaults)
    setUploadInfo(null)
  }, [cartridge.id])

  return (
    <Box className="cf-page">
      <Box className="cf-page-inner">
      <HStack mb={4}>
        <Button onClick={onBack}>← 返回货架</Button>
      </HStack>

      <Box className="cf-page-header">
        <Text className="cf-kicker">Cartridge Player</Text>
        <Heading size="lg" className="cf-page-title">{cartridge.name}</Heading>
      </Box>

      <div className="cf-shelf-detail-grid">
      <VStack align="stretch" gap={6}>
        <Box className="cf-soft-panel" p={5}>
          {cartridge.welcome_html_content ? (
            <iframe className="cf-welcome-html-frame" srcDoc={cartridge.welcome_html_content} title={`${cartridge.id} welcome`} />
          ) : (
            <div className="markdown-body">
              <ReactMarkdown>{cartridge.welcome_content || cartridge.description || '欢迎使用这张卡带。'}</ReactMarkdown>
            </div>
          )}
        </Box>

        <Separator />

        <Box className="cf-soft-panel" p={5}>
          <Heading size="md" mb={4}>输入参数</Heading>
          <VStack align="stretch" gap={4} className="cf-input-group">
            <input
              ref={filePickerRef}
              type="file"
              style={{ display: 'none' }}
              accept=".txt,.md,.markdown,.json,.csv,.log,.html,.htm,.xml,.yaml,.yml"
              onChange={handleUploadFile}
            />
            {inputDefs.length === 0 && <Text color="fg.muted">该卡带没有输入参数。</Text>}
            {inputDefs.map((input: CartridgeInput) => {
              const isFilePathInput = input.id === 'file_path'
              return (
              <Field.Root key={input.id}>
                <Field.Label>
                  {input.label || input.id}
                  {input.required && <Text color="fg.error" style={{ display: 'inline' }}> *</Text>}
                </Field.Label>
                {isFilePathInput && (
                  <HStack mb={2} gap={2} flexWrap="wrap">
                    <Button
                      className="cf-outline-btn"
                      onClick={() => pickUploadFile(input.id)}
                      loading={uploadingFile && uploadFieldId === input.id}
                      loadingText="\u4e0a\u4f20\u4e2d..."
                    >
                      {"\u4e0a\u4f20\u672c\u5730\u6587\u4ef6"}
                    </Button>
                    <Text fontSize="xs" color="fg.muted">
                      {uploadInfo?.fieldId === input.id ? `\u5df2\u4e0a\u4f20\uff1a${uploadInfo.filename}` : "\u4e0a\u4f20\u540e\u4f1a\u81ea\u52a8\u586b\u5165\u53ef\u8fd0\u884c\u8def\u5f84"}
                    </Text>
                  </HStack>
                )}
                {input.type === 'textarea' ? (
                  <Textarea
                    value={inputs[input.id] || ''}
                    onChange={(e) => handleInput(input.id, e.target.value)}
                    placeholder={input.placeholder}
                    rows={4}
                  />
                ) : input.type === 'select' ? (
                  <NativeSelect.Field
                    value={inputs[input.id] || ''}
                    onChange={(e) => handleInput(input.id, e.target.value)}
                  >
                    <option value="">请选择</option>
                    {(input.options || [
                      { value: 'feature', label: '新建功能' },
                      { value: 'bugfix', label: '修复 Bug' },
                      { value: 'refactor', label: '重构代码' },
                    ]).map((opt: { value: string; label: string }) => (
                      <option key={opt.value} value={opt.value}>{opt.label}</option>
                    ))}
                  </NativeSelect.Field>
                ) : (
                  <Input
                    value={inputs[input.id] || ''}
                    onChange={(e) => handleInput(input.id, e.target.value)}
                    placeholder={input.placeholder}
                  />
                )}
              </Field.Root>
            )})}
            <Button
              className="cf-accent-btn"
              onClick={handleRun}
              loading={running}
              loadingText="正在运行..."
              mt={2}
            >
              启动卡带
            </Button>
          </VStack>
        </Box>

        {runError && (
          <Box p={4} className="cf-soft-panel">
            <Text fontWeight="semibold" color="fg.error">运行失败</Text>
            <Text fontSize="sm" mt={1}>{runError}</Text>
          </Box>
        )}

        {runResult && <RunResultView run={runResult} />}
      </VStack>
      <VStack align="stretch" gap={4}>
        <Box className="cf-soft-panel" p={5}>
          <Heading size="md" mb={3}>卡带展开</Heading>
          <VStack align="stretch" gap={2}>
            <HStack justify="space-between"><Text>ID</Text><Badge className="cf-badge">{cartridge.id}</Badge></HStack>
            <HStack justify="space-between"><Text>Source</Text><Badge className="cf-badge">{cartridge.source || 'builtin'}</Badge></HStack>
            <HStack justify="space-between"><Text>Runtime</Text><Badge className="cf-badge">{cartridge.runtime?.type || 'none'}</Badge></HStack>
            <HStack justify="space-between"><Text>MCP 工具</Text><Badge className="cf-badge">{mcpTools.length}</Badge></HStack>
          </VStack>
          <Button className="cf-outline-btn" mt={4} onClick={handlePackage} loading={packaging} loadingText="打包中...">生成卡带文件</Button>
          {!cartridge.editable && (
            <Button className="cf-outline-btn" mt={2} onClick={handleCloneToDev} loading={cloning} loadingText="复制中...">
              复制为可编辑版本
            </Button>
          )}
          {cartridge.source === 'installed' && (
            <Button className="cf-danger-btn" mt={2} onClick={handleUninstall} loading={uninstalling} loadingText="卸载中...">
              卸载卡带
            </Button>
          )}
          {packageResult && (
            <Box mt={3}>
              <Link href={packageResult.url} className="cf-artifact-link">
                <HStack justify="space-between">
                  <Text>{packageResult.filename}</Text>
                  <Badge className="cf-badge">{Math.ceil(packageResult.size / 1024)} KB</Badge>
                </HStack>
              </Link>
            </Box>
          )}
        </Box>

        <Box className="cf-soft-panel" p={5}>
          <Heading size="md" mb={3}>MCP 工具库</Heading>
          <VStack align="stretch" gap={2}>
            {mcpTools.length === 0 && <Text color="fg.muted">这张卡带没有声明 MCP 工具。</Text>}
            {mcpTools.map((tool) => (
              <div key={tool.id} className="cf-mcp-tool-card">
                <HStack justify="space-between">
                  <Text fontWeight="semibold">{tool.name || tool.id}</Text>
                  <Badge className="cf-badge">{tool.enabled === false ? 'disabled' : tool.type || 'builtin'}</Badge>
                </HStack>
                <Text fontSize="xs" color="fg.muted">{tool.server}/{tool.tool}</Text>
                {tool.description && <Text fontSize="sm" mt={1}>{tool.description}</Text>}
              </div>
            ))}
          </VStack>
        </Box>
      </VStack>
      </div>
      </Box>
    </Box>
  )
}

// 运行结果展示
function RunResultView({ run }: { run: RunResult }) {
  const artifacts = run.delivery?.artifacts || run.artifacts || []
  const actions = run.delivery?.actions || []
  const copyText = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text)
      showToast({ title: '路径已复制', description: text, type: 'success' })
    } catch (e: any) {
      showToast({ title: '复制失败', description: e.message, type: 'error' })
    }
  }

  return (
    <Box p={5} className="cf-soft-panel">
      <Heading size="md" mb={3}>运行结果</Heading>
      <VStack align="stretch" gap={2}>
        <HStack><Text fontWeight="semibold" className="cf-label-fixed">Run ID:</Text><Text style={{ fontFamily: 'var(--cf-mono)' }}>{run.run_id}</Text></HStack>
        <HStack><Text fontWeight="semibold" className="cf-label-fixed">状态:</Text><Badge className="cf-badge">{run.status}</Badge></HStack>
        <HStack><Text fontWeight="semibold" className="cf-label-fixed">当前阶段:</Text><Text>{run.current_state}</Text></HStack>
        {run.delivery?.summary && (
          <HStack align="start"><Text fontWeight="semibold" className="cf-label-fixed">摘要:</Text><Text>{run.delivery.summary}</Text></HStack>
        )}
      </VStack>

      {artifacts.length > 0 && (
        <Box mt={4}>
          <Text fontWeight="semibold" mb={2}>输出文件</Text>
          <VStack align="stretch" gap={2}>
            {artifacts.map((item, i) => (
              <Box key={i} className="cf-artifact-link">
                <HStack justify="space-between" align="start" gap={3}>
                  <Box minW={0}>
                    <Text fontWeight="semibold">{item.name}</Text>
                    <Text fontSize="xs" color="fg.muted" style={{ overflowWrap: 'anywhere' }}>
                      {item.display_path || item.path || item.url}
                    </Text>
                  </Box>
                  <HStack gap={2} flexWrap="wrap" justify="end">
                    <Badge className="cf-badge">{item.type}</Badge>
                    <Link href={item.url}>
                      <Button className="cf-outline-btn">打开</Button>
                    </Link>
                    <Button className="cf-outline-btn" onClick={() => copyText(item.display_path || item.path || item.url)}>
                      复制路径
                    </Button>
                  </HStack>
                </HStack>
              </Box>
            ))}
          </VStack>
        </Box>
      )}

      {actions.length > 0 && (
        <HStack mt={4} gap={2} flexWrap="wrap">
          {actions.map((action, i) => (
            <Link key={i} href={action.url}>
              <Button className="cf-outline-btn">{action.label}</Button>
            </Link>
          ))}
        </HStack>
      )}
    </Box>
  )
}
