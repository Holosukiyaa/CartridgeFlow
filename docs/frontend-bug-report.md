# CartridgeFlow 前端代码 Bug 深度分析报告

> 生成日期：2026-08-01
> 分析范围：`src/frontend/` 全部 35+ 源文件，6.8 万+ 行 CSS，约 15 万行代码
> 分析方法：逐行代码审查 + 依赖追踪 + 执行路径分析

---

## 目录

1. [P0 — 数据安全与完整性](#p0--数据安全与完整性)
2. [P1 — 功能错误](#p1--功能错误)
3. [P2 — 边缘情况](#p2--边缘情况)
4. [P3 — 代码质量与性能](#p3--代码质量与性能)
5. [附录：修复建议](#附录修复建议)

---

## P0 — 数据安全与完整性

### Bug 1：`isEngineeringResource` 与 `isEngineeringResourceNode` 判定逻辑不一致

**文件：** `nodeModel.ts` 第 24-26 行 与 `engineeringNode.ts` 第 85-87 行

```ts
// nodeModel.ts — 用于维度计算
function isEngineeringResource(node: FlowNode) {
  return node.scope === 'engineering_resource' || Boolean(node.params?.engineering_resource)
}

// engineeringNode.ts — 用于连线验证和工程投影
export function isEngineeringResourceNode(node: FlowNode) {
  return node.scope === 'engineering_resource' || node.id.startsWith(ENGINEERING_RESOURCE_PREFIX)
}
```

**问题：** 两个函数对「工程资源节点」的判断条件不同。`nodeModel.ts` 检查 `params.engineering_resource`，`engineeringNode.ts` 检查 `id` 前缀。

**影响：**
- 一个 `params.engineering_resource = true` 但 ID 不含 `__engineering_resource__:` 前缀的节点，在维度计算中被视为资源节点（使用 `resourceDimensions`），但在连线验证中不被视为资源节点（`FlowGraphView.tsx:1055` 使用 `isEngineeringResourceNode`），允许绕过 `RESOURCE_EDGE_REJECT_MESSAGE` 保护
- 反之，一个 `id` 以 `__engineering_resource__:` 开头但 `params.engineering_resource` 为 `false` 的节点，在连线验证中被阻止，但在维度计算中被视为普通节点，分配错误的尺寸

**修复：** 统一两个函数使用同一判定条件。建议统一为 `id.startsWith(ENGINEERING_RESOURCE_PREFIX)` 方式，因为 ID 前缀是更稳定的标识。

---

### Bug 2：多选删除仅处理第一个节点（数据丢失）

**文件：** `FlowGraphView.tsx` 第 1751-1757 行

```tsx
onNodesDelete={async (deletedNodes: FlowGraphNode[]) => {
  if (compactStatic || readOnlyGraph || !onDeleteNode || deletedNodes.length === 0) return
  const node = deletedNodes[0].data as unknown as FlowNode  // ← 只处理第一个！
  // ...
  try { await onDeleteNode(node) } finally { deletingNodeRef.current = false }
}}
```

**问题：** 当用户通过框选（lasso）选择多个节点后按 Delete 键，`deletedNodes` 数组包含多个节点，但代码只处理 `deletedNodes[0]`。React Flow 内部会将所有节点从画布移除，但后端只有第一个节点被删除。

**复现步骤：**
1. 进入设计模式，选择「框选」工具
2. 框选 3 个节点
3. 按 Delete 键
4. 3 个节点从画布消失，刷新页面后 2 个节点重新出现

**根本原因：** `onDeleteNode` 是异步 API 调用，每个节点需要独立删除。遍历 `deletedNodes` 并串行/并行删除即可。

---

## P1 — 功能错误

### Bug 3：Toast 累积泄漏——只自动移除最新 toast

**文件：** `toast.tsx` 第 39-44 行

```tsx
useEffect(() => {
  if (toasts.length === 0) return
  const latest = toasts[toasts.length - 1]
  const timer = setTimeout(() => removeToast(latest.id), 3000)
  return () => clearTimeout(timer)
}, [toasts, removeToast])
```

**问题：** 每次 `toasts` 数组变化时，前一个定时器被清除，然后**只对最新 toast 设置自动移除定时器**。历史 toast 的定时器被清除后不会再恢复。

**复现步骤：**
1. 触发 Toast A（如「保存成功」）→ 显示
2. 在 3 秒内触发 Toast B → Toast A 的定时器被清除
3. Toast A 永久停留在屏幕上，直到手动点击关闭
4. Toast B 3 秒后自动消失

**影响：** 快速连续操作时，历史 toast 堆叠不消失，界面被 toast 阻塞。

**修复：** 为每个 toast 独立设置移除定时器，或使用 `useRef` 存储每个 toast 的定时器 ID。

---

### Bug 4：`onConnect` 添加连线后未处理 API 保存失败（数据丢失）

**文件：** `FlowGraphView.tsx` 第 1758-1785 行

```tsx
onConnect={async (connection: Connection) => {
  // ...
  const nextEdges = addEdge({...}, edges)
  setEdges(nextEdges)                  // 1. 更新本地状态
  flowInstance?.setEdges(nextEdges)    // 2. 更新 React Flow
  await saveEdgesQuietly(nextEdges)    // 3. 保存到后端（无 try/catch）
}}
```

**问题：** 第 1、2 步已经将连线添加到 UI，但第 3 步的 `await saveEdgesQuietly(nextEdges)` 没有 `try/catch`。如果 API 调用失败，连线已显示在画布上但未保存到后端。

**影响：** 用户看到连线存在，但刷新页面后连线消失。用户不会收到任何错误提示（因为 `saveEdgesQuietly` 内部的 `onEdgesSave` 虽然有 `try/catch` 但 `onEdgesSave` 是 `FlowWorkbench.tsx` 中定义的，它没有 `catch` — 实际上 `onEdgesSave` 是 `async (edges) => { const result = await saveFlowEdges(...); updateGraphResult(result) }`，没有 `catch`，所以错误会直接冒泡到 `onConnect` 成为未处理的 Promise rejection）。

**修复：**
```tsx
onConnect={async (connection) => {
  // ...
  try {
    await saveEdgesQuietly(nextEdges)
  } catch (error) {
    // 回滚 UI 状态
    setEdges(edges)  // 恢复到之前的 edges
    flowInstance?.setEdges(edges)
    showToast({ title: '保存连线失败', description: error.message, type: 'error' })
  }
}}
```

---

### Bug 5：`onEdgeDelete`、`onNodeDragStop` 等回调缺少错误处理

**文件：** `FlowGraphView.tsx`
- `deleteEdges` 第 1516-1525 行
- `onNodeDragStop` 第 1734-1750 行
- `handleAutoAlign` 第 1373-1403 行
- `renameBranchEdge` 第 1527-1538 行
- `updateEdgeScope` 第 1540-1554 行

**问题：** 这些回调都包含 `await` 调用，但都没有 `try/catch`。如果 API 失败，错误成为未处理 Promise rejection。

**影响：** 用户操作（如删除连线、拖动节点、重命名分支）可能在 UI 上立即生效，但后端保存失败，刷新后操作丢失。

---

### Bug 6：`DlcSandboxFrame.postMessage` 使用 `'*'` 为目标 origin

**文件：** `components/DlcSandboxFrame.tsx` 第 69-78 行

```tsx
frameRef.current?.contentWindow?.postMessage({
  schema: 'cartridgeflow.dlc_ui_host.v1',
  type: mode === 'result' ? 'load_result' : 'load_storyboard',
  run_id: runId,
  context,       // ← 包含整个 DLC context
  project: payload,  // ← 包含项目数据
  artifacts,     // ← 包含产物信息
}, '*')
```

**问题：** `postMessage` 第三个参数 `targetOrigin` 使用 `'*'`，允许任何窗口监听该消息。虽然消息发送到 iframe 的 `contentWindow`，但恶意页面可以通过 `window.open` 或其他方式监听同源消息。

**严重度：** 较低（因为 iframe 的 `sandbox="allow-scripts"` 限制了恶意行为），但不符合最佳安全实践。

**修复：** 使用具体的 origin 或 `frameRef.current?.src` 解析出的 origin。

---

## P2 — 边缘情况

### Bug 7：`ui.tsx` 颜色常量字符串比较脆弱

**文件：** `ui.tsx` 第 109 行

```tsx
if (color) {
  s.color = color
  if (color === 'fg.muted') s.color = 'var(--cf-text-dim)'
  if (color === 'fg.error') s.color = 'var(--cf-red)'
  if (color === 'fg.success') s.color = 'var(--cf-green)'
}
```

**问题：** 严格字符串比较意味着传入 `color="fg.muted "`（带空格）或 `color="fg.muted!important"` 都不会触发 CSS 变量映射，而是直接设置无效的 CSS 值 `color: fg.muted`。

**影响：** 任何对 `Text` 组件传入变体颜色值的地方都会导致文字颜色不可见或使用默认黑色。

---

### Bug 8：`RunInputDialog` 的 `inputs` 类型不安全

**文件：** `pages/flow-workbench/RunInputDialog.tsx` 第 11 行

```tsx
inputs: any[]
```

**问题：** `inputs` 参数声明为 `any[]`，整个组件内部大量使用 `input.type`、`input.options`、`input.id`、`input.required` 等字段，没有任何类型保护。运行时如果 `input` 对象结构不符合预期，会抛出 `Cannot read properties of undefined` 错误。

**影响：** 如果后端返回的输入定义格式有变化，运行输入对话框会直接崩溃，没有任何降级处理。

---

### Bug 9：`FlowGraphView` 的 `graphEdgesMatch` 按索引而不是按 ID 比较

**文件：** `FlowGraphView.tsx` 第 66-69 行

```tsx
function graphEdgesMatch(current: FlowGraphEdge[], next: FlowGraphEdge[]) {
  if (current.length !== next.length) return false
  return current.every((edge, index) => JSON.stringify(edge) === JSON.stringify(next[index]))
}
```

**问题：** `graphEdgesMatch` 比较两个数组时按索引位置匹配，而不是按边 ID。如果 `next` 数组的元素顺序与 `current` 不同（例如由于 `useMemo` 的依赖变化导致重新排序），即使所有边 ID 相同，`graphEdgesMatch` 也会返回 `false`，触发不必要的 `setEdges` 和 `flowInstance.setEdges` 调用。

**影响：** 不必要的全量边替换，可能导致 React Flow 内部状态重置和视觉效果闪烁。

---

### Bug 10：`FlowGraphView` 的 `useEffect` 同步 `initialEdges` 可能覆盖用户手动添加的边

**文件：** `FlowGraphView.tsx` 第 964-969 行

```tsx
useEffect(() => {
  setEdges((current) => graphEdgesMatch(current, initialEdges) ? current : initialEdges)
  if (flowInstance && !graphEdgesMatch(flowInstance.getEdges() as FlowGraphEdge[], initialEdges)) {
    flowInstance.setEdges(initialEdges)
  }
}, [flowInstance, initialEdges])
```

**问题：** `initialEdges` 来自 `useMemo`，依赖 `graph.edges`（属性）。如果用户通过 `onConnect` 添加了边，`edges` 状态已更新，但 `graph.edges` 属性尚未更新（因为后端 API 调用未完成）。如果此时 `initialEdges` 的任一依赖变化（如 `displayMode` 切换），`initialEdges` 被重新计算，`useEffect` 会将 `edges` 覆盖为 `initialEdges`，**丢失用户刚添加的边**。

**时序：**
1. 用户拖拽连线 → `onConnect` 触发
2. `setEdges(nextEdges)` — 本地状态更新
3. `await saveEdgesQuietly(nextEdges)` — 异步保存（可能耗时 200ms+）
4. 在保存完成前，用户切换显示模式（`displayMode` 变化）
5. `initialEdges` 重新计算（不含新边）
6. `useEffect` 执行 → `setEdges(initialEdges)` → 新边丢失

**修复：** 在 `FlowGraphView` 中维护一个本地已添加但未同步到 `graph.edges` 的边集合，`initialEdges` 与之合并后再比较。

---

### Bug 11：`FlowWorkbench` 的 `pollRunUntilStable` 组件卸载后轮询不中止

**文件：** `FlowWorkbench.tsx` 第 356-385 行

```tsx
const pollRunUntilStable = useCallback(async (runId: string, maxAttempts = 900) => {
  let latest: RunResult | null = null
  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    await sleep(800)
    // ...
    if (['completed', 'failed', 'cancelled', 'interrupted', 'paused', 'paused_waiting_user'].includes(runData.status)) break
  }
  // ...
}, [])
```

**问题：** `maxAttempts = 900` × `800ms` = 720 秒（12 分钟）的最大轮询时间。如果组件在此过程中被卸载，循环不会停止（`sleep` 是 `setTimeout` 的 Promise 封装，没有取消机制）。

**修复：** 使用 `AbortController` 或 `useRef` 标记来在组件卸载时中止轮询。

---

## P3 — 代码质量与性能

### Bug 12：`initialNodes` 和 `initialEdges` 的 `useMemo` 依赖链过长导致频繁重算

**文件：** `FlowGraphView.tsx` 第 736-754 行、第 755-840 行

```tsx
const initialNodes: FlowGraphNode[] = useMemo(() => graph.nodes.map((node) => {
  // ... 依赖 displayMode, graph.nodes, layout, nodeDimensions, nodeRunStates, nodeViewMode
}), [displayMode, graph.nodes, layout, nodeDimensions, nodeRunStates, nodeViewMode])

const initialEdges: FlowGraphEdge[] = useMemo(() => {
  // ... 依赖 dataRelations, displayMode, edgePortPlan, layout, nodeById, runActive, runEdgeStates, visibleGraphEdges
}, [dataRelations, displayMode, edgePortPlan, layout, nodeById, runActive, runEdgeStates, visibleGraphEdges])
```

**问题：** `initialNodes` 依赖 6 个值，`initialEdges` 依赖 8 个值。其中 `nodeRunStates` 每 800ms 轮询变化一次，导致 `initialNodes` 每 800ms 重新计算一次，触发 `useEffect` 同步，导致全量节点替换。

**影响：** 运行时轮询期间，每 800ms 触发一次全量节点替换，可能引起 UI 卡顿。

---

### Bug 13：`FlowGraphView` 组件 `key` 变化导致 React Flow 完全重置

**文件：** `FlowGraphView.tsx` 第 1669 行

```tsx
<ReactFlow<FlowGraphNode, FlowGraphEdge>
  key={`${graph.id}:${displayMode}:${compactStatic ? 'compact' : 'canvas'}`}
  // ...
>
```

**问题：** 当 `displayMode` 从 `'engineering'` 切换到 `'outcome'`（或反之），`key` 属性变化，React 销毁旧的 `ReactFlow` 实例并创建新的实例。这会导致：
- 视口位置丢失
- 选择状态丢失
- 节点展开/折叠状态丢失
- 所有内部状态重置

**影响：** 用户在工程视图和结果视图之间切换时，画布完全重置，丢失所有交互状态。

---

### Bug 14：`InteractionSandboxFrame` 的 `ref` 内联函数导致每次渲染重建

**文件：** `components/InteractionSandboxFrame.tsx` 第 135-137 行

```tsx
<iframe
  ref={(node) => {
    frameRef.current = node
    if (node) node.setAttribute('credentialless', '')
  }}
  // ...
>
```

**问题：** `ref` 回调是内联函数，每次渲染 React 都会调用它（先传入 `null` 清理旧 ref，再传入新节点）。这会导致 `frameRef.current` 被重置为 `null` 再重新设置，但 `onLoad` 事件不会因此重新触发。

**影响：** 虽然是 harmless 的重复调用，但可能干扰 `initialize()` 函数中的 `initializedRef.current` 检查（第 101 行），因为 `ref` 重置并不意味着 iframe 重新加载。

---

## 附录：修复建议

### 优先级矩阵

| 优先级 | Bug 编号 | 影响范围 | 修复难度 | 建议修复方式 |
|--------|----------|----------|----------|-------------|
| P0 | Bug 1 | 安全（连线验证绕过） | 低 | 统一 `isEngineeringResource` 判定逻辑 |
| P0 | Bug 2 | 数据丢失 | 中 | 遍历 `deletedNodes` 串行删除 |
| P1 | Bug 3 | 用户体验 | 低 | 每个 toast 独立定时器 |
| P1 | Bug 4 | 数据丢失 | 中 | `onConnect` 加 `try/catch` + 回滚 |
| P1 | Bug 5 | 数据丢失 | 低 | 所有 `async` 回调加 `try/catch` |
| P1 | Bug 6 | 安全 | 低 | 指定 `targetOrigin` |
| P2 | Bug 7 | 样式 | 低 | 增加 `trim()` 或类型约束 |
| P2 | Bug 8 | 稳定性 | 低 | 增加类型定义和运行时检查 |
| P2 | Bug 9 | 性能 | 低 | 改按 ID 比较 |
| P2 | Bug 10 | 数据丢失 | 中 | 维护本地待同步边集合 |
| P2 | Bug 11 | 稳定性 | 中 | 组件卸载时中止轮询 |
| P3 | Bug 12 | 性能 | 中 | 分离运行状态和节点结构 |
| P3 | Bug 13 | 用户体验 | 中 | 用 `state` 而非 `key` 切换视图 |
| P3 | Bug 14 | 代码质量 | 低 | 使用 `useCallback` 稳定 ref |

### 快速修复示例

**Bug 1 修复（统一 `isEngineeringResource`）：**
```ts
// nodeModel.ts
function isEngineeringResource(node: FlowNode) {
  return node.scope === 'engineering_resource' || node.id.startsWith('__engineering_resource__:')
}
```

**Bug 2 修复（遍历 deletedNodes）：**
```tsx
onNodesDelete={async (deletedNodes: FlowGraphNode[]) => {
  if (compactStatic || readOnlyGraph || !onDeleteNode || deletedNodes.length === 0) return
  deletingNodeRef.current = true
  try {
    for (const graphNode of deletedNodes) {
      const node = graphNode.data as unknown as FlowNode
      if (!node || isEngineeringResourceNode(node) || node.locked || isStartNode(node, node.id)) continue
      await onDeleteNode(node)
    }
  } finally {
    deletingNodeRef.current = false
  }
}}
```

**Bug 3 修复（每个 toast 独立定时器）：**
```tsx
useEffect(() => {
  if (toasts.length === 0) return
  const timers = toasts.map((t) => setTimeout(() => removeToast(t.id), 3000))
  return () => timers.forEach(clearTimeout)
}, [toasts, removeToast])
```

---

*报告结束。共发现 14 个 bug，其中 P0 2 个、P1 4 个、P2 4 个、P3 4 个。*