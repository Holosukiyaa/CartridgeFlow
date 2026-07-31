# CartridgeFlow Base Contract v0.2

契约编号：`CARTRIDGEFLOW-BASE-0.2`

契约状态：active

发布日期：2026-07-21

关系：本文规定 CartridgeFlow 基座实现必须遵守的宿主边界。Flow 的可执行语义由基座声明支持的 CF-FARP 版本规定；本文不重复定义某个 CF-FARP 版本的节点细节。

---

## 1. 契约定位

Base Contract 约束 Base，而不是约束某一张卡带的业务内容。它回答以下问题：

- 基座拥有什么通用能力。
- 卡带、DLC、本机配置和用户产物分别由谁拥有。
- 基座如何声明协议、profile、capability 和 tool pack 支持。
- 外部模型、工具、远程 API 和数据源如何与卡带配方绑定。
- 运行失败、检查点、恢复、副作用重放和 Worker 生命周期如何保持安全。
- 旧协议如何被识别而不强迫基座永久携带旧实现。

本文使用以下规范词：

- MUST / 必须：不满足即违反契约。
- MUST NOT / 不得：明确禁止。
- SHOULD / 应当：除非有可审计理由，否则必须遵守。
- MAY / 可以：实现可选。

## 2. 核心原则

### 2.1 空基座

正式基座 MUST 能在没有任何业务卡带时启动。发布源码树 MUST NOT 预装业务卡带、领域协议、供应商 workflow、模型权重或卡带专属 UI。

删除一张卡带后，如果某段实现不再具有跨领域意义，该实现不属于基座。

### 2.2 声明优先

基座、卡带、工具和 DLC MUST 通过机器可读声明描述自身。实现不得依赖目录残留、命名猜测、隐藏默认值或某台开发机的环境偶然成立。

### 2.3 事实分离

以下事实来源不得互相替代：

| 事实 | 权威来源 |
|---|---|
| 基座真实支持范围 | `BASE_IMPLEMENTATION.json` |
| Flow 运行语义 | 当前 CF-FARP 正文与 registry |
| 卡带需求 | `manifest.json` 与 `root.flow.json` |
| 卡带专属实现 | 卡带 `dlc/` |
| 本机连接与凭据 | 基座本机配置 |
| 已验证能力 | conformance 报告与 evidence manifest |

### 2.4 失败关闭

缺少协议、能力、权限、依赖、配置、输入或产物时，基座 MUST 明确阻断、暂停或降级。不得把缺失能力、空结果、mock 或 fallback 合并成普通成功。

## 3. 所有权模型

### 3.1 基座拥有

基座 MAY 拥有：

- 卡带发现、校验、安装和卸载宿主。
- 协议 registry、兼容性检查和认证框架。
- Root Flow 调度、Store、事件、检查点和恢复框架。
- 通用文件、媒体辅助、Artifact、Delivery 和诊断能力。
- LLM Provider 宿主和本机模型绑定。
- MCP、远程 API、数据源和本机凭据配置入口。
- Portable DLC descriptor、作用域代理、隔离 Worker 和前端 sandbox。
- 通用开发工作台、测试台和资源管理页面。

### 3.2 卡带拥有

卡带 MUST 拥有：

- 业务 Manifest、Root Flow、prompt、schema 和静态资产。
- 业务工具、领域协议、供应商 workflow 和专属 UI。
- 模型角色配方与工具资源角色，不含本机 URL、密钥或个人路径。
- 卡带级测试、迁移脚本和资源所有权声明。

### 3.3 本机配置拥有

本机配置 MUST 拥有：

- Provider URL、API key、认证 header 和代理设置。
- MCP command、远程 API endpoint、OpenAPI 地址和凭据引用。
- 数据源位置、刷新策略和访问凭据。
- 卡带配方角色到本机资源实例的绑定。

本机配置 MUST NOT 被打包进卡带或协议文件。

### 3.4 用户拥有

用户拥有其输入、明确保存的草稿和用户 Artifact。普通卸载 MUST 默认保留用户 Artifact，除非用户对 `purge_all` 进行独立高风险确认。

## 4. Base Implementation 声明

每个基座实现 MUST 提供 `BASE_IMPLEMENTATION.json`。最小结构：

```json
{
  "schema_version": "0.2",
  "implementation_id": "cartridgeflow.reference-dev",
  "implementation_version": "0.1.0",
  "base_contract": {
    "id": "CARTRIDGEFLOW-BASE",
    "version": "0.2"
  },
  "supported_protocols": [
    {"id": "CF-FARP", "version": "0.6", "status": "partial"}
  ],
  "profiles": [],
  "capabilities": [],
  "tool_packs": [],
  "conformance": {
    "status": "partial",
    "report_path": ".data/conformance/latest.json"
  }
}
```

规则：

1. `base_contract` MUST 精确声明本实现遵守的 Base Contract。
2. `supported_protocols` 只列出本实现愿意运行的协议版本。
3. `partial` 表示只支持该协议的声明能力子集，不得包装成完整支持。
4. capability 只有在 evidence manifest 中存在实现与测试证据时才可声明。
5. 外部真实能力没有经过真实环境验证时 MUST 标记为 partial、external_unverified 或等价状态。

## 5. 协议版本生命周期

基座 MUST 区分四种状态：

| 状态 | 含义 | 是否运行 |
|---|---|---|
| `supported` | 出现在 Base Implementation 支持矩阵 | 按声明能力运行 |
| `recognized` | 只保留身份与迁移提示 | 不运行 |
| `unsupported` | 已知但当前基座拒绝 | 不运行 |
| `unknown` | 无法确认身份 | 不运行 |

规则：

1. 识别旧协议不要求基座保留旧 validator、runtime adapter 或完整正文。
2. 一个最小历史索引 MAY 只保存协议 ID、版本、状态、摘要、校验和和迁移目标。
3. 完整历史规范 MAY 由独立档案、Release 或其他只读介质保存。
4. 未出现在 `supported_protocols` 中的版本 MUST 在解析业务 Flow 前失败关闭。
5. 基座不得静默使用当前语义解释旧协议。
6. 是否支持 N-1 版本由 Base Implementation 明确声明，不是 Base Contract 的永久义务。

## 6. 卡带接入边界

### 6.1 Manifest 预读

基座 MAY 在不执行卡带代码的情况下预读以下元数据：

- 卡带身份和版本。
- Base Contract 要求。
- Flow Protocol 要求。
- profile、capability、tool 和 resource role 要求。
- 权限、依赖、DLC descriptor 路径和交付状态。

在兼容性和完整性校验通过前，基座 MUST NOT 导入卡带代码、启动 Worker、执行前端脚本、联网或写业务文件。

### 6.2 兼容性报告

兼容性报告 MUST 至少包含：

```json
{
  "ok": false,
  "base_contract": {},
  "protocol": {},
  "profiles": {},
  "capabilities": {},
  "tools": {},
  "resources": {},
  "permissions": {},
  "findings": []
}
```

存在 blocker 时不得运行或认证。warning MUST 对开发者可见；如果 warning 会改变交付质量，最终用户也必须可见。

## 7. 模型配方和本机绑定

卡带 MAY 携带模型角色配方，例如：

```json
{
  "schema": "cartridgeflow.llm_recipe.v1",
  "roles": [
    {
      "id": "analysis_model",
      "label": "分析模型",
      "capability": "text.reasoning",
      "api_type": "openai_compatible",
      "wire_api": "responses",
      "model": "configured-locally",
      "required": true
    }
  ]
}
```

配方 MUST NOT 包含 URL、API key、token、Authorization、私有 header 或本机绝对路径。

基座通过稳定角色 ID、名称或显式 assignment 将配方连接到本机 Provider。缺少绑定时 MUST 返回配置缺失错误并阻止真实调用。

## 8. 工具、远程 API 和数据源绑定

卡带只能声明工具配方和资源角色。连接实例由本机工具配置提供。

```json
{
  "resource_requirements": [
    {
      "role": "document_search",
      "kinds": ["mcp", "remote_api"],
      "required": true
    }
  ]
}
```

规则：

1. 卡带包不得保存 endpoint、OpenAPI 私有地址、command 中的密钥或认证值。
2. Flow 节点引用 `resource_role` 或 manifest tool ID，不直接保存连接秘密。
3. 本机资源绑定 MUST 在运行前预检。
4. 测试环境可以使用全局资源；打包后只携带角色和契约，不携带本机绑定。
5. 供应商专属协议、workflow 解释器和返回值解析 MUST 位于卡带 DLC 或外部适配包。
6. 基座通用远程能力不得硬编码供应商名称、默认端口或个人服务地址。

## 9. 运行状态与错误

基座 MUST 使用合法状态迁移，不得任意写状态字符串。

Run 至少支持：

```text
created -> running
running -> paused_waiting_user | completed | failed | cancelled | interrupted
failed | interrupted -> retrying | recovering | rolling_back | cancelled
retrying | recovering | rolling_back -> running | completed | failed | cancelled | interrupted
```

所有公开错误 MUST 使用稳定结构：

```json
{
  "schema": "runtime_error_envelope.v1",
  "error_id": "err_...",
  "code": "TOOL_TIMEOUT",
  "category": "tool",
  "message": "...",
  "run_id": "...",
  "node_id": "...",
  "source": "runtime.tool",
  "missing_inputs": [],
  "retryable": true,
  "recoverable": true,
  "recovery_actions": ["retry_node"],
  "cause_chain": []
}
```

同一次失败在事件、运行快照、HTTP 响应和 UI 中 MUST 保持相同 `error_id`、`code` 与语义。完整堆栈只写入本机诊断文件，公开 envelope MUST 脱敏。

## 10. 检查点、重试和恢复

### 10.1 检查点

每个节点执行前后 SHOULD 持久化检查点。检查点至少记录：

- run、node、phase、revision 和时间。
- Store 摘要及 hash。
- 上游 revision。
- Artifact 身份。
- 事件快照。
- 重放安全信息。

### 10.2 恢复动作

基座 MUST 区分：

- `retry_current_node`：恢复节点前检查点并重试。
- `resume_checkpoint`：从最近成功检查点继续。
- `rollback_to_node`：使目标之后状态失效并重走。
- `restart_run`：使用原始输入创建新运行语义。

这些动作不得在 UI 中合并成含义模糊的“重试”。

### 10.3 副作用重放

工具契约 MUST 声明 `idempotent`。非幂等或未知幂等性的副作用节点在自动重试、恢复或回滚前 MUST 暂停并要求明确确认。

重试策略 MUST 有最大次数、退避、单次超时和总超时。无限重试违反契约。

## 11. Artifact 与持久数据

Artifact MUST 是结构化记录，不只是文件路径。最小字段：

- 稳定 `artifact_id`。
- run、source node、type、MIME、path、size 和 hash。
- revision、visibility、ownership 和状态。
- 可获得时记录直接输入、工具版本、Provider/model 和工作流版本。

上游输入或审批 revision 改变时，受影响的下游 Artifact MUST 标记失效，不能继续作为最新交付展示。

运行 Store 不应承载大二进制。持久状态写入 MUST 由显式副作用节点完成，并接受权限、审计、失败和恢复约束。

## 12. Portable DLC 宿主

### 12.1 发现

DLC 发现阶段只读 descriptor 和文件 hash，不执行代码、不联网、不启动进程。

### 12.2 后端

可卸载 DLC 后端 MUST 在独立执行域运行。主服务只保存作用域代理和 descriptor 元数据，不得 import 卡带 backend。

### 12.3 前端

DLC 前端 MUST 在 sandbox iframe 或等价隔离域运行。不得获得主前端 DOM、同源权限、全局 Store、路由器或 CSS 控制权。

### 12.4 作用域

DLC 工具、协议 Overlay 和 UI 只对拥有它的卡带可见。默认全局 Registry 不得暴露卡带工具。

### 12.5 卸载

停用和卸载 MUST：

1. 拒绝新调用。
2. 等待或取消活动调用。
3. 终止 Worker。
4. 销毁前端 sandbox。
5. 注销代理、路由和协议 Overlay。
6. 删除 package 与 private_data。
7. 按用户选择保留或清除 user_artifact。
8. 执行无残留检查。

## 13. Worker 生命周期

Worker 调用 MUST 可被 run cancel、timeout 和 host shutdown 终止。最终状态必须结构化记录为 succeeded、failed、timed_out 或 cancelled。

stdout 只承载协议响应；日志写入 stderr 或 run-scoped 日志。Worker 返回值必须是 UTF-8 JSON 对象，超大或二进制产物通过 Artifact 引用传递。

## 14. 前端和用户交互

基座前端分为：

- 最终用户模式：输入、交互、进度、错误和交付。
- 开发者模式：Flow 编辑、测试、诊断、资源绑定和发布预检。

最终用户不得被迫理解节点图。开发者必须能查看协议字段、Store、错误、检查点、工具调用和 Artifact 来源。

交互按钮只修改草稿值；只有显式提交接口可以回答 pending interaction 并恢复运行。

## 15. 测试与证据

Base Implementation 声明的每个 capability MUST 映射到：

- 实现入口。
- 至少一个正向测试。
- 适用时至少一个失败测试。
- UI 可见性或 `not_applicable` 说明。
- 真实外部能力的验证状态。

Conformance 报告 MUST 由真实测试结果生成，不得手工维护通过列表。mock、fixture 和 dry-run 只证明对应测试路径，不证明真实外部质量。

## 16. 发布与变更

### 16.1 不改变契约的修改

以下通常不需要新 Base Contract：

- 修复实现 bug，但不改变公开语义。
- 改善 UI 样式或性能。
- 新增符合既有宿主接口的卡带或 DLC。
- 新增本机 Provider 或资源实例。
- 补充测试和诊断。

### 16.2 必须发布新契约的修改

以下必须发布新的完整 Base Contract：

- 改变所有权边界。
- 改变支持/识别协议的含义。
- 改变公开错误、恢复或卸载的强制语义。
- 改变本机秘密与卡带配方的边界。
- 改变 DLC 隔离或资源保留规则。

### 16.3 快照

已发布 Base Contract 是不可变快照。新版本 MUST 独立完整，不得要求读取旧版本补足含义。

## 17. 一致性清单

一个符合本契约的基座至少满足：

- [ ] 空卡带状态可以启动。
- [ ] `BASE_IMPLEMENTATION.json` 可验证。
- [ ] 未支持协议在执行 Flow 前被拒绝。
- [ ] 卡带不携带本机 URL、密钥和绑定。
- [ ] 外部供应商实现不进入通用源码。
- [ ] 运行错误跨事件、HTTP 和 UI 保持同一身份。
- [ ] 检查点可以持久化并区分四类恢复动作。
- [ ] 非幂等副作用不会未经确认自动重放。
- [ ] Worker 可由 timeout、cancel 和 host shutdown 终止。
- [ ] 默认 Registry 不暴露卡带 DLC 工具。
- [ ] 卸载删除能力和私有数据、保留用户 Artifact。
- [ ] 所有 capability 有机器证据。

## 18. 与 CF-FARP 的关系

Base Contract 规定“宿主必须如何承载协议和卡带”。CF-FARP 规定“Flow 本身如何声明和执行”。

卡带分别声明：

```json
{
  "base_contract": {
    "id": "CARTRIDGEFLOW-BASE",
    "version": "0.2"
  },
  "runtime_contract": {
    "protocol": "CF-FARP",
    "protocol_version": "0.6"
  }
}
```

二者版本不要求相同，也不得再通过“必须相等”判断兼容性。
