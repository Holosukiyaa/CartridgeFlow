#!/usr/bin/env node
import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { mkdirSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { chromium } from 'playwright'

const packageRoot = join(fileURLToPath(new URL('.', import.meta.url)), '..')
const repositoryRoot = join(packageRoot, '..', '..')
const outputRoot = join(repositoryRoot, 'output', 'playwright')
const port = Number(process.env.INTENT_UI_CHECK_PORT || 4173)
const baseUrl = `http://127.0.0.1:${port}/`
const vite = join(packageRoot, 'node_modules', 'vite', 'bin', 'vite.js')
const server = spawn(process.execPath, [vite, '--host', '127.0.0.1', '--port', String(port), '--strictPort'], {
  cwd: packageRoot,
  stdio: ['ignore', 'pipe', 'pipe'],
})
let serverOutput = ''
server.stdout.on('data', (chunk) => { serverOutput += chunk })
server.stderr.on('data', (chunk) => { serverOutput += chunk })

async function waitForServer() {
  for (let attempt = 0; attempt < 80; attempt += 1) {
    if (server.exitCode !== null) throw new Error(`Vite stopped before UI checks started.\n${serverOutput}`)
    try {
      const response = await fetch(baseUrl)
      if (response.ok) return
    } catch {
      // The server is still starting.
    }
    await new Promise((resolve) => setTimeout(resolve, 125))
  }
  throw new Error(`Vite did not become ready at ${baseUrl}.\n${serverOutput}`)
}

async function assertViewport(browser, viewport) {
  const context = await browser.newContext({ viewport, deviceScaleFactor: 1 })
  const page = await context.newPage()
  const browserErrors = []
  page.on('pageerror', (error) => browserErrors.push(error.message))
  page.on('console', (message) => {
    if (message.type() === 'error' && !message.text().includes('Failed to load resource')) browserErrors.push(message.text())
  })
  await page.addInitScript(() => localStorage.clear())
  await page.goto(baseUrl, { waitUntil: 'domcontentloaded' })
  await page.locator('main.creator-workbench').waitFor({ state: 'visible' })

  const compact = viewport.width <= 1120
  const visiblePanes = page.locator('.workbench-pane:visible')
  assert.equal(await visiblePanes.count(), compact ? 1 : 3, `unexpected pane count at ${viewport.width}x${viewport.height}`)

  if (compact) {
    const tabs = page.getByRole('tablist', { name: '工作区视图' })
    await tabs.waitFor({ state: 'visible' })
    assert.equal(await tabs.getByRole('tab').count(), 3, 'compact mode must expose all three panes')
    await tabs.getByRole('tab', { name: '画布' }).click()
    await page.getByRole('region', { name: '语义画布' }).waitFor({ state: 'visible' })
    assert.equal(await visiblePanes.count(), 1, 'compact mode must mount only the active pane')
    const tabLayout = await page.locator('.workbench-pane-tabs .mantine-Tabs-tab').evaluateAll((elements) => elements.map((element) => {
      const tab = element.getBoundingClientRect()
      const icon = element.querySelector('.mantine-Tabs-tabSection')?.getBoundingClientRect()
      const label = element.querySelector('.mantine-Tabs-tabLabel')?.getBoundingClientRect()
      if (!icon || !label) return false
      const groupCenter = (Math.min(icon.left, label.left) + Math.max(icon.right, label.right)) / 2
      return Math.abs(groupCenter - (tab.left + tab.width / 2)) <= 2 && getComputedStyle(element.querySelector('.mantine-Tabs-tabLabel')).flexGrow === '0'
    }))
    assert.deepEqual(tabLayout, [true, true, true], 'compact tabs must keep icon and label grouped')
    assert.equal(await page.locator('.vip-project-crumb:visible').count(), 0, 'compact topbar must not clip the project breadcrumb')
  } else {
    assert.equal(await page.locator('.split-view').count(), 1, 'desktop mode must use the resizable workbench')
  }

  const geometry = await page.evaluate(() => {
    const root = document.documentElement
    const canvas = document.querySelector('[aria-label="语义画布"]')?.getBoundingClientRect()
    const clippedControls = [...document.querySelectorAll('button, input, textarea, select, [role="tab"]')]
      .filter((element) => {
        const style = getComputedStyle(element)
        const rect = element.getBoundingClientRect()
        const transientNotification = String(element.className).includes('mantine-Notification-')
        return !transientNotification && style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0
      })
      .filter((element) => {
        const rect = element.getBoundingClientRect()
        return rect.left < -1 || rect.right > innerWidth + 1 || rect.top < -1 || rect.bottom > innerHeight + 1
          || element.scrollWidth > element.clientWidth + 1 || element.scrollHeight > element.clientHeight + 1
      })
      .map((element) => ({
        tag: element.tagName,
        className: String(element.className),
        label: element.getAttribute('aria-label') || element.textContent?.trim().slice(0, 60) || '',
        client: [element.clientWidth, element.clientHeight],
        scroll: [element.scrollWidth, element.scrollHeight],
        rect: element.getBoundingClientRect().toJSON(),
      }))
    return {
      horizontalOverflow: root.scrollWidth - root.clientWidth,
      canvas: canvas ? { width: canvas.width, height: canvas.height } : null,
      clippedControls,
    }
  })
  assert.ok(geometry.horizontalOverflow <= 1, `horizontal overflow at ${viewport.width}x${viewport.height}: ${geometry.horizontalOverflow}px`)
  assert.ok(geometry.canvas && geometry.canvas.width >= 300 && geometry.canvas.height >= 300, `canvas is not stably framed at ${viewport.width}x${viewport.height}`)
  assert.deepEqual(geometry.clippedControls, [], `controls are clipped at ${viewport.width}x${viewport.height}`)
  assert.deepEqual(browserErrors, [], `unexpected browser errors at ${viewport.width}x${viewport.height}`)

  mkdirSync(outputRoot, { recursive: true })
  await page.screenshot({ path: join(outputRoot, `intent-ui-${viewport.width}x${viewport.height}.png`) })
  await context.close()
}

let browser
try {
  await waitForServer()
  browser = await chromium.launch({ headless: true })
  for (const viewport of [
    { width: 1920, height: 1080 },
    { width: 1536, height: 864 },
    { width: 1120, height: 800 },
    { width: 390, height: 844 },
  ]) await assertViewport(browser, viewport)

  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } })
  const page = await context.newPage()
  await page.goto(baseUrl, { waitUntil: 'domcontentloaded' })
  const themeButton = page.getByRole('button', { name: /主题$/ })
  await themeButton.click()
  await page.getByRole('dialog').waitFor({ state: 'visible' })
  await page.keyboard.press('Escape')
  await page.getByRole('dialog').waitFor({ state: 'hidden' })
  await page.waitForFunction((element) => element === document.activeElement, await themeButton.elementHandle(), { timeout: 3000 })
  await context.close()
  console.log('Intent Studio browser UI acceptance passed for 4 viewports and dialog focus behavior.')
} finally {
  if (browser) await browser.close()
  server.kill()
}
