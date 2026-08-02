import fs from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..')
const read = (relativePath) => fs.readFile(path.join(root, relativePath), 'utf8')
const failures = []

function expect(source, pattern, message) {
  if (!pattern.test(source)) failures.push(message)
}

const [views, workbench, inspector, overlay] = await Promise.all([
  read('src/frontend/src/pages/flow-workbench/views.tsx'),
  read('src/frontend/src/pages/FlowWorkbench.tsx'),
  read('src/frontend/src/pages/flow-workbench/EngineeringInspector.tsx'),
  read('src/frontend/src/pages/flow-workbench/McpTransparencyOverlay.tsx'),
])

expect(views, /isEngineeringResourceNode/, '工程视图必须识别资源投影节点。')
expect(views, /engineeringResourceLayout/, '工程资源位置必须从工作台接线回灌到投影。')
expect(views, /onEngineeringResourceLayoutSave/, '工程视图必须将拖放后的资源位置上报到工作台。')
expect(views, /document\.addEventListener\('pointerup', captureResourceLayout\)/, '资源位置必须在拖放结束后捕获。')
expect(views, /tool\.presentation_mode && tool\.presentation_mode !== 'local_parsable'/, '外部和不可审计 MCP 不得请求源码。')
expect(views, /\[item\.id, item\.resource_id\]\.includes\(resourceId\)/, '选中 MCP 资源卡时必须能映射回资源目录详情。')
expect(workbench, /cartridgeflow\.engineering-resource-layout\.v1/, '工程资源位置必须以 Flow 为键保存到本地布局元数据。')
expect(workbench, /window\.localStorage\.setItem\(engineeringResourceLayoutStorageKey/, '工程资源位置必须在刷新前同步写入本地存储。')
expect(inspector, /查看连接详情/, '外部 MCP 必须保留连接详情入口。')
expect(inspector, /查看已知契约/, '不可审计 MCP 必须保留已知契约入口。')
expect(inspector, /buildTestFixtureView/, '声明 offline_decision 的节点必须识别测试夹具。')
expect(inspector, /不会发送给真实模型/, '测试夹具面板必须明确不会进入真实模型路径。')
expect(overlay, /localParsable \? <>[\s\S]*?MCP Python 源码/, '源码编辑器必须只属于本地可解析 MCP 分支。')

if (failures.length) {
  console.error(failures.map((failure) => `- ${failure}`).join('\n'))
  process.exit(1)
}

console.log('Engineering view integration assertions passed.')
