# CartridgeFlow 意图工作室

这里是方向发现与人工审核语义组合界面的 React + TypeScript 实现。它不暴露可执行 Flow 拓扑、运行控制或能力实现细节。

构建命令：

```powershell
npm --prefix src/intent-studio run build
```

生产资源输出到 `src/intent-studio/dist/`，由 FastAPI 在 `/studio` 和 `/projects/{project_id}/studio` 提供。
