import { useEffect, useMemo, useState } from 'react'
import { Box, CheckCircle2, Database, FolderOpen, Gauge, RefreshCw, ShieldCheck, Wrench } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import { useNavigate } from 'react-router-dom'
import {
  fetchBaseImplementation, fetchCartridgeRuns, fetchLabFlows, fetchLlmProviders, fetchStudioConformance, fetchStudioEnvironment, fetchStudioResources,
  fetchStudioTodo, fetchStudioTodoFile, fetchStudioTodoTemplate,
  type FlowLabItem, type RunResult, type StudioConformanceResponse, type StudioEnvironmentSnapshot, type StudioResources, type StudioTodoResponse,
} from '../api.ts'
import { NextButton, NextDialog, NextEmpty, NextLoading, NextMetricStrip, NextNotice, NextPage, NextPanel, NextStatus } from './NextUi.tsx'

const ACTIVE = new Set(['running', 'retrying', 'recovering', 'rolling_back', 'created'])
const TERMINAL = new Set(['completed', 'failed', 'interrupted', 'cancelled'])
const protocolLabel: Record<string, string> = { supported: '完整支持', partial: '部分支持', experimental: '实验性支持', deprecated: '已弃用' }

function dayStamp(value?: string) { const date = new Date(value || ''); return Number.isNaN(date.getTime()) ? 0 : date.getTime() }

export default function NextOverviewPage() {
  const navigate = useNavigate()
  const [projects, setProjects] = useState<FlowLabItem[]>([])
  const [runs, setRuns] = useState<RunResult[]>([])
  const [todo, setTodo] = useState<StudioTodoResponse | null>(null)
  const [base, setBase] = useState<any>(null)
  const [conformance, setConformance] = useState<StudioConformanceResponse | null>(null)
  const [providers, setProviders] = useState<any[]>([])
  const [resources, setResources] = useState<StudioResources | null>(null)
  const [environment, setEnvironment] = useState<StudioEnvironmentSnapshot | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [todoOpen, setTodoOpen] = useState(false)
  const [todoFile, setTodoFile] = useState<'TODO.md' | 'TODO_TEMPLATE.md'>('TODO.md')
  const [todoMode, setTodoMode] = useState<'preview' | 'source'>('preview')
  const [todoLine, setTodoLine] = useState<number | null>(null)
  const [todoText, setTodoText] = useState('')
  const [evidenceOpen, setEvidenceOpen] = useState(false)

  async function load() {
    setLoading(true); setError('')
    try {
      const [flows, runData, todoData, baseData, conformanceData, providerData, resourceData, environmentData] = await Promise.all([
        fetchLabFlows(), fetchCartridgeRuns(), fetchStudioTodo(), fetchBaseImplementation(), fetchStudioConformance(),
        fetchLlmProviders().catch(() => ({ providers: [] })), fetchStudioResources().catch(() => null), fetchStudioEnvironment().catch(() => null),
      ])
      setProjects(flows.items || []); setRuns(runData.items || []); setTodo(todoData); setBase(baseData.base || null); setConformance(conformanceData)
      setProviders(providerData.providers || []); setResources(resourceData); setEnvironment(environmentData)
    } catch (reason: any) { setError(reason?.message || '概览加载失败') } finally { setLoading(false) }
  }
  useEffect(() => { void load() }, [])

  async function openTodo(file: 'TODO.md' | 'TODO_TEMPLATE.md' = 'TODO.md', line: number | null = null) {
    setTodoFile(file); setTodoLine(line); setTodoMode(line ? 'source' : 'preview'); setTodoText(''); setTodoOpen(true)
    try { setTodoText(file === 'TODO.md' ? await fetchStudioTodoFile() : await fetchStudioTodoTemplate()) } catch (reason: any) { setTodoText(`读取失败：${reason?.message || reason}`) }
  }

  const stats = useMemo(() => {
    const today = new Date(); today.setHours(0, 0, 0, 0)
    const start = today.getTime() - 6 * 86400000; const end = today.getTime() + 86400000
    const recent = runs.filter((run) => dayStamp(run.created_at || run.updated_at) >= start && dayStamp(run.created_at || run.updated_at) < end)
    const terminal = recent.filter((run) => TERMINAL.has(run.status)); const completed = terminal.filter((run) => run.status === 'completed').length
    const daily = Array.from({ length: 7 }, (_, index) => { const date = new Date(today); date.setDate(today.getDate() - (6 - index)); const from = date.getTime(); const to = from + 86400000; return { label: index === 6 ? '今' : `${date.getMonth() + 1}/${date.getDate()}`, count: runs.filter((run) => { const time = dayStamp(run.created_at || run.updated_at); return time >= from && time < to }).length } })
    return { recent: recent.length, success: terminal.length ? Math.round((completed / terminal.length) * 100) : null, attention: runs.filter((run) => ['failed', 'interrupted'].includes(run.status)).length, active: runs.filter((run) => ACTIVE.has(run.status)).length, daily, max: Math.max(1, ...daily.map((item) => item.count)) }
  }, [runs])
  const currentProtocol = (base?.supported_protocols || []).filter((item: any) => item?.id === 'CF-FARP').sort((a: any, b: any) => String(b.version).localeCompare(String(a.version), undefined, { numeric: true }))[0]
  const continueProject = projects.find((project) => project.id === localStorage.getItem('cf.studio.recent_project')) || projects.find((project) => project.editable) || projects[0]
  const openTodoItems = todo?.items.filter((item) => !item.checked).slice(0, 4) || []
  const readyModels = providers.filter((provider) => provider.enabled !== false && provider.has_key && provider.base_url && provider.default_model && provider.tested_ok).length
  const tools = [...(resources?.builtin_tools || []), ...(resources?.tools || [])]
  const configuredVariables = environment?.references.filter((item) => item.configured).length || 0

  return <NextPage page="overview" title="开发控制台" description="专属服务卡带的底座入口与工作记录。" right={<><NextStatus tone={conformance?.report?.status === 'passed' ? 'success' : 'warning'}>{conformance?.report?.status === 'passed' ? '能力验证通过' : '能力部分验证'}</NextStatus><NextButton onClick={() => void load()} aria-label="刷新概览"><RefreshCw size={15} /></NextButton></>}>
    {loading && <NextLoading label="正在读取工作台状态" />}
    {error && <NextNotice tone="danger">{error}</NextNotice>}
    {!loading && !error && <div className="nx-overview-grid">
      <NextPanel className="nx-overview-recent" title="继续最近的工作" kicker="最近打开">
        <div className="nx-recent-main"><div className="nx-cartridge-mark"><Box size={25} /></div><div><strong>{continueProject?.name || '还没有开发卡带'}</strong><span>{continueProject?.id || '创建第一张卡带后，这里会保留入口'}</span></div><NextStatus tone={continueProject ? 'success' : 'neutral'}>{continueProject ? '可继续' : '等待创建'}</NextStatus></div>
        <div className="nx-recent-actions"><NextButton variant="primary" disabled={!continueProject} onClick={() => continueProject && navigate(`/projects/${encodeURIComponent(continueProject.id)}/design`)}>继续工作</NextButton><NextButton onClick={() => navigate('/next/projects?create=1')}>新建卡带</NextButton><NextButton onClick={() => navigate('/next/projects?import=1')}>导入卡带</NextButton></div>
        <div className="nx-recent-facts"><div><span>Flow 数量</span><strong>{projects.length}</strong></div><div><span>可编辑</span><strong>{projects.filter((item) => item.editable).length}</strong></div><div><span>最近运行</span><strong>{stats.recent}</strong></div></div>
      </NextPanel>

      <NextPanel className="nx-overview-activity" title="运行活动" kicker="RUN ACTIVITY" action={<NextButton variant="link" onClick={() => navigate('/next/diagnostics')}>查看全部</NextButton>}>
        <div className="nx-activity-content"><div className="nx-chart">{stats.daily.map((day) => <div key={day.label} title={`${day.label} ${day.count} 次`}><i style={{ height: `${day.count ? Math.max(10, (day.count / stats.max) * 100) : 4}%` }} /><small>{day.label}</small></div>)}</div><div className="nx-activity-side"><span>近 7 日运行</span><strong>{stats.recent}</strong><small>{stats.success === null ? '暂无终态运行' : `成功率 ${stats.success}%`}</small></div></div>
        <div className="nx-activity-metrics"><div><span>全部运行</span><strong>{runs.length}</strong></div><div><span>失败</span><strong className="danger">{stats.attention}</strong></div><div><span>进行中</span><strong className="info">{stats.active}</strong></div><div><span>已完成</span><strong className="success">{runs.filter((run) => run.status === 'completed').length}</strong></div></div>
      </NextPanel>

      <NextPanel className="nx-overview-todo" title="待处理事项" kicker="TODO.md" action={<strong className="nx-open-count">{todo?.open || 0}<small> / {todo?.total || 0}</small></strong>}>
        <div className="nx-todo-list">{openTodoItems.length ? openTodoItems.map((item) => <button type="button" key={`${item.line}-${item.id}`} onClick={() => void openTodo('TODO.md', item.line)}><span className="nx-todo-dot" /><span><small>{item.priority || item.section} · L{item.line}</small><strong>{item.id ? `${item.id} ` : ''}{item.text}</strong></span><b>查看</b></button>) : <NextEmpty icon={<CheckCircle2 size={24} />} title="TODO.md 当前没有未完成事项" description="所有任务都已完成，或文件还没有添加任务。" />}</div>
        <footer><span>已完成 {todo?.completed || 0} 项</span><NextButton variant="link" onClick={() => void openTodo()}>浏览完整 todo.md</NextButton><NextButton variant="link" onClick={() => void openTodo('TODO_TEMPLATE.md')}>查看基础模板</NextButton></footer>
      </NextPanel>

      <aside className="nx-overview-side"><NextPanel className="nx-protocol" title="底座支持的协议" kicker="BASE CONTRACT" action={<NextStatus tone={currentProtocol?.status === 'supported' ? 'success' : 'warning'}>{currentProtocol ? protocolLabel[currentProtocol.status] || currentProtocol.status : '未声明'}</NextStatus>}>
        <p>CF-FARP 定义卡带清单、流程搭建、节点执行、交互、测试探针、产物交付与兼容性边界。业务逻辑仍由具体卡带和模型配方负责。</p><div className="nx-protocol-facts"><div><span>协议族</span><strong>CF-FARP</strong></div><div><span>当前推荐</span><strong>{currentProtocol ? `${currentProtocol.id}@${currentProtocol.version}` : '等待声明'}</strong></div><button type="button" onClick={() => setEvidenceOpen(true)}><ShieldCheck size={16} /><span>能力证据</span><strong>{conformance?.report?.capabilities?.counts?.verified || 0} / {conformance?.report?.capabilities?.declared || 0}</strong></button></div>
      </NextPanel><NextPanel className="nx-run-summary" title="运行诊断" kicker="RUNTIME HEALTH" action={<NextButton variant="link" onClick={() => navigate('/next/diagnostics')}>进入诊断</NextButton>}><p>运行明细、日志、产物和恢复操作集中在独立工作区。</p><NextMetricStrip metrics={[{ label: '全部', value: runs.length }, { label: '失败', value: stats.attention, tone: stats.attention ? 'danger' : 'default' }, { label: '进行中', value: stats.active, tone: stats.active ? 'info' : 'default' }]} /></NextPanel></aside>

      <NextPanel className="nx-overview-resources" title="本地资源接线" kicker="LOCAL RESOURCE ROUTING" action={<NextButton onClick={() => navigate('/next/resources')}>管理接线</NextButton>}><div className="nx-resource-dock"><button type="button" onClick={() => navigate('/next/resources?config=1&kind=model')}><Database size={20} /><span>模型线路</span><strong>{readyModels}<small> / {providers.length}</small></strong><em>{readyModels ? '连接可用' : '等待配置'}</em></button><button type="button" onClick={() => navigate('/next/resources?config=1&kind=tool')}><Wrench size={20} /><span>工具资源</span><strong>{tools.filter((tool) => tool.enabled !== false).length}<small> / {tools.length}</small></strong><em>底座能力</em></button><button type="button" onClick={() => navigate('/next/resources')}><FolderOpen size={20} /><span>本机凭据</span><strong>{configuredVariables}<small> / {environment?.references.length || 0}</small></strong><em>保留在本机</em></button></div></NextPanel>
    </div>}

    <NextDialog title={`${todoFile} 文件浏览器`} eyebrow="WORKSPACE DOCUMENT" open={todoOpen} onClose={() => setTodoOpen(false)} wide><div className="nx-document-toolbar"><span>{todoFile}</span><div><NextButton className={todoMode === 'preview' ? 'selected' : ''} onClick={() => setTodoMode('preview')}>预览</NextButton><NextButton className={todoMode === 'source' ? 'selected' : ''} onClick={() => setTodoMode('source')}>源码</NextButton></div></div>{todoMode === 'preview' ? <article className="nx-markdown"><ReactMarkdown>{todoText || '正在读取…'}</ReactMarkdown></article> : <pre className="nx-source">{todoText.split(/\r?\n/).map((line, index) => <span className={todoLine === index + 1 ? 'highlight' : ''} data-line={index + 1} key={index}><i>{String(index + 1).padStart(4, ' ')}</i>{line || ' '}</span>)}</pre>}</NextDialog>
    <NextDialog title="能力证据" eyebrow="CAPABILITY EVIDENCE" open={evidenceOpen} onClose={() => setEvidenceOpen(false)} wide><div className="nx-evidence-summary"><NextMetricStrip metrics={[{ label: '已验证', value: conformance?.report?.capabilities?.counts?.verified || 0, tone: 'success' }, { label: '已声明', value: conformance?.report?.capabilities?.declared || 0 }, { label: '自动测试', value: `${conformance?.report?.tests?.counts?.passed || 0} / ${conformance?.report?.tests?.total || 0}` }]} /></div><div className="nx-evidence-list">{(conformance?.report?.capabilities?.items || []).map((item: any) => <div key={item.id || item.name}><NextStatus tone={item.status === 'verified' || item.status === 'passed' ? 'success' : 'warning'}>{item.status || '已声明'}</NextStatus><strong>{item.id || item.name || '未命名能力'}</strong><span>{item.evidence || item.source || item.test || '已登记在底座能力证据报告中'}</span></div>)}{!(conformance?.report?.capabilities?.items || []).length && <NextEmpty icon={<Gauge size={22} />} title="当前报告没有逐项证据" description="能力总数仍以底座自动报告为准。" />}</div></NextDialog>
  </NextPage>
}
