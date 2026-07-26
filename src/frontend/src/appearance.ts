export type FontFamilyMode = 'system' | 'classic' | 'developer'
export type FontWeightMode = 'regular' | 'strong'
export type DensityMode = 'comfortable' | 'compact'
export type ScrollbarMode = 'subtle' | 'always'
export type WorkspaceThemeId = 'orange' | 'blue' | 'teal' | 'plum' | 'custom'

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

export const WORKSPACE_THEME_PRESETS: Array<{ id: Exclude<WorkspaceThemeId, 'custom'>; label: string; color: string }> = [
  { id: 'orange', label: '橙色', color: '#e26f35' },
  { id: 'blue', label: '蓝色', color: '#3974c5' },
  { id: 'teal', label: '青绿', color: '#16836e' },
  { id: 'plum', label: '紫红', color: '#8560a8' },
]

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
    if (!value?.id) return { id: 'orange', color: WORKSPACE_THEME_PRESETS[0].color }
    const color = normalizeHexColor(value?.color)
    const preset = WORKSPACE_THEME_PRESETS.find((item) => item.id === value?.id && item.color.toLowerCase() === color.toLowerCase())
    return { id: preset?.id || 'custom', color }
  } catch {
    return { id: 'orange', color: WORKSPACE_THEME_PRESETS[0].color }
  }
}

export function saveWorkspaceTheme(theme: WorkspaceTheme) {
  const normalized = { id: theme.id, color: normalizeHexColor(theme.color) }
  localStorage.setItem(WORKSPACE_THEME_STORAGE_KEY, JSON.stringify(normalized))
  applyWorkspaceTheme(normalized)
  window.dispatchEvent(new CustomEvent('cf:workspace-theme', { detail: normalized }))
  return normalized
}

export function applyWorkspaceTheme(theme: WorkspaceTheme) {
  const color = normalizeHexColor(theme.color)
  const rgb = hexToRgb(color)
  const root = document.documentElement
  root.style.setProperty('--accent', color)
  root.style.setProperty('--accent-dark', mixRgb(rgb, [28, 34, 42], .28))
  root.style.setProperty('--accent-soft', mixRgb(rgb, [255, 255, 255], .9))
  root.style.setProperty('--cf-accent-rgb', rgb.join(' '))
  root.dataset.cfWorkspaceTheme = theme.id
}

function normalizeHexColor(value: unknown) {
  const candidate = String(value || '').trim()
  if (/^#[0-9a-fA-F]{6}$/.test(candidate)) return candidate.toLowerCase()
  return WORKSPACE_THEME_PRESETS[0].color
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
