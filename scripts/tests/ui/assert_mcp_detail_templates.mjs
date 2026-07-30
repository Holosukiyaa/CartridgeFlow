import fs from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..')
const read = (relativePath) => fs.readFile(path.join(root, relativePath), 'utf8')
const failures = []

function expect(source, pattern, message) {
  if (!pattern.test(source)) failures.push(message)
}

const [api, types, inspector, overlay, templates] = await Promise.all([
  read('src/frontend/src/api.ts'),
  read('src/frontend/src/api.types.ts'),
  read('src/frontend/src/pages/flow-workbench/EngineeringInspector.tsx'),
  read('src/frontend/src/pages/flow-workbench/McpTransparencyOverlay.tsx'),
  read('src/frontend/src/pages/flow-workbench/McpDetailTemplates.tsx'),
])

expect(api, /fetchFlowResourceDetail/, '前端必须请求资源详情投影。')
expect(api, /checkFlowResourceConnectivity/, '前端必须支持真实连接检查请求。')
expect(types, /presentation_mode\?: McpPresentationMode/, '资源类型必须声明 MCP 呈现模式。')
expect(types, /connector\?: McpConnector \| null/, '资源类型必须声明脱敏连接器详情。')
expect(types, /health\?: McpResourceHealth/, '资源类型必须声明连接和运行健康摘要。')
expect(templates, /local_parsable.*external_connector.*unauditable/s, '详情模板必须区分本地、外部和不可审计 MCP。')
expect(templates, /连接详情/, '外部 MCP 模板必须展示连接详情。')
expect(templates, /调用契约/, '外部 MCP 模板必须展示调用契约。')
expect(templates, /运行轨迹/, '外部 MCP 模板必须展示运行轨迹。')
expect(templates, /不可观测原因/, '不可审计 MCP 必须说明不可观测原因。')
expect(inspector, /mcpPresentationMode === 'external_connector'/, '检查器必须使用外部 MCP 模板。')
expect(inspector, /查看连接详情/, '外部 MCP 的详情入口必须为“查看连接详情”。')
expect(inspector, /mcpPresentationMode === 'unauditable'/, '检查器必须使用不可审计 MCP 模板。')
expect(inspector, /查看已知契约/, '不可审计 MCP 必须只提供已知契约入口。')
expect(overlay, /localParsable \? <>[\s\S]*?MCP Python 源码/, '源码编辑器必须仅位于本地可解析 MCP 分支。')
expect(overlay, /ExternalMcpDetailTemplate/, '外部 MCP 必须使用独立连接详情模板。')
expect(overlay, /UnauditableMcpDetailTemplate/, '不可审计 MCP 必须使用独立已知契约模板。')
expect(overlay, /fetchFlowResourceDetail/, '外部详情必须读取后端脱敏资源投影。')
expect(overlay, /checkFlowResourceConnectivity/, '外部详情必须使用后端连通性检查，而非模拟成功结果。')
expect(overlay, /replaceMcpSource/, '本地 MCP 必须继续保留源码指纹保存入口。')

if (failures.length) {
  console.error(failures.map((failure) => `- ${failure}`).join('\n'))
  process.exit(1)
}

console.log('MCP detail template assertions passed.')
