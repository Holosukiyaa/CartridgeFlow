import { useEffect, useState } from 'react'
import { listCreatorProjects } from './api/client.ts'
import { copy } from './copy.ts'
import { projectStudioPath, createDraftProjectId, readRecentProjectId, rememberProjectId } from './layer1/persistence.ts'
import { WorkspaceApp } from './layer1/WorkspaceApp.tsx'
import { Button, ThemeProvider } from './ui/index.ts'

function projectIdFromLocation() {
  const parts = window.location.pathname.split('/').filter(Boolean)
  if (parts[0] === 'projects' && parts[1]) return decodeURIComponent(parts[1])
  const params = new URLSearchParams(window.location.search)
  return params.get('projectId') || ''
}

export default function App() {
  const locationProjectId = projectIdFromLocation()
  const [projectId, setProjectId] = useState(locationProjectId)
  const [loadingProjects, setLoadingProjects] = useState(!projectId)
  const [projectLoadError, setProjectLoadError] = useState('')
  const isCapabilities = window.location.pathname.startsWith('/capabilities')
  const capabilitiesBackPath = locationProjectId ? projectStudioPath(locationProjectId) : '/studio'

  useEffect(() => {
    if (projectId) {
      rememberProjectId(projectId)
      if (!isCapabilities) {
        const next = `${projectStudioPath(projectId)}${window.location.search}${window.location.hash}`
        if (`${window.location.pathname}${window.location.search}${window.location.hash}` !== next) {
          window.history.replaceState(null, '', next)
        }
      }
      return
    }
    if (isCapabilities) {
      setLoadingProjects(false)
      return
    }
    let active = true
    listCreatorProjects()
      .then(({ projects }) => {
        if (!active || !projects.length) return
        const recent = readRecentProjectId()
        const next = projects.find((project) => project.project_id === recent)?.project_id || projects[0].project_id
        setProjectId(next)
      })
      .catch(() => { if (active) setProjectLoadError(copy.projectListFail) })
      .finally(() => { if (active) setLoadingProjects(false) })
    return () => { active = false }
  }, [isCapabilities, projectId])

  const createProject = () => {
    const next = createDraftProjectId()
    rememberProjectId(next)
    window.history.pushState(null, '', projectStudioPath(next))
    setProjectId(next)
  }

  return <ThemeProvider>
    {isCapabilities ? <CapabilitiesPlaceholder backPath={capabilitiesBackPath} /> : projectId ? <WorkspaceApp projectId={projectId} /> : <ProjectHub loading={loadingProjects} error={projectLoadError} onCreate={createProject} />}
  </ThemeProvider>
}

function CapabilitiesPlaceholder({ backPath }: { backPath: string }) {
  return <main className="workspace">
    <header className="topbar"><strong className="brand-name">{copy.brand}</strong></header>
    <div className="overlay">
      <section className="dialog" role="status" aria-label="能力工坊">
        <header><div><h2>能力工坊</h2><p>能力工坊还不是独立产品，缺口步骤请从方案里打开第二层.</p></div></header>
        <div className="dialog-foot"><span /> <Button onClick={() => window.location.assign(backPath)}>返回方案</Button></div>
      </section>
    </div>
  </main>
}

function ProjectHub({ loading, error, onCreate }: { loading: boolean; error: string; onCreate: () => void }) {
  return <main className="workspace">
    <header className="topbar"><strong className="brand-name">{copy.brand}</strong></header>
    {loading ? <div className="loading">{copy.loadingProjects}</div> : <div className="overlay">
      <section className="dialog" role="dialog" aria-label={copy.projectEmptyTitle}>
        <header><div><h2>{copy.projectEmptyTitle}</h2><p>{error || copy.projectEmptyHint}</p></div></header>
        <form onSubmit={(event) => { event.preventDefault(); onCreate() }}>
          <div className="dialog-foot"><span /> <Button type="submit">{copy.newProject}</Button></div>
        </form>
      </section>
    </div>}
  </main>
}
