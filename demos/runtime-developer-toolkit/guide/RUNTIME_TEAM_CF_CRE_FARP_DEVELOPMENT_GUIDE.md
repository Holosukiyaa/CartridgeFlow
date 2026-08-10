# 运行台团队 CF-CRE@1 与 CF-FARP 执行计划开发指南

> 创作空间的严格打包边界输出 CF-FARP@1.6。它与本指南的
> `execution_plan.v1` 执行载荷兼容；1.6 的新增语义发生在打包校验阶段，
> 不向运行台增加 Creator 会话或工程配置输入。

文档状态：运行台交接基线

适用对象：不使用 Python、负责实现个人运行台或运行时消费层的 Node.js/TypeScript 团队。

本指南回答三个问题：运行台必须信任什么、运行台必须执行什么、运行台如何证明自己没有越过协议边界。工具包中的 `runtime-developer-toolkit/demo/` 是最小可运行参考实现；它是协议交接起点，不是生产运行台的完整替代品。

## 1. 先记住四条边界

1. **CF-CRE@1 是发行包协议。** 它定义身份、公开合同、摘要、签名、信任和载荷安装边界。
2. **CF-FARP@1.0 是载荷流程协议。** 它定义 `root.flow.json` 如何表达并执行流程，当前基座使用 `execution_plan.v1`。
3. **发行包是唯一运行输入。** 运行台不得读取开发台工程、开发台数据库、Python 模块、`.data/user/dev_flows` 或包外的同名文件来补全缺失字段。
4. **不确定就拒绝。** 缺签名、摘要不一致、信任失败、能力不匹配、路径不安全或未知必需语义时，必须 fail closed，不能猜测、降级或静默回退。

推荐的最小数据流：

```text
CF-CRE ZIP
  -> ZIP 安全检查
  -> release.manifest.json / hashes.json 校验
  -> Ed25519 签名校验
  -> 本地信任库校验
  -> Base/FARP 兼容性校验
  -> 暂存与安装
  -> 资源重绑定
  -> 激活
  -> CF-FARP execution_plan 执行
  -> 公开交付物与运行记录
```

## 2. 参考实现和快速验证

### 2.1 环境

- Node.js 20 或更高版本。
- 不需要 Python。
- 不需要安装 npm 依赖；demo 只使用 Node 内置模块。
- 生产运行台应将 `run.mjs` 的逻辑拆成自己的 TypeScript 模块，并保留同样的验证顺序。

进入仓库根目录后，先检查脚本语法：

```powershell
npm --prefix runtime-developer-toolkit/demo run check
```

### 2.2 找到验收包和信任库

CartridgeFlow 设计台通过开发台「卡带打包」功能（production 模式）生成的验收包位于：

```text
runtime-developer-toolkit/samples/<cartridge>-<version>.cf-cre.zip
```

本工具包提供 5 个样例包：

- `dev.blog-writer-0.1.0.cf-cre.zip` —— 驳回重写循环（`confirm_checkpoint` + `answer_routes` + `loop` 边）。
- `dev.parallel-research-0.1.0.cf-cre.zip` —— fork/join 并行（三路并行抓源 → join 等齐 → AI 提炼）。
- `dev.threejs-arena-0.1.0.cf-cre.zip` —— 综合流程（并行 + 4 个 AI 决策 + 外部工具 + 审核 + HTML 产物）。
- `dev.ai-video-daily-0.1.0.cf-cre.zip` —— 端到端视频日报（多 AI 决策 + 外部 RSS + 审核 + 视频产物）。
- `dev.cf-cre-farp-acceptance-1.0.0.cf-cre.zip` —— 原始最小验收包（纯 sequence，保留兼容参考）。

本地开发信任库位于：

```text
runtime-developer-toolkit/samples/trusted_publishers.json
```

生产运行台不能直接使用开发目录。运行台应在安装或首次启动时导入经过管理员配置的信任库，并将信任库作为受保护的运行台配置管理。

### 2.3 只验证包

```powershell
node runtime-developer-toolkit/demo/run.mjs verify `
  runtime-developer-toolkit/samples/dev.blog-writer-0.1.0.cf-cre.zip `
  --trust runtime-developer-toolkit/samples/trusted_publishers.json
```

成功结果至少包含：

```json
{
  "ok": true,
  "protocol": "CF-CRE@1",
  "release_id": "...",
  "signer": "..."
}
```

这一步不会写入安装目录，也不会执行载荷代码。

### 2.4 只安装载荷

```powershell
node runtime-developer-toolkit/demo/run.mjs install `
  runtime-developer-toolkit/samples/dev.cf-cre-farp-acceptance-1.0.0.cf-cre.zip `
  .data/temp/runtime-install `
  --trust runtime-developer-toolkit/samples/trusted_publishers.json
```

安装器只能写入显式的目标目录。安装目标应该是版本隔离的目录，不得直接覆盖当前激活版本。

### 2.5 mock 流程模式

```powershell
node runtime-developer-toolkit/demo/run.mjs run `
  runtime-developer-toolkit/samples/dev.blog-writer-0.1.0.cf-cre.zip `
  .data/temp/runtime-run-mock `
  --trust runtime-developer-toolkit/samples/trusted_publishers.json `
  --mock
```

`--mock` 是**本地确定性分支**：模型节点不会发 HTTP 请求，而是直接写入 mock 响应。它适合验证协议解析、执行顺序、`loop` 边求值、人工审核自动批准、MCP/artifact 落盘和运行结果格式。

并行流程同样支持（demo 顺序模拟各分支并在 join 等齐）：

```powershell
node runtime-developer-toolkit/demo/run.mjs run `
  runtime-developer-toolkit/samples/dev.parallel-research-0.1.0.cf-cre.zip `
  .data/temp/runtime-run-mock-parallel `
  --trust runtime-developer-toolkit/samples/trusted_publishers.json `
  --mock
```

### 2.6 真实 HTTP 路径

仓库提供了一个明确的本地 OpenAI-compatible 测试服务：

```powershell
node runtime-developer-toolkit/demo/mock-model.mjs
```

另开终端运行：

```powershell
$env:CF_RUNTIME_MODEL_BASE_URL = "http://127.0.0.1:11434/v1"
$env:CF_RUNTIME_MODEL_API_KEY = "cf-demo-key"
$env:CF_RUNTIME_MODEL = "cf-demo-model"

node runtime-developer-toolkit/demo/run.mjs run `
  runtime-developer-toolkit/samples/dev.cf-cre-farp-acceptance-1.0.0.cf-cre.zip `
  .data/temp/runtime-run-http `
  --trust runtime-developer-toolkit/samples/trusted_publishers.json
```

这次不使用 `--mock`，所以 demo 会真实执行 `POST /chat/completions`。但服务端仍是本地测试服务，不代表第三方模型已被验证。生产运行台应将三个环境变量替换为用户明确绑定的模型连接，凭据不能进入发行包。

## 3. CF-CRE@1 发行包必须如何处理

### 3.1 包布局

运行台至少要识别这些固定路径：

```text
release.manifest.json
hashes.json
signatures/
  publisher.ed25519
public/
  experience.json
  delivery.contract.json
payload/
  manifest.json
  root.flow.json
proof/
  package.analysis.json
  portability.json
```

发行包中其它文件也必须被 `hashes.json.files` 列出。不能因为文件位于 `proof/`、`assets/` 或 `payload/` 就跳过摘要检查。

### 3.2 ZIP 安全检查

解压前必须拒绝：

- 绝对路径、反斜杠路径和 `..` 路径段。
- 重复成员名。
- 符号链接或无法判断类型的特殊成员。
- 超过运行台限制的压缩包、单文件或解压后总大小。
- 中央目录和本地文件头不一致的成员。
- 不支持的压缩方式。

解压目标必须使用 `resolve()` 后的路径边界检查，确保任何输出都位于当前安装或暂存目录内部。

### 3.3 摘要检查顺序

1. 解析 `release.manifest.json` 和 `hashes.json`，要求 UTF-8 JSON 对象。
2. 验证两个 schema：
   - `cartridgeflow.release_envelope.v1`
   - `cartridgeflow.release_hashes.v1`
3. 用精确字节计算 `hashes.json` 的 SHA-256，并匹配 `release.integrity.content_digest`。
4. 对 `hashes.json.files` 的每一项检查路径、大小和 SHA-256。
5. 检查归档中的每个非控制文件都在清单中。
6. 重新计算 `payload.digest`，只使用排序后的 payload 文件条目。

任何一步失败都不能进入签名、安装或执行阶段。

### 3.4 Ed25519 签名和信任

签名描述必须满足：

```text
role=publisher
algorithm=ed25519
key_id=稳定合法标识
path=signatures/ 下的安全路径
```

签名覆盖的输入是：

```text
release.manifest.json 的精确字节
换行符 `\n`
hashes.json 的精确字节
```

验证分两层：

1. **密码学有效**：签名确实由对应公钥生成。
2. **信任有效**：该公钥的 `key_id` 和公钥字节存在于当前运行台信任库。

密码学有效但不受信的包只能作为“待审核包”记录，不能激活。信任库变更必须有管理员操作、审计记录和密钥轮换策略。

### 3.5 公开合同与隐私

运行台公开体验和交付 UI 只能消费：

```text
public/experience.json
public/delivery.contract.json
```

公开合同不得泄露：

```text
prompt, system_prompt, api_key, token, endpoint, command,
args, credentials, secret, root_flow, execution_plan, store,
checkpoint, node_id, tool_parameters
```

生产运行台不能从公开合同推断内部流程，也不能把载荷内部节点名称直接展示给普通用户。

## 4. CF-FARP@1.0 载荷执行

### 4.1 载荷入口

`payload/manifest.json` 描述卡带身份和运行合同，`payload/root.flow.json` 描述流程。运行台必须同时验证：

```json
{
  "protocol": {"id": "CF-FARP", "version": "1.0"},
  "execution_plan": {
    "schema": "cartridgeflow.execution_plan.v1",
    "entry": "start",
    "edges": []
  }
}
```

`CF-FARP@1.0` 的可执行关系来自 `execution_plan.edges`，不能把普通 `root_flow.edges`、旧版 `next` 或视觉连线当成 v1 执行依据。

### 4.2 当前 demo 支持的节点与边

demo 实现最小交接范围：

| 节点 | 条件 | 行为 |
|---|---|---|
| `system` / `control` | 作为控制节点 | 沿 sequence edge 继续 |
| `terminal` | 终止节点 | 返回 completed |
| `decision` + `executor=llm` | 模型节点 | mock 或 OpenAI-compatible HTTP |
| `mcp_execute` + `executor=mcp` | MCP 节点 | 当前仅支持 `filesystem_write` |
| `human_gate` + `action=confirm_checkpoint` | 人工审核 | mock 自动批准；真实模式中止（fail-closed，交互审核需生产实现） |
| `process` + `action=pass_result` | 确定性产物 | 按 outputs artifact target 落盘 |

| 边 | demo 行为 |
|---|---|
| `sequence` | 顺序后继 |
| `loop` | 按 `continue_when`（`$store.key.field` 求值）决定继续或 `exit_to` |
| `fork` / `join` | 顺序模拟各分支，join 等齐后继续（校验分支数与 join 目标一致） |
| `failure` | 不执行——生产运行台必须实现 fail-closed 路由 |

### 4.2.1 成熟流程形态（样例包演示）

- **驳回重写循环**（`dev.blog-writer`）：`confirm_checkpoint` 的 `params.interaction.answer_routes` 定义驳回/批准路由——驳回 `policy=resume_target_node` + `target_node` + `clear_store_keys` + `copy_answer_to`；批准 `resume_same_node`。`loop` 边（`continue_when: "$approval.feedback"`、`exit_to`）驱动循环；`approval` 键被清空时下一轮审核重新暂停。
- **fork/join 并行**（`dev.parallel-research`）：`fork` 边共享 `fork.id`、各分支带 `fork.branch`；`join` 边共享 `join.id`/`join.mode`（all）/`join.branches`，每条 join 边还必须带自己的 `join.branch`。join 等齐全部分支才继续。
- **LLM 节点可靠性**（三个新包均配置）：每个 `llm_prompt` 节点声明节点级 `retry_policy`（`max_attempts`/`initial_delay_seconds`/`max_delay_seconds`）——模型偶发空响应（`PROVIDER_EMPTY_RESPONSE`，`finish_reason=length`）时引擎自动重试，耗尽才走 failure 边。生产运行台应实现等价的重试与有界循环（`loop.max_iterations`）。

demo 将非 sequence 边排除在最小执行循环之外的历史说明已不适用：v2.0.0 的 demo 已支持 `loop`/`fork`/`join` 与审核/产物节点；`failure` 边与真实交互审核 UI 仍需生产运行台按 FARP@1.0 完整规范实现。

### 4.3 模型响应

生产适配器应将供应商响应归一化为 `decision_envelope.v1`，至少包含：

```json
{
  "schema": "decision_envelope.v1",
  "status": "resolved",
  "summary": "可审计摘要",
  "payload": {}
}
```

建议明确处理：

- `resolved`：允许声明的 decision consume 继续。
- `blocked`：进入声明的失败路径或人工处理。
- `needs_user_input`：暂停为等待用户状态，不能让下游副作用节点继续。
- 非 JSON、空响应、超时、认证失败和 schema 错误：fail closed。

模型 API 的 endpoint、API key、用户凭据和本地连接名称属于运行台绑定信息，不属于卡带包。

### 4.4 MCP 文件写入

当前卡带的 MCP 节点声明：

```text
allowed_tools = ["filesystem_write"]
permission = write_run_artifacts
failure_policy = fail_closed
```

运行台必须：

1. 根据卡带 allowlist 选择工具，不能接受节点临时指定的任意工具。
2. 将输出路径固定限制在当前运行的 artifact 根目录。
3. 拒绝绝对路径、路径穿越和符号链接逃逸。
4. 记录工具 id、调用时间、结果、字节数和失败原因。
5. 将用户产物与安装包、运行状态和凭据目录分开保存。

## 5. 推荐的生产实现分层

不要把 `verifyArchive()`、模型调用、MCP 调用和业务 UI 写进一个入口文件。建议拆成：

```text
runtime/
  cre/
    zip_reader
    envelope_validator
    signature_verifier
    trust_store
    installer
  farp/
    manifest_validator
    execution_plan_compiler
    execution_plan_runner
    checkpoint_store
  resources/
    model_registry
    mcp_registry
    permission_broker
    resource_preflight
  artifacts/
    run_store
    artifact_store
    delivery_projection
  observability/
    audit_log
    metrics
    redaction
```

每一层都应该有独立的输入和输出类型。尤其不要让执行器直接读取 UI 状态或开发台 API。

## 6. 安装、绑定、激活状态机

建议使用以下不可逆步骤：

```text
discovered
  -> staged
  -> bytes_validated
  -> signature_validated
  -> trusted
  -> compatible
  -> waiting_for_binding
  -> ready
  -> active
```

失败状态应该保留机器可读原因，例如：

```text
cre_bundle_path_invalid
cre_digest_invalid
cre_signature_invalid
cre_publisher_untrusted
recognized_unsupported_protocol
missing_required_capability
resource_binding_required
permission_denied
runtime_contract_invalid
```

任何失败都必须清理暂存目录，保持旧激活版本不变。激活必须是原子操作；不能先删除旧版本，再尝试安装新版本。

## 7. 测试和验收矩阵

### 7.1 正向测试

- 合法签名包验证成功。
- 受信包安装成功。
- CF-FARP@1.0 sequence 流程执行成功。
- 模型 HTTP 调用成功并得到标准 envelope。
- MCP artifact 写入运行目录成功。
- 运行结果包含 `release_id`、状态、trace 和 artifact 引用。
- 同一包重复验证得到相同 `release_id`。

### 7.2 反向测试

- 修改 `release.manifest.json` 后签名失败。
- 修改 `hashes.json` 后摘要失败。
- 修改 payload 文件后摘要失败。
- 删除信任库 key 后安装被拒绝。
- ZIP 中加入 `../escape.txt` 被拒绝。
- ZIP 中加入重复路径被拒绝。
- ZIP 中加入未列出的文件被拒绝。
- 模型返回空响应、非法 JSON、HTTP 401、超时，流程 fail closed。
- MCP 路径逃逸被拒绝。
- 兼容性不足时不能激活新版本。
- 新版本安装失败时旧激活版本仍可运行。

### 7.3 交付证据

运行台团队交付时应提供：

1. 运行台版本和 Node.js 版本。
2. 支持的 Base Contract、CF-CRE 和 CF-FARP 版本。
3. 信任库来源、密钥轮换和吊销策略。
4. 正向和反向测试报告。
5. 一份真实 `.cf-cre.zip` 的 verify/install/run 日志。
6. 不包含 API key、用户文件和绝对路径的脱敏日志。
7. 失败包不会覆盖旧激活版本的证明。

## 8. 从 demo 到生产的实施顺序

### 阶段 A：复制协议边界

- 保留 `verify -> install -> run` 顺序。
- 把 demo 的 JSON 输出转换成稳定 TypeScript 类型。
- 为每个失败原因建立错误码和用户可见文案。

### 阶段 B：接入真实资源

- 实现模型 provider registry 和用户绑定界面。
- 实现 MCP stdio/HTTP adapter 和 permission broker。
- 将 endpoint、token、模型名保存在运行台私有配置中。

### 阶段 C：补齐运行语义

- 实现 FARP execution plan 的 branch、fork、join、loop、wait、retry、cancel、checkpoint 和恢复。
- 为副作用节点建立幂等键和 replay guard。
- 将 `needs_user_input` 变成可恢复的暂停状态。

### 阶段 D：安装生命周期

- 实现版本共存、原子激活、升级、回滚和卸载。
- 保留旧 `release_id` 与运行记录的引用。
- 保留用户 artifact，不随卸载删除。

### 阶段 E：产品化验收

- 运行台 UI 只展示公开合同和公开运行投影。
- 所有密钥、内部 prompt、MCP 参数和节点图在普通用户界面不可见。
- 在 Windows、macOS、Linux 各完成一次签名包安装和运行。

## 9. 交接完成定义

运行台团队可以在以下条件全部满足后宣布完成第一阶段接入：

- 能独立验证并拒绝非法 CF-CRE@1 包。
- 能在本地信任库下安装和激活合法包。
- 能执行至少一个 CF-FARP@1.0 的模型节点和 MCP 节点。
- 能生成不泄露凭据的运行记录和 artifact 记录。
- 能证明失败安装不会破坏旧版本。
- 能在不安装 Python 的机器上完成上述流程。
- 测试日志和实现版本可以被另一名工程师独立复现。

完成这份最小闭环后，再扩展完整运行语义和生产安装生命周期；不要先把 demo 当成生产实现，也不要为了兼容 demo 而放宽协议校验。

## 10. 参考文件

- `protocol-source/protocol-source.sqlite` 的 `current:protocol/release-envelope/1/specification.md`：CF-CRE@1 原本。
- `protocol-source/protocol-source.sqlite` 的 `current:protocol/flow-authoring/1.0/` artifacts：CF-FARP@1.0 原本。
- `config/protocol/protocol-registry.sqlite`：本产品锁定的协议发布、生命周期和默认版本副本。
- `config/base/BASE_IMPLEMENTATION.json`：参考 Base 的支持声明。
- `src/core/protocol/release_builder.py`：Base 的发行包构建和检查实现。
- `src/core/protocol/release_signing.py`：签名和本地信任实现。
- `runtime-developer-toolkit/demo/run.mjs`：无 Python 最小运行台参考。
- `docs/development/FILE_INVENTORY.md`：当前源码所有权和入口索引。
