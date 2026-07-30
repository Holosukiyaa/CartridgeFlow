# Worker 协作使用指南

这份指南用于执行当前 `ENG-021` 工程视图任务。你不需要同时操作三个 worker，也不需要理解 Git worktree 的实现细节。

核心规则有两条：**只让没有文件所有权冲突的 worker 并行；有依赖的 worker 必须等待前序提交验收。**

当前的完整任务分工、允许修改的文件和原始提示词保存在仓库根目录的 [MENTOR_WORKERS.md](../../MENTOR_WORKERS.md)。

## 先理解三个名称

| 名称 | 你可以把它理解为 | 当前作用 |
| --- | --- | --- |
| 基线 | 所有 worker 共同的起点 | 必须是一个 Git 提交，不能只是未保存的本地改动 |
| worker | 一位只处理特定范围的开发者 | 在独立目录和独立分支中工作，不会直接污染主目录 |
| worker 报告 | 开发者的交付单 | 包含提交号、修改文件、测试结果和风险 |

## 当前执行顺序

```text
整理并提交基线
    ├── worker-001-resource-contracts（后端契约）
    └── worker-003-engineering-canvas（画布视觉）
worker-001 验收并合入后
    ↓
worker-002-external-mcp-detail（可与仍在工作的 003 并行）
                 ↓ 001、002、003 三条交付均验收并合入
        worker-004-engineering-integration（接线与浏览器验收）
```

可以并行的只有 worker 001 与 worker 003：一个改后端契约，一个改画布视觉，文件不会冲突。worker 002 依赖 001 的后端契约；worker 004 用于最后接线，依赖前三位。

## 第 0 步：建立基线

在 PowerShell 中进入项目目录：

```powershell
cd "C:\_HOLOLAB\code\CF WS\CartridgeFlow"
git status
git diff
```

当前主目录已有未提交改动。请先检查这些内容，确认哪些应成为本轮开发共同起点，再由你创建一个基线提交。

不要使用 `git add .`，因为它可能把不相关的本地文件也带入提交。基线完成后再次运行：

```powershell
git status
git log -1 --oneline
```

预期结果：`git status` 显示工作区干净，最后一条提交就是本轮 worker 的共同起点。

## 第 1 步：启动 worker 001

它只处理后端：外部 MCP 的连接详情、脱敏、资源目录和接口。它不会修改画布。

### 1. 创建它的独立目录

```powershell
git -C "C:\_HOLOLAB\code\CF WS\CartridgeFlow" worktree add "..\CartridgeFlow-worker-001-resource-contracts" -b "workers/worker-001-resource-contracts"
```

成功后，旁边会出现一个新目录：

```text
C:\_HOLOLAB\code\CF WS\CartridgeFlow-worker-001-resource-contracts
```

### 2. 启动它

在主项目目录执行以下命令：

```powershell
$prompt = @'
实现 ENG-021 的后端资源契约部分。先阅读 AGENT.md、MENTOR_WORKERS.md 与 docs/planning/ENGINEERING_VIEW_RESOURCE_TASK_BRIEF.md。为资源目录提供三种 MCP 呈现模式：本地可解析、本地外部连接器、不可审计。外部连接器必须投影连接身份、server/tool、脱敏端点或配置引用、认证引用状态、权限、参数/输出 schema、超时、重试、幂等性、透明度、连接/运行健康与不可读取原因；绝不向前端输出密钥、token、Authorization、原始敏感 URL 或请求头。实现稳定的资源详情/连通性检查 API 与错误语义，并保持未绑定外部连接器真实失败，不制造模拟成功。只写登记表允许路径，补齐相关测试，提交仅限本任务。报告 changed files、commit SHA、tests、known risks。
'@
codex -C "..\CartridgeFlow-worker-001-resource-contracts" $prompt
```

运行后，可以立刻并行启动 worker 003；不要启动 worker 002 或 004。

## 第 2 步：把报告交回审查

worker 完成时，应提供这四项：

```text
Changed files:
Commit SHA:
Tests:
Known risks:
```

把完整报告发给 mentor。此时不需要你自己合并分支，也不要删除 worktree。审查通过后，`MENTOR_WORKERS.md` 会把该 worker 从 `planned` 更新为 `review` 或 `accepted`。

只有在明确接受并将提交纳入下一轮基线后，才进入下一位 worker。

## 第 3 步：并行启动 worker 003

它只处理画布外观和节点布局：资源卡、类别标识、拖动行为和自适应尺寸，不修改后端、详情模板或 API 类型。它可以与 worker 001 同时运行。

按下文“worker 003 启动命令”执行。

## 第 4 步：启动 worker 002

前提：worker 001 已接受，且其提交已进入当前基线。

它只处理 MCP 详情界面：

- 本地 DLC MCP：源码和内部流程；
- 外部 MCP：连接详情和调用契约；
- 不可审计 MCP：已知信息和不可观测原因。

它不修改后端和画布。按下文“worker 002 启动命令”执行。启动前先确认：

```powershell
git -C "C:\_HOLOLAB\code\CF WS\CartridgeFlow" status
git -C "C:\_HOLOLAB\code\CF WS\CartridgeFlow" log -1 --oneline
```

## 第 5 步：启动 worker 004

前提：workers 001、002、003 都已接受，且三者提交已进入当前基线。

它只负责最后接线：把已验收的后端契约、MCP 详情模板和画布行为接入同一工作台，保存资源位置，并完成浏览器回归。

按下文“worker 004 启动命令”执行。

## worker 003 启动命令

worker 003 可以与 worker 001 同时启动：

```powershell
git -C "C:\_HOLOLAB\code\CF WS\CartridgeFlow" worktree add "..\CartridgeFlow-worker-003-engineering-canvas" -b "workers/worker-003-engineering-canvas"

$prompt = @'
实现 ENG-021 的工程画布视觉部分。先阅读 AGENT.md、MENTOR_WORKERS.md 与任务书。只修改登记表允许的画布文件。实现资源专用卡片、UI 资源预览、节点中文类别标识和低饱和类别色、资源拖动行为与按内容自适应卡片尺寸。资源依赖边不能进入 Root Flow 控制流。不要修改 API、后端、views.tsx 或 MCP 详情模板；资源位置持久化由最终集成 worker 接入。补齐组件和布局测试，提交仅限本任务。报告 changed files、commit SHA、tests、known risks。
'@
codex -C "..\CartridgeFlow-worker-003-engineering-canvas" $prompt
```

## worker 002 启动命令

只有在 worker 001 已验收并进入基线后运行：

```powershell
git -C "C:\_HOLOLAB\code\CF WS\CartridgeFlow" worktree add "..\CartridgeFlow-worker-002-external-mcp-detail" -b "workers/worker-002-external-mcp-detail"

$prompt = @'
实现 ENG-021 的 MCP 详情模板部分。先阅读 AGENT.md、MENTOR_WORKERS.md 与任务书，并基于已合入的 worker-001 资源/API 契约工作。保留本地可解析 DLC MCP 的源码、操作图、指纹编辑入口；为外部 MCP 创建“连接详情、调用契约、运行轨迹”模板；不可审计 MCP 只显示已知契约和不可观测原因。外部 MCP 不显示“打开源码”或空白源码编辑器，入口文案为“查看连接详情”。所有可见文案中文化。只写登记表允许路径，运行前端相关测试和构建，提交仅限本任务。报告 changed files、commit SHA、tests、known risks。
'@
codex -C "..\CartridgeFlow-worker-002-external-mcp-detail" $prompt
```

## worker 004 启动命令

只有在 workers 001、002、003 都已验收并进入基线后运行：

```powershell
git -C "C:\_HOLOLAB\code\CF WS\CartridgeFlow" worktree add "..\CartridgeFlow-worker-004-engineering-integration" -b "workers/worker-004-engineering-integration"

$prompt = @'
实现 ENG-021 的最终集成部分。先阅读 AGENT.md、MENTOR_WORKERS.md 与任务书，并确认 workers 001、002、003 的已验收提交均已在当前基线。只修改登记表允许路径。把后端资源详情、MCP 详情模板和画布行为接入工程工作台；使用已提供的工程布局契约持久化资源位置；完成外部 MCP 连接详情、本地 DLC 源码入口、资源拖拽持久化和 100%/125% 视口的 Playwright 回归。不要修改后端、API 类型、详情组件或节点卡片实现。更新文件清单，提交仅限本任务。报告 changed files、commit SHA、tests、known risks。
'@
codex -C "..\CartridgeFlow-worker-004-engineering-integration" $prompt
```

## 发生问题时怎么做

| 现象 | 处理方式 |
| --- | --- |
| `worktree add` 提示分支已存在 | 不要换名字重试。把报错和 `git worktree list` 发给 mentor。 |
| worker 修改了禁止路径 | 不接受该提交，要求 worker 收缩范围或重新拆分。 |
| worker 没有 commit SHA | 不能进入下一步，要求其提交并重新报告。 |
| 测试失败 | 先让当前 worker 在自己的范围内修复；不能把问题推给下一位 worker。 |
| 不确定是否该合并 | 停在当前步骤，把报告发给 mentor 审查。 |
| 主目录又出现新改动 | 不要启动新 worker。先决定这些改动是否应进入新的基线。 |

## 不要做的事

- 不要同时启动具有依赖关系的 worker；当前只允许 001 与 003 并行。
- 不要在主目录和 worker 目录里修改同一份产品文件。
- 不要用 `git reset --hard`、`git checkout --` 清理改动。
- 不要在没有审查报告的情况下假设 worker 已完成。
- 不要把真实密钥、token、请求头或本地凭证发给 worker。

## 你现在该做什么

现在只做两件事：

1. 在主目录运行 `git status` 和 `git diff`，整理本轮共同基线。
2. 基线提交完成后，同时启动 `worker-001-resource-contracts` 和 `worker-003-engineering-canvas`。

启动后，把两位 worker 的最终报告发回来，再决定后续验收和合入。
