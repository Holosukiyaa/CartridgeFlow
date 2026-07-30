# CartridgeFlowLite 文件清单

本清单只描述当前 Lite 工程。删除文件、移动所有权或新增长期文件时必须同步更新；缓存、依赖、用户数据和构建产物不逐文件登记。

## 根目录

| 文件 | 作用 |
|---|---|
| `.gitattributes` | 统一文本换行和 Git 属性。 |
| `.gitignore` | 排除用户数据、密钥、依赖、缓存和构建产物。 |
| `AGENT.md` | AI 接手 Lite 工程的自包含快速起点。 |
| `README.md` | 面向开发者的项目介绍和快速启动。 |
| `VERSION` | 当前 Lite 版本。 |
| `requirements.txt` | 后端与自动测试的 Python 依赖。 |
| `run.bat` | 检查系统 Python/Node 并启动工作台。 |

## 配置与协议

| 路径 | 作用 |
|---|---|
| `config/base/BASE_IMPLEMENTATION.json` | 底座真实协议、能力和验证命令声明。 |
| `config/base/capability_evidence.json` | 能力到实现与测试的证据映射。 |
| `config/defaults/llm_retry.json` | 模型调用默认重试策略。 |
| `config/templates/llm/*.json` | 无密钥的模型连接与角色分配模板。 |
| `config/templates/studio/*.json` | 无密钥的凭据与工具资源模板。 |
| `config/README.md` | 配置区与本机数据边界说明。 |
| `protocol/releases/CF-FARP-0.1.json` 至 `CF-FARP-0.9.json` | Flow 协议机器快照；v0.9 是最新规范，v0.8 是当前 Base 支持的上一版，旧版本用于支持、识别或迁移。 |
| `protocol/base/CARTRIDGEFLOW-BASE-0.2.json` | 当前 Base Contract 机器清单。 |
| `protocol/vocabulary/capabilities*.json` | 能力注册表与 0.7/0.8/0.9 版本化快照。 |
| `protocol/vocabulary/profiles*.json` | Profile 注册表与 0.7/0.8/0.9 版本化快照。 |
| `protocol/governance/` | 可变的协议治理说明和历史兼容镜像。 |
| `protocol/catalog/release_manifest.json` | 协议发布的唯一生命周期、默认版本、迁移目标和快照路径来源。 |
| `protocol/tooling/tool_packs.json` | 工具包契约注册表。 |
| `protocol/README.md` | 机器协议目录说明。 |

## 后端入口

| 文件 | 作用 |
|---|---|
| `src/backend/lite_main.py` | Lite FastAPI 入口和 API 白名单。 |
| `src/backend/main.py` | 共享 HTTP 实现；未进入 Lite 白名单的路由不会对外开放。 |

## 核心层

| 路径 | 作用 |
|---|---|
| `src/core/data_paths.py` | 定义 `.data` 用户、运行、报告和临时区路径。 |
| `src/core/local_config.py` | 本机配置加载、保存和脱敏。 |
| `src/core/cartridge/` | 卡带发现、校验、权限、依赖、资产、根 Flow、执行和产物。 |
| `src/core/conformance/reporting.py` | 汇总自动测试并生成能力证据报告。 |
| `src/core/extensions/` | Portable DLC 描述、注册、沙箱渲染、隔离 Worker、v0.9 MCP source model 静态解析与结构化 source editing。 |
| `src/core/lab/dev_flow.py` | 开发 Flow 的创建、读取和保存。 |
| `src/core/lab/graph.py` | Flow 图结构与编辑操作。 |
| `src/core/lab/flow_analyzer.py` | 可达性、孤立节点和结构诊断。 |
| `src/core/lab/ai_steward.py` | AI 管家的结构化上下文、提示构造和响应解析。 |
| `src/core/lab/node_executor.py` | 工作台节点的真实执行入口。 |
| `src/core/lab/todo.py` | TODO Markdown 解析。 |
| `src/core/lab/mcp_slots.py` | Flow 工具槽位和启用清单。 |
| `src/core/lab/builtin_mcp.py`、`mcp/` | 通用 MCP 与媒体/DLC 工具契约。 |
| `src/core/llm/` | 模型配置、导入、检测、Provider、Responses API 和重试。 |
| `src/core/protocol/` | Base 清单、发布清单加载、能力注册、兼容报告、认证、决策信封和工具计划。 |
| `src/core/runtime/` | 状态机、错误、检查点、模型提示、Agent 协作和运行管理。 |
| `src/core/studio/` | 系统环境、工具资源、外部适配、便携性、发布和卫生检查。 |
| `src/core/workspace/host.py` | 卡带工作区宿主能力。 |
| 各目录 `__init__.py` | Python 包边界和稳定导出。 |

## 前端入口与公共层

| 文件 | 作用 |
|---|---|
| `src/frontend/index.html` | Vite HTML 入口。 |
| `src/frontend/package.json`、`package-lock.json` | 前端依赖和锁定版本。 |
| `src/frontend/tsconfig*.json` | TypeScript 构建配置。 |
| `src/frontend/vite.config.ts` | Vite 开发与生产构建配置。 |
| `src/frontend/src/main.tsx` | React 挂载和外观初始化。 |
| `src/frontend/src/App.tsx` | 单一工作台路由入口。 |
| `src/frontend/src/api.ts` | Lite 前端使用的后端请求封装。 |
| `src/frontend/src/api.types.ts` | 前端共享的 API 数据契约。 |
| `src/frontend/src/appearance.ts` | 字体、密度和动效偏好。 |
| `src/frontend/src/ui.tsx` | 共享图标与小型 UI 原语。 |
| `src/frontend/src/toast.tsx` | 全局操作提示。 |
| `src/frontend/src/llmRecipe.ts` | 模型角色与连接表单转换。 |
| `src/frontend/src/components/ConfigModal.tsx` | 工作台配置弹窗。 |
| `src/frontend/src/components/DlcSandboxFrame.tsx` | DLC 前端沙箱宿主。 |
| `src/frontend/src/components/InteractionSandboxFrame.tsx` | 交互节点沙箱宿主。 |

## 工作台

| 文件 | 作用 |
|---|---|
| `src/frontend/src/pages/FlowWorkbench.tsx` | Lite 主界面、状态编排和面板入口。 |
| `flow-workbench/CartridgeWorkspaceControl.tsx` | 当前卡带信息、切换、创建、导入和维护。 |
| `flow-workbench/FlowGraphView.tsx` | React Flow 画布、视口、连线和工具模式。 |
| `flow-workbench/clusterLayout.ts` | 主节点与卫星卡片的节点簇整理、拓扑排布和自适应折行。 |
| `flow-workbench/FlowNodeCard.tsx` | 协议驱动的主节点卡片。 |
| `flow-workbench/FlowNodePorts.tsx` | 节点连接端口。 |
| `flow-workbench/EngineeringNodeCard.tsx`、`engineeringNode.ts` | 工程视图节点、数据/依赖关系和展示模型。 |
| `flow-workbench/EngineeringInspector.tsx` | 工程视图节点检查与字段级选择面板。 |
| `flow-workbench/AIFlowStewardPanel.tsx` | AI 管家引导、委托和结构化变更交互。 |
| `flow-workbench/NodeDetailCard.tsx` | 可拖动、可钉住、共享草稿并按协议分区编辑的节点卫星卡。 |
| `flow-workbench/InteractionAssetEditor.tsx` | 交互卫星内的组件定义与 HTML/Markdown 页面资产编辑。 |
| `flow-workbench/InteractionContractEditor.tsx` | 交互节点的输入字段映射与命名动作静态路由编辑。 |
| `flow-workbench/CartridgeDefinitionPanel.tsx` | 画布配置内的运行入口、模型角色、工具绑定与交付输出编辑。 |
| `flow-workbench/ResourceManagementPanels.tsx` | 模型连接、角色、Flow 工具配置和当前卡带打包面板。 |
| `flow-workbench/RunInputDialog.tsx` | 主工作台运行输入与本地文件上传弹窗。 |
| `flow-workbench/TestBenchView.tsx`、`TestBench.css` | 真实运行、历史、失败日志、恢复和产物。 |
| `flow-workbench/flowNodeView.ts` | 主节点展示模型与状态映射。 |
| `flow-workbench/nodeBuilder.ts` | 节点预设、MCP 绑定和协议字段组装。 |
| `flow-workbench/nodeDetails.ts` | 按节点能力生成详情分区。 |
| `flow-workbench/nodeEditing.ts` | 各卫星分区共享的节点草稿校验与统一保存。 |
| `flow-workbench/nodeAuthoring.ts` | 按节点语义生成画布内引导步骤、进度和完成判定。 |
| `flow-workbench/newFlowSetup.ts` | 新建卡带首次进入工作台时的一次性自动整理标记。 |
| `flow-workbench/nodeModel.ts` | 节点类型、默认值和转换。 |
| `flow-workbench/passiveHtml.ts` | 被动 HTML 资产安全处理。 |
| `flow-workbench/runState.ts` | 运行事件到节点状态及探针范围的纯计算。 |
| `flow-workbench/types.ts` | 工作台本地类型。 |
| `flow-workbench/views.tsx` | 工作台共享视图组件。 |

## 样式

| 文件 | 作用 |
|---|---|
| `src/frontend/src/index.css` | 唯一样式入口和加载顺序。 |
| `styles/00-foundation.css` | 变量、重置、字体和基础控件。 |
| `styles/10-workbench-shell.css` | 页面外壳与共享按钮。 |
| `styles/15-cartridge-workspace.css` | 卡带工作区和切换弹窗。 |
| `styles/30-workbench-runtime.css` | 运行、历史和日志界面。 |
| `styles/50-workbench-design.css` | 画布、节点、详情卡和工具栏。 |
| `styles/95-config-and-appearance.css` | 配置弹窗与保留的外观变量。 |
| `styles/98-reference-theme.css` | 参考主题令牌与弹窗基础。 |
| `styles/99-workbench-reference-shell.css` | Lite 工作台最终覆盖层。 |
| `styles/README.md` | 样式所有权和加载顺序。 |

## 文档

| 路径 | 作用 |
|---|---|
| `docs/README.md` | 文档总入口。 |
| `docs/architecture/AI_STEWARD_INTERACTION_MODES.md` | AI 管家的引导/委托双模式、工程视图定位工具和修改边界。 |
| `docs/architecture/AI_VIDEO_DAILY_CARTRIDGE.md` | AI 视频日报参考卡带的完整闭环、质量门槛、发布安全和版本演进草案。 |
| `docs/architecture/FLOW_NODE_INFORMATION_ARCHITECTURE.md` | 各节点主卡和详情信息架构。 |
| `docs/architecture/FLOW_AUTHORING_ANALYSIS_CONTRACT.md` | Flow 业务流程、执行契约、工程关系三层边界，以及统一分析、强制检测和创作 AI 入口。 |
| `docs/architecture/PORTABLE_DLC_ARCHITECTURE.md` | DLC 所有权、安全和宿主边界。 |
| `docs/development/WORKER_COLLABORATION_GUIDE.md` | 面向操作者的 worker 协作目录、可直接粘贴的启动命令、固定交付报告、验收与受控清理指南。 |
| `docs/development/README.md` | 开发维护区说明。 |
| `docs/development/skills/` | 可选协议升级与 Flow 创作 AI Skill；`cartridgeflow-flow-author` 内含真实工作台创作仿真和目标卡带预检脚本。 |
| `docs/overview/PROJECT_STRUCTURE.md` | 项目分层和数据流。 |
| `docs/planning/ROADMAP.md` | 少量长期方向。 |
| `docs/planning/TODO.md` | 当前高价值任务。 |
| `docs/planning/ENGINEERING_VIEW_RESOURCE_TASK_BRIEF.md` | 工程视图资源化表达、外部 MCP 连接详情、资源节点与自适应布局的实施任务书。 |
| `docs/planning/TODO_TEMPLATE.md` | TODO 基础模板。 |
| `docs/protocol/README.md` | 协议文档导航与目录边界。 |
| `docs/protocol/base-contract/` | Base Contract 的发布正文历史。 |
| `docs/protocol/flow-authoring/` | CF-FARP Flow Authoring 协议的发布正文历史。 |
| `docs/protocol/governance/` | 人类阅读的协议治理规则。 |

## 脚本与测试

| 路径 | 作用 |
|---|---|
| `scripts/bootstrap.ps1` | 使用系统 Python/Node 安装项目依赖，不下载运行时。 |
| `scripts/launch.py` | 启动 Lite 后端和 Vite 工作台。 |
| `scripts/audit_protocol_governance.py` | 全盘校验协议发布清单、历史镜像、快照、Base 声明、发放入口和文档基线。 |
| `scripts/run_conformance.py` | 运行全量测试并写入 conformance 报告。 |
| `scripts/tests/conformance/` | 当前协议、兼容性、能力和认证。 |
| `scripts/tests/history/` | 历史协议识别与迁移规则快照。 |
| `scripts/tests/hygiene/` | 仓库、配置、数据和发布卫生。 |
| `scripts/tests/lite/` | Lite API 白名单。 |
| `scripts/tests/llm/` | 模型配置、导入、检测和调用。 |
| `scripts/tests/runtime/` | 节点执行、错误、恢复、DLC 和 Worker。 |
| `scripts/tests/studio/` | 本机环境、工具绑定、便携性和 TODO。 |
| `scripts/tests/ui/` | 节点信息架构断言和工作台截图。 |
| `scripts/tests/fixtures/` | 跨测试复用夹具。 |

## 不属于源码的目录

| 路径 | 处理规则 |
|---|---|
| `.data/user/` | 用户卡带、配置和产物；默认保留。 |
| `.data/runtime/` | 运行记录与检查点；由运行历史管理。 |
| `.data/reports/` | 日志和自动测试报告；可按需清理。 |
| `.data/temp/` | 导入和上传缓存；可安全清理。 |
| `src/frontend/node_modules/` | npm 依赖；可由 `npm ci` 重建。 |
| `src/frontend/dist/` | 构建产物；不进入 Git。 |
| `__pycache__/`、`.pytest_cache/` | Python 缓存；可安全清理。 |

Lite 不再创建或使用 `.tools/`。开发者负责在系统 PATH 中提供 Python、Node.js 和 npm。
