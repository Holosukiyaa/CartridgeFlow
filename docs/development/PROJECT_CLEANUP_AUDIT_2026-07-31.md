# CartridgeFlow 全仓清理审计（2026-07-31）

## 范围与结论

本报告审阅了审计开始时全部 303 个 Git 跟踪文件，并对 Python、TypeScript/TSX、CSS、JSON、脚本和 Markdown 做了内容、入口、静态引用及测试交叉检查。`.git`、`.data/`、`node_modules/`、`dist/`、缓存和构建输出不属于可提交源码，未列为删除候选。

当前工作树已有 35 个已修改文件和一个未跟踪的 `scripts/tests/conformance/test_protocol_v10_completeness.py`，内容是在推进 `CF-FARP@1.0`。它们不是本次审计产生的修改；本报告不建议在该协议迁移完成前混入删除或重构。

**总判断：** `Lite` 不是一个可以直接全局替换的普通遗留词，而是一套已经失真的产品边界。它同时作为应用名、启动入口、API 网关、测试目录、文档规则和 localStorage 前缀存在；但已不再可靠地限制产品能力。清理应先明确产品是否仍是“受限 Lite 工作台”。根据当前代码、路线图、AI 管家、工程视图和个人运行台目标，推荐将正式产品统一为 **CartridgeFlow 开发台**，并以显式迁移替代继续叠加 Lite 例外。

## 已验证发现

### P0：Lite 的声明边界与实际暴露能力冲突

`AGENT.md`、`README.md`、`docs/development/FILE_INVENTORY.md` 和 `src/backend/lite_main.py` 都宣称 Lite 不包含 AI 管家。实际前端却渲染 `AIFlowStewardPanel`，它调用 `POST /api/lab/flows/{cartridge_id}/ai-steward`；该路由也存在于 `src/backend/main.py`。

`lite_main.py` 的规则 `^/api/lab/flows(?:/.*)?$` 放行整个 Flow 子树，但 `_REMOVED_WORKBENCH_PATHS` 只阻止路径含 `/assistant`、`/steward/` 或 `/certification`。真实路径为 `/ai-steward`，不会命中阻止条件。因此“Lite 禁用 AI 管家”的承诺为假；现有 Lite API 测试也只测了不存在的 `/steward/suggest`，没有覆盖真实端点。

**处理：** 先作产品决策。若保留 Lite，必须收紧白名单、删除/隐藏 AI 管家 UI、删除端点或将其改名后加入明确禁用测试。若 Lite 是遗留概念，删除 `lite_main.py` 的白名单门面并将安全边界移入正式权限/能力模型，同时改名所有启动、测试、文档和存储键。两种方案不能并存。

### P1：前端 API 与后端路由保留了不可达的完整版本表面

`src/backend/main.py` 有 111 个 HTTP 路由；Lite 中间件让一部分路由永远返回 `LITE_CAPABILITY_NOT_AVAILABLE`。`src/frontend/src/api.ts` 仍导出 27 个当前 TS/TSX 调用方为零的 API：

```text
activateLlmProvider, applyLabFlowCertification, createCartridgeRun,
createMcpTool, deleteCartridgeAsset, deleteCartridgeRun,
deleteInteractionComponent, deleteMcpTool, deleteStudioCredential,
detectLlmProvider, fetchCartridgeCertification, fetchCartridgeCompatibility,
fetchCartridgeRunDiagnostics, fetchCartridgeRuns, fetchCartridges,
fetchLabFlowCertification, fetchLabFlowCompatibility, fetchLlmProviders,
fetchMcpSourceModel, fetchStudioConformance, fetchStudioTodo,
fetchStudioTodoFile, fetchStudioTodoTemplate, previewLabFlowGraph,
uninstallInstalledCartridge, updateMcpTool, updateStudioCredential,
validateLabFlow
```

这些导出掩盖了“前端允许什么”和“后端实际提供什么”的差异，也提高了后续误接回全局页面的概率。

**处理：** 在 Lite 去留决策后，将 API 合约改为按当前 UI 导出的最小集合；随后删除无调用方的前端导出、不可达路由及其专属 Pydantic payload/helper。每删除一个路由，更新 API 表面测试；不要只从前端删掉函数。

### P1：旧 TestBench 主视图已经失联，但其代码和 CSS 仍被整体加载

`TestBenchView.tsx` 为 1,289 行、62 KB。当前唯一外部引用是从中导入 `PendingInteractionForm`；`TestBenchView` 本身没有调用方。主工作台已在 `FlowWorkbench.tsx` 和 `views.tsx` 内实现运行、历史、日志、产物和恢复交互。

关联的 `TestBench.css` 为 2,733 行、63 KB，其中静态 class-name 检查发现 201 个 `cf-*` 类有 71 个不再出现在 TS/TSX。诊断面板、决策信封、数据 modal 和完整运行模式是明确的失联组；同名 `.cf-data-modal*` 还与 `30-workbench-runtime.css` 重复。

**处理：** 先把 `PendingInteractionForm` 移到独立的小组件及其最小样式，再删除未引用的 `TestBenchView` 主组件；仅保留现有 `FlowWorkbench`/`views.tsx` 所需的运行 CSS。此项必须配合 UI 截图断言与 100%/125% 缩放检查，不能用纯文本搜索直接删整份 CSS。

### P1：样式层保留大批已删除页面的选择器

所有样式由 `index.css` 无条件加载。基于当前 TS/TSX 中的 class literal，以下文件的 `cf-*` 选择器没有命中比例很高（动态类名可能造成少量假阳性，故均为“待视觉验证的删除候选”）：

| 文件 | `cf-*` 类数 | 无静态调用方 | 主要残留 |
| --- | ---: | ---: | --- |
| `styles/98-reference-theme.css` | 153 | 146 | overview、diagnostics、settings、旧资源中心 |
| `styles/95-config-and-appearance.css` | 102 | 98 | 全局设置、overview、旧模型/凭据页；保留 `html[data-cf-*]` 外观变量 |
| `styles/30-workbench-runtime.css` | 176 | 148 | 旧 TestBench、数据链与左侧运行面板 |
| `styles/10-workbench-shell.css` | 92 | 74 | 旧节点抽屉、概览、能力面板 |
| `styles/50-workbench-design.css` | 24 | 21 | 旧 MCP drawer/library |
| `styles/00-foundation.css` | 16 | 15 | 已移除的 sidebar/nav |
| `TestBench.css` | 201 | 71 | 已失联 TestBench 区域 |
| `styles/99-workbench-reference-shell.css` | 251 | 21 | 少量旧 drawer/resource 类；其余仍是当前画布外壳 |

`styles/README.md` 已承认 `98`、`99` 是“final/reference”补丁层，这种覆盖式命名会继续掩盖所有权。`98-reference-theme.css` 和 `95-config-and-appearance.css` 中的 overview/settings 规则在当前 UI 中没有实现。

**处理：** 不再新增编号补丁 CSS。清理时先把仍有效规则归并到 `foundation`、`workbench-shell`、`runtime`、`design` 的所属文件，再逐组删除无调用方规则；最后删除 `98-reference-theme.css`，并将 `99` 重命名为实际职责名。每步运行构建、UI 断言和截图对比。

### P1：协议升级已改变事实，但维护文档仍保留旧叙述

当前未提交工作树将 `CF-FARP@1.0` 标为 `current/active/supported`，并把默认新 Flow 改为 1.0；但 `docs/development/FILE_INVENTORY.md` 仍写“v0.9 是当前正式规范，v1.0 未执行支持的草案”，`TODO.md` 的已完成 `ORCH-001` 也仍称 1.0 为 draft/unsupported，`ROADMAP.md` 的阶段 A 完成标准仍引用 v0.7。

这不是历史快照，而是当前入口文档之间的矛盾。`FILE_INVENTORY.md` 自称“当前 Lite 工程”，却只以目录通配描述文件；对 303 个跟踪文件做精确路径比对时有 227 个不在该文档中逐项出现，无法承担“完整文件清单”的职责。

**处理：** 协议升级提交前，执行一次“当前事实”文档同步：入口、路线图、TODO、文件清单、技能说明、发布清单和 Base 证据必须一致。发布历史正文和机器快照不可改写；当前说明应只引用 `release_manifest.json` 的当前版本。

### P1：名为 conformance 的总入口没有覆盖编排和 Lab 测试

`scripts/run_conformance.py` 只发现 `conformance`、`runtime`、`studio`、`llm`、`lite`、`hygiene`、`history` 七组，不包含：

- `scripts/tests/orchestration/test_execution_plan_compiler.py`：ExecutionPlan 编译与确定性关键测试；
- `scripts/tests/lab/test_flow_analyzer_execution_plan_projection.py`：执行计划工程投影测试；
- `scripts/tests/ui/*.mjs`：浏览器外壳/节点/工程视图断言。

因此 `python scripts/run_conformance.py` 成功不等于当前编排语义或 UI 全部通过。审计时三项被排除测试单独运行均通过，但这个入口命名会误导后续清理和发布判断。

**处理：** 将 `lab`、`orchestration` 加入正式 Python 验证入口，另增加明确的 `ui` 命令或让 CI 调用 UI 断言。报告应区分 unit/conformance/UI，不再把一个脚本称作全量验证。

### P2：存在第二套旧 Runtime adapter 路径，应隔离后再决定删除

`CartridgeRunner` 除了 Root Flow/NodeExecutor 路径外，还在 `run` 状态调用 `RuntimeManager.start()`。后者注册 `HtmlGeneratorRuntime`、`LlmPromptRuntime` 和 467 行的 `AgentSquadRuntime`。

`html_generator` 仍被 `DevFlowManager` 的默认模板使用，不能直接删；但 `agent_squad` 与 `llm_prompt` 没有默认模板、前端入口或直接测试，只是被管理器注册。两者承载了早期的“一个 Runtime 直接产物”模型，与当前 Flow 节点/令牌执行模型重叠。`LlmPromptRuntime` 还把异常转换为 error artifact，再由 Runner 解释状态，责任边界不如 NodeExecutor 清晰。

**处理：** 先在 `.data/user` 的真实卡带清单中做只读使用审计，再将仍需兼容的 runtime type 明确标为 legacy adapter 并增加迁移提示；没有用户卡带引用时，移除 `agent_squad`、`llm_prompt`、注册表条目和 `/api/runtimes`。不要因为源码无调用方而跳过用户数据迁移。

### P2：当前工具链版本与构建声明不一致

前端构建通过，但 Vite 8 警告宿主 Node 为 `20.18.0`，最低要求为 `20.19+` 或 `22.12+`。`bootstrap.ps1` 只检查 Node 是否存在，不验证版本。构建还产生 766 KB 的单一 JS chunk（gzip 236 KB）和 347 KB CSS（gzip 59 KB）。

**处理：** 将 Node 最低版本写入 bootstrap 和 README；完成 CSS/TestBench 清理后重新测量。只有在导航/面板边界稳定后再用动态 import 分包，避免在清理期引入行为回归。

## 必须保留的内容

以下“旧”内容有明确兼容、证据或迁移职责，不能纳入第一轮删除：

- `protocol/releases/CF-FARP-0.1.json` 到 `0.9.json`、对应 vocabulary JSON、历史 Flow 协议正文和 `scripts/tests/history/`：发布快照、迁移识别和兼容测试。
- `src/core/data_paths.py` 的 `LEGACY_*_MOVES`：用户本机数据布局迁移；删除前必须证明所有已安装版本已迁移。
- `legacy_opaque`、旧拓扑校验和协议 compatibility 分支：在旧协议仍受识别/兼容时是诚实降级，不能与 UI 遗留代码混淆。
- `AI_VIDEO_DAILY_CARTRIDGE.md` 和个人运行台/CF-CRE 文档：是延后业务卡带与发行目标的设计证据，不是嵌入底座的业务实现。
- `src/core/runtime/html_generator.py`：当前默认开发 Flow 模板仍引用它；应先替换模板或给出迁移，不能孤立删除。

## 建议的清理顺序

1. **冻结并独立完成 FARP-100。** 不将协议状态升级、旧设计删除和改名放入同一提交；先让当前工作树通过全部 Python、UI 和治理验证。
2. **确立产品名与 API 边界。** 推荐正式名为 `CartridgeFlow`；若采纳，迁移 localStorage 的 `cartridgeflow.lite.*`/`cf.lite.*` 键后移除 Lite 启动器、白名单和测试目录命名。若不采纳，先修复 AI 管家泄漏并删掉全部非 Lite 表面。
3. **删除失联 UI。** 拆出 `PendingInteractionForm`，删除旧 TestBench 主体和专属 CSS；逐组清理 `98`、`95`、`30`、`10`、`50` 的无引用选择器，保留截图基线。
4. **收敛 API 与运行时。** 最小化 `api.ts`/`api.types.ts`，删除不可达路由；再对 `agent_squad` 与 `llm_prompt` 做真实用户卡带引用审计和兼容迁移。
5. **收敛文档与验证入口。** 让 `FILE_INVENTORY.md` 改为可生成的精确清单或明确其只是导航；修复 v0.7/v0.9/1.0 叙述；把 lab、orchestration、UI 纳入正式验证矩阵。
6. **最后处理历史协议。** 只有在独立归档具备稳定 URL、SHA-256、迁移说明及外部引用确认后，才从主开发树移动已发布快照。

## 审计时的验证结果

```powershell
python scripts/run_conformance.py --quiet
# 322 tests passed

python -m unittest discover -s scripts/tests/lab -p "test_*.py" -v
# 3 tests passed

python -m unittest discover -s scripts/tests/orchestration -p "test_*.py" -v
# 5 tests passed

npm --prefix src/frontend run build
# passed; Node/Vite version and chunk-size warnings remain
```

## 完整文件树

以下为审计开始时的 303 个 Git 跟踪文件；未跟踪的 1.0 completeness 测试列在树后。

```text
CartridgeFlow/
  .gitattributes
  .gitignore
  AGENT.md
  MENTOR_WORKERS.md
  README.md
  VERSION
  requirements.txt
  run.bat
  config/
    README.md
    base/BASE_IMPLEMENTATION.json
    base/capability_evidence.json
    defaults/llm_retry.json
    templates/llm/assignments.json
    templates/llm/providers.json
    templates/studio/credentials.json
    templates/studio/resources.json
  docs/
    README.md
    architecture/AI_STEWARD_INTERACTION_MODES.md
    architecture/AI_VIDEO_DAILY_CARTRIDGE.md
    architecture/FLOW_AUTHORING_ANALYSIS_CONTRACT.md
    architecture/FLOW_NODE_INFORMATION_ARCHITECTURE.md
    architecture/N8N_ORCHESTRATION_BENCHMARK_REPORT.md
    architecture/PERSONAL_RUNTIME_DISTRIBUTION_ARCHITECTURE.md
    architecture/PORTABLE_DLC_ARCHITECTURE.md
    development/FILE_INVENTORY.md
    development/PERSONAL_RUNTIME_CF_CRE_HANDOFF_GUIDE.md
    development/README.md
    development/WORKER_COLLABORATION_GUIDE.md
    development/skills/cartridgeflow-flow-author/SKILL.md
    development/skills/cartridgeflow-flow-author/agents/openai.yaml
    development/skills/cartridgeflow-flow-author/references/authoring-checklist.md
    development/skills/cartridgeflow-flow-author/scripts/preflight_flow.py
    development/skills/cartridgeflow-flow-author/scripts/simulate_authoring.ps1
    development/skills/cartridgeflow-protocol-upgrader/SKILL.md
    development/skills/cartridgeflow-protocol-upgrader/agents/openai.yaml
    development/skills/cartridgeflow-protocol-upgrader/references/upgrade-checklist.md
    overview/PROJECT_STRUCTURE.md
    planning/ENGINEERING_VIEW_RESOURCE_TASK_BRIEF.md
    planning/ORCHESTRATION_EXECUTION_TASK_BRIEF.md
    planning/ROADMAP.md
    planning/TODO.md
    planning/TODO_TEMPLATE.md
    protocol/README.md
    protocol/base-contract/CARTRIDGEFLOW_BASE_CONTRACT_v0.1.md
    protocol/base-contract/CARTRIDGEFLOW_BASE_CONTRACT_v0.2.md
    protocol/flow-authoring/CARTRIDGEFLOW_FLOW_AUTHORING_RUNTIME_PROTOCOL_v0.3.md
    protocol/flow-authoring/CARTRIDGEFLOW_FLOW_AUTHORING_RUNTIME_PROTOCOL_v0.4.md
    protocol/flow-authoring/CARTRIDGEFLOW_FLOW_AUTHORING_RUNTIME_PROTOCOL_v0.5.md
    protocol/flow-authoring/CARTRIDGEFLOW_FLOW_AUTHORING_RUNTIME_PROTOCOL_v0.6.md
    protocol/flow-authoring/CARTRIDGEFLOW_FLOW_AUTHORING_RUNTIME_PROTOCOL_v0.7.md
    protocol/flow-authoring/CARTRIDGEFLOW_FLOW_AUTHORING_RUNTIME_PROTOCOL_v0.8.md
    protocol/flow-authoring/CARTRIDGEFLOW_FLOW_AUTHORING_RUNTIME_PROTOCOL_v0.9.md
    protocol/flow-authoring/CARTRIDGEFLOW_FLOW_AUTHORING_RUNTIME_PROTOCOL_v1.0.md
    protocol/governance/GOVERNANCE.md
    protocol/release-envelope/CARTRIDGEFLOW_RELEASE_ENVELOPE_PROTOCOL_v1.md
  protocol/
    README.md
    base/CARTRIDGEFLOW-BASE-0.2.json
    catalog/release_manifest.json
    governance/README.md
    governance/protocol_history.json
    releases/CF-CRE-1.json
    releases/CF-FARP-0.1.json
    releases/CF-FARP-0.2.json
    releases/CF-FARP-0.3.json
    releases/CF-FARP-0.4.json
    releases/CF-FARP-0.5.json
    releases/CF-FARP-0.6.json
    releases/CF-FARP-0.7.json
    releases/CF-FARP-0.8.json
    releases/CF-FARP-0.9.json
    releases/CF-FARP-1.0.json
    tooling/tool_packs.json
    vocabulary/capabilities.json
    vocabulary/capabilities-0.7.json
    vocabulary/capabilities-0.8.json
    vocabulary/capabilities-0.9.json
    vocabulary/capabilities-1.0.json
    vocabulary/profiles.json
    vocabulary/profiles-0.7.json
    vocabulary/profiles-0.8.json
    vocabulary/profiles-0.9.json
    vocabulary/profiles-1.0.json
    vocabulary/release-envelope-capabilities-1.json
    vocabulary/release-envelope-profiles-1.json
  scripts/
    audit_protocol_governance.py
    bootstrap.ps1
    demo_cf_cre_runtime_handoff.py
    demo_personal_runtime.py
    launch.py
    run_conformance.py
    run_lite_node_coverage.py
    tests/conformance/test_base_manifest.py
    tests/conformance/test_compatibility_report.py
    tests/conformance/test_conformance_reporting.py
    tests/conformance/test_mcp_source_editing_v09.py
    tests/conformance/test_mcp_transparency_v09.py
    tests/conformance/test_personal_runtime_demo.py
    tests/conformance/test_protocol_certification.py
    tests/conformance/test_protocol_extensions.py
    tests/conformance/test_protocol_release_governance.py
    tests/conformance/test_protocol_v06_contract.py
    tests/conformance/test_protocol_v07_specification.py
    tests/conformance/test_protocol_v08_runtime.py
    tests/conformance/test_protocol_v08_specification.py
    tests/conformance/test_protocol_v09_specification.py
    tests/conformance/test_protocol_v10_execution_plan.py
    tests/conformance/test_release_builder.py
    tests/conformance/test_release_envelope_protocol.py
    tests/conformance/test_resource_catalog_v08.py
    tests/conformance/test_runtime_contract.py
    tests/fixtures/portable_dlc.py
    tests/history/test_protocol_history_compatibility.py
    tests/history/test_protocol_v02_flow_contract.py
    tests/history/test_protocol_v02_registry.py
    tests/history/test_protocol_v03_flow_contract.py
    tests/history/test_protocol_v03_registry.py
    tests/history/test_protocol_v04_flow_contract.py
    tests/history/test_protocol_v04_registry.py
    tests/hygiene/test_clean_base_hygiene.py
    tests/lab/test_flow_analyzer_execution_plan_projection.py
    tests/lite/test_lite_api_surface.py
    tests/llm/test_llm_config_manager.py
    tests/llm/test_llm_connection.py
    tests/llm/test_llm_detection.py
    tests/llm/test_llm_recipe.py
    tests/llm/test_llm_responses_api.py
    tests/orchestration/test_execution_plan_compiler.py
    tests/runtime/test_builtin_filesystem.py
    tests/runtime/test_decision_consume.py
    tests/runtime/test_execution_token_runner.py
    tests/runtime/test_interaction_assets.py
    tests/runtime/test_optional_input.py
    tests/runtime/test_portable_dlc.py
    tests/runtime/test_process_nodes.py
    tests/runtime/test_runtime_decision.py
    tests/runtime/test_runtime_errors.py
    tests/runtime/test_runtime_interaction.py
    tests/runtime/test_runtime_recovery.py
    tests/runtime/test_sandboxed_interaction.py
    tests/runtime/test_tool_plan_v1.py
    tests/runtime/test_worker_lifecycle.py
    tests/studio/test_ai_steward.py
    tests/studio/test_external_adapters.py
    tests/studio/test_flow_tool_bindings.py
    tests/studio/test_portability.py
    tests/studio/test_resource_catalog_eng021.py
    tests/studio/test_studio_environment.py
    tests/studio/test_studio_flow_directory.py
    tests/studio/test_studio_resources.py
    tests/studio/test_studio_todo.py
    tests/ui/assert_engineering_canvas.mjs
    tests/ui/assert_engineering_view_integration.mjs
    tests/ui/assert_execution_plan_projection.mjs
    tests/ui/assert_mcp_detail_templates.mjs
    tests/ui/assert_node_information_architecture.mjs
    tests/ui/capture_workbench.mjs
  src/
    backend/lite_main.py
    backend/main.py
    core/__init__.py
    core/data_paths.py
    core/local_config.py
    core/cartridge/__init__.py
    core/cartridge/artifacts.py
    core/cartridge/assets.py
    core/cartridge/dependencies.py
    core/cartridge/environment.py
    core/cartridge/node_normalizer.py
    core/cartridge/permissions.py
    core/cartridge/registry.py
    core/cartridge/root_flow.py
    core/cartridge/runner.py
    core/cartridge/validator.py
    core/conformance/__init__.py
    core/conformance/reporting.py
    core/extensions/__init__.py
    core/extensions/descriptor.py
    core/extensions/mcp_source_editor.py
    core/extensions/mcp_source_parser.py
    core/extensions/registry.py
    core/extensions/sandbox_renderer.py
    core/extensions/sandbox_service.py
    core/extensions/worker_bootstrap.py
    core/extensions/worker_client.py
    core/extensions/worker_sdk.py
    core/lab/__init__.py
    core/lab/ai_steward.py
    core/lab/builtin_mcp.py
    core/lab/dev_flow.py
    core/lab/flow_analyzer.py
    core/lab/graph.py
    core/lab/mcp/__init__.py
    core/lab/mcp/shared.py
    core/lab/mcp_slots.py
    core/lab/node_executor.py
    core/lab/todo.py
    core/llm/__init__.py
    core/llm/base.py
    core/llm/config.py
    core/llm/config_manager.py
    core/llm/detection.py
    core/llm/errors.py
    core/llm/importers.py
    core/llm/openai_provider.py
    core/llm/openai_responses_provider.py
    core/llm/retry.py
    core/orchestration/__init__.py
    core/orchestration/execution_plan.py
    core/protocol/__init__.py
    core/protocol/base_manifest.py
    core/protocol/capability_registry.py
    core/protocol/certification.py
    core/protocol/compatibility.py
    core/protocol/decision_envelope.py
    core/protocol/flow_contract.py
    core/protocol/release_builder.py
    core/protocol/release_catalog.py
    core/protocol/release_envelope.py
    core/protocol/report.py
    core/protocol/tool_plan.py
    core/runtime/__init__.py
    core/runtime/agent_squad.py
    core/runtime/checkpoints.py
    core/runtime/errors.py
    core/runtime/html_generator.py
    core/runtime/llm_prompt.py
    core/runtime/manager.py
    core/runtime/state_machine.py
    core/studio/__init__.py
    core/studio/environment.py
    core/studio/external_adapters.py
    core/studio/hygiene.py
    core/studio/portability.py
    core/studio/release.py
    core/studio/resource_catalog.py
    core/studio/resource_resolver.py
    core/studio/resources.py
    core/workspace/__init__.py
    core/workspace/host.py
    frontend/.gitignore
    frontend/README.md
    frontend/index.html
    frontend/package.json
    frontend/package-lock.json
    frontend/public/favicon.svg
    frontend/tsconfig.app.json
    frontend/tsconfig.json
    frontend/tsconfig.node.json
    frontend/vite.config.ts
    frontend/src/App.tsx
    frontend/src/api.ts
    frontend/src/api.types.ts
    frontend/src/appearance.ts
    frontend/src/index.css
    frontend/src/llmRecipe.ts
    frontend/src/main.tsx
    frontend/src/toast.tsx
    frontend/src/ui.tsx
    frontend/src/components/ConfigModal.tsx
    frontend/src/components/DlcSandboxFrame.tsx
    frontend/src/components/InteractionSandboxFrame.tsx
    frontend/src/pages/FlowWorkbench.tsx
    frontend/src/pages/flow-workbench/AIFlowStewardPanel.tsx
    frontend/src/pages/flow-workbench/BrandMark.tsx
    frontend/src/pages/flow-workbench/CanvasAnnotationCard.tsx
    frontend/src/pages/flow-workbench/CartridgeDefinitionPanel.tsx
    frontend/src/pages/flow-workbench/CartridgeWorkspaceControl.tsx
    frontend/src/pages/flow-workbench/EngineeringInspector.tsx
    frontend/src/pages/flow-workbench/EngineeringNodeCard.tsx
    frontend/src/pages/flow-workbench/FlowGraphView.tsx
    frontend/src/pages/flow-workbench/FlowNodeCard.tsx
    frontend/src/pages/flow-workbench/FlowNodePorts.tsx
    frontend/src/pages/flow-workbench/InteractionAssetEditor.tsx
    frontend/src/pages/flow-workbench/InteractionContractEditor.tsx
    frontend/src/pages/flow-workbench/McpDetailTemplates.tsx
    frontend/src/pages/flow-workbench/McpTransparencyOverlay.tsx
    frontend/src/pages/flow-workbench/NodeDetailCard.tsx
    frontend/src/pages/flow-workbench/ResourceManagementPanels.tsx
    frontend/src/pages/flow-workbench/RunInputDialog.tsx
    frontend/src/pages/flow-workbench/TestBench.css
    frontend/src/pages/flow-workbench/TestBenchView.tsx
    frontend/src/pages/flow-workbench/clusterLayout.ts
    frontend/src/pages/flow-workbench/engineeringNode.ts
    frontend/src/pages/flow-workbench/flowNodeView.ts
    frontend/src/pages/flow-workbench/newFlowSetup.ts
    frontend/src/pages/flow-workbench/nodeAuthoring.ts
    frontend/src/pages/flow-workbench/nodeBuilder.ts
    frontend/src/pages/flow-workbench/nodeDetails.ts
    frontend/src/pages/flow-workbench/nodeEditing.ts
    frontend/src/pages/flow-workbench/nodeModel.ts
    frontend/src/pages/flow-workbench/passiveHtml.ts
    frontend/src/pages/flow-workbench/runState.ts
    frontend/src/pages/flow-workbench/types.ts
    frontend/src/pages/flow-workbench/views.tsx
    frontend/src/styles/00-foundation.css
    frontend/src/styles/10-workbench-shell.css
    frontend/src/styles/100-mcp-transparency.css
    frontend/src/styles/15-cartridge-workspace.css
    frontend/src/styles/30-workbench-runtime.css
    frontend/src/styles/50-workbench-design.css
    frontend/src/styles/95-config-and-appearance.css
    frontend/src/styles/98-reference-theme.css
    frontend/src/styles/99-workbench-reference-shell.css
    frontend/src/styles/README.md
```

未跟踪、但已纳入本次工作树审阅：

```text
scripts/tests/conformance/test_protocol_v10_completeness.py
```
