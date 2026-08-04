import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react'
import { Bot, CheckCircle2, CircleAlert, Loader2, Save, ShieldCheck, Sparkles, X } from 'lucide-react'
import { Box } from '../../ui.tsx'
import {
  ApiError,
  acceptCreatorProposal,
  composeCreatorRecipe,
  fetchCreatorProject,
  fetchCreatorSession,
  freezeCreatorNode,
  previewCreatorProposal,
  proposeCreatorNodeValues,
  refineCreatorNodeWithAi,
  rejectCreatorProposal,
  type CreatorCapabilityGap,
  type CreatorProjection,
  type CreatorProposal,
  type CreatorTrustedRecipeNode,
  type FlowEvent,
  type FlowFiles,
  type FlowGraph,
  type FlowNode,
  type RunResult,
} from '../../api.ts'
import { showToast } from '../../toast.tsx'
import { FlowGraphView } from './FlowGraphView.tsx'
import type { NodeRunState } from './runState.ts'

type CreatorWorkspaceProps = {
  flowId: string
  files: FlowFiles
  showEngineeringSemantics: boolean
  onShowEngineeringSemanticsChange: (visible: boolean) => void
  runStatus?: string
  nodeRunStates?: Map<string, NodeRunState>
  runEvents?: FlowEvent[]
  runCompletionVisible?: boolean
  runCompletion?: RunResult
  onDismissRunCompletion?: () => void
  onOpenRunLog?: (run: RunResult) => void
  onOpenRunResult?: (run: RunResult) => void
  onOpenPendingInteraction?: () => void
}

const creatorId = () => `creator.${crypto.randomUUID()}`

function creatorError(error: unknown) {
  if (error instanceof ApiError) {
    const code = String(error.detail?.code || '')
    if (code === 'AI_CREATOR_FLOW_MODEL_UNBOUND') return '整体编排模型尚未配置。打开工程语义后，在模型设置中绑定 mentor 模型。'
    if (code === 'AI_CREATOR_NODE_MODEL_UNBOUND') return '节点深化模型尚未配置。打开工程语义后，在模型设置中绑定 mentor 模型。'
    return error.message
  }
  return error instanceof Error ? error.message : 'Creator 请求失败。'
}

function fieldSummary(value: unknown) {
  if (Array.isArray(value)) return value.join('、')
  if (typeof value === 'boolean') return value ? '是' : '否'
  return value === undefined || value === null ? '' : String(value)
}

function creatorGraph(flowId: string, creator: CreatorProjection | null): FlowGraph {
  if (!creator) return {
    id: `creator:${flowId}:empty`,
    name: '新的 Creator 项目',
    nodes: [{
      id: 'creator.start', title: '开始创作', display_name: '开始创作', type: 'start', action: 'start',
      description: '说出你想实现的结果。', x: 80, y: 160, scope: 'creator', locked: true,
      data: { creator_semantics: { empty: true } },
    }],
    edges: [],
  }
  const frozen = new Set(creator.frozen_steps)
  return {
    id: `creator:${flowId}:r${creator.revision}`,
    name: creator.intent,
    nodes: creator.trusted_recipe.nodes.map((node, index) => ({
      id: node.id,
      title: node.label,
      display_name: node.label,
      type: 'process',
      action: 'creator_recipe_step',
      kind: 'extension',
      executor: 'trusted_preset',
      effect: 'none',
      description: node.editable_fields
        .map((field) => `${field.label}：${fieldSummary(node.values[field.id] ?? field.default)}`)
        .filter((item) => !item.endsWith('：'))
        .join('；'),
      x: 80 + index * 360,
      y: 160,
      scope: 'creator',
      data: {
        creator_semantics: {
          trusted: frozen.has(node.id),
          preset_id: node.preset.id,
          preset_revision: node.preset.revision,
          values: node.values,
          fields: node.editable_fields.map(({ id, label }) => ({ id, label })),
        },
      },
    })),
    edges: creator.trusted_recipe.relations.map((edge) => ({
      from: edge.from_node_id,
      to: edge.to_node_id,
      label: edge.relation,
      kind: 'creator_relation',
      scope: 'root',
    })),
  }
}

function CreatorFieldEditor({ node, values, onChange }: {
  node: CreatorTrustedRecipeNode
  values: Record<string, unknown>
  onChange: (values: Record<string, unknown>) => void
}) {
  return <div className="cf-creator-field-list">{node.editable_fields.map((field) => {
    const value = values[field.id] ?? field.default ?? ''
    if (field.value_type === 'boolean') return <label key={field.id} className="check"><input type="checkbox" checked={Boolean(value)} onChange={(event) => onChange({ ...values, [field.id]: event.target.checked })} /><span>{field.label}</span></label>
    if (field.value_type === 'number') return <label key={field.id}><span>{field.label}{field.required && <i>必填</i>}</span><input type="number" value={Number(value)} onChange={(event) => onChange({ ...values, [field.id]: Number(event.target.value) })} /></label>
    if (field.value_type === 'string_list') return <label key={field.id}><span>{field.label}{field.required && <i>必填</i>}</span><textarea value={Array.isArray(value) ? value.join('\n') : ''} onChange={(event) => onChange({ ...values, [field.id]: event.target.value.split('\n').map((item) => item.trim()).filter(Boolean) })} /></label>
    return <label key={field.id}><span>{field.label}{field.required && <i>必填</i>}</span><input value={String(value)} onChange={(event) => onChange({ ...values, [field.id]: event.target.value })} /></label>
  })}</div>
}

function CreatorNodeEditor({ creator, node, values, prompt, proposal, impact, busy, onValuesChange, onPromptChange, onStage, onAskAi, onPreview, onAccept, onReject, onTrust, onClose }: {
  creator: CreatorProjection
  node: CreatorTrustedRecipeNode
  values: Record<string, unknown>
  prompt: string
  proposal: CreatorProposal | null
  impact: string
  busy: boolean
  onValuesChange: (values: Record<string, unknown>) => void
  onPromptChange: (value: string) => void
  onStage: () => void
  onAskAi: () => void
  onPreview: () => void
  onAccept: () => void
  onReject: () => void
  onTrust: () => void
  onClose: () => void
}) {
  const trusted = creator.frozen_steps.includes(node.id)
  return <article className="cf-creator-node-editor">
    <header className="cf-node-satellite-head"><div><span>节点深入调整</span><strong>{node.label}</strong><small>{node.preset.id} · r{node.preset.revision}</small></div><button type="button" onClick={onClose} title="关闭节点编辑"><X /></button></header>
    <div className="cf-creator-node-editor-body">
      <CreatorFieldEditor node={node} values={values} onChange={onValuesChange} />
      <button type="button" className="cf-creator-primary" onClick={onStage} disabled={busy || proposal !== null}><Save />提交字段修改</button>
      <label className="cf-creator-ai-request"><span><Bot />继续和 AI 对齐这个节点</span><textarea value={prompt} onChange={(event) => onPromptChange(event.target.value)} placeholder="例如：只保留官方和研究机构的 RSS，并按重要性排序" /></label>
      <button type="button" onClick={onAskAi} disabled={busy || !prompt.trim() || proposal !== null}><Sparkles />生成节点建议</button>
      {proposal && <section className="cf-creator-review"><strong>变更审阅</strong><p>{proposal.summary}</p>{impact ? <p className="impact">{impact}</p> : <button type="button" onClick={onPreview}>检查影响</button>}<div><button type="button" onClick={onReject} disabled={busy}>拒绝</button><button type="button" className="cf-creator-primary" onClick={onAccept} disabled={busy || !impact}>接受修改</button></div></section>}
      <button type="button" className={`cf-creator-trust ${trusted ? 'trusted' : ''}`} onClick={onTrust} disabled={busy || trusted || proposal !== null}><ShieldCheck />{trusted ? '节点已可信' : '确认节点可信'}</button>
    </div>
  </article>
}

export function CreatorWorkspace(props: CreatorWorkspaceProps) {
  const { flowId, files, showEngineeringSemantics, onShowEngineeringSemanticsChange } = props
  const [creator, setCreator] = useState<CreatorProjection | null>(null)
  const [loading, setLoading] = useState(true)
  const [goal, setGoal] = useState('')
  const [gap, setGap] = useState<CreatorCapabilityGap | null>(null)
  const [selectedId, setSelectedId] = useState('')
  const [draftValues, setDraftValues] = useState<Record<string, unknown>>({})
  const [prompt, setPrompt] = useState('')
  const [proposal, setProposal] = useState<CreatorProposal | null>(null)
  const [impact, setImpact] = useState('')
  const [busy, setBusy] = useState(false)
  const intentRef = useRef<HTMLTextAreaElement | null>(null)

  useEffect(() => {
    let active = true
    setLoading(true)
    fetchCreatorProject(flowId).then(({ creator: loaded }) => {
      if (!active || !loaded) return
      setCreator(loaded)
      setGoal(loaded.intent)
    }).catch((error) => {
      if (active && (!(error instanceof ApiError) || error.status !== 404)) showToast({ title: 'Creator 项目读取失败', description: creatorError(error), type: 'error' })
    }).finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [flowId])

  const graph = useMemo(() => creatorGraph(flowId, creator), [creator, flowId])
  const selectedRecipeNode = useMemo(() => creator?.trusted_recipe.nodes.find((node) => node.id === selectedId) || null, [creator, selectedId])
  const selectedGraphNode = useMemo(() => graph.nodes.find((node) => node.id === selectedId) || null, [graph.nodes, selectedId])
  const trustedCount = creator?.frozen_steps.length || 0
  const totalCount = creator?.trusted_recipe.nodes.length || 0

  const saveCreator = (next: CreatorProjection) => {
    setCreator(next)
    const selected = next.trusted_recipe.nodes.find((node) => node.id === selectedId)
    if (selected) setDraftValues(selected.values)
  }
  const notifyError = (title: string, error: unknown) => showToast({ title, description: creatorError(error), type: 'error' })
  const openNode = (node: FlowNode) => {
    if (!creator) { intentRef.current?.focus(); return }
    const recipeNode = creator.trusted_recipe.nodes.find((item) => item.id === node.id)
    if (!recipeNode) return
    setSelectedId(recipeNode.id)
    setDraftValues(recipeNode.values)
    setPrompt('')
    setProposal(creator.pending_proposals.find((pending) => pending.changes.some((change) => change.target_id === recipeNode.id)) || null)
    setImpact('')
  }
  const compose = async (event: FormEvent) => {
    event.preventDefault()
    if (goal.trim().length < 3) return
    setBusy(true); setGap(null)
    try {
      const result = await composeCreatorRecipe({ session_id: creatorId(), project_id: flowId, goal: goal.trim() })
      if (result.capability_gap) { setGap(result.capability_gap); return }
      if (!result.creator) throw new Error('整体草稿没有返回。')
      saveCreator(result.creator)
      showToast({ title: '整体草稿已生成', description: '所有节点均为待审核状态。', type: 'success' })
    } catch (error) { notifyError('整体草稿生成失败', error) } finally { setBusy(false) }
  }
  const stageValues = async () => {
    if (!creator || !selectedRecipeNode) return
    setBusy(true)
    try {
      const result = await proposeCreatorNodeValues(creator.session_id, { expected_revision: creator.revision, author: 'creator-workbench', summary: `调整节点：${selectedRecipeNode.label}`, changes: [{ id: `edit.${selectedRecipeNode.id}.${creator.revision}`, target_id: selectedRecipeNode.id, operation: 'set_creator_binding', value: draftValues }] })
      setProposal(result.proposal); setImpact('')
    } catch (error) { notifyError('节点修改提交失败', error) } finally { setBusy(false) }
  }
  const askAi = async () => {
    if (!creator || !selectedRecipeNode || !prompt.trim()) return
    setBusy(true)
    try {
      const result = await refineCreatorNodeWithAi(creator.session_id, selectedRecipeNode.id, { prompt: prompt.trim(), expected_revision: creator.revision, author: 'creator-workbench', summary: `AI 深化节点：${selectedRecipeNode.label}` })
      setProposal(result.proposal); setImpact('')
    } catch (error) { notifyError('AI 节点深化失败', error) } finally { setBusy(false) }
  }
  const preview = async () => {
    if (!creator || !proposal) return
    try {
      const result = await previewCreatorProposal(creator.session_id, proposal.proposal_id)
      setImpact(result.impact.plain_summary || '该修改只影响当前节点。')
    } catch (error) { notifyError('影响检查失败', error) }
  }
  const accept = async () => {
    if (!creator || !proposal) return
    setBusy(true)
    try {
      const result = await acceptCreatorProposal(creator.session_id, proposal.proposal_id)
      saveCreator(result.creator); setProposal(null); setImpact(''); setPrompt('')
      showToast({ title: '节点修改已接受', type: 'success' })
    } catch (error) { notifyError('接受修改失败', error) } finally { setBusy(false) }
  }
  const reject = async () => {
    if (!creator || !proposal) return
    setBusy(true)
    try { const result = await rejectCreatorProposal(creator.session_id, proposal.proposal_id); saveCreator(result.creator); setProposal(null); setImpact('') }
    catch (error) { notifyError('拒绝修改失败', error) } finally { setBusy(false) }
  }
  const trust = async () => {
    if (!creator || !selectedRecipeNode) return
    setBusy(true)
    try {
      await freezeCreatorNode(creator.session_id, selectedRecipeNode.id)
      const result = await fetchCreatorSession(creator.session_id)
      saveCreator(result.creator)
      showToast({ title: '节点已确认为可信', type: 'success' })
    } catch (error) { notifyError('节点可信确认失败', error) } finally { setBusy(false) }
  }

  const nodeEditors = selectedRecipeNode && selectedGraphNode && creator ? [{
    editorId: `${selectedRecipeNode.id}:creator`, nodeId: selectedRecipeNode.id, section: 'contract' as const,
    width: 470, height: 620, connectorFraction: 0.28,
    content: <CreatorNodeEditor creator={creator} node={selectedRecipeNode} values={draftValues} prompt={prompt} proposal={proposal} impact={impact} busy={busy} onValuesChange={setDraftValues} onPromptChange={setPrompt} onStage={() => void stageValues()} onAskAi={() => void askAi()} onPreview={() => void preview()} onAccept={() => void accept()} onReject={() => void reject()} onTrust={() => void trust()} onClose={() => setSelectedId('')} />,
  }] : []

  return <div className={`cf-design-studio outcome-mode creator-mode ${nodeEditors.length ? 'drawer-open' : ''}`}>
    <div className="cf-design-main">
      <div className="cf-design-modebar cf-creator-modebar">
        <div><Sparkles /><span><b>整体草稿</b><small>{creator?.intent || '等待创作目标'}</small></span></div>
        <div className={`cf-creator-readiness ${totalCount > 0 && trustedCount === totalCount ? 'ready' : ''}`}><ShieldCheck /><span>{trustedCount}/{totalCount || '-'} 节点已可信</span></div>
      </div>
      <Box className="cf-flow-panel cf-flow-overview cf-flow-overview-studio" overflow="hidden">
        <FlowGraphView
          graph={graph}
          files={files}
          displayMode="outcome"
          workspaceSemantics="creator"
          showEngineeringSemantics={showEngineeringSemantics}
          onShowEngineeringSemanticsChange={onShowEngineeringSemanticsChange}
          selectedNode={selectedGraphNode}
          focusNodeId={selectedId || null}
          onSelectNode={openNode}
          nodeEditors={nodeEditors}
          activeNodeEditorId={selectedId || null}
          onCloseNodeEditor={() => setSelectedId('')}
          readOnlyGraph
          runStatus={props.runStatus}
          nodeRunStates={props.nodeRunStates}
          runEvents={props.runEvents}
          runCompletionVisible={props.runCompletionVisible}
          runCompletion={props.runCompletion}
          onDismissRunCompletion={props.onDismissRunCompletion}
          onOpenRunLog={props.onOpenRunLog}
          onOpenRunResult={props.onOpenRunResult}
          onOpenPendingInteraction={props.onOpenPendingInteraction}
        />
        {!creator && !loading && <form className="cf-creator-intent-panel" onSubmit={compose}>
          <label><span>想在这张画布上完成什么？</span><textarea ref={intentRef} aria-label="创作目标" value={goal} onChange={(event) => setGoal(event.target.value)} placeholder="例如：每天收集可靠的 AI 资讯，筛选后生成中文日报" /></label>
          <button type="submit" className="cf-creator-primary" disabled={busy || goal.trim().length < 3}>{busy ? <Loader2 className="spinning" /> : <Sparkles />}生成整体草稿</button>
          {gap && <div className="cf-creator-gap"><CircleAlert /><div><strong>可信能力不足</strong>{gap.needed_capabilities.map((item) => <span key={item}>{item}</span>)}</div></div>}
        </form>}
        {loading && <div className="cf-creator-loading"><Loader2 className="spinning" /><span>正在读取 Creator 项目</span></div>}
        {creator?.generation_readiness.ready && <div className="cf-creator-ready-notice"><CheckCircle2 /><span>Creator 设计已就绪</span></div>}
      </Box>
    </div>
  </div>
}
