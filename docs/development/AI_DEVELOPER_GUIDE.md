# CartridgeFlow v0.2.0 AI Developer Guide

本文用于指导一个没有历史上下文的 AI 或开发者从零接手 CartridgeFlow。它描述正式基座的事实、边界、协议运行方式、Portable DLC 插拔系统、开发顺序和验收标准。

## 1. 接手顺序

开始修改之前，按顺序完成：

1. 阅读根目录 `README.md`、`docs/planning/TODO.md` 和 `docs/planning/ROADMAP.md`。
2. 阅读 `config/base/BASE_IMPLEMENTATION.json`，确认基座真实声明的协议、profile、capability 和 tool pack。
3. 涉及宿主或流程语义时，完整阅读 `docs/protocol/CARTRIDGEFLOW_BASE_CONTRACT_v0.2.md` 与 `docs/protocol/CARTRIDGEFLOW_FLOW_AUTHORING_RUNTIME_PROTOCOL_v0.6.md`。
4. 涉及 DLC 时，阅读 `docs/architecture/PORTABLE_DLC_ARCHITECTURE.md` 和 `src/core/extensions/`。
5. 检查 `git status --short`，保留用户已有改动。
6. 先定位所有权边界，再决定修改核心还是卡带。

不要从某张卡带倒推基座语义。协议和基座是宿主，卡带是消费者。

## 2. v0.2.0 基线

本版本是无预装业务卡带的正式基座。

启动后卡带架为空是正确状态。基座提供：

- manifest 与 root flow 发现、校验和兼容性报告；
- 流程图编辑、运行、探针、事件和数据链诊断；
- 结构化 LLM 决策和 Provider 管理；
- 用户交互暂停、提交与恢复；
- 通用 filesystem/media 工具宿主；
- Artifact 和 Delivery 管理；
- Portable DLC 发现、完整性检查、隔离执行、前端沙箱和卸载；
- 卡带导入、开发克隆和打包。

基座不提供任何具体视频、游戏、3D、动作、分镜或内容生产业务。那些能力只能来自卡带。

## 3. 代码所有权

```text
src/core/protocol/
  协议解释、flow contract、decision envelope、tool plan、认证和报告。

src/core/cartridge/
  卡带 registry、manifest validator、runner、artifact、dependency 和 environment。

src/core/extensions/
  Portable DLC descriptor、tool proxy、worker client/bootstrap/SDK。

src/core/lab/
  开发流程、节点执行、图分析、测试探针和通用 MCP。

src/core/llm/
  Provider 配置、OpenAI wire adapters、重试和错误分类。

src/backend/
  通用 HTTP API。不能放卡带专属路由或业务实现。

src/frontend/
  通用卡带架、流程工作台、测试台和 DLC sandbox host。

.data/user/dev_cartridges/<id>/
  单张开发卡带的全部业务定义和可选 DLC。
```

判断规则：删除一张卡带后，如果某段代码不再有通用意义，它就不属于基座。

## 4. 协议治理

### 4.1 权威来源

机器 registry：

```text
protocol/CARTRIDGEFLOW-BASE-0.2.json
protocol/CF-FARP-0.6.json
protocol/capabilities.json
protocol/profiles.json
protocol/tool_packs.json
```

规范正文：

```text
docs/protocol/CARTRIDGEFLOW_BASE_CONTRACT_v0.2.md
docs/protocol/CARTRIDGEFLOW_FLOW_AUTHORING_RUNTIME_PROTOCOL_v0.6.md
```

基座声明：

```text
config/base/BASE_IMPLEMENTATION.json
```

正文定义语义，registry 定义可发现身份，基座声明定义当前实现范围。三者不能互相冒充。

### 4.2 只读规则

已发布的协议文件是不可变快照。

- 修正文案但改变语义：必须新建协议版本。
- 新增必需字段、状态、能力或副作用规则：必须新建协议版本。
- 修复实现没有改变协议语义：修改基座和 conformance 测试，不修改协议。
- 领域规则：放入卡带 DLC 的 `protocols/`，不能写入根协议目录。

### 4.3 CF-FARP@0.6 运行链

```text
manifest
  -> compatibility report
  -> root.flow.json
  -> process node normalization
  -> executor
  -> store / pending interaction / artifact
  -> delivery
```

Manifest 至少声明身份、root flow、runtime 和输入输出。声明 `runtime_contract` 后，兼容性检查会验证：

- protocol 是否注册并被基座声明支持；
- required profiles/capabilities/tool packs 是否存在；
- required tools 是否在 manifest 中启用；
- root flow 是否满足对应版本契约；
- 认证标签是否与真实报告一致。

### 4.4 Process Node

业务节点统一使用：

```json
{
  "type": "process",
  "kind": "decision",
  "executor": "llm",
  "effect": "none",
  "protocol_version": "0.6"
}
```

- `kind` 表示语义类型，例如 `input`、`decision`、`mcp_read`、`mcp_execute`、`human_gate`。
- `executor` 表示执行者，例如 `user`、`llm`、`mcp`、`human`、`deterministic`。
- `effect` 表示副作用，例如 `none`、`read_only`、`writes_artifacts`、`writes_files`。

有副作用的节点必须声明权限、失败策略和 `audit_log: true`。AI decision 节点不能直接执行副作用。

### 4.5 Decision Envelope

LLM decision 必须输出：

```json
{
  "schema": "decision_envelope.v1",
  "status": "resolved",
  "summary": "...",
  "payload": {"business_value": {}}
}
```

合法状态：

- `resolved`：结果已完成；
- `needs_user_input`：必须暂停；
- `blocked`：无法继续。

业务结果必须用显式 consume 投影：

```json
{
  "consume": {
    "mode": "payload_path",
    "path": "payload.business_value",
    "as": "business_value",
    "on_missing": "fail_closed"
  }
}
```

不得让后续节点从自然语言 summary 猜数据，也不得靠 output key 命名习惯隐式推断。

### 4.6 交互暂停与恢复

`needs_user_input` 和 `human_gate` 会产生 `pending_interaction`。运行状态必须变为 `paused_waiting_user`，后续节点不能执行。

提交答案后，runner 根据 `resume_policy` 恢复：

- `resume_same_node`：重新执行当前节点；
- `resume_next_node`：从下一节点继续；
- answer routes：按结构化答案跳转或回滚。

UI 按钮本身不能直接绕过提交。只有 pending interaction answer API 写入 store 后才能恢复。

### 4.7 测试模式

Decision 模式：

- `live_collaboration`
- `mock_resolved`
- `mock_interaction`
- `mock_blocked`

Tool 模式：

- `real`
- `dry_run`

Mock 和 dry-run 必须带明确标记。不得把测试产物包装成真实生产结果。真实工具不可用时应失败关闭。

## 5. Portable DLC 插拔系统

### 5.1 何时使用 DLC

以下任一条件成立，就应使用卡带 DLC：

- 卡带需要专属 Python 工具；
- 卡带需要专属工作台或复杂 UI；
- 卡带需要领域协议；
- 卡带携带供应商 workflow、模型适配或专属资源；
- 删除卡带后该功能不应继续存在。

### 5.2 目录结构

```text
.data/user/dev_cartridges/<cartridge-id>/
  manifest.json
  root.flow.json
  dlc/
    descriptor.json
    backend/
      entry.py
    frontend/
      index.html
    protocols/
    workflows/
    tests/
```

### 5.3 Manifest 激活

```json
{
  "portable_dlc": {
    "protocol": "CF-FARP@0.6",
    "descriptor": "dlc/descriptor.json",
    "activation": "manifest_scoped",
    "uninstall": {
      "remove_package_owned_code": true,
      "remove_private_data": true,
      "preserve_user_artifacts": true
    }
  }
}
```

只有 `BuiltinMcpRegistry.for_manifest(..., package_path=...)` 会加载当前卡带 DLC。默认全局 registry 不加载任何卡带代码。

### 5.4 Descriptor

`dlc/descriptor.json` 使用 `cartridgeflow.portable_dlc.v1`，必须声明：

- DLC id/version/owner/scope；
- JSON stdio backend entry；
- 可选 sandbox frontend entry 与 context keys；
- tools；
- 可选领域协议；
- resources ownership；
- files SHA-256。

Descriptor 的 enabled tool 集合必须与 manifest 的 enabled MCP tool 集合完全一致。多一个或少一个都会拒绝加载。

Descriptor 发现阶段只读元数据和文件哈希，不能导入 DLC、联网、启动外部程序或生成文件。

### 5.5 后端 Worker

主进程只保存 `PortableDlcToolProxy`。调用时启动隔离 worker，通过 UTF-8 JSON stdin/stdout 传递：

```json
{
  "schema": "cartridgeflow.dlc_worker_request.v1",
  "cartridge_id": "...",
  "dlc_id": "...",
  "server": "media",
  "tool": "...",
  "params": {}
}
```

卡带入口使用 `core.extensions.worker_sdk.DlcWorkerRegistry` 注册函数。DLC 不得依赖或导入另一张卡带的私有模块。

### 5.6 前端 Sandbox

DLC UI 通过：

```text
GET /api/cartridges/<id>/dlc/frontend
```

进入 `sandbox="allow-scripts"` iframe。不得启用 `allow-same-origin`。

子页面准备完成后发送：

```json
{"schema":"cartridgeflow.dlc_ui_message.v1","type":"ready"}
```

宿主发送：

```json
{
  "schema":"cartridgeflow.dlc_ui_host.v1",
  "type":"load_storyboard",
  "run_id":"...",
  "project":{},
  "artifacts":[]
}
```

`project` 是通用 DLC payload，字段名不应硬编码某个领域。现有 host 为兼容旧 UI 仍使用 `load_storyboard`/`load_result` 类型。

提交交互：

```json
{
  "schema":"cartridgeflow.dlc_ui_message.v1",
  "type":"submit_interaction",
  "values":{}
}
```

### 5.7 资源所有权

- `package`：随卡带删除；
- `private_data`：卸载时删除；
- `shared_dependency`：不自动删除；
- `user_artifact`：默认保留。

路径必须明确，不能把整个工作区声明为私有数据。卸载测试必须证明工具代理失效、私有数据删除、用户产物保留。

### 5.8 完整性哈希

每次修改 descriptor `files` 中的文件后，都必须重新计算 SHA-256 并更新 descriptor。禁止在运行时自动放宽或跳过哈希校验。

PowerShell 示例：

```powershell
Get-FileHash -Algorithm SHA256 .data/user/dev_cartridges/<id>/dlc/backend/entry.py
```

## 6. 从零开发一张卡带

1. 选择唯一 id，例如 `dev.example_flow`。
2. 只创建 `manifest.json` 和 `root.flow.json`，先通过基础兼容性检查。
3. 将业务输入输出写成明确 schema。
4. 将 AI 节点改为 Decision Envelope，并声明 consume。
5. 将只读工具与写入工具分开，声明 effect、permission、failure policy 和 audit log。
6. 需要专属实现时再增加 DLC，不提前创建大而全的扩展层。
7. 给每个用户暂停点提供 input schema 和真实提交路径。
8. 为 mock、dry-run 和 live 分别测试，不能只测 happy path。
9. 测试 descriptor hash、作用域注册、worker UTF-8、大 JSON、卸载无残留。
10. 打包前确认基座没有新增卡带 id、领域工具名或专属 UI 分支。

## 7. 测试与验收

Python：

```powershell
.\.tools\runtimes\python\python.exe scripts\run_conformance.py
```

前端：

```powershell
$env:Path = (Resolve-Path .tools/runtimes/node).Path + ";" + $env:Path
Set-Location src/frontend
npm.cmd run build
```

发布前最低验收：

- 所有 conformance tests 通过；
- 前端 TypeScript 与 Vite build 通过；
- `CartridgeRegistry.list_cartridges()` 在干净仓库返回空列表；
- 默认 `BuiltinMcpRegistry` 不暴露任何卡带工具；
- 临时 Portable DLC 可以注册、调用和失活；
- 仓库不跟踪 `.data/`、`.tools/`、`test_output/`、日志、密钥和模型；
- `VERSION`、`config/base/BASE_IMPLEMENTATION.json`、前端 package version 和 Git tag 一致。

## 8. 禁止事项

- 不修改已发布协议快照。
- 不为单张卡带放宽通用 validator 或 compatibility 规则。
- 不在核心导入卡带 backend。
- 不把卡带工具注册到全局默认 registry。
- 不让 iframe 获得同源权限或任意文件访问。
- 不把 Mock、fixture、placeholder 或静默 fallback 当作生产完成。
- 不提交 API key、Provider 私密配置、模型、缓存、运行产物或第三方受限素材。
- 不在没有测试的情况下改写恢复、回滚、artifact 或卸载语义。

## 9. 修改完成后的交接

最终说明至少包含：

- 改动结果；
- 所有权边界；
- 运行过的测试；
- 未运行或无法验证的真实外部能力；
- 是否改变协议语义；
- 是否需要更新 descriptor hashes 或版本号。

判断完成的最后一句不是“代码写完了”，而是“契约、运行、交互、产物和卸载都能被验证”。
