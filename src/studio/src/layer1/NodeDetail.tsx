import { useEffect, useState } from 'react'
import { ChevronRight, Puzzle, X } from 'lucide-react'
import {
  acceptCreatorProposal,
  ApiError,
  confirmCreatorNode,
  discoverCreatorSources,
  fetchCreatorSession,
  inspectCreatorSource,
  previewCreatorProposal,
  proposeCreatorNodeValues,
  refineCreatorNodeWithAi,
  rejectCreatorCapability,
  rejectCreatorProposal,
  setCreatorExperience,
  type CreatorProjection,
  type CreatorProposal,
  type CreatorRecipeNode,
  type CreatorSourceCandidate,
} from '../api/client.ts'
import { copy } from '../copy.ts'
import { Button, Dialog, StatusBadge } from '../ui/index.ts'
import { stepContract } from './graph.ts'
import { nodeReviewState, requiredFieldsEmpty, trustCopy } from './model.ts'

type CreatorSourceReference = { id: string; name?: string; remote_url?: string; rss_url?: string }
type SourceInspection = Awaited<ReturnType<typeof inspectCreatorSource>>
type ExperienceDraft = { component_id: string; field_sources: Record<string, string> }

function slotDraft(slot: NonNullable<CreatorRecipeNode['experience']>['slots'][number]): ExperienceDraft {
  return { component_id: slot.selected_component_id, field_sources: { ...slot.field_sources } }
}

export function NodeDetail({
  creator,
  node,
  busy,
  returned,
  onCreatorChange,
  onClose,
  onOpenNode,
  onOpenLayer,
  onModelRequired,
}: {
  creator: CreatorProjection
  node: CreatorRecipeNode
  busy: boolean
  returned?: boolean
  onCreatorChange: (creator: CreatorProjection) => void
  onClose: () => void
  onOpenNode: (nodeId: string) => void
  onOpenLayer: (nodeId: string) => void
  onModelRequired: () => void
}) {
  const [values, setValues] = useState(node.values)
  const [prompt, setPrompt] = useState('')
  const [proposal, setProposal] = useState<CreatorProposal | null>(() => creator.pending_proposals.find((item) => item.changes.some((change) => change.target_id === node.id)) || null)
  const [impact, setImpact] = useState('')
  const [working, setWorking] = useState(false)
  const [sourceCandidates, setSourceCandidates] = useState<CreatorSourceCandidate[]>([])
  const [sourceUrl, setSourceUrl] = useState('')
  const [inspection, setInspection] = useState<SourceInspection | null>(null)
  const [sourceError, setSourceError] = useState('')
  const [experienceDrafts, setExperienceDrafts] = useState<Record<string, ExperienceDraft>>({})
  const [leaveDialogOpen, setLeaveDialogOpen] = useState(false)
  const state = nodeReviewState(creator, node)
  const unresolved = state === 'unresolved'
  const changed = JSON.stringify(values) !== JSON.stringify(node.values)
  const index = creator.trusted_recipe.nodes.findIndex((item) => item.id === node.id)
  const nextNode = creator.trusted_recipe.nodes[index + 1]
  const isBusy = busy || working
  const capability = node.resolution?.capability
  const trust = trustCopy(capability?.trust_scope)
  const contract = stepContract(creator, node)
  const experienceSlots = node.experience?.slots || []
  const creatorSources = ((creator as CreatorProjection & { sources?: CreatorSourceReference[] }).sources || []).filter((source) => source.remote_url || source.rss_url)
  const sourceContextAvailable = Boolean(node.resolution?.needed_capability?.trim() || unresolved || creatorSources.length || experienceSlots.some((slot) => slot.sources.length))
  const experienceDirty = experienceSlots.some((slot) => {
    const draft = experienceDrafts[slot.id]
    return Boolean(draft && (draft.component_id !== slot.selected_component_id || JSON.stringify(draft.field_sources) !== JSON.stringify(slot.field_sources)))
  })

  const close = () => {
    if (changed || experienceDirty) {
      setLeaveDialogOpen(true)
      return
    }
    onClose()
  }

  const discardAndClose = () => {
    setLeaveDialogOpen(false)
    onClose()
  }

  useEffect(() => {
    setValues(node.values)
    setPrompt('')
    setProposal(creator.pending_proposals.find((item) => item.changes.some((change) => change.target_id === node.id)) || null)
    setImpact('')
    setSourceCandidates([])
    setInspection(null)
    setSourceError('')
    setExperienceDrafts(Object.fromEntries(experienceSlots.map((slot) => [slot.id, slotDraft(slot)])))
    setSourceUrl(creatorSources[0]?.remote_url || creatorSources[0]?.rss_url || '')
  }, [creator.pending_proposals, node.id, node.values])

  const fail = (error: unknown) => {
    if (error instanceof ApiError && error.code.includes('MODEL_UNBOUND')) onModelRequired()
  }

  const stage = async () => {
    setWorking(true)
    try {
      const result = await proposeCreatorNodeValues(creator.session_id, {
        expected_revision: creator.revision,
        author: 'creator',
        summary: `调整 ${node.label}`,
        changes: [{ id: `edit.${node.id}.${creator.revision}`, target_id: node.id, operation: 'set_creator_binding', value: values }],
      })
      setProposal(result.proposal)
    } catch (error) { fail(error) } finally { setWorking(false) }
  }

  const ask = async () => {
    if (!prompt.trim()) return
    setWorking(true)
    try {
      const result = await refineCreatorNodeWithAi(creator.session_id, node.id, {
        prompt: prompt.trim(), expected_revision: creator.revision, author: 'creator', summary: `深化 ${node.label}`,
      })
      setProposal(result.proposal)
    } catch (error) { fail(error) } finally { setWorking(false) }
  }

  const preview = async () => {
    if (!proposal) return
    setWorking(true)
    try {
      const result = await previewCreatorProposal(creator.session_id, proposal.proposal_id)
      const count = result.impact.changed_steps?.length || 1
      setImpact(count === 1 ? '这次修改只影响当前步骤。' : `这次修改会影响 ${count} 个步骤。`)
    } catch (error) { fail(error) } finally { setWorking(false) }
  }

  const accept = async () => {
    if (!proposal) return
    setWorking(true)
    try {
      const result = await acceptCreatorProposal(creator.session_id, proposal.proposal_id)
      onCreatorChange(result.creator)
      setProposal(null)
      setImpact('')
      setPrompt('')
    } catch (error) { fail(error) } finally { setWorking(false) }
  }

  const reject = async () => {
    if (!proposal) return
    setWorking(true)
    try {
      const result = await rejectCreatorProposal(creator.session_id, proposal.proposal_id)
      onCreatorChange(result.creator)
      setValues(node.values)
      setProposal(null)
      setImpact('')
    } catch (error) { fail(error) } finally { setWorking(false) }
  }

  const rejectCapability = async () => {
    if (!capability) return
    setWorking(true)
    try {
      const result = await rejectCreatorCapability(creator.session_id, node.id, creator.revision)
      onCreatorChange(result.creator)
    } catch (error) { fail(error) } finally { setWorking(false) }
  }

  const discoverSources = async () => {
    setWorking(true)
    setSourceError('')
    try {
      const request = node.resolution?.needed_capability || node.description || node.label
      const result = await discoverCreatorSources(creator.session_id, request)
      setSourceCandidates(result.candidates)
      const firstUrl = result.candidates.find((candidate) => candidate.remote_url || candidate.rss_url)
      if (!sourceUrl && firstUrl) setSourceUrl(firstUrl.remote_url || firstUrl.rss_url)
    } catch (error) {
      setSourceError(error instanceof Error ? error.message : '来源发现失败')
      fail(error)
    } finally { setWorking(false) }
  }

  const inspectSource = async (url = sourceUrl) => {
    const target = url.trim()
    if (!target) return
    setWorking(true)
    setSourceError('')
    try {
      const result = await inspectCreatorSource(target)
      setInspection(result)
      setSourceUrl(target)
    } catch (error) {
      setSourceError(error instanceof Error ? error.message : '来源检查失败')
      fail(error)
    } finally { setWorking(false) }
  }

  const updateExperienceDraft = (slotId: string, next: Partial<ExperienceDraft>) => {
    setExperienceDrafts((current) => {
      const previous = current[slotId] || { component_id: '', field_sources: {} }
      return { ...current, [slotId]: { ...previous, ...next } }
    })
  }

  const saveExperience = async (slotId: string) => {
    const slot = experienceSlots.find((item) => item.id === slotId)
    const draft = experienceDrafts[slotId]
    if (!slot || !draft?.component_id) return
    setWorking(true)
    try {
      const result = await setCreatorExperience(creator.session_id, node.id, {
        expected_revision: creator.revision,
        expected_experience_revision: creator.experience_revision ?? 0,
        slot_id: slot.id,
        component_id: draft.component_id,
        field_sources: Object.fromEntries(Object.entries(draft.field_sources).filter(([, sourceId]) => sourceId)),
      })
      onCreatorChange(result.creator)
    } catch (error) { fail(error) } finally { setWorking(false) }
  }

  const confirm = async () => {
    setWorking(true)
    try {
      await confirmCreatorNode(creator.session_id, node.id)
      const result = await fetchCreatorSession(creator.session_id)
      onCreatorChange(result.creator)
    } catch (error) { fail(error) } finally { setWorking(false) }
  }

  return <><aside className="detail" aria-label={`审核 ${node.label}`}>
    <header className="detail-head">
      <div>
        <small>{String(index + 1).padStart(2, '0')}</small>
        <StatusBadge state={state} />
        <h2>{node.label}</h2>
      </div>
      <div className="detail-head-actions">
        <Button variant="icon" aria-label={copy.openLayer2} title={copy.openLayer2} onClick={() => onOpenLayer(node.id)}><Puzzle size={14} /></Button>
        <Button variant="icon" aria-label={copy.close} onClick={close}><X size={14} /></Button>
      </div>
    </header>
    <div className="detail-body">
      {returned && !unresolved ? <p className="return-note">{copy.returnedFromWorkshop}</p> : null}
      <section className="block"><strong>{copy.nodeGoal}</strong><p>{node.description}</p></section>
      <section className="block">
        <strong>{copy.currentApproach}</strong>
        {unresolved ? <div className="capability is-gap"><span>待补齐 是方案的一部分，不是报错；需要进入第二层选定做法后才能继续确认。</span></div> : null}
        <Button onClick={() => onOpenLayer(node.id)}><Puzzle size={14} />{unresolved ? '打开第二层 · 补齐' : '查看或替换这一步的内部做法'}</Button>
        {!unresolved && capability ? <>
          <p className="fill-label">回填后</p>
          <div className="capability">
            <span>{capability.label}<em>{trust} · v{capability.revision}</em></span>
            <button type="button" className="ghost-link" onClick={() => onOpenLayer(node.id)}><Puzzle size={12} />{copy.inspectLayer2}</button>
            <button type="button" className="ghost-link" disabled={isBusy} onClick={() => void rejectCapability()}>退回这个做法</button>
          </div>
        </> : null}
      </section>
      {sourceContextAvailable ? <section className="block">
        <strong>来源检查</strong>
        <div className="fields">
          <label>来源 URL<input list={`node-sources-${node.id}`} value={sourceUrl} disabled={isBusy} onChange={(event) => setSourceUrl(event.currentTarget.value)} /></label>
          <datalist id={`node-sources-${node.id}`}>
            {[...creatorSources, ...sourceCandidates].flatMap((source) => [source.remote_url, source.rss_url]).filter(Boolean).map((url) => <option value={url} key={url} />)}
          </datalist>
        </div>
        <div className="answers">
          <Button variant="ghost" disabled={isBusy} onClick={() => void discoverSources()}>发现来源</Button>
          <Button disabled={isBusy || !sourceUrl.trim()} onClick={() => void inspectSource()}>检查来源</Button>
        </div>
        {creatorSources.length ? <div className="fields">
          {creatorSources.map((source) => {
            const url = source.remote_url || source.rss_url || ''
            return <button type="button" className="ghost-link" key={source.id} disabled={isBusy || !url} onClick={() => void inspectSource(url)}>{source.name || source.id}</button>
          })}
        </div> : null}
        {sourceCandidates.length ? <div className="fields">
          {sourceCandidates.map((candidate) => {
            const url = candidate.remote_url || candidate.rss_url
            return <button type="button" className="ghost-link" key={candidate.id} disabled={isBusy || !url} onClick={() => void inspectSource(url)}>{candidate.name}</button>
          })}
        </div> : null}
        {sourceError ? <p className="muted">{sourceError}</p> : null}
        {inspection ? <div className="capability">
          <span>状态 <em>{inspection.status}</em></span>
          <span>类型 <em>{inspection.content_type}</em></span>
          <span>样本 <em>{inspection.sample || '无样本'}</em></span>
        </div> : null}
      </section> : null}
      {experienceSlots.length ? <section className="block">
        <strong>结果呈现</strong>
        {experienceSlots.map((slot) => {
          const draft = experienceDrafts[slot.id] || slotDraft(slot)
          const selected = slot.components.find((component) => component.id === draft.component_id)
          const mappingReady = Boolean(selected?.available && selected.fields.every((field) => !field.required || field.compatible_source_ids.includes(draft.field_sources[field.id] || '')))
          return <div className="capability" key={slot.id}>
            <label>{slot.label}<select value={draft.component_id} disabled={isBusy} onChange={(event) => {
              const component = slot.components.find((item) => item.id === event.currentTarget.value)
              const fieldSources = Object.fromEntries((component?.fields || []).map((field) => [field.id, draft.field_sources[field.id] || field.compatible_source_ids[0] || '']))
              updateExperienceDraft(slot.id, { component_id: event.currentTarget.value, field_sources: fieldSources })
            }}>
              <option value="">选择组件</option>
              {slot.components.map((component) => <option value={component.id} key={component.id} disabled={!component.available}>{component.label}</option>)}
            </select></label>
            {selected?.fields.map((field) => {
              const sourceIds = [...new Set([...(field.compatible_source_ids || []), draft.field_sources[field.id]].filter(Boolean))]
              return <label key={field.id}>{field.label}{field.required ? ' *' : ''}<select value={draft.field_sources[field.id] || ''} disabled={isBusy} onChange={(event) => updateExperienceDraft(slot.id, { field_sources: { ...draft.field_sources, [field.id]: event.currentTarget.value } })}>
                <option value="">选择字段来源</option>
                {sourceIds.map((sourceId) => <option value={sourceId} key={sourceId}>{slot.sources.find((source) => source.id === sourceId)?.label || sourceId}</option>)}
              </select></label>
            })}
            <Button variant="ghost" disabled={isBusy || !mappingReady} onClick={() => void saveExperience(slot.id)}>保存呈现</Button>
            <em>{slot.status === 'configured' ? '已配置' : '需要配置'}</em>
          </div>
        })}
      </section> : null}
      {node.studio_layer2?.params?.length ? <section className="block">
        <strong>使用者参数</strong>
        <p className="muted">{node.studio_layer2.params.map((item) => `${item.label}${item.required ? '（必填）' : ''}`).join('、')}</p>
      </section> : null}
      <section className="block">
        <strong>交接</strong>
        <p className="muted">{contract.inputs.length ? null : copy.contractEmptyIn}</p>
        {contract.outputs.length ? <p className="handoff">产出给 {contract.outputs.map((item) => <button type="button" key={item.nodeId} onClick={() => onOpenNode(item.nodeId)}><em>能力</em> {item.label}</button>)}</p> : <p className="muted">{copy.contractEmptyOut}</p>}
      </section>
      {node.editable_fields.length ? <section className="block">
        <strong>{copy.fields}</strong>
        <div className="fields">
          {node.editable_fields.map((field) => {
            const value = values[field.id] ?? field.default ?? ''
            if (field.value_type === 'boolean') {
              return <label className="check" key={field.id}>
                <input type="checkbox" checked={Boolean(value)} disabled={isBusy} onChange={(event) => setValues({ ...values, [field.id]: event.target.checked })} />
                {field.label}{field.required ? ' *' : ''}
              </label>
            }
            if (field.value_type === 'string_list') {
              return <label key={field.id}>{field.label}{field.required ? ' *' : ''}<textarea disabled={isBusy} value={Array.isArray(value) ? value.join('\n') : ''} onChange={(event) => setValues({ ...values, [field.id]: event.currentTarget.value.split('\n').map((item) => item.trim()).filter(Boolean) })} /></label>
            }
            return <label key={field.id}>{field.label}{field.required ? ' *' : ''}<input disabled={isBusy} type={field.value_type === 'number' ? 'number' : 'text'} value={String(value)} onChange={(event) => setValues({ ...values, [field.id]: field.value_type === 'number' ? Number(event.currentTarget.value) : event.currentTarget.value })} /></label>
          })}
        </div>
        {changed ? <Button variant="ghost" disabled={isBusy} onClick={() => void stage()}>{copy.saveFields}</Button> : null}
      </section> : null}
      <section className="block">
        <strong>{copy.aiSuggestion}</strong>
        {proposal ? <>
          <div className="compare">
            <article><small>{copy.current}</small><p>{node.description}</p></article>
            <article><small>{copy.suggested}</small><p>{proposal.summary}</p></article>
          </div>
          {impact ? <p>{impact}</p> : <Button variant="ghost" disabled={isBusy} onClick={() => void preview()}>{copy.previewImpact}</Button>}
          <div className="answers">
            <Button variant="ghost" disabled={isBusy} onClick={() => void reject()}>{copy.rejectSuggestion}</Button>
            <Button disabled={isBusy} onClick={() => void accept()}>{copy.applySuggestion}</Button>
          </div>
        </> : <>
          <textarea value={prompt} disabled={isBusy || changed} placeholder={copy.refinePlaceholder} onChange={(event) => setPrompt(event.currentTarget.value)} />
          <Button variant="ghost" disabled={isBusy || changed || !prompt.trim()} onClick={() => void ask()}>{copy.generateSuggestion}</Button>
        </>}
      </section>
    </div>
    <footer className="detail-actions">
      <Button variant="ghost" onClick={close}>{copy.deferConfirm}</Button>
      <Button disabled={isBusy || state === 'confirmed' || changed || experienceDirty || unresolved || requiredFieldsEmpty(node, values)} onClick={() => void confirm()}>
        {nextNode ? copy.confirmNext : copy.confirmNode} <ChevronRight />
      </Button>
    </footer>
  </aside>
    {leaveDialogOpen ? <Dialog
      title="放弃未保存的修改？"
      description="字段或结果呈现中有尚未保存的修改。离开后，这些修改将丢失。"
      onClose={() => setLeaveDialogOpen(false)}
    >
      <form onSubmit={(event) => { event.preventDefault(); discardAndClose() }}>
        <div className="dialog-foot">
          <span />
          <Button autoFocus variant="ghost" onClick={() => setLeaveDialogOpen(false)}>取消</Button>
          <Button type="submit">放弃修改</Button>
        </div>
      </form>
    </Dialog> : null}
  </>
}
