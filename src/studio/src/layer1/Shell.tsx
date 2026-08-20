import { Bot, ChevronDown, Moon, Settings, Sun } from 'lucide-react'
import type { ReactNode } from 'react'
import { SHELL_TABS, type ShellTabId } from '../config.ts'
import { copy } from '../copy.ts'
import { Button, cx, useTheme } from '../ui/index.ts'
import { statusCopy, type Guidance, type ReviewCounts, type ReviewState } from './model.ts'

export function Shell({
  narrow,
  header,
  next,
  tabs,
  children,
}: {
  narrow: boolean
  header: ReactNode
  next: ReactNode
  tabs?: ReactNode
  children: ReactNode
}) {
  return <main className={cx('workspace', narrow && 'is-narrow')}>
    {header}
    {next}
    {narrow ? tabs : null}
    {children}
  </main>
}

export function WorkspaceHeader({
  projectName,
  projectMenu,
  syncLabel,
  connected,
  connectionLabel,
  onConnect,
  onOpenSettings,
  onToggleSteward,
  stewardOn,
  onToggleProjectMenu,
}: {
  projectName: string
  projectMenu: ReactNode
  syncLabel: string
  connected: boolean
  connectionLabel: string
  onConnect: () => void
  onOpenSettings: () => void
  onToggleSteward?: () => void
  stewardOn?: boolean
  onToggleProjectMenu: () => void
}) {
  return <header className="topbar">
    <strong className="brand-name">{copy.brand}</strong>
    <span className="brand-slash">/</span>
    <button type="button" className="project-name" title={projectName} onClick={onToggleProjectMenu}>
      {projectName}
      <ChevronDown size={13} />
    </button>
    {projectMenu}
    <span className="topbar-spacer" />
    <div className="topbar-meta">
      <span>{syncLabel}</span>
      <Button variant="icon" aria-label={copy.settings} title={copy.settings} onClick={onOpenSettings}><Settings size={14} /></Button>
      {onToggleSteward ? <button type="button" className="btn-steward" aria-label={copy.toggleSteward} onClick={onToggleSteward}>
        <Bot size={11} />
        {copy.steward}
        {stewardOn ? <i className="dot" /> : null}
      </button> : null}
      <ThemeToggle />
      <button type="button" className={cx('connection', connected && 'is-on')} onClick={onConnect}>
        <b />
        {connectionLabel}
      </button>
    </div>
  </header>
}

export function NextBar({
  guidance,
  stats,
  narrow,
  onAction,
  onToggleSteward,
  onTrialRun,
}: {
  guidance: Guidance
  stats: ReviewCounts | null
  stewardOn?: boolean
  narrow?: boolean
  onAction: () => void
  onToggleSteward?: () => void
  onTrialRun?: () => void
}) {
  const chip = guidance.stage === 'complete-step' ? guidance.title.replace(/^补齐「/, '').replace(/」$/, '') : ''
  return <div className="nextbar">
    <span className="next-kicker">下一步</span>
    <span className="next-chevron" aria-hidden="true">›</span>
    <div className="nextbar-main">
      {stats ? <>
        <span className="next-title">{guidance.stage === 'complete-step' && chip ? '补齐' : guidance.title}</span>
        {chip ? <span className="next-chip">{narrow ? `「${chip}」` : chip}</span> : null}
      </> : <span className="next-title">{guidance.title}</span>}
    </div>
    {stats ? <div className="next-stats" aria-label="审核状态统计">
      {(['confirmed', 'review', 'unresolved'] as ReviewState[]).map((state) => <span key={state} className={state === 'confirmed' ? 'is-ok' : state === 'review' ? 'is-review' : 'is-gap'}>
        {statusCopy(state)} <b>{stats[state]}</b>
      </span>)}
    </div> : null}
    {onToggleSteward ? <>
      <span className="next-split" />
      <button type="button" className="btn-next-steward" onClick={onToggleSteward}><Bot size={10} />{copy.steward}</button>
    </> : null}
    {onTrialRun ? <Button variant="ghost" onClick={onTrialRun}>{copy.trialRun}</Button> : null}
    {guidance.showAction ? <Button onClick={onAction}>{guidance.actionLabel}</Button> : null}
  </div>
}

export function NarrowTabs({ tab, onTab }: { tab: ShellTabId; onTab: (tab: ShellTabId) => void }) {
  return <nav className="narrow-tabs" aria-label="工作台面板">
    {SHELL_TABS.map((item) => <button key={item.id} type="button" className={tab === item.id ? 'is-on' : ''} onClick={() => onTab(item.id)}>{item.label}</button>)}
  </nav>
}

function ThemeToggle() {
  const { theme, toggleTheme } = useTheme()
  const next = theme === 'light' ? copy.themeDark : copy.themeLight
  return <Button variant="icon" aria-label={copy.toggleTheme} title={next} onClick={toggleTheme}>
    {theme === 'light' ? <Moon size={14} /> : <Sun size={14} />}
  </Button>
}

export function ProjectMenu({
  projectId,
  projects,
}: {
  projectId: string
  projects: Array<{ project_id: string; name: string; revision: number }>
}) {
  return <div className="project-menu">
    {projects.map((project) => <a className={project.project_id === projectId ? 'is-current' : ''} href={`/projects/${encodeURIComponent(project.project_id)}/studio`} key={project.project_id}>
      <span>{project.name}</span>
      <small>v{project.revision}</small>
    </a>)}
  </div>
}