import { useState } from 'react'
import { DEFAULT_APPEARANCE, loadAppearance, saveAppearance, type AppearanceSettings, type DensityMode, type FontFamilyMode, type FontWeightMode, type ScrollbarMode } from '../appearance.ts'

const FONT_MODES: { value: FontFamilyMode; label: string; sample: string }[] = [
  { value: 'system', label: '系统默认', sample: '跟随当前系统的界面字体' },
  { value: 'classic', label: '经典', sample: '带有印刷感的复古字形' },
  { value: 'developer', label: '现代精密', sample: '清晰、克制的现代无衬线界面' },
]

export default function SettingsPage() {
  const [settings, setSettings] = useState<AppearanceSettings>(() => loadAppearance())

  function update(patch: Partial<AppearanceSettings>) {
    setSettings((current) => saveAppearance({ ...current, ...patch }))
  }

  function reset() {
    setSettings(saveAppearance({ ...DEFAULT_APPEARANCE }))
  }

  return (
    <div className="cf-resource-page cf-settings-page">
      <header className="cf-resource-heading">
        <div><span className="cf-resource-kicker">STUDIO / OTHER SETTINGS</span><h1>其他设置</h1><p>界面偏好与工作台可读性，不参与模型、工具或运行环境配置。</p></div>
        <button type="button" className="cf-settings-reset" onClick={reset}>恢复默认</button>
      </header>
      <div className="cf-settings-layout">
        <section className="cf-settings-controls">
          <div className="cf-resource-panel-head"><div><span>TYPOGRAPHY</span><h2>字体与可读性</h2></div><b>{settings.fontScale}%</b></div>
          <label className="cf-settings-range"><span><strong>全局字体大小</strong><small>导航、页面标题、正文与表单控件</small></span><input type="range" min="90" max="115" step="5" value={settings.fontScale} onChange={(event) => update({ fontScale: Number(event.target.value) })} /><output>{settings.fontScale}%</output></label>
          <div className="cf-settings-group"><span>字体风格</span><div className="cf-settings-options">{FONT_MODES.map((mode) => <button type="button" key={mode.value} className={settings.fontFamily === mode.value ? 'active' : ''} onClick={() => update({ fontFamily: mode.value })}><strong>{mode.label}</strong><small>{mode.sample}</small></button>)}</div></div>
          <div className="cf-settings-group cf-settings-weight"><span>界面字重</span><div className="cf-settings-segment" role="group" aria-label="界面字重">{(['regular', 'strong'] as FontWeightMode[]).map((mode) => <button type="button" key={mode} className={settings.fontWeight === mode ? 'active' : ''} onClick={() => update({ fontWeight: mode })}>{mode === 'regular' ? '标准' : '加粗'}</button>)}</div><small>加粗会增强正文、说明文字和控件的清晰度，不改变标题层级。</small></div>
          <div className="cf-settings-group"><span>界面密度</span><div className="cf-settings-segment" role="group" aria-label="界面密度">{(['comfortable', 'compact'] as DensityMode[]).map((mode) => <button type="button" key={mode} className={settings.density === mode ? 'active' : ''} onClick={() => update({ density: mode })}>{mode === 'comfortable' ? '舒展' : '紧凑'}</button>)}</div></div>
          <div className="cf-settings-group"><span>滚动条显示</span><div className="cf-settings-segment" role="group" aria-label="滚动条显示">{(['subtle', 'always'] as ScrollbarMode[]).map((mode) => <button type="button" key={mode} className={settings.scrollbarMode === mode ? 'active' : ''} onClick={() => update({ scrollbarMode: mode })}>{mode === 'subtle' ? '悬停显示' : '始终显示'}</button>)}</div></div>
          <label className="cf-settings-toggle"><input type="checkbox" checked={settings.reducedMotion} onChange={(event) => update({ reducedMotion: event.target.checked })} /><span><strong>减少动效</strong><small>关闭非必要的过渡和入场动画</small></span></label>
        </section>
        <section className="cf-settings-preview">
          <div className="cf-resource-panel-head"><div><span>LIVE PREVIEW</span><h2>实时预览</h2></div><small>自动保存</small></div>
          <div className="cf-settings-preview-surface"><span>CartridgeFlow / Developer Studio</span><h2>专属服务开发工作台</h2><p>模型、工具和运行底座统一在资源配置中管理；这里仅调整工作台外观与可读性。</p><div><code>Resources / Other Settings</code><b>配置自动保存</b></div><button type="button">示例操作</button></div>
          <dl className="cf-settings-facts"><div><dt>保存范围</dt><dd>当前浏览器</dd></div><div><dt>字体比例</dt><dd>{settings.fontScale}%</dd></div><div><dt>界面字重</dt><dd>{settings.fontWeight === 'strong' ? '加粗' : '标准'}</dd></div><div><dt>密度</dt><dd>{settings.density === 'comfortable' ? '舒展' : '紧凑'}</dd></div><div><dt>滚动条</dt><dd>{settings.scrollbarMode === 'subtle' ? '悬停显示' : '始终显示'}</dd></div><div><dt>动效</dt><dd>{settings.reducedMotion ? '已减少' : '标准'}</dd></div></dl>
        </section>
      </div>
    </div>
  )
}
