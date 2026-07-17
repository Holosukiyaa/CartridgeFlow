import { useEffect, useState } from 'react'
import { Badge, Box, Button, Field, HStack, Heading, Input, NativeSelect, SimpleGrid, Text, Textarea, VStack } from '../../ui.tsx'
import { updateFlowNode, type FlowFiles, type FlowNode } from '../../api.ts'
import { showToast } from '../../toast.tsx'
import type { GraphResult, NodeCategory, NodeDraft } from './types.ts'
import { CATEGORY_BY_ID, NODE_CATEGORIES, buildProtocolNodePayload, getNodeCategory, getProcessDisplayLabel, getProtocolDefaults, makeNodeDraft } from './nodeModel.ts'

export function FiveCategoryNodeEditor({ node, flowId, files, onSaved }: {
  node: FlowNode
  flowId: string
  files: FlowFiles
  onSaved: (result: GraphResult) => void
}) {
  const [draft, setDraft] = useState<NodeDraft>(() => makeNodeDraft(node))
  const [saving, setSaving] = useState(false)
  const category = CATEGORY_BY_ID.get(draft.category) || getNodeCategory(node)

  useEffect(() => setDraft(makeNodeDraft(node)), [node])

  const updateDraft = (patch: Partial<NodeDraft>) => setDraft((current) => ({ ...current, ...patch }))

  const save = async () => {
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

    const mergedParams = {
      ...(paramsParsed || {}),
      node_category: draft.category,
      description: draft.description,
      input: draft.input,
      output: draft.output,
      save_to: draft.saveTo,
      condition: draft.condition,
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
        params: mergedParams,
      })
      onSaved(result)
    } catch (e: any) {
      showToast({ title: '保存失败', description: e.message, type: 'error' })
    } finally {
      setSaving(false)
    }
  }

  return (
    <Box p={4} className="cf-panel cf-node-editor-panel">
      <HStack justify="space-between" align="start" mb={3}>
        <Box>
          <Text className="cf-kicker">配置节点</Text>
          <Heading size="sm">{node.title}</Heading>
          <Text fontSize="sm" color="fg.muted">先用自然语言说明这个节点做什么，再按需打开高级 JSON。</Text>
        </Box>
        <Badge className="cf-badge">{getProcessDisplayLabel({ ...node, ...buildProtocolNodePayload(draft, category) } as FlowNode) || category.label}</Badge>
      </HStack>

      <VStack align="stretch" gap={3}>
        <Box className="cf-node-editor-section">
          <Text fontWeight="semibold" mb={2}>1. 这个节点是什么？</Text>
          <SimpleGrid columns={2} gap={3}>
            <Field.Root>
              <Field.Label>显示名称</Field.Label>
              <Input value={draft.title} onChange={(e) => updateDraft({ title: e.target.value })} />
            </Field.Root>
            <Field.Root>
              <Field.Label>节点分类</Field.Label>
              <NativeSelect.Field value={draft.category} onChange={(e) => {
                const nextCategory = CATEGORY_BY_ID.get(e.target.value as any)!
                const defaults = getProtocolDefaults(nextCategory.id)
                updateDraft({
                  category: nextCategory.id,
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
          </SimpleGrid>
          <Box mt={3}>
            <Field.Root>
              <Field.Label>一句话说明</Field.Label>
              <Textarea value={draft.description} onChange={(e) => updateDraft({ description: e.target.value })} rows={3} placeholder={category.description} />
            </Field.Root>
          </Box>
        </Box>

        <Box className="cf-node-editor-section">
          <Text fontWeight="semibold" mb={2}>2. 它接收什么，产生什么？</Text>
          <SimpleGrid columns={2} gap={3}>
            <Field.Root>
              <Field.Label>输入信息</Field.Label>
              <Input value={draft.input} onChange={(e) => updateDraft({ input: e.target.value })} placeholder="例如：用户需求、项目结构、测试结果" />
            </Field.Root>
            <Field.Root>
              <Field.Label>输出结果</Field.Label>
              <Input value={draft.output} onChange={(e) => updateDraft({ output: e.target.value })} placeholder="例如：需求分析、实现计划、最终报告" />
            </Field.Root>
          </SimpleGrid>
        </Box>

        <CategorySpecificFields draft={draft} category={category} onChange={updateDraft} />

        <Box className="cf-node-editor-section">
          <Text fontWeight="semibold" mb={2}>4. 执行设置</Text>
          <SimpleGrid columns={3} gap={3} mb={3}>
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
          </SimpleGrid>
          <SimpleGrid columns={2} gap={3}>
            <Field.Root>
              <Field.Label>Action</Field.Label>
              <Input value={draft.action} onChange={(e) => updateDraft({ action: e.target.value })} />
            </Field.Root>
            <Field.Root>
              <Field.Label>下一节点 next</Field.Label>
              <Input value={draft.next} onChange={(e) => updateDraft({ next: e.target.value })} placeholder="通常由连线维护" />
            </Field.Root>
          </SimpleGrid>
          <SimpleGrid columns={2} gap={3} mb={0}>
            <Field.Root>
              <Field.Label>Agent</Field.Label>
              <Input value={draft.agent} onChange={(e) => updateDraft({ agent: e.target.value })} placeholder="如 planner / coder / reviewer" />
            </Field.Root>
            <Field.Root>
              <Field.Label>Model Role</Field.Label>
              <Input value={draft.modelRole} onChange={(e) => updateDraft({ modelRole: e.target.value })} placeholder="如 runtime / mentor" />
            </Field.Root>
          </SimpleGrid>
          <Box mt={3}>
            <SimpleGrid columns={3} gap={3}>
              <Field.Root>
                <Field.Label>Output Contract</Field.Label>
                <Input value={draft.outputContract} onChange={(e) => updateDraft({ outputContract: e.target.value })} placeholder="decision_envelope.v1 / tool_plan.v1 / gate_result.v1" />
              </Field.Root>
              <Field.Root>
                <Field.Label>Tool Binding</Field.Label>
                <Input value={draft.toolBinding} onChange={(e) => updateDraft({ toolBinding: e.target.value })} placeholder="static_params / from_tool_plan" />
              </Field.Root>
              <Field.Root>
                <Field.Label>Failure Policy</Field.Label>
                <Input value={draft.failurePolicy} onChange={(e) => updateDraft({ failurePolicy: e.target.value })} placeholder="fail_closed / skip_optional" />
              </Field.Root>
            </SimpleGrid>
          </Box>
          {draft.kind === 'decision' && draft.executor === 'llm' && (
            <Box mt={3}>
              <Text fontWeight="semibold" mb={2}>AI 决策协议</Text>
              <SimpleGrid columns={2} gap={3}>
                <Field.Root>
                  <Field.Label>Decision Contract JSON</Field.Label>
                  <Textarea value={draft.decisionContract} onChange={(e) => updateDraft({ decisionContract: e.target.value })} rows={8} placeholder='{"schema":"decision_envelope.v1"}' />
                </Field.Root>
                <Field.Root>
                  <Field.Label>Mock Decision Envelope JSON</Field.Label>
                  <Textarea value={draft.mockDecisionEnvelope} onChange={(e) => updateDraft({ mockDecisionEnvelope: e.target.value })} rows={8} placeholder='{"schema":"decision_envelope.v1","status":"resolved","summary":"...","payload":{}}' />
                </Field.Root>
              </SimpleGrid>
              <Box mt={3}>
                <Field.Root>
                  <Field.Label>Decision Test Mode</Field.Label>
                  <NativeSelect.Field value={draft.decisionTestMode} onChange={(e) => updateDraft({ decisionTestMode: e.target.value })}>
                    <option value="">live / default</option>
                    <option value="mock">mock</option>
                    <option value="offline_fallback">offline_fallback</option>
                  </NativeSelect.Field>
                </Field.Root>
              </Box>
            </Box>
          )}
          <Box mt={3}>
            <SimpleGrid columns={2} gap={3}>
              <Field.Root>
                <Field.Label>Allowed Tools</Field.Label>
                <Input value={draft.allowedTools} onChange={(e) => updateDraft({ allowedTools: e.target.value })} placeholder='["filesystem_write"]' />
              </Field.Root>
              <Field.Root>
                <Field.Label>Permission</Field.Label>
                <Input value={draft.permission} onChange={(e) => updateDraft({ permission: e.target.value })} placeholder="write_run_artifacts" />
              </Field.Root>
            </SimpleGrid>
          </Box>
        </Box>

        <Box className="cf-node-editor-section">
          <Text fontWeight="semibold" mb={2}>5. 高级 JSON</Text>
          <Text fontSize="sm" color="fg.muted" mb={2}>保留给工具、复杂参数和后端兼容。普通配置会在保存时合并到 params。</Text>
          <SimpleGrid columns={2} gap={3}>
            <Field.Root>
              <Field.Label>Tools JSON</Field.Label>
              <Textarea value={draft.tools} onChange={(e) => updateDraft({ tools: e.target.value })} rows={7} placeholder={'[{"type":"builtin","name":"search_codebase"}]'} />
            </Field.Root>
            <Field.Root>
              <Field.Label>Params JSON</Field.Label>
              <Textarea value={draft.params} onChange={(e) => updateDraft({ params: e.target.value })} rows={7} placeholder={'{"prompt":"..."}'} />
            </Field.Root>
          </SimpleGrid>
        </Box>

        <Button className="cf-accent-btn" onClick={save} loading={saving} loadingText="保存中...">保存节点</Button>
      </VStack>
    </Box>
  )
}

function CategorySpecificFields({ draft, category, onChange }: {
  draft: NodeDraft
  category: NodeCategory
  onChange: (patch: Partial<NodeDraft>) => void
}) {
  if (category.id === 'store') {
    return (
      <Box className="cf-node-editor-section">
        <Text fontWeight="semibold" mb={2}>3. 要存在哪里？</Text>
        <Field.Root>
          <Field.Label>保存位置 / 名称</Field.Label>
          <Input value={draft.saveTo} onChange={(e) => onChange({ saveTo: e.target.value })} placeholder="例如：context.plan、artifacts/report.md、cache.project_map" />
        </Field.Root>
      </Box>
    )
  }
  if (category.id === 'control') {
    return (
      <Box className="cf-node-editor-section">
        <Text fontWeight="semibold" mb={2}>3. 什么时候继续？</Text>
        <Field.Root>
          <Field.Label>确认文案 / 判断条件</Field.Label>
          <Textarea value={draft.condition} onChange={(e) => onChange({ condition: e.target.value })} rows={3} placeholder="例如：用户确认后继续；测试通过进入交付，失败回到修复。" />
        </Field.Root>
      </Box>
    )
  }
  if (category.id === 'transfer') {
    return (
      <Box className="cf-node-editor-section">
        <Text fontWeight="semibold" mb={2}>3. 要传给谁？</Text>
        <Field.Root>
          <Field.Label>传递规则</Field.Label>
          <Textarea value={draft.condition} onChange={(e) => onChange({ condition: e.target.value })} rows={3} placeholder="例如：把 analysis 传给计划节点；把失败结果传给错误分析节点。" />
        </Field.Root>
      </Box>
    )
  }
  return (
    <Box className="cf-node-editor-section">
      <Text fontWeight="semibold" mb={2}>3. 处理方式</Text>
      <Field.Root>
        <Field.Label>{category.id === 'input' ? '收集方式' : '处理提示 / 规则'}</Field.Label>
        <Textarea value={draft.condition} onChange={(e) => onChange({ condition: e.target.value })} rows={3} placeholder={category.examples.join(' / ')} />
      </Field.Root>
    </Box>
  )
}
