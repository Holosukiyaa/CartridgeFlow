# 创作者 AI 创作视觉基线

基线 ID：`creator-ai-authoring-visual-2026-08-r2`

状态：已冻结

冻结时间：2026-08-03 16:48 +08:00

视口：1536 x 1024 桌面端

此目录是交付项 `creator-ai-authoring-2026-08` 唯一的视觉参考集。原始探索
包含 18 张图片；下列 6 张被选为规范页面参考。其余 12 个草稿仍是未跟踪的
探索材料，不作为实现输入。

每个页面恰有一张主要参考图。Worker 只能打开其正在实现页面对应的图片；不要
为单个页面任务加载整套图片。

| 界面 | 页面路由 | 必需状态 | 图片 | 来源草稿 | SHA-256 |
| --- | --- | --- | --- | --- | --- |
| 创作者工作室 | `/creator/designs/new` | 已捕获意图和三个来源角色；一个来源未解决；语义草稿尚未接受 | `creator-studio-intent-and-sources.png` | `temp/result/02.png` | `376451e62de399a4c8c81458282867b991aeecb6b4b4b6eb1e588aac9dfdc37c` |
| 创作者工作室 | `/creator/designs/:designId/clarify` | 待回答最少量澄清问题，且已接受的设计状态未改变 | `creator-studio-clarification.png` | `temp/result/03.png` | `3b4b690986ac5f49448062f36d68b221c8797ebe62d92917600c05ab21a63eeb` |
| 创作者工作室 | `/creator/designs/:designId/review` | 已预览 AI 变更集，可选择性接受，并显示影响 | `creator-studio-change-set-review.png` | `temp/result/05.png` | `0f9126d2ddec13ef509a519a1dccae28de793c390f12a8fb9f3f83797bde84aa` |
| 创作者工作室 | `/creator/designs/:designId` | 已接受的修订、混合固化状态、阻塞项可见性和撤销 | `creator-studio-progressive-freeze-and-undo.png` | `temp/result/06.png` | `568401a02d730abd951e108ee8745deff5d6a6d34d4204a1d0b20cda34724ca8` |
| 开发者控制台 | `/developer/flows/:flowId` | 完整工程拓扑、资源、失败项和待处理工程变更 | `developer-console-flow-engineering.png` | `temp/result/01-3.png` | `de70569e509640c951d2eefd6c56d7797dd93c7e5c9d5c2039727e773df83381` |
| 开发者控制台 | `/developer/flows/:flowId/tuning` | 调优修订时间线、精确差异、确定性物化和回滚 | `developer-console-tuning-revision-diff.png` | `temp/result/05-3.png` | `aa46e3799030edc37d51fb316271157e29abb40531169dc0d10c7c82f3c638d4` |

## 已冻结的决策

这些图片是页面构成、信息密度、面板归属、操作层级、画布处理、状态颜色，以及
已接受状态、提案和阻塞项之间可见区分的规范依据。

在相同的语义状态仍清晰时，夹具名称、示例文案和精确数据值可以变化。本基线未
规定低于冻结桌面视口时的响应式行为，须另行提供证据。

视觉相似性不能代替功能验收。每项实现仍须满足 `PLAN.md` 中的协议、API、状态
转换、可访问性和构建门禁。

更改页面分配图片、增加另一张主要图片或改变冻结构成，均须创建新的基线修订，
并在本文件更新图片到页面的映射。
