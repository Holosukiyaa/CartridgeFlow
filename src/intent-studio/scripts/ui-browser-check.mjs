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
const server = spawn(process.execPath, [vite, '--host', '127.0.0.1', '--port', String(port), '--strictPort'], { cwd: packageRoot, stdio: ['ignore', 'pipe', 'pipe'] })
let serverOutput = ''
server.stdout.on('data', (chunk) => { serverOutput += chunk })
server.stderr.on('data', (chunk) => { serverOutput += chunk })

async function waitForServer() {
  for (let attempt = 0; attempt < 80; attempt += 1) {
    if (server.exitCode !== null) throw new Error(`Vite stopped before UI checks started.\n${serverOutput}`)
    try { if ((await fetch(baseUrl)).ok) return } catch { /* still starting */ }
    await new Promise((resolve) => setTimeout(resolve, 125))
  }
  throw new Error(`Vite did not become ready at ${baseUrl}.\n${serverOutput}`)
}

const matureProjectId = 'ui-semantic-fixture'
const entryProjectId = 'ui-semantic-entry'
const fixtureNodes = [
  ['collect', 'Collect requirements', 'Gather the release requirements.', true],
  ['verify', 'Verify sources', 'Review public sources and constraints.', false],
  ['deliver', 'Deliver package', 'Prepare a reviewed package.', false],
].map(([id, label, description, trusted], index) => ({
  id, label, description, values: { instruction: description },
  editable_fields: [{ id: 'instruction', label: 'Instruction', value_type: 'string', required: true, default: description }],
  resolution: { status: 'resolved', needed_capability: '', capability: { id: `fixture.${id}`, revision: 1, digest: `fixture-${index}`, trust_scope: 'workspace', label: 'Available capability', description } },
  trusted,
}))
const fixtureCreator = {
  project_id: matureProjectId, project_name: 'Semantic release review', session_id: 'session.semantic-fixture', revision: 1, intent: 'Review a release package',
  trusted_recipe: { id: 'recipe.semantic-fixture', goal: 'Review a release package', nodes: fixtureNodes, relations: [
    { id: 'collect-verify', from_node_id: 'collect', to_node_id: 'verify', relation: 'informs' },
    { id: 'verify-deliver', from_node_id: 'verify', to_node_id: 'deliver', relation: 'uses' },
  ] },
  frozen_steps: ['collect'], active_freezes: [], pending_proposals: [], history: [],
  generation_readiness: { ready: false }, capability_resolution: { resolved: 3, unresolved: 0, revision: 1 },
}

async function installApiFixture(page) {
  await page.route('**/api/**', async (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    if (path === `/api/creator/projects/${matureProjectId}`) return route.fulfill({ json: { creator: fixtureCreator } })
    if (path === `/api/creator/projects/${entryProjectId}`) return route.fulfill({ json: { creator: null } })
    if (path.endsWith('/workspace')) {
      const snapshot = request.method() === 'PUT' ? request.postDataJSON()?.snapshot : null
      return route.fulfill({ json: { workspace: snapshot ? { revision: 1, updated_at: '2026-08-18T00:00:00Z', snapshot } : null } })
    }
    if (path === '/api/creator/projects') return route.fulfill({ json: { projects: [{ project_id: matureProjectId, session_id: fixtureCreator.session_id, name: fixtureCreator.project_name, intent: fixtureCreator.intent, revision: 1 }] } })
    if (path === '/api/settings') return route.fulfill({ json: { provider: '', has_key: false, base_url: '', model: '' } })
    if (path === '/api/llm/providers') return route.fulfill({ json: { providers: [] } })
    if (path === '/api/studio/resources') return route.fulfill({ json: { version: 1, tools: [], builtin_tools: [], bindings: { tools: {}, roles: {} } } })
    if (path === '/api/creator/desktop-runner') return route.fulfill({ json: { available: false, url: 'http://127.0.0.1:18990/' } })
    return route.continue()
  })
}

async function geometry(page) {
  return page.evaluate(() => {
    const root = document.documentElement
    const controls = [...document.querySelectorAll('button,input,textarea,select,[role="tab"]')].filter((element) => {
      const style = getComputedStyle(element); const rect = element.getBoundingClientRect()
      return !element.closest('.react-flow__viewport') && style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0
        && (rect.left < -1 || rect.right > innerWidth + 1 || rect.top < -1 || rect.bottom > innerHeight + 1 || (element.tagName !== 'BUTTON' && (element.scrollWidth > element.clientWidth + 1 || element.scrollHeight > element.clientHeight + 1)))
    }).map((element) => ({
      label: element.getAttribute('aria-label') || element.textContent?.trim().slice(0, 48) || element.tagName,
      client: [element.clientWidth, element.clientHeight],
      scroll: [element.scrollWidth, element.scrollHeight],
      rect: element.getBoundingClientRect().toJSON(),
    }))
    const canvas = document.querySelector('.vip-canvas-surface')?.getBoundingClientRect()
    const surface = document.querySelector('.vip-canvas-surface')
    const node = document.querySelector('.creator-node')
    return {
      overflow: root.scrollWidth - root.clientWidth,
      canvas: canvas ? { width: canvas.width, height: canvas.height } : null,
      controls,
      pattern: surface ? getComputedStyle(surface).backgroundImage : 'none',
      canvasColor: surface ? getComputedStyle(surface).backgroundColor : '',
      nodeColor: node ? getComputedStyle(node).backgroundColor : '',
      nodeRadius: node ? Number.parseFloat(getComputedStyle(node).borderRadius) : 0,
    }
  })
}

async function setupPage(browser, viewport, projectId) {
  const context = await browser.newContext({ viewport, deviceScaleFactor: 1 })
  const page = await context.newPage()
  const errors = []
  page.on('pageerror', (error) => errors.push(error.message))
  page.on('console', (message) => { if (message.type() === 'error' && !message.text().includes('Failed to load resource')) errors.push(message.text()) })
  await page.addInitScript(() => localStorage.clear())
  await installApiFixture(page)
  await page.goto(`${baseUrl}projects/${projectId}/studio`, { waitUntil: 'domcontentloaded' })
  await page.locator('main.creator-workspace').waitFor({ state: 'visible' })
  await page.waitForTimeout(500)
  return { context, page, errors }
}

async function assertCommon(page, viewport, errors) {
  const result = await geometry(page)
  assert.ok(result.canvas && result.canvas.width >= 300 && result.canvas.height >= 300, `canvas is not stably framed at ${viewport.width}x${viewport.height}`)
  assert.ok(result.overflow <= 1, `horizontal overflow at ${viewport.width}x${viewport.height}: ${result.overflow}px`)
  assert.deepEqual(result.controls, [], `controls are clipped at ${viewport.width}x${viewport.height}`)
  assert.notEqual(result.pattern, 'none', `canvas grid is missing at ${viewport.width}x${viewport.height}`)
  assert.notEqual(result.canvasColor, result.nodeColor, `canvas and node surfaces collapse at ${viewport.width}x${viewport.height}`)
  assert.ok(result.nodeRadius >= 6, `node surface hierarchy is missing at ${viewport.width}x${viewport.height}`)
  assert.deepEqual(errors, [], `browser errors at ${viewport.width}x${viewport.height}`)
}

async function assertEntry(browser, viewport) {
  const { context, page, errors } = await setupPage(browser, viewport, entryProjectId)
  await page.locator('.creator-node').nth(0).waitFor({ state: 'visible' })
  assert.equal(await page.locator('.creator-node').count(), 2, 'empty projects must expose only start and end placeholders')
  assert.deepEqual(await page.locator('.creator-node-title strong').allTextContents(), ['开始', '结束'])
  assert.equal(await page.locator('.creator-stage-rail').count(), 0, 'stage concept must stay absent')
  assert.equal(await page.locator('.semantic-runtime-bar').count(), 1, 'runtime bar must remain visible')
  await assertCommon(page, viewport, errors)
  mkdirSync(outputRoot, { recursive: true })
  await page.screenshot({ path: join(outputRoot, `intent-ui-semantic-entry-${viewport.width}x${viewport.height}.png`) })
  await context.close()
}

async function assertMature(browser, viewport) {
  const { context, page, errors } = await setupPage(browser, viewport, matureProjectId)
  await page.locator('.creator-node').nth(0).waitFor({ state: 'visible' })
  assert.equal(await page.locator('.creator-node').count(), 3, 'mature fixture must render semantic nodes')
  assert.equal(await page.locator('.creator-edge.is-control').count(), 1, 'control relation must render as a curved edge')
  assert.equal(await page.locator('.creator-edge.is-dependency').count(), 1, 'dependency relation must render as a curved edge')
  assert.match(await page.locator('.creator-edge.is-control path').first().getAttribute('d') || '', /C/, 'semantic relations must use bezier curves')
  assert.equal(await page.locator('.semantic-node-route button').count(), 3, 'route strip must expose one point per node')
  assert.equal(await page.locator('.creator-node-confirmed').count(), 1, 'trusted node must retain the confirmed state')
  assert.equal(await page.locator('.creator-node-review').count(), 2, 'untrusted review nodes must remain visibly distinct')
  const trustSurfaces = await page.locator('.creator-node').evaluateAll((nodes) => nodes.map((node) => ({ background: getComputedStyle(node).backgroundColor, status: getComputedStyle(node.querySelector('.creator-node-footer strong')).color })))
  assert.notEqual(trustSurfaces[0].background, trustSurfaces[1].background, 'trusted and untrusted node surfaces must differ')
  assert.notEqual(trustSurfaces[0].status, trustSurfaces[1].status, 'trusted and untrusted status colors must differ')
  await page.locator('.semantic-relation-filters input').nth(2).click()
  assert.equal(await page.locator('.creator-edge.is-dependency').count(), 0, 'dependency filter must hide dependency relations')
  await page.locator('.semantic-relation-filters input').nth(2).click()
  if (viewport.width > 1280) {
    const routePoint = page.locator('.semantic-node-route button').first()
    const before = await routePoint.boundingBox()
    await routePoint.hover()
    const after = await routePoint.boundingBox()
    assert.ok(before && after && after.width > before.width, 'route points must enlarge on hover')
  }
  await page.locator('.semantic-panel-actions button').nth(0).click()
  assert.equal(await page.locator('.semantic-detail-panel:visible').count(), 1, 'detail panel toggle must be independent')
  if (viewport.width > 1280) {
    assert.equal(await page.locator('.semantic-side-panel:visible').count(), 2, 'details and AI may be open together')
    const order = await page.locator('.semantic-side-panel:visible').evaluateAll((items) => items.map((item) => item.className))
    assert.ok(order[0].includes('detail') && order[1].includes('ai'), 'AI must remain the far-right side panel')
    await page.waitForTimeout(500)
    const frameReport = await page.locator('.vip-canvas-surface').evaluate((canvas) => {
      const frame = canvas.getBoundingClientRect()
      const tools = canvas.querySelector('.semantic-canvas-toolstack')?.getBoundingClientRect()
      const nodes = [...canvas.querySelectorAll('.creator-node')].map((node) => {
        const rect = node.getBoundingClientRect()
        const overlapsTools = tools && rect.left < tools.right + 12 && rect.right > tools.left - 12 && rect.top < tools.bottom + 12 && rect.bottom > tools.top - 12
        return { rect: rect.toJSON(), overlapsTools }
      })
      return { frame: frame.toJSON(), tools: tools?.toJSON(), nodes }
    })
    assert.ok(frameReport.nodes.every(({ rect, overlapsTools }) => !overlapsTools && rect.left >= frameReport.frame.left + 16 && rect.right <= frameReport.frame.right - 16 && rect.top >= frameReport.frame.top + 16 && rect.bottom <= frameReport.frame.bottom - 16), `opening detail and AI together must reframe every semantic node: ${JSON.stringify(frameReport)}`)
    if (viewport.width === 1536) {
      mkdirSync(outputRoot, { recursive: true })
      await page.screenshot({ path: join(outputRoot, 'intent-ui-semantic-both-1536x864.png') })
    }
    await page.locator('.semantic-side-panel.semantic-detail-panel button').first().click()
    assert.equal(await page.locator('.semantic-side-panel:visible').count(), 1, 'detail panel must collapse independently')
  } else {
    const tabs = page.locator('.semantic-panel-tabs')
    assert.equal(await tabs.getByRole('tab').count(), 3, 'compact mode must expose canvas, detail, and AI tabs')
    await tabs.getByRole('tab', { name: '详情' }).click()
    assert.equal(await page.locator('.semantic-detail-panel:visible').count(), 1, 'compact detail tab must mount only detail')
    await tabs.getByRole('tab', { name: /AI/ }).click()
    assert.equal(await page.locator('.semantic-ai-panel:visible').count(), 1, 'compact AI tab must mount only AI')
  }
  if (viewport.width === 1536) {
    await page.locator('.semantic-canvas-toolstack button').nth(3).click()
    await page.getByRole('dialog').waitFor({ state: 'visible' })
    assert.equal(await page.locator('.resource-manager').count(), 1, 'model manager must use the shared dialog')
    await page.getByRole('tab', { name: /工具配置/ }).click()
    assert.equal(await page.locator('.resource-manager-layout:visible').count(), 1, 'tool configuration must be available beside model configuration')
    await page.keyboard.press('Escape')
    await page.locator('.resource-manager').waitFor({ state: 'hidden' })
    await page.locator('.creator-node-layer-actions button').first().click()
    await page.locator('.nested-cartridge-shell').waitFor({ state: 'visible' })
    assert.equal(await page.locator('.nested-cartridge-shell iframe').count(), 1, 'second semantic layer must open in a modal iframe')
    await page.keyboard.press('Escape')
    await page.locator('.nested-cartridge-shell').waitFor({ state: 'hidden' })
  }
  if (viewport.width > 1280 || await page.locator('.vip-canvas-surface:visible').count()) await assertCommon(page, viewport, errors)
  mkdirSync(outputRoot, { recursive: true })
  await page.screenshot({ path: join(outputRoot, `intent-ui-semantic-mature-${viewport.width}x${viewport.height}.png`) })
  await context.close()
}

let browser
try {
  await waitForServer()
  browser = await chromium.launch({ headless: true })
  for (const viewport of [{ width: 1920, height: 1080 }, { width: 1536, height: 864 }, { width: 1229, height: 691 }, { width: 1120, height: 800 }, { width: 390, height: 844 }]) {
    await assertEntry(browser, viewport)
    await assertMature(browser, viewport)
  }
  console.log('Intent Studio semantic canvas acceptance passed at 5 viewports, including independent panels, resource management, and nested layer modal.')
} finally {
  if (browser) await browser.close()
  server.kill()
}
