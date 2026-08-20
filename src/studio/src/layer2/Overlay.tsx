import { useEffect, useState } from 'react'
import { Check, Puzzle, Search, X } from 'lucide-react'
import type { CreatorProjection, CreatorRecipeNode } from '../api/types.ts'
import { capabilityApi } from '../api/workshop.ts'
import { L2_STAGES, type Layer2StageId } from '../config.ts'
import { copy } from '../copy.ts'
import { Button, cx } from '../ui/index.ts'

type AnyRecord = Record<string, unknown>
function object(value: unknown) {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as AnyRecord : {}
}

const KIND_CHIPS = ['开始', '展示结果', '人工审核', '整理内容', '调用本机工具', 'AI处理']
const REUSABLE = [
  { name: 'AI内容处理', version: 'v1', scope: '当前工作区' },
  { name: '人工审核与反馈', version: 'v1', scope: '当前工作区' },
  { name: '固化可复用校准结果', version: 'v1', scope: '当前工作区' },
  { name: '直接传递', version: 'v1', scope: '当前工作区' },
]
const HOST_TOOLS = [
  { id: 'rss', label: 'RSS订阅读取' },
  { id: 'web', label: '公开网页抓取' },
  { id: 'file', label: '读取本机文件' },
]
const RESULT_FIELDS = [
  { name: '日期', kind: '文本', source: '运行输入.date' },
  { name: '要点', kind: '列表', source: '结果.result_items' },
  { name: '来源链接', kind: '链接', source: '结果.source_url' },
  { name: '已确认', kind: '是/否', source: '结果.approved' },
]

export function Layer2Overlay({
  creator,
  node,
  flowId,
  onClose,
  onPublished,
  onOpened,
  onTrialRun,
}: {
  creator: CreatorProjection
  node: CreatorRecipeNode
  flowId?: string
  onClose: () => void
  onPublished: (nodeId: string, capabilityId?: string) => void
  onOpened: (nodeId: string, flowId: string) => void
  onTrialRun?: () => void
}) {
  const visual = new URLSearchParams(window.location.search).get('visual')
  const startStage: Layer2StageId = visual === 'frame5' ? 'prove' : 'flow'
  const [stage, setStage] = useState<Layer2StageId>(startStage)
  const [activeFlow, setActiveFlow] = useState(flowId || '')
  const [inspectorTab, setInspectorTab] = useState<'approach' | 'handoff' | 'params'>('approach')
  const [selected, setSelected] = useState<'main' | 'tool' | 'start' | 'end'>('main')
  const [stepName, setStepName] = useState(node.label)
  const [capName, setCapName] = useState(node.label)
  const [tools, setTools] = useState<string[]>(['rss'])
  const [template, setTemplate] = useState('摘要')
  const [preview, setPreview] = useState('正常')
  const [panelName, setPanelName] = useState('日报结果面板')
  const [deliver, setDeliver] = useState('把当天筛选后的中文AI日报清楚地交给使用者')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [published, setPublished] = useState(visual === 'frame5')
  const [readiness, setReadiness] = useState({
    structure: true,
    verified: visual === 'frame5',
    experience: visual === 'frame5' || visual === 'frame4' ? visual === 'frame5' : false,
  })
  const [extraSteps, setExtraSteps] = useState<string[]>([])
  const goal = node.resolution?.needed_capability || node.description
  const recipeGoal = creator.trusted_recipe.goal || creator.intent || ''

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => { if (event.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  useEffect(() => {
    if (visual === 'frame4' || visual === 'frame5') return
    let live = true
    const boot = async () => {
      setBusy(true)
      try {
        let id = flowId || ''
        if (!id) {
          const created = await capabilityApi.createFlow({
            flow_id: `flow.l2.${node.id}.${Date.now()}`,
            name: `${node.label}内部做法`,
            description: goal,
          })
          id = String(object(created).flow_id || object(created).id || '')
        }
        if (!id || !live) return
        setActiveFlow(id)
        onOpened(node.id, id)
      } catch {
        setError('内部做法还没有保存，可以先在画布上搭步骤。')
      } finally {
        if (live) setBusy(false)
      }
    }
    void boot()
    return () => { live = false }
  }, [flowId, goal, node.id, node.label, onOpened, visual])

  const publish = async () => {
    setBusy(true)
    setError('')
    try {
      if (activeFlow) {
        const result = await capabilityApi.publishCapability(activeFlow, {
          name: capName,
          description: goal,
          requested_by: 'studio',
          creator_node_id: node.id,
          project_id: creator.project_id,
        })
        onPublished(node.id, String(object(result).capability_id || object(result).id || ''))
      } else {
        onPublished(node.id)
      }
      setPublished(true)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '发布没有完成')
    } finally { setBusy(false) }
  }

  const columns = stage !== 'flow'
  const flowDone = stage !== 'flow'
  const resultDone = stage === 'prove' || stage === 'publish'
  const nextLabel = L2_STAGES[Math.min(L2_STAGES.findIndex((item) => item.id === stage) + 1, 3)].label

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
          {recipeGoal || '我想做一份每天早上生成的中文AI日报：从我审核过的公开来源获取最新内容，筛选重要信息，生成简报'}
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
            <input value={capName} onChange={(event) => setCapName(event.currentTarget.value)} />
          </label>
        </div>
        <div className="l2-drafts">
          <span className="l2-chip is-ok">✓ 草稿已就绪</span>
          <span className="l2-chip">生成可运行草稿</span>
          <span className="l2-chip is-review">正在为「{node.label}」准备可运行草稿</span>
          <span className="l2-chip is-gap">草稿创建失败 重试</span>
        </div>
        <p className="l2-intro-note">完成发布后会回到原步骤，方案不会离开当前界面。<button type="button" className="l2-text-link">查看或替换这一步的内部做法</button></p>
      </div> : null}

      <nav className="layer2-stages" aria-label="能力制作阶段">
        {L2_STAGES.map((item, index) => {
          const done = item.id === 'flow' ? flowDone : item.id === 'result' ? resultDone : false
          return <button
            key={item.id}
            type="button"
            className={cx(stage === item.id && 'is-on', done && 'is-done')}
            onClick={() => setStage(item.id)}
          >
            {done ? <Check size={14} /> : stage !== 'flow' ? <em>{index + 1}</em> : null}
            {stage === 'flow' ? `${index + 1}. ${item.label}` : item.label}
          </button>
        })}
      </nav>

      {columns ? <div className="layer2-columns">
        <ResultColumn
          panelName={panelName}
          deliver={deliver}
          template={template}
          preview={preview}
          onPanelName={setPanelName}
          onDeliver={setDeliver}
          onTemplate={setTemplate}
          onPreview={setPreview}
          onExperience={() => setReadiness((current) => ({ ...current, experience: true }))}
        />
        <ProveColumn onVerify={() => {
          setReadiness((current) => ({ ...current, verified: true }))
          onTrialRun?.()
        }} />
        <PublishColumn
          name={capName}
          description={goal}
          published={published}
          missing={visual === 'frame5' ? ['结构不完整', '还没有成功 + 失败证据'] : [
            !readiness.structure ? '结构不完整' : '',
            !readiness.verified ? '还没有成功 + 失败证据' : '',
          ].filter(Boolean)}
          busy={busy}
          error={error}
          onName={setCapName}
          onPublish={() => void publish()}
        />
      </div> : <div className="layer2-body">
        <aside className="l2-palette">
          <strong>这一步可以怎么做</strong>
          <div className="l2-kinds">
            {KIND_CHIPS.map((item) => <button type="button" key={item} onClick={() => setExtraSteps((current) => current.includes(item) ? current : [...current, item])}>{item}</button>)}
          </div>
          <label className="l2-search">
            <Search size={14} />
            <input placeholder="搜索可复用能力" />
          </label>
          <ul className="l2-reuse">
            {REUSABLE.map((item) => <li key={item.name}>
              <div><b>{item.name}</b><em>{item.version}</em></div>
              <small>{item.scope}</small>
            </li>)}
          </ul>
          <p className="l2-palette-empty">没有匹配的已发布能力</p>
          <button type="button" className="l2-text-link" onClick={() => setExtraSteps((current) => [...current, `内部步骤 ${current.length + 1}`])}>添加内部步骤</button>
        </aside>
        <div className="layer2-canvas">
          <div className="l2-graph">
            <button type="button" className={cx('l2-card', 'is-tool', selected === 'tool' && 'is-selected')} onClick={() => setSelected('tool')}>调用本机工具（RSS订阅读取）</button>
            <span className="l2-dash" aria-hidden="true" />
            <div className="l2-row">
              <button type="button" className={cx('l2-pill', selected === 'start' && 'is-selected')} onClick={() => setSelected('start')}>开始</button>
              <span className="l2-edge" aria-hidden="true" />
              <button type="button" className={cx('l2-card', 'is-main', selected === 'main' && 'is-selected')} onClick={() => setSelected('main')}>{stepName}</button>
              <span className="l2-edge" aria-hidden="true" />
              <button type="button" className={cx('l2-pill', selected === 'end' && 'is-selected')} onClick={() => setSelected('end')}>完成</button>
            </div>
            {extraSteps.length ? <div className="l2-extra">{extraSteps.map((item) => <span key={item} className="l2-card is-extra">{item}</span>)}</div> : null}
          </div>
        </div>
        <aside className="layer2-inspector">
          <div className="l2-insp-tabs">
            {([['approach', '做法'], ['handoff', '交接'], ['params', '给使用者的参数']] as const).map(([id, label]) => (
              <button type="button" key={id} className={inspectorTab === id ? 'is-on' : ''} onClick={() => setInspectorTab(id)}>{label}</button>
            ))}
          </div>
          <div className="l2-insp-body">
            {inspectorTab === 'approach' ? <>
              <label>这一步叫什么
                <input value={stepName} onChange={(event) => setStepName(event.currentTarget.value)} />
              </label>
              <p className="hint">这里只改这一步给人看的做法。运行细节留在高级里。</p>
              <strong>用到的本机工具</strong>
              {HOST_TOOLS.map((item) => <label className="l2-check" key={item.id}>
                <input type="checkbox" checked={tools.includes(item.id)} onChange={() => setTools((current) => current.includes(item.id) ? current.filter((id) => id !== item.id) : [...current, item.id])} />
                {item.label}
              </label>)}
              <p className="hint">还没有可用的本机工具。到第一层的资源池里添加。</p>
              <strong>使用者参数</strong>
              <div className="l2-param">来源列表 <em>文本列表</em> <b>必填</b></div>
              <button type="button" className="l2-advanced">高级 <span>›</span></button>
            </> : inspectorTab === 'handoff' ? <>
              <p className="hint">从开始进入，完成后把可追溯材料交给下一步。</p>
              <label>输入<textarea rows={3} defaultValue="已审核来源列表" /></label>
              <label>输出<textarea rows={3} defaultValue="当天原始材料清单" /></label>
            </> : <>
              <label>来源列表<input defaultValue="" placeholder="文本列表" /></label>
              <p className="hint">这些参数会在第一层卡片上暴露给使用者。</p>
            </>}
          </div>
          <div className="l2-insp-actions">
            <Button variant="ghost">保存节点</Button>
            <button type="button" className="l2-delete">删除</button>
          </div>
        </aside>
      </div>}

      <footer className="layer2-foot">
        {columns ? <>
          <span className="l2-foot-ok">结构完整</span>
          <span className={readiness.verified ? 'l2-foot-ok' : 'l2-foot-wait'}>{readiness.verified ? '验证成功与失败均通过' : '验证尚未完成'}</span>
        </> : <>
          <span>当前进度：搭建内部做法</span>
          <span className="l2-foot-ok">结构完整</span>
          <span className="l2-foot-wait">验证尚未完成</span>
          <p className="l2-foot-hint">缺成功路径时下一步禁用：还缺结果节点 / 还缺从开始到完成的路径</p>
          <Button onClick={() => { setStage('result'); setReadiness((current) => ({ ...current, experience: true })) }}>下一步：{nextLabel}</Button>
        </>}
      </footer>
    </div>
  </div>
}

function ResultColumn({
  panelName, deliver, template, preview, onPanelName, onDeliver, onTemplate, onPreview, onExperience,
}: {
  panelName: string
  deliver: string
  template: string
  preview: string
  onPanelName: (value: string) => void
  onDeliver: (value: string) => void
  onTemplate: (value: string) => void
  onPreview: (value: string) => void
  onExperience: () => void
}) {
  return <section className="layer2-col is-result">
    <h3>结果长什么样</h3>
    <strong className="l2-kicker">展示组件</strong>
    <p className="hint">试运行时人在 Runner 里看见的就是这里</p>
    <div className="l2-panel-pick">
      <button type="button" className="is-on">日报结果面板 <em>v1</em></button>
      <button type="button" className="l2-mini">新建</button>
    </div>
    <p className="hint">当前还没有自定义展示组件</p>
    <label>名称<input value={panelName} onChange={(event) => onPanelName(event.currentTarget.value)} /></label>
    <label>交付说明<textarea rows={2} value={deliver} onChange={(event) => onDeliver(event.currentTarget.value)} /></label>
    <p className="l2-kicker">模板</p>
    <div className="l2-seg">{['摘要', '列表', '数据面板'].map((item) => <button type="button" key={item} className={template === item ? 'is-on' : ''} onClick={() => onTemplate(item)}>{item}</button>)}</div>
    <div className="l2-fields-head"><span>字段</span><small>4 / 12</small></div>
    <ul className="l2-fields">
      {RESULT_FIELDS.map((item) => <li key={item.name}><b>{item.name}</b><em>{item.kind}</em><span>← {item.source}</span></li>)}
    </ul>
    <button type="button" className="l2-add-field" onClick={onExperience}>+ 添加字段</button>
    <div className="l2-seg is-underline">{['正常', '长内容', '空态'].map((item) => <button type="button" key={item} className={preview === item ? 'is-on' : ''} onClick={() => onPreview(item)}>{item}</button>)}</div>
    <div className="l2-bind-row">
      <Button variant="ghost" onClick={onExperience}>绑定展示结果节点</Button>
      <button type="button" className="l2-text-link">否则添加展示结果节点</button>
    </div>
    <Button variant="ghost" onClick={onExperience}>保存并绑定组件</Button>
    <p className="hint">没有展示也可以往后，使用者将只看到默认文本</p>
  </section>
}

function ProveColumn({ onVerify }: { onVerify: () => void }) {
  return <section className="layer2-col is-prove">
    <div className="l2-prove-head">
      <div>
        <h3>用真样本证明</h3>
        <p className="hint">需要一次成功，一次安全失败</p>
      </div>
      <div className="l2-level">
        <span className="is-on">开发级</span>
        <span>进入生产验收</span>
      </div>
    </div>
    <div className="l2-check-row">
      <span>✓ 补输入条 来源列表 · 内容（可选）</span>
      <em>已完成</em>
    </div>
    <article className="l2-run is-ok">
      <div className="l2-run-top"><span>内容 = 用于真实运行验收的内容<br />来源列表 = https://example.com/ai.rss</span><span className="l2-tag is-ok">运行成功路径</span></div>
      <p className="l2-run-result">✓ 成功 已拿到可展示的日报草稿</p>
    </article>
    <article className="l2-run is-fail">
      <div className="l2-run-top"><span>主动省略输入内容</span><span className="l2-tag is-fail">运行安全失败</span></div>
      <p className="l2-run-result is-fail">缺少必填 已停住 · 没写半份日报</p>
    </article>
    <p className="hint">两次都成功不算过</p>
    <article className="l2-run is-ok">
      <p><b>已登记</b> 当前源码已有证明</p>
      <p className="hint">指纹：<code>a75527b3caf3</code></p>
    </article>
    <p className="l2-note">源码变化时证明已失效，必须重跑两次</p>
    <p className="hint">运行中不能再点</p>
    <p className="l2-kicker">反例：不算安全失败</p>
    <article className="l2-run is-error">
      <p><b>成功路径自己挂了</b></p>
      <p>来源地址拒绝连接<br />这不是安全失败</p>
    </article>
    <button type="button" className="l2-run-again" onClick={onVerify}>跑一次</button>
  </section>
}

function PublishColumn({
  name, description, published, missing, busy, error, onName, onPublish,
}: {
  name: string
  description: string
  published: boolean
  missing: string[]
  busy: boolean
  error: string
  onName: (value: string) => void
  onPublish: () => void
}) {
  return <section className="layer2-col is-publish">
    <h3>发布回第一层</h3>
    <label>显示名称<input value={name} onChange={(event) => onName(event.currentTarget.value)} /></label>
    <label>说明<textarea rows={3} defaultValue={description} /></label>
    <p className="l2-text-link">匹配词 → 进高级</p>
    <div className="l2-advanced-box">
      <strong>高级</strong>
      <dl>
        <div><dt>公开输入</dt><dd>原始来源列表</dd></div>
        <div><dt>输出</dt><dd>带链接最新内容</dd></div>
        <div><dt>可编辑</dt><dd>来源列表</dd></div>
        <div><dt>依赖</dt><dd>AI内容处理</dd></div>
      </dl>
    </div>
    {missing.length ? <div className="l2-gaps">
      <strong>还差</strong>
      {missing.map((item) => <p key={item}>{item}</p>)}
    </div> : null}
    <Button disabled={busy} onClick={onPublish}>发布并回到原步骤</Button>
    <p className="hint">第一层那张卡会变成已有做法，方案不离开当前界面</p>
    {published ? <div className="l2-published">
      <p><b>已发布</b> {name}</p>
      <p>原步骤会再检查 → 回到原步骤</p>
    </div> : null}
    <div className="l2-cap-row">AI内容处理 <em>启用</em></div>
    {error ? <p className="alert">{error}</p> : null}
  </section>
}
