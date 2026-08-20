import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'

export type ThemeId = 'light' | 'dark'

const THEME_KEY = 'cartridgeflow.studio.theme'
const ThemeContext = createContext<{ theme: ThemeId; setTheme: (theme: ThemeId) => void; toggleTheme: () => void } | null>(null)

function readTheme(): ThemeId {
  try {
    const saved = localStorage.getItem(THEME_KEY)
    if (saved === 'dark' || saved === 'light') return saved
  } catch {
    // Keep the readable default when storage is unavailable.
  }
  return 'light'
}

function applyTheme(theme: ThemeId) {
  document.documentElement.dataset.theme = theme
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<ThemeId>(readTheme)

  useEffect(() => {
    applyTheme(theme)
    localStorage.setItem(THEME_KEY, theme)
  }, [theme])

  const value = useMemo(() => ({
    theme,
    setTheme: setThemeState,
    toggleTheme: () => setThemeState((current) => current === 'light' ? 'dark' : 'light'),
  }), [theme])

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
}

export function useTheme() {
  const value = useContext(ThemeContext)
  if (!value) throw new Error('useTheme must be used inside ThemeProvider')
  return value
}
