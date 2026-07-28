import { useMemo } from 'react'
import { Activity, ArrowDownToLine, ArrowUpFromLine, Boxes, Bot, ChevronRight, GripHorizontal, PackageCheck, Pin, PinOff, PlugZap, RotateCcw, Route, Save, ShieldCheck, SlidersHorizontal, X } from 'lucide-react'
import type { FlowEdge, FlowEvent, FlowFiles, FlowNode } from '../../api.ts'
import { buildNodeDetailFacts, resolveNodeSemanticKind } from './flowNodeView.ts'
import { CATEGORY_BY_ID, NODE_CATEGORIES, getNodeCategory, getNodePalette, getPreset, getPresets, getProcessDisplayLabel, getProtocolDefaults } from './nodeModel.ts'
import { NODE_DETAIL_SECTION_BY_ID, type NodeDetailSection } from './nodeDetails.ts'
import type { NodeRunState } from './runState.ts'
import type { NodeCategoryId, NodeDraft } from './types.ts'
import { InteractionAssetEditor } from './InteractionAssetEditor.tsx'
import { InteractionContractEditor } from './InteractionContractEditor.tsx'
import type { NodeAuthoringPath } from './nodeAuthoring.ts'

function SectionIcon({ section }: { section: NodeDetailSection }) {
  if (section === 'inputs') return <ArrowDownToLine aria-hidden="true" />
  if (section === 'outputs') return <ArrowUpFromLine aria-hidden="true" />
  if (section === 'component') return <Boxes aria-hidden="true" />
  if (section === 'model') return <Bot aria-hidden="true" />
  if (section === 'resources') return <PlugZap aria-hidden="true" />
  if (section === 'routing') return <Route aria-hidden="true" />
  if (section === 'safety') return <ShieldCheck aria-hidden="true" />
  if (section === 'runtime') return <Activity aria-hidden="true" />
  if (section === 'artifacts') return <PackageCheck aria-hidden="true" />
  return <SlidersHorizontal aria-hidden="true" />
}

function parseInteractionComponents(files: FlowFiles) {
  try {
    const value = JSON.parse(files.interaction_components || '{}')
    return Array.isArray(value.components) ? value.components : []
  } catch {
    return []
  }
}

function parseModelRoles(files: FlowFiles) {
  try {
    const value = JSON.parse(files.manifest || '{}')
    const roles = value.llm_recipe?.roles
    if (Array.isArray(roles)) return roles.map((item) => ({ id: String(item.id || item.role || ''), label: String(item.label || item.name || item.id || item.role || '') })).filter((item) => item.id)
    if (roles && typeof roles === 'object') return Object.entries(roles).map(([id, item]: [string, any]) => ({ id, label: String(item?.label || item?.name || id) }))
  } catch {
    // The manifest error is surfaced by the save endpoint.
  }
  return []
}

function presetSection(category: NodeCategoryId): NodeDetailSection {
  if (category === 'input') return 'inputs'
  if (category === 'interaction') return 'component'
  if (category === 'tool' || category === 'remote') return 'resources'
  if (category === 'transfer' || category === 'store') return 'outputs'
  if (category === 'control') return 'routing'
  return 'contract'
}

function EditorField({ label, value, onChange, multiline = false, mono = false, placeholder, children }: {
  label: string
  value?: string
  onChange?: (value: string) => void
  multiline?: boolean
  mono?: boolean
  placeholder?: string
  children?: React.ReactNode
}) {
  return (
    <label className={`cf-satellite-field ${mono ? 'mono' : ''}`}>
      <span>{label}</span>
      {children || (multiline ? (
        <textarea value={value || ''} onChange={(event) => onChange?.(event.target.value)} placeholder={placeholder} rows={3} />
      ) : (
        <input value={value || ''} onChange={(event) => onChange?.(event.target.value)} placeholder={placeholder} />
      ))}
    </label>
  )
}

function SectionEditor({ section, draft, files, flowId, node, graphNodes, onFilesChange, onChange }: {
  section: NodeDetailSection
  draft: NodeDraft
  files: FlowFiles
  flowId: string
  node: FlowNode
  graphNodes: FlowNode[]
  onFilesChange: (files: FlowFiles) => void
  onChange: (patch: Partial<NodeDraft>) => void
}) {
  const interactionComponents = useMemo(() => parseInteractionComponents(files), [files])
  const interactionNode = resolveNodeSemanticKind(node) === 'interaction'
  const selectedInteractionComponent = interactionComponents.find((item: any) => item.id === draft.componentRef)
  const modelRoles = useMemo(() => parseModelRoles(files), [files])
  const presets = getPresets(draft.category)
  const activePreset = getPreset(draft.category, draft.preset)
  const upstreamOutputs = graphNodes.flatMap((item) => {
    if (item.id === node.id) return []
    const candidate = item.params?.output || item.params?.save_to || item.primary_output || item.params?.preset_config?.output_name || ''
    return String(candidate).split(/[\n,]/).map((value) => value.trim()).filter(Boolean).map((value) => ({ value, label: `${item.display_name || item.title || item.id} · ${value}` }))
  })

  const changeCategory = (categoryId: NodeCategoryId) => {
    const category = CATEGORY_BY_ID.get(categoryId)!
    const preset = getPreset(categoryId)
    const defaults = getProtocolDefaults(categoryId, preset.id)
    onChange({
      category: categoryId,
      preset: preset.id,
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
      toolBinding: defaults.toolBinding || '',
      failurePolicy: defaults.failurePolicy || '',
      permission: defaults.permission || '',
      auditLog: Boolean(defaults.auditLog),
      title: draft.title || category.defaultTitle,
    })
  }

  const changePreset = (presetId: string) => {
    const defaults = getProtocolDefaults(draft.category, presetId)
    onChange({
      preset: presetId,
      presetConfig: {},
      type: defaults.type,
      action: defaults.action,
      kind: defaults.kind,
      executor: defaults.executor,
      effect: defaults.effect,
      displaySuffix: defaults.displaySuffix,
      outputContract: defaults.outputContract || '',
      toolBinding: defaults.toolBinding || '',
      failurePolicy: defaults.failurePolicy || '',
      permission: defaults.permission || '',
      auditLog: Boolean(defaults.auditLog),
    })
  }

  const applyInteractionMode = (interactionMode: string) => {
    const waitsForUser = interactionMode === 'collect' || interactionMode === 'review'
    onChange({
      interactionMode,
      executor: waitsForUser ? 'user' : 'deterministic',
      effect: waitsForUser ? 'writes_store' : 'none',
      ...(waitsForUser && !draft.output ? { output: `${node.id}_result` } : {}),
    })
  }
  const interactionContractNeedsRepair = draft.interactionMode === 'display'
    ? draft.executor !== 'deterministic' || draft.effect !== 'none'
    : !['user', 'human'].includes(draft.executor) || draft.effect !== 'writes_store' || !draft.output

  const presetFields = presetSection(draft.category) === section && (
    <fieldset className="cf-satellite-fieldset">
      <legend>节点预设</legend>
      <EditorField label="预设">
        <select value={draft.preset} onChange={(event) => changePreset(event.target.value)}>
          {presets.map((preset) => <option key={preset.id} value={preset.id}>{preset.label}</option>)}
        </select>
      </EditorField>
      {activePreset.fields.map((field) => (
        <EditorField
          key={field.key}
          label={field.label}
          value={draft.presetConfig[field.key] || ''}
          multiline={field.multiline}
          placeholder={field.placeholder}
          onChange={(value) => onChange({ presetConfig: { ...draft.presetConfig, [field.key]: value } })}
        />
      ))}
    </fieldset>
  )

  return (
    <div className="cf-satellite-editor-fields">
      {section === 'contract' && <>
        <EditorField label="节点名称" value={draft.title} onChange={(title) => onChange({ title })} />
        <EditorField label="画布简称" value={draft.displayName} onChange={(displayName) => onChange({ displayName })} />
        <EditorField label="节点职责" value={draft.description} multiline onChange={(description) => onChange({ description })} />
        <EditorField label="节点类型">
          <select value={draft.category} onChange={(event) => changeCategory(event.target.value as NodeCategoryId)}>
            {NODE_CATEGORIES.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
          </select>
        </EditorField>
        <div className="cf-satellite-field-grid">
          <EditorField label="Kind" value={draft.kind} mono onChange={(kind) => onChange({ kind })} />
          <EditorField label="Executor" value={draft.executor} mono onChange={(executor) => onChange({ executor })} />
          <EditorField label="Effect" value={draft.effect} mono onChange={(effect) => onChange({ effect })} />
          <EditorField label="Action" value={draft.action} mono onChange={(action) => onChange({ action })} />
        </div>
      </>}

      {section === 'inputs' && <>
        <label className="cf-satellite-field mono"><span>输入变量</span><input list={`upstream-output-${node.id}`} value={draft.input} onChange={(event) => onChange({ input: event.target.value })} placeholder="选择上游输出或输入 Store 键" /><datalist id={`upstream-output-${node.id}`}>{upstreamOutputs.map((item) => <option key={`${item.label}:${item.value}`} value={item.value}>{item.label}</option>)}</datalist></label>
        <EditorField label="可选输入" value={draft.optionalInput} mono onChange={(optionalInput) => onChange({ optionalInput })} />
        <div className="cf-satellite-field-grid">
          <EditorField label="输入来源" value={draft.source} onChange={(source) => onChange({ source })} />
          <EditorField label="输入类型" value={draft.inputKind} mono onChange={(inputKind) => onChange({ inputKind })} />
        </div>
        <EditorField label="输入契约" value={draft.inputSchema} mono multiline onChange={(inputSchema) => onChange({ inputSchema })} />
        {interactionNode && <InteractionContractEditor files={files} componentRef={draft.componentRef} currentNodeId={node.id} graphNodes={graphNodes} inputBinding={draft.inputBinding} actionRoutes={draft.actionRoutes} showRoutes={false} onChange={onChange} />}
      </>}

      {section === 'outputs' && <>
        <EditorField label="输出变量" value={draft.output} mono onChange={(output) => onChange({ output })} />
        <EditorField label="主输出" value={draft.primaryOutput} mono onChange={(primaryOutput) => onChange({ primaryOutput })} />
        <EditorField label="输出契约" value={draft.outputContract} mono onChange={(outputContract) => onChange({ outputContract })} />
        <EditorField label="保存键/位置" value={draft.saveTo} mono onChange={(saveTo) => onChange({ saveTo })} />
      </>}

      {section === 'component' && <>
        <EditorField label="交互组件">
          <select value={draft.componentRef} onChange={(event) => onChange({ componentRef: event.target.value })}>
            <option value="">未绑定</option>
            {interactionComponents.map((item: any) => <option key={item.id} value={item.id}>{item.id} · {item.runtime}</option>)}
          </select>
        </EditorField>
        <EditorField label="交互模式">
          <select value={draft.interactionMode} onChange={(event) => applyInteractionMode(event.target.value)}>
            {(['display', 'collect', 'review'] as const).filter((mode) => !selectedInteractionComponent || selectedInteractionComponent.supported_modes?.includes(mode) || mode === draft.interactionMode).map((mode) => <option key={mode} value={mode}>{mode === 'display' ? '展示' : mode === 'collect' ? '收集' : '审核'}</option>)}
          </select>
        </EditorField>
        {interactionContractNeedsRepair && <div className="cf-interaction-contract-repair"><span>当前执行约束与交互模式不一致</span><button type="button" onClick={() => applyInteractionMode(draft.interactionMode || 'display')}>修复</button></div>}
      </>}

      {section === 'model' && <>
        <EditorField label="模型角色">
          <select value={draft.modelRole} onChange={(event) => onChange({ modelRole: event.target.value })}>
            <option value="">未绑定</option>
            {draft.modelRole && !modelRoles.some((role) => role.id === draft.modelRole) && <option value={draft.modelRole}>{draft.modelRole}</option>}
            {modelRoles.map((role) => <option key={role.id} value={role.id}>{role.label} · {role.id}</option>)}
          </select>
        </EditorField>
        <EditorField label="输入变量" value={draft.input} mono onChange={(input) => onChange({ input })} />
        <EditorField label="输出变量" value={draft.output} mono onChange={(output) => onChange({ output })} />
        <EditorField label="决策契约 JSON" value={draft.decisionContract} mono multiline onChange={(decisionContract) => onChange({ decisionContract })} />
      </>}

      {section === 'resources' && <>
        <EditorField label="工具绑定" value={draft.toolBinding} mono onChange={(toolBinding) => onChange({ toolBinding })} />
        <EditorField label="允许工具" value={draft.allowedTools} mono multiline onChange={(allowedTools) => onChange({ allowedTools })} placeholder='["filesystem_read"]' />
        <EditorField label="MCP 绑定 JSON" value={draft.mcpBinding} mono multiline onChange={(mcpBinding) => onChange({ mcpBinding })} />
        <div className="cf-satellite-field-grid">
          <EditorField label="远端地址" value={draft.endpoint} mono onChange={(endpoint) => onChange({ endpoint })} />
          <EditorField label="超时 ms" value={draft.timeoutMs} mono onChange={(timeoutMs) => onChange({ timeoutMs })} />
        </div>
      </>}

      {section === 'routing' && <>
        <EditorField label="执行条件" value={draft.condition} mono multiline onChange={(condition) => onChange({ condition })} />
        <EditorField label="主链 next" value={draft.next} mono onChange={(next) => onChange({ next })} />
        {interactionNode ? <InteractionContractEditor files={files} componentRef={draft.componentRef} currentNodeId={node.id} graphNodes={graphNodes} inputBinding={draft.inputBinding} actionRoutes={draft.actionRoutes} showBindings={false} onChange={onChange} /> : <EditorField label="动作路由 JSON" value={draft.actionRoutes} mono multiline onChange={(actionRoutes) => onChange({ actionRoutes })} />}
      </>}

      {section === 'safety' && <>
        <EditorField label="副作用" value={draft.effect} mono onChange={(effect) => onChange({ effect })} />
        <EditorField label="权限策略" value={draft.permission} mono onChange={(permission) => onChange({ permission })} />
        <EditorField label="失败策略" value={draft.failurePolicy} mono onChange={(failurePolicy) => onChange({ failurePolicy })} />
        <EditorField label="重放策略" value={draft.replayPolicy} mono onChange={(replayPolicy) => onChange({ replayPolicy })} />
        <EditorField label="幂等策略" value={draft.idempotency} mono onChange={(idempotency) => onChange({ idempotency })} />
        <label className="cf-satellite-check"><input type="checkbox" checked={draft.auditLog} onChange={(event) => onChange({ auditLog: event.target.checked })} /><span>记录审计日志</span></label>
      </>}

      {section === 'artifacts' && <>
        <EditorField label="主输出" value={draft.primaryOutput} mono onChange={(primaryOutput) => onChange({ primaryOutput })} />
        <EditorField label="产物类型" value={draft.artifactType} onChange={(artifactType) => onChange({ artifactType })} />
        <EditorField label="交付位置" value={draft.deliveryPath} mono onChange={(deliveryPath) => onChange({ deliveryPath })} />
        <EditorField label="输出契约" value={draft.outputContract} mono onChange={(outputContract) => onChange({ outputContract })} />
      </>}

      {presetFields}
      {section === 'component' && <InteractionAssetEditor flowId={flowId} componentRef={draft.componentRef} onComponentRefChange={(componentRef) => onChange({ componentRef })} onFilesChange={onFilesChange} />}
    </div>
  )
}

export function NodeDetailCard({ node, section, graphNodes, graphEdges, files, flowId, pinned, runState, runEvents = [], editable = false, draft, dirty = false, saving = false, authoringPath, onFilesChange, onDraftChange, onReset, onSave, onContinue, onSaveAndContinue, onTogglePin, onClose }: {
  node: FlowNode
  section: NodeDetailSection
  graphNodes: FlowNode[]
  graphEdges: FlowEdge[]
  files: FlowFiles
  flowId: string
  pinned: boolean
  runState?: NodeRunState
  runEvents?: FlowEvent[]
  editable?: boolean
  draft: NodeDraft
  dirty?: boolean
  saving?: boolean
  authoringPath?: NodeAuthoringPath | null
  onFilesChange: (files: FlowFiles) => void
  onDraftChange: (patch: Partial<NodeDraft>) => void
  onReset: () => void
  onSave: () => void | Promise<void>
  onContinue?: () => void
  onSaveAndContinue?: () => void | Promise<void>
  onTogglePin: () => void
  onClose: () => void
}) {
  const category = getNodeCategory(node)
  const palette = getNodePalette(node)
  const semanticKind = resolveNodeSemanticKind(node)
  const meta = NODE_DETAIL_SECTION_BY_ID.get(section)!
  const details = useMemo(() => buildNodeDetailFacts(node, section, { edges: graphEdges, runState, runEvents }), [graphEdges, node, runEvents, runState, section])
  const displayLabel = getProcessDisplayLabel(node) || category.label
  const sectionEditable = editable && section !== 'runtime'
  const authoringIndex = authoringPath?.steps.findIndex((item) => item.section === section) ?? -1
  const authoringStep = authoringIndex >= 0 ? authoringPath?.steps[authoringIndex] : null
  const hasNextAuthoringStep = Boolean(authoringPath && authoringIndex >= 0 && authoringIndex < authoringPath.steps.length - 1)

  return (
    <aside className={`cf-node-satellite cf-node-satellite-${section} ${sectionEditable ? 'editable' : 'readonly'}`} data-node-id={node.id} data-node-kind={semanticKind} data-detail-section={section} style={{ '--satellite-accent': palette.color, '--satellite-tint': palette.bg } as React.CSSProperties}>
      <header className="cf-node-satellite-head">
        <div className="cf-node-satellite-heading"><span className="cf-node-satellite-icon"><SectionIcon section={section} /></span><strong>{draft.displayName || draft.title || node.id}</strong><span className="cf-node-satellite-kind">{authoringStep ? `${authoringIndex + 1}/${authoringPath!.total} · ${authoringStep.label}` : details.title || meta.label}</span></div>
        <div className="cf-node-satellite-actions"><span className="cf-node-satellite-drag" title="拖动详情组件"><GripHorizontal aria-hidden="true" /></span><button type="button" className={`cf-node-satellite-pin ${pinned ? 'active' : ''}`} aria-label={pinned ? '取消钉住详情组件' : '钉住详情组件'} aria-pressed={pinned} title={pinned ? '已钉住，刷新后恢复' : '未钉住，刷新后不恢复'} onClick={onTogglePin}>{pinned ? <Pin aria-hidden="true" /> : <PinOff aria-hidden="true" />}</button><button type="button" className="cf-node-satellite-close" aria-label="关闭详情组件" title="关闭详情组件" onClick={onClose}><X aria-hidden="true" /></button></div>
        <p><span>{sectionEditable ? (dirty ? '有未保存修改' : '可直接编辑') : displayLabel}</span><code>{node.id}</code></p>
      </header>
      <section className="cf-node-satellite-body" aria-label={`${details.title}详情`}>
        {sectionEditable ? (
          <form className="cf-satellite-editor" onSubmit={(event) => { event.preventDefault(); void onSave() }}>
            <div className="cf-satellite-editor-scroll">{authoringStep && <div className={`cf-authoring-step-intro ${authoringStep.complete ? 'complete' : ''}`}><span>{authoringStep.complete ? '当前配置已满足' : '当前步骤'}</span><strong>{authoringStep.label}</strong><p>{authoringStep.hint}</p></div>}<SectionEditor section={section} draft={draft} files={files} flowId={flowId} node={node} graphNodes={graphNodes} onFilesChange={onFilesChange} onChange={onDraftChange} /></div>
            <footer><span className={dirty ? 'dirty' : ''}>{authoringStep ? `步骤 ${authoringIndex + 1}/${authoringPath!.total}` : dirty ? '修改尚未保存' : '配置已同步'}</span><button type="button" onClick={onReset} disabled={!dirty || saving} title="撤销本节点未保存修改"><RotateCcw />撤销</button>{authoringStep ? <button type="button" className="primary guide" disabled={saving} onClick={() => void (dirty ? onSaveAndContinue?.() : onContinue?.())}>{dirty ? <Save /> : <ChevronRight />}{saving ? '保存中' : dirty ? hasNextAuthoringStep ? '保存并继续' : '保存并完成' : hasNextAuthoringStep ? '下一步' : '完成配置'}</button> : <button type="submit" className="primary" disabled={!dirty || saving}><Save />{saving ? '保存中' : '保存'}</button>}</footer>
          </form>
        ) : (
          <article className={`cf-node-detail-card ${section}`} data-detail-section={section}><header><SectionIcon section={section} /><strong>{details.title}</strong></header><p className="cf-node-detail-description">{details.description}</p><dl>{details.fields.map((item) => <div key={item.label} data-tone={item.tone || 'default'}><dt>{item.label}</dt><dd className={item.mono ? 'mono' : ''} title={item.value}>{item.value}</dd></div>)}</dl></article>
        )}
      </section>
    </aside>
  )
}
