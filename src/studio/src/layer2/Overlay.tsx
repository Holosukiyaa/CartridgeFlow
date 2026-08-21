import { useEffect, useState } from 'react'
import { Check, Puzzle, Search, X } from 'lucide-react'
import type { CreatorProjection, CreatorRecipeNode, StudioLayer2, StudioLayer2Field } from '../api/types.ts'
import { proveStudioLayer2, publishStudioLayer2, saveStudioLayer2 } from '../api/client.ts'
import { capabilityApi } from '../api/workshop.ts'
import { L2_STAGES, type Layer2StageId } from '../config.ts'
import { copy } from '../copy.ts'
import { Button, cx } from '../ui/index.ts'

const KIND_CHIPS = ['开始', '展示结果', '人工审核', '整理内容', '调用本机工具', 'AI处理']

function fieldKind(schema: Record<string, unknown> | undefined) {
  if (schema?.type === 'array') return '列表'
  if (schema?.type === 'boolean') return '是/否'
  if (schema?.type === 'string' && (schema.format === 'uri' || schema.format === 'url')) return '链接'
  return '文本'
}

function nodeFields(node: CreatorRecipeNode): StudioLayer2Field[] {
  const fields: StudioLayer2Field[] = []
  const usedIds = new Set<string>()
  for (const slot of node.experience?.slots || []) {
    const component = slot.components.find((item) => item.id === slot.selected_component_id)
    const contracted = component?.fields.map((field) => {
      const sourceId = slot.field_sources[field.id] || field.id
      const source = slot.sources.find((item) => item.id === sourceId)
      return { id: field.id, label: field.label || field.id, schema: source?.schema, sourceId }
    }) || slot.sources.map((source) => ({ ...source, sourceId: source.id }))
    for (const field of contracted) {
      let id = field.id
      while (usedIds.has(id)) id = `${slot.id}_${id}`
      usedIds.add(id)
      fields.push({ id, label: field.label || field.id, kind: fieldKind(field.schema), source: `结果.${field.sourceId}` })
    }
  }
  return fields
}

function panelName(node: CreatorRecipeNode) {
  for (const slot of node.experience?.slots || []) {
    const component = slot.components.find((item) => item.id === slot.selected_component_id)
    if (component?.label) return component.label
  }
  return node.experience?.slots[0]?.label || '结果面板'
}

function emptyLayer(node: CreatorRecipeNode): StudioLayer2 {
  return node.studio_layer2 || {
    step_name: node.label,
    params: node.editable_fields.map((field) => ({
      ...field,
      default: Object.prototype.hasOwnProperty.call(node.values, field.id) ? node.values[field.id] : field.default,
    })),
    fields: nodeFields(node),
    template: '列表',
    preview: '正常',
    panel_name: panelName(node),
    deliver: node.resolution?.needed_capability || node.description || node.label,
    tools: [],
    handoff_in: '',
    handoff_out: '',
    internal_steps: ['开始', node.label, '完成'],
    proof: {},
  }
}

function hasSampleValue(value: unknown) {
  if (value === undefined || value === null) return false
  if (typeof value === 'string') return value.trim().length > 0
  if (Array.isArray(value)) return value.length > 0 && value.every(hasSampleValue)
  if (typeof value === 'object') return Object.keys(value).length > 0
  return true
}

function sampleValue(param: StudioLayer2['params'][number]) {
  return hasSampleValue(param.default) ? param.default : undefined
}

function displaySample(value: unknown) {
  if (Array.isArray(value)) return value.map(String).join('、')
  if (typeof value === 'object' && value !== null) return JSON.stringify(value)
  return String(value)
}

export function Layer2Overlay({
  creator,
  node,
  flowId,
  onClose,
  onPublished,
  onOpened,
  onCreator,
  onOpenResources,
}: {
  creator: CreatorProjection
  node: CreatorRecipeNode
  flowId?: string
  onClose: () => void
  onPublished: (nodeId: string, capabilityId?: string) => void
  onOpened: (nodeId: string, flowId: string) => void
  onCreator?: (next: CreatorProjection) => void
  onOpenResources?: () => void
}) {
  const visual = new URLSearchParams(window.location.search).get('visual')
  const startStage: Layer2StageId = visual === 'frame5' ? 'prove' : 'flow'
  const [stage, setStage] = useState<Layer2StageId>(startStage)
  const [inspectorTab, setInspectorTab] = useState<'approach' | 'handoff' | 'params'>('approach')
  const [selected, setSelected] = useState<'main' | 'tool' | 'start' | 'end' | string>('main')
  const [layer, setLayer] = useState<StudioLayer2>(() => emptyLayer(node))
  const [draft, setDraft] = useState<'idle' | 'generating' | 'ready' | 'failed'>(flowId ? 'ready' : 'generating')
  const [search, setSearch] = useState('')
  const [reusable, setReusable] = useState<Array<{ name: string; version: string; scope: string }>>([])
  const [advanced, setAdvanced] = useState(false)
  const [busy, setBusy] = useState(false)
  const [proving, setProving] = useState(false)
  const [error, setError] = useState('')
  const [proveNote, setProveNote] = useState('')
  const [infraNote, setInfraNote] = useState('')
  const [prodLevel, setProdLevel] = useState(false)
  const [publishAdvanced, setPublishAdvanced] = useState(false)
  const goal = node.resolution?.needed_capability || node.description
  const recipeGoal = creator.trusted_recipe.goal || creator.intent || ''
  const hasPath = layer.internal_steps.includes('开始') && layer.internal_steps.includes('完成') && layer.internal_steps.length >= 3
  const proof = layer.proof || {}
  const missing = [
    !hasPath ? '结构不完整' : '',
    !(proof.success && proof.safe_fail) ? '还没有成功 + 失败证据' : '',
  ].filter(Boolean)
  const nextLabel = L2_STAGES[Math.min(L2_STAGES.findIndex((item) => item.id === stage) + 1, 3)].label

  useEffect(() => setLayer(emptyLayer(node)), [node.id, node.studio_layer2?.saved_at])
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => { if (event.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])
  useEffect(() => {
    void capabilityApi.capabilityRegistry().then((payload) => {
      const items = (payload.capabilities || payload.entries || []) as Array<Record<string, unknown>>
      setReusable(items.slice(0, 12).map((item) => ({
        name: String(item.label || item.name || item.id || '能力'),
        version: `v${item.revision || 1}`,
        scope: String(item.trust_scope || '当前工作区'),
      })))
    }).catch(() => setReusable([]))
  }, [])
  useEffect(() => {
    if (visual === 'frame4' || visual === 'frame5') {
      setDraft('ready')
      return
    }
    if (flowId) {
      setDraft('ready')
      onOpened(node.id, flowId)
      return
    }
    let live = true
    setDraft('generating')
    void capabilityApi.createFlow({
      flow_id: `flow.l2.${node.id}.${Date.now()}`,
      name: `${node.label}内部做法`,
      description: goal,
    }).then((created) => {
      if (!live) return
      const id = String(created.flow_id || created.id || '')
      if (id) onOpened(node.id, id)
      setDraft('ready')
    }).catch(() => { if (live) { setDraft('failed'); setError('内部做法还没有保存，可以先在画布上搭步骤。') } })
    return () => { live = false }
  }, [flowId, goal, node.id, node.label, onOpened, visual])

  const persist = async (next = layer, extra: Partial<StudioLayer2> = {}) => {
    const body: Record<string, unknown> = { ...next, ...extra }
    const proof = (body.proof || {}) as StudioLayer2['proof']
    if (!proof.success && !proof.safe_fail) delete body.proof
    const result = await saveStudioLayer2(creator.session_id, node.id, creator.revision, body)
    onCreator?.(result.creator)
    const saved = result.creator.trusted_recipe.nodes.find((item) => item.id === node.id)?.studio_layer2
    if (saved) setLayer(saved)
    return result.creator
  }

  const saveNode = async () => {
    setBusy(true)
    setError('')
    try { await persist() } catch (reason) { setError(reason instanceof Error ? reason.message : '保存没有完成') }
    finally { setBusy(false) }
  }

  const prove = async () => {
    setProving(true)
    setError('')
    setProveNote('')
    setInfraNote('')
    try {
      const missingSamples = layer.params.filter((param) => param.required && !hasSampleValue(param.default))
      if (missingSamples.length) {
        setError(`请先为必填参数「${missingSamples.map((param) => param.label || param.id).join('、')}」填写真实样本，再运行证明`)
        return
      }
      const values: Record<string, unknown> = {}
      for (const param of layer.params) {
        const value = sampleValue(param)
        if (value !== undefined) values[param.id] = value
      }
      const latest = await persist()
      const ok = await proveStudioLayer2(latest.session_id, node.id, latest.revision, 'success', values)
      const failInputs: Record<string, unknown> = {}
      const fail = await proveStudioLayer2(ok.creator.session_id, node.id, ok.creator.revision, 'omit_required', failInputs)
      onCreator?.(fail.creator)
      const saved = fail.creator.trusted_recipe.nodes.find((item) => item.id === node.id)?.studio_layer2
      if (saved) setLayer(saved)
      const proof = saved?.proof || {}
      if (proof.success && proof.safe_fail) setProveNote('已登记成功路径与安全失败')
      else setError('还需要一次成功和一次安全失败')
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : '证明没有完成'
      setInfraNote(message)
      setError('这不是安全失败')
    } finally { setProving(false) }
  }

  const publish = async () => {
    if (missing.length) return
    setBusy(true)
    setError('')
    try {
      const latest = await persist()
      const result = await publishStudioLayer2(latest.session_id, node.id, latest.revision)
      onCreator?.(result.creator)
      onPublished(node.id)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '发布没有完成')
    } finally { setBusy(false) }
  }

  const filteredReusable = reusable.filter((item) => !search || item.name.includes(search))
  const columns = stage !== 'flow'
  const selectedToolLabel = layer.tools.length ? `调用本机工具（已选 ${layer.tools.length} 项）` : '调用本机工具'

  return <div className="layer2-backdrop" role="presentation">
    <div className="layer2" role="dialog" aria-label={`${copy.layer2Kicker} ${node.label}`}>
      <header className="layer2-head">
        <span className="layer2-mark" aria-hidden="true"><Puzzle size={16} /></span>
        <div className="layer2-head-title">
          <small>{copy.layer2Kicker}</small>
          <h2>{node.label}</h2>
        </div>
        <p className="layer2-banner">{copy.layer2Hint}</p>
        <Button variant="ghost" onClick={onClose}>{copy.layer2Close}</Button>
        <Button variant="icon" aria-label={copy.close} onClick={onClose}><X size={14} /></Button>
      </header>

      {stage === 'flow' ? <div className="l2-intro">
        <p className="l2-crumb">
          <span>原方案目标：</span>
          {recipeGoal}
          <span className="l2-crumb-arrow">→</span>
          当前要补齐 <b>{node.label}</b>
          <em className="status is-unresolved">待补齐</em>
        </p>
        <div className="l2-intro-row">
          <div>
            <strong>原方案补齐一个子能力</strong>
            <p>外层方案已经保留。这里只制作当前步骤的内部做法，发布后会自动回填到这一张卡片。</p>
          </div>
          <label>子能力名称
            <input value={layer.step_name} onChange={(event) => setLayer((current) => ({ ...current, step_name: event.currentTarget.value }))} />
          </label>
        </div>
        <div className="l2-drafts">
          {draft === 'ready' ? <span className="l2-chip is-ok">✓ 草稿已就绪</span> : null}
          {draft === 'idle' ? <button type="button" className="l2-chip" onClick={() => setDraft('generating')}>生成可运行草稿</button> : null}
          {draft === 'generating' ? <span className="l2-chip is-review">正在为「{node.label}」准备可运行草稿</span> : null}
          {draft === 'failed' ? <button type="button" className="l2-chip is-gap" onClick={() => setDraft('generating')}>草稿创建失败 重试</button> : null}
        </div>
        <p className="l2-intro-note">完成发布后会回到原步骤，方案不会离开当前界面。</p>
        {layer.published || flowId ? <button type="button" className="l2-text-link" onClick={() => setStage('flow')}>查看或替换这一步的内部做法</button> : null}
      </div> : null}

      <nav className="layer2-stages" aria-label="能力制作阶段">
        {L2_STAGES.map((item, index) => (
          <button key={item.id} type="button" className={cx(stage === item.id && 'is-on', (item.id === 'flow' ? columns : item.id === 'result' ? stage === 'prove' || stage === 'publish' : false) && 'is-done')} onClick={() => setStage(item.id)}>
            {item.id === 'flow' && columns ? <Check size={14} /> : stage !== 'flow' ? <em>{index + 1}</em> : null}
            {stage === 'flow' ? `${index + 1}. ${item.label}` : item.label}
          </button>
        ))}
      </nav>

      {columns ? <div className="layer2-columns">
        <ResultColumn
          layer={layer}
          onChange={setLayer}
          onSave={() => void persist()}
          onBindResult={() => {
            const next = layer.internal_steps.includes('展示结果')
              ? layer
              : { ...layer, internal_steps: [...layer.internal_steps.filter((step) => step !== '完成'), '展示结果', '完成'] }
            setLayer(next)
            void persist(next)
          }}
        />
        <ProveColumn
          layer={layer}
          proving={proving}
          note={proveNote}
          infra={infraNote}
          prodLevel={prodLevel}
          onProdLevel={setProdLevel}
          onProve={() => void prove()}
        />
        <PublishColumn
          name={layer.step_name}
          description={goal}
          published={Boolean(layer.published)}
          missing={missing}
          busy={busy || proving}
          error={error}
          layer={layer}
          advanced={publishAdvanced}
          onAdvanced={() => setPublishAdvanced(true)}
          onName={(value) => setLayer((current) => ({ ...current, step_name: value }))}
          onPublish={() => void publish()}
        />
      </div> : <div className="layer2-body">
        <aside className="l2-palette">
          <strong>这一步可以怎么做</strong>
          <div className="l2-kinds">
            {KIND_CHIPS.map((item) => <button type="button" key={item} onClick={() => setLayer((current) => current.internal_steps.includes(item) ? current : { ...current, internal_steps: [...current.internal_steps.filter((step) => step !== '完成'), item, '完成'] })}>{item}</button>)}
          </div>
          <label className="l2-search">
            <Search size={14} />
            <input placeholder="搜索可复用能力" value={search} onChange={(event) => setSearch(event.currentTarget.value)} />
          </label>
          <ul className="l2-reuse">
            {filteredReusable.map((item) => <li key={item.name}>
              <button type="button" onClick={() => setLayer((current) => ({ ...current, internal_steps: [...current.internal_steps.filter((step) => step !== '完成'), item.name, '完成'] }))}>
                <div><b>{item.name}</b><em>{item.version}</em></div>
                <small>{item.scope}</small>
              </button>
            </li>)}
          </ul>
          {!filteredReusable.length ? <p className="l2-palette-empty">没有匹配的已发布能力</p> : null}
          <button type="button" className="l2-text-link" onClick={() => setLayer((current) => ({ ...current, internal_steps: [...current.internal_steps.filter((step) => step !== '完成'), `内部步骤 ${current.internal_steps.length}`, '完成'] }))}>添加内部步骤</button>
        </aside>
        <div className="layer2-canvas">
          <div className="l2-graph">
            {layer.tools.map((toolId) => <button type="button" key={toolId} className={cx('l2-card', 'is-tool', selected === 'tool' && 'is-selected')} onClick={() => setSelected('tool')}>调用本机工具（{toolId}）</button>)}
            <span className="l2-dash" aria-hidden="true" />
            <div className="l2-row">
              <button type="button" className={cx('l2-pill', selected === 'start' && 'is-selected')} onClick={() => setSelected('start')}>开始</button>
              <span className="l2-edge" aria-hidden="true" />
              <button type="button" className={cx('l2-card', 'is-main', selected === 'main' && 'is-selected')} onClick={() => setSelected('main')}>{layer.step_name}</button>
              <span className="l2-edge" aria-hidden="true" />
              <button type="button" className={cx('l2-pill', selected === 'end' && 'is-selected')} onClick={() => setSelected('end')}>完成</button>
            </div>
            <div className="l2-extra">{layer.internal_steps.filter((item) => !['开始', '完成', layer.step_name].includes(item)).map((item) => <button type="button" key={item} className={cx('l2-card', 'is-extra', selected === item && 'is-selected')} onClick={() => setSelected(item)}>{item}</button>)}</div>
          </div>
        </div>
        <aside className="layer2-inspector">
          <div className="l2-insp-tabs">
            {([['approach', '做法'], ['handoff', '交接'], ['params', '给使用者的参数']] as const).map(([id, label]) => (
              <button key={id} type="button" className={inspectorTab === id ? 'is-on' : ''} onClick={() => setInspectorTab(id)}>{label}</button>
            ))}
          </div>
          <div className="l2-insp-body">
            {inspectorTab === 'approach' ? <>
              <label>这一步叫什么
                <input value={selected === 'main' || selected === 'start' || selected === 'end' || selected === 'tool' ? (selected === 'main' ? layer.step_name : selected === 'start' ? '开始' : selected === 'end' ? '完成' : selectedToolLabel) : selected} onChange={(event) => {
                  const value = event.currentTarget.value
                  if (selected === 'main') setLayer((current) => ({ ...current, step_name: value }))
                  else if (selected !== 'start' && selected !== 'end' && selected !== 'tool') {
                    setLayer((current) => ({ ...current, internal_steps: current.internal_steps.map((step) => step === selected ? value : step) }))
                    setSelected(value)
                  }
                }} />
              </label>
              <p className="hint">这里只改这一步给人看的做法。运行细节留在高级里。</p>
              <strong>用到的本机工具</strong>
              {layer.tools.map((toolId) => <label className="l2-check" key={toolId}>
                <input type="checkbox" checked onChange={() => setLayer((current) => ({ ...current, tools: current.tools.filter((id) => id !== toolId) }))} />
                {toolId}
              </label>)}
              {layer.tools.length ? null : <button type="button" className="l2-text-link" onClick={() => onOpenResources?.()}>还没有可用的本机工具。到第一层的资源池里添加。</button>}
              <strong>使用者参数</strong>
              {layer.params.map((param) => <div className="l2-param" key={param.id}>{param.label} <em>{param.value_type === 'string_list' ? '文本列表' : '文本'}</em> {param.required ? <b>必填</b> : null}</div>)}
              <button type="button" className="l2-advanced" onClick={() => setAdvanced((open) => !open)}>高级 <span>›</span></button>
              {advanced ? <dl>
                <div><dt>公开输入</dt><dd>{layer.handoff_in}</dd></div>
                <div><dt>输出</dt><dd>{layer.handoff_out}</dd></div>
                <div><dt>可编辑</dt><dd>{layer.params.map((item) => item.label).join('、')}</dd></div>
              </dl> : null}
            </> : inspectorTab === 'handoff' ? <>
              <p className="hint">从开始进入，完成后把可追溯材料交给下一步。</p>
              <label>输入<textarea rows={3} value={layer.handoff_in} onChange={(event) => setLayer((current) => ({ ...current, handoff_in: event.currentTarget.value }))} /></label>
              <label>输出<textarea rows={3} value={layer.handoff_out} onChange={(event) => setLayer((current) => ({ ...current, handoff_out: event.currentTarget.value }))} /></label>
            </> : <>
              {layer.params.map((param) => (
                <label key={param.id}>{param.label}
                  <input value={Array.isArray(param.default) ? param.default.join('\n') : String(param.default || '')} placeholder={param.value_type === 'string_list' ? '文本列表' : ''} onChange={(event) => setLayer((current) => ({
                    ...current,
                    params: current.params.map((item) => item.id === param.id ? { ...item, default: param.value_type === 'string_list' ? event.currentTarget.value.split(/\n+/).filter(Boolean) : event.currentTarget.value } : item),
                  }))} />
                </label>
              ))}
              <p className="hint">这些参数会在第一层卡片上暴露给使用者。</p>
            </>}
          </div>
          <div className="l2-insp-actions">
            <Button variant="ghost" disabled={busy} onClick={() => void saveNode()}>保存节点</Button>
            <button type="button" className="l2-delete" onClick={() => {
              if (selected === 'start' || selected === 'end' || selected === 'main') return
              if (!window.confirm(`删除「${selected}」？`)) return
              setLayer((current) => ({ ...current, internal_steps: current.internal_steps.filter((item) => item !== selected) }))
              setSelected('main')
            }}>删除</button>
          </div>
        </aside>
      </div>}

      <footer className="layer2-foot">
        {columns ? <>
          <span className={hasPath ? 'l2-foot-ok' : 'l2-foot-wait'}>{hasPath ? '结构完整' : '结构不完整'}</span>
          <span className={proof.success && proof.safe_fail ? 'l2-foot-ok' : 'l2-foot-wait'}>{proof.success && proof.safe_fail ? '验证成功与失败均通过' : '验证尚未完成'}</span>
        </> : <>
          <span>当前进度：搭建内部做法</span>
          <span className={hasPath ? 'l2-foot-ok' : 'l2-foot-wait'}>{hasPath ? '结构完整' : '结构不完整'}</span>
          <span className="l2-foot-wait">验证尚未完成</span>
          <p className="l2-foot-hint">缺成功路径时下一步禁用：{hasPath ? '路径已齐' : '还缺结果节点 / 还缺从开始到完成的路径'}</p>
          <Button disabled={!hasPath} onClick={() => setStage('result')}>下一步：{nextLabel}</Button>
        </>}
        {error ? <p className="alert">{error}</p> : null}
      </footer>
    </div>
  </div>
}

function ResultColumn({ layer, onChange, onSave, onBindResult }: { layer: StudioLayer2; onChange: (layer: StudioLayer2) => void; onSave: () => void; onBindResult: () => void }) {
  const addField = () => {
    if (layer.fields.length >= 12) return
    onChange({
      ...layer,
      fields: [...layer.fields, { id: `field_${layer.fields.length + 1}`, label: `字段${layer.fields.length + 1}`, kind: '文本', source: `结果.custom_${layer.fields.length + 1}` }],
    })
  }
  return <section className="layer2-col is-result">
    <h3>结果长什么样</h3>
    <strong className="l2-kicker">展示组件</strong>
    <p className="hint">试运行时人在 Runner 里看见的就是这里</p>
    <div className="l2-panel-pick">
      <button type="button" className="is-on">{layer.panel_name || '结果面板'} <em>v1</em></button>
      <button type="button" onClick={() => onChange({ ...layer, panel_name: '自定义结果面板' })}>新建</button>
    </div>
    {layer.panel_name === '自定义结果面板' ? null : <p className="hint">当前还没有自定义展示组件</p>}
    <label>名称<input value={layer.panel_name} onChange={(event) => onChange({ ...layer, panel_name: event.currentTarget.value })} /></label>
    <label>交付说明<textarea rows={2} value={layer.deliver} onChange={(event) => onChange({ ...layer, deliver: event.currentTarget.value })} /></label>
    <p className="l2-kicker">模板</p>
    <div className="l2-seg">{['摘要', '列表', '数据面板'].map((item) => <button type="button" key={item} className={layer.template === item ? 'is-on' : ''} onClick={() => onChange({ ...layer, template: item })}>{item}</button>)}</div>
    <div className="l2-fields-head"><span>字段</span><small>{layer.fields.length} / 12</small></div>
    <ul className="l2-fields">
      {layer.fields.map((field) => <li key={field.id}>
        <b>{field.label}</b><em>{field.kind}</em><span>← {field.source}</span>
        <button type="button" className="l2-text-link" onClick={() => onChange({ ...layer, fields: layer.fields.filter((item) => item.id !== field.id) })}>删除</button>
      </li>)}
    </ul>
    <button type="button" className="l2-add-field" onClick={addField}>+ 添加字段</button>
    <div className="l2-seg is-underline">{['正常', '长内容', '空态'].map((item) => <button type="button" key={item} className={layer.preview === item ? 'is-on' : ''} onClick={() => onChange({ ...layer, preview: item })}>{item}</button>)}</div>
    <ResultPreview fields={layer.fields} preview={layer.preview} template={layer.template} />
    <div className="l2-bind-row">
      <Button variant="ghost" onClick={onBindResult}>{layer.internal_steps.includes('展示结果') ? '绑定展示结果节点' : '否则添加展示结果节点'}</Button>
    </div>
    <Button variant="ghost" onClick={onSave}>保存并绑定组件</Button>
    <p className="hint">没有展示也可以往后，使用者将只看到默认文本</p>
  </section>
}

function ResultPreview({ fields, preview, template }: { fields: StudioLayer2Field[]; preview: string; template: string }) {
  if (!fields.length || preview === '空态') return <div className="runtime-result-widgets"><p className="hint">还没有交付内容</p></div>
  const long = preview === '长内容'
  return <div className={cx('runtime-result-widgets', template === '数据面板' && 'is-grid')}>
    {fields.map((field) => {
      if (field.kind === '是/否') return <label key={field.id} className="runtime-check"><input type="checkbox" defaultChecked /> {field.label}</label>
      if (field.kind === '链接') return <p key={field.id} className="runtime-result-field"><span>{field.label}</span><small>待提供链接</small></p>
      if (field.source.includes('date') || field.label === '日期') return <p key={field.id} className="runtime-result-field"><span>{field.label}</span><small>{new Date().toISOString().slice(0, 10)}</small></p>
      return <div key={field.id} className="runtime-result-field">
        <span>{field.label}{template === '列表' ? ' · 列表' : template === '数据面板' ? ' · 面板' : ''}</span>
        {template === '摘要' && !long ? <small>示例内容一；示例内容二</small> : <ul>{['示例内容一', '示例内容二', ...(long ? ['示例内容三', '示例内容四'] : [])].map((item) => <li key={item}>{item}</li>)}</ul>}
      </div>
    })}
  </div>
}

function ProveColumn({ layer, proving, note, infra, prodLevel, onProdLevel, onProve }: { layer: StudioLayer2; proving: boolean; note: string; infra: string; prodLevel: boolean; onProdLevel: (on: boolean) => void; onProve: () => void }) {
  const proof = layer.proof || {}
  const samples = layer.params.flatMap((param) => {
    const value = sampleValue(param)
    return value === undefined ? [] : [`${param.label || param.id} = ${displaySample(value)}`]
  })
  const missingSamples = layer.params.filter((param) => param.required && !hasSampleValue(param.default))
  const ready = Boolean(proof.success && proof.safe_fail)
  return <section className="layer2-col is-prove">
    <div className="l2-prove-head">
      <div>
        <h3>用真样本证明</h3>
        <p className="hint">需要一次成功，一次安全失败</p>
      </div>
      <div className="l2-level">
        <span className={!prodLevel ? 'is-on' : ''}>开发级</span>
        <button type="button" className={prodLevel ? 'is-on' : ''} disabled={!ready} onClick={() => onProdLevel(true)}>进入生产验收</button>
      </div>
    </div>
    <div className="l2-check-row">
      <span>✓ 准备真实样本 {layer.params.map((item) => item.label).join(' · ') || '无需公开参数'}</span>
      <em>{missingSamples.length ? '未完成' : '已完成'}</em>
    </div>
    {proof.success ? <article className="l2-run is-ok">
      <div className="l2-run-top"><span>{samples.join(' · ') || '无需公开参数'}</span><span className="l2-tag is-ok">运行成功路径</span></div>
      <p className="l2-run-result">✓ 成功 已拿到可展示结果</p>
    </article> : <article className="l2-run"><p className="hint">还没有成功路径。点「跑一次」会用声明的输入真跑。</p></article>}
    {proof.safe_fail ? <article className="l2-run is-fail">
      <div className="l2-run-top"><span>主动省略输入内容</span><span className="l2-tag is-fail">运行安全失败</span></div>
      <p className="l2-run-result is-fail">缺少必填 已停住 · 未生成不完整结果</p>
    </article> : null}
    <p className="hint">两次都成功不算过</p>
    {proof.success && proof.safe_fail ? <article className="l2-run is-ok">
      <p><b>已登记</b> 当前源码已有证明</p>
      <p className="hint">指纹：<code>{proof.fingerprint}</code></p>
    </article> : null}
    <p className="l2-note">源码变化时证明已失效，必须重跑两次</p>
    <p className="hint">{proving ? '运行中不能再点' : '需要一次成功，一次安全失败'}</p>
    {note ? <p className="hint">{note}</p> : null}
    {infra ? <article className="l2-run is-fail">
      <p className="l2-run-result is-fail">不算安全失败 / 成功路径自己挂了</p>
      <p className="hint">{infra}</p>
      <p className="hint">请检查真实样本或运行环境 · 这不是安全失败</p>
    </article> : null}
    <button type="button" className="l2-run-again" disabled={proving} onClick={onProve}>跑一次</button>
  </section>
}

function PublishColumn({
  name, description, published, missing, busy, error, layer, advanced, onAdvanced, onName, onPublish,
}: {
  name: string
  description: string
  published: boolean
  missing: string[]
  busy: boolean
  error: string
  layer: StudioLayer2
  advanced: boolean
  onAdvanced: () => void
  onName: (value: string) => void
  onPublish: () => void
}) {
  return <section className="layer2-col is-publish">
    <h3>发布回第一层</h3>
    <label>显示名称<input value={name} onChange={(event) => onName(event.currentTarget.value)} /></label>
    <label>说明<textarea rows={3} value={description} readOnly /></label>
    <button type="button" className="l2-text-link" onClick={onAdvanced}>匹配词 → 进高级</button>
    {advanced ? <dl>
      <div><dt>公开输入</dt><dd>{layer.handoff_in || '未声明'}</dd></div>
      <div><dt>输出</dt><dd>{layer.handoff_out || '未声明'}</dd></div>
      <div><dt>可编辑</dt><dd>{layer.params.map((item) => item.label).join('、') || '无'}</dd></div>
      <div><dt>依赖</dt><dd>{layer.internal_steps.filter((item) => item !== '开始' && item !== '完成').join('、') || '无'}</dd></div>
    </dl> : null}
    {missing.length && !published ? <div className="l2-gaps">
      <strong>还差</strong>
      {missing.map((item) => <p key={item}>{item}</p>)}
    </div> : null}
    <Button disabled={busy || missing.length > 0 || published} onClick={onPublish}>发布并回到原步骤</Button>
    <p className="hint">第一层那张卡会变成已有做法，方案不离开当前界面</p>
    {published ? <div className="l2-published">
      <p><b>已发布</b> {name}</p>
      <p>原步骤会再检查 → 回到原步骤</p>
      {layer.internal_steps.filter((item) => !['开始', '完成', layer.step_name].includes(item)).slice(0, 4).map((item) => <p key={item}>{item} 启用</p>)}
    </div> : null}
    {error ? <p className="alert">{error}</p> : null}
  </section>
}
