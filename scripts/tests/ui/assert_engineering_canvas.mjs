import fs from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..')
const read = (relativePath) => fs.readFile(path.join(root, relativePath), 'utf8')
const failures = []

function expect(source, pattern, message) {
  if (!pattern.test(source)) failures.push(message)
}

const [projection, card, graph, model, styles] = await Promise.all([
  read('src/frontend/src/pages/flow-workbench/engineeringNode.ts'),
  read('src/frontend/src/pages/flow-workbench/EngineeringNodeCard.tsx'),
  read('src/frontend/src/pages/flow-workbench/FlowGraphView.tsx'),
  read('src/frontend/src/pages/flow-workbench/nodeModel.ts'),
  read('src/frontend/src/styles/99-workbench-reference-shell.css'),
])

expect(projection, /buildEngineeringResourceNodes\(analyzerRelations\)/, '工程投影必须保留全部资源依赖，包括 MCP 依赖。')
expect(projection, /normalizeResourceKind/, '资源投影必须区分 UI、MCP、模型和工具资源。')
expect(projection, /relation\.kind === 'mcp_dependency'\) return 'mcp'/, 'MCP 依赖不能退化为通用工具资源。')
expect(projection, /referenced_by/, '资源节点必须保留被业务节点引用的摘要。')
expect(card, /function ResourcePreview/, 'UI 资源卡必须提供 HTML 预览组件。')
expect(card, /data-resource-kind/, '资源卡必须暴露资源类别以支持样式和布局回归。')
expect(card, /cf-engineering-node-category/, '业务节点必须渲染中文类别标识。')
expect(graph, /resourcePositions/, '资源节点拖放必须在画布本地状态中保留位置。')
expect(graph, /资源依赖仅用于工程视图，不能写入 Root Flow 控制流/, '连接校验必须拒绝资源进入 Root Flow 控制流。')
expect(graph, /isEngineeringResourceNode\(source\).*isEngineeringResourceNode\(target\)/s, '边保存必须过滤资源节点。')
expect(model, /export function getFlowNodeDimensions/, '自动布局必须使用可预测的内容自适应尺寸。')
expect(model, /nodeDimensions/, '布局计算必须接受每个节点的实际预测尺寸。')
expect(styles, /\.cf-engineering-resource-preview/, 'UI 资源预览必须有专用布局样式。')
expect(styles, /\.cf-engineering-node-category/, '节点类别标识必须有低饱和类别样式。')

if (failures.length) {
  console.error(failures.map((failure) => `- ${failure}`).join('\n'))
  process.exit(1)
}

console.log('Engineering canvas component and layout assertions passed.')
