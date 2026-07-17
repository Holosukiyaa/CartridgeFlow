// ui.tsx — 纯 HTML 薄封装，替代 Chakra UI，保持相同组件名和 Props
import React, { type ReactNode, type CSSProperties, type ChangeEvent } from 'react'

// ── 工具类型 ──
type WithChildren = { children?: ReactNode }
type WithClass = { className?: string; style?: CSSProperties }

// ── Box ──
export function Box({ children, className, style, p, m, w, h, minH, maxH, overflow, flex, flexShrink, minW, borderColor, bg, mt, mb, ml, mr, display, whiteSpace, fontSize, position }: WithChildren & WithClass & {
  p?: number | string; m?: number | string; w?: string; h?: string; minH?: string; maxH?: string
  overflow?: string; flex?: number | string; flexShrink?: number; minW?: number | string
  borderColor?: string; bg?: string; mt?: number | string; mb?: number | string
  ml?: number | string; mr?: number | string; display?: string; whiteSpace?: string
  fontSize?: string; position?: CSSProperties['position']
}) {
  const s: CSSProperties = { ...style }
  if (p !== undefined) s.padding = typeof p === 'number' ? `${p * 4}px` : p
  if (m !== undefined) s.margin = typeof m === 'number' ? `${m * 4}px` : m
  if (w) s.width = w; if (h) s.height = h
  if (minH) s.minHeight = minH; if (maxH) s.maxHeight = maxH
  if (overflow) s.overflow = overflow
  if (flex !== undefined) s.flex = flex
  if (flexShrink !== undefined) s.flexShrink = flexShrink
  if (minW) s.minWidth = typeof minW === 'number' ? `${minW}px` : minW
  if (borderColor) s.borderColor = borderColor
  if (bg) s.background = bg
  if (mt !== undefined) s.marginTop = typeof mt === 'number' ? `${mt * 4}px` : mt
  if (mb !== undefined) s.marginBottom = typeof mb === 'number' ? `${mb * 4}px` : mb
  if (ml !== undefined) s.marginLeft = typeof ml === 'number' ? `${ml * 4}px` : ml
  if (mr !== undefined) s.marginRight = typeof mr === 'number' ? `${mr * 4}px` : mr
  if (display) s.display = display
  if (whiteSpace) s.whiteSpace = whiteSpace
  if (fontSize) s.fontSize = fontSize
  if (position) s.position = position
  return <div className={className} style={s}>{children}</div>
}

// ── Flex ──
export function Flex({ children, className, style, ...rest }: WithChildren & WithClass & { minH?: string; w?: string; flexShrink?: number }) {
  return <Box className={className} style={{ display: 'flex', ...style }} {...rest}>{children}</Box>
}

// ── VStack ──
export function VStack({ children, className, align, gap, mb, mt, h, maxH, overflow }: WithChildren & WithClass & { align?: string; gap?: number | string; mb?: number | string; mt?: number | string; h?: string; maxH?: string; overflow?: string }) {
  const s: CSSProperties = { display: 'flex', flexDirection: 'column' }
  if (align === 'stretch') s.alignItems = 'stretch'
  else if (align === 'start') s.alignItems = 'flex-start'
  else if (align === 'center') s.alignItems = 'center'
  if (gap !== undefined) s.gap = typeof gap === 'number' ? `${gap * 4}px` : gap
  if (mb !== undefined) s.marginBottom = typeof mb === 'number' ? `${mb * 4}px` : mb
  if (mt !== undefined) s.marginTop = typeof mt === 'number' ? `${mt * 4}px` : mt
  if (h) s.height = h
  if (maxH) s.maxHeight = maxH
  if (overflow) s.overflow = overflow
  return <div className={className} style={s}>{children}</div>
}

// ── HStack ──
export function HStack({ children, className, justify, gap, flexWrap, mb, mt, align, p }: WithChildren & WithClass & { justify?: string; gap?: number | string; flexWrap?: string; mb?: number | string; mt?: number | string; align?: string; p?: number | string }) {
  const s: CSSProperties = { display: 'flex', flexDirection: 'row', alignItems: 'center' }
  if (justify === 'space-between') s.justifyContent = 'space-between'
  else if (justify) s.justifyContent = justify
  if (gap !== undefined) s.gap = typeof gap === 'number' ? `${gap * 4}px` : gap
  if (flexWrap === 'wrap') s.flexWrap = 'wrap'
  if (mb !== undefined) s.marginBottom = typeof mb === 'number' ? `${mb * 4}px` : mb
  if (mt !== undefined) s.marginTop = typeof mt === 'number' ? `${mt * 4}px` : mt
  if (align === 'start') s.alignItems = 'flex-start'
  else if (align === 'end') s.alignItems = 'flex-end'
  else if (align === 'center') s.alignItems = 'center'
  if (p !== undefined) s.padding = typeof p === 'number' ? `${p * 4}px` : p
  return <div className={className} style={s}>{children}</div>
}

// ── Grid ──
export function Grid({ children, templateColumns, gap, className, style }: WithChildren & WithClass & { templateColumns?: string; gap?: number | string }) {
  const s: CSSProperties = { display: 'grid', ...style }
  if (templateColumns) s.gridTemplateColumns = templateColumns
  if (gap !== undefined) s.gap = typeof gap === 'number' ? `${gap * 4}px` : gap
  return <div className={className} style={s}>{children}</div>
}

// ── SimpleGrid ──
export function SimpleGrid({ children, columns, gap, className, mb }: WithChildren & WithClass & { columns?: number; gap?: number | string; mb?: number | string }) {
  const cols = columns || 1
  const s: CSSProperties = { display: 'grid', gridTemplateColumns: `repeat(${cols}, 1fr)` }
  if (gap !== undefined) s.gap = typeof gap === 'number' ? `${gap * 4}px` : gap
  if (mb !== undefined) s.marginBottom = typeof mb === 'number' ? `${mb * 4}px` : mb
  return <div className={className} style={s}>{children}</div>
}

// ── Heading ──
export function Heading({ children, size, className, mb, mt, color }: WithChildren & WithClass & { size?: string; mb?: number | string; mt?: number | string; color?: string }) {
  const Tag = size === 'sm' ? 'h4' : size === 'md' ? 'h3' : 'h2'
  const s: CSSProperties = {}
  if (mb !== undefined) s.marginBottom = typeof mb === 'number' ? `${mb * 4}px` : mb
  if (mt !== undefined) s.marginTop = typeof mt === 'number' ? `${mt * 4}px` : mt
  if (color) s.color = color
  return React.createElement(Tag, { className, style: s }, children)
}

// ── Text ──
export function Text({ children, className, fontSize, fontWeight, color, mb, mt, ml, mr, minH, style }: WithChildren & WithClass & {
  fontSize?: string; fontWeight?: string; color?: string
  mb?: number | string; mt?: number | string; ml?: number | string; mr?: number | string; minH?: string
}) {
  const s: CSSProperties = { ...style }
  if (fontSize) s.fontSize = fontSize
  if (fontWeight) s.fontWeight = fontWeight
  if (color) { s.color = color; if (color === 'fg.muted') s.color = 'var(--cf-text-dim)'; if (color === 'fg.error') s.color = 'var(--cf-red)'; if (color === 'fg.success') s.color = 'var(--cf-green)' }
  if (mb !== undefined) s.marginBottom = typeof mb === 'number' ? `${mb * 4}px` : mb
  if (mt !== undefined) s.marginTop = typeof mt === 'number' ? `${mt * 4}px` : mt
  if (ml !== undefined) s.marginLeft = typeof ml === 'number' ? `${ml * 4}px` : ml
  if (mr !== undefined) s.marginRight = typeof mr === 'number' ? `${mr * 4}px` : mr
  if (minH) s.minHeight = minH
  return <p className={className} style={s}>{children}</p>
}

// ── Button ──
export function Button({ children, className, onClick, w, loading, loadingText, mt, disabled, style }: WithChildren & WithClass & {
  onClick?: () => void
  w?: string; loading?: boolean; loadingText?: string; mt?: number | string; disabled?: boolean
}) {
  const btnClass = `cf-btn-reset ${className || ''}`
  const width = w === '100%' ? '100%' : w
  const s: CSSProperties = { ...style }
  if (width) s.width = width
  if (mt !== undefined) s.marginTop = typeof mt === 'number' ? `${mt * 4}px` : mt
  return (
    <button className={btnClass} style={s} onClick={onClick} disabled={disabled || loading}>
      {loading ? (loadingText || '...') : children}
    </button>
  )
}

// ── Badge ──
export function Badge({ children, className }: WithChildren & WithClass) {
  return <span className={`${className || ''} cf-badge-reset`}>{children}</span>
}

// ── Spinner ──
export function Spinner({ size: _size, color: _color }: { size?: string; color?: string }) {
  return <span className="cf-spinner" />
}

// ── Input ──
export function Input({ value, onChange, placeholder, className, style }: WithClass & { value?: string; onChange?: (e: ChangeEvent<HTMLInputElement>) => void; placeholder?: string }) {
  return <input type="text" value={value || ''} onChange={onChange} placeholder={placeholder} className={`cf-input ${className || ''}`} style={style} />
}

// ── Textarea ──
export function Textarea({ value, onChange, rows, fontFamily, fontSize, placeholder, className }: WithClass & {
  value?: string; onChange?: (e: ChangeEvent<HTMLTextAreaElement>) => void
  rows?: number; fontFamily?: string; fontSize?: string; placeholder?: string
}) {
  const s: CSSProperties = {}
  if (fontFamily === 'mono') s.fontFamily = 'var(--cf-mono)'
  if (fontSize) s.fontSize = fontSize
  return <textarea value={value || ''} onChange={onChange} rows={rows} placeholder={placeholder} className={`cf-input ${className || ''}`} style={s} />
}

// ── NativeSelect ──
export const NativeSelect = {
  Root: ({ children }: WithChildren) => <>{children}</>,
  Field: ({ value, onChange, children, className }: WithChildren & WithClass & { value?: string; onChange?: (e: ChangeEvent<HTMLSelectElement>) => void }) => (
    <select value={value} onChange={onChange} className={`cf-select ${className || ''}`}>{children}</select>
  ),
}

// ── Field ──
export const Field = {
  Root: ({ children }: WithChildren) => <div className="cf-field">{children}</div>,
  Label: ({ children }: WithChildren) => <label className="cf-field-label">{children}</label>,
}

// ── Separator ──
export function Separator({ borderColor: _bc, mb }: { borderColor?: string; mb?: number | string }) {
  const s: CSSProperties = { border: 'none', borderTop: '1px solid var(--cf-border)', margin: 0 }
  if (mb !== undefined) s.marginBottom = typeof mb === 'number' ? `${mb * 4}px` : mb
  return <hr style={s} />
}

// ── Card ──
export const Card = {
  Root: ({ children, className, borderColor }: WithChildren & WithClass & { borderColor?: string }) => (
    <div className={className} style={borderColor ? { borderColor } : undefined}>{children}</div>
  ),
  Body: ({ children, p }: WithChildren & { p?: number | string }) => {
    const s: CSSProperties = p !== undefined ? { padding: typeof p === 'number' ? `${p * 4}px` : p } : {}
    return <div style={s}>{children}</div>
  },
  Footer: ({ children, p, pt }: WithChildren & { p?: number | string; pt?: number | string }) => {
    const s: CSSProperties = {}
    if (p !== undefined) s.padding = typeof p === 'number' ? `${p * 4}px` : p
    if (pt !== undefined) s.paddingTop = typeof pt === 'number' ? `${pt * 4}px` : pt
    if (p === undefined && pt === undefined) s.padding = '16px'
    return <div style={s}>{children}</div>
  },
}

// ── Code ──
export function Code({ children, display, whiteSpace, fontSize, p, bg, mt, className }: WithChildren & WithClass & {
  display?: string; whiteSpace?: string; fontSize?: string; p?: number | string; bg?: string; mt?: number | string
}) {
  const s: CSSProperties = {}
  if (display) s.display = display
  if (whiteSpace) s.whiteSpace = whiteSpace
  if (fontSize) s.fontSize = fontSize
  if (p !== undefined) s.padding = typeof p === 'number' ? `${p * 4}px` : p
  if (bg) s.background = bg
  if (mt !== undefined) s.marginTop = typeof mt === 'number' ? `${mt * 4}px` : mt
  return <code className={className} style={s}>{children}</code>
}

// ── Link ──
export function Link({ children, href, className }: WithChildren & WithClass & { href?: string }) {
  return <a href={href} className={className}>{children}</a>
}

// ── Tabs ──
export function Tabs({ children, value, className }: WithChildren & WithClass & { value?: string }) {
  return <div className={`cf-tabs ${className || ''}`} data-value={value}>{children}</div>
}
Tabs.Root = Tabs
Tabs.List = ({ children }: WithChildren) => <div className="cf-tabs-list">{children}</div>
Tabs.Trigger = ({ children, value, onClick }: WithChildren & { value: string; onClick?: () => void }) => (
  <button className={`cf-tab-trigger`} data-tab={value} onClick={onClick}>{children}</button>
)
Tabs.Content = ({ children, value, style }: WithChildren & { value: string; style?: CSSProperties }) => (
  <div className="cf-tab-content" data-tab={value} style={style}>{children}</div>
)
// Wrapper that manages active tab state internally
export function TabsRoot({ value, onValueChange, children }: { value: string; onValueChange: (e: { value: string }) => void; children: ReactNode }) {
  return (
    <div className="cf-tabs" data-value={value}>
      {React.Children.map(children, (child) => {
        if (!React.isValidElement(child)) return child
        // Pass onChange to TabTrigger clicks
        const childProps: any = {}
        if (child.type === TabsList) {
          childProps.children = React.Children.map((child.props as any).children, (tab: any) => {
            if (!React.isValidElement(tab) || tab.type !== TabsTrigger) return tab
            const tabValue = (tab.props as any).value
            const isActive = tabValue === value
            return React.cloneElement(tab as React.ReactElement<any>, {
              onClick: () => onValueChange({ value: tabValue }),
              'data-active': isActive ? 'true' : 'false',
            })
          })
          return React.cloneElement(child as React.ReactElement<any>, childProps)
        }
        if (child.type === TabsContent) {
          const contentValue = (child.props as any).value
          if (contentValue !== value) return null
        }
        return child
      })}
    </div>
  )
}

// Re-export for composite usage
export const TabsList = Tabs.List
export const TabsTrigger = Tabs.Trigger
export const TabsContent = Tabs.Content

// ── Collapsible ──
export function Collapsible({ children, open, className }: WithChildren & WithClass & { open?: boolean }) {
  return <div className={`cf-collapsible ${className || ''}`} data-open={open ? 'true' : 'false'}>{children}</div>
}
Collapsible.Root = Collapsible
Collapsible.Content = ({ children }: WithChildren) => <div className="cf-collapsible-content">{children}</div>

// ── Checkbox ──
export function Checkbox({ children, checked, onCheckedChange, className }: WithChildren & WithClass & { checked?: boolean; onCheckedChange?: (e: { checked: boolean }) => void }) {
  const id = React.useId()
  return (
    <label className={`cf-checkbox ${className || ''}`}>
      <input type="checkbox" id={id} checked={checked} onChange={(e) => onCheckedChange?.({ checked: e.target.checked })} />
      <span className="cf-checkbox-label">{children}</span>
    </label>
  )
}
Checkbox.Root = Checkbox
Checkbox.HiddenInput = () => null
Checkbox.Control = () => null
Checkbox.Label = ({ children }: WithChildren) => <>{children}</>
