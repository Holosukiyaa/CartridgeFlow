export type FontFamilyMode = 'system' | 'classic' | 'developer'
export type FontWeightMode = 'regular' | 'strong'
export type DensityMode = 'comfortable' | 'compact'
export type ScrollbarMode = 'subtle' | 'always'

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

function normalizeAppearance(value: Partial<AppearanceSettings>): AppearanceSettings {
  const fontScaleValue = value.fontScale ?? DEFAULT_APPEARANCE.fontScale
  const fontScale = Math.min(115, Math.max(90, Math.round(Number(fontScaleValue) / 5) * 5))
  const fontFamily: FontFamilyMode = ['system', 'classic', 'developer'].includes(String(value.fontFamily)) ? value.fontFamily as FontFamilyMode : DEFAULT_APPEARANCE.fontFamily
  const fontWeight: FontWeightMode = ['regular', 'strong'].includes(String(value.fontWeight)) ? value.fontWeight as FontWeightMode : DEFAULT_APPEARANCE.fontWeight
  const density: DensityMode = ['comfortable', 'compact'].includes(String(value.density)) ? value.density as DensityMode : DEFAULT_APPEARANCE.density
  const scrollbarMode: ScrollbarMode = ['subtle', 'always'].includes(String(value.scrollbarMode)) ? value.scrollbarMode as ScrollbarMode : DEFAULT_APPEARANCE.scrollbarMode
  return { fontScale, fontFamily, fontWeight, density, reducedMotion: Boolean(value.reducedMotion), scrollbarMode }
}
