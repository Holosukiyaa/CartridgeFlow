import { useMemo } from 'react'
import { ThemeProvider } from './ui/index.ts'
import { WorkspaceApp } from './layer1/WorkspaceApp.tsx'

const PROJECT_KEY = 'cartridgeflow.studio-project'

function projectIdFromLocation() {
  const parts = window.location.pathname.split('/').filter(Boolean)
  if (parts[0] === 'projects' && parts[1]) return decodeURIComponent(parts[1])
  const params = new URLSearchParams(window.location.search)
  if (params.get('projectId')) return params.get('projectId') as string
  const recent = localStorage.getItem(PROJECT_KEY)
  return recent || `project.${crypto.randomUUID()}`
}

export default function App() {
  const projectId = useMemo(projectIdFromLocation, [])
  localStorage.setItem(PROJECT_KEY, projectId)
  const isCapabilities = window.location.pathname.startsWith('/capabilities')
  const canonicalPath = isCapabilities
    ? '/capabilities'
    : `/projects/${encodeURIComponent(projectId)}/studio`
  const query = window.location.search
  const next = `${canonicalPath}${query}${window.location.hash}`
  if (`${window.location.pathname}${window.location.search}${window.location.hash}` !== next && !isCapabilities) {
    window.history.replaceState(null, '', next)
  }
  return <ThemeProvider><WorkspaceApp projectId={projectId} /></ThemeProvider>
}
