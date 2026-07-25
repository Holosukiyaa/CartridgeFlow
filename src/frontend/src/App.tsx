import { useEffect, useState } from 'react'
import { Navigate, Route, Routes, useNavigate, useParams } from 'react-router-dom'
import { Box, Button, Spinner, Text } from './ui.tsx'
import { fetchLabFlows, type FlowLabItem } from './api.ts'
import FlowWorkbench from './pages/FlowWorkbench.tsx'
import CartridgeWorkspaceControl from './pages/flow-workbench/CartridgeWorkspaceControl.tsx'

function cartridgePath(flowId: string) {
  return `/cartridges/${encodeURIComponent(flowId)}/design`
}

function CartridgeWorkbenchRoute() {
  const navigate = useNavigate()
  const { flowId = '', workspaceMode = 'design' } = useParams()

  useEffect(() => {
    if (flowId) localStorage.setItem('cf.lite.recent_cartridge', flowId)
  }, [flowId])

  if (!flowId) return <Navigate to="/" replace />
  if (workspaceMode !== 'design') return <Navigate to={cartridgePath(flowId)} replace />

  return (
    <FlowWorkbench
      flowId={flowId}
      onSwitchFlow={(nextFlowId) => navigate(nextFlowId ? cartridgePath(nextFlowId) : '/', { replace: !nextFlowId })}
    />
  )
}

function WorkbenchEntryRoute() {
  const navigate = useNavigate()
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

  const recentId = localStorage.getItem('cf.lite.recent_cartridge')
  const target = items.find((item) => item.id === recentId) || items.find((item) => item.editable) || items[0]
  return <Navigate to={cartridgePath(target.id)} replace />
}

function LegacyWorkbenchRedirect() {
  const { flowId = '' } = useParams()
  if (!flowId) return <Navigate to="/" replace />
  return <Navigate to={cartridgePath(flowId)} replace />
}

export default function App() {
  return (
    <Box minH="100vh" className="cf-lite-shell">
      <main className="cf-main cf-lite-main">
        <Routes>
          <Route path="/" element={<WorkbenchEntryRoute />} />
          <Route path="/cartridges" element={<WorkbenchEntryRoute />} />
          <Route path="/cartridges/:flowId" element={<CartridgeWorkbenchRoute />} />
          <Route path="/cartridges/:flowId/:workspaceMode" element={<CartridgeWorkbenchRoute />} />
          <Route path="/projects" element={<Navigate to="/" replace />} />
          <Route path="/projects/:flowId" element={<LegacyWorkbenchRedirect />} />
          <Route path="/projects/:flowId/:workspaceMode" element={<LegacyWorkbenchRedirect />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </Box>
  )
}
