import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import {
  fetchBaseImplementation,
  fetchStudioConformance,
  fetchCartridgeRuns,
  fetchCartridgeRunEvents,
  fetchLabFlows,
  fetchStudioTodo,
  fetchStudioTodoFile,
  fetchStudioTodoTemplate,
  type FlowLabItem,
  type FlowEvent,
  type RunResult,
  type StudioTodoResponse,
  type StudioConformanceResponse,
} from '../api.ts'
import { Box, Heading, Spinner, Text } from '../ui.tsx'

const STATUS_LABELS: Record<string, string> = {
  completed: '运行完成',
  failed: '运行失败',
  interrupted: '运行中断',
  cancelled: '已取消',
  paused_waiting_user: '等待用户',
  running: '运行中',
  created: '已创建',
}

function formatActivityTime(value?: string) {
  if (!value) return '时间未知'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(date)
}

function artifactKind(item: any) {
  const mime = String(item?.mime_type || '').toLowerCase()
  const name = String(item?.name || '').toLowerCase()
  if (mime.includes('html') || name.endsWith('.html')) return 'html'
  if (mime.startsWith('image/') || /\.(png|jpe?g|gif|webp)$/i.test(name)) return 'image'
  if (mime.startsWith('video/') || /\.(mp4|webm|mov)$/i.test(name)) return 'video'
  return 'file'
}

export default function HomePage() {
  const navigate = useNavigate()
  const [projects, setProjects] = useState<FlowLabItem[]>([])
  const [runs, setRuns] = useState<RunResult[]>([])
  const [todo, setTodo] = useState<StudioTodoResponse | null>(null)
  const [base, setBase] = useState<any>(null)
  const [conformance, setConformance] = useState<StudioConformanceResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [todoViewerOpen, setTodoViewerOpen] = useState(false)
  const [todoViewerFile, setTodoViewerFile] = useState<'TODO.md' | 'TODO_TEMPLATE.md'>('TODO.md')
  const [todoText, setTodoText] = useState('')
  const [todoViewerLoading, setTodoViewerLoading] = useState(false)
  const [logRun, setLogRun] = useState<RunResult | null>(null)
  const [logEvents, setLogEvents] = useState<FlowEvent[]>([])
  const [logLoading, setLogLoading] = useState(false)
  const [previewRun, setPreviewRun] = useState<RunResult | null>(null)

  useEffect(() => {
    let active = true
    const load = async () => {
      setLoading(true)
      try {
        const [flowData, baseData, runData, todoData, conformanceData] = await Promise.all([
          fetchLabFlows(),
          fetchBaseImplementation(),
          fetchCartridgeRuns(),
          fetchStudioTodo(),
          fetchStudioConformance(),
        ])
        if (!active) return
        setProjects(flowData.items || [])
        setBase(baseData.base || null)
        setConformance(conformanceData)
        setRuns(runData.items || [])
        setTodo(todoData)
        setError('')
      } catch (reason: any) {
        if (active) setError(reason?.message || '概览加载失败')
      } finally {
        if (active) setLoading(false)
      }
    }
    void load()
    return () => { active = false }
  }, [])

  const projectById = useMemo(
    () => new Map(projects.map((project) => [project.id, project])),
    [projects],
  )
  const recentRuns = useMemo(() => [...runs]
    .sort((a, b) => String(b.updated_at || b.created_at || '').localeCompare(String(a.updated_at || a.created_at || '')))
    .slice(0, 20), [runs])
  const openTodoItems = todo?.items.filter((item) => !item.checked).slice(0, 20) || []
  const storedProjectId = localStorage.getItem('cf.studio.recent_project') || ''
  const continueProject = projects.find((project) => project.id === storedProjectId)
    || projects.find((project) => project.editable)
    || projects[0]
  const supportedProtocols = base?.supported_protocols || []
  const protocol05 = supportedProtocols.find((item: any) => item.id === 'CF-FARP' && item.version === '0.5')
  const previewArtifacts = useMemo(() => {
    if (!previewRun) return []
    return [...(previewRun.delivery?.artifacts || []), ...(previewRun.artifacts || [])]
  }, [previewRun])

  const openTodoViewer = async (file: 'TODO.md' | 'TODO_TEMPLATE.md' = 'TODO.md') => {
    setTodoViewerFile(file)
    setTodoViewerOpen(true)
    setTodoText('')
    setTodoViewerLoading(true)
    try {
      setTodoText(file === 'TODO.md' ? await fetchStudioTodoFile() : await fetchStudioTodoTemplate())
    } catch (reason: any) {
      setTodoText(`读取 ${file} 失败\n\n${reason?.message || reason}`)
    } finally {
      setTodoViewerLoading(false)
    }
  }

  const openRunLog = async (run: RunResult) => {
    setLogRun(run)
    setLogEvents([])
    setLogLoading(true)
    try {
      const result = await fetchCartridgeRunEvents(run.run_id)
      setLogEvents(result.items || [])
    } catch (reason: any) {
      setLogEvents([{ type: 'error', message: reason?.message || '运行日志读取失败' }])
    } finally {
      setLogLoading(false)
    }
  }

  return (
    <Box className="cf-page cf-home-page">
      <Box className="cf-page-inner cf-home-inner">
        <header className="cf-overview-heading">
          <div>
            <Text className="cf-kicker">Developer Console</Text>
            <Heading className="cf-home-title">开发控制台</Heading>
            <Text className="cf-home-subtitle">专属服务卡带的底座入口与工作记录</Text>
          </div>
          <div className={`cf-overview-health ${conformance?.report?.status === 'passed' ? 'ok' : 'partial'}`}>
            <i />
            <span>底座 {conformance?.report?.status === 'passed' ? '自动测试通过' : '能力部分验证'}</span>
          </div>
        </header>

        {loading && <div className="cf-home-loading"><Spinner /></div>}
        {error && <div className="cf-home-alert danger">{error}</div>}

        {!loading && !error && (
          <>
            <section className="cf-overview-resume" aria-label="继续最近的工作">
              <div className="cf-overview-resume-copy">
                <span>Resume Work</span>
                <h2>继续最近的工作</h2>
                <p>{continueProject ? `最近打开：${continueProject.name}` : '还没有最近打开的卡带'}</p>
              </div>
              <div className="cf-overview-resume-meta">
                <small>{continueProject ? continueProject.id : '创建第一个开发卡带后，这里会保留入口'}</small>
                <span>{continueProject ? '从设计台继续' : '工作记录将显示在这里'}</span>
              </div>
              <div className="cf-overview-resume-actions">
                <button
                  type="button"
                  className="primary"
                  disabled={!continueProject}
                  onClick={() => continueProject && navigate(`/projects/${encodeURIComponent(continueProject.id)}/design`)}
                >继续工作</button>
                <button type="button" onClick={() => navigate('/projects?create=1')}>新建卡带</button>
                <button type="button" onClick={() => navigate('/projects?import=1')}>导入卡带</button>
              </div>
            </section>

            <div className="cf-overview-main-grid">
              <section className="cf-overview-panel cf-overview-todo">
                <div className="cf-overview-panel-head">
                  <div className="cf-overview-section-label"><span>Source: {todo?.source || 'TODO.md'}</span><h2>待处理事项</h2></div>
                  <div className="cf-overview-todo-count"><strong>{todo?.open || 0}</strong><span>/ {todo?.total || 0}</span></div>
                </div>
                {openTodoItems.length === 0 ? (
                  <div className="cf-overview-clear"><i /><div><strong>TODO.md 当前没有未完成事项</strong><span>所有任务都已完成，或文件还没有添加任务。</span></div></div>
                ) : (
                  <div className="cf-overview-todo-list">
                    {openTodoItems.map((item) => (
                      <button type="button" key={`${item.line}-${item.id}`} onClick={() => void openTodoViewer()}>
                        <i />
                        <span><small>{item.priority || item.section} · L{item.line}</small><strong>{item.id ? `${item.id} ` : ''}{item.text}</strong></span>
                        <b>查看</b>
                      </button>
                    ))}
                  </div>
                )}
                <div className="cf-overview-todo-footer">
                  <span>已完成 {todo?.completed || 0} 项</span>
                  <button type="button" onClick={() => void openTodoViewer()}>浏览完整 todo.md</button>
                  <button type="button" onClick={() => void openTodoViewer('TODO_TEMPLATE.md')}>查看基础模板</button>
                </div>
              </section>

              <div className="cf-overview-right-stack">
              <section className="cf-overview-panel cf-overview-protocol">
                <div className="cf-overview-panel-head">
                  <div className="cf-overview-section-label"><span>Base Contract</span><h2>底座支持的协议</h2></div>
                  <b className="cf-overview-protocol-status">{protocol05?.status || 'unknown'}</b>
                </div>
                <p className="cf-overview-protocol-copy">CF-FARP 定义卡带的清单读取、流程搭建、节点执行、用户交互、测试探针、产物交付与兼容性边界。业务逻辑仍由具体卡带和模型配方负责，底座只提供通用运行能力。</p>
                <div className="cf-overview-protocol-facts">
                  <div><span>协议族</span><strong>CF-FARP</strong></div>
                  <div><span>当前推荐</span><strong>CF-FARP@0.6</strong></div>
                  <div><span>能力证据</span><strong>{conformance?.report?.capabilities?.counts?.verified || 0} / {conformance?.report?.capabilities?.declared || 0}</strong></div>
                </div>
                <div className="cf-overview-conformance-line">
                  <span>自动测试 {conformance?.report?.tests?.counts?.passed || 0} / {conformance?.report?.tests?.total || 0}</span>
                  <span>{conformance?.report?.generated_at ? `报告 ${new Date(conformance.report.generated_at).toLocaleString('zh-CN')}` : '尚未生成自动报告'}</span>
                </div>
                <div className="cf-overview-protocol-list">
                  {supportedProtocols.slice().reverse().map((protocol: any) => (
                    <span key={`${protocol.id}-${protocol.version}`} className={protocol.version === '0.5' ? 'current' : ''}>{protocol.id}@{protocol.version}<b>{protocol.status}</b></span>
                  ))}
                </div>
              </section>

              <section className="cf-overview-panel cf-overview-activity cf-overview-right-activity">
                <div className="cf-overview-panel-head">
                  <div className="cf-overview-section-label"><span>Run Ledger</span><h2>近期运行</h2></div>
                  <span className="cf-overview-activity-total">{runs.length > recentRuns.length ? `最近 ${recentRuns.length} / ${runs.length}` : `${recentRuns.length} 条记录`}</span>
                </div>
                {recentRuns.length === 0 ? (
                  <div className="cf-overview-activity-empty">暂无运行记录</div>
                ) : (
                  <div className="cf-overview-activity-list">
                    {recentRuns.map((run) => {
                      const project = projectById.get(run.cartridge_id)
                      return (
                        <div className="cf-overview-activity-row" key={run.run_id}>
                          <i className={run.status} />
                          <span className="cf-overview-activity-identity">
                            <strong><em>卡带</em>{project?.name || run.cartridge_id}</strong>
                            <small title={`${run.cartridge_id} · ${run.run_id}`}>{run.cartridge_id} · {run.run_id}</small>
                          </span>
                          <span className="cf-overview-activity-meta"><b>{STATUS_LABELS[run.status] || run.status}</b><time>{formatActivityTime(run.updated_at || run.created_at)}</time></span>
                          <span className="cf-overview-activity-actions">
                            <button type="button" onClick={() => void openRunLog(run)}>查看日志</button>
                            <button type="button" onClick={() => setPreviewRun(run)}>预览产物</button>
                          </span>
                        </div>
                      )
                    })}
                  </div>
                )}
              </section>
              </div>
            </div>
          </>
        )}

        {todoViewerOpen && (
          <div className="cf-modal-backdrop" role="presentation" onClick={() => setTodoViewerOpen(false)}>
            <section className="cf-file-viewer" role="dialog" aria-modal="true" aria-label={`${todoViewerFile} 文件浏览器`} onClick={(event) => event.stopPropagation()}>
              <header className="cf-modal-head">
                <div>
                  <span className="cf-modal-kicker">Markdown file</span>
                  <h2>{todoViewerFile}</h2>
                </div>
                <button type="button" className="cf-modal-close" onClick={() => setTodoViewerOpen(false)} aria-label="关闭文件浏览器">关闭</button>
              </header>
              <div className="cf-file-viewer-meta"><span>{todoViewerFile === 'TODO.md' ? `${todo?.open || 0} open / ${todo?.total || 0} tasks` : '基础待办模板'}</span><code>docs/planning/{todoViewerFile}</code></div>
              <div className="cf-file-viewer-body">
                {todoViewerLoading ? <div className="cf-modal-empty">读取 {todoViewerFile}...</div> : <pre>{todoText}</pre>}
              </div>
            </section>
          </div>
        )}

        {logRun && (
          <div className="cf-modal-backdrop" role="presentation" onClick={() => setLogRun(null)}>
            <section className="cf-run-log-viewer" role="dialog" aria-modal="true" aria-label="运行日志" onClick={(event) => event.stopPropagation()}>
              <header className="cf-modal-head">
                <div>
                  <span className="cf-modal-kicker">Run log</span>
                  <h2>{logRun.run_id}</h2>
                </div>
                <button type="button" className="cf-modal-close" onClick={() => setLogRun(null)} aria-label="关闭运行日志">关闭</button>
              </header>
              <div className="cf-run-log-meta"><span>{projectById.get(logRun.cartridge_id)?.name || logRun.cartridge_id}</span><b className={logRun.status}>{STATUS_LABELS[logRun.status] || logRun.status}</b></div>
              <div className="cf-run-log-body">
                {logLoading ? <div className="cf-modal-empty">读取运行事件...</div> : logEvents.length === 0 ? <div className="cf-modal-empty">没有可显示的运行事件</div> : logEvents.map((event, index) => (
                  <div className="cf-run-log-row" key={`${event.timestamp || 'event'}-${index}`}>
                    <time>{formatActivityTime(event.timestamp)}</time>
                    <span className="cf-run-log-state">{event.state || event.type || 'event'}</span>
                    <p>{event.message || event.data?.output || event.data?.action || '状态已更新'}</p>
                  </div>
                ))}
              </div>
            </section>
          </div>
        )}

        {previewRun && (
          <div className="cf-modal-backdrop" role="presentation" onClick={() => setPreviewRun(null)}>
            <section className="cf-run-preview-viewer" role="dialog" aria-modal="true" aria-label="运行预览" onClick={(event) => event.stopPropagation()}>
              <header className="cf-modal-head">
                <div>
                  <span className="cf-modal-kicker">Run preview</span>
                  <h2>{previewRun.run_id}</h2>
                </div>
                <button type="button" className="cf-modal-close" onClick={() => setPreviewRun(null)} aria-label="关闭运行预览">关闭</button>
              </header>
              <div className="cf-run-preview-body">
                {previewRun.delivery?.summary && <p className="cf-run-preview-summary">{previewRun.delivery.summary}</p>}
                {previewArtifacts.length === 0 ? (
                  <div className="cf-modal-empty">这个运行还没有可预览的交付产物</div>
                ) : previewArtifacts.map((item, index) => {
                  const kind = artifactKind(item)
                  return (
                    <article className="cf-preview-artifact" key={`${item.artifact_id || item.name}-${index}`}>
                      <div className="cf-preview-artifact-head"><strong>{item.name}</strong><span>{item.mime_type || item.type || kind}</span></div>
                      {kind === 'html' && item.url ? <iframe className="cf-run-preview-iframe" src={item.url} title={item.name} /> : null}
                      {kind === 'image' && item.url ? <img className="cf-run-preview-image" src={item.url} alt={item.name} /> : null}
                      {kind === 'video' && item.url ? <video className="cf-run-preview-video" controls src={item.url} /> : null}
                      {kind === 'file' && <div className="cf-preview-file"><code>{item.display_path || item.path || item.url}</code>{item.url && <a href={item.url} target="_blank" rel="noreferrer">打开文件</a>}</div>}
                    </article>
                  )
                })}
              </div>
            </section>
          </div>
        )}
      </Box>
    </Box>
  )
}
