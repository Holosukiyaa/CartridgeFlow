import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App.tsx'
import { AppThemeProvider } from './ui/index.ts'
import '@mantine/core/styles.css'
import '@mantine/notifications/styles.css'
import 'allotment/dist/style.css'
import './index.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <AppThemeProvider>
      <App />
    </AppThemeProvider>
  </StrictMode>,
)
