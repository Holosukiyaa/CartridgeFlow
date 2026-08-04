import { useMemo } from 'react'
import { CreatorStudio } from './pages/flow-workbench/CreatorStudio.tsx'

const PROJECT_KEY = 'cartridgeflow.creator-project'

function projectIdFromLocation() {
  const parts = window.location.pathname.split('/').filter(Boolean)
  if (parts[0] === 'projects' && parts[1]) return decodeURIComponent(parts[1])
  if (parts[0] === 'cartridges' && parts[1]) return decodeURIComponent(parts[1])
  const recent = localStorage.getItem(PROJECT_KEY)
  return recent || `project.${crypto.randomUUID()}`
}

export default function App() {
  const projectId = useMemo(projectIdFromLocation, [])
  localStorage.setItem(PROJECT_KEY, projectId)
  const canonicalPath = `/projects/${encodeURIComponent(projectId)}/creator`
  if (window.location.pathname !== canonicalPath) window.history.replaceState(null, '', canonicalPath)
  return <CreatorStudio projectId={projectId} />
}
