// App 根组件：侧边栏导航 + 主内容区
import { useState } from 'react'
import { Box, Flex, VStack, Button, Heading, Text, Separator } from './ui.tsx'
import ShelfPage from './pages/ShelfPage.tsx'
import LabPage from './pages/LabPage.tsx'
import LlmPage from './pages/LlmPage.tsx'

type NavView = 'shelf' | 'lab' | 'llm'

const NAV_ITEMS: { key: NavView; label: string; desc: string }[] = [
  { key: 'shelf', label: '卡带货架', desc: 'Shelf' },
  { key: 'lab', label: 'Flow 实验室', desc: 'Lab' },
  { key: 'llm', label: 'LLM 设置', desc: 'LLM' },
]

export default function App() {
  const [view, setView] = useState<NavView>('shelf')
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)

  return (
    <Flex minH="100vh" className={`cf-app-shell ${sidebarCollapsed ? 'sidebar-collapsed' : ''}`}>
      <Box minH="100vh" className="cf-sidebar" flexShrink={0}>
        <VStack align="stretch" gap={0} h="100%">
          <Box className="cf-logo-wrap">
            <Box className="cf-logo-mark">CF</Box>
            <Box className="cf-logo-text">
              <Heading className="cf-logo-title">CARTRIDGEFLOW</Heading>
              <Text className="cf-logo-subtitle">v0.0.0-pre</Text>
            </Box>
            <Button
              className="cf-sidebar-toggle"
              onClick={() => setSidebarCollapsed((value) => !value)}
            >
              {sidebarCollapsed ? '›' : '‹'}
            </Button>
          </Box>
          <Separator />
          <Text className="cf-sidebar-section-label">Modules</Text>
          <VStack align="stretch" className="cf-nav-stack">
            {NAV_ITEMS.map((item) => (
              <Box key={item.key}>
                <Button
                  className={`cf-nav-item ${view === item.key ? 'active' : ''}`}
                  onClick={() => setView(item.key)}
                >
                  <span className="cf-nav-label">{item.label}</span>
                  <span className="cf-nav-short">{item.desc.slice(0, 1)}</span>
                </Button>
                <Text className="cf-nav-desc">{item.desc}</Text>
              </Box>
            ))}
          </VStack>
        </VStack>
      </Box>
      <Box flex={1} minW={0} overflow="auto" className="cf-main">
        {view === 'shelf' && <ShelfPage />}
        {view === 'lab' && <LabPage />}
        {view === 'llm' && <LlmPage />}
      </Box>
    </Flex>
  )
}
