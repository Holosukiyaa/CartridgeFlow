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
    await page.getByRole('button', { name: '对话管家' }).click()
    await page.getByRole('button', { name: '开始补齐' }).click()
  })

  test('project menu exposes new, rename, and safe delete', async ({ page }) => {
    let exists = true
    let name = '日报项目'
    const creator = () => ({
      project_id: project,
      project_name: name,
      short_name: name,
      session_id: 'creator.test',
      revision: 1,
      intent: '生成日报',
      trusted_recipe: { id: 'recipe.test', goal: '生成日报', nodes: [], relations: [] },
      frozen_steps: [],
      active_freezes: [],
      pending_proposals: [],
      history: [],
      generation_readiness: { ready: true },
    })
    await page.route(/\/api\/creator\/projects$/, (route) => route.fulfill({ json: { projects: exists ? [{ project_id: project, session_id: 'creator.test', name, intent: '生成日报', revision: 1 }] : [] } }))
    await page.route(new RegExp(`/api/creator/projects/${project.replaceAll('.', '\\.')}\\?optional=true$`), (route) => route.fulfill({ json: { creator: exists ? creator() : null } }))
    await page.route(new RegExp(`/api/creator/projects/${project.replaceAll('.', '\\.')}/workspace$`), (route) => route.fulfill({ json: { workspace: null } }))
    await page.route(new RegExp(`/api/creator/projects/${project.replaceAll('.', '\\.')}$`), async (route) => {
      if (route.request().method() === 'PATCH') {
        name = String((await route.request().postDataJSON()).name)
        await route.fulfill({ json: { creator: creator() } })
        return
      }
      if (route.request().method() === 'DELETE') {
        exists = false
        await route.fulfill({ json: { deleted: true } })
        return
      }
      await route.fallback()
    })
    await page.route('**/api/settings', (route) => route.fulfill({ json: { provider: '', has_key: false, base_url: '', model: '' } }))
    await page.route('**/api/creator/desktop-runner', (route) => route.fulfill({ json: { schema: 'cartridgeflow.desktop_runner_status.v1', available: false, url: '', version: '', busy: false, cartridge: null } }))
    await page.reload({ waitUntil: 'domcontentloaded' })

    await page.locator('button.project-name').click()
    await expect(page.getByRole('button', { name: '新建项目' })).toBeVisible()

    await page.getByRole('button', { name: '重命名' }).click()
    const rename = page.getByRole('dialog', { name: '重命名项目' })
    const nameInput = rename.getByRole('textbox', { name: '项目短名' })
    await expect(nameInput).toHaveAttribute('maxlength', '16')
    await nameInput.fill('每周产品简报')
    await rename.getByRole('button', { name: '重命名', exact: true }).click()
    await expect(page.locator('button.project-name')).toContainText('每周产品简报')

    await page.locator('button.project-name').click()
    await page.getByRole('button', { name: '删除项目' }).click()
    const remove = page.getByRole('dialog', { name: '确认删除项目' })
    await expect(remove.getByRole('button', { name: '取消' })).toBeFocused()
    await remove.getByRole('button', { name: '确认删除' }).click()
    await expect(page.getByRole('dialog', { name: '还没有项目' })).toBeVisible()
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

test('empty hub creates a draft with a new project identity only after the user asks', async ({ page }) => {
  const draftUuid = '7b27fe6d-2f91-4e46-b9ee-74e604debec9'
  const draftProject = `project.${draftUuid}`
  const requestedProjectIds: string[] = []
  await page.addInitScript((uuid) => {
    Object.defineProperty(crypto, 'randomUUID', { configurable: true, value: () => uuid })
  }, draftUuid)
  await page.route(/^https?:\/\/[^/]+\/api\//, async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    if (url.pathname === '/api/creator/projects') {
      await route.fulfill({ json: { projects: [] } })
      return
    }
    if (url.pathname === '/api/settings') {
      await route.fulfill({ json: { provider: '', has_key: false, base_url: '', model: '' } })
      return
    }
    if (url.pathname === '/api/creator/desktop-runner') {
      await route.fulfill({ json: { schema: 'cartridgeflow.desktop_runner_status.v1', available: false, url: '', version: '', busy: false, cartridge: null } })
      return
    }
    const projectPath = url.pathname.match(/^\/api\/creator\/projects\/([^/]+)(\/workspace)?$/)
    if (projectPath) {
      const requestedProjectId = decodeURIComponent(projectPath[1])
      requestedProjectIds.push(requestedProjectId)
      if (projectPath[2] === '/workspace') {
        await route.fulfill({ json: { workspace: null } })
        return
      }
      await route.fulfill({ json: { creator: null } })
      return
    }
    await route.fulfill({ status: 404, json: { detail: 'Unexpected mocked API request.' } })
  })

  await page.goto('/studio', { waitUntil: 'domcontentloaded' })
  await expect(page.getByRole('dialog', { name: '还没有项目' })).toBeVisible()
  await expect(page).toHaveURL(/\/studio$/)
  await page.getByRole('button', { name: '新建项目' }).click()
  await expect(page).toHaveURL(new RegExp(`/projects/${draftProject.replaceAll('.', '\\.')}/studio$`))
  await expect(page.locator('.topbar')).toBeVisible()
  await expect.poll(() => requestedProjectIds.length).toBeGreaterThanOrEqual(2)
  expect(requestedProjectIds.every((projectId) => projectId === draftProject)).toBe(true)
  expect(requestedProjectIds).not.toContain(project)
  expect(await page.evaluate(() => localStorage.getItem('cartridgeflow.studio-project'))).toBe(draftProject)
})

test('workspace save surfaces revision conflicts', async ({ page }) => {
  const conflictProject = 'project.revision-conflict'
  const snapshot = {
    version: 1,
    goal: '保留这份冲突草稿',
    messages: [],
    clarification: null,
    possibilities: [],
    selectedId: '',
    packageResult: null,
    packageRevision: null,
    layer2Flows: {},
    runtimeInputs: {},
  }
  await page.route(new RegExp(`/api/creator/projects/${conflictProject.replaceAll('.', '\\.')}\\?optional=true$`), (route) => route.fulfill({ json: { creator: null } }))
  await page.route(new RegExp(`/api/creator/projects/${conflictProject.replaceAll('.', '\\.')}/workspace$`), (route) => {
    if (route.request().method() === 'PUT') {
      void route.fulfill({ status: 409, json: { detail: { code: 'CREATOR_WORKSPACE_REVISION_CONFLICT', message: 'Workspace changed.' } } })
      return
    }
    void route.fulfill({ json: { workspace: { schema: 'cartridgeflow.creator_workspace.v1', project_id: conflictProject, revision: 2, updated_at: '', snapshot } } })
  })
  await page.route(/\/api\/creator\/projects$/, (route) => route.fulfill({ json: { projects: [] } }))
  await page.route('**/api/settings', (route) => route.fulfill({ json: { provider: 'creator-ai', has_key: true, base_url: '', model: 'test-model' } }))
  await page.route('**/api/creator/desktop-runner', (route) => route.fulfill({ json: { schema: 'cartridgeflow.desktop_runner_status.v1', available: false, url: '', version: '', busy: false, cartridge: null } }))

  await page.goto(`/projects/${conflictProject}/studio`, { waitUntil: 'domcontentloaded' })
  await expect(page.locator('.topbar-meta')).toContainText('REVISION_CONFLICT')
})
