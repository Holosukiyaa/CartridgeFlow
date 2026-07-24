import type { CSSProperties, ReactNode } from 'react'
import NextOverviewPage from './NextOverviewPage.tsx'
import NextProjectsPage from './NextProjectsPage.tsx'
import './next-redesign.css'

export type NextPageKind = 'overview' | 'projects' | 'diagnostics' | 'resources' | 'release' | 'settings'

type PageDefinition = {
  title: string
  description: string
  metrics?: number
  actions?: number
}

const PAGE_DEFINITIONS: Record<NextPageKind, PageDefinition> = {
  overview: { title: '开发控制台', description: '专属服务卡带的底座入口与工作记录。', metrics: 4, actions: 1 },
  projects: { title: '卡带管理', description: '设计、验证和打包专属服务卡带。', actions: 3 },
  diagnostics: { title: '运行诊断', description: '集中查看 Flow 的运行证据、失败原因和恢复动作。', metrics: 4, actions: 1 },
  resources: { title: '资源中心', description: '集中查看底座可调用的模型、工具、本机环境与待分配需求。', actions: 2 },
  release: { title: '打包发布', description: '完成交付预检、迁移检查并生成可下载的卡带包。', metrics: 4, actions: 1 },
  settings: { title: '其他设置', description: '调整工作台的显示、密度、滚动条与动效偏好。', actions: 1 },
}

function Line({ width = '100%', strong = false }: { width?: string; strong?: boolean }) {
  return <span className={`cf-next-line ${strong ? 'is-strong' : ''}`} style={{ width }} aria-hidden="true" />
}

function ActionShapes({ count = 1 }: { count?: number }) {
  return <div className="cf-next-action-shapes" aria-hidden="true">{Array.from({ length: count }, (_, index) => <span key={index} className={index === count - 1 ? 'is-primary' : ''} />)}</div>
}

function MetricStrip({ count = 4 }: { count?: number }) {
  return <div className="cf-next-metric-strip" style={{ '--metric-count': count } as CSSProperties} aria-hidden="true">{Array.from({ length: count }, (_, index) => <div key={index}><Line width="54%" /><Line width="32%" strong /></div>)}</div>
}

function SkeletonRows({ count = 5, compact = false }: { count?: number; compact?: boolean }) {
  return <div className={`cf-next-rows ${compact ? 'is-compact' : ''}`} aria-hidden="true">{Array.from({ length: count }, (_, index) => <div className="cf-next-row" key={index}><span className="cf-next-row-mark" /><div><Line width={`${64 + (index % 3) * 10}%`} strong={index % 2 === 0} /><Line width={`${38 + (index % 2) * 18}%`} /></div><Line width="54px" /></div>)}</div>
}

function Panel({ className = '', rows = 0, children }: { className?: string; rows?: number; children?: ReactNode }) {
  return <section className={`cf-next-panel ${className}`}><header className="cf-next-panel-head" aria-hidden="true"><div><Line width="92px" strong /><Line width="156px" /></div><span className="cf-next-panel-action" /></header>{children ?? (rows > 0 ? <SkeletonRows count={rows} /> : <div className="cf-next-fill" aria-hidden="true" />)}</section>
}

function PageHeader({ definition }: { definition: PageDefinition }) {
  return <header className="cf-next-page-head"><div className="cf-next-title-group"><h1>{definition.title}</h1><p>{definition.description}</p></div><div className="cf-next-page-head-tools">{definition.metrics ? <MetricStrip count={definition.metrics} /> : null}{definition.actions ? <ActionShapes count={definition.actions} /> : null}</div></header>
}

function OverviewSkeleton() {
  return <div className="cf-next-overview-layout"><Panel className="cf-next-recent-work"><div className="cf-next-feature" aria-hidden="true"><span className="cf-next-feature-icon" /><div><Line width="72%" strong /><Line width="48%" /></div><ActionShapes count={3} /></div><div className="cf-next-feature-meta" aria-hidden="true">{Array.from({ length: 4 }, (_, index) => <div key={index}><Line width="52%" /><Line width="66%" strong /></div>)}</div></Panel><Panel className="cf-next-activity"><div className="cf-next-chart" aria-hidden="true">{Array.from({ length: 7 }, (_, index) => <span key={index} style={{ height: `${34 + ((index * 17) % 58)}%` }} />)}</div></Panel><Panel className="cf-next-todo" rows={4} /><div className="cf-next-overview-side"><Panel className="cf-next-capability" rows={3} /><Panel className="cf-next-run-summary" rows={2} /></div><Panel className="cf-next-resource-dock"><div className="cf-next-dock-items" aria-hidden="true">{Array.from({ length: 3 }, (_, index) => <div key={index}><span /><div><Line width="78%" strong /><Line width="46%" /></div></div>)}</div></Panel></div>
}

function ProjectsSkeleton() {
  return <div className="cf-next-project-layout"><div className="cf-next-project-label"><Line width="120px" strong /></div><div className="cf-next-project-grid">{Array.from({ length: 6 }, (_, index) => <article className="cf-next-project-card" key={index} aria-hidden="true"><header><Line width="46%" strong /><Line width="24%" /></header><Line width="68%" /><div className="cf-next-project-meta">{Array.from({ length: 5 }, (_, metaIndex) => <div key={metaIndex}><Line width="52%" /><Line width="72%" strong /></div>)}</div><footer>{Array.from({ length: 4 }, (_, actionIndex) => <span key={actionIndex} />)}</footer></article>)}</div></div>
}

function DiagnosticsSkeleton() {
  return <div className="cf-next-diagnostics-layout"><Panel className="cf-next-run-list"><div className="cf-next-filter-stack" aria-hidden="true"><Line /><Line width="62%" /></div><SkeletonRows count={9} compact /></Panel><div className="cf-next-diagnostic-detail"><Panel className="cf-next-selected-run"><div className="cf-next-selected-summary" aria-hidden="true"><span className="cf-next-status-shape" /><div><Line width="70%" strong /><Line width="52%" /></div><div className="cf-next-selected-actions"><ActionShapes count={4} /></div></div><div className="cf-next-diagnosis-pair"><div><Line width="82px" strong /><SkeletonRows count={3} compact /></div><div><Line width="96px" strong /><SkeletonRows count={3} compact /></div></div></Panel><div className="cf-next-diagnostic-lower"><Panel rows={6} /><Panel rows={6} /></div><Panel className="cf-next-artifacts"><div className="cf-next-empty-band" aria-hidden="true"><Line width="120px" strong /><Line width="240px" /></div></Panel></div></div>
}

function ResourcesSkeleton() {
  return <div className="cf-next-resources-layout"><div className="cf-next-resource-metrics"><MetricStrip count={4} /></div><Panel className="cf-next-model-connections" rows={4} /><Panel className="cf-next-tool-connections"><div className="cf-next-empty-figure" aria-hidden="true"><span /><Line width="130px" strong /><Line width="210px" /></div></Panel><Panel className="cf-next-runtime" rows={6} /><div className="cf-next-resource-side"><Panel className="cf-next-needs" rows={2} /><Panel className="cf-next-variables" rows={3} /></div></div>
}

function ReleaseSkeleton() {
  return <div className="cf-next-release-layout"><div className="cf-next-release-rail"><Panel rows={6} /><Panel rows={5} /></div><div className="cf-next-release-workspace"><div className="cf-next-steps" aria-hidden="true">{Array.from({ length: 4 }, (_, index) => <span key={index} />)}</div><Panel className="cf-next-preflight"><MetricStrip count={4} /><div className="cf-next-preflight-grid"><SkeletonRows count={6} compact /><SkeletonRows count={3} compact /></div></Panel><Panel className="cf-next-migration"><MetricStrip count={4} /></Panel><div className="cf-next-package-row"><Panel rows={3} /><Panel rows={4} /></div><div className="cf-next-release-actionbar" aria-hidden="true"><div><Line width="180px" strong /><Line width="260px" /></div><ActionShapes count={3} /></div></div></div>
}

function SettingsSkeleton() {
  return <div className="cf-next-settings-layout"><Panel className="cf-next-settings-form"><div className="cf-next-setting-groups" aria-hidden="true">{Array.from({ length: 5 }, (_, index) => <div key={index}><Line width="32%" strong /><span className={index === 0 ? 'is-slider' : 'is-segmented'} /></div>)}</div></Panel><div className="cf-next-settings-preview"><Panel className="cf-next-current-values"><MetricStrip count={5} /></Panel><Panel className="cf-next-preview-surface"><div className="cf-next-preview-document" aria-hidden="true"><div><Line width="34%" /><Line width="58px" /></div><Line width="48%" strong /><Line width="72%" /><SkeletonRows count={5} compact /><ActionShapes count={2} /></div></Panel></div></div>
}

const PAGE_CONTENT: Record<NextPageKind, () => ReactNode> = { overview: OverviewSkeleton, projects: ProjectsSkeleton, diagnostics: DiagnosticsSkeleton, resources: ResourcesSkeleton, release: ReleaseSkeleton, settings: SettingsSkeleton }

export default function NextRedesignPage({ page }: { page: NextPageKind }) {
  if (page === 'overview') return <NextOverviewPage />
  if (page === 'projects') return <NextProjectsPage />
  const Content = PAGE_CONTENT[page]
  return <main className={`cf-next-page cf-next-page-${page}`} data-next-page={page}><PageHeader definition={PAGE_DEFINITIONS[page]} /><div className="cf-next-page-body"><Content /></div></main>
}
