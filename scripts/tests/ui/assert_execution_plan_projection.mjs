import fs from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..')
const read = (relativePath) => fs.readFile(path.join(root, relativePath), 'utf8')
const failures = []

function expect(source, pattern, message) {
  if (!pattern.test(source)) failures.push(message)
}

const [projection, views, graph] = await Promise.all([
  read('src/frontend/src/pages/flow-workbench/engineeringNode.ts'),
  read('src/frontend/src/pages/flow-workbench/views.tsx'),
  read('src/frontend/src/pages/flow-workbench/FlowGraphView.tsx'),
])

expect(projection, /relation\.kind !== 'execution_plan_edge'[\s\S]*?relation\.runtime_effect !== true[\s\S]*?relation\.executable !== true/, '工程投影只能把编译器确认的 ExecutionPlan 关系作为可执行线。')
expect(projection, /plan_edge_id: planEdgeId/, '每条工程执行线必须保留 plan_edge_id。')
expect(projection, /transition === 'loop_exit'/, '循环退出必须作为同一计划边的显式可视替代路径。')
expect(projection, /options\.executionPlanV1 \? buildExecutionPlanEdges/, 'CF-FARP@1.0 工程图不得回退到旧图边。')
expect(views, /isExecutionPlanV1/, '工程视图必须识别 CF-FARP@1.0。')
expect(views, /analyzeLabFlow<ExecutionPlanAnalysis>/, '工程视图必须通过统一 API 请求 Analyzer 的 ExecutionPlan 投影。')
expect(views, /旧连线不会显示为运行路线/, '未编译计划必须明确告知旧连线不会成为运行路线。')
expect(views, /executionPlanV1 \|\| engineering \? engineeringGraph : graph/, '1.0 引导视图也必须使用计划投影，不能重新显示旧运行线。')
expect(graph, /plan-edge-\$\{planEdgeId\}/, '画布边 DOM 标识必须携带计划边身份。')
expect(graph, /planEdgeId,[\s\S]*?planEdgeKind,[\s\S]*?planTransition/, '画布边数据必须保留计划边身份与转移类型。')

if (failures.length) {
  console.error(failures.map((failure) => `- ${failure}`).join('\n'))
  process.exit(1)
}

console.log('ExecutionPlan engineering projection assertions passed.')
