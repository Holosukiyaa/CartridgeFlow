import { test, expect } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'
import { PNG } from 'pngjs'
import pixelmatch from 'pixelmatch'

const root = path.resolve('test')
const project = 'project.1ec8b174-01cf-4fc5-bc57-ac9867516497'
const studio = `/projects/${project}/studio`

type Frame = { id: string; width: number; height: number; url: string }

const frames: Frame[] = [
  { id: 'frame1', width: 1459, height: 900, url: studio },
  { id: 'frame2', width: 1543, height: 906, url: '/projects/project.visual-empty/studio' },
  { id: 'frame3', width: 1543, height: 900, url: studio },
  { id: 'frame4', width: 1543, height: 900, url: studio },
  { id: 'frame5', width: 1543, height: 900, url: studio },
  { id: 'frame6', width: 390, height: 844, url: studio },
]

function compare(actualPath: string, baselinePath: string, diffPath: string) {
  const actual = PNG.sync.read(fs.readFileSync(actualPath))
  const baseline = PNG.sync.read(fs.readFileSync(baselinePath))
  const width = Math.min(actual.width, baseline.width)
  const height = Math.min(actual.height, baseline.height)
  const diff = new PNG({ width, height })
  const mismatch = pixelmatch(actual.data, baseline.data, diff.data, width, height, { threshold: 0.1 })
  fs.mkdirSync(path.dirname(diffPath), { recursive: true })
  fs.writeFileSync(diffPath, PNG.sync.write(diff))
  const similarity = 1 - mismatch / (width * height)
  return { mismatch, similarity, width, height }
}

for (const frame of frames) {
  test(`visual ${frame.id} >= 95%`, async ({ page }) => {
    await page.setViewportSize({ width: frame.width, height: frame.height })
    await page.addInitScript(() => {
      const style = document.createElement('style')
      style.textContent = '* { caret-color: transparent !important; } .zoom, .react-flow__panel.zoom, .react-flow__controls, .react-flow__attribution { display: none !important; }'
      document.head.appendChild(style)
    })
    await page.goto(frame.url, { waitUntil: 'domcontentloaded' })
    await page.waitForSelector('.topbar', { timeout: 15_000 })
    await page.waitForTimeout(800)
    if (frame.id === 'frame1') {
      await page.locator('button.btn-steward').click()
      await page.waitForSelector('.steward')
    }
    if (frame.id === 'frame2') {
      await page.locator('button.connection').click()
      await page.waitForSelector('.dialog')
    }
    if (frame.id === 'frame3') {
      await page.getByRole('button', { name: '本机资源' }).click()
      await page.getByRole('button', { name: '添加接口' }).first().click()
      await page.getByRole('button', { name: '添加工具' }).first().click()
    }
    if (frame.id === 'frame4' || frame.id === 'frame5') {
      await page.locator('.creator-node.is-unresolved .node-layer').first().click()
      await page.waitForSelector('.layer2', { timeout: 15_000 })
      if (frame.id === 'frame5') await page.getByRole('button', { name: /结果长什么样/ }).click()
    }
    const shot = path.join(root, 'diff', `${frame.id}-actual.png`)
    const baseline = path.join(root, 'baselines', `${frame.id}.png`)
    fs.mkdirSync(path.dirname(shot), { recursive: true })
    await page.screenshot({ path: shot, fullPage: false })
    if (process.env.UPDATE_VISUAL === '1') {
      fs.copyFileSync(shot, baseline)
      return
    }
    test.skip(!fs.existsSync(baseline), `missing baseline ${frame.id}`)
    const result = compare(shot, baseline, path.join(root, 'diff', `${frame.id}-diff.png`))
    fs.writeFileSync(path.join(root, 'diff', `${frame.id}.json`), JSON.stringify(result, null, 2))
    expect(result.similarity, `${frame.id} similarity ${result.similarity}`).toBeGreaterThanOrEqual(0.95)
  })
}
