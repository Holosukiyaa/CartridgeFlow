// 应用入口：纯 React + CSS，不依赖 Chakra
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App.tsx'
import { ToastProvider } from './toast.tsx'
import { applyAppearance, applyWorkspaceTheme, loadAppearance, loadWorkspaceTheme } from './appearance.ts'
import './index.css'

applyAppearance(loadAppearance())
applyWorkspaceTheme(loadWorkspaceTheme())

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ToastProvider>
      <App />
    </ToastProvider>
  </StrictMode>,
)
