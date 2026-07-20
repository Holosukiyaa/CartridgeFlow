// LLM 设置页面：Provider 列表 + 新增/编辑/删除/激活 + 智能导入 + 导出 + 测试 + 快速设置
import { useEffect, useState } from 'react'
import {
  Box, Heading, Text, SimpleGrid, Card, Button, Badge, HStack, VStack,
  Spinner, Input, Textarea, Field, NativeSelect, Separator,
  Collapsible,
} from '../ui.tsx'
import {
  fetchLlmProviders, createLlmProvider, updateLlmProvider, deleteLlmProvider,
  activateLlmProvider, testLlmProvider, smartImportLlm, exportLlmConfig, quickSetProvider,
  type LlmProvider,
} from '../api.ts'
import { showToast } from '../toast.tsx'

export default function LlmPage() {
  const [providers, setProviders] = useState<LlmProvider[]>([])
  const [loading, setLoading] = useState(true)
  const [statusText, setStatusText] = useState('')
  const [showForm, setShowForm] = useState(false)
  const [editing, setEditing] = useState<LlmProvider | null>(null)
  const [importText, setImportText] = useState('')
  const [importResult, setImportResult] = useState('')

  const load = async () => {
    setLoading(true)
    setStatusText('加载中...')
    try {
      const data = await fetchLlmProviders()
      setProviders(data.providers || [])
      setStatusText((data.providers || []).length ? `共 ${data.providers.length} 个 Provider` : '尚未配置 Provider')
    } catch (e: any) {
      setStatusText(`加载失败：${e.message}`)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const handleActivate = async (id: string) => {
    try {
      await activateLlmProvider(id)
      showToast({ title: '已激活', type: 'success' })
      await load()
    } catch (e: any) {
      setStatusText(`激活失败：${e.message}`)
    }
  }

  const handleDelete = async (id: string) => {
    try {
      await deleteLlmProvider(id)
      showToast({ title: '已删除', type: 'success' })
      await load()
    } catch (e: any) {
      setStatusText(`删除失败：${e.message}`)
    }
  }

  const handleSmartImport = async () => {
    const content = importText.trim()
    if (!content) { setStatusText('请粘贴内容'); return }
    setStatusText('正在导入...')
    try {
      const data = await smartImportLlm(content)
      setImportResult(`成功导入 ${data.providers.length} 个 Provider${data.assignments_imported ? '（含 assignments）' : ''}`)
      setStatusText(`导入 ${data.providers.length} 个`)
      await load()
    } catch (e: any) {
      setStatusText(`导入失败：${e.message}`)
    }
  }

  const handleExport = async () => {
    try {
      const data = await exportLlmConfig()
      setImportText(JSON.stringify(data, null, 2))
      setStatusText('配置已导出到上方文本框')
    } catch (e: any) {
      setStatusText(`导出失败：${e.message}`)
    }
  }

  const handleTest = async (vision = false) => {
    setStatusText(vision ? '正在测试图片理解...' : '正在测试文本...')
    try {
      const active = providers.find((p) => p.enabled)
      if (!active) { setStatusText('没有激活的 Provider'); return }
      const data = await testLlmProvider(active.id, undefined, vision ? 'Inspect this image and reply with OK.' : undefined, vision)
      if (data.ok) {
        setImportResult(`${vision ? '图片测试' : '文本测试'}成功：${data.content || ''}`)
        setStatusText(vision ? '图片理解测试通过' : '文本测试通过')
      } else {
        setImportResult(`测试失败：${data.error || ''}`)
        setStatusText('测试失败')
      }
    } catch (e: any) {
      setStatusText(`测试失败：${e.message}`)
    }
  }

  return (
    <Box className="cf-page">
      <Box className="cf-page-inner">
      <HStack justify="space-between" className="cf-page-header">
        <VStack align="start" gap={1}>
          <Text className="cf-kicker">LLM Control Deck</Text>
          <Heading size="lg" className="cf-page-title">LLM 设置</Heading>
          <Text className="cf-page-subtitle">{statusText}</Text>
        </VStack>
        <HStack gap={2}>
          <Button className="cf-outline-btn" onClick={load}>刷新</Button>
          <Button className="cf-accent-btn" onClick={() => { setEditing(null); setShowForm(true) }}>新增 Provider</Button>
        </HStack>
      </HStack>

      {loading && <Spinner />}
      {!loading && providers.length === 0 && (
        <Card.Root className="cf-soft-panel">
          <Card.Body p={5}>
            <Text color="fg.muted">尚未配置 Provider，可点击「新增 Provider」或使用下方智能导入。</Text>
          </Card.Body>
        </Card.Root>
      )}

      <SimpleGrid className="cf-shelf-grid" mb={6}>
        {providers.map((p) => (
          <Card.Root key={p.id} className="cf-cartridge-card cf-provider-card">
            <Card.Body p={0}>
              <HStack className="cf-card-top" justify="space-between" align="start" mb={3}>
                <Box>
                  <Text className="cf-kicker" mb={1}>
                    {p.source || 'provider'}
                  </Text>
                  <Heading className="cf-card-title" mb={0}>{p.name}</Heading>
                </Box>
                <Box className="cf-card-icon">AI</Box>
              </HStack>
              <HStack gap={2} flexWrap="wrap" mb={2}>
                <Badge className="cf-badge">{p.api_type}</Badge>
                <Badge className="cf-badge">{p.default_model || 'no model'}</Badge>
                <Badge className="cf-badge">{p.has_key ? 'has key' : 'no key'}</Badge>
                {p.enabled && <Badge className="cf-badge">active</Badge>}
                {p.tested_ok && <Badge className="cf-badge">tested</Badge>}
              </HStack>
              <Text className="cf-card-desc">{p.base_url || ''} · {p.key_preview || '****'}</Text>
            </Card.Body>
            <Card.Footer p={0} pt={0}>
              <HStack gap={2} className="cf-card-actions">
                {!p.enabled && (
                  <Button className="cf-accent-btn" onClick={() => handleActivate(p.id)}>激活</Button>
                )}
                <Button className="cf-outline-btn" onClick={() => { setEditing(p); setShowForm(true) }}>编辑</Button>
                <Button className="cf-danger-btn" onClick={() => handleDelete(p.id)}>删除</Button>
              </HStack>
            </Card.Footer>
          </Card.Root>
        ))}
      </SimpleGrid>

      <Collapsible.Root open={showForm}>
        <Collapsible.Content>
          <ProviderForm
            editing={editing}
            onCancel={() => { setShowForm(false); setEditing(null) }}
            onSaved={async () => {
              setShowForm(false)
              setEditing(null)
              await load()
            }}
          />
        </Collapsible.Content>
      </Collapsible.Root>

      <Separator mb={24} />

      <Heading size="md" mb={3}>智能导入 / 导出 / 测试</Heading>
      <VStack align="stretch" gap={3} mb={4}>
        <Textarea
          value={importText}
          onChange={(e) => setImportText(e.target.value)}
          rows={6}
          fontFamily="mono"
          fontSize="sm"
          placeholder="粘贴 JSON 配置内容进行智能导入，或点击导出查看当前配置..."
        />
        <HStack gap={2} flexWrap="wrap">
          <Button className="cf-accent-btn" onClick={handleSmartImport}>智能导入</Button>
          <Button className="cf-outline-btn" onClick={handleExport}>导出配置</Button>
          <Button className="cf-outline-btn" onClick={() => handleTest(false)}>测试文本</Button>
          <Button className="cf-outline-btn" onClick={() => handleTest(true)}>测试看图</Button>
        </HStack>
        {importResult && (
          <Box p={3} className="cf-soft-panel">
            <Text fontSize="sm">{importResult}</Text>
          </Box>
        )}
      </VStack>

      <Separator mb={24} />

      <QuickSetup onSaved={async () => { await load() }} />
      </Box>
    </Box>
  )
}

// Provider 新增/编辑表单
function ProviderForm({ editing, onCancel, onSaved }: {
  editing: LlmProvider | null
  onCancel: () => void
  onSaved: () => void
}) {
  const [name, setName] = useState('')
  const [apiType, setApiType] = useState('openai')
  const [wireApi, setWireApi] = useState('chat_completions')
  const [baseUrl, setBaseUrl] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [defaultModel, setDefaultModel] = useState('')
  const [timeout, setProviderTimeout] = useState(120)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (editing) {
      setName(editing.name || '')
      setApiType(editing.api_type || 'openai')
      setWireApi(editing.wire_api || 'chat_completions')
      setBaseUrl(editing.base_url || '')
      setApiKey('')
      setDefaultModel(editing.default_model || '')
      setProviderTimeout(editing.timeout || 120)
    } else {
      setName('')
      setApiType('openai')
      setWireApi('chat_completions')
      setBaseUrl('')
      setApiKey('')
      setDefaultModel('')
      setProviderTimeout(120)
    }
  }, [editing])

  const handleSubmit = async () => {
    setSaving(true)
    try {
      const data: any = {
        name, api_type: apiType, wire_api: wireApi,
        base_url: baseUrl, default_model: defaultModel, timeout, enabled: true,
      }
      if (apiKey) data.api_key = apiKey
      if (editing) {
        await updateLlmProvider(editing.id, data)
        showToast({ title: '已更新', type: 'success' })
      } else {
        await createLlmProvider(data)
        showToast({ title: '已创建', type: 'success' })
      }
      onSaved()
    } catch (e: any) {
      showToast({ title: '保存失败', description: e.message, type: 'error' })
    } finally {
      setSaving(false)
    }
  }

  return (
    <Card.Root className="cf-soft-panel" style={{ padding: 20, marginBottom: 24 }}>
      <Card.Body>
        <Heading size="sm" mb={4}>{editing ? `编辑 ${editing.name}` : '新增 Provider'}</Heading>
        <SimpleGrid columns={2} gap={3}>
          <Field.Root>
            <Field.Label>名称</Field.Label>
            <Input value={name} onChange={(e) => setName(e.target.value)} />
          </Field.Root>
          <Field.Root>
            <Field.Label>api_type</Field.Label>
            <NativeSelect.Field value={apiType} onChange={(e) => setApiType(e.target.value)}>
              <option value="openai">openai</option>
              <option value="anthropic">anthropic</option>
            </NativeSelect.Field>
          </Field.Root>
          <Field.Root>
            <Field.Label>wire_api</Field.Label>
            <NativeSelect.Field value={wireApi} onChange={(e) => setWireApi(e.target.value)}>
              <option value="chat_completions">chat_completions</option>
              <option value="responses">responses</option>
              <option value="messages">messages</option>
            </NativeSelect.Field>
          </Field.Root>
          <Field.Root>
            <Field.Label>default_model</Field.Label>
            <Input value={defaultModel} onChange={(e) => setDefaultModel(e.target.value)} />
          </Field.Root>
          <Field.Root>
            <Field.Label>base_url</Field.Label>
            <Input value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} placeholder="https://api.openai.com/v1" />
          </Field.Root>
          <Field.Root>
            <Field.Label>timeout (秒)</Field.Label>
            <Input
              value={String(timeout)}
              onChange={(e) => setProviderTimeout(parseInt(e.target.value) || 120)}
            />
          </Field.Root>
          <Field.Root>
            <Field.Label>api_key {editing && '(留空则不修改)'}</Field.Label>
            <Input value={apiKey} onChange={(e) => setApiKey(e.target.value)} />
          </Field.Root>
        </SimpleGrid>
        <HStack gap={2} mt={4}>
          <Button className="cf-accent-btn" onClick={handleSubmit} loading={saving} loadingText="保存中...">
            {editing ? '更新' : '创建'}
          </Button>
          <Button onClick={onCancel}>取消</Button>
        </HStack>
      </Card.Body>
    </Card.Root>
  )
}

// 快速设置
function QuickSetup({ onSaved }: { onSaved: () => void }) {
  const [provider, setProvider] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [baseUrl, setBaseUrl] = useState('')
  const [model, setModel] = useState('')
  const [saving, setSaving] = useState(false)
  const [status, setStatus] = useState('')

  const handleSave = async () => {
    setSaving(true)
    setStatus('正在保存...')
    try {
      await quickSetProvider(provider, apiKey, baseUrl, model)
      setStatus('已保存并激活')
      showToast({ title: '已保存并激活', type: 'success' })
      onSaved()
    } catch (e: any) {
      setStatus(`保存失败：${e.message}`)
    } finally {
      setSaving(false)
    }
  }

  return (
    <Box>
      <Heading size="md" mb={3}>快速设置</Heading>
      <Card.Root className="cf-soft-panel">
        <Card.Body p={5}>
          <Text fontSize="sm" color="fg.muted" mb={3}>
            简易配置：根据 provider 名称自动判断 api_type（含 claude/anthropic 则用 anthropic）。
          </Text>
          <SimpleGrid columns={2} gap={3}>
            <Field.Root>
              <Field.Label>Provider 名称</Field.Label>
              <Input value={provider} onChange={(e) => setProvider(e.target.value)} placeholder="例如：openai / anthropic" />
            </Field.Root>
            <Field.Root>
              <Field.Label>API Key</Field.Label>
              <Input value={apiKey} onChange={(e) => setApiKey(e.target.value)} />
            </Field.Root>
            <Field.Root>
              <Field.Label>Base URL（可选）</Field.Label>
              <Input value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} />
            </Field.Root>
            <Field.Root>
              <Field.Label>Model</Field.Label>
              <Input value={model} onChange={(e) => setModel(e.target.value)} placeholder="例如：gpt-4o / claude-sonnet-4-20250514" />
            </Field.Root>
          </SimpleGrid>
          <HStack gap={2} mt={4}>
            <Button className="cf-accent-btn" onClick={handleSave} loading={saving} loadingText="保存中...">
              保存并激活
            </Button>
            {status && <Text fontSize="sm" color="fg.muted">{status}</Text>}
          </HStack>
        </Card.Body>
      </Card.Root>
    </Box>
  )
}
