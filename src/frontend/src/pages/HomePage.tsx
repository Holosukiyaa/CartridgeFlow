import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import {
  fetchBaseImplementation,
  fetchStudioConformance,
  fetchCartridgeRuns,
  fetchLabFlows,
  fetchStudioTodo,
  fetchStudioTodoFile,
  fetchStudioTodoTemplate,
  type FlowLabItem,
  type RunResult,
  type StudioTodoResponse,
  type StudioConformanceResponse,
} from '../api.ts'
import { Box, Heading, Spinner, Text } from '../ui.tsx'
import CapabilityEvidenceViewer from '../components/CapabilityEvidenceViewer.tsx'

const PROTOCOL_STATUS_LABELS: Record<string, string> = {
  supported: '完整支持',
  partial: '部分支持',
  experimental: '实验性支持',
  deprecated: '已弃用',
}

const ACTIVE_RUN_STATUSES = ['running', 'retrying', 'recovering', 'rolling_back', 'created']
const ATTENTION_RUN_STATUSES = ['failed', 'interrupted']
const TERMINAL_RUN_STATUSES = ['completed', 'failed', 'interrupted', 'cancelled']

function runTimestamp(run: RunResult) {
  const date = new Date(run.created_at || run.updated_at || '')
  return Number.isNaN(date.getTime()) ? 0 : date.getTime()
}

function protocolVersionNumber(value: any) {
  return String(value || '')
    .split('.')
    .map((part) => Number.parseInt(part, 10) || 0)
    .reduce((total, part, index) => total + part / (10 ** (index * 3)), 0)
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
  const [evidenceViewerOpen, setEvidenceViewerOpen] = useState(false)

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

  const openTodoItems = todo?.items.filter((item) => !item.checked).slice(0, 3) || []
  const runSummary = useMemo(() => ({
    total: runs.length,
    failed: runs.filter((run) => run.status === 'failed').length,
    active: runs.filter((run) => ACTIVE_RUN_STATUSES.includes(run.status)).length,
  }), [runs])
  const overviewStats = useMemo(() => {
    const today = new Date()
    today.setHours(0, 0, 0, 0)
    const currentStartDate = new Date(today)
    currentStartDate.setDate(today.getDate() - 6)
    const currentStart = currentStartDate.getTime()
    const currentEnd = new Date(today).setDate(today.getDate() + 1)
    const previousStart = currentStart - 7 * 24 * 60 * 60 * 1000
    const recentRuns = runs.filter((run) => {
      const timestamp = runTimestamp(run)
      return timestamp >= currentStart && timestamp < currentEnd
    })
    const previousRuns = runs.filter((run) => {
      const timestamp = runTimestamp(run)
      return timestamp >= previousStart && timestamp < currentStart
    })
    const terminalRuns = recentRuns.filter((run) => TERMINAL_RUN_STATUSES.includes(run.status))
    const completedRuns = terminalRuns.filter((run) => run.status === 'completed').length
    const successRate = terminalRuns.length ? Math.round((completedRuns / terminalRuns.length) * 100) : null
    const delta = recentRuns.length - previousRuns.length
    const deltaLabel = previousRuns.length === 0
      ? (recentRuns.length ? `本周期新增 ${recentRuns.length} 次` : '近两周暂无运行')
      : delta === 0
        ? '与前 7 天持平'
        : `${delta > 0 ? '+' : ''}${Math.round((delta / previousRuns.length) * 100)}% 较前 7 天`
    return {
      recentCount: recentRuns.length,
      successRate,
      attention: runs.filter((run) => ATTENTION_RUN_STATUSES.includes(run.status)).length,
      editableFlows: projects.filter((project) => project.editable).length,
      deltaLabel,
    }
  }, [projects, runs])
  const storedProjectId = localStorage.getItem('cf.studio.recent_project') || ''
  const continueProject = projects.find((project) => project.id === storedProjectId)
    || projects.find((project) => project.editable)
    || projects[0]
  const supportedProtocols = base?.supported_protocols || []
  const currentProtocol = supportedProtocols
    .filter((item: any) => item?.id === 'CF-FARP' && item?.version)
    .sort((a: any, b: any) => protocolVersionNumber(b.version) - protocolVersionNumber(a.version))[0]
  const currentProtocolStatus = currentProtocol
    ? (PROTOCOL_STATUS_LABELS[currentProtocol.status] || currentProtocol.status || '已声明')
    : '未声明'
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

            <section className="cf-overview-activity-block" aria-label="运行活动">
              <header className="cf-overview-activity-heading">
                <div><span>RUN ACTIVITY</span><h2>运行活动</h2></div>
                <p>Flow 执行状态与近七日运行节奏</p>
              </header>

            <section className="cf-overview-stat-strip" aria-label="开发统计">
              <button type="button" onClick={() => navigate('/projects')}>
                <span>Flow 总数</span><strong>{projects.length}</strong><small>{overviewStats.editableFlows} 个可编辑 Flow</small><i><b style={{ width: `${projects.length ? Math.max(12, (overviewStats.editableFlows / projects.length) * 100) : 0}%` }} /></i>
              </button>
              <button type="button" onClick={() => navigate('/diagnostics?range=7d')}>
                <span>近 7 日运行</span><strong>{overviewStats.recentCount}</strong><small>{overviewStats.deltaLabel}</small><i className="neutral"><b style={{ width: `${Math.min(100, overviewStats.recentCount * 8)}%` }} /></i>
              </button>
              <button type="button" onClick={() => navigate('/diagnostics?range=7d&status=completed')}>
                <span>运行成功率</span><strong>{overviewStats.successRate === null ? '--' : `${overviewStats.successRate}%`}</strong><small>{overviewStats.successRate === null ? '暂无终态运行' : '按近 7 日终态运行计算'}</small><i className="success"><b style={{ width: `${overviewStats.successRate || 0}%` }} /></i>
              </button>
              <button type="button" className={overviewStats.attention ? 'attention' : ''} onClick={() => navigate('/diagnostics?status=attention')}>
                <span>需要关注</span><strong>{overviewStats.attention}</strong><small>{overviewStats.attention ? '失败或中断的运行' : '当前没有待诊断运行'}</small><i><b style={{ width: `${overviewStats.attention ? Math.min(100, overviewStats.attention * 18) : 0}%` }} /></i>
              </button>
            </section>
            </section>

            <div className="cf-overview-comfort-grid">
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
                  <span>{(todo?.open || 0) > openTodoItems.length ? `首页仅展示 ${openTodoItems.length} 项，还有 ${(todo?.open || 0) - openTodoItems.length} 项` : `已完成 ${todo?.completed || 0} 项`}</span>
                  <button type="button" onClick={() => void openTodoViewer()}>浏览完整 todo.md</button>
                  <button type="button" onClick={() => void openTodoViewer('TODO_TEMPLATE.md')}>查看基础模板</button>
                </div>
              </section>

              <div className="cf-overview-comfort-side">
              <section className="cf-overview-panel cf-overview-protocol">
                <div className="cf-overview-panel-head">
                  <div className="cf-overview-section-label"><span>Base Contract</span><h2>底座支持的协议</h2></div>
                  <b className="cf-overview-protocol-status">{currentProtocolStatus}</b>
                </div>
                <p className="cf-overview-protocol-copy">CF-FARP 定义卡带的清单读取、流程搭建、节点执行、用户交互、测试探针、产物交付与兼容性边界。业务逻辑仍由具体卡带和模型配方负责，底座只提供通用运行能力。</p>
                <div className="cf-overview-protocol-facts">
                  <div><span>协议族</span><strong>CF-FARP</strong></div>
                  <div><span>当前推荐</span><strong>{currentProtocol ? `${currentProtocol.id}@${currentProtocol.version}` : '等待声明'}</strong></div>
                  <button type="button" className="cf-overview-evidence-entry" onClick={() => setEvidenceViewerOpen(true)} title="查看底座能力证据列表"><span>能力证据</span><strong>{conformance?.report?.capabilities?.counts?.verified || 0} / {conformance?.report?.capabilities?.declared || 0}</strong></button>
                </div>
                <div className="cf-overview-conformance-line">
                  <span>自动测试 {conformance?.report?.tests?.counts?.passed || 0} / {conformance?.report?.tests?.total || 0}</span>
                  <span>{conformance?.report?.generated_at ? `报告 ${new Date(conformance.report.generated_at).toLocaleString('zh-CN')}` : '尚未生成自动报告'}</span>
                </div>
                <div className="cf-overview-protocol-list">
                  {supportedProtocols.slice().reverse().map((protocol: any) => (
                    <span key={`${protocol.id}-${protocol.version}`} className={protocol.version === currentProtocol?.version ? 'current' : ''}>
                      {protocol.id}@{protocol.version}
                      <b>{PROTOCOL_STATUS_LABELS[protocol.status] || protocol.status || '已声明'}</b>
                    </span>
                  ))}
                </div>
              </section>

              <section className="cf-overview-run-summary" aria-label="运行诊断摘要">
                <div><span>Runtime Health</span><h2>运行诊断</h2><p>运行明细、日志、产物和恢复操作已统一移至独立工作区。</p></div>
                <div className="cf-overview-run-counts"><span><b>{runSummary.total}</b>全部</span><span className={runSummary.failed ? 'danger' : ''}><b>{runSummary.failed}</b>失败</span><span className={runSummary.active ? 'active' : ''}><b>{runSummary.active}</b>进行中</span></div>
                <button type="button" onClick={() => navigate('/diagnostics')}>进入运行诊断</button>
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

        <CapabilityEvidenceViewer open={evidenceViewerOpen} report={conformance?.report} onClose={() => setEvidenceViewerOpen(false)} />
      </Box>
    </Box>
  )
}
