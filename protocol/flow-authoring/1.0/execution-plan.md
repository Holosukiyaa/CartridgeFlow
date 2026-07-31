# CF-FARP@1.0 - Explicit execution plan

This file is a normative module of CF-FARP@1.0. The release is defined only by the same-version modules listed in README and CARTRIDGEFLOW-BASE@0.2.

## 51. 执行计划是唯一控制事实

`CF-FARP@1.0` 以 `root_flow.execution_plan` 取代根级 `edges`、`control_edges` 与节点 `next`。它不是画布投影，也不能由画布自动猜测；执行、分析、工程关系、检查点与认证必须消费同一份声明。

```json
{
  "protocol": {"id": "CF-FARP", "version": "1.0"},
  "states": {
    "start": {"type": "control"},
    "complete": {"type": "terminal"}
  },
  "execution_plan": {
    "schema": "cartridgeflow.execution_plan.v1",
    "entry": "start",
    "edges": [{"id": "start_complete", "kind": "sequence", "from": "start", "to": "complete"}]
  }
}
```

`entry` 必须指向已声明状态；边 `id` 唯一；`from`、`to` 存在；边不得标记 `executable: false`。在 1.0 中出现根级 `edges`、`control_edges`、节点 `next`、`action_route`、`action_routes` 或 `failure_route` 都是阻断错误，不能作为兼容降级路径。

## 52. 关系种类

唯一允许的关系种类为：

```text
sequence | fork | join | loop | batch | wait | failure
```

- `sequence`：成功令牌从来源到目标；一个来源只能有一个成功去向，除非所有成功边属于同一分叉组。
- `fork`：同组边共享 `fork.id` 和来源，每条具有不同 `fork.branch`，至少两个分支；运行器必须保存分支血缘。
- `join`：唯一的成功汇合关系。组内边共享 `join.id`、目标、模式和完整 `join.branches`；`all` 等齐，`any` 需要 `remaining=cancel|drain`，`keyed` 还需要共同的 `key_ref`。
- `loop`：唯一允许的控制环，必须声明稳定 id、正整数 `max_iterations`、`continue_when` 与 `exit_to`；普通顺序环必须拒绝。
- `batch`：必须声明 `items_ref`、正整数 `size`、不大于 size 的 `max_concurrency` 与 `preserve|unordered`；来源序号和批次血缘必须持久化。
- `wait`：必须声明 id、`duration|signal|condition` 模式、超时和 `resume_key`；超时必须走显式失败边，恢复不能重放来源业务节点。
- `failure`：只在声明原因发生时执行；原因只能是 `cancelled`、`exception`、`resource`、`retry_exhausted`、`timeout`、`validation`，且同一来源不得歧义。

普通目标的多个成功入边属于隐式汇合，必须拒绝。可能失败的处理状态必须拥有失败出口；副作用未知结果只能在明确确认后恢复，禁止自动重放。

## 53. 编译、令牌、检查点与恢复

静态校验通过后，Base 必须把作者声明编译为 `cartridgeflow.execution_plan.compiled.v1`。编译产物必须包含稳定 `source_digest`、`plan_digest`、关系身份和可重复的规范化结果；编译不得执行节点业务代码、访问网络或读取运行态秘密。

运行器必须建立 `cartridgeflow.execution_tokens.v1` 令牌账本。每个令牌都必须可追溯到运行、父令牌、分叉、循环、批次和尝试次数。每个检查点必须持久化计划摘要和令牌快照；计划摘要不匹配、损坏或未知副作用都必须阻止自动恢复。

取消、等待、人工交互、汇合、失败和恢复必须留下稳定运行事件。工程视图只可投影编译后的执行关系，并保留 `plan_edge_id`；它不能创建或隐藏真实执行关系。

## 54. 1.0 最低能力、兼容性和认证

1.0 卡带必须声明全部适用的基础 profile 与 capability，并额外声明 `execution_plan_runtime`、`execution_plan_v1_authoring`、`execution_plan_static_conformance`、`execution_plan_compile`、令牌、汇合、等待恢复、取消和摘要保护能力。

兼容性检查必须验证基础契约、完整能力集合、资源预检、执行计划静态校验和目标门禁。认证只能在兼容性零阻断、零警告并通过成功、失败、取消、持久化和恢复测试后发放 `CF-FARP@1.0` 标签。外部 MCP 未绑定或不可读取时必须如实失败或显示不可审计，不能以模拟成功换取认证。
