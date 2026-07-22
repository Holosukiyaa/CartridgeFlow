// Studio 根组件：开发者导航 + 可恢复的工作区路由
import { useEffect, useState } from 'react'
import { Navigate, NavLink, Route, Routes, useNavigate, useParams } from 'react-router-dom'
import versionSource from '../../../VERSION?raw'
import { Box, Flex, VStack, Heading, Text, Separator } from './ui.tsx'
import LabPage from './pages/LabPage.tsx'
import HomePage from './pages/HomePage.tsx'
import FlowWorkbench from './pages/FlowWorkbench.tsx'
import ModelConfigPage from './pages/ModelConfigPage.tsx'
import ResourceConfigPage from './pages/ResourceConfigPage.tsx'
import ReleasePage from './pages/ReleasePage.tsx'
import RunDiagnosticsPage from './pages/RunDiagnosticsPage.tsx'
import SettingsPage from './pages/SettingsPage.tsx'
import type { WorkbenchMode } from './pages/flow-workbench/types.ts'

const STUDIO_VERSION = versionSource.trim().replace(/^CartridgeFlow-/, '') || 'v0.3.0'

const NAV_GROUPS = [
  { label: '工作台', items: [
    { path: '/', label: '全局概览', desc: 'Base Overview', short: '总' },
    { path: '/projects', label: 'Flow管理', desc: 'Flows', short: '流' },
    { path: '/diagnostics', label: '运行诊断', desc: 'Runs & Recovery', short: '诊' },
  ] },
  { label: '本地资源', items: [
    { path: '/models', label: '模型配置', desc: 'Local Models', short: '模' },
    { path: '/tools', label: '工具配置', desc: 'Tools & APIs', short: '工' },
  ] },
  { label: '交付', items: [
    { path: '/release', label: '打包发布', desc: 'Package & Release', short: '发' },
  ] },
]

function projectPath(flowId: string, mode: WorkbenchMode) {
  const workspace = mode === 'run' ? 'test' : mode === 'models' ? 'models' : mode === 'assets' ? 'assets' : 'design'
  return `/projects/${encodeURIComponent(flowId)}/${workspace}`
}

function ProjectWorkbenchRoute() {
  const navigate = useNavigate()
  const { flowId = '', workspaceMode = 'design' } = useParams()
  useEffect(() => {
    if (flowId) localStorage.setItem('cf.studio.recent_project', flowId)
  }, [flowId])
  if (!flowId) return <Navigate to="/projects" replace />
  if (!['design', 'assets', 'test', 'models'].includes(workspaceMode)) {
    return <Navigate to={projectPath(flowId, 'design')} replace />
  }
  const mode: WorkbenchMode = workspaceMode === 'test' ? 'run' : workspaceMode === 'models' ? 'models' : workspaceMode === 'assets' ? 'assets' : 'design'
  return (
    <FlowWorkbench
      flowId={flowId}
      mode={mode}
      onBack={() => navigate('/projects')}
      onModeChange={(nextMode) => navigate(projectPath(flowId, nextMode))}
      onSwitchFlow={(nextFlowId) => navigate(projectPath(nextFlowId, mode))}
    />
  )
}

export default function App() {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => localStorage.getItem('cf.studio.sidebar') === 'collapsed')

  useEffect(() => {
    localStorage.setItem('cf.studio.sidebar', sidebarCollapsed ? 'collapsed' : 'expanded')
  }, [sidebarCollapsed])

  return (
    <Flex minH="100vh" className={`cf-app-shell ${sidebarCollapsed ? 'sidebar-collapsed' : ''}`}>
      <Box minH="100vh" className="cf-sidebar" flexShrink={0}>
        <VStack align="stretch" gap={0} h="100%">
          <Box className="cf-logo-wrap">
            {sidebarCollapsed ? (
              <button
                type="button"
                className="cf-logo-mark cf-logo-expand"
                onClick={() => setSidebarCollapsed(false)}
                aria-label="展开侧栏"
                title="展开侧栏"
              >
                CF
              </button>
            ) : (
              <Box className="cf-logo-mark">CF</Box>
            )}
            <Box className="cf-logo-text">
              <Heading className="cf-logo-title">CARTRIDGEFLOW</Heading>
              <Text className="cf-logo-subtitle">Studio {STUDIO_VERSION}</Text>
            </Box>
            {!sidebarCollapsed && (
              <button
                type="button"
                className="cf-sidebar-toggle"
                onClick={() => setSidebarCollapsed(true)}
                aria-label="收起侧栏"
                title="收起侧栏"
              >
                ←
              </button>
            )}
          </Box>
          <Separator />
          <VStack align="stretch" className="cf-nav-stack">
            {NAV_GROUPS.map((group) => (
              <Box className="cf-nav-group" key={group.label}>
                <Text className="cf-sidebar-section-label">{group.label}</Text>
                {group.items.map((item) => (
                  <Box className="cf-nav-entry" key={item.path}>
                    <NavLink
                      to={item.path}
                      end={item.path === '/'}
                      className={({ isActive }) => `cf-nav-item ${isActive ? 'active' : ''}`}
                    >
                      <span className="cf-nav-label">{item.label}</span>
                      <span className="cf-nav-short">{item.short}</span>
                    </NavLink>
                    <Text className="cf-nav-desc">{item.desc}</Text>
                  </Box>
                ))}
              </Box>
            ))}
          </VStack>
          <Box className="cf-sidebar-bottom">
            <NavLink to="/settings" className={({ isActive }) => `cf-nav-item cf-settings-nav ${isActive ? 'active' : ''}`}>
              <span className="cf-nav-label">系统设置</span>
              <span className="cf-nav-short">设</span>
            </NavLink>
            <Text className="cf-nav-desc">Preferences</Text>
          </Box>
        </VStack>
      </Box>
      <Box flex={1} minW={0} overflow="auto" className="cf-main">
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/projects" element={<LabPage />} />
          <Route path="/projects/:flowId" element={<ProjectWorkbenchRoute />} />
          <Route path="/projects/:flowId/:workspaceMode" element={<ProjectWorkbenchRoute />} />
          <Route path="/diagnostics" element={<RunDiagnosticsPage />} />
          <Route path="/models" element={<ModelConfigPage />} />
          <Route path="/tools" element={<ResourceConfigPage />} />
          <Route path="/sources" element={<Navigate to="/tools" replace />} />
          <Route path="/environment" element={<Navigate to="/settings?section=environment" replace />} />
          <Route path="/release" element={<ReleasePage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/preview/*" element={<Navigate to="/" replace />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Box>
    </Flex>
  )
}
