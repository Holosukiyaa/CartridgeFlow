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
C:\_HOLOLAB\code\CF WS\CartridgeFlow-worker-002-external-mcp-detail
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

只有在 `git status` 干净、前置 worker 已验收并合入基线时，才能启动依赖它的下一位 worker。当前 `ENG-021` 中，worker-002 依赖已合入的 worker-001；worker-004 还必须等待 001、002、003 都合入。

## 启动 Worker

每次启动都采用同一结构：先切换根目录、创建同级 worktree、把范围和报告格式写入提示词、再用绝对 worktree 路径启动。不要在提示词中要求 worker 阅读 `MENTOR_WORKERS.md`。

以下是当前可启动的 worker-002 示例。它的后端契约已在基线中：

```powershell
Set-Location -LiteralPath "C:\_HOLOLAB\code\CF WS\CartridgeFlow"
$worktree = "C:\_HOLOLAB\code\CF WS\CartridgeFlow-worker-002-external-mcp-detail"
git worktree add $worktree -b "workers/worker-002-external-mcp-detail"

$prompt = @'
你是 worker-002-external-mcp-detail。

目标：为 ENG-021 实现按 MCP 呈现模式区分的前端详情模板。
允许修改：src/frontend/src/api.ts、src/frontend/src/api.types.ts、src/frontend/src/pages/flow-workbench/EngineeringInspector.tsx、src/frontend/src/pages/flow-workbench/McpTransparencyOverlay.tsx、同目录新增详情模板组件，以及直接覆盖这些组件的前端测试。
禁止修改：src/core/**、src/backend/**、FlowGraphView.tsx、engineeringNode.ts、views.tsx、共享 CSS、docs/**、MENTOR_WORKERS.md。
依赖：worker-001 的资源目录、资源详情与连通性 API 已合入当前基线；直接消费该契约，不要修改它。
验收：本地可解析 DLC MCP 保留源码、操作图和指纹编辑入口；外部 MCP 显示“连接详情、调用契约、运行轨迹”，且不显示源码入口；不可审计 MCP 仅显示已知契约和不可观测原因；所有用户可见文案使用中文；前端测试和生产构建通过。

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
git branch --list "workers/worker-002-external-mcp-detail"
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
$worktree = "C:\_HOLOLAB\code\CF WS\CartridgeFlow-worker-002-external-mcp-detail"
git -C $worktree status --short
git branch --contains <accepted-commit-sha>
git worktree remove $worktree
git branch -d "workers/worker-002-external-mcp-detail"
```

若 worktree 仍有改动、提交未合入或任务未验收，mentor 不会删除它，而会报告阻塞原因。

## 固定规则

- 只有没有文件所有权冲突的 worker 才能并行。
- 有依赖关系的 worker 必须等待前序提交验收并进入基线。
- 不使用 `git reset --hard`、`git checkout --` 或强制删除 worktree。
- 不把密钥、token、请求头或本地凭据写进提示词、提交或报告。
- 主目录出现新的未提交改动时，先决定它是否应成为新基线，再启动后续 worker。
