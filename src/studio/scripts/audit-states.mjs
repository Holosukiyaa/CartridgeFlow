import { mkdirSync } from 'node:fs'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
import { chromium } from '@playwright/test'

const out = resolve(dirname(fileURLToPath(import.meta.url)), '../.data/ui-layout-audit/after/states')
mkdirSync(out, { recursive: true })
const host = 'http://127.0.0.1:5173'
const sample = `${host}/projects/project.1ec8b174-01cf-4fc5-bc57-ac9867516497/studio?visual=frame1`
const empty = `${host}/projects/project.layout-empty-audit/studio`
const viewports = [
  { width: 1672, height: 940, label: '1672x940' },
  { width: 1530, height: 766, label: '1530x766' },
]

const browser = await chromium.launch({ headless: true })
const page = await browser.newPage({ deviceScaleFactor: 1 })

try {
  for (const viewport of viewports) {
    await page.setViewportSize(viewport)

    await page.goto(sample, { waitUntil: 'domcontentloaded' })
    await page.waitForSelector('.topbar', { timeout: 15000 })
    await page.waitForTimeout(800)
    await page.locator('.detail-head-actions .icon-btn').last().click().catch(() => {})
    await page.locator('.steward-head .icon-btn').click().catch(() => {})
    await page.waitForTimeout(400)
    await page.screenshot({ path: resolve(out, `sparse-canvas-${viewport.label}.png`) })

    await page.goto(empty, { waitUntil: 'domcontentloaded' })
    await page.waitForSelector('.topbar', { timeout: 15000 })
    await page.waitForTimeout(800)
    await page.screenshot({ path: resolve(out, `empty-${viewport.label}.png`) })
  }

  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto(sample, { waitUntil: 'domcontentloaded' })
  await page.waitForSelector('.topbar', { timeout: 15000 })
  await page.waitForTimeout(800)
  await page.screenshot({ path: resolve(out, 'narrow-390x844.png') })
} finally {
  await browser.close()
}

console.log('states written', out)
