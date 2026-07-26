import { useEffect, useState, type ReactNode } from 'react'
import { Badge, Button, Field, Heading, Input, NativeSelect, Text, Textarea, VStack } from '../../ui.tsx'
import { Activity, ArrowLeftRight, Box, ClipboardCopy, Download, FileText, GitBranch, GripHorizontal, Pin, PinOff, Trash2, Wrench, X } from 'lucide-react'
import { updateFlowNode, type FlowEdge, type FlowEvent, type FlowFiles, type FlowNode } from '../../api.ts'
import { normalizeRecipeRoles } from '../../llmRecipe.ts'
import { showToast } from '../../toast.tsx'
import type { GraphResult, NodeCategoryId, NodeDraft } from './types.ts'
import { CATEGORY_BY_ID, NODE_CATEGORIES, buildProtocolNodePayload, getNodeCategory, getProcessDisplayLabel, getPreset, getPresets, getProtocolDefaults, makeNodeDraft } from './nodeModel.ts'
import type { NodeRunState } from './runState.ts'

const RUN_STATE_LABELS: Record<NodeRunState['status'], string> = {
  idle: '尚未执行',
  running: '正在执行',
  completed: '执行完成',
  failed: '执行失败',
  paused: '等待继续',
}

function detailValue(value: unknown, fallback = '未配置') {
  if (value === undefined || value === null || value === '') return fallback
  if (Array.isArray(value)) return value.length ? value.join(', ') : fallback
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

async function copyText(value: string) {
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(value)
      return
    } catch {
      // Use the local-page fallback below.
    }
  }
  const field = document.createElement('textarea')
  field.value = value
  field.style.position = 'fixed'
  field.style.opacity = '0'
  document.body.appendChild(field)
  field.select()
  const copied = document.execCommand('copy')
  field.remove()
  if (!copied) throw new Error('Clipboard access is unavailable')
}

function DetailFact({ label, value, mono = false }: { label: string; value: unknown; mono?: boolean }) {
  const text = detailValue(value)
  return <div><dt>{label}</dt><dd className={mono ? 'mono' : ''} title={text}>{text}</dd></div>
}

function readInteractionComponents(files: FlowFiles) {
  try {
    const document = JSON.parse(files.interaction_components || '{}')
    return Array.isArray(document.components) ? document.components : []
  } catch {
    return []
  }
}

function readModelRoles(files: FlowFiles) {
  try {
    const manifest = JSON.parse(files.manifest || '{}')
    return normalizeRecipeRoles(manifest.llm_recipe)
  } catch {
    return []
  }
}

function DrawerSection({ title, summary, children, defaultOpen = false }: { title: string; summary?: string; children: ReactNode; defaultOpen?: boolean }) {
  const [isOpen, setIsOpen] = useState(defaultOpen)
  return (
    <section className={`cf-drawer-block ${isOpen ? 'open' : ''}`}>
      <button type="button" className="cf-drawer-block-head" onClick={() => setIsOpen((value) => !value)}>
        <span><b>{title}</b>{summary && <small>{summary}</small>}</span>
        <em aria-hidden="true">{isOpen ? '−' : '+'}</em>
      </button>
      {isOpen ? <div className="cf-drawer-block-content">{children}</div> : null}
    </section>
  )
}

export function NodeDrawer({ node, graphEdges, flowId, files, editable, open, pinned, showSummary = true, runState, runEvents = [], onTogglePin, onClose, onDelete, onSaved }: {
  node: FlowNode | null
  graphEdges: FlowEdge[]
  flowId: string
  files: FlowFiles
  editable: boolean
  open: boolean
  pinned: boolean
  showSummary?: boolean
  runState?: NodeRunState
  runEvents?: FlowEvent[]
  onTogglePin: () => void
  onClose: () => void
  onDelete?: () => Promise<void> | void
  onSaved: (result: GraphResult) => void
}) {
  const [draft, setDraft] = useState<NodeDraft | null>(node ? makeNodeDraft(node) : null)
  const [saving, setSaving] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const category = draft ? CATEGORY_BY_ID.get(draft.category) || getNodeCategory(node) : null
  const presets = category && draft ? getPresets(draft.category) : []
  const activePreset = category && draft ? getPreset(draft.category, draft.preset) : null
  const isCustom = draft?.category === 'custom'
  const isInteraction = draft?.category === 'interaction'
  const isLlmDecision = draft?.kind === 'decision' && draft.executor === 'llm'
  const interactionComponents = readInteractionComponents(files)
  const modelRoles = readModelRoles(files)
  const incomingEdges = node ? graphEdges.filter((edge) => edge.to === node.id) : []
  const outgoingEdges = node ? graphEdges.filter((edge) => edge.from === node.id) : []

  useEffect(() => {
    setDraft(node ? makeNodeDraft(node) : null)
  }, [node?.id])

  if (!open || !node || !draft || !category) return null

  const readOnly = !editable || node.locked || node.scope === 'root'
  const updateDraft = (patch: Partial<NodeDraft>) => {
    if (readOnly) return
    setDraft((current) => current ? { ...current, ...patch } : current)
  }

  const changeCategory = (categoryId: NodeCategoryId) => {
    const nextCategory = CATEGORY_BY_ID.get(categoryId)!
    const nextPreset = getPreset(nextCategory.id)
    const defaults = getProtocolDefaults(nextCategory.id, nextPreset.id)
    updateDraft({
      category: nextCategory.id,
      preset: nextPreset.id,
      presetConfig: {},
      type: defaults.type,
      action: defaults.action,
      kind: defaults.kind,
      executor: defaults.executor,
      effect: defaults.effect,
      displaySuffix: defaults.displaySuffix,
      inputKind: defaults.inputKind || '',
      source: defaults.source || '',
      inputSchema: defaults.inputSchema || '',
      outputContract: defaults.outputContract || '',
      decisionContract: defaults.decisionContract ? JSON.stringify(defaults.decisionContract, null, 2) : '',
      decisionTestMode: '',
      mockDecisionEnvelope: '',
      toolBinding: defaults.toolBinding || '',
      failurePolicy: defaults.failurePolicy || '',
      permission: defaults.permission || '',
      auditLog: Boolean(defaults.auditLog),
      displayName: draft.displayName || draft.title || nextCategory.defaultTitle,
      componentRef: nextCategory.id === 'interaction' ? interactionComponents[0]?.id || '' : '',
      interactionMode: nextCategory.id === 'interaction' ? 'display' : '',
      inputBinding: '{}',
      actionRoutes: '{}',
      title: draft.title || nextCategory.defaultTitle,
    })
  }

  const save = async () => {
    if (readOnly) return
    let toolsParsed: any = null
    let paramsParsed: any = {}
    try {
      if (draft.tools.trim()) toolsParsed = JSON.parse(draft.tools)
      if (draft.params.trim()) paramsParsed = JSON.parse(draft.params)
      if (draft.decisionContract.trim()) JSON.parse(draft.decisionContract)
      if (draft.inputBinding.trim()) JSON.parse(draft.inputBinding)
      if (draft.actionRoutes.trim()) JSON.parse(draft.actionRoutes)
    } catch (e: any) {
      showToast({ title: 'JSON 解析失败', description: e.message, type: 'error' })
      return
    }

    setSaving(true)
    try {
      const result = await updateFlowNode(flowId, node.id, {
        files,
        title: draft.title,
        ...buildProtocolNodePayload(draft, category),
        next: draft.next,
        agent: draft.agent || null,
        model_role: draft.modelRole || null,
        tools: toolsParsed,
        params: {
          ...(paramsParsed || {}),
          node_category: draft.category,
          preset: draft.preset,
          preset_config: draft.presetConfig,
          description: draft.description,
          input: draft.input,
          output: draft.output,
          save_to: draft.saveTo,
          condition: draft.condition,
          model_role: isLlmDecision ? draft.modelRole || null : (paramsParsed || {}).model_role,
        },
      })
      onSaved(result)
      const savedNode = result.graph.nodes.find((item) => item.id === node.id)
      if (savedNode) setDraft(makeNodeDraft(savedNode))
    } catch (e: any) {
      showToast({ title: '保存失败', description: e.message, type: 'error' })
    } finally {
      setSaving(false)
    }
  }

  const copyNodeId = async () => {
    try {
      await copyText(node.id)
      showToast({ title: '节点 ID 已复制', type: 'success' })
    } catch (error: any) {
      showToast({ title: '复制失败', description: error?.message, type: 'error' })
    }
  }

  const copyNodeConfig = async () => {
    try {
      await copyText(JSON.stringify(node, null, 2))
      showToast({ title: '节点配置已复制', type: 'success' })
    } catch (error: any) {
      showToast({ title: '复制失败', description: error?.message, type: 'error' })
    }
  }

  const exportNodeConfig = () => {
    const blob = new Blob([JSON.stringify(node, null, 2)], { type: 'application/json;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = `${node.id}.node.json`
    anchor.click()
    URL.revokeObjectURL(url)
  }

  const deleteCurrentNode = async () => {
    if (!onDelete || !window.confirm(`确认删除节点“${draft.title || node.id}”？`)) return
    setDeleting(true)
    try {
      await onDelete()
    } finally {
      setDeleting(false)
    }
  }

  const dirty = JSON.stringify(draft) !== JSON.stringify(makeNodeDraft(node))
  const displayLabel = getProcessDisplayLabel({ ...node, ...buildProtocolNodePayload(draft, category) } as FlowNode) || category.label
  const selectedComponent = interactionComponents.find((item: any) => item.id === draft.componentRef)
  const latestRunEvent = runEvents[runEvents.length - 1] || runState?.events?.[runState.events.length - 1]

  return (
    <aside className={`cf-node-drawer cf-node-drawer-floating cf-node-config-window ${readOnly ? 'readonly' : ''}`}>
      <div className="cf-node-drawer-header" style={{ borderColor: readOnly ? '#b8b2aa' : category.color }}>
        <div className="cf-node-drawer-heading">
          <div className="cf-node-drawer-eyebrow"><span>{readOnly ? '系统节点' : '完整配置'}</span><code>{node.id}</code></div>
          <div className="cf-node-drawer-titleline">
            <Heading size="md">{draft.title || node.id}</Heading>
            <Badge className="cf-badge" style={{ color: category.color } as any}>{displayLabel}</Badge>
          </div>
          <Text>{readOnly ? '系统根节点用于标记链路边界，不能直接修改。' : category.description}</Text>
        </div>
        <div className="cf-node-drawer-window-actions">
          <span className="cf-node-drawer-drag-hint" title="拖动节点详情"><GripHorizontal aria-hidden="true" /></span>
          <button
            type="button"
            className={`cf-node-drawer-pin ${pinned ? 'active' : ''}`}
            aria-label={pinned ? '取消钉住节点详情' : '钉住节点详情'}
            aria-pressed={pinned}
            title={pinned ? '已钉住：打开其他节点时保留' : '未钉住：打开其他节点时替换'}
            onClick={onTogglePin}
          >
            {pinned ? <Pin aria-hidden="true" /> : <PinOff aria-hidden="true" />}
          </button>
          <button type="button" className="cf-node-drawer-close" aria-label="关闭节点设置" title="关闭节点详情" onClick={onClose}><X aria-hidden="true" /></button>
        </div>
      </div>

      <div className="cf-node-drawer-body">
        {showSummary && <section className="cf-node-detail-dashboard" aria-label="节点详情摘要">
          <article className="cf-node-detail-card basic" data-detail-section="basic">
            <header><FileText aria-hidden="true" /><strong>基础信息</strong></header>
            <dl>
              <DetailFact label="节点名称" value={draft.title} />
              <DetailFact label="节点描述" value={draft.description} />
              <DetailFact label="节点 ID" value={node.id} mono />
            </dl>
          </article>
          <article className="cf-node-detail-card" data-detail-section="type">
            <header><Box aria-hidden="true" /><strong>节点类型</strong></header>
            <dl>
              <DetailFact label="类型" value={`${category.label} · ${draft.kind || node.type}`} />
              <DetailFact label="执行器" value={draft.executor} />
              <DetailFact label="作用域" value={node.scope || 'root'} />
              <DetailFact label="副作用" value={draft.effect} />
            </dl>
          </article>
          <article className="cf-node-detail-card" data-detail-section="trigger">
            <header><GitBranch aria-hidden="true" /><strong>触发条件</strong></header>
            <dl>
              <DetailFact label="触发动作" value={draft.action} mono />
              <DetailFact label="条件表达式" value={draft.condition || '上游流转后执行'} mono />
              <DetailFact label="上游连接" value={incomingEdges.length ? incomingEdges.map((edge) => edge.from) : '无'} mono />
            </dl>
          </article>
          <article className="cf-node-detail-card" data-detail-section="io">
            <header><ArrowLeftRight aria-hidden="true" /><strong>输入输出</strong></header>
            <dl>
              <DetailFact label="输入变量" value={draft.input} mono />
              <DetailFact label="输出变量" value={draft.output || node.primary_output} mono />
              <DetailFact label="输出契约" value={draft.outputContract} mono />
              <DetailFact label="后续节点" value={draft.next || outgoingEdges.map((edge) => edge.to)} mono />
            </dl>
          </article>
          <article className="cf-node-detail-card runtime" data-detail-section="runtime">
            <header><Activity aria-hidden="true" /><strong>运行数据</strong></header>
            <dl>
              <DetailFact label="当前状态" value={runState ? RUN_STATE_LABELS[runState.status] : '当前没有运行记录'} />
              <DetailFact label="关联事件" value={`${runEvents.length || runState?.events.length || 0} 条`} />
              <DetailFact label="输入键" value={runState?.inputKey} mono />
              <DetailFact label="输出键" value={runState?.outputKey} mono />
              {latestRunEvent && <DetailFact label="最新事件" value={latestRunEvent.message || latestRunEvent.type} />}
              {runState?.errorMsg && <DetailFact label="错误信息" value={runState.errorMsg} />}
            </dl>
          </article>
          <article className="cf-node-detail-card quick-actions" data-detail-section="actions">
            <header><Wrench aria-hidden="true" /><strong>快捷操作</strong></header>
            <div>
              <button type="button" onClick={() => void copyNodeId()}><ClipboardCopy aria-hidden="true" />复制节点 ID</button>
              <button type="button" onClick={() => void copyNodeConfig()}><ClipboardCopy aria-hidden="true" />复制配置</button>
              <button type="button" onClick={exportNodeConfig}><Download aria-hidden="true" />导出配置</button>
              <button type="button" className="danger" disabled={!onDelete || readOnly || deleting} onClick={() => void deleteCurrentNode()}><Trash2 aria-hidden="true" />{deleting ? '删除中' : '删除节点'}</button>
            </div>
          </article>
        </section>}
        {readOnly ? (
          <section className="cf-system-node-card">
            <div className="cf-system-node-mark">ROOT</div>
            <div className="cf-system-node-copy">
              <b>系统根节点</b>
              <span>这是系统根节点，用来标记链路的起点或终点，不能直接调整。</span>
            </div>
          </section>
        ) : (
          <>
            <DrawerSection title="核心配置" summary="名称与职责" defaultOpen>
              <VStack align="stretch" gap={3}>
                <Field.Root>
                  <Field.Label>节点名称</Field.Label>
                  <Input value={draft.title} onChange={(e) => updateDraft({ title: e.target.value })} />
                </Field.Root>
                <Field.Root>
                  <Field.Label>画布简称</Field.Label>
                  <Input value={draft.displayName} onChange={(e) => updateDraft({ displayName: e.target.value })} placeholder={draft.title || node.id} />
                </Field.Root>
                <Field.Root>
                  <Field.Label>节点职责</Field.Label>
                  <Textarea value={draft.description} onChange={(e) => updateDraft({ description: e.target.value })} rows={3} />
                </Field.Root>
              </VStack>
            </DrawerSection>

            {isInteraction && (
              <DrawerSection title="交互配置" summary={selectedComponent ? `${selectedComponent.id} · ${draft.interactionMode}` : '尚未绑定组件'} defaultOpen>
                <VStack align="stretch" gap={3}>
                  <Field.Root>
                    <Field.Label>交互组件</Field.Label>
                    <NativeSelect.Field value={draft.componentRef} onChange={(e) => updateDraft({ componentRef: e.target.value })}>
                      <option value="">请选择组件</option>
                      {interactionComponents.map((item: any) => <option key={item.id} value={item.id}>{item.id} · {item.runtime}</option>)}
                    </NativeSelect.Field>
                  </Field.Root>
                  <Field.Root>
                    <Field.Label>交互模式</Field.Label>
                    <NativeSelect.Field value={draft.interactionMode} onChange={(e) => {
                      const mode = e.target.value
                      updateDraft({
                        interactionMode: mode,
                        preset: mode,
                        next: mode === 'display' ? draft.next : '',
                        executor: mode === 'display' ? 'deterministic' : 'user',
                        effect: mode === 'display' ? 'none' : 'writes_store',
                      })
                    }}>
                      <option value="display">展示</option>
                      <option value="collect">收集</option>
                      <option value="review">审核</option>
                    </NativeSelect.Field>
                  </Field.Root>
                  {draft.interactionMode !== 'display' && (
                    <Field.Root>
                      <Field.Label>结果写入 Store</Field.Label>
                      <Input value={draft.output} onChange={(e) => updateDraft({ output: e.target.value })} placeholder="review_result" />
                    </Field.Root>
                  )}
                  <div className={`cf-node-component-state ${selectedComponent ? 'ok' : 'warn'}`}>
                    <b>{selectedComponent ? '组件可用' : '需要选择组件'}</b>
                    <span>{selectedComponent ? `${selectedComponent.supported_modes?.length || 0} 种模式 · ${selectedComponent.actions?.length || 0} 个命名动作` : '先到顶部“交互节点”维护组件，再回到这里绑定。'}</span>
                  </div>
                  <details className="cf-node-inline-advanced">
                    <summary>数据映射与动作路由</summary>
                    <VStack align="stretch" gap={3} mt={3}>
                      <Field.Root>
                        <Field.Label>输入绑定 JSON</Field.Label>
                        <Textarea value={draft.inputBinding} onChange={(e) => updateDraft({ inputBinding: e.target.value })} rows={4} placeholder={'{"summary":"store:final_summary"}'} />
                      </Field.Root>
                      {draft.interactionMode !== 'display' && <Field.Root>
                        <Field.Label>动作路由 JSON</Field.Label>
                        <Textarea value={draft.actionRoutes} onChange={(e) => updateDraft({ actionRoutes: e.target.value })} rows={5} placeholder={'{"approve":"complete","revise":"draft"}'} />
                      </Field.Root>}
                    </VStack>
                  </details>
                </VStack>
              </DrawerSection>
            )}

            {!isCustom && !isInteraction && activePreset && (
              <DrawerSection title="节点配置" summary={activePreset.label} defaultOpen>
                <div className="cf-preset-grid">
                  {presets.map((preset) => (
                    <button
                      key={preset.id}
                      className={`cf-preset-card ${draft.preset === preset.id ? 'active' : ''}`}
                      onClick={() => {
                        const defaults = getProtocolDefaults(category.id, preset.id)
                        updateDraft({
                          preset: preset.id,
                          presetConfig: {},
                          type: defaults.type,
                          action: defaults.action,
                          kind: defaults.kind,
                          executor: defaults.executor,
                          effect: defaults.effect,
                          displaySuffix: defaults.displaySuffix,
                          outputContract: defaults.outputContract || '',
                          decisionContract: defaults.decisionContract ? JSON.stringify(defaults.decisionContract, null, 2) : '',
                          decisionTestMode: '',
                          mockDecisionEnvelope: '',
                          toolBinding: defaults.toolBinding || '',
                          failurePolicy: defaults.failurePolicy || '',
                          permission: defaults.permission || '',
                          auditLog: Boolean(defaults.auditLog),
                        })
                      }}
                    >
                      <b>{preset.label}</b>
                      <span>{preset.description}</span>
                    </button>
                  ))}
                </div>
                {activePreset.fields.length > 0 && <VStack align="stretch" gap={3} mt={4}>
                  {activePreset.fields.map((field) => (
                    <Field.Root key={field.key}>
                      <Field.Label>{field.label}</Field.Label>
                      {field.multiline ? (
                        <Textarea value={draft.presetConfig[field.key] || ''} onChange={(e) => updateDraft({ presetConfig: { ...draft.presetConfig, [field.key]: e.target.value } })} rows={3} placeholder={field.placeholder} />
                      ) : (
                        <Input value={draft.presetConfig[field.key] || ''} onChange={(e) => updateDraft({ presetConfig: { ...draft.presetConfig, [field.key]: e.target.value } })} placeholder={field.placeholder} />
                      )}
                    </Field.Root>
                  ))}
                </VStack>}
                {isLlmDecision && <div className="cf-node-field-spaced"><Field.Root>
                    <Field.Label>模型角色</Field.Label>
                    <NativeSelect.Field value={draft.modelRole} onChange={(e) => updateDraft({ modelRole: e.target.value })}>
                      <option value="">请选择配方角色</option>
                      {draft.modelRole && !modelRoles.some((role) => role.id === draft.modelRole) && <option value={draft.modelRole}>{draft.modelRole}（未在配方声明）</option>}
                      {modelRoles.map((role) => <option key={role.id} value={role.id}>{role.label} · {role.id}</option>)}
                    </NativeSelect.Field>
                    <Text fontSize="xs" color={modelRoles.length ? 'fg.muted' : 'red.600'}>{modelRoles.length ? '运行时由本地模型配置接入这个角色。' : '模型配方尚未声明可选角色。'}</Text>
                  </Field.Root></div>}
              </DrawerSection>
            )}

            {isCustom && (
              <DrawerSection title="自定义配置" summary="输入、输出与行为" defaultOpen>
                <div className="cf-node-flow-fields">
                  <Field.Root>
                    <Field.Label>输入</Field.Label>
                    <Textarea value={draft.input} onChange={(e) => updateDraft({ input: e.target.value })} rows={3} placeholder="这个节点需要哪些信息？" />
                  </Field.Root>
                  <div className="cf-node-flow-arrow">→</div>
                  <Field.Root>
                    <Field.Label>输出</Field.Label>
                    <Textarea value={draft.output} onChange={(e) => updateDraft({ output: e.target.value })} rows={3} placeholder="这个节点会产生什么结果？" />
                  </Field.Root>
                </div>
                <div className="cf-node-field-spaced"><Field.Root>
                    <Field.Label>这个节点如何运行？</Field.Label>
                    <Textarea value={draft.condition} onChange={(e) => updateDraft({ condition: e.target.value })} rows={4} placeholder="自由描述这个节点的执行方式、限制、输入输出规则。" />
                  </Field.Root></div>
              </DrawerSection>
            )}

            <DrawerSection title="连接摘要" summary={`${incomingEdges.length} 入 · ${outgoingEdges.length} 出`} defaultOpen>
              <div className="cf-node-edge-summary">
                <div>
                  <b>接入这个节点</b>
                  {incomingEdges.length ? incomingEdges.map((edge, index) => <span key={`${edge.from}-${edge.to}-${index}`}>{edge.from}{edge.label ? ` · ${edge.label}` : ''}</span>) : <em>暂无上游接入</em>}
                </div>
                <div>
                  <b>从这里接出</b>
                  {outgoingEdges.length ? outgoingEdges.map((edge, index) => <span key={`${edge.from}-${edge.to}-${index}`}>{edge.to}{edge.label ? ` · ${edge.label}` : ''}</span>) : <em>暂无下游接出</em>}
                </div>
              </div>
              <Text fontSize="xs" color="fg.muted" mt={3}>连线关系以画布为准；这里用于快速核对，不在侧栏重复编辑。</Text>
            </DrawerSection>

            <DrawerSection title="高级协议" summary="类型转换与运行字段">
              <div className="cf-node-category-switch">
                <Field.Root>
                  <Field.Label>节点类型</Field.Label>
                  <NativeSelect.Field value={draft.category} onChange={(e) => changeCategory(e.target.value as NodeCategoryId)}>
                    {NODE_CATEGORIES.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
                  </NativeSelect.Field>
                </Field.Root>
                <p>更换类型会重置这个节点的专项配置，请确认后再保存。</p>
              </div>
              <div className="cf-node-execution-grid">
                <Field.Root>
                  <Field.Label>Kind</Field.Label>
                  <Input value={draft.kind} onChange={(e) => updateDraft({ kind: e.target.value })} />
                </Field.Root>
                <Field.Root>
                  <Field.Label>Executor</Field.Label>
                  <Input value={draft.executor} onChange={(e) => updateDraft({ executor: e.target.value })} />
                </Field.Root>
                <Field.Root>
                  <Field.Label>Effect</Field.Label>
                  <Input value={draft.effect} onChange={(e) => updateDraft({ effect: e.target.value })} />
                </Field.Root>
                <Field.Root>
                  <Field.Label>Output Contract</Field.Label>
                  <Input value={draft.outputContract} onChange={(e) => updateDraft({ outputContract: e.target.value })} placeholder="tool_plan.v1 / gate_result.v1" />
                </Field.Root>
                <Field.Root>
                  <Field.Label>Tool Binding</Field.Label>
                  <Input value={draft.toolBinding} onChange={(e) => updateDraft({ toolBinding: e.target.value })} placeholder="static_params / from_tool_plan" />
                </Field.Root>
                <Field.Root>
                  <Field.Label>Allowed Tools</Field.Label>
                  <Input value={draft.allowedTools} onChange={(e) => updateDraft({ allowedTools: e.target.value })} placeholder='["filesystem_write"]' />
                </Field.Root>
                <Field.Root>
                  <Field.Label>Failure Policy</Field.Label>
                  <Input value={draft.failurePolicy} onChange={(e) => updateDraft({ failurePolicy: e.target.value })} placeholder="fail_closed / skip_optional" />
                </Field.Root>
                <Field.Root>
                  <Field.Label>Permission</Field.Label>
                  <Input value={draft.permission} onChange={(e) => updateDraft({ permission: e.target.value })} placeholder="write_run_artifacts" />
                </Field.Root>
                <label className="cf-mcp-check">
                  <input type="checkbox" checked={draft.auditLog} onChange={(e) => updateDraft({ auditLog: e.target.checked })} />
                  Audit log
                </label>
              </div>
              {draft.kind === 'decision' && draft.executor === 'llm' && (
                <VStack align="stretch" gap={3} mt={3}>
                  <Field.Root>
                    <Field.Label>Decision Contract JSON</Field.Label>
                    <Textarea value={draft.decisionContract} onChange={(e) => updateDraft({ decisionContract: e.target.value })} rows={7} />
                  </Field.Root>
                </VStack>
              )}
              <div className="cf-node-execution-grid cf-node-protocol-tail">
                {isCustom && (
                  <Field.Root>
                    <Field.Label>Action</Field.Label>
                    <Input value={draft.action} onChange={(e) => updateDraft({ action: e.target.value })} />
                  </Field.Root>
                )}
                <Field.Root>
                  <Field.Label>主链 next</Field.Label>
                  <Input value={draft.next} onChange={(e) => updateDraft({ next: e.target.value })} />
                </Field.Root>
                {isCustom && (
                  <>
                    <Field.Root>
                      <Field.Label>Agent</Field.Label>
                      <Input value={draft.agent} onChange={(e) => updateDraft({ agent: e.target.value })} />
                    </Field.Root>
                    {!isLlmDecision && <Field.Root>
                      <Field.Label>Model Role</Field.Label>
                      <Input value={draft.modelRole} onChange={(e) => updateDraft({ modelRole: e.target.value })} />
                    </Field.Root>}
                  </>
                )}
              </div>
              {isCustom && (
                <VStack align="stretch" gap={3}>
                  <Field.Root>
                    <Field.Label>Tools JSON</Field.Label>
                    <Textarea value={draft.tools} onChange={(e) => updateDraft({ tools: e.target.value })} rows={6} />
                  </Field.Root>
                  <Field.Root>
                    <Field.Label>Params JSON</Field.Label>
                    <Textarea value={draft.params} onChange={(e) => updateDraft({ params: e.target.value })} rows={6} />
                  </Field.Root>
                </VStack>
              )}
            </DrawerSection>
          </>
        )}
      </div>

      <div className="cf-node-drawer-footer">
        {!readOnly && <span className={dirty ? 'dirty' : ''}>{dirty ? '有未保存修改' : '所有修改已保存'}</span>}
        <Button className="cf-outline-btn" onClick={onClose}>{readOnly ? '关闭' : '取消'}</Button>
        {!readOnly && <Button className="cf-accent-btn" disabled={!dirty} onClick={save} loading={saving} loadingText="保存中...">保存节点</Button>}
      </div>
    </aside>
  )
}
