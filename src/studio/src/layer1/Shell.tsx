import { Bot, ChevronDown, Moon, Pencil, Plus, Settings, Sun, Trash2 } from 'lucide-react'
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
  section,
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
  section?: string
}) {
  return <header className="topbar">
    <strong className="brand-name">{copy.brand}</strong>
    <span className="brand-slash">/</span>
    <button type="button" className="project-name" title={projectName} onClick={onToggleProjectMenu}>
      {projectName}
      <ChevronDown size={13} />
    </button>
    {section ? <>
      <span className="brand-slash">/</span>
      <span className="topbar-section">{section}</span>
    </> : null}
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
  reviewFilter,
  onFilterReview,
}: {
  guidance: Guidance
  stats: ReviewCounts | null
  narrow?: boolean
  onAction: () => void
  reviewFilter?: ReviewState | ''
  onFilterReview?: (state: ReviewState | '') => void
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
      {(['confirmed', 'review', 'unresolved'] as ReviewState[]).map((state) => <button type="button" key={state} className={cx(state === 'confirmed' ? 'is-ok' : state === 'review' ? 'is-review' : 'is-gap', reviewFilter === state && 'is-on')} onClick={() => onFilterReview?.(reviewFilter === state ? '' : state)}>
        {statusCopy(state)} <b>{stats[state]}</b>
      </button>)}
    </div> : null}
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
  onNew,
  onRename,
  onDelete,
}: {
  projectId: string
  projects: Array<{ project_id: string; name: string; revision: number }>
  onNew: () => void
  onRename: (name: string) => void
  onDelete: (name: string) => void
}) {
  return <div className="project-menu">
    {projects.map((project) => <a className={project.project_id === projectId ? 'is-current' : ''} href={`/projects/${encodeURIComponent(project.project_id)}/studio`} key={project.project_id}>
      <span>{shortProjectName(project.name)}</span>
      <small>v{project.revision}</small>
    </a>)}
    <div className="dialog-foot">
      <Button variant="ghost" onClick={onNew}><Plus size={13} />{copy.newProject}</Button>
      {projects.some((project) => project.project_id === projectId) ? <>
        <Button variant="icon" aria-label={copy.renameProject} title={copy.renameProject} onClick={() => onRename(projects.find((project) => project.project_id === projectId)?.name || '')}><Pencil size={13} /></Button>
        <Button variant="icon" aria-label={copy.deleteProject} title={copy.deleteProject} onClick={() => onDelete(projects.find((project) => project.project_id === projectId)?.name || '')}><Trash2 size={13} /></Button>
      </> : null}
    </div>
  </div>
}

function shortProjectName(name: string) {
  const compact = name.trim()
  return compact.length > 16 ? `${compact.slice(0, 16)}…` : compact
}
