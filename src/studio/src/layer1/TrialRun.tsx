import { useEffect, useState } from 'react'
import { X } from 'lucide-react'
import { composeTrialDigest, fetchTrialSources, type TrialDigest, type TrialItem } from '../api/client.ts'
import { Button } from '../ui/index.ts'

type StepState = 'idle' | 'running' | 'ok' | 'fallback' | 'error'

const STEPS = [
  { id: 'fetch', label: '获取已审核来源的最新内容' },
  { id: 'organize', label: '用 AI 整理成新闻' },
  { id: 'output', label: '输出今日新闻日报' },
] as const

export function TrialRun({ onClose }: { onClose: () => void }) {
  const [stepState, setStepState] = useState<Record<string, StepState>>({ fetch: 'idle', organize: 'idle', output: 'idle' })
  const [detail, setDetail] = useState<Record<string, string>>({})
  const [items, setItems] = useState<TrialItem[]>([])
  const [digest, setDigest] = useState<TrialDigest | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const mark = (id: string, status: StepState, text = '') => {
    setStepState((current) => ({ ...current, [id]: status }))
    if (text) setDetail((current) => ({ ...current, [id]: text }))
  }

  const run = async () => {
    setBusy(true)
    setError('')
    setDigest(null)
    setItems([])
    setStepState({ fetch: 'running', organize: 'idle', output: 'idle' })
    setDetail({})
    try {
      const fetched = await fetchTrialSources()
      setItems(fetched.items)
      mark('fetch', 'ok', `${fetched.items.length} 条 · ${fetched.feeds.map((item) => item.name).join('、')}`)
      mark('organize', 'running')
      const composed = await composeTrialDigest(fetched.items)
      mark('organize', composed.digest.used_model ? 'ok' : 'fallback', composed.digest.used_model ? composed.digest.model : '未连接模型，使用条目摘要')
      mark('output', 'ok', composed.digest.headline)
      setDigest(composed.digest)
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : '试运行没有完成'
      setError(message)
      setStepState((current) => {
        const next = { ...current }
        const running = STEPS.find((item) => next[item.id] === 'running')
        if (running) next[running.id] = 'error'
        return next
      })
    } finally {
      setBusy(false)
    }
  }

  useEffect(() => { void run() }, [])

  return <div className="overlay" role="presentation" onClick={onClose}>
    <div className="dialog is-wide trial-run" role="dialog" aria-label="试运行今日日报" onClick={(event) => event.stopPropagation()}>
      <header>
        <div>
          <h2>试运行今日日报</h2>
          <p>真实拉取公开 RSS，再交给已连接的共创 AI 整理成今天的新闻日报。</p>
        </div>
        <Button variant="icon" aria-label="关闭" onClick={onClose}><X size={14} /></Button>
      </header>
      <div className="trial-body">
        <ol className="trial-steps">
          {STEPS.map((item, index) => <li key={item.id} className={`is-${stepState[item.id]}`}>
            <em>{index + 1}</em>
            <div>
              <strong>{item.label}</strong>
              <small>{stepState[item.id] === 'running' ? '进行中…' : detail[item.id] || '等待开始'}</small>
            </div>
          </li>)}
        </ol>
        <div className="trial-main">
          {!items.length && !digest && !error ? <p className="hint">点开始后会先取 Hacker News · AI 和 MIT Technology Review 的公开订阅，再生成日报。</p> : null}
          {items.length ? <section>
            <h3>取到的来源</h3>
            <ul className="trial-items">
              {items.slice(0, 8).map((item) => <li key={item.link || item.title}>
                <a href={item.link} target="_blank" rel="noreferrer">{item.title}</a>
                <small>{item.source}{item.published ? ` · ${item.published}` : ''}</small>
              </li>)}
            </ul>
          </section> : null}
          {digest ? <section className="trial-digest">
            <h3>{digest.headline}</h3>
            <p className="hint">{digest.used_model ? `由 ${digest.model} 整理` : '共创 AI 未连接，这是按条目标题拼出的草稿'}</p>
            <pre>{digest.body.replace(/\*\*/g, '')}</pre>
          </section> : null}
          {error ? <p className="alert" role="alert">{error}</p> : null}
        </div>
      </div>
      <div className="dialog-foot">
        <span>{busy ? '正在跑真实流程' : digest ? '这次已经跑完' : '不会写入方案，只在这一页演示'}</span>
        <Button variant="ghost" onClick={onClose}>关闭</Button>
        <Button disabled={busy} onClick={() => void run()}>{digest ? '再跑一次' : '开始试运行'}</Button>
      </div>
    </div>
  </div>
}
