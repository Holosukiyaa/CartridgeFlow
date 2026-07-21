export type FontFamilyMode = 'system' | 'classic' | 'developer'
export type DensityMode = 'comfortable' | 'compact'

export type AppearanceSettings = {
  fontScale: number
  fontFamily: FontFamilyMode
  density: DensityMode
  reducedMotion: boolean
}

export const DEFAULT_APPEARANCE: AppearanceSettings = {
  fontScale: 100,
  fontFamily: 'system',
  density: 'comfortable',
  reducedMotion: false,
}

const STORAGE_KEY = 'cf.studio.appearance'

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
  root.dataset.cfFontFamily = settings.fontFamily
  root.dataset.cfDensity = settings.density
  root.dataset.cfReducedMotion = settings.reducedMotion ? 'true' : 'false'
}

function normalizeAppearance(value: Partial<AppearanceSettings>): AppearanceSettings {
  const fontScale = Math.min(115, Math.max(90, Math.round(Number(value.fontScale || 100) / 5) * 5))
  const fontFamily: FontFamilyMode = ['system', 'classic', 'developer'].includes(String(value.fontFamily)) ? value.fontFamily as FontFamilyMode : 'system'
  const density: DensityMode = value.density === 'compact' ? 'compact' : 'comfortable'
  return { fontScale, fontFamily, density, reducedMotion: Boolean(value.reducedMotion) }
}
