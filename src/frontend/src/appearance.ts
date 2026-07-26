export type FontFamilyMode = 'system' | 'classic' | 'developer'
export type FontWeightMode = 'regular' | 'strong'
export type DensityMode = 'comfortable' | 'compact'
export type ScrollbarMode = 'subtle' | 'always'
export type WorkspaceThemeId = 'orange' | 'gray' | 'teal' | 'plum' | 'custom'

export type WorkspaceTheme = {
  id: WorkspaceThemeId
  color: string
}

export type AppearanceSettings = {
  fontScale: number
  fontFamily: FontFamilyMode
  fontWeight: FontWeightMode
  density: DensityMode
  reducedMotion: boolean
  scrollbarMode: ScrollbarMode
}

export const DEFAULT_APPEARANCE: AppearanceSettings = {
  fontScale: 110,
  fontFamily: 'developer',
  fontWeight: 'strong',
  density: 'comfortable',
  reducedMotion: false,
  scrollbarMode: 'subtle',
}

const STORAGE_KEY = 'cf.studio.appearance'
const WORKSPACE_THEME_STORAGE_KEY = 'cf.lite.workspace-theme'

// Workspace theme palette and default are maintained together in this block.
export const WORKSPACE_THEME_PRESETS: Array<{ id: Exclude<WorkspaceThemeId, 'custom'>; label: string; color: string }> = [
  { id: 'orange', label: '橙色', color: '#e26f35' },
  { id: 'gray', label: '灰色', color: '#919191' },
  { id: 'teal', label: '青绿', color: '#16836e' },
  { id: 'plum', label: '紫红', color: '#a33d73' },
]

export const DEFAULT_WORKSPACE_THEME: WorkspaceTheme = {
  id: 'teal',
  color: WORKSPACE_THEME_PRESETS.find((theme) => theme.id === 'teal')!.color,
}

export function loadAppearance(): AppearanceSettings {
  try {
    const raw = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}')
    return normalizeAppearance(raw)
  } catch {
    return { ...DEFAULT_APPEARANCE }
  }
}

export function saveAppearance(settings: AppearanceSettings) {
  const normalized = normalizeAppearance(settings)
  localStorage.setItem(STORAGE_KEY, JSON.stringify(normalized))
  applyAppearance(normalized)
  window.dispatchEvent(new CustomEvent('cf:appearance', { detail: normalized }))
  return normalized
}

export function applyAppearance(settings: AppearanceSettings) {
  const root = document.documentElement
  root.style.setProperty('--cf-user-font-scale', String(settings.fontScale / 100))
  root.dataset.cfFontScale = String(settings.fontScale)
  root.dataset.cfFontFamily = settings.fontFamily
  root.dataset.cfFontWeight = settings.fontWeight
  root.dataset.cfDensity = settings.density
  root.dataset.cfReducedMotion = settings.reducedMotion ? 'true' : 'false'
  root.dataset.cfScrollbarMode = settings.scrollbarMode
}

export function loadWorkspaceTheme(): WorkspaceTheme {
  try {
    const value = JSON.parse(localStorage.getItem(WORKSPACE_THEME_STORAGE_KEY) || '{}')
    if (!value?.id) return { ...DEFAULT_WORKSPACE_THEME }
    return normalizeWorkspaceTheme(value)
  } catch {
    return { ...DEFAULT_WORKSPACE_THEME }
  }
}

export function saveWorkspaceTheme(theme: WorkspaceTheme) {
  const normalized = normalizeWorkspaceTheme(theme)
  localStorage.setItem(WORKSPACE_THEME_STORAGE_KEY, JSON.stringify(normalized))
  applyWorkspaceTheme(normalized)
  window.dispatchEvent(new CustomEvent('cf:workspace-theme', { detail: normalized }))
  return normalized
}

export function applyWorkspaceTheme(theme: WorkspaceTheme) {
  const normalized = normalizeWorkspaceTheme(theme)
  const rgb = hexToRgb(normalized.color)
  const root = document.documentElement
  root.style.setProperty('--accent', normalized.color)
  root.style.setProperty('--accent-dark', mixRgb(rgb, [28, 34, 42], .28))
  root.style.setProperty('--accent-soft', mixRgb(rgb, [255, 255, 255], .9))
  root.style.setProperty('--cf-accent-rgb', rgb.join(' '))
  root.dataset.cfWorkspaceTheme = normalized.id
}

function normalizeWorkspaceTheme(value: Partial<WorkspaceTheme>): WorkspaceTheme {
  const color = normalizeHexColor(value.color)
  const preset = WORKSPACE_THEME_PRESETS.find((item) => item.id === value.id && item.color.toLowerCase() === color)
  return { id: preset?.id || 'custom', color }
}

function normalizeHexColor(value: unknown) {
  const candidate = String(value || '').trim()
  if (/^#[0-9a-fA-F]{6}$/.test(candidate)) return candidate.toLowerCase()
  return DEFAULT_WORKSPACE_THEME.color
}

function hexToRgb(color: string): [number, number, number] {
  return [
    Number.parseInt(color.slice(1, 3), 16),
    Number.parseInt(color.slice(3, 5), 16),
    Number.parseInt(color.slice(5, 7), 16),
  ]
}

function mixRgb(source: [number, number, number], target: [number, number, number], targetWeight: number) {
  return `rgb(${source.map((value, index) => Math.round(value * (1 - targetWeight) + target[index] * targetWeight)).join(', ')})`
}

function normalizeAppearance(value: Partial<AppearanceSettings>): AppearanceSettings {
  const fontScaleValue = value.fontScale ?? DEFAULT_APPEARANCE.fontScale
  const fontScale = Math.min(115, Math.max(90, Math.round(Number(fontScaleValue) / 5) * 5))
  const fontFamily: FontFamilyMode = ['system', 'classic', 'developer'].includes(String(value.fontFamily)) ? value.fontFamily as FontFamilyMode : DEFAULT_APPEARANCE.fontFamily
  const fontWeight: FontWeightMode = ['regular', 'strong'].includes(String(value.fontWeight)) ? value.fontWeight as FontWeightMode : DEFAULT_APPEARANCE.fontWeight
  const density: DensityMode = ['comfortable', 'compact'].includes(String(value.density)) ? value.density as DensityMode : DEFAULT_APPEARANCE.density
  const scrollbarMode: ScrollbarMode = ['subtle', 'always'].includes(String(value.scrollbarMode)) ? value.scrollbarMode as ScrollbarMode : DEFAULT_APPEARANCE.scrollbarMode
  return { fontScale, fontFamily, fontWeight, density, reducedMotion: Boolean(value.reducedMotion), scrollbarMode }
}
