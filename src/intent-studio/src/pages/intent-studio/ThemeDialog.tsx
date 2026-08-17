import { Palette } from 'lucide-react'
import { APP_THEME_PRESETS, Button, Dialog, Field, type AppThemePreset } from '../../ui/index.ts'

export function ThemeDialog({ opened, theme, onChange, onClose }: {
  opened: boolean
  theme: AppThemePreset
  onChange: (theme: AppThemePreset) => void
  onClose: () => void
}) {
  const update = (key: keyof Pick<AppThemePreset, 'accent' | 'focus' | 'page'>, value: string) => {
    onChange({ ...theme, id: 'custom', label: '自定义主题', [key]: value })
  }

  return <Dialog opened={opened} onClose={onClose} title="调整全局视觉" aria-label="全局视觉主题">
    <div className="theme-dialog-content">
      <Field.Select
        label="主题预设"
        leftSection={<Palette size={16} />}
        value={theme.id}
        data={[{ value: 'custom', label: '自定义主题' }, ...APP_THEME_PRESETS.map((preset) => ({ value: preset.id, label: preset.label }))]}
        onChange={(value) => {
          const preset = APP_THEME_PRESETS.find((item) => item.id === value)
          if (preset) onChange(preset)
        }}
      />
      <div className="theme-dialog-colors">
        <Field.Color label="控件颜色" value={theme.accent} onChange={(value) => update('accent', value)} />
        <Field.Color label="焦点颜色" value={theme.focus} onChange={(value) => update('focus', value)} />
        <Field.Color label="背景颜色" value={theme.page} onChange={(value) => update('page', value)} />
      </div>
      <p>主题会应用到当前创作空间，并自动保存在本机。</p>
      <div className="dialog-actions"><Button onClick={onClose}>完成</Button></div>
    </div>
  </Dialog>
}
