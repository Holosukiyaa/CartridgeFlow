# CartridgeFlow 前端清理审查

Date: 2026-07-31

## Scope

本次审查只覆盖 `src/frontend`。我检查了文件树、文件体量与样式使用情况，用 Playwright 走查了主浏览器链路，并执行了生产构建。

## 结论

前端目前功能是活着的，但背着很重的样式债和视图债。最大的问题不是某个页面坏了，而是视觉状态散落在全局 CSS、inline style 和超大的组件文件里。这会让全局样式修改变得昂贵且高风险。

应用仍然可以正常启动，检查到的设计链路可以渲染，运行弹窗可以打开，控制台除了标准的 React DevTools 提示外没有异常，生产构建也能成功。维护风险是结构性的。

## 前端文件树

```text
src/frontend/
  README.md
  index.html
  package-lock.json
  package.json
  public/
    favicon.svg
  src/
    App.tsx
    appearance.ts
    api.ts
    api.types.ts
    components/
      ConfigModal.tsx
      DlcSandboxFrame.tsx
      InteractionSandboxFrame.tsx
    index.css
    llmRecipe.ts
    main.tsx
    storage.ts
    toast.tsx
    ui.tsx
    pages/
      FlowWorkbench.tsx
      flow-workbench/
        AIFlowStewardPanel.tsx
        BrandMark.tsx
        CanvasAnnotationCard.tsx
        CartridgeDefinitionPanel.tsx
        CartridgeWorkspaceControl.tsx
        clusterLayout.ts
        EngineeringInspector.tsx
        EngineeringNodeCard.tsx
        flowNodeView.ts
        FlowGraphView.tsx
        FlowNodeCard.tsx
        FlowNodePorts.tsx
        InteractionAssetEditor.tsx
        InteractionContractEditor.tsx
        McpDetailTemplates.tsx
        McpTransparencyOverlay.tsx
        newFlowSetup.ts
        nodeAuthoring.ts
        nodeBuilder.ts
        nodeDetails.ts
        nodeEditing.ts
        nodeModel.ts
        NodeDetailCard.tsx
        passiveHtml.ts
        ResourceManagementPanels.tsx
        runState.ts
        RunInputDialog.tsx
        TestBench.css
        TestBenchView.tsx
        types.ts
        views.tsx
    styles/
      00-foundation.css
      10-workbench-shell.css
      15-cartridge-workspace.css
      30-workbench-runtime.css
      50-workbench-design.css
      95-config-and-appearance.css
      98-reference-theme.css
      99-workbench-reference-base.css
      99-workbench-reference-engineering.css
      99-workbench-reference-polish.css
      99-workbench-reference-resources.css
      99-workbench-reference-shell.css
      100-mcp-transparency.css
      README.md
```

## 高风险发现

### P1

- 前端仍然由单一的全局基础层统治。`src/frontend/src/styles/00-foundation.css:1-50` 重置了所有内容，强制 `html, body, #root` 使用 `overflow: hidden`，用 `!important` 全局设置 letter-spacing，并且硬编码了滚动条颜色。对于一个视觉语言还要持续演进的产品来说，这个底座太脆了。

- 样式系统已经过载。对 `src/frontend/src` 的扫描发现了 713 处 `!important`、2246 处硬编码颜色或 `rgba()` 字面量，以及 42 处 inline style。最大的文件是 `TestBench.css`（3129 行）、`30-workbench-runtime.css`（2853 行）、`99-workbench-reference-engineering.css`（2520 行）、`FlowGraphView.tsx`（2144 行）、`TestBenchView.tsx`（1334 行）和 `10-workbench-shell.css`（1312 行）。这就是全局字体或颜色一改，样式仍会漏到角落里的根本原因。

- `FlowGraphView.tsx` 是一个上帝文件。它把图形几何、连线路由、注释布局、主题色块、上下文菜单定位、工作区主题编辑全部塞在一个地方（`src/frontend/src/pages/flow-workbench/FlowGraphView.tsx:1821-2032`）。对于一个还要负责实时画布的文件来说，这个职责面太大了。

- `30-workbench-runtime.css` 也是另一个上帝文件，而且它同时在承担多个样式系统的职责。这个文件有 2853 行，包含大量硬编码颜色、断点覆盖和运行态节点的特例样式（`src/frontend/src/styles/30-workbench-runtime.css:177-267`、`:610-611`、`:989-991`、`:2763-2812`）。这意味着运行态样式被页面结构强耦合了。

### P2

- 主题模型只改写了强调色，没有覆盖完整的语义色板。`appearance.ts` 把主题持久化到 `cf.workspace-theme`，仍然迁移 `cf.lite.workspace-theme`，并且只向文档写入 `--accent`、`--accent-dark`、`--accent-soft` 和 `--cf-accent-rgb`（`src/frontend/src/appearance.ts:31-32`、`:35-45`、`:93-108`）。大多数 UI 仍然依赖 CSS 和 TSX 里的硬编码颜色，所以主题变更只做到了部分集中化。

- 旧的 `cf.lite` 存储键仍在活跃迁移中。`src/frontend/src/App.tsx:8-9` 和 `src/frontend/src/appearance.ts:31-32` 展示了这条迁移路径。只有在兼容窗口仍然开放时，这才是可以接受的；否则它就是残留，应在最后一次兼容过渡后移除。

- `api.ts` 功能可用，但比较脆。它总是注入 `Content-Type: application/json`，成功时总是调用 `res.json()`，核心辅助函数里大量使用宽泛的 `any`，并且混用了编码和未编码的路径参数（`src/frontend/src/api.ts:21-39`、`:165`、`:234`）。这会在空响应体场景下出问题，也让 API 回归更难定位。

- `toast.tsx` 有一笔不大但真实存在的 UX / 无障碍债。Toast 通过点击整张卡片来关闭，没有 `role` 或 `aria-live`，而且每当 toast 列表变化时，自动消失计时器都会重新创建（`src/frontend/src/toast.tsx:38-73`）。当前行为能用，但不够稳。

- `package.json` 没有 lint 或测试门禁。当前只定义了 `dev`、`build` 和 `preview`（`src/frontend/package.json:6-10`）。这意味着仓库缺少一种便宜的方式去提前拦住这类样式和链路回归。

- 检查到的浏览器快照里，壳层标题仍然显示 `基座目标 CF-FARP@1.0` 和 `当前卡带 CF-FARP@0.9`。这可能只是 fixture 数据，不一定是代码问题，但它看起来相对当前协议目标是偏旧的，仍然值得确认。

## 链路审查

1. 入口和重定向路径正常。应用打开在 `http://127.0.0.1:5173/cartridges/dev.ai-video-daily/design`，并且在没有控制台错误的情况下渲染出了工作台壳层。

2. 设计链路存在且内容很密。快照显示了工作台头部、设计模式切换、图过滤标签、流程图、资源投影卡片、画布工具栏、缩放控件和小地图。

3. 运行链路可以正常打开。点击 `运行` 后，`运行输入` 弹窗会出现，必填字段在输入前会保持开始按钮禁用。

4. 浏览器健康状态干净。控制台只报告了标准的 React DevTools 信息消息。该页面观察到的网络请求均为 `200 OK`。

5. 在 100% 视图和用于 125% 检查的更小视口下，主壳层都保持了相同结构，没有明显裁切或重叠；不过左侧画布栏和部分图内容离边缘很近，仍然需要持续关注。

## 验证

- `npm --prefix src/frontend run build` 通过。
- Vite 只给出了两个警告：Node 20.18.0 低于它偏好的 20.19+ 下限，以及生成的 JS chunk 超过 500 kB。
- 已对真实前端链路执行了 Playwright 快照和截图。
- 在检查会话中，浏览器控制台显示 0 个错误、0 个警告。

## 清理顺序

1. 先拆 `FlowGraphView.tsx` 和 `30-workbench-runtime.css`。这两个文件承担了最多混杂职责。
2. 引入语义化颜色和排版 token，然后从基础层移除全局的 `letter-spacing` 和 `overflow` 覆盖。
3. 把 `TestBench.css` 和 `TestBenchView.tsx` 拆成按功能划分的模块。
4. 收紧 `api.ts`，统一 typed helper、编码后的路由，以及非 JSON 成功响应的处理。
5. 等不再需要兼容后，移除 `cf.lite` 迁移路径。

## 备注

本次审查没有修改代码。它只是记录当前状态，方便下一轮清理在同一套证据基础上继续推进。
