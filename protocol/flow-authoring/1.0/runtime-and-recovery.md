# CF-FARP@1.0 - Runtime and recovery

This file is a normative module of CF-FARP@1.0. The release is defined only by the same-version modules listed in README and CARTRIDGEFLOW-BASE@0.2.

## 19. Run 与节点状态

Run 合法状态：

```text
created running paused paused_waiting_user failed interrupted
retrying recovering rolling_back completed cancelled
```

Node 合法状态：

```text
entered paused_waiting_user completed failed cancelled
```

Tool Call 合法状态：

```text
queued running retrying succeeded failed timed_out cancelled
```

Interaction 合法状态：

```text
waiting_user answered cancelled expired
```

状态只能沿 Base 声明的合法迁移表变化。终态不得被普通更新重新打开。

### 19.1 Run 迁移

```text
created -> running | cancelled
running -> paused | paused_waiting_user | completed | failed | interrupted | cancelled
paused -> running | cancelled | interrupted
paused_waiting_user -> running | cancelled | interrupted
failed | interrupted -> retrying | recovering | rolling_back | cancelled
retrying | recovering | rolling_back -> running | completed | failed | interrupted | cancelled
```

completed、cancelled 是终态。对终态执行 restart 必须创建新的 Run identity 或明确的新 attempt/revision，不能原地改回 running。

### 19.2 Node、Tool 与 Interaction 迁移

Node entered 后可 completed、failed、cancelled 或 paused_waiting_user。Tool queued 后可 running/cancelled；running 后可 retrying、succeeded、failed、timed_out 或 cancelled。Interaction 只能从 waiting_user 进入 answered、cancelled 或 expired。

### 19.3 状态事件

每次迁移 MUST 记录 entity、identity、from、to、reason、timestamp 和触发者。非法迁移必须被拒绝并生成稳定错误，不得只记录日志后继续。

## 20. Runtime Error Envelope

公开失败 MUST 使用：

```json
{
  "schema": "runtime_error_envelope.v1",
  "error_id": "err_...",
  "code": "DEPENDENCY_UNAVAILABLE",
  "category": "dependency",
  "message": "运行依赖当前不可用。",
  "run_id": "run_...",
  "node_id": "call_service",
  "source": "runtime.tool",
  "missing_inputs": [],
  "retryable": true,
  "recoverable": true,
  "recovery_actions": ["check_dependency", "retry_node"],
  "cause_chain": []
}
```

规则：

1. code MUST 稳定，不能把所有失败归为 unknown。
2. 同一错误跨事件、run snapshot、HTTP 和 UI 保持同一 error_id。
3. cause_chain MUST 脱敏。
4. 完整 traceback 只进入本机诊断文件。
5. 未识别错误使用 `INTERNAL_UNEXPECTED` 或等价稳定 code，并作为实现缺陷处理。

### 20.1 最低错误分类

Base 至少稳定区分：

- required input / Store path 缺失。
- Decision Envelope 解析或 schema 失败。
- Decision Consume path 缺失。
- Provider 配置缺失、认证失败、限流、超时和响应非法。
- resource binding 或 dependency 缺失。
- tool validation、tool timeout、worker crash 和 tool result 非法。
- permission 拒绝与 replay confirmation required。
- checkpoint 缺失或损坏。
- Artifact 文件、primary output 或 delivery 不完整。
- asset 缺失、hash/size/media type 不匹配、悬空引用或主动内容伪装为被动资产。
- interaction component、mode、action、payload schema、input revision 或 route 不一致。
- frontend script、CSP、sandbox token、network/origin guard、process isolation、Host capability、channel scope 或 descriptor files 闭包失败。
- DLC descriptor、hash、scope、sandbox 或 lifecycle 失败。
- 内部未知缺陷。

### 20.2 传播规则

1. 节点失败创建一次 error_id。
2. Node event、Run snapshot、HTTP response 和 UI 引用同一 envelope。
3. 包装层 MAY 添加上下文，但不得更换原 code 或丢失 source node。
4. 用户可见 message 不得泄露密钥、绝对私有路径或完整第三方响应。
5. recovery_actions 必须与 retryable、recoverable、effect 和 checkpoint 事实一致。

### 20.3 本机诊断

完整 traceback、原始异常链和必要的脱敏上下文写入 run-scoped 本机诊断文件。公开 envelope 可包含 diagnostic reference，但不得允许越权读取其他 Run 或卡带诊断。

## 21. Checkpoint

节点执行前后 SHOULD 写入 `cartridgeflow.run_checkpoint.v1`：

```json
{
  "schema": "cartridgeflow.run_checkpoint.v1",
  "checkpoint_id": "cp_...",
  "revision": 1,
  "run_id": "run_...",
  "node_id": "plan",
  "phase": "before",
  "outcome": "entered",
  "store_sha256": "...",
  "input_summary": {},
  "upstream_revisions": [],
  "artifact_ids": [],
  "replay": {}
}
```

检查点 MUST 原子写入，并能在进程重启后读取。敏感值只能保存脱敏摘要或受保护快照。

### 21.1 Checkpoint 内容

除最小示例外，checkpoint SHOULD 保存或引用：

- run identity、attempt 与协议版本。
- node identity、phase、outcome 和 revision。
- 原始输入摘要与 Store snapshot/hash。
- 已提交事件边界。
- Artifact identity、revision 和状态。
- pending interaction 与审批 revision。
- tool call replay metadata。
- 上游节点/输入 revision。
- 创建时间和完整性 hash。

### 21.2 写入边界

节点前 checkpoint 必须在副作用启动前提交；节点后 checkpoint 必须在 output、Artifact 与事件一致提交后写入。写入失败时不得声称恢复能力可用。

### 21.3 读取与损坏

Checkpoint 列表、内容和 hash 必须在 Base 重启后可读。缺失、截断、hash 不匹配或 schema 不兼容时返回结构化错误，不能选用随机较旧快照继续。

## 22. Retry、Resume、Rollback 与 Restart

四类动作语义不同：

| 动作 | 起点 | 语义 |
|---|---|---|
| `retry_current_node` | 当前节点前检查点 | 重试同一节点 |
| `resume_checkpoint` | 最近成功检查点 | 从成功边界继续 |
| `rollback_to_node` | 目标节点前检查点 | 使下游失效并重走 |
| `restart_run` | 原始输入 | 创建整轮重新运行语义 |

规则：

1. 恢复 MUST 保存失败经验、用户反馈和来源 error_id。
2. 回滚 MUST 使目标之后的 Store、Artifact、审批和缓存失效，但保留 revision 历史。
3. 重试只适用于错误和节点契约允许的情况。
4. max attempts、退避和总超时 MUST 有界。
5. 不得把四类操作合并成一个无语义的“重试”按钮。

### 22.1 retry_current_node

从当前失败节点的 before checkpoint 恢复。只有 error、node、tool 和 replay policy 都允许时才能执行。重试必须增加 attempt 并关联原 error_id。

### 22.2 resume_checkpoint

从最近成功 after checkpoint 继续。Base 必须验证后续拓扑、输入 revision、Artifact 状态和 pending interaction 仍与快照一致。

### 22.3 rollback_to_node

回滚到目标节点 before checkpoint，并使目标之后的 Store revision、Artifact、审批、缓存和 pending interaction 失效。历史记录保留，只是不能继续作为 latest 或 delivered。

### 22.4 restart_run

使用原始输入和可选明确反馈创建新的 Run identity。旧 Run 保持原终态，新 Run 记录 parent_run_id 与 restart reason。

### 22.5 恢复反馈

用户反馈和人工修复信息必须进入结构化 recovery context，供重试节点显式读取。不得把反馈只拼进隐藏 prompt 而不记录来源。

## 23. Replay Safety

安全重放条件：

- effect 为 `none | read_only | writes_store`，或
- 所有工具明确声明 `idempotent=true`，并满足其 deduplication 契约。

其他副作用在自动恢复前 MUST 返回 `REPLAY_CONFIRMATION_REQUIRED` 或等价错误并暂停等待确认。

确认只授权当前恢复动作，不得成为永久绕过权限的开关。

### 23.1 幂等性分类

- `idempotent=true`：相同 idempotency/deduplication key 重放不会重复产生业务副作用。
- `idempotent=false`：重放可能重复创建、发布、扣费或通知。
- 未声明：按不安全处理。

只读不自动等于幂等；如果读取会推进游标、消费消息或触发计费，必须按真实副作用声明。

### 23.2 自动重试边界

自动重试只处理明确 transient 且 retryable 的失败，并同时满足最大次数、退避、单次 timeout 和总 timeout。参数、资源 binding 或业务输入变化后不再是同一次自动重试，应创建新的人工恢复动作。

### 23.3 部分成功

工具超时或 worker crash 后如果无法证明副作用未发生，状态必须标记 unknown_effect 或等价风险，并要求用户确认、查询外部状态或执行 compensation。不得直接自动重放。

## 24. Artifact

Artifact 最小记录：

```json
{
  "artifact_id": "artifact_report",
  "run_id": "run_...",
  "source_node": "build_report",
  "type": "document",
  "mime_type": "text/markdown",
  "path": "...",
  "size": 0,
  "sha256": "...",
  "revision": 1,
  "visibility": "user",
  "ownership": "user_artifact",
  "status": "draft",
  "inputs": [],
  "producer": {}
}
```

合法状态 SHOULD 包含：

```text
draft preview approved delivered invalidated archived
```

Artifact MUST 可反查 source node、run 和直接输入。上游 revision 改变后，下游旧 Artifact 必须 invalidated，不能继续显示为最新交付。

### 24.1 Provenance

Artifact producer SHOULD 记录：

- source node 和 Flow/Cartridge version。
- 直接 input Store keys 与 revision。
- Decision consume revision。
- tool identity、DLC version 与 call id。
- Provider role、model 和 execution mode（适用时）。
- 用户审批 interaction 与 answer revision。

无法公开的敏感数据可以记录 hash 或受保护引用，但不能完全丢失来源关系。

### 24.2 Revision

同一逻辑 Artifact 的内容变化 MUST 增加 revision。新 revision 不得覆盖唯一历史文件后仍声称可回滚。preview、approved 和 delivered 状态必须绑定具体 revision。

### 24.3 Invalidation

上游输入、Decision projection、工具结果、审批或 Flow version 改变时，Base 必须沿 provenance 关系标记受影响下游 Artifact invalidated。invalidated Artifact MAY 被归档和查看，但不得作为最新 primary output。

### 24.4 文件与引用验证

Artifact 状态变为 approved 或 delivered 前，Base MUST 验证引用目标存在、size/hash 匹配且位于允许 ownership 范围。缺失文件、空占位、目录路径或越权 URL 不得通过交付门禁。

## 25. Delivery

Delivery MUST 汇总：

- 最终输入摘要。
- 主要决策投影。
- 工具与恢复摘要。
- 审批 revision。
- 主要 Artifact 和辅助 Artifact。
- 未满足项与 fallback。

Manifest 示例：

```json
{
  "delivery": {
    "type": "summary_with_artifacts",
    "primary_output": "final_delivery",
    "show_artifacts": true
  }
}
```

缺少 primary output 或其 Artifact 文件时，Run 可以技术完成，但 MUST NOT 标记为成功交付。

### 25.1 Delivery Snapshot

Delivery SHOULD 是不可变或可版本化快照，至少记录：

- delivery id 与 revision。
- run、cartridge、flow 和 protocol identity。
- primary output Store/Artifact identity 与 revision。
- auxiliary Artifact identities。
- 用户输入摘要和审批 revision。
- fallback/mock/dry-run 标记。
- 未满足项和生成时间。

### 25.2 技术完成与成功交付

`run.status=completed` 只表示执行图到达终点；成功交付还要求 primary output 存在、引用有效、未 invalidated、满足 readiness 与审批要求。UI 必须区分这两个概念。

### 25.3 多交付版本

用户修改上游输入或审批后生成的新 Delivery 必须增加 revision，并保留 supersedes 关系。旧版本可以归档查看，不能继续显示为当前完成结果。

## 26. Fallback 与测试替身

Fallback、mock、fixture 和 dry-run MUST 可见。

结果至少记录：

```json
{
  "fallback": true,
  "fallback_reason": "...",
  "execution_mode": "offline_fallback"
}
```

测试台不得把 mock 决策、dry-run 工具或本地占位产物包装成 live/real 结果。使用 fallback 的运行不得获得等同真实路径的质量认证。

Fallback 必须由节点、卡带或 Base 明确声明，不能在捕获任意异常后自动启用。fallback 输出必须通过自己的 schema，并说明哪些质量或副作用保证不成立。

外部 Provider 缺少配置时，Base 默认应返回配置缺失错误；只有卡带明确允许 offline_fallback 且当前运行模式授权时才可使用替代结果。

## 27. 测试台与探针

测试台 MUST 展示：

- 运行模式与 mock/fallback 标记。
- 节点输入输出与 Store 变化。
- Decision Envelope 与 consume 投影。
- 工具调用、effect、permission 和状态。
- Runtime Error Envelope。
- Checkpoint 与恢复动作。
- Artifact 与 Delivery 状态。
- Asset/component identity、hash、interaction mode、input revision、action 和 route。
- passive/sandboxed runtime、CSP、Host capability、channel lifecycle 和脚本安全 finding。

探针范围 MUST 保留原子图拓扑。seeded 数据必须标记，探针通过不等于全流程通过或协议认证。

### 27.1 全流程测试

全流程模式从真实 start 开始，不接受 probe seed，不跳过 required gate，并按声明的 live/mock/tool mode 执行到终态。失败必须保留完整事件、错误和 checkpoint。

### 27.2 探针范围

探针起点和终点必须是合法节点，范围内边来自原子图。范围外 input 可 seeded，但每个 seed 必须通过目标 schema。探针不得通过重连边改变原流程语义。

### 27.3 可观察性

测试台至少展示 execution mode、节点 input/output、Store revision、Decision Envelope、consume path/as/value summary、tool plan、tool call、effect、permission、error、checkpoint、Artifact、Delivery，以及 interaction component/action/revision 和脚本安全状态。测试台不得为了预览方便在主前端直接执行组件脚本。
