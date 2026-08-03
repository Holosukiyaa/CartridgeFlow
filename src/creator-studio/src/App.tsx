import { useMemo, useState } from 'react'
import { Bot, Check, ChevronRight, CircleAlert, FileText, Link2, Lock, Minus, MousePointer2, Paperclip, PenLine, Plus, Redo2, Send, ShieldCheck, Sparkles, Undo2, X } from 'lucide-react'

type StepState = 'exploring' | 'needs-confirmation' | 'confirmed' | 'frozen' | 'blocked'
type Step = { id: number; title: string; description: string; state: StepState; inputs: string; output: string }
type Proposal = { id: number; label: string; detail: string; selected: boolean }

const initialSteps: Step[] = [
  { id: 1, title: '收集指定来源', description: '读取你确认的三个来源', state: 'frozen', inputs: '来源', output: '原始消息' },
  { id: 2, title: '整理重复与营销内容', description: '排除重复和宣传内容', state: 'frozen', inputs: '原始消息', output: '整理后消息' },
  { id: 3, title: '识别供应链变化', description: '找出值得关注的变化', state: 'needs-confirmation', inputs: '整理后消息', output: '变化候选' },
  { id: 4, title: '核查关键数字', description: '监督公告网站还缺少地址', state: 'blocked', inputs: '变化候选', output: '核查结果' },
  { id: 5, title: '整理一页中文简报', description: '形成便于快速阅读的简报', state: 'exploring', inputs: '核查结果', output: '中文简报' },
]

const stateMeta: Record<StepState, { label: string; className: string }> = {
  exploring: { label: '构思中', className: 'state-exploring' },
  'needs-confirmation': { label: '待确认', className: 'state-confirm' },
  confirmed: { label: '已确认', className: 'state-confirmed' },
  frozen: { label: '已固化', className: 'state-frozen' },
  blocked: { label: '需处理', className: 'state-blocked' },
}

function Status({ state }: { state: StepState }) { const meta = stateMeta[state]; return <span className={`status ${meta.className}`}>{state === 'frozen' && <Lock size={13} />}{meta.label}</span> }

function SourceCard({ title, detail, missing, onResolve }: { title: string; detail: string; missing?: boolean; onResolve?: () => void }) {
  return <div className={`source ${missing ? 'source-missing' : ''}`}><ShieldCheck size={20} /><span><b>{title}</b><small>{detail}</small></span>{missing ? <button className="small-button" onClick={onResolve}>补充</button> : <i />}</div>
}

export default function App() {
  const [intent, setIntent] = useState('每天从半导体公司官网、行业媒体和监管公告中，找出真正影响供应链的变化，去掉营销内容，整理成一页中文简报。')
  const [sourceReady, setSourceReady] = useState(false)
  const [steps, setSteps] = useState(initialSteps)
  const [mode, setMode] = useState<'input' | 'review' | 'canvas'>('input')
  const [proposals, setProposals] = useState<Proposal[]>([
    { id: 6, label: '新增：提取公告关键数字', detail: '让关键数字能进入核查', selected: true },
    { id: 7, label: '新增：交叉核对变化与数字', detail: '找出不一致或异常的变化', selected: true },
    { id: 8, label: '调整：简报使用交叉核对结果', detail: '提高简报的准确性', selected: false },
  ])
  const [history, setHistory] = useState<string[]>([])
  const [notice, setNotice] = useState('')
  const [editingStep, setEditingStep] = useState<number | null>(null)
  const [editTitle, setEditTitle] = useState('')
  const [designValidated, setDesignValidated] = useState(false)

  const accepted = proposals.filter((proposal) => proposal.selected)
  const summary = useMemo(() => `${steps.filter((step) => step.state === 'frozen').length} 个已固化 · ${steps.filter((step) => step.state === 'needs-confirmation').length} 个待确认 · ${steps.filter((step) => step.state === 'blocked').length} 个需处理`, [steps])
  const update = (label: string, action: () => void) => { action(); setHistory((items) => [...items, label]) }
  const generateDraft = () => { setMode('review'); setNotice('AI 已整理出 3 项可审阅的设计改动。') }
  const acceptSelected = () => update('接受 AI 改动', () => { setSteps((current) => [...current, ...accepted.filter((p) => p.id !== 8).map((p) => ({ id: p.id, title: p.label.replace('新增：', ''), description: p.detail, state: 'exploring' as StepState, inputs: '整理后消息', output: p.id === 6 ? '数字列表' : '核查结果' }))]); setMode('canvas'); setNotice(`已接受 ${accepted.length} 项改动。`) })
  const freezeStep = (id: number) => update('固化步骤', () => setSteps((current) => current.map((step) => step.id === id ? { ...step, state: 'frozen' } : step)))
  const beginEdit = (step: Step) => { setEditingStep(step.id); setEditTitle(step.title) }
  const saveEdit = (id: number) => update('直接编辑画布', () => { setSteps((current) => current.map((step) => step.id === id ? { ...step, title: editTitle.trim() || step.title, state: step.state === 'frozen' ? 'confirmed' : step.state } : step)); setEditingStep(null); setNotice('画布编辑已作为一项修订保存。') })
  const resolveBlock = () => update('补全监管公告来源', () => { setSourceReady(true); setDesignValidated(false); setSteps((current) => current.map((step) => step.id === 4 ? { ...step, state: 'confirmed', description: '将数字与公告内容交叉核查' } : step)); setNotice('阻塞项已解决，设计可继续验证。') })
  const undo = () => { if (!history.length) return; setHistory((items) => items.slice(0, -1)); setNotice('已撤销上一项编辑。') }
  const validateDesign = () => { if (!sourceReady) { setNotice('先补全阻塞的来源，再进行设计检查。'); return } setDesignValidated(true); setNotice('设计检查通过：步骤、来源和影响说明已就绪。') }
  const canGenerate = designValidated && steps.every((step) => step.state !== 'blocked') && steps.some((step) => step.state === 'frozen')

  return <div className="studio">
    <header className="topbar"><div className="brand"><span className="brand-mark">C</span><b>创作工作室</b><span className="badge">设计中</span></div><div className="toolbar"><button aria-label="撤销" title="撤销" onClick={undo}><Undo2 /></button><button aria-label="重做" title="重做"><Redo2 /></button><button aria-label="选择" title="选择"><MousePointer2 /></button><button aria-label="添加步骤" title="添加步骤"><Plus /></button></div><div className="top-actions"><button onClick={validateDesign}><FileText size={18} /> 设计检查</button><button><PenLine size={18} /> 保存</button><button className="primary" disabled={!canGenerate} onClick={() => setNotice('设计验证通过，已生成 cartridge。')}><Sparkles size={18} /> 生成 cartridge</button></div></header>
    <div className="progress"><CircleAlert size={17} /><span>5 个步骤</span><span className="dot frozen" /> 2 个已固化 <span className="dot confirm" /> 1 个待确认 <span className="dot blocked" /> {sourceReady ? '0 个需处理' : '1 个需处理'} <span className="dot exploring" /> 1 个构思中</div>
    <main className="workspace">
      <aside className="rail"><button><MousePointer2 />选择</button><button><Link2 />连接</button><button><span className="layers">▱</span>步骤</button><button><ShieldCheck />来源</button><button><Bot />AI 操作</button></aside>
      <section className="canvas" aria-label="语义画布">
        <div className="collaborator"><div className="panel-heading">共同创作 <button aria-label="关闭"><X size={18} /></button></div><textarea aria-label="创作意图" value={intent} onChange={(event) => setIntent(event.target.value)} /><h3>我的来源</h3><SourceCard title="半导体公司官网" detail="已连接" /><SourceCard title="行业媒体 RSS" detail="已连接" /><SourceCard title="监管公告网站" detail={sourceReady ? '已补充地址' : '需要网址'} missing={!sourceReady} onResolve={resolveBlock} /><button className="prompt"><Paperclip size={17} />告诉 AI 你想怎么调整 <Send size={17} /></button><button className="continue" onClick={generateDraft}>生成语义初稿 <ChevronRight size={16} /></button></div>
        <div className="canvas-title"><span>语义画布</span><small>每个方块都是可读、可编辑的创作步骤</small></div>
        <div className="flow-lines" aria-hidden="true" />
        <div className="step-grid">{steps.map((step) => <article className={`step-card ${stateMeta[step.state].className}`} key={step.id}><div className="step-top"><span className="step-number">{step.id}</span><div>{editingStep === step.id ? <><input aria-label={`编辑 ${step.title}`} value={editTitle} onChange={(event) => setEditTitle(event.target.value)} /><button className="save-edit" onClick={() => saveEdit(step.id)}>保存编辑</button></> : <><b>{step.title}</b><small>{step.description}</small></>}</div><Status state={step.state} /></div><div className="ports"><span>输入 <b>{step.inputs}</b></span><span>输出 <b>{step.output}</b></span><button className="edit-step" onClick={() => beginEdit(step)}>编辑</button></div>{step.state === 'blocked' && <div className="block-note">阻塞：需要监管公告网址</div>}{(step.state === 'needs-confirmation' || step.state === 'exploring') && <button className="freeze" onClick={() => freezeStep(step.id)}>{step.state === 'needs-confirmation' ? '确认并固化' : '固化此步骤'}</button>}</article>)}</div>
        <div className="manual-canvas"><div><b>手动画布</b><small>拖动生成、个人或可信蓝图，再连接匹配的输入和输出。</small></div><button aria-label="放大" title="放大"><Plus size={17} /></button><button aria-label="缩小" title="缩小"><Minus size={17} /></button><div className="mini-map"><i /><i /><i /></div></div>
      </section>
      <aside className="inspector"><div className="panel-heading">{mode === 'review' ? '变化与影响' : '设计检查'} <button aria-label="收起"><ChevronRight size={18} /></button></div><section><h3>你想得到什么</h3><p>{intent}</p></section><section><h3>会使用什么</h3><p>公司官网、行业媒体和监管公告。所有来源在生成前都可检查和替换。</p></section><section><h3>仍缺少什么</h3><p>{sourceReady ? '来源已完整。' : '监管公告网站的网址。补充后，数字核查才能完成。'}</p></section><section><h3>通俗步骤检查器</h3>{steps.map((step) => <div className="check-row" key={step.id}><Status state={step.state} /><span>{step.title}</span></div>)}</section></aside>
    </main>
    <footer className="bottom-sheet">{mode === 'review' ? <><div className="sheet-title"><Bot /> AI 建议了 {proposals.length} 项改动 <button aria-label="关闭"><X size={18} /></button></div>{proposals.map((proposal) => <label className="proposal" key={proposal.id}><input type="checkbox" checked={proposal.selected} onChange={() => setProposals((current) => current.map((item) => item.id === proposal.id ? { ...item, selected: !item.selected } : item))} /><span><b>{proposal.label}</b><small>{proposal.detail}</small></span></label>)}<div className="review-actions"><button onClick={() => setProposals((current) => current.map((item) => ({ ...item, selected: false })))}>拒绝选中</button><button onClick={() => setNotice('已请求 AI 根据你的反馈修订。')}>请 AI 修改</button><button className="primary" onClick={acceptSelected}>接受 {accepted.length} 项修改</button></div></> : <><div><b>{notice || '当前设计尚无可生成的步骤'}</b><p>{sourceReady ? '可以继续确认并固化步骤，完成设计验证。' : '补全一个来源后即可解决阻塞项。'}</p></div><button className="primary" onClick={generateDraft}>审阅 AI 变更</button></>}</footer>
  </div>
}
