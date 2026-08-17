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

const fixtureProjectId = 'ui-layout-fixture'
const fixtureNodes = [
  ['collect', '收集发布要求', '汇总产品、法务和运营团队对本次发布的具体要求。'],
  ['verify', '核对可信来源', '检查公开来源、内部约束和待确认事实是否一致。'],
  ['deliver', '交付桌面试运行', '打包确认方案并交付 Desktop Runner 进行试用。'],
].map(([id, label, description], index) => ({
  id, label, description, values: { instruction: description },
  editable_fields: [{ id: 'instruction', label: '执行说明', value_type: 'string', required: true, default: description }],
  resolution: { status: 'resolved', needed_capability: '', capability: { id: `fixture.${id}`, revision: 1, digest: `fixture-${index}`, trust_scope: 'workspace', label: '可用做法', description } },
}))
const fixtureCreator = {
  project_id: fixtureProjectId, project_name: '跨团队发布审核', session_id: 'session.ui-layout-fixture', revision: 1, intent: '整理跨团队发布要求并交付可审核的桌面试运行流程',
  trusted_recipe: {
    id: 'recipe.ui-layout-fixture', goal: '整理跨团队发布要求并交付可审核的桌面试运行流程', nodes: fixtureNodes,
    relations: [
      { id: 'collect-verify', from_node_id: 'collect', to_node_id: 'verify', relation: 'informs' },
      { id: 'verify-deliver', from_node_id: 'verify', to_node_id: 'deliver', relation: 'informs' },
    ],
  },
  frozen_steps: [], active_freezes: [], pending_proposals: [], history: [],
  generation_readiness: { ready: false }, capability_resolution: { resolved: 3, unresolved: 0, revision: 1 },
}

async function installMatureFixture(page) {
  await page.route('**/api/**', async (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    if (path === `/api/creator/projects/${fixtureProjectId}`) return route.fulfill({ json: { creator: fixtureCreator } })
    if (path === `/api/creator/projects/${fixtureProjectId}/workspace`) {
      const snapshot = request.method() === 'PUT' ? request.postDataJSON()?.snapshot : null
      return route.fulfill({ json: { workspace: snapshot ? { revision: 1, updated_at: '2026-08-17T00:00:00Z', snapshot } : null } })
    }
    if (path === '/api/creator/projects') return route.fulfill({ json: { projects: [{ project_id: fixtureProjectId, session_id: fixtureCreator.session_id, name: fixtureCreator.project_name, intent: fixtureCreator.intent, revision: 1 }] } })
    if (path === '/api/settings') return route.fulfill({ json: { provider: '', has_key: false, base_url: '', model: '' } })
    if (path === '/api/creator/desktop-runner') return route.fulfill({ json: { available: false, url: 'http://127.0.0.1:18990/' } })
    return route.continue()
  })
}

async function assertMatureViewport(browser, viewport) {
  const context = await browser.newContext({ viewport, deviceScaleFactor: 1 })
  const page = await context.newPage()
  const browserErrors = []
  page.on('pageerror', (error) => browserErrors.push(error.message))
  page.on('console', (message) => {
    if (message.type() === 'error' && !message.text().includes('Failed to load resource')) browserErrors.push(message.text())
  })
  await page.addInitScript(() => {
    localStorage.clear()
    localStorage.setItem('cartridgeflow.intent-studio.panes.v2.collaboration.outline.canvas', '[320,416,800]')
  })
  await installMatureFixture(page)
  await page.goto(`${baseUrl}projects/${fixtureProjectId}/studio`, { waitUntil: 'domcontentloaded' })
  await page.locator('main.creator-workbench').waitFor({ state: 'visible' })
  const compact = viewport.width <= 1280
  if (compact) await page.getByRole('complementary', { name: 'AI 共创记录' }).waitFor({ state: 'visible' })
  else await page.getByRole('region', { name: '项目与大纲' }).waitFor({ state: 'visible' })

  const stages = page.getByRole('navigation', { name: '卡带创作阶段' })
  assert.equal(await stages.locator('li').count(), 6, 'mature workspace must retain the six authoring stages')
  assert.equal((await stages.locator('[aria-current="step"]').textContent())?.trim(), '审核', 'mature outline with pending nodes must expose the review stage')
  assert.equal(await page.getByRole('button', { name: '准备试运行' }).count(), 0, 'trial action must stay hidden until the project is ready')

  const visiblePanes = page.locator('.workbench-pane:visible')
  assert.equal(await visiblePanes.count(), compact ? 1 : 3, `unexpected pane count at ${viewport.width}x${viewport.height}`)

  if (compact) {
    const tabs = page.getByRole('tablist', { name: '工作区视图' })
    await tabs.waitFor({ state: 'visible' })
    assert.equal(await tabs.getByRole('tab').count(), 3, 'compact mode must expose all three panes')
    await tabs.getByRole('tab', { name: '画布' }).click()
    await page.getByRole('region', { name: '语义画布' }).waitFor({ state: 'visible' })
    assert.equal(await visiblePanes.count(), 1, 'compact mode must mount only the active pane')
    const activeTabContrast = await tabs.getByRole('tab', { name: '画布' }).evaluate((element) => {
      const channels = (value) => {
        const parsed = value.match(/[\d.]+/g)?.slice(0, 3).map(Number) || [0, 0, 0]
        return value.startsWith('color(srgb') ? parsed.map((channel) => channel * 255) : parsed
      }
      const luminance = (value) => {
        if (value.startsWith('oklab')) return Number(value.match(/[\d.]+/)?.[0] || 0) ** 3
        return channels(value).map((channel) => channel / 255).map((channel) => channel <= .03928 ? channel / 12.92 : ((channel + .055) / 1.055) ** 2.4).reduce((sum, channel, index) => sum + channel * [.2126, .7152, .0722][index], 0)
      }
      const style = getComputedStyle(element)
      const values = [luminance(style.color), luminance(style.backgroundColor)].sort((left, right) => right - left)
      return (values[0] + .05) / (values[1] + .05)
    })
    assert.ok(activeTabContrast >= 4.5, `compact active tab contrast is too low: ${activeTabContrast.toFixed(2)}`)
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
      visual: (() => {
        const brand = document.querySelector('.creator-brand-mark')
        const canvasSurface = document.querySelector('.vip-canvas-surface')
        const canvasHeader = document.querySelector('.vip-canvas-header')
        const canvasTitle = canvasHeader?.querySelector('strong')
        const node = document.querySelector('.creator-node')
        return {
          brandRadius: brand ? Number.parseFloat(getComputedStyle(brand).borderRadius) : 0,
          canvasPattern: canvasSurface ? getComputedStyle(canvasSurface).backgroundImage : 'none',
          canvasColor: canvasSurface ? getComputedStyle(canvasSurface).backgroundColor : '',
          canvasHeaderColor: canvasHeader ? getComputedStyle(canvasHeader).backgroundColor : '',
          canvasTitleSingleLine: canvasTitle ? canvasTitle.getBoundingClientRect().height <= Number.parseFloat(getComputedStyle(canvasTitle).fontSize) * 1.8 : false,
          nodeRadius: node ? Number.parseFloat(getComputedStyle(node).borderRadius) : 0,
          nodeColor: node ? getComputedStyle(node).backgroundColor : '',
        }
      })(),
    }
  })
  assert.ok(geometry.horizontalOverflow <= 1, `horizontal overflow at ${viewport.width}x${viewport.height}: ${geometry.horizontalOverflow}px`)
  assert.ok(geometry.canvas && geometry.canvas.width >= 300 && geometry.canvas.height >= 300, `canvas is not stably framed at ${viewport.width}x${viewport.height}`)
  assert.deepEqual(geometry.clippedControls, [], `controls are clipped at ${viewport.width}x${viewport.height}`)
  assert.ok(geometry.visual.brandRadius >= 6 && geometry.visual.nodeRadius >= 6, `visual hierarchy lost at ${viewport.width}x${viewport.height}`)
  assert.notEqual(geometry.visual.canvasPattern, 'none', `canvas structure lost at ${viewport.width}x${viewport.height}`)
  assert.notEqual(geometry.visual.canvasColor, geometry.visual.nodeColor, `canvas and nodes must remain distinct at ${viewport.width}x${viewport.height}`)
  assert.notEqual(geometry.visual.canvasColor, geometry.visual.canvasHeaderColor, `canvas header and work surface must remain distinct at ${viewport.width}x${viewport.height}`)
  assert.equal(geometry.visual.canvasTitleSingleLine, true, `canvas title wrapped at ${viewport.width}x${viewport.height}`)
  assert.deepEqual(browserErrors, [], `unexpected browser errors at ${viewport.width}x${viewport.height}`)

  mkdirSync(outputRoot, { recursive: true })
  await page.screenshot({ path: join(outputRoot, `intent-ui-mature-${viewport.width}x${viewport.height}.png`) })

  if (!compact && viewport.width === 1536) {
    await page.getByRole('row', { name: /01 收集发布要求/ }).dblclick()
    await page.getByRole('complementary', { name: '调整 收集发布要求' }).waitFor({ state: 'visible' })
    assert.equal(await visiblePanes.count(), 2, 'node review must keep only detail and canvas panes')
    assert.equal(await page.getByRole('complementary', { name: 'AI 共创记录' }).count(), 0, 'node review must release collaboration space')
    const detailWidth = await page.getByRole('complementary', { name: '调整 收集发布要求' }).evaluate((element) => element.getBoundingClientRect().width)
    assert.ok(detailWidth >= 500, `node detail remains too narrow: ${detailWidth}px`)
    await page.waitForTimeout(500)
    const framedNodes = await page.locator('.vip-canvas-surface').evaluate((canvas) => {
      const frame = canvas.getBoundingClientRect()
      return [...canvas.querySelectorAll('.creator-node')].every((node) => {
        const rect = node.getBoundingClientRect()
        return rect.left >= frame.left - 1 && rect.right <= frame.right + 1 && rect.top >= frame.top - 1 && rect.bottom <= frame.bottom + 1
      })
    })
    assert.equal(framedNodes, true, 'node review must reframe every semantic node inside the visible canvas')
    await page.screenshot({ path: join(outputRoot, 'intent-ui-node-review-1536x864.png') })
  }
  await context.close()
}

async function assertEntryViewport(browser, viewport) {
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
  const compact = viewport.width <= 1280
  if (compact) await page.getByRole('complementary', { name: 'AI 共创记录' }).waitFor({ state: 'visible' })
  else await page.getByRole('region', { name: '方向探索' }).waitFor({ state: 'visible' })
  const visiblePanes = page.locator('.workbench-pane:visible')
  assert.equal(await visiblePanes.count(), compact ? 1 : 2, `entry pane count is wrong at ${viewport.width}x${viewport.height}`)
  assert.equal(await page.getByRole('region', { name: '语义画布' }).count(), 0, 'entry stage must not expose an empty canvas')
  assert.equal(await page.getByRole('button', { name: '准备试运行' }).count(), 0, 'entry stage must not expose trial delivery')
  const stages = page.getByRole('navigation', { name: '卡带创作阶段' })
  assert.equal(await stages.locator('li').count(), 6, 'entry stage rail must expose the complete journey')
  assert.equal((await stages.locator('[aria-current="step"]').textContent())?.trim(), '目标', 'new projects must start at the goal stage')
  const entryStatus = page.getByText('等待连接 AI', { exact: true })
  assert.equal((await entryStatus.textContent())?.trim(), '等待连接 AI', 'new project status must describe its actual prerequisite')
  if (!compact) await entryStatus.waitFor({ state: 'visible' })
  const composerHeight = await page.getByPlaceholder('描述你想得到的结果和使用场景...').evaluate((element) => element.getBoundingClientRect().height)
  assert.ok(composerHeight >= 100, `entry composer is not prominent enough: ${composerHeight}px`)

  if (compact) {
    const tabs = page.getByRole('tablist', { name: '工作区视图' })
    assert.equal(await tabs.getByRole('tab').count(), 2, 'entry compact mode must expose only goal and direction')
    await tabs.getByRole('tab', { name: '方向' }).click()
    await page.getByRole('region', { name: '方向探索' }).waitFor({ state: 'visible' })
  } else {
    assert.equal(await page.locator('.split-view').count(), 1, 'desktop entry must use one resizable two-pane workspace')
    const widths = await visiblePanes.evaluateAll((elements) => elements.map((element) => element.getBoundingClientRect().width))
    assert.ok(widths.every((width) => width >= 470), `entry panes are too narrow: ${widths.join(', ')}`)
  }

  const geometry = await page.evaluate(() => ({
    horizontalOverflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
    clippedControls: [...document.querySelectorAll('button, input, textarea, select, [role="tab"]')].filter((element) => {
      const style = getComputedStyle(element)
      const rect = element.getBoundingClientRect()
      return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0
        && (rect.left < -1 || rect.right > innerWidth + 1 || rect.top < -1 || rect.bottom > innerHeight + 1 || element.scrollWidth > element.clientWidth + 1 || element.scrollHeight > element.clientHeight + 1)
    }).map((element) => element.getAttribute('aria-label') || element.textContent?.trim().slice(0, 60) || element.tagName),
  }))
  assert.ok(geometry.horizontalOverflow <= 1, `entry page overflows at ${viewport.width}x${viewport.height}`)
  assert.deepEqual(geometry.clippedControls, [], `entry controls are clipped at ${viewport.width}x${viewport.height}`)
  assert.deepEqual(browserErrors, [], `entry browser errors at ${viewport.width}x${viewport.height}`)
  mkdirSync(outputRoot, { recursive: true })
  await page.screenshot({ path: join(outputRoot, `intent-ui-entry-${viewport.width}x${viewport.height}.png`) })
  await context.close()
}

let browser
try {
  await waitForServer()
  browser = await chromium.launch({ headless: true })
  for (const viewport of [
    { width: 1920, height: 1080 },
    { width: 1536, height: 864 },
    { width: 1229, height: 691 },
    { width: 1120, height: 800 },
    { width: 390, height: 844 },
  ]) {
    await assertEntryViewport(browser, viewport)
    await assertMatureViewport(browser, viewport)
  }

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
  console.log('Intent Studio browser UI acceptance passed for entry and mature flows at 5 viewports, node review, and dialog focus behavior.')
} finally {
  if (browser) await browser.close()
  server.kill()
}
