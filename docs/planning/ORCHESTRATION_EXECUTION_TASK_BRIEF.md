# ORCH-001 编排执行任务书

来源：[n8n 编排取经与差异化报告](../architecture/N8N_ORCHESTRATION_BENCHMARK_REPORT.md)。本批次只建立 `ExecutionPlan v1` 的协议、编译、运行和投影视图，不实现 n8n 兼容、连接器市场、子 Flow、Fixture/TestBench、产品交付合同或企业版能力。

## 交付顺序

```text
worker-101 协议与合同
  -> worker-102 纯计划编译
       -> worker-103 Token 运行器
       -> worker-104 Analyzer 与工程视图投影
```

worker 103 和 104 可以在 worker 102 合并后并行启动。每个 worker 只能写自己的路径，不能修改 `MENTOR_WORKERS.md`，不能自行合并，也不能为了让演示通过而制造成功、放松旧协议或跳过真实错误。

`CF-FARP@1.0` 是新的草案协议版本：worker 101 可以登记其身份、语义和拒绝规则，但 `config/base/BASE_IMPLEMENTATION.json` 在 worker 103 的运行时、兼容和 conformance 证据完整前不得宣称支持它。

## worker-101-execution-plan-contract

目标：冻结 `sequence`、`fork`、`join(all/any/keyed)`、`loop`、`batch`、`wait` 和 `failure` 的 CF-FARP@1.0 作者事实与验证规则，并保留 v0.9 的既有含义。

允许写入：`docs/protocol/flow-authoring/CARTRIDGEFLOW_FLOW_AUTHORING_RUNTIME_PROTOCOL_v1.0.md`、`docs/protocol/governance/GOVERNANCE.md`、`protocol/releases/CF-FARP-1.0.json`、`protocol/catalog/release_manifest.json`、`protocol/governance/protocol_history.json`、`protocol/vocabulary/*`、`src/core/protocol/flow_contract.py`、直接相关 conformance 测试。

禁止写入：`config/base/BASE_IMPLEMENTATION.json`、`src/core/cartridge/**`、`src/core/lab/**`、`src/core/runtime/**`、`src/frontend/**`、`src/backend/**`、`MENTOR_WORKERS.md`。

验收：旧 v0.9 语义和历史快照不变；新 registry/文档/词表治理检查通过；正反 conformance 覆盖每种新边，拒绝隐式合流、无界循环、未声明失败出口和不可执行的旧 `action_route`；Base 不宣称 v1.0 可运行。

```powershell
Set-Location -LiteralPath "C:\_HOLOLAB\code\CF WS\CartridgeFlow"
$worktree = "C:\_HOLOLAB\code\CF WS\CartridgeFlow-worker-101-execution-plan-contract"
git worktree add $worktree -b "workers/worker-101-execution-plan-contract"

$prompt = @'
你是 worker-101-execution-plan-contract。
目标：为 ORCH-001 冻结独立实现的 CF-FARP@1.0 ExecutionPlan 作者语义。定义 sequence、fork、join(all/any/keyed)、loop、batch、wait、failure 的规范事实、拒绝规则和 conformance；绝不做 n8n JSON/源码兼容。CF-FARP@1.0 只能是 draft/unsupported，直到运行器、兼容和完整证据存在，绝不修改 Base 支持声明。
先阅读 AGENT.md、docs/architecture/N8N_ORCHESTRATION_BENCHMARK_REPORT.md、docs/protocol/governance/GOVERNANCE.md、当前 CF-FARP@0.9 正文、protocol/catalog/release_manifest.json，以及 docs/development/skills/cartridgeflow-protocol-upgrader/SKILL.md 和 references/upgrade-checklist.md。
允许写入：docs/protocol/flow-authoring/CARTRIDGEFLOW_FLOW_AUTHORING_RUNTIME_PROTOCOL_v1.0.md；docs/protocol/governance/GOVERNANCE.md；protocol/releases/CF-FARP-1.0.json；protocol/catalog/release_manifest.json；protocol/governance/protocol_history.json；protocol/vocabulary/*；src/core/protocol/flow_contract.py；直接相关 conformance 测试。
禁止写入：config/base/BASE_IMPLEMENTATION.json；src/core/cartridge/**；src/core/lab/**；src/core/runtime/**；src/frontend/**；src/backend/**；MENTOR_WORKERS.md。
验收：v0.9 语义和快照不变；新的 registry、文档和词表通过治理审计；每种新边都有正反 conformance；隐式合流、无界循环、未声明失败出口、旧 action_route 和可视但不可执行的边有稳定错误；Base 不声称支持 v1.0。完成后只提交本任务范围内的改动。
## Worker Delivery Report
Changed files: <one path per line>
Commit SHA: <full SHA>
Tests: <command and result per line>
Known risks: <none or concrete risks>
Scope confirmation: <confirm no excluded paths changed>
'@
codex -C $worktree $prompt
```

## worker-102-execution-plan-compiler

依赖：worker 101 已验收并由用户批准合并。目标：创建无副作用、可序列化、可按 source digest 复现的 `ExecutionPlan v1` 纯编译器。

允许写入：新建 `src/core/orchestration/**`、直接相关 `scripts/tests/orchestration/**`。禁止写入：`src/core/protocol/**`、`protocol/**`、`config/**`、`src/core/cartridge/**`、`src/core/lab/**`、`src/core/runtime/**`、`src/frontend/**`、`src/backend/**`、`MENTOR_WORKERS.md`。

验收：同一有效 Flow 产生相同 plan/digest；plan 显式携带所有控制和等待/失败语义；错误是稳定、机器可消费的编译错误；编译不执行节点、不访问外部资源、不写运行状态。

```powershell
Set-Location -LiteralPath "C:\_HOLOLAB\code\CF WS\CartridgeFlow"
$worktree = "C:\_HOLOLAB\code\CF WS\CartridgeFlow-worker-102-execution-plan-compiler"
git worktree add $worktree -b "workers/worker-102-execution-plan-compiler"

$prompt = @'
你是 worker-102-execution-plan-compiler。前置条件：worker-101-execution-plan-contract 已验收并合并，当前基线包含 CF-FARP@1.0 的作者合同。
目标：实现纯 Python 的 ExecutionPlan v1 编译器。它只消费已验证的 Flow 作者事实，产出确定性、可序列化、digest-bound 的计划，显式表达 sequence、fork、join(all/any/keyed)、loop、batch、wait、failure。不得执行节点、探测资源、写运行状态或将共享 store 重新解释为隐式数据流。
先阅读 AGENT.md、docs/architecture/N8N_ORCHESTRATION_BENCHMARK_REPORT.md、worker 101 合入后的 CF-FARP@1.0 协议、src/core/protocol/flow_contract.py 和现有 RootFlow/Analyzer 只读实现。
允许写入：新建 src/core/orchestration/**；直接相关 scripts/tests/orchestration/**。
禁止写入：src/core/protocol/**；protocol/**；config/**；src/core/cartridge/**；src/core/lab/**；src/core/runtime/**；src/frontend/**；src/backend/**；MENTOR_WORKERS.md。
验收：相同 source digest 生成相同计划；计划含完整调度事实和稳定节点/边 identity；非法合同产生稳定编译错误；测试证明没有节点执行或外部副作用。完成后只提交本任务范围内的改动。
## Worker Delivery Report
Changed files: <one path per line>
Commit SHA: <full SHA>
Tests: <command and result per line>
Known risks: <none or concrete risks>
Scope confirmation: <confirm no excluded paths changed>
'@
codex -C $worktree $prompt
```

## worker-103-token-runner

依赖：worker 102 已验收并由用户批准合并。目标：让运行器以 token 而非全局 `visited` 集合调度，并把 checkpoint 与重放边界写为真实证据。

允许写入：`src/core/cartridge/root_flow.py`、`src/core/cartridge/runner.py`、`src/core/runtime/checkpoints.py`、直接相关 `scripts/tests/runtime/**`。禁止写入：`src/core/orchestration/**`、协议目录、Analyzer、前端、后端和 `MENTOR_WORKERS.md`。

验收：循环可重入；fork/join、暂停/恢复、checkpoint trace 确定；带外部副作用的 token 不会自动重放；旧 v0.9 Flow 保持既有行为或得到明确不支持错误。

```powershell
Set-Location -LiteralPath "C:\_HOLOLAB\code\CF WS\CartridgeFlow"
$worktree = "C:\_HOLOLAB\code\CF WS\CartridgeFlow-worker-103-token-runner"
git worktree add $worktree -b "workers/worker-103-token-runner"

$prompt = @'
你是 worker-103-token-runner。前置条件：worker-102-execution-plan-compiler 已验收并合并，当前基线含有稳定的 ExecutionPlan v1 编译器。
目标：让 Root Flow 运行器消费 ExecutionPlan token，而不是用全局 visited 集合阻止节点重复执行。持久化 token 的 run、node、attempt、输入引用和 checkpoint；支持有界 loop/batch、fork/join、wait/resume 的确定性 trace。外部副作用 token 的恢复必须真实拒绝自动重放，要求既有确认/恢复边界，绝不伪造成功。
先阅读 AGENT.md、docs/architecture/N8N_ORCHESTRATION_BENCHMARK_REPORT.md、已合入的 CF-FARP@1.0、src/core/orchestration/**、src/core/cartridge/root_flow.py、src/core/cartridge/runner.py、src/core/runtime/checkpoints.py 和相关运行时测试。
允许写入：src/core/cartridge/root_flow.py；src/core/cartridge/runner.py；src/core/runtime/checkpoints.py；直接相关 scripts/tests/runtime/**。
禁止写入：src/core/orchestration/**；src/core/protocol/**；protocol/**；src/core/lab/**；src/frontend/**；src/backend/**；MENTOR_WORKERS.md。
验收：测试证明 loop 可重入、fork/join 条件准确、暂停恢复的 token/checkpoint trace 确定；带外部副作用 token 不会静默自动重放；旧 v0.9 Flow 保持原语义或返回明确的不支持错误。完成后只提交本任务范围内的改动。
## Worker Delivery Report
Changed files: <one path per line>
Commit SHA: <full SHA>
Tests: <command and result per line>
Known risks: <none or concrete risks>
Scope confirmation: <confirm no excluded paths changed>
'@
codex -C $worktree $prompt
```

## worker-104-plan-projection

依赖：worker 102 已验收并由用户批准合并；可与 worker 103 并行。目标：让 Analyzer 与工程视图投影同一份 ExecutionPlan，不再把 `action_route`、`failure_route` 或隐式合流画成可执行路线。

允许写入：`src/core/lab/flow_analyzer.py`、`src/frontend/src/pages/flow-workbench/**`、直接相关 Analyzer/UI 测试。禁止写入：`src/core/orchestration/**`、协议目录、运行器、后端和 `MENTOR_WORKERS.md`。

验收：每条可执行视觉线都有 plan identity；旧隐式/不可执行路线显示中文诊断而非误导；生产构建和目标 UI/Analyzer 测试通过。

```powershell
Set-Location -LiteralPath "C:\_HOLOLAB\code\CF WS\CartridgeFlow"
$worktree = "C:\_HOLOLAB\code\CF WS\CartridgeFlow-worker-104-plan-projection"
git worktree add $worktree -b "workers/worker-104-plan-projection"

$prompt = @'
你是 worker-104-plan-projection。前置条件：worker-102-execution-plan-compiler 已验收并合并，当前基线含有稳定的 ExecutionPlan v1 编译器。你可与 worker-103-token-runner 并行，但不得改动其拥有的运行时文件。
目标：让 Flow Analyzer 与工程视图投影同一份 ExecutionPlan 语义。每条被标为可执行的视觉边必须能定位 plan edge identity；action_route、failure_route、隐式合流和其他无法编译/执行的旧关系必须显示为中文、可操作的诊断，不能继续被画成真实运行路线。
先阅读 AGENT.md、docs/architecture/N8N_ORCHESTRATION_BENCHMARK_REPORT.md、已合入的 CF-FARP@1.0、src/core/orchestration/**、src/core/lab/flow_analyzer.py 和现有工程视图代码/测试。
允许写入：src/core/lab/flow_analyzer.py；src/frontend/src/pages/flow-workbench/**；直接相关 Analyzer/UI 测试。
禁止写入：src/core/orchestration/**；src/core/protocol/**；protocol/**；src/core/cartridge/**；src/core/runtime/**；src/backend/**；MENTOR_WORKERS.md。
验收：每条可执行视觉线映射到一个 plan edge；不支持的旧隐式/不可执行路线给出中文诊断且不误导运行；Analyzer 测试、相关 UI 测试、前端生产构建通过。完成后只提交本任务范围内的改动。
## Worker Delivery Report
Changed files: <one path per line>
Commit SHA: <full SHA>
Tests: <command and result per line>
Known risks: <none or concrete risks>
Scope confirmation: <confirm no excluded paths changed>
'@
codex -C $worktree $prompt
```
