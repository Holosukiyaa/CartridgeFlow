import { chromium } from '@playwright/test'
import { mkdir } from 'node:fs/promises'
import path from 'node:path'

const outDir = path.resolve('test/accept')
await mkdir(outDir, { recursive: true })
const project = 'project.1ec8b174-01cf-4fc5-bc57-ac9867516497'
const studio = `http://localhost:5173/projects/${project}/studio`
const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1459, height: 900 } })
page.setDefaultTimeout(40_000)
const shot = async (name) => { await page.screenshot({ path: path.join(outDir, `${name}.png`) }); console.log('shot', name) }
const fail = (id, detail) => { console.log('FAIL', id, detail); throw new Error(`${id}: ${detail}`) }
const ok = (id, detail) => console.log('OK', id, detail)
const bodyText = async () => page.locator('body').innerText()

const completeLayer = async ({ addField }) => {
  const dialog = page.getByRole('dialog', { name: /第二层/ })
  await dialog.waitFor({ state: 'visible' })
  const next = page.getByRole('button', { name: /下一步：结果长什么样/ })
  if (await next.count()) await next.click()
  else await page.getByRole('button', { name: '结果长什么样' }).click()
  await page.waitForTimeout(400)
  if (addField) {
    const before = await page.locator('.l2-fields li').count()
    await page.getByRole('button', { name: /添加字段/ }).click()
    await page.waitForTimeout(200)
    const after = await page.locator('.l2-fields li').count()
    if (after <= before) fail('add-field', `still ${after}`)
    ok('add-field', `${before} -> ${after}`)
    await page.getByRole('button', { name: '保存并绑定组件' }).click()
    await page.waitForTimeout(600)
  }
  await page.getByRole('button', { name: '用真样本证明' }).click()
  await page.getByRole('button', { name: '跑一次' }).click()
  await page.waitForFunction(() => /已登记|还需要一次成功/.test(document.body.innerText), null, { timeout: 20_000 })
  const prove = await page.locator('.layer2-col.is-prove').innerText()
  if (!/已登记/.test(prove) || !/成功/.test(prove) || !/安全失败/.test(prove)) fail('prove', prove.slice(0, 240))
  ok('prove', prove.slice(0, 160).replace(/\s+/g, ' '))
  const publish = page.getByRole('button', { name: '发布并回到原步骤' })
  if (await publish.isDisabled()) fail('publish-gate', prove.slice(0, 200))
  ok('publish-gate', 'enabled')
  await publish.click()
  await page.waitForTimeout(1200)
  if (await dialog.isVisible().catch(() => false)) {
    const err = await page.locator('.layer2 .alert, .l2-gaps').innerText().catch(() => '')
    fail('publish', err || 'L2 still open')
  }
  ok('publish', 'closed L2')
}

await page.goto(studio, { waitUntil: 'domcontentloaded' })
await page.waitForSelector('.topbar')
await page.waitForTimeout(1000)
const name = await page.locator('.project-name').innerText()
if (/我想做一份/.test(name)) fail('short-name', name)
ok('short-name', name)

let first = true
for (let i = 0; i < 6; i += 1) {
  const text = await bodyText()
  const gapCount = Number((text.match(/待补齐\s+(\d+)/) || [])[1] || '0')
  ok('gaps', `待补齐 ${gapCount}`)
  if (gapCount === 0) break
  const start = page.getByRole('button', { name: '开始补齐' })
  if (await start.count()) await start.click()
  else {
    const gapBtn = page.locator('.runtime-gap button, .need-chip, .node-layer').first()
    await page.getByRole('button', { name: /打开第二层|补齐/ }).click().catch(async () => {
      await page.locator('button.node-layer').first().click()
    })
  }
  await page.waitForTimeout(600)
  if (!(await page.getByRole('dialog', { name: /第二层/ }).count())) fail('start-gap-opens-l2', 'L2 did not open')
  if (first) ok('start-gap-opens-l2', 'opened')
  await completeLayer({ addField: first })
  first = false
}

await page.getByRole('button', { name: '打开运行台' }).click()
const desk = page.getByRole('dialog', { name: '运行台' })
await desk.waitFor({ state: 'visible' })
await page.waitForTimeout(600)
let deskText = await desk.innerText()
ok('desk', deskText.slice(0, 280).replace(/\s+/g, ' '))
if (!deskText.includes('来源列表')) fail('protocol-input', 'missing 来源列表')
if (/还有\s*[1-9]\s*步待补齐/.test(deskText)) fail('gaps-after-publish', deskText.slice(0, 200))
ok('gaps-after-publish', 'no remaining gaps')
const histBefore = await page.locator('.runtime-history-item').count()
ok('history-filter', `items=${histBefore}`)

const issue = page.getByRole('button', { name: '签发发行包' })
if (await issue.count() && !(await issue.isDisabled())) {
  await issue.click()
  await page.waitForFunction(() => /指纹/.test(document.body.innerText), null, { timeout: 45_000 })
}
deskText = await desk.innerText()
if (!/已签发/.test(deskText)) fail('signed', deskText.slice(0, 240))
if (!/指纹/.test(deskText) || !/签发于|已验签/.test(deskText)) fail('pack-card', deskText.slice(0, 240))
if (!deskText.includes('下载发行包')) fail('download', 'missing download')
ok('signed', deskText.match(/指纹[^\n]+/)?.[0] || 'signed')
await shot('z-signed')

const sources = page.locator('.runtime-field textarea')
if (!(await sources.count())) fail('sources', 'no textarea')
await sources.fill('https://hnrss.org/newest?q=AI')
const date = page.locator('.runtime-field input[type="date"]')
if (await date.count()) await date.fill(new Date().toISOString().slice(0, 10))
await page.getByRole('button', { name: '关闭运行台' }).click()
await page.getByRole('button', { name: '打开运行台' }).click()
await desk.waitFor({ state: 'visible' })
const again = await page.locator('.runtime-field textarea').inputValue()
if (!again.includes('hnrss')) fail('input-persist', again)
ok('input-persist', again)

const startRun = page.getByRole('button', { name: '开始运行' })
if (await startRun.isDisabled()) fail('start-run', '开始运行 disabled')
await startRun.click()
const blocker = page.getByRole('alertdialog')
await blocker.waitFor({ state: 'visible' })
await page.waitForTimeout(500)
const layerText = await blocker.innerText()
if (!/正在运行|运行完成|运行结束/.test(layerText)) fail('run-layer', layerText.slice(0, 200))
ok('run-layer', layerText.slice(0, 120).replace(/\s+/g, ' '))
await shot('z-running')
const layerFoot = page.locator('.runtime-layer .dialog-foot button')
if (await layerFoot.count()) await layerFoot.click()
else await page.getByRole('alertdialog').getByRole('button').last().click()
await page.getByRole('button', { name: '关闭运行台' }).click()
await page.waitForFunction(() => /运行已完成|没有跑完|运行完成/.test(document.body.innerText), null, { timeout: 60_000 })
ok('toast', (await bodyText()).match(/运行已完成[^\n]{0,80}|没有跑完[^\n]{0,80}/)?.[0] || 'toast')
await shot('z-toast')
await page.getByRole('button', { name: /查看结果/ }).click()
await blocker.waitFor({ state: 'visible' })
const resultText = await blocker.innerText()
if (!/日期|要点|来源|已确认/.test(resultText)) fail('result-fields', resultText.slice(0, 240))
ok('result-fields', resultText.slice(0, 160).replace(/\s+/g, ' '))
const approve = blocker.locator('label.runtime-check input[type="checkbox"]').last()
if (await approve.count()) {
  if (!(await approve.isChecked())) {
    await approve.click({ force: true })
    await page.waitForFunction(() => {
      const box = document.querySelector('.runtime-layer label.runtime-check input[type="checkbox"]')
      return Boolean(box && box.checked)
    }, null, { timeout: 10_000 })
  }
}
await page.locator('.runtime-layer .dialog-foot button').click()
await page.getByRole('button', { name: '打开运行台' }).click()
await desk.waitFor({ state: 'visible' })
await page.waitForTimeout(800)
const hist = page.locator('.runtime-history-item')
await hist.first().waitFor({ state: 'visible', timeout: 15_000 }).catch(() => {})
if (!(await hist.count())) fail('history-after-run', await desk.innerText().then((text) => text.slice(0, 240)))
await hist.first().click()
await page.waitForTimeout(400)
const histText = await desk.innerText()
if (!/已确认/.test(histText)) fail('history-fields', histText.slice(0, 200))
const checked = await page.locator('.runtime-history-item input[type="checkbox"]').first().isChecked().catch(() => false)
if (!checked) fail('approved-persist', '已确认 not checked after reopen')
ok('approved-persist', 'checked')
await shot('z-final')
await page.setViewportSize({ width: 390, height: 844 })
await page.waitForTimeout(400)
await shot('z-mobile')
const mobile = await page.locator('body').innerText()
if (!/开始运行|签发发行包|运行台|已签发/.test(mobile)) fail('mobile', mobile.slice(0, 160))
ok('mobile', 'runtime chrome visible')
await browser.close()
console.log('ACCEPTANCE_DONE')
