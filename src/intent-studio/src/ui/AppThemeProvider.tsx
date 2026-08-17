import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { createTheme, MantineProvider, type MantineColorsTuple } from '@mantine/core'
import { Notifications } from '@mantine/notifications'

export type AppThemePreset = {
  id: string
  label: string
  accent: string
  focus: string
  page: string
}

export const APP_THEME_PRESETS: AppThemePreset[] = [
  { id: 'light-reference', label: '浅色主题', accent: '#0b5bd3', focus: '#0b5bd3', page: '#eef2f6' },
  { id: 'quiet-workbench', label: '静定工作台', accent: '#426b9b', focus: '#3f6ea8', page: '#f2f4f5' },
  { id: 'clear-sky', label: '清透蓝', accent: '#176bff', focus: '#2563eb', page: '#f8fbff' },
  { id: 'morning-mist', label: '晨雾青', accent: '#087f82', focus: '#0f9da0', page: '#f7faf9' },
  { id: 'paper-ink', label: '纸张墨', accent: '#3c5360', focus: '#4f7180', page: '#faf9f6' },
  { id: 'quiet-forest', label: '静谧林', accent: '#3f725d', focus: '#5d9b7d', page: '#f5f8f5' },
]

const APP_THEME_KEY = 'cartridgeflow.creator-theme'

function readTheme(): AppThemePreset {
  try {
    const saved = JSON.parse(localStorage.getItem(APP_THEME_KEY) || 'null') as Partial<AppThemePreset> | null
    if (saved?.id && saved.accent && saved.focus && saved.page) {
      return { ...APP_THEME_PRESETS[0], ...saved }
    }
  } catch {
    // Use the bundled accessible default when local preferences are malformed.
  }
  return APP_THEME_PRESETS[0]
}

type AppThemeContextValue = {
  theme: AppThemePreset
  setTheme: (theme: AppThemePreset) => void
}

const AppThemeContext = createContext<AppThemeContextValue | null>(null)

function colorScale(theme: AppThemePreset): MantineColorsTuple {
  return [
    `color-mix(in srgb, ${theme.accent} 5%, ${theme.page})`,
    `color-mix(in srgb, ${theme.accent} 9%, ${theme.page})`,
    `color-mix(in srgb, ${theme.accent} 16%, ${theme.page})`,
    `color-mix(in srgb, ${theme.accent} 28%, ${theme.page})`,
    `color-mix(in srgb, ${theme.accent} 46%, ${theme.page})`,
    `color-mix(in srgb, ${theme.accent} 70%, ${theme.page})`,
    theme.accent,
    `color-mix(in srgb, ${theme.accent} 84%, #152033)`,
    `color-mix(in srgb, ${theme.accent} 70%, #152033)`,
    `color-mix(in srgb, ${theme.accent} 58%, #152033)`,
  ]
}

export function AppThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<AppThemePreset>(readTheme)
  const mantineTheme = useMemo(() => createTheme({
    primaryColor: 'brand',
    primaryShade: 6,
    colors: { brand: colorScale(theme) },
    fontFamily: '"Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI Variable Text", "Segoe UI", sans-serif',
    headings: { fontFamily: 'inherit' },
    defaultRadius: 6,
    focusRing: 'auto',
    cursorType: 'pointer',
    components: {
      Button: { defaultProps: { size: 'sm' } },
      ActionIcon: { defaultProps: { size: 36, variant: 'default' } },
      TextInput: { defaultProps: { size: 'sm' } },
      Textarea: { defaultProps: { size: 'sm' } },
      Select: { defaultProps: { size: 'sm' } },
      Modal: { defaultProps: { radius: 6, centered: true } },
    },
  }), [theme])

  const setTheme = (next: AppThemePreset) => {
    localStorage.setItem(APP_THEME_KEY, JSON.stringify(next))
    setThemeState(next)
  }

  useEffect(() => {
    const root = document.documentElement
    const variables = {
      '--intent-accent': theme.accent,
      '--intent-accent-dark': `color-mix(in srgb, ${theme.accent} 78%, #152033)`,
      '--intent-accent-soft': `color-mix(in srgb, ${theme.accent} 12%, ${theme.page})`,
      '--intent-focus': theme.focus,
      '--intent-focus-ring': `color-mix(in srgb, ${theme.focus} 24%, transparent)`,
      '--intent-page': theme.page,
      '--intent-surface-muted': `color-mix(in srgb, ${theme.page} 66%, #ffffff)`,
    }
    for (const [name, value] of Object.entries(variables)) root.style.setProperty(name, value)
  }, [theme])

  return <AppThemeContext.Provider value={{ theme, setTheme }}>
    <MantineProvider theme={mantineTheme} cssVariablesSelector=":root">
      <Notifications position="top-right" limit={4} />
      {children}
    </MantineProvider>
  </AppThemeContext.Provider>
}

export function useAppTheme() {
  const value = useContext(AppThemeContext)
  if (!value) throw new Error('useAppTheme must be used inside AppThemeProvider')
  return value
}
