import { useEffect, useState, type ReactNode } from 'react'
import { Badge, Box, Button, Field, HStack, Heading, Input, NativeSelect, Text, Textarea, VStack } from '../../ui.tsx'
import { updateFlowNode, type FlowEdge, type FlowFiles, type FlowNode } from '../../api.ts'
import { showToast } from '../../toast.tsx'
import type { GraphResult, NodeCategoryId, NodeDraft } from './types.ts'
import { CATEGORY_BY_ID, NODE_CATEGORIES, buildProtocolNodePayload, getNodeCategory, getProcessDisplayLabel, getPreset, getPresets, getProtocolDefaults, makeNodeDraft } from './nodeModel.ts'

function DrawerSection({ title, children, defaultOpen = false }: { title: string; children: ReactNode; defaultOpen?: boolean }) {
  const [isOpen, setIsOpen] = useState(defaultOpen)
  return (
    <section className="cf-drawer-block">
      <button type="button" className="cf-drawer-block-head" onClick={() => setIsOpen((value) => !value)}>
        <span>{title}</span>
        <em>{isOpen ? '收起' : '展开'}</em>
      </button>
      {isOpen ? <div className="cf-drawer-block-content">{children}</div> : null}
    </section>
  )
}

export function NodeDrawer({ node, graphEdges, flowId, files, editable, open, onClose, onSaved }: {
  node: FlowNode | null
  graphEdges: FlowEdge[]
  flowId: string
  files: FlowFiles
  editable: boolean
  open: boolean
  onClose: () => void
  onSaved: (result: GraphResult) => void
}) {
  const [draft, setDraft] = useState<NodeDraft | null>(node ? makeNodeDraft(node) : null)
  const [saving, setSaving] = useState(false)
  const category = draft ? CATEGORY_BY_ID.get(draft.category) || getNodeCategory(node) : null
  const presets = category && draft ? getPresets(draft.category) : []
  const activePreset = category && draft ? getPreset(draft.category, draft.preset) : null
  const isCustom = draft?.category === 'custom'
  const incomingEdges = node ? graphEdges.filter((edge) => edge.to === node.id) : []
  const outgoingEdges = node ? graphEdges.filter((edge) => edge.from === node.id) : []

  useEffect(() => {
    setDraft(node ? makeNodeDraft(node) : null)
  }, [node])

  if (!open || !node || !draft || !category) return null

  const readOnly = !editable || node.locked || node.scope === 'root'
  const updateDraft = (patch: Partial<NodeDraft>) => {
    if (readOnly) return
    setDraft((current) => current ? { ...current, ...patch } : current)
  }

  const save = async () => {
    if (readOnly) return
    let toolsParsed: any = null
    let paramsParsed: any = {}
    try {
      if (draft.tools.trim()) toolsParsed = JSON.parse(draft.tools)
      if (draft.params.trim()) paramsParsed = JSON.parse(draft.params)
      if (draft.decisionContract.trim()) JSON.parse(draft.decisionContract)
      if (draft.mockDecisionEnvelope.trim()) JSON.parse(draft.mockDecisionEnvelope)
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
        },
      })
      onSaved(result)
    } catch (e: any) {
      showToast({ title: '保存失败', description: e.message, type: 'error' })
    } finally {
      setSaving(false)
    }
  }

  return (
    <aside className={`cf-node-drawer ${readOnly ? 'readonly' : ''}`}>
      <div className="cf-node-drawer-header" style={{ borderColor: readOnly ? '#b8b2aa' : category.color }}>
        <Box>
          <Text className="cf-kicker">{readOnly ? 'SYSTEM NODE' : 'NODE SETUP'}</Text>
          <Heading size="md">{draft.title || node.id}</Heading>
          <Text fontSize="sm" color="fg.muted">{readOnly ? '这是系统根节点，用来标记链路的起点或终点，不能直接调整。' : '配置这个节点在链路中的职责、输入、输出和运行方式。'}</Text>
        </Box>
        <Button className="cf-outline-btn" onClick={onClose}>收起</Button>
      </div>

      <div className="cf-node-drawer-body">
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
            <section className="cf-node-drawer-card cf-node-drawer-hero" style={{ background: category.bg, borderColor: category.color }}>
              <HStack justify="space-between" align="start">
                <Box>
                  <Badge className="cf-badge" style={{ color: category.color } as any}>{getProcessDisplayLabel({ ...node, ...buildProtocolNodePayload(draft, category) } as FlowNode) || category.label}</Badge>
                  <Text mt={2} fontWeight="semibold">{category.description}</Text>
                </Box>
                <Text className="cf-node-drawer-id">{node.id}</Text>
              </HStack>
              <HStack gap={1} flexWrap="wrap" mt={3}>
                {category.examples.map((item) => <span key={item} className="cf-node-chip">{item}</span>)}
              </HStack>
            </section>

            <DrawerSection title="01 / 基本信息" defaultOpen>
              <VStack align="stretch" gap={3}>
                <Field.Root>
                  <Field.Label>节点名称</Field.Label>
                  <Input value={draft.title} onChange={(e) => updateDraft({ title: e.target.value })} />
                </Field.Root>
                <Field.Root>
                  <Field.Label>节点类型</Field.Label>
                  <NativeSelect.Field value={draft.category} onChange={(e) => {
                    const nextCategory = CATEGORY_BY_ID.get(e.target.value as NodeCategoryId)!
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
                      title: draft.title || nextCategory.defaultTitle,
                    })
                  }}>
                    {NODE_CATEGORIES.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
                  </NativeSelect.Field>
                </Field.Root>
                <Field.Root>
                  <Field.Label>这个节点要做什么？</Field.Label>
                  <Textarea value={draft.description} onChange={(e) => updateDraft({ description: e.target.value })} rows={3} />
                </Field.Root>
              </VStack>
            </DrawerSection>

            {!isCustom && activePreset && (
              <DrawerSection title="02 / 选择用途" defaultOpen>
                <Text fontSize="sm" color="fg.muted" mb={3}>这个{category.shortLabel}节点要做什么？先选一个简单用途，再填写少量配置。</Text>
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
              </DrawerSection>
            )}

            {!isCustom && activePreset && activePreset.fields.length > 0 && (
              <DrawerSection title="03 / 用途配置" defaultOpen>
                <VStack align="stretch" gap={3}>
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
                </VStack>
              </DrawerSection>
            )}

            {isCustom && (
              <DrawerSection title="02 / 自定义输入输出" defaultOpen>
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
              </DrawerSection>
            )}

            {isCustom && (
              <DrawerSection title="03 / 自定义行为">
                <Field.Root>
                  <Field.Label>这个节点如何运行？</Field.Label>
                  <Textarea value={draft.condition} onChange={(e) => updateDraft({ condition: e.target.value })} rows={4} placeholder="自由描述这个节点的执行方式、限制、输入输出规则。" />
                </Field.Root>
              </DrawerSection>
            )}

            <DrawerSection title="04 / 协议字段" defaultOpen>
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
                  <Field.Root>
                    <Field.Label>Decision Test Mode</Field.Label>
                    <NativeSelect.Field value={draft.decisionTestMode} onChange={(e) => updateDraft({ decisionTestMode: e.target.value })}>
                      <option value="">live / default</option>
                      <option value="mock">mock</option>
                      <option value="offline_fallback">offline_fallback</option>
                    </NativeSelect.Field>
                  </Field.Root>
                  <Field.Root>
                    <Field.Label>Mock Decision Envelope JSON</Field.Label>
                    <Textarea value={draft.mockDecisionEnvelope} onChange={(e) => updateDraft({ mockDecisionEnvelope: e.target.value })} rows={7} />
                  </Field.Root>
                </VStack>
              )}
            </DrawerSection>

            <DrawerSection title="05 / 执行连接">
              <div className="cf-node-execution-grid">
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
                    <Field.Root>
                      <Field.Label>Model Role</Field.Label>
                      <Input value={draft.modelRole} onChange={(e) => updateDraft({ modelRole: e.target.value })} />
                    </Field.Root>
                  </>
                )}
              </div>
              <div className="cf-node-edge-summary">
                <div>
                  <b>接入这个节点</b>
                  {incomingEdges.length ? incomingEdges.map((edge, index) => <span key={`${edge.from}-${edge.to}-${index}`}>{edge.from}{edge.label ? ` · ${edge.label}` : ''}</span>) : <em>暂无上游接入</em>}
                </div>
                <div>
                  <b>这个节点接出</b>
                  {outgoingEdges.length ? outgoingEdges.map((edge, index) => <span key={`${edge.from}-${edge.to}-${index}`}>{edge.to}{edge.label ? ` · ${edge.label}` : ''}</span>) : <em>暂无下游接出</em>}
                </div>
              </div>
              <Text fontSize="xs" color="fg.muted" mt={3}>主链 next 只代表默认执行下一步；完整多入多出关系以画布连线为准。</Text>
            </DrawerSection>

            {isCustom && (
              <DrawerSection title="高级 JSON" defaultOpen>
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
              </DrawerSection>
            )}
          </>
        )}
      </div>

      <div className="cf-node-drawer-footer">
        <Button className="cf-outline-btn" onClick={onClose}>{readOnly ? '关闭' : '取消'}</Button>
        {!readOnly && <Button className="cf-accent-btn" onClick={save} loading={saving} loadingText="保存中...">保存节点</Button>}
      </div>
    </aside>
  )
}
