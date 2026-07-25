import fs from 'node:fs/promises'

const [, , metricsPath] = process.argv
if (!metricsPath) throw new Error('Usage: node assert_node_information_architecture.mjs <capture-metrics.json>')

const metrics = JSON.parse(await fs.readFile(metricsPath, 'utf8'))
const failures = []
const nodes = Array.isArray(metrics.nodePresentations) ? metrics.nodePresentations : []
const details = Array.isArray(metrics.detailPresentations) ? metrics.detailPresentations : []

if (!nodes.length) failures.push('画布没有采集到节点展示模型。')
for (const node of nodes) {
  if (!node.kind) failures.push(`${node.nodeId}: 缺少 data-node-kind。`)
  if (!node.health) failures.push(`${node.nodeId}: 缺少 data-config-health。`)
  if (node.sectionTitles.length !== 3) failures.push(`${node.nodeId}: 主卡必须恰好包含职责、关键事实、流程关系三个内容分区。`)
  if (node.sectionTitles.some((title) => title === '摘要说明' || title === '关键信息')) failures.push(`${node.nodeId}: 仍在使用旧的通用信息标题。`)
  if (node.factLabels.length < 4) failures.push(`${node.nodeId}: 主卡事实不足，无法支持开发判断。`)
}

for (const detail of details) {
  if (['basic', 'type', 'trigger', 'io', 'actions'].includes(detail.section)) failures.push(`${detail.nodeId}: 仍打开了旧通用详情 ${detail.section}。`)
  if (!detail.kind) failures.push(`${detail.nodeId}:${detail.section}: 详情卡缺少节点语义。`)
  if (detail.factLabels.length < 3) failures.push(`${detail.nodeId}:${detail.section}: 详情事实过少。`)
}

if (metrics.contextMenus) {
  const oldSection = ['basic', 'type', 'trigger', 'io', 'actions'].find((section) => metrics.contextMenuHtml?.includes(`data-section=\"${section}\"`))
  if (oldSection) failures.push(`右键菜单仍暴露旧通用详情 ${oldSection}。`)
  if (!metrics.contextMenuHtml?.includes('data-section=')) failures.push('右键菜单没有按节点能力生成详情入口。')
}

if (metrics.page?.scrollWidth > metrics.page?.clientWidth + 1) failures.push('页面出现横向溢出。')
if (metrics.page?.scrollHeight > metrics.page?.clientHeight + 1) failures.push('页面出现纵向溢出。')
if (metrics.canvas?.scrollWidth > metrics.canvas?.clientWidth + 1) failures.push('画布容器出现横向溢出。')
if (metrics.canvas?.scrollHeight > metrics.canvas?.clientHeight + 1) failures.push('画布容器出现纵向溢出。')

if (failures.length) {
  console.error(failures.map((failure) => `- ${failure}`).join('\n'))
  process.exit(1)
}

console.log(`Node information architecture passed: ${nodes.length} nodes, ${details.length} details.`)
