import { useEffect, useState } from 'react'
import { ChevronRight, Puzzle, X } from 'lucide-react'
import {
  acceptCreatorProposal,
  ApiError,
  confirmCreatorNode,
  fetchCreatorSession,
  previewCreatorProposal,
  proposeCreatorNodeValues,
  refineCreatorNodeWithAi,
  rejectCreatorProposal,
  type CreatorProjection,
  type CreatorProposal,
  type CreatorRecipeNode,
} from '../api/client.ts'
import { copy } from '../copy.ts'
import { Button, StatusBadge } from '../ui/index.ts'
import { stepContract } from './graph.ts'
import { nodeReviewState, requiredFieldsEmpty, trustCopy } from './model.ts'

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
  const state = nodeReviewState(creator, node)
  const unresolved = state === 'unresolved'
  const changed = JSON.stringify(values) !== JSON.stringify(node.values)
  const index = creator.trusted_recipe.nodes.findIndex((item) => item.id === node.id)
  const nextNode = creator.trusted_recipe.nodes[index + 1]
  const isBusy = busy || working
  const trust = trustCopy(node.resolution?.capability?.trust_scope)
  const contract = stepContract(creator, node)

  useEffect(() => {
    setValues(node.values)
    setPrompt('')
    setProposal(creator.pending_proposals.find((item) => item.changes.some((change) => change.target_id === node.id)) || null)
    setImpact('')
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

  const confirm = async () => {
    setWorking(true)
    try {
      await confirmCreatorNode(creator.session_id, node.id)
      const result = await fetchCreatorSession(creator.session_id)
      onCreatorChange(result.creator)
    } catch (error) { fail(error) } finally { setWorking(false) }
  }

  return <aside className="detail" aria-label={`审核 ${node.label}`}>
    <header className="detail-head">
      <div>
        <small>{String(index + 1).padStart(2, '0')}</small>
        <StatusBadge state={state} />
        <h2>{node.label}</h2>
      </div>
      <div className="detail-head-actions">
        <Button variant="icon" aria-label={copy.openLayer2} title={copy.openLayer2} onClick={() => onOpenLayer(node.id)}><Puzzle size={14} /></Button>
        <Button variant="icon" aria-label={copy.close} onClick={onClose}><X size={14} /></Button>
      </div>
    </header>
    <div className="detail-body">
      {returned ? <p className="return-note">{copy.returnedFromWorkshop}</p> : null}
      <section className="block"><strong>{copy.nodeGoal}</strong><p>{node.description}</p></section>
      <section className="block">
        <strong>{copy.currentApproach}</strong>
        {unresolved ? <div className="capability is-gap"><span>待补齐 是方案的一部分，不是报错；需要进入第二层选定做法后才能继续确认。</span></div> : null}
        <Button onClick={() => onOpenLayer(node.id)}><Puzzle size={14} />{unresolved ? '打开第二层 · 补齐' : '查看或替换这一步的内部做法'}</Button>
        <p className="fill-label">回填后</p>
        <div className="capability">
          <span>{node.label}<em>{trust}</em></span>
          <button type="button" className="ghost-link" onClick={() => onOpenLayer(node.id)}><Puzzle size={12} />{copy.inspectLayer2}</button>
        </div>
      </section>
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
      <Button variant="ghost" onClick={onClose}>{copy.deferConfirm}</Button>
      <Button disabled={isBusy || state === 'confirmed' || changed || unresolved || requiredFieldsEmpty(node, values)} onClick={() => void confirm()}>
        {nextNode ? copy.confirmNext : copy.confirmNode} <ChevronRight />
      </Button>
    </footer>
  </aside>
}
