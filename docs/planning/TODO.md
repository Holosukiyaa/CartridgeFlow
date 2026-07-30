# CartridgeFlowLite TODO

- `DEMO-001`: Create `dev.mcp-transparency-demo` with two parseable DLC MCP nodes to validate v0.9 multi-MCP source transparency.
- `UI-003`: Remove user-facing MCP internal-ID resource nodes from the engineering canvas and localize the engineering-view guidance and headings to Chinese.
- `REL-005`: Publish CartridgeFlow v0.5.3 with the completed v0.9 MCP transparency and engineering-view improvements.

> 当前目标：把完整版收敛为专注卡带开发的轻量工作台，只保留卡带设计、交互、模型与工具配置、真实运行、诊断和产物闭环。

## 当前任务

- `UI-002`：在工程视图为可解析的 v0.9 DLC MCP 节点接入 source model，展示可展开的 operation graph、透明度/来源/运行信息和 Python 源码入口；opaque 与远程工具必须保留真实可见性状态。
- `PROTO-013`：将 `protocol/` 根目录中的机器协议工件按 catalog、base、releases、vocabulary、tooling、governance 分类入目录；同步运行时加载器、发布清单、文档、测试与审计，使根目录不再平铺协议文件。
- `PROTO-012`：整理 `docs/protocol/` 的平铺协议正文，按 Base Contract、Flow Authoring 发布文档和治理规则分类入目录；同步发布清单、文件索引、全部内部引用与治理审计，保持发布内容不变。
- `PROTO-010`：建立统一协议发布清单与全盘治理审计，将协议生命周期、默认新建版本、历史迁移、快照路径和 Base 支持矩阵集中校验，并由 API 向工作台发放。
- `PROTO-011`：整理协议目录，将可变治理镜像集中到 `protocol/governance/`，保持已发布快照与词表的稳定路径，并由全盘审计防止路径回退。
- `UI-001`：修正工作台协议展示，把当前基座目标协议与当前卡带运行协议分开展示，避免旧 v0.7 文案误导。
- `PROTO-009`：将 CF-FARP 协议升级到 v0.9，新增 MCP/DLC 透明执行、可编辑 operation graph、source model、descriptor v3 与 tool transparency 相关快照，保留 v0.8 只读语义。
- `QA-001`：持续执行基础验证、协议/运行链测试、真实浏览器 E2E 与安全审计，修复证据充分的高、中优先级缺陷并完成两轮全量回归。
- `LITE-032`：完善设计台真实运行闭环，包括运行前检查、输入、状态反馈、历史、日志与产物入口。
- `LITE-033`：记录大型 Flow 画布性能瓶颈、分阶段优化方案与性能验收基准，供后续专项实施。
- `ARCH-001`：记录从 Lite 卡带设计工作台走向企业级 AI 能力扩展平台的方向性架构草案。
- `REF-001`：定义 AI 视频日报参考卡带的完整闭环、首版范围、质量门槛与演进梯度。
- `LITE-034`：重构模型管理的三级绑定交互，明确模型 API 资源池、当前 Flow 与具体 AI 节点的递进关系。
- `LITE-035`：在画布工具栏接入当前卡带的发布预检、开发包/生产包生成、下载与打包历史。
- `LITE-036`：清理调试产物、核对长期文件清单并完成提交前构建与测试验证。
- `REL-004`：以 `CartridgeFlow-v0.4.0` 身份发布当前工作台能力，更新正式版本提交并创建 Git 标签。
- `CARD-001`：实战构建 AI 科技日报卡带，跑通真实 RSS 获取、AI 整理、中文配音、竖屏视频合成与成品产物闭环。

## 当前基线

`LITE-001` 至 `LITE-005`、`LITE-008` 至 `LITE-022`、`LITE-024` 至 `LITE-031` 已完成。当前基线已经具备：

- 单一卡带工作台入口，以及卡带切换、新建、导入和维护。
- React Flow 设计画布、节点库、连线、自动整理、选择与拖动画布工具。
- 协议驱动的主节点信息架构、配置健康和按能力生成的详情卫星卡。
- 工作台内模型连接、Flow 模型角色、工具连接和 Flow 工具启用名单。
- 真实运行、暂停、停止、历史、失败日志、恢复和产物查看入口。
- Lite API 白名单、节点 UI 自动断言以及 100%/125% 布局回归。

## 暂不进入 Lite

- 全局统计、全局 TODO 和跨卡带运行诊断。
- 独立资源中心、跨卡带发布管理和生产认证 UI。
- 旧协议迁移与完整版能力证据页面。
- 与卡带开发闭环无关的全局设置。
- AI 助手、自动建议和自动补丁入口。

## 验收边界

- 普通启动直接进入最近使用的卡带；没有卡带时在工作台内创建或导入。
- 开发者可以在一个工作台内完成设计、资源配置、真实运行、交互恢复和产物检查。
- Lite 后端只公开工作台真实使用的能力，缺失能力明确失败，不隐藏降级。
- 前端生产构建和全量自动测试通过。
- `.data`、`.tools`、密钥、日志、依赖和构建产物不进入 Git。
