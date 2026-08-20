import { test, expect } from '@playwright/test'

const project = 'project.1ec8b174-01cf-4fc5-bc57-ac9867516497'
const studio = `/projects/${project}/studio`

test.describe('click inventory', () => {
  test.beforeEach(async ({ page }) => {
    await page.setViewportSize({ width: 1459, height: 900 })
    await page.goto(studio, { waitUntil: 'domcontentloaded' })
    await page.waitForSelector('.topbar')
  })

  test('topbar and nextbar controls respond', async ({ page }) => {
    await page.getByRole('button', { name: '本机资源' }).click()
    const pool = page.getByRole('dialog', { name: '本机资源池' })
    await expect(pool).toBeVisible()
    await pool.getByRole('button', { name: '关闭' }).last().click()
    await expect(pool).toHaveCount(0)
    await page.locator('button.connection').click()
    const connect = page.getByRole('dialog', { name: '连接共创 AI' })
    await expect(connect).toBeVisible()
    await connect.getByRole('button', { name: '取消' }).click()
    await page.locator('button.btn-steward').click()
    await page.locator('button.btn-next-steward').click()
    await page.getByRole('button', { name: '开始补齐' }).click()
  })

  test('steward, canvas, detail, layer2', async ({ page }) => {
    const whole = page.getByRole('button', { name: '整份方案' })
    if (await whole.isVisible()) await whole.click()
    const step = page.getByRole('button', { name: '当前步骤' })
    if (await step.isVisible()) await step.click()
    const node = page.locator('.creator-node').first()
    await expect(node).toBeVisible()
    await node.click()
    await expect(page.locator('.detail').first()).toBeVisible()
    await page.locator('.creator-node .node-layer').first().click()
    await expect(page.getByRole('dialog', { name: /第二层/ })).toBeVisible()
    await page.locator('.layer2-stages button', { hasText: '结果长什么样' }).click()
    await page.locator('.layer2-stages button', { hasText: '用真样本证明' }).click()
    await page.locator('.layer2-stages button', { hasText: '发布回第一层' }).click()
    await page.locator('.layer2-stages button', { hasText: '内部怎么走' }).click()
    await page.getByRole('button', { name: '添加内部步骤' }).click()
    await page.getByRole('button', { name: '回到方案' }).click()
    await expect(page.locator('.layer2')).toHaveCount(0)
  })

  test('narrow tabs', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 })
    await page.reload({ waitUntil: 'domcontentloaded' })
    await page.waitForSelector('.narrow-tabs')
    await page.locator('.narrow-tabs button', { hasText: '管家' }).click()
    await page.locator('.narrow-tabs button', { hasText: '详情' }).click()
    await page.locator('.narrow-tabs button', { hasText: '画布' }).click()
    await expect(page.locator('.mobile-list')).toBeVisible()
  })
})