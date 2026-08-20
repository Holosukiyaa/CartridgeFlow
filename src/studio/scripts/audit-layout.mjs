import { mkdirSync, writeFileSync } from 'node:fs'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
import { chromium } from '@playwright/test'

const args = process.argv.slice(2)
const after = args.includes('--after')
const url = args.find((item) => item.startsWith('http')) || 'http://127.0.0.1:5173/projects/project.1ec8b174-01cf-4fc5-bc57-ac9867516497/studio?visual=frame1'
const out = resolve(dirname(fileURLToPath(import.meta.url)), after ? '../.data/ui-layout-audit/after' : '../.data/ui-layout-audit')
mkdirSync(out, { recursive: true })
const viewports = [{ width: 1672, height: 940, label: '1672x940' }, { width: 1530, height: 766, label: '1530x766' }]
const selectors = ['.workspace', '.topbar', '.nextbar', '.steward', '.canvas-region', '.detail', '.pack-corner']

const browser = await chromium.launch({ headless: true })
const page = await browser.newPage({ deviceScaleFactor: 1 })
const reports = []

const inspectExpression = (sels) => `(() => {
  const selectors = ${JSON.stringify(sels)}
  const root = document.documentElement
  const visible = (node) => {
    const style = getComputedStyle(node)
    const rect = node.getBoundingClientRect()
    return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0
  }
  const inspect = (selector) => {
    const node = document.querySelector(selector)
    if (!node) return { selector, missing: true }
    const rect = node.getBoundingClientRect()
    const style = getComputedStyle(node)
    const descendants = [...node.querySelectorAll('*')].filter(visible)
    const textNodes = descendants.filter((item) => item.textContent.trim() && !['svg', 'path'].includes(item.tagName.toLowerCase()))
    const fontSizes = textNodes.map((item) => Number.parseFloat(getComputedStyle(item).fontSize)).filter(Number.isFinite)
    const controls = descendants.filter((item) => item.matches('button,a,input,select,textarea,[role="button"]')).map((item) => {
      const itemRect = item.getBoundingClientRect()
      return { tag: item.tagName.toLowerCase(), text: item.textContent.trim().slice(0, 50), width: Math.round(itemRect.width), height: Math.round(itemRect.height), fontSize: Number.parseFloat(getComputedStyle(item).fontSize) }
    })
    const unexpectedOverflow = descendants.filter((item) => {
      const itemStyle = getComputedStyle(item)
      const overflowX = item.scrollWidth > item.clientWidth + 2
      const overflowY = item.scrollHeight > item.clientHeight + 2
      const scrollX = ['auto', 'scroll'].includes(itemStyle.overflowX)
      const scrollY = ['auto', 'scroll'].includes(itemStyle.overflowY)
      const ellipsis = itemStyle.textOverflow === 'ellipsis' && itemStyle.overflowX === 'hidden'
      const lineClamp = itemStyle.webkitLineClamp && itemStyle.webkitLineClamp !== 'none'
      return (overflowX && !scrollX && !ellipsis) || (overflowY && !scrollY && !lineClamp)
    }).map((item) => ({ className: String(item.className || '').slice(0, 80), client: [item.clientWidth, item.clientHeight], scroll: [item.scrollWidth, item.scrollHeight] })).slice(0, 20)
    const smallText = textNodes.filter((item) => Number.parseFloat(getComputedStyle(item).fontSize) < 12).map((item) => ({ text: item.textContent.trim().slice(0, 40), fontSize: Number.parseFloat(getComputedStyle(item).fontSize), className: String(item.className || '').slice(0, 60) })).slice(0, 30)
    const smallControls = controls.filter((item) => item.height > 0 && item.height < 36)
    return {
      selector,
      rect: { x: rect.x, y: rect.y, width: rect.width, height: rect.height },
      client: [node.clientWidth, node.clientHeight],
      scroll: [node.scrollWidth, node.scrollHeight],
      padding: [style.paddingTop, style.paddingRight, style.paddingBottom, style.paddingLeft],
      minFontSize: fontSizes.length ? Math.min(...fontSizes) : null,
      maxFontSize: fontSizes.length ? Math.max(...fontSizes) : null,
      smallText,
      smallControls,
      unexpectedOverflow,
    }
  }
  return { viewport: [innerWidth, innerHeight], pageOverflow: [root.scrollWidth - root.clientWidth, root.scrollHeight - root.clientHeight], containers: selectors.map(inspect) }
})()`

try {
  for (const viewport of viewports) {
    await page.setViewportSize({ width: viewport.width, height: viewport.height })
    await page.goto(url, { waitUntil: 'domcontentloaded' })
    await page.waitForSelector('.topbar', { timeout: 15000 })
    await page.waitForTimeout(1500)
    const report = await page.evaluate(inspectExpression(selectors))
    reports.push({ label: viewport.label, ...report })
    await page.screenshot({ path: resolve(out, `page-${viewport.label}.png`), fullPage: false })
    for (let i = 0; i < selectors.length; i++) {
      const handle = await page.$(selectors[i])
      if (!handle) continue
      await handle.screenshot({ path: resolve(out, `${String(i + 1).padStart(2, '0')}-${selectors[i].slice(1)}-${viewport.label}.png`) }).catch(() => {})
    }
    writeFileSync(resolve(out, `report-${viewport.label}.json`), JSON.stringify(report, null, 2))
  }
} finally {
  await browser.close()
}
const summary = reports.map((r) => ({
  viewport: r.viewport,
  pageOverflow: r.pageOverflow,
  minFonts: r.containers.filter((c) => !c.missing).map((c) => [c.selector, c.minFontSize]),
  smallControlCount: r.containers.filter((c) => !c.missing).map((c) => [c.selector, c.smallControls?.length || 0]),
  overflow: r.containers.filter((c) => c.unexpectedOverflow?.length).map((c) => [c.selector, c.unexpectedOverflow.length]),
}))
writeFileSync(resolve(out, 'summary.json'), JSON.stringify(summary, null, 2))
console.log(JSON.stringify(summary, null, 2))
