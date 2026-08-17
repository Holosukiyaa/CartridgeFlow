# CartridgeFlow 意图工作室

这里是方向发现与人工审核语义组合界面的 React + TypeScript 实现。它不暴露可执行 Flow 拓扑、运行控制或能力实现细节。

构建命令：

```powershell
npm --prefix src/intent-studio run build
```

生产资源输出到 `src/intent-studio/dist/`，由 FastAPI 在 `/studio` 和 `/projects/{project_id}/studio` 提供。

## UI 架构

页面只通过 `src/ui/index.ts` 使用通用控件、主题、通知、弹窗和工作台原语。Mantine 负责可访问控件与覆盖层，Allotment 负责桌面三栏尺寸，React Flow 继续独立负责语义节点、连线与视口。`1120px` 及以下切换为单面板 Tabs，不压缩三栏。

面板尺寸保存在浏览器本机；节点位置仍使用原有画布偏好键，两者互不改写。新增 UI 能力应先扩展 `src/ui` 公共入口，领域页面不得直接导入 Mantine 或 Allotment。

本次迁移前生产产物为 JS `505.51 kB`（gzip `160.63 kB`）、CSS `34.56 kB`（gzip `6.29 kB`）。采用 Mantine、Allotment 和 Notifications 后，主入口 JS 为 `625.14 kB`（gzip `198.58 kB`），低频控件与弹窗延迟块合计 `145.02 kB`（gzip `45.41 kB`），CSS 为 `278.97 kB`（gzip `41.93 kB`）。当前接受这项体积成本，以换取统一键盘、焦点、弹窗、主题和可调整布局行为；后续新增依赖不得再引入平行控件或图标系统。

本地验收命令：

```powershell
npm test
npm run build
```

目标视口为 `1920x1080`、`1536x864`、`1120x800` 和 `390x844`；检查页面横向溢出、单面板切换、分隔条持久化、Modal 焦点恢复和画布稳定尺寸。
