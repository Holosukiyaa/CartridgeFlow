import { useEffect, useRef } from 'react'
import { Send, Sparkles, X } from 'lucide-react'
import type { CreatorRecipeNode, CreatorRecipePreview } from '../api/types.ts'
import { copy } from '../copy.ts'
import { Button, cx } from '../ui/index.ts'

export type StewardMessage = { id: string; role: 'assistant' | 'user'; text: string }
export type StewardScope = 'recipe' | 'node'

export function Steward({
  messages,
  input,
  busy,
  error,
  scope,
  contextNodes,
  preview,
  onInput,
  onSubmit,
  onScope,
  onApplyPreview,
  onRejectPreview,
  onClearContext,
  onRemoveContext,
  onClose,
}: {
  messages: StewardMessage[]
  input: string
  busy: boolean
  error: string
  scope: StewardScope
  contextNodes: CreatorRecipeNode[]
  preview: CreatorRecipePreview | null
  onInput: (value: string) => void
  onSubmit: () => void
  onScope: (scope: StewardScope) => void
  onApplyPreview: () => void
  onRejectPreview: () => void
  onClearContext: () => void
  onRemoveContext: (nodeId: string) => void
  onClose?: () => void
}) {
  const threadRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    threadRef.current?.scrollTo({ top: threadRef.current.scrollHeight, behavior: 'smooth' })
  }, [busy, messages, preview])

  return <aside className="steward" aria-label={copy.steward}>
    <header className="steward-head">
      <div>
        <strong>{copy.steward}</strong>
        <small>共创AI只帮你改方案，不进入运行时</small>
      </div>
      {onClose ? <Button variant="icon" aria-label={copy.close} onClick={onClose}><X size={14} /></Button> : null}
    </header>
    <div className="steward-modes" role="tablist" aria-label={copy.steward}>
      <button type="button" className={scope === 'recipe' ? 'is-on' : ''} onClick={() => onScope('recipe')}>{copy.stewardWhole}</button>
      <button type="button" className={scope === 'node' ? 'is-on' : ''} onClick={() => onScope('node')}>{copy.stewardStep}</button>
    </div>
    {contextNodes.length ? <div className="steward-chips">
      {contextNodes.map((node) => <button type="button" key={node.id} onClick={() => onRemoveContext(node.id)}>{node.label}</button>)}
      <button type="button" className="is-clear" onClick={onClearContext}>{copy.stewardClear}</button>
    </div> : null}
    <div className="steward-thread" ref={threadRef}>
      {messages.map((message) => <article className={cx('steward-msg', `is-${message.role}`)} key={message.id}>
        {message.role === 'assistant' ? <span className="avatar" aria-hidden="true"><Sparkles size={10} /></span> : null}
        <p>{message.text}</p>
      </article>)}
      {preview ? <section className="steward-preview">
        <strong>{copy.stewardPreview}</strong>
        <div className="impact-row">
          <div><b>{preview.impact.added_node_ids.length}</b><small>{copy.stewardAdded}</small></div>
          <div><b>{preview.impact.removed_node_ids.length}</b><small>{copy.stewardRemoved}</small></div>
          <div><b>{preview.impact.retained_node_ids.length}</b><small>{copy.stewardKept}</small></div>
        </div>
        <div className="answers">
          <Button variant="ghost" disabled={busy} onClick={onRejectPreview}>{copy.stewardReject}</Button>
          <Button disabled={busy} onClick={onApplyPreview}>{copy.stewardApply}</Button>
        </div>
      </section> : null}
      {busy ? <p className="steward-busy">{copy.stewardTalking}</p> : null}
      {error ? <p className="steward-error" role="alert">{error}</p> : null}
    </div>
    <form className="steward-foot" onSubmit={(event) => { event.preventDefault(); onSubmit() }}>
      <textarea
        value={input}
        disabled={busy}
        placeholder={copy.stewardPlaceholder}
        onChange={(event) => onInput(event.currentTarget.value)}
        onKeyDown={(event) => {
          if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault()
            onSubmit()
          }
        }}
      />
      <Button type="submit" disabled={busy || input.trim().length < 3}><Send size={14} />{copy.stewardSend}</Button>
    </form>
  </aside>
}
