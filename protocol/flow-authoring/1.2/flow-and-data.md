# CF-FARP@1.1 - Flow and data

This file is a normative module of CF-FARP@1.1. The release is defined only by the same-version modules listed in README and CARTRIDGEFLOW-BASE@0.3.

## 10. Root Flow

```json
{
  "schema_version": "1.0",
  "id": "example.workflow.root",
  "mode": "lifecycle",
  "cartridge_id": "example.workflow",
  "protocol": {
    "id": "CF-FARP",
    "version": "1.1"
  },
  "states": {},
  "execution_plan": {
    "schema": "cartridgeflow.execution_plan.v1",
    "entry": "start",
    "edges": []
  }
}
```

规则：

1. `states` MUST 是非空对象。
2. `execution_plan.entry` MUST 指向存在节点。
3. 生命周期节点 MAY 使用 `type=system | terminal`。
4. 业务节点 MUST 使用 `type=process`。
5. 所有可执行关系 MUST 只出现在 `execution_plan.edges` 中。
6. 从 entry 不可达的节点必须显式标记 isolated/experimental，否则是结构问题。
7. Flow MUST 可静态分析，不得靠运行时猜测生成主拓扑。

### 10.1 拓扑来源

`execution_plan` 是唯一的可执行拓扑来源。它的 `entry`、边身份、关系类型、条件、失败、等待、分叉、汇合、循环和批次语义由 [显式执行计划](execution-plan.md) 定义。数据、模型、工具、MCP、资源和 Artifact 依赖不得伪装为计划边；Analyzer 派生关系也不得被 Runner 解释为后继节点。

### 10.2 生命周期节点

- `type=system` MAY 用于 start、checkpoint 或受控系统事件。
- `type=terminal` 表示路径终止，不执行隐藏业务逻辑。
- 生命周期节点不得伪装成工具、LLM 或持久写入节点。
- 一个 Flow MAY 有多个 terminal，但每条可成功路径必须到达明确终态。

### 10.3 图分析

静态分析至少检查 entry、缺失节点、不可达节点、无出口节点、计划边冲突、未受控循环、数据链来源、分支数据可用性、资源绑定和副作用路径。分析发现与运行事件必须使用稳定 node id。v1.1 Base 必须生成规范化执行计划；前端不得维护另一套决定运行语义的图推导规则。

## 11. 业务节点与两类搭建模型

统一模型：

```json
{
  "type": "process",
  "kind": "decision",
  "executor": "llm",
  "effect": "none",
  "inputs": {
    "request": {"binding": "store:request_context", "required": true}
  },
  "outputs": {
    "decision": {"identity": "store:planning_decision"}
  }
}
```

`kind` 合法基础词表：

```text
input transfer retrieval decision transform validation routing
mcp_read mcp_execute remote_call gate interaction human_gate delivery
```

`executor` 基础词表：

```text
user deterministic rules rag llm mcp remote human plugin
```

`effect` 基础词表：

```text
none read_only writes_store writes_artifacts writes_files
mutates_state external_side_effect
```

节点 MUST 声明与真实行为一致的 kind、executor 和 effect。UI 显示名可以友好化，但不得改变或隐藏协议字段。

作者视角下，Base MUST 将业务节点解释为两类：

- **Capability Node / 能力节点**：除 `kind=interaction` 外的标准业务节点，负责模型、工具、读取、转换、校验、路由、交付等系统工作。
- **Interaction Node / 交互节点**：固定使用 `kind=interaction`，负责展示、收集和审核，并以声明动作把用户结果交还 Flow。

`node_family` 是可由 `kind` 唯一推导的展示属性，不得作为第二个可冲突的持久字段。生命周期 `system | terminal` 节点不属于上述业务节点两类。

### 11.1 通用字段

| 字段 | 语义 |
|---|---|
| `id` | 来自 states key 的稳定节点身份 |
| `display_name` | 画布上的开发者可编辑名称，不参与协议身份或路由 |
| `experience` | 由受信任调优发布物化的普通用户投影，不参与执行语义 |
| `type` | 业务节点固定为 process |
| `kind` | 业务语义分类 |
| `executor` | 实际执行主体 |
| `effect` | 最大副作用级别 |
| `inputs` | 具名输入契约，包含 required、schema 和 binding |
| `outputs` | 具名输出契约，包含 Store/Artifact identity 与 schema |
| `input_schema` | 输入结构约束 |
| `output_contract` | 标准输出容器身份 |
| `allowed_tools` | 节点可调用工具白名单 |
| `tool_binding` | 工具选择来源和绑定方式 |
| `resource_role` | 本机资源抽象身份 |
| `permission` | 副作用授权要求 |
| `failure_policy` | 失败后的运行语义 |
| `audit_log` | 是否记录副作用审计 |
| `replay_policy` | 恢复时的重放规则 |

协议字段 MUST 位于节点顶层；节点不得在嵌套参数中定义另一份可冲突的协议字段。

### 11.2 多输入与多输出

v1.1 作者源文件 MUST 使用结构化 `inputs` 与 `outputs`。字符串、逗号/换行分隔字符串和字符串数组不是本版本的输入输出契约；Analyzer 必须产生 `LEGACY_IO_CONTRACT` finding，production、package 与 publish 目标下是 blocker。

节点不得依赖执行器根据返回字段名临时发明 Store key。每个 required 输入必须有显式 binding，每个输出必须有稳定 identity 和可解析 schema。多个逻辑字段 MAY 写入一个对象输出，但消费者必须通过结构化路径显式绑定。

### 11.3 Executor 规则

| executor | 执行主体 | 约束 |
|---|---|---|
| `user` | 用户输入 | 必须有 schema 和受控提交 |
| `deterministic` | 确定性代码 | 不得隐藏模型或远程调用 |
| `rules` | 规则引擎 | 规则集必须可识别和审计 |
| `rag` | 检索增强处理器 | 外部读取必须声明 resource/tool |
| `llm` | 语言模型 | 必须遵守 Decision 或生成契约 |
| `mcp` | MCP 工具执行器 | 必须经过 Manifest tool 与 allowlist |
| `remote` | 远程服务 | 必须通过本机 resource role |
| `human` | 人工判断 | 缺少答案时形成 interaction |
| `plugin` | 插件/DLC | 必须处于当前卡带作用域 |

真实模型调用必须使用 `executor=llm`。真实工具调用必须使用 mcp、remote 或 plugin 等可审计执行器，不能用 deterministic 名称逃避工具和副作用规则。

### 11.4 Effect 规则

| effect | 允许的改变 |
|---|---|
| `none` | 不产生外部副作用；可以写节点声明 output |
| `read_only` | 读取外部资源，不修改外部状态 |
| `writes_store` | 修改当前 Run Store |
| `writes_artifacts` | 创建或更新 Artifact |
| `writes_files` | 写受权限控制的文件 |
| `mutates_state` | 修改持久业务或卡带私有状态 |
| `external_side_effect` | 对外部系统产生动作 |

effect MUST 表示节点可能发生的最大副作用。副作用不能因测试模式而被低报。`writes_files`、`mutates_state` 和 `external_side_effect` 必须有 permission、failure_policy、audit_log 和 replay_policy。

### 11.5 用户层显示

每个业务节点 MAY 声明 `display_name`。画布应优先显示该名称，但开发者详情中必须同时显示稳定 node id、kind、executor、effect、tool/resource binding 和 permission。

`display_name` 可以修改、本地化或重复，并且必须作为纯文本转义呈现；修改它不得改变 states key、边、Store key、组件引用、日志关联、检查点或恢复身份。Base SHOULD 在运行事件中同时保存稳定 node id 与当次执行所见的 display name snapshot。

普通用户界面 SHOULD 读取活动配方发布物化的 `experience`，只显示开发者明确配置的阶段、动作、物料、结果和可调参数。该对象不得替代 interaction contract、permission、failure policy 或数据契约；缺少 `experience` 时 Base MAY 生成只用于开发预览的安全默认值，但不得把未确认默认值写入已发布配方。

UI MAY 使用“输入节点”“AI 决策节点”“MCP 读取节点”“远程执行节点”“交互节点”“交付节点”等友好名称，也可以使用领域名称。

不得把所有 Process Node 都显示为模糊“处理节点”，也不得用显示标签反向推导协议字段。

### 11.6 能力节点与交互节点边界

1. 能力节点负责业务执行；模型、工具、远程调用、文件写入和 Artifact 生成不得藏入 interaction component 脚本。
2. 交互节点负责界面与用户动作；它不得直接调用其他节点、改写原子图、绕过 gate 或伪造工具结果。
3. 交互组件只能维护 payload 草稿或提出 action intent；Host control 最终提交已声明 `action_id + payload`。恢复由执行计划的 `wait` 边驱动，动作值作为结构化输出供后续节点消费，组件和客户端不得选择后继节点。
4. 可复用内部流程应表达为声明的 Flow/subflow 资产或协议扩展，不得塞入浏览器脚本形成不可观察的隐藏流程。
5. 单个节点真实行为跨越两类时必须拆分。交互 -> 工具 -> 交互是三节点链路，不是一个万能脚本节点。
6. `input`、`human_gate` 或 decision 的 `needs_user_input` MAY 创建由 Base 完全根据 schema 渲染的通用 Pending Interaction；它们仍是标准能力节点，MUST NOT 引用卡带 Interaction Component。
7. 一旦需要卡带自定义 HTML、图片布局、动效、复杂编辑器或脚本，就必须使用显式 `kind=interaction`；不得把自定义界面藏进标准能力节点参数。

## 12. Kind 与交互节点约束

### 12.1 input

- executor：`user | human | remote | plugin`
- effect：`writes_store`
- MUST 声明 `input_schema`、`source` 和 `output`

### 12.2 transfer

- executor：`deterministic | rules`
- effect：`writes_store`
- MUST NOT 调用 LLM、MCP、远程服务或副作用工具

### 12.3 retrieval

- effect：`read_only | writes_store`
- 使用 MCP 时 SHOULD 表达为 `mcp_read`

### 12.4 decision

- executor：`llm | rules | human`
- AI decision MUST 使用 effect=`none`
- MUST NOT 直接执行工具或外部副作用

### 12.5 mcp_read

- executor：`mcp`
- effect：`read_only`
- 只能绑定 `none | read_only | environment_probe` 工具

### 12.6 mcp_execute

- executor：`mcp`
- MUST 声明 `allowed_tools`、`tool_binding`、`permission`、`failure_policy` 和 `audit_log=true`
- effect MUST 与工具 contract 一致

### 12.7 remote_call

- executor：`remote`
- effect：`read_only | external_side_effect | writes_artifacts`
- MUST 声明 `resource_role`、`allowed_tools`、`timeout_ms` 和 `failure_policy`
- 有副作用时 MUST 声明 permission、audit_log 和 replay policy
- MUST NOT 在节点中声明 URL、key 或私有 header

### 12.8 gate / human_gate

- MUST 声明通过、不通过和暂停语义
- human gate 缺少答案时进入 pending interaction

### 12.9 interaction

交互节点标准结构：

```json
{
  "type": "process",
  "kind": "interaction",
  "display_name": "请审核生成结果",
  "executor": "user",
  "effect": "writes_store",
  "interaction_mode": "review",
  "component_ref": "review.result",
  "input_binding": {
    "result": "store:generated_result",
    "images": "store:selected_images"
  },
  "outputs": {
    "answer": {"identity": "store:review_answer"}
  },
  "allowed_actions": ["approve", "revise", "cancel"],
  "wait_id": "review_result"
}
```

通用规则：

1. `interaction_mode` MUST 为 `display | collect | review`，并被目标组件 `supported_modes` 允许。
2. `component_ref` MUST 解析到当前卡带 interaction component；不得引用其他卡带组件或裸 HTML 路径。
3. `input_binding` 的值只能引用节点已声明的 required/optional input、受控 Run metadata 或 Artifact ref。组件不得读取整个 Store。
4. `display` 使用 `executor=deterministic | plugin`、`effect=none`，不得创建等待用户的 interaction；其后续执行只由 `execution_plan` 声明。
5. `collect | review` 使用 `executor=user | human`、`effect=writes_store`；组件脚本是隔离 renderer，不是替代用户的 executor。节点 MUST 声明结构化 `outputs`、`allowed_actions`、`wait_id` 和可解析的 payload schema，并创建可持久恢复的 Pending Interaction。
6. `allowed_actions` MUST 是 component actions 的非空子集；动作只能影响已提交的结构化答案，不得选择或构造执行计划边。
7. Component iframe 只能更新 run-scoped draft 或提出 action intent，不能调用最终 answer/commit API。Host 必须在 iframe 外根据 Registry 生成自身拥有的 action controls；只有用户在 Host control 上的可信操作才能提交 action ID 与当前 draft payload。
8. payload 经 schema 校验后才可写入 output；失败不得恢复 Run。
9. interaction 脚本不因运行在前端而获得 `effect=none` 豁免。它只能通过宿主授权能力产生声明效果，真实能力必须反映在节点 effect、permission、审计和重放规则中。
10. `kind=ui` 不是 v1.1 的合法别名。交互节点必须明确组件、模式、输入、输出、允许动作和等待身份。

提交后 `output` MUST 写入标准答案而不是裸 payload：

```json
{
  "schema": "cartridgeflow.interaction_answer.v1",
  "interaction_id": "interaction_...",
  "action_id": "approve",
  "value": {},
  "input_revision": 3,
  "answer_revision": 1
}
```

下游业务读取声明 output 中的 `action_id` 与 value。Host commit 必须绑定当前 draft hash 与 input revision，避免脚本在用户确认后替换 payload。

#### 12.9.1 Display

Display 用于欢迎页、中间说明、图片、HTML/Markdown 预览和结果展示。它可以引用 passive 或 sandboxed component，但不得等待提交、写业务 Store 或用脚本决定下一节点。需要按钮影响流程时必须改用 collect/review。

#### 12.9.2 Collect

Collect 用于自定义表单、文件选择和结构化用户输入。首次进入时创建 Pending Interaction；页面刷新、Base 重启或组件重新挂载后必须恢复同一 interaction identity、component version、输入 revision 和草稿引用。

#### 12.9.3 Review

Review 用于展示 Artifact、方案或中间结果并收集批准、退回、修改或取消。批准必须绑定被查看内容的 revision；上游内容变化后旧批准必须 invalidated。动作结果由后续节点消费，组件本身不得发起路由、回滚或重放。

### 12.10 delivery

- MUST 声明 input、output 和 primary_output
- primary output 缺失时 Run 不得标记为成功交付

### 12.11 transform

- executor：`deterministic | rules | plugin`
- effect：通常为 `writes_store`
- MUST 声明 input、output 和转换契约或 schema
- 不得以 transform 名义隐藏 LLM 或未声明工具调用

### 12.12 validation

- executor：`deterministic | rules | human | plugin`
- MUST 输出结构化 validation result，而不是只返回 `ok=true`
- 结果 SHOULD 包含 passed、issues、severity 和 checked_revision
- validation 失败与执行器崩溃是不同语义

### 12.13 routing

- executor：`deterministic | rules`
- effect：`none | writes_store`
- routes MUST 可静态枚举，默认分支必须明确
- 不得通过运行时生成任意节点 ID 改写主拓扑

### 12.14 Kind 扩展

卡带领域协议 MAY 增加 kind，但必须通过 Protocol Overlay 声明字段、executor、effect、输入输出、失败和副作用规则。未知 kind 在没有已激活 Overlay 时必须失败关闭。

## 13. Store 与数据链

Store 是单次运行的数据总线。

规则：

1. `input` 是必需输入；`optional_input` 是可选输入。
2. 缺失必需 key 是数据链错误；缺失可选 key 是 info/warning。
3. 节点只能读取声明的 input，写入声明的 output 和协议审计字段。
4. `store:key.path[0]` MAY 用于结构化引用；base key 缺失必须报告。
5. 全流程运行不得使用探针 seeded 数据冒充真实上游。
6. 大二进制必须使用 Artifact，不得内联进 Store。
7. Store key MUST 稳定明确，禁止依赖隐式 output 命名约定。

### 13.1 Store Key 与引用

Store key MUST 匹配 Base 公布的稳定标识规则，SHOULD 使用可读的 snake_case。协议保留字段必须命名空间化，卡带不得覆盖 Run identity、error、checkpoint 或审计元数据。

合法引用形式：

```text
store:request
store:approved_plan.steps[0]
store:tool_result.items
```

Base key 缺失时必须产生数据链 finding。路径成员缺失时按节点 input contract、consume `required` 和 failure_policy 处理，不得返回随机空对象继续。

### 13.2 数据来源与谱系

每次 Store 写入 SHOULD 记录：

- key 与 revision。
- source node 或 interaction。
- 直接 input keys 与 revision。
- execution mode。
- tool call、Decision Envelope 或用户答案 identity。
- 写入时间和可选 value hash。

后续回滚、诊断和 Artifact provenance 必须使用这些记录，而不是从当前值反推历史。

### 13.3 写入语义

1. 节点 output 与对应事件 SHOULD 原子提交。
2. 节点失败时不得留下未标记的半写入值。
3. 覆盖已有 key 时必须生成新 revision，除非节点明确声明 append-only 结构。
4. 用户已审批值被覆盖时，相关审批必须失效或重新确认。
5. 大对象可写入 Artifact 并在 Store 保存稳定 artifact reference。
6. 跨 Run 持久数据不属于普通 Store，必须由显式持久化节点和权限承载。

### 13.4 Probe Seed

探针可为范围外上游输入注入 seeded value，但必须记录 `seeded_by_probe=true`、来源、schema 和有效范围。seed 不能写回真实 Run，也不能成为生产 Delivery 或协议认证证据。

## 14. Decision Envelope

AI decision MUST 输出：

```json
{
  "schema": "decision_envelope.v1",
  "status": "resolved",
  "summary": "已经完成规划。",
  "payload": {
    "plan": {
      "steps": []
    }
  }
}
```

合法 status：

- `resolved`
- `needs_user_input`
- `blocked`

`resolved` 必须提供节点契约要求的 payload。

`needs_user_input` 必须提供 question 与 resume：

```json
{
  "schema": "decision_envelope.v1",
  "status": "needs_user_input",
  "summary": "需要补充目标范围。",
  "question": {
    "id": "target_scope",
    "prompt": "请选择目标范围。",
    "input_schema": {"type": "string"},
    "store_key": "target_scope_reply"
  },
  "resume": {"policy": "resume_same_node"},
  "payload": {}
}
```

`blocked` 必须提供结构化 issues，且不得继续执行后续副作用节点。

### 14.1 resolved

`resolved` 表示 Decision 已产生满足节点业务 schema 的可继续结果。payload 字段由节点自己的 schema 定义，例如 plan、spec、decision、tool_plan 或其他领域中立结构。

resolved MUST：

- 提供非空或 schema 允许为空的 payload。
- 通过 `decision_contract.consume` 暴露后续业务值。
- 不携带“已经调用工具”之类无法审计的隐藏副作用结果。
- 保留 summary 作为人类说明，而不是下游机器输入。

### 14.2 needs_user_input

question 至少包含稳定 id、prompt、input_schema 和 store_key。resume 至少包含 policy；使用 target policy 时还必须包含 target_node。

同一 pending interaction 的 question schema 在回答前不得静默变化。若流程升级导致 schema 不兼容，旧 interaction 必须取消并生成新 identity。

### 14.3 blocked

blocked 示例：

```json
{
  "schema": "decision_envelope.v1",
  "status": "blocked",
  "summary": "当前请求超出已声明范围。",
  "issues": [
    {
      "code": "UNSUPPORTED_REQUEST_SCOPE",
      "message": "缺少可执行的输入或能力。",
      "field": "request.type"
    }
  ],
  "payload": {}
}
```

issues MUST 是结构化数组，code MUST 稳定。blocked 是合法 Decision 结果，不等于模型调用崩溃；但它会阻止当前路径继续执行副作用。

### 14.4 Envelope 校验

校验顺序：

1. 解析 JSON 对象，拒绝额外包裹层歧义。
2. 校验 schema identity 和 status。
3. 校验 status 对应字段。
4. 校验 payload 业务 schema。
5. 校验 allowed_statuses。
6. resolved 时校验 consume。
7. 生成结构化事件或 Runtime Error Envelope。

解析失败不得从自然语言中猜测 status。修复性 JSON 归一化如果存在，必须确定、有限且记录原始输入摘要。

## 15. Decision Consume

允许 resolved 的 AI decision MUST 声明显式消费：

```json
{
  "output_contract": "decision_envelope.v1",
  "decision_contract": {
    "schema": "decision_envelope.v1",
    "allowed_statuses": ["resolved", "needs_user_input", "blocked"],
    "consume": {
      "mode": "payload_path",
      "path": "payload.plan",
      "as": "approved_plan",
      "required": true,
      "on_missing": "fail_closed"
    }
  }
}
```

运行顺序：

1. 取得 decision output。
2. 解析并校验完整 envelope。
3. 把 envelope 写入节点 output。
4. resolved 时读取 consume.path。
5. 写入 consume.as。
6. 记录 path、as、状态和值摘要。

`needs_user_input` 和 `blocked` 不得产生 consume 投影。`consume.as` 不得覆盖完整 envelope output。

### 15.1 Consume 字段规则

1. `mode` 在本版本 MUST 为 `payload_path`。
2. `path` MUST 为 `payload` 或以 `payload.` 开头。
3. `as` MUST 是合法且明确的 Store key。
4. `as` MUST NOT 等于节点完整 envelope 的 output。
5. `required` 默认 SHOULD 为 true。
6. `on_missing` 合法值为 `fail_closed` 或 `block_decision`。
7. path、as、required 和 on_missing MUST 在运行前可静态读取。
8. 禁止依据节点 output 名、payload 首字段或历史命名习惯隐式生成投影 key。

### 15.2 后续消费规则

后续业务节点 SHOULD 读取 consume.as，例如 `approved_plan`，而不是读取 `planning_decision` 完整 envelope。完整 envelope 只用于审计、状态展示、错误追踪和恢复。

如果多个下游需要不同 payload 分支，作者应使用多个显式 projection/transform 节点或协议允许的结构化 projection 列表，不得让每个执行器自行解释 envelope。

### 15.3 投影审计

投影事件至少记录 decision node、envelope output key、envelope revision、path、as、值 hash、状态和时间。敏感业务值可只记录摘要，但恢复时必须能确定所用 revision。

## 16. Pending Interaction

当 decision、human gate 或 `collect | review` interaction 节点等待用户时，Base MUST：

1. 将 run 设为 `paused_waiting_user`。
2. 保存 pending interaction，状态为 `waiting_user`。
3. 停止后续节点。
4. 暴露结构化提交接口。
5. 提交后将 interaction 设为 `answered` 并按 policy 恢复。

合法 resume policy：

- `resume_same_node`
- `resume_wait`
- `restart_run_with_inputs`

UI 中选择按钮不等于提交。只有 answer API 或等价受控命令在校验 interaction identity、action、payload schema、revision 和幂等键后可以恢复运行。

### 16.1 Interaction 记录

```json
{
  "schema": "cartridgeflow.pending_interaction.v2",
  "interaction_id": "interaction_...",
  "run_id": "run_...",
  "node_id": "review_plan",
  "status": "waiting_user",
  "presentation": {
    "component_id": "review.result",
    "component_runtime": "sandboxed",
    "component_version": "1.0.0",
    "entry_sha256": "...",
    "input_revision": 3
  },
  "allowed_actions": ["approve", "revise", "cancel"],
  "question": {
    "id": "approval",
    "prompt": "是否批准当前方案？",
    "input_schema": {"type": "boolean"},
    "store_key": "plan_approval"
  },
  "resume": {"policy": "resume_wait"},
  "created_at": "...",
  "answered_at": null,
  "answer_revision": 0
}
```

Interaction MUST 持久化到 run-scoped 状态，并能在页面刷新或 Base 重启后读取。

`presentation` 对 decision/human gate MAY 省略；由 interaction 节点创建时 MUST 固定 component identity、runtime、版本或内容 hash、输入 revision 和允许动作。恢复时任一 required 组件文件或 hash 变化都必须阻断旧 interaction，并要求显式迁移或重启，不得把等待中的用户悄悄切换到另一版脚本。

### 16.2 生命周期

```text
waiting_user -> answered | cancelled | expired
```

只有 waiting_user 可以接受首次答案。重复提交必须通过 idempotency key 返回原结果或稳定冲突，不得重复恢复 Run。修改已回答内容必须创建新 answer revision 和明确的回滚/重新审批语义。组件 mount/unmount、iframe reload、浏览器刷新和重复 `ready` 消息都不得创建新的 interaction 或重复提交。

### 16.3 Resume Policy

- `resume_same_node`：将答案写入 store_key，重新执行当前节点。
- `resume_wait`：答案写入声明输出后，恢复同一 `wait_id` 对应的执行计划令牌；客户端不能提供 target。
- `restart_run_with_inputs`：使用原始输入和答案创建新的 Run 语义。

Policy 不得绕过尚未满足的 gate、permission 或 required input。等待身份不存在或不匹配时必须阻断。

### 16.4 Answer Routes

human gate 和 interaction node MUST 把结构化答案写入声明输出。后续行为由执行计划和消费该输出的节点决定。sandbox component 只能提出允许的 action intent；最终答案由 Host control 提交，且不能直接指定目标节点。Host commit 的 `action_id` 不存在、payload schema 不匹配、输入 revision 已失效或审批对象已更新时必须返回稳定冲突并保持 Run 暂停。

## 17. Tool Plan

AI MAY 生成工具计划，但不得自己执行：

```json
{
  "schema": "tool_plan.v1",
  "tool_id": "lookup_documents",
  "params": {"query": "store:approved_plan.query"},
  "expected_output": "document_results",
  "reason": "Retrieve declared context."
}
```

执行前 MUST 校验：

- tool_id 在 allowed_tools 中。
- params 符合 schema。
- effect 与工具 side_effect 匹配。
- resource role 已绑定。
- permission 已满足。
- expected_output 与节点 output 一致。

合法链路：

```text
decision -> consume/tool_plan -> gate -> mcp_execute/remote_call
```

### 17.1 Tool Plan 字段

| 字段 | 要求 |
|---|---|
| `schema` | 固定为 tool_plan.v1 |
| `tool_id` | 必须位于执行节点 allowed_tools |
| `params` | 必须通过 Manifest tool params_schema |
| `expected_output` | 必须匹配执行节点声明 output |
| `reason` | 人类可读审计说明，不参与授权 |
| `idempotency_key` | 可选；不能替代工具 idempotent 声明 |

Tool Plan 是数据，不是可执行代码。不得包含 handler、URL、command、凭据、任意脚本或动态 import。

### 17.2 Binding Mode

执行节点 MAY 使用固定 `tool_binding` 或 `from_tool_plan`。固定绑定必须引用 Manifest tool ID；from_tool_plan 必须从声明 input 读取并完整校验。任何模式都不能扩大 allowed_tools。

### 17.3 验证失败

未知 tool、参数不合法、effect 不匹配、资源未绑定或 permission 缺失时，工具不得启动。失败必须具有稳定 code，并保留被拒绝计划的脱敏摘要。

## 18. 工具调用与副作用

工具 contract MUST 声明：

- capability。
- side_effect。
- idempotent。
- timeout_ms。
- retry_policy。
- params_schema。
- 适用时的 result_schema、deduplication_key 和 compensation。

副作用节点默认失败关闭。`continue_with_report` 或 `skip_with_report` 只有在下游明确接受不完整结果时才合法。

工具返回 `ok=true` 不代表业务门禁通过；validation、asset 或 quality 状态必须使用独立结构化字段。

### 18.1 完整 Tool Contract 示例

```json
{
  "id": "lookup_documents",
  "type": "mcp",
  "server": "document_tools",
  "tool": "search",
  "resource_role": "document_lookup",
  "enabled": true,
  "required": true,
  "contract": {
    "capability": "remote_tool_call",
    "side_effect": "read_only",
    "idempotent": true,
    "timeout_ms": 30000,
    "retry_policy": {
      "max_attempts": 2,
      "initial_delay_seconds": 0.5,
      "max_delay_seconds": 2,
      "total_timeout_seconds": 45
    }
  },
  "params_schema": {
    "type": "object",
    "properties": {"query": {"type": "string"}},
    "required": ["query"],
    "additionalProperties": false
  },
  "result_schema": {
    "type": "object"
  }
}
```

### 18.2 mcp_read

mcp_read 只能调用 side_effect 为 none、read_only 或 environment_probe 的工具。即使工具当前参数看似只读，只要 contract 声明可能写入，就不得由 mcp_read 调用。

### 18.3 mcp_execute

mcp_execute 用于可能产生 Artifact、文件、持久状态或外部副作用的工具。节点必须声明 allowed_tools、tool_binding、permission、failure_policy、audit_log=true 和适用的 replay_policy。

### 18.4 remote_call

remote_call 通过 resource_role 和 Manifest tool ID 调用本机配置的远程资源。节点和 Manifest MUST NOT 保存 URL、key、Authorization、私有 header、供应商默认端口或个人代理设置。

远程上传、轮询、结果解析和供应商 workflow 不属于通用 remote executor；它们应由卡带 DLC 或外部适配包实现，并仍受 Tool Contract 约束。

### 18.5 Failure Policy

| policy | 语义 |
|---|---|
| `fail_closed` | 节点和当前路径失败 |
| `continue_with_report` | 写入结构化失败报告后继续声明路径 |
| `skip_with_report` | 明确跳过并记录不完整结果 |
| `pause_for_user` | 形成可恢复 interaction |

continue/skip 只有在下游 schema 明确接受缺失或失败报告时才合法。副作用是否已经部分发生必须单独记录，不能因 policy=continue 而隐藏。

### 18.6 Tool Call 审计

审计至少记录 call id、run/node、tool identity、resource role、参数 hash、effect、permission decision、attempt、timeout、结果状态、Artifact IDs、错误 identity 和 replay metadata。敏感参数必须脱敏。
