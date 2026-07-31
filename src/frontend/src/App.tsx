import { useCallback, useEffect, useState } from 'react'
import { Box, Button, Spinner, Text } from './ui.tsx'
import { fetchLabFlows, type FlowLabItem } from './api.ts'
import FlowWorkbench from './pages/FlowWorkbench.tsx'
import CartridgeWorkspaceControl from './pages/flow-workbench/CartridgeWorkspaceControl.tsx'

const RECENT_CARTRIDGE_STORAGE_KEY = 'cartridgeflow.recent-cartridge'

function cartridgePath(flowId: string) {
  return `/cartridges/${encodeURIComponent(flowId)}/design`
}

type Navigate = (path: string, options?: { replace?: boolean }) => void

function Redirect({ to, navigate }: { to: string; navigate: Navigate }) {
  useEffect(() => navigate(to, { replace: true }), [navigate, to])
  return null
}

function CartridgeWorkbenchRoute({ flowId, workspaceMode, navigate }: {
  flowId: string
  workspaceMode: string
  navigate: Navigate
}) {

  useEffect(() => {
    if (flowId) localStorage.setItem(RECENT_CARTRIDGE_STORAGE_KEY, flowId)
  }, [flowId])

  if (!flowId) return <Redirect to="/" navigate={navigate} />
  if (workspaceMode !== 'design') return <Redirect to={cartridgePath(flowId)} navigate={navigate} />

  return (
    <FlowWorkbench
      flowId={flowId}
      onSwitchFlow={(nextFlowId) => navigate(nextFlowId ? cartridgePath(nextFlowId) : '/', { replace: !nextFlowId })}
    />
  )
}

function WorkbenchEntryRoute({ navigate }: { navigate: Navigate }) {
  const [items, setItems] = useState<FlowLabItem[] | null>(null)
  const [error, setError] = useState('')

  const load = () => {
    setItems(null)
    setError('')
    fetchLabFlows()
      .then((data) => setItems(data.items || []))
      .catch((loadError) => setError(loadError.message || '无法读取本机卡带'))
  }

  useEffect(load, [])

  if (error) {
    return <Box className="cf-workbench-entry-state"><Text color="fg.error">{error}</Text><Button className="cf-outline-btn" onClick={load}>重新加载</Button></Box>
  }
  if (items === null) return <Box className="cf-workbench-entry-state"><Spinner /></Box>
  if (items.length === 0) {
    return <CartridgeWorkspaceControl empty onSwitchFlow={(flowId) => { if (flowId) navigate(cartridgePath(flowId)) }} />
  }

  const recentId = localStorage.getItem(RECENT_CARTRIDGE_STORAGE_KEY)
  const target = items.find((item) => item.id === recentId) || items.find((item) => item.editable) || items[0]
  return <Redirect to={cartridgePath(target.id)} navigate={navigate} />
}

export default function App() {
  const [pathname, setPathname] = useState(() => window.location.pathname)
  const navigate = useCallback<Navigate>((path, options) => {
    if (options?.replace) window.history.replaceState(null, '', path)
    else window.history.pushState(null, '', path)
    setPathname(window.location.pathname)
  }, [])

  useEffect(() => {
    const onPopState = () => setPathname(window.location.pathname)
    window.addEventListener('popstate', onPopState)
    return () => window.removeEventListener('popstate', onPopState)
  }, [])

  let segments: string[] = []
  try {
    segments = pathname.split('/').filter(Boolean).map((segment) => decodeURIComponent(segment))
  } catch {
    segments = []
  }

  let route: React.ReactNode
  if (segments.length === 0 || (segments.length === 1 && segments[0] === 'cartridges')) {
    route = <WorkbenchEntryRoute navigate={navigate} />
  } else if (segments[0] === 'cartridges' && segments.length >= 2 && segments.length <= 3) {
    route = <CartridgeWorkbenchRoute flowId={segments[1]} workspaceMode={segments[2] || 'design'} navigate={navigate} />
  } else if (segments[0] === 'projects' && segments.length >= 2 && segments.length <= 3) {
    route = <Redirect to={cartridgePath(segments[1])} navigate={navigate} />
  } else {
    route = <Redirect to="/" navigate={navigate} />
  }

  return (
    <Box minH="100vh" className="cf-workbench-shell">
      <main className="cf-main cf-workbench-main">
        {route}
      </main>
    </Box>
  )
}
