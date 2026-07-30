# Worker 协作使用指南

本指南面向手动启动多个 Codex worker 的操作者。当前执行批次为 `ORCH-001`，完整任务边界、依赖和提示词见 [编排执行任务书](../planning/ORCHESTRATION_EXECUTION_TASK_BRIEF.md)；唯一状态来源是仓库根目录的 [MENTOR_WORKERS.md](../../MENTOR_WORKERS.md)。

## 使用目录

主仓库固定为：

```text
C:\_HOLOLAB\code\CF WS\CartridgeFlow
```

每位 worker 在主仓库同级的独立目录工作，例如：

```text
C:\_HOLOLAB\code\CF WS\CartridgeFlow-worker-101-execution-plan-contract
```

本文档中的每条 PowerShell 命令都自带 `Set-Location`，可从任意目录直接粘贴。不要在主仓库和 worker 目录同时修改同一文件；不要让 worker 读取 `MENTOR_WORKERS.md` 来猜测职责，启动提示词已内嵌完整边界。

## 启动前检查

```powershell
Set-Location -LiteralPath "C:\_HOLOLAB\code\CF WS\CartridgeFlow"
git status --short
git log -1 --oneline
git worktree list
```

只有主仓库没有未提交改动、前置 worker 已被验收并由用户批准合并时，才启动依赖它的下一位 worker。`ORCH-001` 现在只能启动 worker 101；worker 102 必须等 101 合并，worker 103 与 104 必须等 102 合并。

## 当前启动命令

直接复制 [编排执行任务书](../planning/ORCHESTRATION_EXECUTION_TASK_BRIEF.md) 中对应 worker 的完整代码块。它会创建专属 branch/worktree，并将目标、允许路径、排除项、依赖、验收标准和固定交付报告格式交给 worker。

## 交付、验收与合并

worker 完成后，把完整的 `Worker Delivery Report` 发给 mentor。报告缺少完整 SHA、测试结果或范围确认时不能验收。mentor 会核对提交基线、文件所有权、测试证据和真实失败语义；只有用户明确批准后才合并进 `main`。

不要把“构建通过”当成编排语义通过：ORCH-001 的验收还需要正反 conformance 用例，证明隐式合流、未声明循环、不可执行可视边和不安全重放都被拒绝。

## 全部完成后的清理

所有 worker 均已验收和合并、最终集成证据通过，且登记表中没有 `planned`、`running` 或 `review` 后，mentor 才会逐个清理 worktree。清理前必须确认路径、worktree 干净、accepted commit 已包含于 `main`；不清理脏目录、未验收目录或未合并目录。
