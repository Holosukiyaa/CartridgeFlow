// Studio 根组件：开发者导航 + 可恢复的工作区路由
import { useEffect, useState } from 'react'
import { Navigate, NavLink, Route, Routes, useLocation, useNavigate, useParams } from 'react-router-dom'
import { Activity, ChevronLeft, Database, LayoutDashboard, Package, PackageCheck, Settings, type LucideIcon } from 'lucide-react'
import versionSource from '../../../VERSION?raw'
import { Box, Flex, VStack, Heading, Text, Separator } from './ui.tsx'
import LabPage from './pages/LabPage.tsx'
import HomePage from './pages/HomePage.tsx'
import FlowWorkbench from './pages/FlowWorkbench.tsx'
import ResourceOverviewPage from './pages/ResourceOverviewPage.tsx'
import ReleasePage from './pages/ReleasePage.tsx'
import RunDiagnosticsPage from './pages/RunDiagnosticsPage.tsx'
import SettingsPage from './pages/SettingsPage.tsx'
import NextRedesignPage from './next/NextRedesignPage.tsx'
import type { WorkbenchMode } from './pages/flow-workbench/types.ts'

const STUDIO_VERSION = versionSource.trim().replace(/^CartridgeFlow-/, '') || 'v0.3.0'

type NavItem = { path: string; label: string; desc: string; icon: LucideIcon }

const NAV_GROUPS: { label: string; items: NavItem[] }[] = [
  { label: '工作台', items: [
    { path: '/', label: '全局概览', desc: 'Base Overview', icon: LayoutDashboard },
    { path: '/projects', label: '卡带管理', desc: 'Cartridges', icon: Package },
    { path: '/diagnostics', label: '运行诊断', desc: 'Runs & Recovery', icon: Activity },
  ] },
  { label: '本地资源', items: [
    { path: '/resources', label: '资源中心', desc: 'Resource Center', icon: Database },
  ] },
  { label: '交付', items: [
    { path: '/release', label: '打包发布', desc: 'Package & Release', icon: PackageCheck },
  ] },
]

function projectPath(flowId: string, mode: WorkbenchMode) {
  const workspace = mode === 'run' ? 'test' : mode === 'resources' ? 'resources' : mode === 'assets' ? 'assets' : 'design'
  return `/projects/${encodeURIComponent(flowId)}/${workspace}`
}

function ProjectWorkbenchRoute() {
  const navigate = useNavigate()
  const { flowId = '', workspaceMode = 'design' } = useParams()
  useEffect(() => {
    if (flowId) localStorage.setItem('cf.studio.recent_project', flowId)
  }, [flowId])
  if (!flowId) return <Navigate to="/projects" replace />
  if (!['design', 'assets', 'test', 'resources', 'models'].includes(workspaceMode)) {
    return <Navigate to={projectPath(flowId, 'design')} replace />
  }
  const mode: WorkbenchMode = workspaceMode === 'test' ? 'run' : ['resources', 'models'].includes(workspaceMode) ? 'resources' : workspaceMode === 'assets' ? 'assets' : 'design'
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

function LegacyResourceConfigurationRoute() {
  const { search } = useLocation()
  const params = new URLSearchParams(search)
  params.set('config', '1')
  return <Navigate to={`/resources?${params.toString()}`} replace />
}

export default function App() {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => localStorage.getItem('cf.studio.sidebar') === 'collapsed')
  const location = useLocation()
  const isNextPreview = location.pathname === '/next' || location.pathname.startsWith('/next/')

  const navigationPath = (path: string) => {
    if (!isNextPreview) return path
    return path === '/' ? '/next' : `/next${path}`
  }

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
                <ChevronLeft size={16} strokeWidth={1.8} aria-hidden="true" />
              </button>
            )}
          </Box>
          <Separator />
          <VStack align="stretch" className="cf-nav-stack">
            {NAV_GROUPS.map((group) => (
              <Box className="cf-nav-group" key={group.label}>
                <Text className="cf-sidebar-section-label">{group.label}</Text>
                {group.items.map((item) => {
                  const Icon = item.icon
                  return (
                  <Box className="cf-nav-entry" key={item.path}>
                    <NavLink
                      to={navigationPath(item.path)}
                      end={item.path === '/' || item.path === '/resources'}
                      className={({ isActive }) => `cf-nav-item ${isActive ? 'active' : ''}`}
                    >
                      <Icon className="cf-nav-icon" size={18} strokeWidth={1.7} aria-hidden="true" />
                      <span className="cf-nav-label">{item.label}</span>
                    </NavLink>
                    <Text className="cf-nav-desc">{item.desc}</Text>
                  </Box>
                  )
                })}
              </Box>
            ))}
          </VStack>
          <Box className="cf-sidebar-bottom">
            <NavLink to={navigationPath('/settings')} className={({ isActive }) => `cf-nav-item cf-settings-nav ${isActive ? 'active' : ''}`}>
              <Settings className="cf-nav-icon" size={18} strokeWidth={1.7} aria-hidden="true" />
              <span className="cf-nav-label">其他设置</span>
            </NavLink>
            <Text className="cf-nav-desc">Other Settings</Text>
          </Box>
        </VStack>
      </Box>
      <Box flex={1} minW={0} overflow="auto" className="cf-main">
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/projects" element={<LabPage />} />
          <Route path="/projects/:flowId" element={<ProjectWorkbenchRoute />} />
          <Route path="/projects/:flowId/:workspaceMode" element={<ProjectWorkbenchRoute />} />
          <Route path="/resources" element={<ResourceOverviewPage />} />
          <Route path="/resources/config" element={<LegacyResourceConfigurationRoute />} />
          <Route path="/assets" element={<Navigate to="/resources?config=1" replace />} />
          <Route path="/diagnostics" element={<RunDiagnosticsPage />} />
          <Route path="/models" element={<Navigate to="/resources?config=1&kind=model" replace />} />
          <Route path="/tools" element={<Navigate to="/resources?config=1&kind=tool" replace />} />
          <Route path="/sources" element={<Navigate to="/resources?config=1&kind=tool" replace />} />
          <Route path="/environment" element={<Navigate to="/resources" replace />} />
          <Route path="/release" element={<ReleasePage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/next" element={<NextRedesignPage page="overview" />} />
          <Route path="/next/projects" element={<NextRedesignPage page="projects" />} />
          <Route path="/next/diagnostics" element={<NextRedesignPage page="diagnostics" />} />
          <Route path="/next/resources" element={<NextRedesignPage page="resources" />} />
          <Route path="/next/release" element={<NextRedesignPage page="release" />} />
          <Route path="/next/settings" element={<NextRedesignPage page="settings" />} />
          <Route path="/next/*" element={<Navigate to="/next" replace />} />
          <Route path="/preview/*" element={<Navigate to="/" replace />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Box>
    </Flex>
  )
}
