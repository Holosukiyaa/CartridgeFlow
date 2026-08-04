import { useEffect, useMemo, useState } from 'react'
import { BrainCircuit, CheckCircle2, CircleAlert, Cloud, Loader2, RefreshCw, Settings, ShieldCheck, Shuffle, Upload, UserCheck, Wrench } from 'lucide-react'
import { ApiError, fetchDeveloperFlowNodeTrustedReadiness, fetchDeveloperTrustedNodePublications, publishDeveloperFlowNode } from '../../api.ts'
import type { DeveloperTrustedNodePublication, DeveloperTrustedNodeReadiness, FlowNode } from '../../api.ts'
import { showToast } from '../../toast.tsx'
import type { NodeCategoryId } from './types.ts'

type EditableCandidate = {
  id: string
  label: string
  path: string
  value_type: 'string' | 'string_list' | 'boolean' | 'number'
  default: string | string[] | boolean | number
}

const forbiddenCreatorField = /token|secret|password|credential|api[_-]?key|authorization|cookie|private[_-]?key|code|script|command|executor|permission|topology|execution[_-]?plan|endpoint|model|tool/i
const internalCreatorField = new Set(['node_category', 'preset', 'output_name', 'from', 'to', 'source', 'path', 'key', 'server', 'service', 'resource_role', 'model_role'])

const capabilityStarters: Array<{
  id: string
  label: string
  categoryId: NodeCategoryId
  presetId: string
  icon: typeof BrainCircuit
}> = [
  { id: 'ai', label: 'AI 处理', categoryId: 'process', presetId: 'analyze', icon: BrainCircuit },
  { id: 'tool', label: '工具执行', categoryId: 'tool', presetId: 'filesystem_read', icon: Wrench },
  { id: 'remote', label: '远程服务', categoryId: 'remote', presetId: 'remote_mcp_call', icon: Cloud },
  { id: 'transform', label: '确定性处理', categoryId: 'transfer', presetId: 'pass', icon: Shuffle },
  { id: 'review', label: '人工审核', categoryId: 'control', presetId: 'confirm', icon: UserCheck },
]

function stableId(value: string, fallback: string) {
  let result = value.toLowerCase().replace(/[^a-z0-9_.-]+/g, '-').replace(/^[^a-z]+/, '').replace(/[.-]+$/, '')
  if (!result) result = fallback
  return result.slice(0, 120)
}

function editableCandidates(node: FlowNode | null): EditableCandidate[] {
  const found: EditableCandidate[] = []
  const seen = new Set<string>()
  const walk = (value: unknown, parts: string[]) => {
    if (parts.length > 5) return
    if (typeof value === 'string' && value.trim()) add('string', value)
    else if (typeof value === 'boolean') add('boolean', value)
    else if (typeof value === 'number' && Number.isFinite(value)) add('number', value)
    else if (Array.isArray(value) && value.length > 0 && value.every((item) => typeof item === 'string' && item.trim())) add('string_list', value as string[])
    else if (value && typeof value === 'object' && !Array.isArray(value)) {
      Object.entries(value as Record<string, unknown>).forEach(([key, child]) => walk(child, [...parts, key]))
    }
    function add(value_type: EditableCandidate['value_type'], defaultValue: EditableCandidate['default']) {
      if (!parts.length || parts.some((part) => forbiddenCreatorField.test(part) || internalCreatorField.has(part.toLowerCase()))) return
      let id = stableId(parts.join('_'), 'field').replace(/[.-]/g, '_')
      while (seen.has(id)) id = `${id}_value`
      seen.add(id)
      found.push({ id, label: parts[parts.length - 1].replace(/[_-]+/g, ' '), path: `params.${parts.join('.')}`, value_type, default: defaultValue })
    }
  }
  if (node?.params) Object.entries(node.params).forEach(([key, value]) => walk(value, [key]))
  return found
}

function readinessMessage(readiness: DeveloperTrustedNodeReadiness | null) {
  const code = readiness?.blocker?.code || ''
  if (code === 'TRUSTED_NODE_MAPPING_NODE_INVALID') return '所选节点还不是完整的可执行 process 节点。'
  if (code === 'TRUSTED_NODE_MAPPING_ACTION_UNSUPPORTED') return '当前动作不在 Base 可执行动作清单中，请更换执行动作。'
  if (code === 'TRUSTED_NODE_MAPPING_RESOURCE_UNSUPPORTED') return '该节点依赖包内 UI 或 DLC，暂时不能作为单节点能力复用。'
  if (code === 'TRUSTED_NODE_MAPPING_TOPOLOGY_UNSUPPORTED') return '该节点包含跳转目标；可信节点必须只描述一个可独立复用的能力。'
  if (code === 'TRUSTED_NODE_MAPPING_REQUIREMENT_MISSING') return '节点引用的模型、工具或权限尚未在当前卡带中声明。'
  if (code === 'TRUSTED_NODE_SOURCE_FLOW_READ_ONLY') return '只读卡带不能发布可信节点，请先复制为可编辑版本。'
  if (code === 'TRUSTED_NODE_SOURCE_UNKNOWN') return '所选节点已经不存在，请重新选择。'
  return readiness?.blocker?.message || '当前节点尚未达到可信发布条件。'
}

export function TrustedNodePanel({ flowId, selectedNode, onCreateCapability, onConfigureNode }: {
  flowId: string
  selectedNode: FlowNode | null
  onCreateCapability: (categoryId: NodeCategoryId, presetId: string) => Promise<FlowNode | undefined>
  onConfigureNode: () => void
}) {
  const [publications, setPublications] = useState<DeveloperTrustedNodePublication[]>([])
  const [loading, setLoading] = useState(true)
  const [publishing, setPublishing] = useState(false)
  const [creatingId, setCreatingId] = useState('')
  const [readiness, setReadiness] = useState<DeveloperTrustedNodeReadiness | null>(null)
  const [checking, setChecking] = useState(false)
  const [presetId, setPresetId] = useState('')
  const [label, setLabel] = useState('')
  const [description, setDescription] = useState('')
  const [terms, setTerms] = useState('')
  const [selectedFields, setSelectedFields] = useState<Set<string>>(new Set())
  const candidates = useMemo(() => editableCandidates(selectedNode), [selectedNode])
  const eligible = selectedNode?.type === 'process'

  const load = async () => {
    setLoading(true)
    try {
      const response = await fetchDeveloperTrustedNodePublications()
      setPublications(response.publications || [])
    } catch (error) {
      showToast({ title: '可信节点读取失败', description: error instanceof Error ? error.message : String(error), type: 'error' })
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void load() }, [])
  useEffect(() => {
    let active = true
    setReadiness(null)
    if (!selectedNode) return () => { active = false }
    setChecking(true)
    void fetchDeveloperFlowNodeTrustedReadiness(flowId, selectedNode.id)
      .then((result) => { if (active) setReadiness(result) })
      .catch((error) => {
        if (!active) return
        setReadiness({
          schema: 'cartridgeflow.developer_trusted_node_readiness.v1',
          flow_id: flowId,
          node_id: selectedNode.id,
          ready: false,
          blocker: { code: 'TRUSTED_NODE_READINESS_FAILED', message: error instanceof Error ? error.message : String(error) },
        })
      })
      .finally(() => { if (active) setChecking(false) })
    return () => { active = false }
  }, [flowId, selectedNode])
  useEffect(() => {
    if (!selectedNode) return
    const title = selectedNode.display_name || selectedNode.title || selectedNode.id
    setPresetId(stableId(selectedNode.id, 'trusted-node'))
    setLabel(title)
    setDescription(selectedNode.description || `复用已经由 Developer 配置并发布的“${title}”能力。`)
    setTerms([title, selectedNode.kind || ''].filter((item) => item && !forbiddenCreatorField.test(item)).join(', '))
    setSelectedFields(new Set())
  }, [selectedNode?.id])

  const publish = async () => {
    if (!selectedNode || !eligible || !readiness?.ready) return
    const matchTerms = terms.split(/[,，\n]/).map((item) => item.trim()).filter(Boolean)
    if (!presetId.trim() || !label.trim() || !description.trim() || !matchTerms.length) {
      showToast({ title: '请补全可信能力说明', type: 'warning' })
      return
    }
    const fields = candidates.filter((item) => selectedFields.has(item.path))
    setPublishing(true)
    try {
      const result = await publishDeveloperFlowNode(flowId, selectedNode.id, {
        preset_id: stableId(presetId, 'trusted-node'),
        creator_label: label.trim(),
        creator_description: description.trim(),
        match_terms: matchTerms,
        editable_fields: fields.map(({ id, label: fieldLabel, value_type, default: defaultValue }) => ({
          id, label: fieldLabel, value_type, required: true, default: defaultValue,
        })),
        creator_bindings: Object.fromEntries(fields.map((item) => [item.id, item.path])),
      })
      setPublications((current) => [result.publication, ...current.filter((item) => item.preset.id !== result.publication.preset.id)])
      showToast({ title: '可信节点已发布', description: `${result.publication.preset.creator_label} · v${result.publication.preset.revision}`, type: 'success' })
    } catch (error) {
      const message = error instanceof ApiError ? error.message : error instanceof Error ? error.message : String(error)
      showToast({ title: '可信节点发布失败', description: message, type: 'error' })
    } finally {
      setPublishing(false)
    }
  }

  const createCapability = async (starter: (typeof capabilityStarters)[number]) => {
    setCreatingId(starter.id)
    try {
      await onCreateCapability(starter.categoryId, starter.presetId)
    } finally {
      setCreatingId('')
    }
  }

  return <div className="cf-trusted-node-panel cf-canvas-tool-content">
    <section className="cf-trusted-node-source">
      <div className="cf-trusted-node-heading"><span className="cf-trusted-node-step">1</span><span><strong>新建或选择执行节点</strong><small>新建后仍需完成 Developer 执行配置</small></span></div>
      <div className="cf-trusted-node-starters">
        {capabilityStarters.map((starter) => {
          const Icon = starter.icon
          return <button type="button" key={starter.id} disabled={Boolean(creatingId)} onClick={() => void createCapability(starter)} title={`新建${starter.label}节点`}>
            {creatingId === starter.id ? <Loader2 className="spinning" aria-hidden="true" /> : <Icon aria-hidden="true" />}
            <span>{starter.label}</span>
          </button>
        })}
      </div>
      {!selectedNode && <p className="cf-trusted-node-empty">也可以先在画布上选择一个已有的 process 节点。</p>}
      {selectedNode && <div className="cf-trusted-node-selected"><CheckCircle2 aria-hidden="true" /><span><strong>{selectedNode.display_name || selectedNode.title}</strong><small>{selectedNode.action || '未配置动作'} · {selectedNode.executor || '未配置执行器'} · {selectedNode.effect || '未配置副作用'}</small></span></div>}
    </section>

    <section className="cf-trusted-node-readiness">
      <div className="cf-trusted-node-heading"><span className="cf-trusted-node-step">2</span><span><strong>确认执行映射</strong><small>检查该节点能否形成独立、可移植的执行快照</small></span></div>
      {!selectedNode && <p className="cf-trusted-node-empty">选择或新建节点后，这里会显示阻断项。</p>}
      {selectedNode && checking && <div className="cf-trusted-node-checking"><Loader2 className="spinning" aria-hidden="true" /><span>正在检查节点</span></div>}
      {selectedNode && !checking && readiness?.ready && <div className="cf-trusted-node-status ready"><CheckCircle2 aria-hidden="true" /><span><strong>执行映射已就绪</strong><small>{readiness.action} · {readiness.executor} · {readiness.effect}</small></span></div>}
      {selectedNode && !checking && readiness && !readiness.ready && <div className="cf-trusted-node-status blocked"><CircleAlert aria-hidden="true" /><span><strong>还不能发布</strong><small>{readinessMessage(readiness)}</small></span></div>}
      {selectedNode && <button type="button" className="cf-trusted-node-configure" onClick={onConfigureNode}><Settings aria-hidden="true" /><span>编辑节点执行配置</span></button>}
    </section>

    <section className="cf-trusted-node-publish-stage">
      <div className="cf-trusted-node-heading"><span className="cf-trusted-node-step">3</span><span><strong>发布给 Creator</strong><small>发布后生成不可变版本，Creator 只能修改明确开放的字段</small></span></div>
      {selectedNode && readiness?.ready && <div className="cf-trusted-node-form">
        <div className="cf-trusted-node-selected"><CheckCircle2 aria-hidden="true" /><span><strong>{selectedNode.display_name || selectedNode.title}</strong><small>{selectedNode.action} · {selectedNode.executor} · {selectedNode.effect}</small></span></div>
        <label><span>可信能力 ID</span><input value={presetId} onChange={(event) => setPresetId(event.target.value)} /></label>
        <label><span>Creator 中的名称</span><input value={label} onChange={(event) => setLabel(event.target.value)} /></label>
        <label><span>能力说明</span><textarea rows={3} value={description} onChange={(event) => setDescription(event.target.value)} /></label>
        <label><span>AI 匹配词</span><input value={terms} onChange={(event) => setTerms(event.target.value)} placeholder="日报, RSS, 信息收集" /></label>
        <fieldset>
          <legend>允许 Creator 调整的参数</legend>
          {candidates.length ? candidates.map((item) => <label key={item.path} className="cf-trusted-node-field">
            <input type="checkbox" checked={selectedFields.has(item.path)} onChange={(event) => setSelectedFields((current) => {
              const next = new Set(current)
              if (event.target.checked) next.add(item.path); else next.delete(item.path)
              return next
            })} />
            <span><strong>{item.label}</strong><small>{item.path} · {item.value_type}</small></span>
          </label>) : <p>这个节点没有可安全开放的 `params` 字段，将作为固定能力发布。</p>}
        </fieldset>
        <button type="button" className="cf-trusted-node-publish" onClick={() => void publish()} disabled={publishing}><Upload aria-hidden="true" />{publishing ? '正在发布' : '发布可信节点'}</button>
      </div>}
      {(!selectedNode || !readiness?.ready) && <p className="cf-trusted-node-empty">执行映射通过后，发布信息会在这里开放。</p>}
    </section>
    <section className="cf-trusted-node-registry">
      <header><span><strong>已发布能力</strong><small>{publications.length} 个可供 Creator 复用</small></span><button type="button" onClick={() => void load()} disabled={loading} title="刷新可信节点"><RefreshCw aria-hidden="true" /></button></header>
      {publications.length ? publications.map((item) => <article key={item.digest}>
        <ShieldCheck aria-hidden="true" />
        <span><strong>{item.preset.creator_label}</strong><small>{item.preset.id} · v{item.preset.revision} · {item.mapping.source.flow_id}/{item.mapping.source.node_id}</small></span>
      </article>) : <p className="cf-trusted-node-empty">还没有可信能力。Developer 发布第一个节点后，Creator 才能用 AI 编排它。</p>}
    </section>
  </div>
}
