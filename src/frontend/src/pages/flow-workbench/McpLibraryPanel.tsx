import { useEffect, useMemo, useState } from 'react'
import { Button } from '../../ui.tsx'
import type { FlowFiles, FlowNode, McpTool } from '../../api.ts'
import { getProtocolKind } from './nodeModel.ts'

type McpToolDraft = {
  id: string
  name: string
  type: string
  server: string
  tool: string
  description: string
  defaultParamsText: string
  paramsSchemaText: string
  enabled: boolean
}

const filesystemPresets: McpToolDraft[] = [
  {
    id: 'filesystem_write',
    name: 'Filesystem 写入文件',
    type: 'builtin',
    server: 'filesystem',
    tool: 'write_file',
    description: '把 AI 处理节点产出的内容写入工作区文件。',
    defaultParamsText: JSON.stringify({ path: 'test_output/result.txt', content: 'store:analysis_result' }, null, 2),
    paramsSchemaText: JSON.stringify({
      type: 'object',
      properties: {
        path: { type: 'string', description: '文件路径' },
        content: { type: 'string', description: '写入内容或 store:xxx 引用' },
      },
    }, null, 2),
    enabled: true,
  },
  {
    id: 'filesystem_read',
    name: 'Filesystem 读取文件',
    type: 'builtin',
    server: 'filesystem',
    tool: 'read_file',
    description: '读取工作区文件，并把内容写回节点输出。',
    defaultParamsText: JSON.stringify({ path: 'test_output/result.txt' }, null, 2),
    paramsSchemaText: JSON.stringify({
      type: 'object',
      properties: {
        path: { type: 'string', description: '文件路径' },
      },
    }, null, 2),
    enabled: true,
  },
  {
    id: 'filesystem_list',
    name: 'Filesystem 列出目录',
    type: 'builtin',
    server: 'filesystem',
    tool: 'list_dir',
    description: '列出工作区目录内容。',
    defaultParamsText: JSON.stringify({ path: '.' }, null, 2),
    paramsSchemaText: JSON.stringify({
      type: 'object',
      properties: {
        path: { type: 'string', description: '目录路径' },
      },
    }, null, 2),
    enabled: true,
  },
]

function parseJsonObject(text: string, fallback: Record<string, any> = {}) {
  try {
    const value = JSON.parse(text || '{}')
    return value && typeof value === 'object' && !Array.isArray(value) ? value : fallback
  } catch {
    return fallback
  }
}

function toDraft(tool?: Partial<McpTool>): McpToolDraft {
  const preset = filesystemPresets[0]
  return {
    id: tool?.id || preset.id,
    name: tool?.name || preset.name,
    type: tool?.type || preset.type,
    server: tool?.server || preset.server,
    tool: tool?.tool || preset.tool,
    description: tool?.description || preset.description,
    defaultParamsText: JSON.stringify(tool?.default_params || parseJsonObject(preset.defaultParamsText), null, 2),
    paramsSchemaText: JSON.stringify(tool?.params_schema || parseJsonObject(preset.paramsSchemaText), null, 2),
    enabled: tool?.enabled ?? true,
  }
}

function toPayload(draft: McpToolDraft): Partial<McpTool> {
  return {
    id: draft.id,
    name: draft.name,
    type: draft.type,
    server: draft.server,
    tool: draft.tool,
    description: draft.description,
    default_params: JSON.parse(draft.defaultParamsText || '{}'),
    params_schema: JSON.parse(draft.paramsSchemaText || '{}'),
    enabled: draft.enabled,
  }
}

function schemaFields(schemaText: string) {
  const schema = parseJsonObject(schemaText)
  const properties = schema.properties && typeof schema.properties === 'object' ? schema.properties : {}
  return Object.entries(properties).map(([key, value]) => {
    const field = value && typeof value === 'object' ? value as Record<string, any> : {}
    return {
      key,
      type: String(field.type || 'string'),
      description: String(field.description || ''),
      enumValues: Array.isArray(field.enum) ? field.enum.map((item) => String(item)) : [],
    }
  })
}

function formatParamValue(value: any) {
  if (value === undefined || value === null) return ''
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

function isCoreFilesystemTool(toolId?: string) {
  return filesystemPresets.some((preset) => preset.id === toolId)
}

export function McpLibraryPanel({ tools, selectedNode, files, onCreate, onUpdate, onDelete, onBindToNode }: {
  tools: McpTool[]
  selectedNode: FlowNode | null
  files: FlowFiles
  onCreate: (tool: Partial<McpTool>) => Promise<void>
  onUpdate: (toolId: string, tool: Partial<McpTool>) => Promise<void>
  onDelete: (toolId: string) => Promise<void>
  onBindToNode: (tool: McpTool) => Promise<void>
}) {
  const [editingId, setEditingId] = useState<string | null>(tools[0]?.id || null)
  const current = useMemo(() => tools.find((tool) => tool.id === editingId), [editingId, tools])
  const [draft, setDraft] = useState<McpToolDraft>(() => toDraft(current))
  const [error, setError] = useState('')
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null)
  const selectedKind = getProtocolKind(selectedNode)
  const selectedIsTool = selectedKind === 'mcp_read' || selectedKind === 'mcp_execute' || selectedKind === 'remote_call' || selectedNode?.action === 'tool_call' || selectedNode?.action === 'remote_call' || selectedNode?.params?.node_category === 'tool' || selectedNode?.params?.node_category === 'remote'
  const installedIds = useMemo(() => new Set(tools.map((tool) => tool.id)), [tools])
  const missingPresets = useMemo(() => filesystemPresets.filter((preset) => !installedIds.has(preset.id)), [installedIds])
  const paramFields = useMemo(() => schemaFields(draft.paramsSchemaText), [draft.paramsSchemaText])
  const paramValues = useMemo(() => parseJsonObject(draft.defaultParamsText), [draft.defaultParamsText])

  const setParamValue = (key: string, value: any) => {
    const next = { ...parseJsonObject(draft.defaultParamsText), [key]: value }
    setDraft({ ...draft, defaultParamsText: JSON.stringify(next, null, 2) })
  }

  useEffect(() => {
    if (!editingId && tools[0]) {
      setEditingId(tools[0].id)
      setDraft(toDraft(tools[0]))
    }
    if (editingId && !tools.some((tool) => tool.id === editingId)) {
      const next = tools[0]
      setEditingId(next?.id || null)
      setDraft(toDraft(next))
    }
  }, [editingId, tools])

  const resetDraft = (tool?: Partial<McpTool>) => {
    setError('')
    setPendingDeleteId(null)
    setDraft(toDraft(tool))
  }

  const selectTool = (tool: McpTool) => {
    setEditingId(tool.id)
    resetDraft(tool)
  }

  const usePreset = (preset: McpToolDraft) => {
    setEditingId(null)
    setDraft({ ...preset })
    setError('')
    setPendingDeleteId(null)
  }

  const addPreset = async (preset: McpToolDraft) => {
    setError('')
    setPendingDeleteId(null)
    try {
      await onCreate(toPayload(preset))
      setEditingId(preset.id)
      setDraft({ ...preset })
    } catch (e: any) {
      setError(e.message || '添加工具失败')
    }
  }

  const restoreDefaults = async () => {
    setError('')
    setPendingDeleteId(null)
    try {
      for (const preset of missingPresets) {
        await onCreate(toPayload(preset))
      }
      if (missingPresets[0]) {
        setEditingId(missingPresets[0].id)
        setDraft({ ...missingPresets[0] })
      }
    } catch (e: any) {
      setError(e.message || '恢复默认工具失败')
    }
  }

  const save = async () => {
    setError('')
    setPendingDeleteId(null)
    try {
      const payload = toPayload(draft)
      if (editingId) await onUpdate(editingId, payload)
      else await onCreate(payload)
      setEditingId(payload.id || editingId)
    } catch (e: any) {
      setError(e.message || '保存失败：请检查默认参数 JSON')
    }
  }

  const requestDelete = async () => {
    if (!current) return
    if (pendingDeleteId !== current.id) {
      setPendingDeleteId(current.id)
      setError(isCoreFilesystemTool(current.id)
        ? '这是常用 filesystem 工具。确定要删除的话，再点一次“确认删除”。误删后可用“恢复默认工具”找回。'
        : '再点一次“确认删除”才会真正删除。')
      return
    }
    setError('')
    await onDelete(current.id)
    setPendingDeleteId(null)
  }

  return (
    <div className="cf-mcp-library">
      <div className="cf-mcp-library-head">
        <span>已安装 {tools.length} 个工具</span>
        <Button className="cf-outline-btn" disabled={!missingPresets.length} onClick={restoreDefaults}>
          {missingPresets.length ? `恢复默认工具 · 缺 ${missingPresets.length}` : '默认工具完整'}
        </Button>
      </div>

      <div className="cf-mcp-section-title">
        <b>已安装工具</b>
        <small>点击左侧卡片查看和编辑。核心工具误删后可一键恢复。</small>
      </div>
      <div className="cf-mcp-tool-list">
        {tools.length === 0 && (
          <div className="cf-mcp-empty">
            还没有工具。建议先点“恢复默认工具”，会添加 filesystem 写入、读取、列目录。
          </div>
        )}
        {tools.map((tool) => (
          <button key={tool.id} type="button" className={editingId === tool.id ? 'active' : ''} onClick={() => selectTool(tool)}>
            <b>{tool.name || tool.id}</b>
            <small>{tool.server}/{tool.tool}</small>
            {isCoreFilesystemTool(tool.id) && <em>默认</em>}
          </button>
        ))}
      </div>

      <div className="cf-mcp-section-title">
        <b>快速添加模板</b>
        <small>只显示未安装的模板，避免重复添加。</small>
      </div>
      <div className="cf-mcp-presets">
        {filesystemPresets.map((preset) => {
          const installed = installedIds.has(preset.id)
          return (
            <button key={preset.id} type="button" disabled={installed} onClick={() => installed ? usePreset(preset) : addPreset(preset)}>
              <span>{installed ? '✓ 已安装' : '+ 添加'}</span>
              <b>{preset.name}</b>
              <small>{preset.server}/{preset.tool}</small>
            </button>
          )
        })}
      </div>

      <div className="cf-mcp-section-title">
        <b>{editingId ? '编辑工具' : '新增工具'}</b>
        <small>{editingId ? '修改后点保存。删除需要二次确认。' : '可从模板添加，也可以手动填写。'}</small>
      </div>
      <div className="cf-mcp-editor">
        <label>ID<input value={draft.id} disabled={Boolean(editingId)} onChange={(e) => setDraft({ ...draft, id: e.target.value })} /></label>
        <label>名称<input value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} /></label>
        <label>Server<input value={draft.server} onChange={(e) => setDraft({ ...draft, server: e.target.value })} /></label>
        <label>Tool<input value={draft.tool} onChange={(e) => setDraft({ ...draft, tool: e.target.value })} /></label>
        <label>说明<textarea rows={2} value={draft.description} onChange={(e) => setDraft({ ...draft, description: e.target.value })} /></label>
        {paramFields.length > 0 && (
          <div className="cf-mcp-param-fields">
            <div className="cf-mcp-param-title">
              <b>参数字段</b>
              <small>由 params_schema 生成，保存后同步到默认参数 JSON。</small>
            </div>
            {paramFields.map((field) => (
              <label key={field.key}>
                {field.key}
                {field.enumValues.length > 0 ? (
                  <select value={formatParamValue(paramValues[field.key])} onChange={(e) => setParamValue(field.key, e.target.value)}>
                    <option value="">未设置</option>
                    {field.enumValues.map((item) => <option key={item} value={item}>{item}</option>)}
                  </select>
                ) : field.type === 'boolean' ? (
                  <input type="checkbox" checked={Boolean(paramValues[field.key])} onChange={(e) => setParamValue(field.key, e.target.checked)} />
                ) : (
                  <input
                    type={field.type === 'integer' || field.type === 'number' ? 'number' : 'text'}
                    value={formatParamValue(paramValues[field.key])}
                    onChange={(e) => setParamValue(field.key, field.type === 'integer'
                      ? Number.parseInt(e.target.value || '0', 10)
                      : field.type === 'number'
                        ? Number.parseFloat(e.target.value || '0')
                        : e.target.value)}
                  />
                )}
                {field.description && <small>{field.description}</small>}
              </label>
            ))}
          </div>
        )}
        <label>默认参数 JSON<textarea rows={5} value={draft.defaultParamsText} onChange={(e) => setDraft({ ...draft, defaultParamsText: e.target.value })} /></label>
        <label>参数 Schema JSON<textarea rows={4} value={draft.paramsSchemaText} onChange={(e) => setDraft({ ...draft, paramsSchemaText: e.target.value })} /></label>
        <label className="cf-mcp-check"><input type="checkbox" checked={draft.enabled} onChange={(e) => setDraft({ ...draft, enabled: e.target.checked })} /> 启用</label>
      </div>

      {error && <p className="cf-mcp-error">{error}</p>}

      <div className="cf-mcp-actions">
        <Button className="cf-accent-btn" onClick={save}>{editingId ? '保存工具' : '新增工具'}</Button>
        {current && (
          <Button className={`cf-outline-btn ${pendingDeleteId === current.id ? 'danger' : ''}`} onClick={requestDelete}>
            {pendingDeleteId === current.id ? '确认删除' : '删除'}
          </Button>
        )}
        {current && <Button className="cf-outline-btn" disabled={!selectedIsTool} onClick={() => onBindToNode(current)}>绑定到当前工具节点</Button>}
      </div>

      <p className="cf-mcp-hint">
        工具库会写入 manifest.mcp_tools，并随卡带一起打包。当前选中节点：{selectedNode ? selectedNode.title : '无'}。
        {files.manifest ? '' : ' 当前文件缓存为空，请先等待 Flow 加载。'}
      </p>
    </div>
  )
}
