# CartridgeFlow 文件用途清单

本清单覆盖清理后的 **202 个项目自有文件**，严格分为 **148 个源码文件**和 **54 个非源码文件**，每个文件只列一次。物理目录中另外存在项目本地依赖、运行数据和构建产物；它们在末尾按目录解释，不逐个枚举第三方包内部文件。

## 废弃审计（2026-07-21）

这里的“候选”表示已经找到删除依据，但本轮没有删除。没有出现在下列审计表中的项目自有文件，当前按“保留”处理。

### 源码：高置信度删除候选

| 文件 | 判断 | 删除前要一起处理 |
|---|---|---|
| `src/core/lab/steward.py` | 旧 Flow Steward 实现；当前界面已经改用 `FlowAssistantPanel` 与 `/api/lab/flows/{id}/assistant`，测试、本机 Flow 和日志均未发现 Steward 使用记录。 | 删除 `src/core/lab/__init__.py` 中的导出、`src/backend/main.py` 中的实例和三个 `/steward/*` 路由，以及 `src/frontend/src/api.ts` 中两个未使用的 Steward 请求函数。 |
| `src/core/lab/steward_llm.py` | 只被旧 `steward.py` 导入，并且内部仍按 CF-FARP 0.3 生成提示。 | 随 `steward.py` 一起删除。 |

这两个文件是目前唯一达到“整文件可删除候选”标准的源码。旧路由可能仍被仓库外调用，因此正式删除前应先完成一次 HTTP API 兼容确认。

### 源码：需要产品决策

| 文件 | 现状 | 建议 |
|---|---|---|
| `src/core/runtime/agent_squad.py` | 已被 `RuntimeManager` 注册，所以不是死代码；但当前前端、测试、文档入口、本机 Flow 和日志均没有实际使用或能力证据。 | 如果多 Agent Runtime 是基座通用能力，补 manifest 示例、测试和能力证据；否则删除该文件及 `src/core/runtime/manager.py` 中的注册。 |

### 非源码：历史归档候选，当前不能删

| 文件组 | 文件 | 当前处理 |
|---|---|---|
| 旧协议正文 | `docs/protocol/CARTRIDGEFLOW_BASE_CONTRACT_v0.1.md`、`docs/protocol/CARTRIDGEFLOW_FLOW_AUTHORING_RUNTIME_PROTOCOL_v0.3.md`、`v0.4.md`、`v0.5.md` | 不再是日常开发入口，也不能运行；在带稳定地址、SHA-256 和迁移说明的外部只读归档建立前继续保留。 |
| 旧协议 Registry | `protocol/CF-FARP-0.1.json` 至 `protocol/CF-FARP-0.5.json` | 当前只用于历史身份识别和迁移；完成外部归档后可移除完整快照，只保留 `protocol_history.json`。 |

### 源码：不是废弃文件，但有遗留代码

| 位置 | 遗留内容 | 处理方向 |
|---|---|---|
| `src/backend/main.py` | `/api/settings` 与 `/api/settings/provider` 明确标为旧版快速设置；当前前端不调用。 | 确认无外部客户端后删除两个路由及专用 payload。 |
| `src/backend/main.py`、`src/frontend/src/api.ts`、`src/core/lab/__init__.py` | 旧 Steward 的路由、请求函数、实例和导出。 | 随两个 Steward 文件一起清理。 |
| `src/core/protocol/flow_contract.py`、`compatibility.py`、`certification.py`、`__init__.py` | 仍保留 v0.2-v0.5 validator、分支和导出；当前基座只支持 v0.6。 | 历史拒绝逻辑收敛到 `protocol_history.json` 后，移除不可达的旧解释器代码。不能删除这些整文件，因为它们同时包含当前 v0.6 实现。 |
| `src/core/lab/mcp/dlc.py`、`src/core/lab/mcp/media_core.py` | 通用媒体工具仍通过名为 DLC 的内部注册器加载，并声明已停止支持的 `CF-FARP@0.4`。 | 保留媒体能力，改为基座 tool pack/module 命名和当前协议元数据。 |
| `src/core/lab/flow_assistant_llm.py` | 当前 Flow Assistant 正在使用，但提示词仍写着 CF-FARP 0.3。 | 将生成约束更新为 CF-FARP 0.6；这是内容升级，不是删文件。 |
| `src/frontend/src/components/DlcSandboxFrame.tsx` | 为旧 DLC UI 继续发送 `load_storyboard`/`load_result`。 | 按 `TODO.md` 的 `UI-001` 增加领域中立消息和显式兼容窗口。 |
| `scripts/tests/history/` 下的 v0.2-v0.4 契约测试 | 已与当前能力测试分离，也不再被 capability evidence 引用；它们仍验证历史规则快照。 | 移除旧 validator 前，将仍有价值的识别、拒绝和迁移断言收敛为更小的历史兼容套件。 |

### 源码：明确保留

- `src/frontend/src/styles/` 下所有样式文件都有导入入口；没有发现孤立 CSS。
- `src/core/runtime/html_generator.py` 和 `src/core/runtime/llm_prompt.py` 都有真实 Flow/Runner 入口。
- `src/core/lab/mcp/media_core.py` 是通用媒体能力，问题是旧命名和协议元数据，不是文件本身无用。

### 非源码：本机状态与生成物

- `.data/user/config/` 下的模型、绑定、凭据和资源文件是本机状态，不是废弃配置，不能随源码清理删除。
- `.tools/`、`.data/`、`src/frontend/node_modules/` 和 `src/frontend/dist/` 分别承担本地工具链、用户与运行数据、前端依赖和可运行构建；它们不属于 202 个项目自有文件。
- `.data/reports/logs/`、`.data/temp/`、`.pytest_cache/`、`__pycache__/`、`*.pyc` 属于可安全清理的运行或缓存生成物。

## 源码（148）

源码分为产品源码和开发维护源码。前者参与应用启动、构建和运行，后者包括测试、测试夹具与自动化脚本；两者都是真正会被解释器、浏览器或命令行执行的代码。

### 启动与构建入口（4）

| 文件 | 作用 |
|---|---|
| `scripts/launch.py` | 同时启动 FastAPI 与 Vite，并打开浏览器的开发启动器。 |
| `run.bat` | Windows 一键引导和启动入口。 |
| `src/frontend/index.html` | Vite HTML 入口、favicon 和 React 根节点。 |
| `src/frontend/vite.config.ts` | Vite 代理、端口和 `src/frontend/dist` 构建输出配置。 |

### 核心包入口（1）

| 文件 | 作用 |
|---|---|
| `src/core/__init__.py` | 标记 `core` 为 Python 包。 |

### 本机数据路径（2）

| 文件 | 作用 |
|---|---|
| `src/core/data_paths.py` | 统一定义 `.data` 的 user/runtime/reports/temp 四区路径，并无覆盖迁移旧布局。 |
| `src/core/local_config.py` | 为本机 JSON 配置提供原子写入、损坏文件备份和安全默认恢复。 |

### 卡带与运行编排（10）

| 文件 | 作用 |
|---|---|
| `src/core/cartridge/__init__.py` | 汇总导出 Registry、Runner、权限、环境和依赖服务。 |
| `src/core/cartridge/artifacts.py` | 创建 Artifact、计算文件信息并构建交付数据。 |
| `src/core/cartridge/dependencies.py` | 解析卡带依赖声明和依赖状态。 |
| `src/core/cartridge/environment.py` | 检查卡带要求的操作系统、命令和环境条件。 |
| `src/core/cartridge/node_normalizer.py` | 把不同版本/写法的节点归一成运行时 Process Node。 |
| `src/core/cartridge/permissions.py` | 汇总和判断卡带请求的权限。 |
| `src/core/cartridge/registry.py` | 发现开发/安装卡带，读取 manifest、flow 和卡带资源。 |
| `src/core/cartridge/root_flow.py` | Root Flow 队列、边、节点进入/完成和暂停/取消状态机。 |
| `src/core/cartridge/runner.py` | 运行总编排：检查、执行、事件、错误、检查点、恢复、回滚和交付。 |
| `src/core/cartridge/validator.py` | 校验 manifest、LLM 配方、MCP 工具和 Portable DLC 声明。 |

### 自动一致性报告（2）

| 文件 | 作用 |
|---|---|
| `src/core/conformance/__init__.py` | 导出一致性报告 API。 |
| `src/core/conformance/reporting.py` | 记录测试结果、合并 capability 证据并生成机器报告。 |

### Portable DLC 隔离宿主（6）

| 文件 | 作用 |
|---|---|
| `src/core/extensions/__init__.py` | 导出 DLC 校验、注册和 Worker 生命周期控制。 |
| `src/core/extensions/descriptor.py` | 读取 descriptor、验证路径/hash/工具/资源和协议 Overlay。 |
| `src/core/extensions/registry.py` | 把当前卡带的 DLC 工具注册为作用域内代理。 |
| `src/core/extensions/worker_bootstrap.py` | 隔离子进程入口，加载卡带 handler 并通过 JSON stdio 返回结果。 |
| `src/core/extensions/worker_client.py` | 启动和监管 Worker，处理 UTF-8、大输出、超时、取消和宿主退出。 |
| `src/core/extensions/worker_sdk.py` | 给卡带 Worker 使用的最小工具注册 SDK。 |

### Flow 开发与测试（15）

| 文件 | 作用 |
|---|---|
| `src/core/lab/__init__.py` | 导出 Flow 图、开发 Flow 管理器和 Steward。 |
| `src/core/lab/builtin_mcp.py` | 通用内置 MCP Registry，提供 filesystem/media 基座工具。 |
| `src/core/lab/dev_flow.py` | 创建、读取、保存和删除 `.data/user/dev_cartridges` 中的开发 Flow。 |
| `src/core/lab/flow_analyzer.py` | 分析 Flow 结构、入口、出口、断链和节点统计。 |
| `src/core/lab/flow_assistant_llm.py` | 把 Flow 助手请求转换成 LLM 提示并解析草稿操作。 |
| `src/core/lab/graph.py` | 把 Root Flow 转成前端可编辑的图模型。 |
| `src/core/lab/mcp/__init__.py` | 标记 MCP 实现目录为包。 |
| `src/core/lab/mcp/dlc.py` | 将通用 media MCP 模块接入内置 Registry。 |
| `src/core/lab/mcp/media_core.py` | 通用本地媒体探测、关键帧处理和产物 QC；外部图像提供商必须由卡带 DLC 接入。 |
| `src/core/lab/mcp/shared.py` | MCP 路径、JSON、命令探测等共享辅助函数。 |
| `src/core/lab/mcp_slots.py` | 归一节点工具槽并生成工具摘要。 |
| `src/core/lab/node_executor.py` | 执行 input、LLM、decision、tool、UI、transfer、delivery 等节点动作。 |
| `src/core/lab/steward.py` | Flow Steward 总入口，生成并应用结构修改建议。 |
| `src/core/lab/steward_llm.py` | Steward 的系统提示、用户提示和模型响应解析。 |
| `src/core/lab/todo.py` | 解析 `TODO.md` 的章节、任务 ID、优先级和完成状态。 |

### 模型适配（9）

| 文件 | 作用 |
|---|---|
| `src/core/llm/__init__.py` | 导出统一聊天调用和模型配置类型。 |
| `src/core/llm/base.py` | 根据 wire API 把统一请求路由到 Chat 或 Responses Provider。 |
| `src/core/llm/config.py` | 定义 Provider/模型运行配置结构。 |
| `src/core/llm/config_manager.py` | 读取、保存、脱敏和解析本地 Provider 与角色绑定。 |
| `src/core/llm/errors.py` | 把模型异常归类为可重试或不可重试错误。 |
| `src/core/llm/importers.py` | 从外部或旧格式导入 Provider 配置。 |
| `src/core/llm/openai_provider.py` | OpenAI 兼容 Chat Completions 调用与流式处理。 |
| `src/core/llm/openai_responses_provider.py` | OpenAI Responses API 的消息转换、工具调用和流式处理。 |
| `src/core/llm/retry.py` | 按本地策略执行 LLM 重试和退避。 |

### 协议实现（9）

| 文件 | 作用 |
|---|---|
| `src/core/protocol/__init__.py` | 汇总导出协议加载、兼容性、认证、Decision 和 Tool Plan API。 |
| `src/core/protocol/base_manifest.py` | 读取并校验 `config/base/BASE_IMPLEMENTATION.json`。 |
| `src/core/protocol/capability_registry.py` | 读取机器协议 registry 并查询支持关系。 |
| `src/core/protocol/certification.py` | 生成认证报告并应用认证标签。 |
| `src/core/protocol/compatibility.py` | 比较基座、卡带、协议、profile、capability 和工具要求。 |
| `src/core/protocol/decision_envelope.py` | 创建、解析和校验 `decision_envelope.v1`。 |
| `src/core/protocol/flow_contract.py` | 校验 CF-FARP 0.2 至 0.6 的 Flow/Process Node 契约。 |
| `src/core/protocol/report.py` | 协议 finding 和严重度汇总公共函数。 |
| `src/core/protocol/tool_plan.py` | 校验模型生成的 `tool_plan.v1` 是否只调用允许工具。 |

### 运行内核（8）

| 文件 | 作用 |
|---|---|
| `src/core/runtime/__init__.py` | 导出错误、检查点和状态迁移公共 API。 |
| `src/core/runtime/agent_squad.py` | 多 Agent Worker/Mentor 运行适配器和产物渲染。 |
| `src/core/runtime/checkpoints.py` | 原子保存节点前后运行、Store、Artifact、事件和上游 revision 快照。 |
| `src/core/runtime/errors.py` | 稳定错误目录、统一错误信封、分类、脱敏和本地堆栈诊断。 |
| `src/core/runtime/html_generator.py` | HTML 生成型卡带的 Runtime Adapter。 |
| `src/core/runtime/llm_prompt.py` | 单次 LLM 提示型卡带的 Runtime Adapter。 |
| `src/core/runtime/manager.py` | 注册 Runtime Adapter 并按 manifest runtime type 启动。 |
| `src/core/runtime/state_machine.py` | 冻结 run、node、interaction 和 tool 的合法状态迁移。 |

### Studio 本地配置与发布（6）

| 文件 | 作用 |
|---|---|
| `src/core/studio/__init__.py` | 导出资源与环境配置 API。 |
| `src/core/studio/environment.py` | 管理本机凭据、环境引用和系统命令检查。 |
| `src/core/studio/hygiene.py` | 扫描源码和包，阻止业务泄漏、密钥、缓存和本机文件进入发布物。 |
| `src/core/studio/release.py` | 生成发布预检和卡带打包结果。 |
| `src/core/studio/resource_resolver.py` | 按卡带资源角色解析本机绑定，生成脱敏摘要并在工具调用时提供私有连接上下文。 |
| `src/core/studio/resources.py` | 读写全局工具、API、数据源和卡带绑定。 |

### 工作区宿主（2）

| 文件 | 作用 |
|---|---|
| `src/core/workspace/__init__.py` | 标记工作区模块为包。 |
| `src/core/workspace/host.py` | 按卡带 workspace 声明创建和管理本地工作区状态。 |

### HTTP 服务（1）

| 文件 | 作用 |
|---|---|
| `src/backend/main.py` | FastAPI 应用、全局异常处理和所有通用 Studio/卡带/运行/DLC HTTP 路由。 |

### 前端公共代码（10）

| 文件 | 作用 |
|---|---|
| `src/frontend/src/api.ts` | 前端全部 HTTP 类型和 API 调用封装。 |
| `src/frontend/src/App.tsx` | 应用路由、左侧导航和页面骨架。 |
| `src/frontend/src/appearance.ts` | 字号、密度和主题偏好的读取与应用。 |
| `src/frontend/src/components/ConfigModal.tsx` | 通用配置弹窗。 |
| `src/frontend/src/components/DlcSandboxFrame.tsx` | 隔离 iframe 宿主和 DLC 消息桥。 |
| `src/frontend/src/index.css` | 按固定顺序导入各页面样式文件。 |
| `src/frontend/src/llmRecipe.ts` | LLM 配方前端类型、默认值和校验辅助函数。 |
| `src/frontend/src/main.tsx` | React、Router、Toast 和外观设置启动入口。 |
| `src/frontend/src/toast.tsx` | 全局轻提示状态与视图。 |
| `src/frontend/src/ui.tsx` | 项目自有的基础 UI 组件封装。 |

### 前端页面（8）

| 文件 | 作用 |
|---|---|
| `src/frontend/src/pages/EnvironmentPage.tsx` | 本机环境、命令和凭据引用页面。 |
| `src/frontend/src/pages/FlowWorkbench.tsx` | 单张 Flow 的设计、测试和模型配方工作区总控制器。 |
| `src/frontend/src/pages/HomePage.tsx` | 全局概览、TODO、协议能力和近期运行页面。 |
| `src/frontend/src/pages/LabPage.tsx` | Flow 列表、创建、导入、克隆和删除页面。 |
| `src/frontend/src/pages/ModelConfigPage.tsx` | 全局本地模型 Provider 配置页面。 |
| `src/frontend/src/pages/ReleasePage.tsx` | 兼容性、预检、打包和发布页面。 |
| `src/frontend/src/pages/ResourceConfigPage.tsx` | 工具/远程 API 与数据来源的共用配置页面。 |
| `src/frontend/src/pages/SettingsPage.tsx` | 字号、密度、风格等全局偏好页面。 |

### Flow 工作台组件（10）

| 文件 | 作用 |
|---|---|
| `src/frontend/src/pages/flow-workbench/FlowAssistantPanel.tsx` | 对话式 Flow 助手、草稿预览和操作应用。 |
| `src/frontend/src/pages/flow-workbench/FlowGraphView.tsx` | React Flow 画布、节点、边、执行高亮和探针拖拽。 |
| `src/frontend/src/pages/flow-workbench/McpLibraryPanel.tsx` | Flow 内 MCP 工具库选择和编辑面板。 |
| `src/frontend/src/pages/flow-workbench/ModelRecipeView.tsx` | 卡带模型角色配方和本机连接绑定视图。 |
| `src/frontend/src/pages/flow-workbench/NodeDrawer.tsx` | 新建节点抽屉和预设选择。 |
| `src/frontend/src/pages/flow-workbench/nodeModel.ts` | 节点分类、预设、默认值和协议显示模型。 |
| `src/frontend/src/pages/flow-workbench/TestBench.css` | 测试台、日志、交互、恢复和产物预览的独立样式。 |
| `src/frontend/src/pages/flow-workbench/TestBenchView.tsx` | 测试运行、探针、日志、交互、恢复和诊断包 UI。 |
| `src/frontend/src/pages/flow-workbench/types.ts` | 工作台局部 TypeScript 类型。 |
| `src/frontend/src/pages/flow-workbench/views.tsx` | 组合 Design/Run 视图和工作台顶部栏。 |

### 前端样式分层（11）

| 文件 | 作用 |
|---|---|
| `src/frontend/src/styles/00-foundation.css` | 色彩 token、重置、应用外壳、侧栏和通用页面框架。 |
| `src/frontend/src/styles/10-workbench-shell.css` | Flow 工作台外壳和助手区域。 |
| `src/frontend/src/styles/20-flow-management.css` | Flow 管理列表、卡片、按钮和状态。 |
| `src/frontend/src/styles/30-workbench-runtime.css` | 运行画布、节点、日志和 Inspector。 |
| `src/frontend/src/styles/40-resource-config.css` | 模型、工具和数据源页面共享控件。 |
| `src/frontend/src/styles/50-workbench-design.css` | 设计工作区和编辑器布局。 |
| `src/frontend/src/styles/60-overview.css` | 概览 TODO、协议、近期运行和文件浏览器。 |
| `src/frontend/src/styles/70-home-and-model.css` | 开发者页面框架和卡带模型配方。 |
| `src/frontend/src/styles/80-overview-layout.css` | 概览密度、100%/110%/125% 和视口适配。 |
| `src/frontend/src/styles/90-environment-release.css` | 环境、凭据、预检和发布页面。 |
| `src/frontend/src/styles/95-config-and-appearance.css` | 配置弹窗、外观和系统设置。 |

### 开发维护源码：当前协议与认证测试（7）

| 文件 | 作用 |
|---|---|
| `scripts/tests/conformance/test_base_manifest.py` | 验证基座声明可以加载。 |
| `scripts/tests/conformance/test_compatibility_report.py` | 验证 capability 和 tool pack 缺失会阻断兼容性。 |
| `scripts/tests/conformance/test_conformance_reporting.py` | 验证报告由真实测试和证据生成，而不是手工通过列表。 |
| `scripts/tests/conformance/test_protocol_certification.py` | 验证当前协议认证条件和认证标签。 |
| `scripts/tests/conformance/test_protocol_extensions.py` | 验证协议 Overlay 的身份、继承和未知扩展阻断。 |
| `scripts/tests/conformance/test_protocol_v06_contract.py` | 验证 Base 0.2、FARP 0.6、资源隔离、认证和 DLC 协议跟随。 |
| `scripts/tests/conformance/test_runtime_contract.py` | 验证当前 manifest 可运行，以及旧 manifest 被明确阻断。 |

### 开发维护源码：运行时测试（11）

| 文件 | 作用 |
|---|---|
| `scripts/tests/runtime/test_builtin_media_core.py` | 验证默认媒体工具保持通用且无卡带业务泄漏。 |
| `scripts/tests/runtime/test_decision_consume.py` | 验证 Decision consume 投影、跳过和 fail-closed。 |
| `scripts/tests/runtime/test_optional_input.py` | 验证 optional input 不被误判为错误。 |
| `scripts/tests/runtime/test_portable_dlc.py` | 验证当前 DLC descriptor、作用域、Worker、完整性和失活。 |
| `scripts/tests/runtime/test_process_nodes.py` | 使用 v0.6 验证 Process Node 合约、执行映射、工具计划和副作用边界。 |
| `scripts/tests/runtime/test_runtime_decision.py` | 验证 Decision Envelope 的 live、mock、blocked 和 needs-input 行为。 |
| `scripts/tests/runtime/test_runtime_errors.py` | 验证错误目录、脱敏、堆栈和跨事件/HTTP 错误身份。 |
| `scripts/tests/runtime/test_runtime_interaction.py` | 使用 v0.6 验证 pending interaction、提交、拒绝和恢复。 |
| `scripts/tests/runtime/test_runtime_recovery.py` | 验证状态迁移、检查点、重试、回滚、副作用确认和失效记录。 |
| `scripts/tests/runtime/test_tool_plan_v1.py` | 验证 Tool Plan 允许列表、参数 schema 和副作用边界。 |
| `scripts/tests/runtime/test_worker_lifecycle.py` | 真实验证 Worker 超时、run 取消和宿主退出。 |

### 开发维护源码：Studio、LLM 与卫生测试（6）

| 文件 | 作用 |
|---|---|
| `scripts/tests/studio/test_studio_environment.py` | 验证凭据遮罩、资源引用和环境预检。 |
| `scripts/tests/studio/test_studio_resources.py` | 验证资源配置归一、ID 和绑定去重。 |
| `scripts/tests/studio/test_studio_todo.py` | 验证 TODO 章节、任务和代码块解析。 |
| `scripts/tests/llm/test_llm_recipe.py` | 验证卡带 LLM 配方可移植且不能携带本机密钥或 URL。 |
| `scripts/tests/llm/test_llm_responses_api.py` | 验证 Responses API 消息、图片、工具和流转换。 |
| `scripts/tests/hygiene/test_clean_base_hygiene.py` | 验证空卡带架、源码所有权、目录边界和发布包卫生。 |

### 开发维护源码：历史协议测试（7）

| 文件 | 作用 |
|---|---|
| `scripts/tests/history/test_protocol_history_compatibility.py` | 验证 v0.2/v0.5 可识别但不可运行或认证。 |
| `scripts/tests/history/test_protocol_v02_flow_contract.py` | 保存 v0.2 Process Node、工具和 effect 规则快照。 |
| `scripts/tests/history/test_protocol_v02_registry.py` | 验证 v0.2 registry 和历史正文缺失状态。 |
| `scripts/tests/history/test_protocol_v03_flow_contract.py` | 保存 v0.3 交互式 Decision 契约快照。 |
| `scripts/tests/history/test_protocol_v03_registry.py` | 验证 v0.3 registry、正文和 capability 快照。 |
| `scripts/tests/history/test_protocol_v04_flow_contract.py` | 保存 v0.4 显式 consume 契约快照。 |
| `scripts/tests/history/test_protocol_v04_registry.py` | 验证 v0.4 完整协议正文和 registry 快照。 |

### 开发维护源码：测试夹具（1）

| 文件 | 作用 |
|---|---|
| `scripts/tests/fixtures/portable_dlc.py` | 为当前协议和运行时测试提供共享的 v0.6 Portable DLC 临时包。 |

### 开发维护源码：自动化脚本（2）

| 文件 | 作用 |
|---|---|
| `scripts/bootstrap.ps1` | 下载并校验固定版本 Python/Node，安装项目本地依赖。 |
| `scripts/run_conformance.py` | 运行全部自动测试并生成机器报告。 |

## 非源码（54）

非源码不直接实现产品行为，包含配置、协议快照、文档、依赖元数据和本机状态说明。它们可以被运行时代码读取，但不应和产品源码放在同一类里。

### 根目录元数据与说明（6）

| 文件 | 作用 |
|---|---|
| `.gitattributes` | 固定文本文件的 Git 行尾和属性行为。 |
| `.gitignore` | 排除本机配置、依赖、运行数据、日志、缓存和构建产物。 |
| `AGENT.md` | AI 自包含快速起点，直接说明项目结构、所有权、运行链路、配置边界、开发规则和验收命令。 |
| `README.md` | 面向项目访客的产品定位、核心能力、适用对象和快速开始。 |
| `requirements.txt` | Python 运行依赖清单。 |
| `VERSION` | 基座正式版本的权威文本值。 |

### 配置（8）

| 文件 | 作用 |
|---|---|
| `config/README.md` | 说明源码配置、默认模板和 `.data/user/config/` 本机状态之间的边界。 |
| `config/base/BASE_IMPLEMENTATION.json` | 当前基座真实支持的 Base Contract、Flow 协议、profile、capability 和 tool pack 声明；Flow 运行支持矩阵只含 CF-FARP v0.6。 |
| `config/base/capability_evidence.json` | 每个已声明 capability 的实现、正反测试和 UI 证据映射。 |
| `config/defaults/llm_retry.json` | LLM 调用的默认重试次数、错误类型和退避参数。 |
| `config/templates/llm/assignments.json` | 不含个人绑定的模型角色配置模板。 |
| `config/templates/llm/providers.json` | 不含真实地址和密钥的 Provider 配置模板。 |
| `config/templates/studio/credentials.json` | 空的本机凭据配置模板。 |
| `config/templates/studio/resources.json` | 空的工具、数据源和绑定配置模板。 |

### 前端构建元数据与静态资源（9）

| 文件 | 作用 |
|---|---|
| `src/frontend/.gitignore` | 排除前端本地构建和工具生成物。 |
| `src/frontend/package.json` | 前端依赖和 dev/build 命令。 |
| `src/frontend/package-lock.json` | 锁定完整 npm 依赖版本。 |
| `src/frontend/public/favicon.svg` | 浏览器标签图标。 |
| `src/frontend/README.md` | 前端职责和独立构建命令。 |
| `src/frontend/tsconfig.app.json` | 浏览器端 TypeScript 编译配置。 |
| `src/frontend/tsconfig.json` | TypeScript 工程引用入口。 |
| `src/frontend/tsconfig.node.json` | Vite 配置文件的 Node TypeScript 设置。 |
| `src/frontend/src/styles/README.md` | 样式文件所有权和级联顺序说明。 |

### 项目文档（16）

| 文件 | 作用 |
|---|---|
| `docs/README.md` | 文档总入口，区分当前文档、历史快照、开发规则和运行产物。 |
| `docs/architecture/PORTABLE_DLC_ARCHITECTURE.md` | Portable DLC 的激活、隔离、资源所有权和不可破坏边界。 |
| `docs/development/README.md` | 开发与维护文档入口，说明根目录 `scripts/` 的结构和常用命令。 |
| `docs/development/AI_DEVELOPER_GUIDE.md` | 深层架构、协议、DLC 和验收参考；不是 AI 接手项目的前置入口。 |
| `docs/development/FILE_INVENTORY.md` | 本文件，逐项解释项目自有文件。 |
| `docs/overview/PROJECT_STRUCTURE.md` | 大白话项目分层、运行链路和架构图。 |
| `docs/planning/ROADMAP.md` | 产品目标、阶段定义、完成标准和长期路线。 |
| `docs/planning/TODO.md` | 当前唯一的可执行任务清单。 |
| `docs/planning/TODO_TEMPLATE.md` | 新建或重构 TODO 时使用的格式模板。 |
| `docs/protocol/GOVERNANCE.md` | 协议修改和 Flow 作者的治理规则。 |
| `docs/protocol/CARTRIDGEFLOW_BASE_CONTRACT_v0.1.md` | 早期基座契约快照和历史语义依据。 |
| `docs/protocol/CARTRIDGEFLOW_BASE_CONTRACT_v0.2.md` | 当前 Base Contract 完整正文。 |
| `docs/protocol/CARTRIDGEFLOW_FLOW_AUTHORING_RUNTIME_PROTOCOL_v0.3.md` | CF-FARP 0.3 已发布协议快照。 |
| `docs/protocol/CARTRIDGEFLOW_FLOW_AUTHORING_RUNTIME_PROTOCOL_v0.4.md` | CF-FARP 0.4 已发布协议快照。 |
| `docs/protocol/CARTRIDGEFLOW_FLOW_AUTHORING_RUNTIME_PROTOCOL_v0.5.md` | CF-FARP 0.5 已发布协议快照。 |
| `docs/protocol/CARTRIDGEFLOW_FLOW_AUTHORING_RUNTIME_PROTOCOL_v0.6.md` | 当前 CF-FARP 0.6 完整协议正文。 |

### 机器协议 Registry（12）

| 文件 | 作用 |
|---|---|
| `protocol/README.md` | 区分当前 registry、历史 draft registry、共享词表和基座支持矩阵。 |
| `protocol/capabilities.json` | 可声明 capability 的机器词汇表。 |
| `protocol/CARTRIDGEFLOW-BASE-0.2.json` | 当前 Base Contract 0.2 注册信息及正文路径。 |
| `protocol/CF-FARP-0.1.json` | CF-FARP 0.1 注册信息。 |
| `protocol/CF-FARP-0.2.json` | CF-FARP 0.2 兼容注册信息；其历史正文不在当前仓库。 |
| `protocol/CF-FARP-0.3.json` | CF-FARP 0.3 注册信息及正文路径。 |
| `protocol/CF-FARP-0.4.json` | CF-FARP 0.4 注册信息及正文路径。 |
| `protocol/CF-FARP-0.5.json` | CF-FARP 0.5 注册信息及正文路径。 |
| `protocol/CF-FARP-0.6.json` | 当前 CF-FARP 0.6 注册信息、Base 依赖和正文路径。 |
| `protocol/profiles.json` | capability 组合成运行 profile 的机器声明。 |
| `protocol/protocol_history.json` | 已识别但不再运行的旧协议版本及其迁移目标。 |
| `protocol/tool_packs.json` | 基座通用 tool pack 的身份和工具集合。 |

### AI Skill 包（3）

| 文件 | 作用 |
|---|---|
| `docs/development/skills/cartridgeflow-protocol-upgrader/SKILL.md` | 协议升级 Skill 的主操作说明。 |
| `docs/development/skills/cartridgeflow-protocol-upgrader/agents/openai.yaml` | Skill 的 Agent 元数据和调用配置。 |
| `docs/development/skills/cartridgeflow-protocol-upgrader/references/upgrade-checklist.md` | 协议升级时逐项核对的检查表。 |

### 本机状态、依赖与生成物目录

| 目录/文件模式 | 所有权与处理方式 |
|---|---|
| `.data/user/` | 用户拥有的 Flow、已安装卡带、包、私有数据和产物；禁止自动清理，应纳入备份。 |
| `.data/runtime/` | 运行记录、检查点和 Worker 状态；活动运行不可清理，历史运行需按保留策略处理。 |
| `.data/reports/` | 服务日志、错误报告和 conformance 报告；可以查看、轮转或重新生成。 |
| `.data/temp/` | 上传和导入缓存；无活动操作时可安全清理。 |
| `.tools/runtimes/` | Bootstrap 安装的项目本地 Python/Node 开发运行时；删除后可重建，但会导致当前开发环境暂时不可运行。 |
| `.tools/downloads/` | Python 和 Node 安装包的下载缓存，可直接清理并在需要时重新下载。 |
| `src/frontend/node_modules/` | npm 第三方依赖，由 `package-lock.json` 和 `npm ci` 重建。 |
| `src/frontend/dist/` | `npm run build` 生成的前端静态文件，后端在无 Vite 时可托管。 |
| `.data/reports/logs/`、`*.log` | 调试和服务日志；可安全轮转。 |
| `.pytest_cache/`、`__pycache__/`、`*.pyc` | 测试/Python 缓存；可安全清理。 |

## 清单维护规则

1. 新增项目文件时，同步在本清单中增加一行。
2. 每个项目自有文件只出现在“源码”或“非源码”中的一处，不按目录重复列出。
3. 删除文件时，先证明没有入口、导入、构建或协议引用，再删除清单行。
4. 已发布协议快照即使不是当前默认版本，也不能当作普通“历史垃圾”删除。
5. `.data` 和本机凭据属于用户状态，不因为源码整理而删除。
