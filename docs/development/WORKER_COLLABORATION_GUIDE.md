# Worker 协作使用指南

本指南面向需要手动启动多个 Codex worker 的操作者。它解决三件事：每个 worker 在独立目录工作、依赖任务不抢跑、每份交付都有统一可验收的报告。

当前任务分工、分支和验收状态以仓库根目录的 [MENTOR_WORKERS.md](../../MENTOR_WORKERS.md) 为准；worker 本身不依赖阅读该文件，启动提示词会内嵌其完整范围和交付格式。

## 使用目录

你可以在任意 PowerShell 目录粘贴本指南中的命令。每段命令都会先切换到项目根目录：

```text
C:\_HOLOLAB\code\CF WS\CartridgeFlow
```

worker 的独立目录位于项目同级目录，例如：

```text
C:\_HOLOLAB\code\CF WS\CartridgeFlow-worker-004-engineering-integration
```

不要手动在 worker 目录和主目录之间切换来执行命令，也不要在两个目录修改同一份产品文件。

## 开始前检查

先确认当前基线干净。下面的命令可从任何位置运行：

```powershell
Set-Location -LiteralPath "C:\_HOLOLAB\code\CF WS\CartridgeFlow"
git status
git log -1 --oneline
git worktree list
```

只有在 `git status` 干净、前置 worker 已验收并合入基线时，才能启动依赖它的下一位 worker。当前 `ENG-021` 的 worker-001、002、003 已合入，下一位可启动的是 worker-004。

## 启动 Worker

每次启动都采用同一结构：先切换根目录、创建同级 worktree、把范围和报告格式写入提示词、再用绝对 worktree 路径启动。不要在提示词中要求 worker 阅读 `MENTOR_WORKERS.md`。

以下是当前可启动的 worker-004。它负责最终接线、资源位置持久化和浏览器验收；不要把前面三位 worker 已验收的实现重新改写。

```powershell
Set-Location -LiteralPath "C:\_HOLOLAB\code\CF WS\CartridgeFlow"
$worktree = "C:\_HOLOLAB\code\CF WS\CartridgeFlow-worker-004-engineering-integration"
git worktree add $worktree -b "workers/worker-004-engineering-integration"

$prompt = @'
你是 worker-004-engineering-integration。

目标：完成 ENG-021 的最终工程视图接线、资源位置持久化和端到端验收。
允许修改：src/frontend/src/pages/flow-workbench/views.tsx、仅为接线所需的 src/frontend/src/pages/FlowWorkbench.tsx、最终集成/E2E 测试、docs/development/FILE_INVENTORY.md。
禁止修改：src/core/**、src/backend/**、src/frontend/src/api.ts、src/frontend/src/api.types.ts、EngineeringInspector.tsx、McpTransparencyOverlay.tsx、McpDetailTemplates.tsx、FlowGraphView.tsx、engineeringNode.ts、EngineeringNodeCard.tsx、FlowNodeCard.tsx、nodeModel.ts、docs/planning/**、MENTOR_WORKERS.md。
依赖：worker-001、worker-002、worker-003 已合入当前基线。直接接入既有资源契约、MCP 详情模板与工程画布行为，不要重写它们。
验收：工程视图能打开本地可解析、外部连接器和不可审计三类 MCP 的正确详情；外部 MCP 没有源码入口；资源拖动后刷新仍保留本地工程视图位置且不改变 Root Flow 拓扑；使用 AI 日报外部采集卡带完成桌面 100%/125% 与窄视口 Playwright 回归；前端构建、相关 API/UI 测试和流程预检通过。

先阅读 AGENT.md、任务书 docs/planning/ENGINEERING_VIEW_RESOURCE_TASK_BRIEF.md，以及你将修改的源码。只在允许路径内工作，保留真实失败状态，不制造模拟成功。完成后只提交本任务的改动。

## Worker Delivery Report
Changed files: <one path per line>
Commit SHA: <full SHA>
Tests: <command and result per line>
Known risks: <none or concrete risks>
Scope confirmation: <confirm no excluded paths changed>
'@
codex -C $worktree $prompt
```

若 `git worktree add` 报分支或目录已存在，不要改名重试。运行下面命令并把完整输出交给 mentor：

```powershell
Set-Location -LiteralPath "C:\_HOLOLAB\code\CF WS\CartridgeFlow"
git worktree list
git branch --list "workers/worker-004-engineering-integration"
```

## 交付与验收

worker 完成后，把它的 `Worker Delivery Report` 原样交给 mentor。没有完整 SHA、测试结果或范围确认的报告不能验收。

mentor 会检查提交基线、允许路径、测试、真实错误语义和已知风险；只有用户明确批准后才会将 worker 提交合入 `main`。已合入不等于全部工作完成，仍需等待依赖链和最终集成验证。

## 全部完成后的清理

所有 worker 均已验收并合入、最终集成测试通过、登记表没有 `planned`、`running` 或 `review` 状态后，mentor 会清理 worktree。清理前必须逐个确认：

1. `git worktree list` 中的路径就是要移除的 worker 目录。
2. 对应 worktree 没有未提交改动。
3. 对应提交已经在最终基线中。

确认后执行的命令形态如下；通常由 mentor 执行，不需要你提前运行：

```powershell
Set-Location -LiteralPath "C:\_HOLOLAB\code\CF WS\CartridgeFlow"
$worktree = "C:\_HOLOLAB\code\CF WS\CartridgeFlow-worker-004-engineering-integration"
git -C $worktree status --short
git branch --contains <accepted-commit-sha>
git worktree remove $worktree
git branch -d "workers/worker-004-engineering-integration"
```

若 worktree 仍有改动、提交未合入或任务未验收，mentor 不会删除它，而会报告阻塞原因。

## 固定规则

- 只有没有文件所有权冲突的 worker 才能并行。
- 有依赖关系的 worker 必须等待前序提交验收并进入基线。
- 不使用 `git reset --hard`、`git checkout --` 或强制删除 worktree。
- 不把密钥、token、请求头或本地凭据写进提示词、提交或报告。
- 主目录出现新的未提交改动时，先决定它是否应成为新基线，再启动后续 worker。
