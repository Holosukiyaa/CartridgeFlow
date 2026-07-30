# Flow 创作、执行契约与工程分析架构

> 状态：本文记录 v0.8 的架构决策；当前发布基线已升级到 `CF-FARP@1.0`，新增 MCP/DLC 透明执行语义以 v1.0 正文和 `protocol/catalog/release_manifest.json` 为准。
> 日期：2026-07-28
> 当前规范基线：`CARTRIDGEFLOW-BASE@0.2 + CF-FARP@1.0`；Base 对 v0.6-v1.0 的 partial 支持以 `config/base/BASE_IMPLEMENTATION.json` 为准。
> 范围：记录业务流程、执行契约和工程关系三层边界的架构依据。规范性要求以 `docs/protocol/flow-authoring/CARTRIDGEFLOW_FLOW_AUTHORING_RUNTIME_PROTOCOL_v0.8.md` 为准；本文没有改写 v0.7 快照。

## 1. 一句话结论

Flow 应当把“真正决定怎么运行的声明”和“帮助开发者看懂流程的关系图”彻底分开：

```text
用户与创作 AI 编写：业务流程 + 执行契约
系统自动生成：工程关系 + 诊断报告
运行器只消费：通过校验的业务流程 + 执行契约
```

画布上的数据流、模型依赖和工具依赖不是运行器寻找数据或资源的路线。它们是系统根据节点声明自动生成的只读投影。

但是，“运行器不依赖数据流向线”不等于“运行器不依赖数据关系”。运行器仍然必须依赖明确的 `input_binding`、`output`、`model_role`、`tool_binding`、`action_routes` 和 `failure_policy`。只是这些事实以结构化契约存在，不靠用户或 AI 手动画线表达。

## 2. 为什么需要这份架构

### 2.1 当前系统已经具备的能力

当前项目已经有以下基础：

1. Root Flow 可以声明节点、`next`、`routes` 和顶层 `edges`。
2. 节点可以声明输入、输出、Store/Artifact 引用、模型角色、工具绑定、权限和失败策略。
3. 运行器可以直接解析节点声明，不需要沿画布上的数据虚线查找数据。
4. 工程视图可以根据部分字段推导数据流和资源依赖线。
5. 前后端已经存在若干节点检查和协议检查逻辑。

因此，本方案不是重新发明 Flow，而是把已经存在但分散的能力收敛成清楚、稳定、可强制执行的体系。

### 2.2 当前真正的问题

当前问题不是“没有任何检查”，而是检查和关系推导没有形成统一入口：

- 主拓扑由 Root Flow 表达。
- 数据关系主要由前端扫描 `input_binding`、`source` 和输出字段后推导。
- 工具、模型、失败策略和节点健康检查分散在不同模块。
- 一部分检查用于 UI 提示，一部分用于协议验证，一部分直到运行时才暴露。
- 创作 AI 没有一个统一的完成标准，也没有稳定的机器可读修复闭环。
- `root_flow.edges` 当前会被运行器当作执行后继；如果把视觉数据线或资源依赖线写入其中，可能错误改变执行顺序。

当前流程可以概括为：

```text
AI 或用户编写 Flow
    -> 前端局部猜测工程关系
    -> 多处代码分别检查部分问题
    -> 运行或打包时继续发现遗漏
```

目标流程应当是：

```text
AI 或用户编写业务流程和执行契约
    -> 统一 Analyzer 规范化并生成工程关系
    -> 统一 Validator 输出可修复诊断
    -> 阻断项清零后才允许运行、打包或发布
```

## 3. 新能力位于哪一层

这不是一套替代 CF-FARP 的新运行协议，也不是新的领域协议。它属于“创作与编译层”，位于创作工具和现有运行协议之间：

```text
开发者 / 创作 AI / AI 管家
              |
              v
Flow 创作与分析层
  - Authoring API
  - Normalizer
  - Analyzer
  - Validator
  - Diagnostics
              |
              v
CF-FARP Root Flow 与节点执行契约
              |
              v
CartridgeFlow Runner
```

各层回答的问题不同：

| 层级 | 回答的问题 |
|---|---|
| Base Contract | 宿主提供什么能力，如何隔离、安装、恢复和卸载？ |
| CF-FARP | 卡带交给合规 Base 后，节点、Store、工具、交互和运行状态具有什么公开语义？ |
| Flow 创作与分析层 | 开发者和 AI 如何可靠地产生、检查和修复一个符合 CF-FARP 的 Flow？ |
| 工作台与 AI 管家 | 用户如何理解、编辑和运行这些声明？ |

CF-FARP v0.7 是已发布快照，未被原地改写。本文确认的跨 Base 公开语义已经由 CF-FARP v0.8 正式发布；工作台内部缓存、布局和 UI 投影仍不属于跨 Base 运行协议。

## 4. 三层模型

### 4.1 第一层：业务流程层

业务流程层表达“实际业务怎么走”，包括：

- 有哪些业务节点。
- 从哪里开始，到哪里结束。
- 正常情况下下一个节点是谁。
- 条件成立时进入哪个分支。
- 用户选择某个动作后进入哪个节点。
- 发生明确故障转移时进入哪个恢复节点。

这一层主要由用户和创作 AI 生产。它必须保持接近业务语言，使创作 AI 不需要先理解工程视图的全部视觉规则。

典型来源：

```text
start
  -> collect_sentence
  -> expand_with_ai
  -> show_result
  -> complete
```

真正改变执行顺序的关系属于这一层，必须进入可执行拓扑。

### 4.2 第二层：执行契约层

执行契约层表达“每个节点如何安全、确定地执行”，包括：

- required/optional input。
- output、output schema 和 Store key。
- `input_binding` 与 Artifact 引用。
- 模型角色和 Flow 内模型绑定。
- 工具、MCP、远程资源角色和 allowlist。
- permission、effect、timeout、audit 和 replay policy。
- `action_routes`、结构化 decision consume 和条件表达式。
- `failure_policy` 与可选故障转移声明。

这一层也由创作 AI 或开发者填写，但应通过结构化表单和专用 API 操作，不能要求 AI 修改任意 JSON 文本或手动画依赖线。

示例：

```json
{
  "id": "expand_with_ai",
  "type": "process",
  "kind": "decision",
  "executor": "llm",
  "input_binding": {
    "sentence": "store:user_sentence"
  },
  "output": "expanded_sentence",
  "model_role": "copywriter",
  "failure_policy": "fail_closed",
  "next": "show_result"
}
```

这个节点已经声明数据来源、产出、模型需求、失败方式和正常后继。运行器不需要一根额外的数据线才能理解它。

### 4.3 第三层：工程关系与诊断层

工程关系层表达“为了让人和 AI 看懂、检查和维护流程而生成的信息”，包括：

- 数据从哪个节点的哪个输出进入哪个节点的哪个输入。
- 节点依赖哪个模型角色、工具、MCP、远程资源或 Artifact。
- 哪条控制边属于主流程、条件分支、用户动作或故障转移。
- 哪些输入没有生产者。
- 哪些输出没有消费者。
- 哪些资源未绑定、权限不足或不属于当前 Flow。
- 哪些路径存在副作用、重放风险或缺少失败策略。
- 哪些节点不可达、没有出口或形成未受控循环。

这一层必须由系统根据前两层自动生成。用户和创作 AI 可以查看、筛选、定位和要求修复，但不得直接编辑生成结果。

如果用户想改变一条数据关系，应修改第二层的 `input_binding`；如果想改变真实分支，应修改第一层的 route。禁止把拖动工程关系线作为修改源事实的隐式方式。

## 5. 唯一事实来源

### 5.1 必须持久化的事实

以下内容属于卡带源数据，必须持久化：

- 节点及稳定 node id。
- `next`、结构化 routes 和真正影响执行的控制边。
- 输入输出契约与数据引用。
- 模型角色、工具角色和 Flow 级资源绑定身份。
- 权限、副作用、失败、审计和重放策略。
- 交互组件与具名动作路由。

### 5.2 不应作为第二份事实持久化的内容

以下内容默认不写回 Root Flow：

- 根据 `input_binding` 推导的数据流线。
- 根据工具或模型绑定推导的资源依赖线。
- 节点健康颜色和“可运行/待配置/阻断”标签。
- Analyzer 生成的说明文案。
- 工程视图的关系标签和视觉样式。
- 可由源声明重新计算的诊断结果。

这些内容可以缓存以提升大型 Flow 的显示性能，但缓存必须包含源文档摘要并可随时丢弃重建。缓存不得成为 Runner 的输入，也不得参与卡带业务语义。

### 5.3 控制边与工程边必须隔离

建议统一使用以下概念：

```text
Executable Control Edge
  真正改变调度和执行顺序，由 Runner 消费。

Derived Engineering Relation
  根据声明生成，只用于工作台、AI 管家、诊断和审计。
```

禁止把 `data`、`resource_dependency` 等工程关系直接保存到当前 `root_flow.edges`，除非未来协议明确拆分字段且 Runner 对类型执行严格过滤。

## 6. 关系由谁生产

关系不是由一个主体全部生产，而是按职责分工：

| 关系或声明 | 原始事实生产者 | 最终关系生产者 |
|---|---|---|
| 主流程 | 用户或创作 AI | 拓扑规范化器 |
| 条件分支 | 用户或创作 AI 声明条件与目标 | 拓扑规范化器 |
| 用户动作分支 | 组件契约与创作 AI 声明 `action_routes` | 拓扑规范化器 |
| 数据流 | 创作 AI 声明输入、输出和绑定 | Dataflow Analyzer |
| 模型依赖 | 创作 AI 声明模型角色和绑定 | Resource Analyzer |
| 工具/MCP 依赖 | 创作 AI 声明工具身份、角色和 allowlist | Resource Analyzer |
| 普通失败策略 | 创作 AI 选择策略 | Policy Analyzer |
| 故障转移 | 用户或创作 AI 声明失败目标 | Topology/Policy Analyzer |
| 问题与修复建议 | 无需作者声明 | Validator 与 Diagnostic Engine |

创作 AI 负责表达意图和契约，确定性分析器负责生成关系。分析器不得反过来凭自然语言猜测并静默修改运行事实。

## 7. 统一 Flow Analyzer

### 7.1 定位

需要新增一个统一的 `Flow Analyzer/Compiler`。它不是 Runner，也不执行模型、工具或业务代码。它只读取静态声明，输出规范化图、工程关系和诊断报告。

所有入口必须调用同一套核心分析逻辑：

- 工作台保存前检查。
- AI 管家“检查流程”。
- 点击运行前预检。
- 打包前检查。
- 官方仓库审核。
- conformance 测试。

前端可以消费分析结果，但不得维护一套与后端不一致的独立真相。

### 7.2 输入

Analyzer 至少读取：

- Manifest。
- Root Flow。
- 节点 schema、prompt、组件和资产 registry。
- Flow 内模型角色与绑定身份。
- Flow 内工具、MCP 和资源角色绑定身份。
- Base capability 与协议支持声明。
- 目标运行级别：draft、dev、preview 或 production。

Analyzer 不读取 API Key 明文，也不通过真实调用验证业务效果。连接健康检查和静态契约分析是两个不同阶段。

### 7.3 输出

建议统一输出：

```json
{
  "analysis_version": "flow-analysis.v1",
  "source_digest": "sha256:...",
  "protocol": "CF-FARP@0.7",
  "normalized_topology": {
    "start": "start",
    "control_edges": []
  },
  "relations": [],
  "findings": [],
  "summary": {
    "blockers": 0,
    "warnings": 1,
    "runnable": true,
    "packagable": false,
    "publishable": false
  }
}
```

`normalized_topology` 是对 `next`、routes 和合法控制 edges 的规范化结果。`relations` 是只读工程投影。`findings` 是机器可读诊断。

## 8. 分阶段分析规则

Analyzer 应按固定阶段工作。前一阶段出现结构性 blocker 时，后续阶段可以继续给出安全诊断，但不得假装得到完整可信的结果。

### 8.1 协议与结构检测

检查：

- 协议身份和版本是否已知、是否被当前 Base 支持。
- Manifest、Root Flow 和节点字段类型是否合法。
- 必填字段是否存在。
- 稳定 ID 是否唯一。
- 引用对象是否存在。
- schema 是否可解析。

### 8.2 拓扑规范化

将 `next`、结构化 routes 和可执行 control edges 规范化为同一原子控制图，并检查：

- start 是否存在。
- terminal 是否仍然拥有普通后继。
- 是否存在悬空目标。
- 是否存在不可达节点。
- 是否存在无出口业务节点。
- 是否存在冲突条件或重复边。
- 循环是否具有退出条件和最大迭代限制。

### 8.3 数据契约分析

Dataflow Analyzer 根据声明建立生产者和消费者索引：

```text
生产者索引：Store key / Artifact id -> source node + output contract
消费者索引：target node + input field -> reference + required/optional
```

检查：

- required input 是否有合法来源。
- 引用路径是否由上游 output schema 提供。
- 类型和 schema 是否兼容。
- 数据生产者是否在消费者可能执行的控制路径之前。
- 分支汇合后需要的数据是否在所有可达分支上都存在。
- 是否存在未使用的重要输出或覆盖冲突。

只有明确引用和契约匹配才能生成确定性数据关系。字段名相似只能产生建议，不得自动成为可运行绑定。

### 8.4 资源依赖分析

Resource Analyzer 分别分析：

- 模型角色与 Flow 级模型连接。
- 工具身份、工具角色和 Flow allowlist。
- MCP 工具与当前 Flow 的显式加入状态。
- 远程资源角色与本机连接。
- Cartridge DLC 能力与 Base capability。
- Artifact、组件和包资产引用。

检查：

- 资源是否在 Manifest 或 Flow 中声明。
- 当前节点是否被允许使用该资源。
- 资源是否已经绑定，但不读取或泄漏密钥。
- 工具 effect 与节点声明是否一致。
- 当前 Base 是否支持所需 capability。

### 8.5 分支与条件分析

条件分支不能由数据线替代。Analyzer 必须检查：

- 每个 route 是否有稳定条件或具名 action。
- route target 是否存在且可达。
- 同一条件是否指向多个目标。
- 是否需要 default route。
- Decision Envelope 是否通过显式 consume 投影后参与条件。
- UI 组件 action 是否是 `action_routes` 的合法子集。

只存在一个无条件后继时，工程视图可以显示为一根普通主流程线；存在多个真实目标时，必须保留可解释的分支关系。

### 8.6 失败与副作用分析

失败处理分为两种：

1. 节点策略：失败关闭、带报告继续、带报告跳过、重试等，不需要单独画路线。
2. 故障转移：失败后进入指定恢复节点，属于真实控制拓扑，必须有明确目标和条件语义。

Analyzer 必须检查：

- 有副作用节点是否声明 permission、failure policy、audit 和 replay policy。
- retry 是否符合幂等性约束。
- 失败继续后，下游 required input 是否仍然可用。
- 恢复节点是否可达且不会形成无控制循环。
- 故障转移与普通成功路线是否可区分。

### 8.7 可运行性与交付等级

同一 Flow 在不同阶段具有不同门槛：

| 阶段 | blocker 行为 |
|---|---|
| draft 保存 | 允许保存，但必须显示问题和未完成状态 |
| dev 运行 | 运行路径上的 blocker 必须阻断；允许明确标记的 mock/fallback |
| preview | 全部已知限制必须可见，外部资源必须通过要求的预检 |
| production | 不得依赖编辑器临时修复，不得存在协议 blocker |
| package | 必须生成与源摘要绑定的分析报告 |
| publish | 必须通过协议、权限、安全、资产和审核策略 |

## 9. 工程关系的标准结构

建议 Analyzer 使用统一关系结构，而不是让前端根据字段临时拼接：

```json
{
  "id": "relation:collect_sentence:user_sentence:expand_with_ai:sentence",
  "kind": "data",
  "from": {
    "type": "node_output",
    "node_id": "collect_sentence",
    "field": "user_sentence"
  },
  "to": {
    "type": "node_input",
    "node_id": "expand_with_ai",
    "field": "sentence"
  },
  "derived_from": [
    "states.collect_sentence.output",
    "states.expand_with_ai.input_binding.sentence"
  ],
  "confidence": "deterministic",
  "runtime_effect": false
}
```

建议基础 `kind`：

- `control`
- `branch`
- `failure_route`
- `data`
- `model_dependency`
- `tool_dependency`
- `mcp_dependency`
- `resource_dependency`
- `artifact_dependency`

其中 `control`、`branch` 和 `failure_route` 是可执行拓扑的投影；其他关系默认 `runtime_effect=false`。

## 10. 诊断与自动修复契约

### 10.1 诊断必须机器可读

仅返回“请求不符合规范”或“节点执行失败”无法帮助用户和 AI 修复。每个 finding 至少包含：

```json
{
  "severity": "blocker",
  "code": "INPUT_SOURCE_MISSING",
  "node_id": "expand_with_ai",
  "path": "states.expand_with_ai.input_binding.sentence",
  "message": "AI 扩写需要 sentence，但尚未绑定数据来源。",
  "expected": "store or artifact reference",
  "suggested_sources": [
    "store:user_sentence"
  ],
  "autofix": {
    "safe": true,
    "operation": "set_input_binding",
    "arguments": {
      "field": "sentence",
      "reference": "store:user_sentence"
    }
  }
}
```

### 10.2 自动修复分级

| 等级 | 含义 | 行为 |
|---|---|---|
| safe | 唯一、确定、可逆，不改变业务意图 | AI 可在委托权限内自动应用 |
| confirm | 有多个合理选择或会改变业务路径 | 必须让用户确认 |
| manual | 涉及密钥、权限、收费资源、外部副作用或缺少信息 | 只解释，不自动执行 |

Analyzer 只提出修复；Authoring API 负责应用变更。分析器不得一边扫描一边静默改写 Flow。

## 11. 给创作 AI 的三个入口

创作 AI 不应直接面对一个万能的“修改 JSON”工具。应当提供三个职责清楚的入口。

### 11.1 业务流程入口

负责：

- 创建、删除和重命名节点。
- 设置职责、kind 和业务说明。
- 设置主流程、条件分支、用户动作分支和故障转移。
- 调整业务拓扑。

示例操作：

```text
create_node
set_next
set_route
set_failure_route
remove_control_edge
```

### 11.2 执行契约入口

负责：

- 声明输入输出和 schema。
- 设置 `input_binding`。
- 绑定模型角色、工具、MCP 和远程资源角色。
- 配置权限、副作用、失败、审计和重放策略。
- 配置交互组件和 action contract。

示例操作：

```text
set_input_contract
set_output_contract
set_input_binding
bind_model_role
allow_flow_tool
bind_node_tool
set_failure_policy
```

### 11.3 分析、解释与修复入口

负责：

- 运行全量或局部分析。
- 查询节点、选区或路径的工程关系。
- 返回 blockers、warnings 和建议。
- 解释为什么某节点不可运行。
- 生成修复计划并调用前两个入口应用修复。

示例操作：

```text
analyze_flow
analyze_selection
explain_relation
list_blockers
propose_fixes
verify_after_changes
```

这个入口不提供“直接编辑工程关系线”。工程关系只能通过修改源声明后重新生成。

## 12. 创作 AI 的标准闭环

创作 AI 的默认工作流应固化为：

```text
1. 理解用户业务目标
2. 生成最小业务流程
3. 为每个节点补齐执行契约
4. 调用 Analyzer
5. 先修复 blocker，再处理 warning
6. 重新运行 Analyzer
7. 向用户展示业务流程和关键工程关系
8. 只有检查通过后才允许运行或打包
```

AI 不需要一次性生成完美 Flow。系统应鼓励“生成 -> 检查 -> 定点修复 -> 再检查”的确定性闭环。

为减少上下文和工具调用，Analyzer 应支持增量分析：当只修改一个节点时，只重算该节点、直接上下游、相关资源和受影响路径，最终仍输出与全量分析一致的结果。

## 13. 工作台呈现原则

### 13.1 引导视图

引导视图优先展示业务流程：

- 普通顺序只显示一根主流程线。
- 真实多出口显示大白话分支标签。
- 数据和资源关系默认隐藏。
- 节点显示职责、输入、输出和“提示”。
- blocker 用人话解释，不暴露无必要的协议字段。

### 13.2 工程视图

工程视图消费 Analyzer 结果：

- 主流程、条件分支和故障转移可以独立筛选。
- 数据流、模型依赖、工具依赖和 Artifact 依赖可以叠加显示。
- 工程关系默认只读。
- 点击关系时展示 `derived_from`，说明它由哪些源字段推导。
- 修改源字段后，只更新受影响关系，避免大型 Flow 全图重算。

### 13.3 AI 管家

AI 管家的拖拽指针和框选工具应把选择范围交给 Analyzer：

- “解释这里”读取选中节点、控制路径、数据关系、资源关系和 findings。
- “修改这里”先生成结构化变更计划，再调用业务流程或执行契约入口。
- AI 管家不得根据画面像素猜测关系，也不得直接修改派生线。

## 14. 当前实现与目标架构的对应关系

### 14.1 已有可复用部分

- `src/frontend/src/pages/flow-workbench/engineeringNode.ts` 中的 `buildEngineeringDataRelations()` 已能从输出、`input_binding` 和部分 source 字段推导工程关系，可作为 Dataflow Analyzer 的原型和前端兼容层。
- `src/frontend/src/pages/flow-workbench/flowNodeView.ts` 已有按节点 kind 生成健康问题的逻辑，可迁移为统一 finding 的展示适配器。
- `src/core/cartridge/assets.py` 已有 v0.7 组件、action route 和 input binding 检查，可并入协议验证阶段。
- `src/core/lab/graph.py` 已经能构造节点和部分控制边，可复用为规范化拓扑输入。
- `src/core/lab/node_executor.py` 已经按绑定读取 Store/Artifact 和解析 Flow 工具资源，证明运行器不需要视觉工程线。

### 14.2 必须修正的边界

1. 当前工程关系主要在前端生成，后端运行前检查和 AI 管家无法稳定复用同一结果。
2. 当前关系类型判定较粗，例如目标节点使用工具时，进入该节点的数据关系可能整体被标为 dependency；未来应分别生成数据关系和工具依赖关系。
3. 当前部分关系依靠字段名匹配。目标实现必须优先读取显式引用和 schema；模糊语义匹配只能给建议。
4. 当前检查分散，错误 code、严重级别和修复信息不统一。
5. 当前 `RootFlowEngine.next_states()` 会读取所有顶层 `root_flow.edges`，没有按工程关系类型隔离。工程关系不得写入该数组；后续 Runner 应只消费经过规范化的可执行控制拓扑。
6. Analyzer 必须成为共享核心，前端只负责渲染，不能继续成为关系语义的唯一拥有者。

## 15. 强制检测脚本

项目应提供一个稳定、可在本地和 CI 中运行的强制检测入口。建议形式：

```text
scripts/flow_analyze.py <cartridge-or-flow-path> --target dev|preview|production|package|publish --format json
```

要求：

1. 默认只读，不修改用户 Flow。
2. JSON 输出稳定，便于工作台和创作 AI 调用。
3. 人类输出使用大白话，并保留稳定 code 和 node id。
4. 存在目标级别 blocker 时返回非零退出码。
5. 支持只分析一个 node、selection 或受影响路径。
6. 输出包含源文件 hash，防止旧报告被用于新 Flow。
7. 不执行卡带业务代码，不调用收费模型和外部副作用工具。
8. 连接探针必须显式开启，并与静态分析结果分开记录。

强制检测点：

```text
保存草稿：允许 blocker，但更新健康状态
点击运行：阻断当前运行路径上的 blocker
打包卡带：阻断全部 package blocker
提交官方仓库：要求 publish 分析报告和审核证据
```

## 16. 协议落地结果

### 16.1 已进入 CF-FARP v0.8 的语义

以下影响跨 Base 可移植行为的内容已经在 v0.8 正式规定：

- 可执行控制边与派生工程关系的边界。
- Root Flow 中只有声明为控制拓扑的边才能影响 Runner 调度。
- 数据链来源、资源引用、分支和失败路线的静态可分析要求。
- 标准 finding identity、严重级别和最低诊断字段。
- 运行、打包和认证前的最低静态分析门槛。
- Analyzer 报告与源摘要、协议版本和 Base capability 的绑定方式。

### 16.2 不必进入运行协议的实现细节

以下内容可以由 Base 自主实现：

- 工程线颜色、虚实、动画和筛选控件。
- 关系缓存结构。
- 前端布局和节点卡样式。
- AI 管家的对话文案。
- 增量计算使用的索引和 Worker 技术。

### 16.3 版本治理

CF-FARP v0.7 保持只读，上述新语义通过 v0.8 完整快照发布。后续实现必须：

1. 以 v0.8 正文和版本化 registry 为唯一规范来源。
2. 实现 Analyzer、Runner 过滤、失败路径和测试证据。
3. 完成 conformance 后再由 Base 声明支持 v0.8。

在 Base 声明支持前，本文继续约束 Lite 的实现顺序；生成的工程关系不能冒充当前 Base 已具备 v0.8 conformance。

## 17. 分阶段实施计划

### 阶段 A：固定边界

- 定义 `control_edges` 与 `derived_relations` 内部类型。
- 明确 `root_flow.edges` 当前只允许表达可执行拓扑。
- 禁止前端把数据/依赖线写回 Root Flow。
- 为现有 Flow 增加混合边审计。

### 阶段 B：统一分析核心

- 把拓扑、数据、资源、分支和失败检查收敛到后端 Analyzer。
- 统一 finding schema、code 和严重级别。
- 保留前端关系推导作为过渡兼容，并增加一致性测试。

### 阶段 C：创作 AI 入口

- 提供业务流程、执行契约、分析修复三组结构化工具。
- AI 管家改为消费 Analyzer 的 selection report。
- safe autofix 通过 Authoring API 应用并自动复检。

### 阶段 D：强制门禁

- 运行前接入 dev target 检测。
- 打包和发布接入 package/publish target。
- 输出带 source digest 的报告。
- 禁止过期报告和手工勾选替代机器证据。

### 阶段 E：协议发布（已完成）

- v0.8 正文、registry 和 capability/profile 已发布。
- conformance 规范测试已建立；运行实现与迁移器仍按阶段 A-D 推进。
- Base 完成实现和失败路径后再声明支持。

## 18. 验收标准

### 18.1 正确性

- 普通顺序 Flow 只需要主控制线即可运行。
- 删除工程视图数据线缓存不影响运行结果。
- 修改 `input_binding` 后，数据关系自动更新。
- 未绑定模型、工具或 MCP 时，在运行前产生稳定 blocker。
- 工具未加入当前 Flow 时，即使 Base 拥有该工具也不得通过检查或执行。
- 条件分支缺少目标、条件冲突或 default 缺失时产生明确 finding。
- 普通失败策略不生成虚假控制边；故障转移生成真实可执行路线。
- 工程关系永远不能被 Runner 当作后继节点执行。

### 18.2 AI 创作体验

- AI 创建最小流程时无需调用“绘制数据线”或“绘制工具依赖线”。
- Analyzer 能把问题定位到稳定 node id 和字段路径。
- 每个 blocker 至少提供人话说明和下一步动作。
- 唯一确定的修复可以一次完成并通过复检。
- 多个合理来源或资源时，AI 必须向用户展示选择而不是擅自猜测。

### 18.3 工作台体验

- 引导视图默认不显示工程关系噪声。
- 工程视图可以独立筛选数据、模型、工具、分支和失败关系。
- 关系详情能追溯到源声明。
- 大型 Flow 修改单节点时不触发无必要的全画布重建。

## 19. 不可破坏的设计约束

1. 视觉线不是运行事实，结构化声明才是运行事实。
2. 工程关系只有一个来源：Analyzer 对当前源声明的推导。
3. Runner 不得消费 `runtime_effect=false` 的关系。
4. Analyzer 不执行业务代码，不产生外部副作用。
5. 模糊语义匹配不得静默变成可运行绑定。
6. AI 不直接编辑派生关系，只修改业务流程或执行契约。
7. blockers 可以存在于草稿，但不得被 `runnable=true`、UI 绿色状态或用户手工勾选覆盖。
8. 密钥、私有 URL 和本机连接细节不进入卡带、分析报告或 AI 上下文。
9. 已发布协议不原地改写；公开语义变化必须发布新版本。
10. 工作台、AI 管家、运行前检查、打包和审核必须消费同一套分析语义。

## 20. 完整示例

### 20.1 作者写入的事实

```json
{
  "start": "start",
  "states": {
    "start": {
      "type": "system",
      "kind": "start",
      "next": "collect_sentence"
    },
    "collect_sentence": {
      "type": "process",
      "kind": "interaction",
      "interaction_mode": "collect",
      "component_ref": "sentence_form",
      "output": "user_sentence",
      "action_routes": {
        "submit": "expand_with_ai"
      }
    },
    "expand_with_ai": {
      "type": "process",
      "kind": "decision",
      "executor": "llm",
      "input_binding": {
        "sentence": "store:user_sentence"
      },
      "output": "expanded_sentence",
      "model_role": "copywriter",
      "failure_policy": "fail_closed",
      "next": "show_result"
    },
    "show_result": {
      "type": "process",
      "kind": "interaction",
      "interaction_mode": "display",
      "component_ref": "expanded_result",
      "input_binding": {
        "content": "store:expanded_sentence"
      },
      "next": "complete"
    },
    "complete": {
      "type": "terminal",
      "kind": "complete"
    }
  }
}
```

### 20.2 Analyzer 生成的工程关系

```text
控制：start -> collect_sentence
动作分支：collect_sentence --submit--> expand_with_ai
控制：expand_with_ai -> show_result
控制：show_result -> complete

数据：collect_sentence.user_sentence -> expand_with_ai.sentence
数据：expand_with_ai.expanded_sentence -> show_result.content
模型依赖：expand_with_ai -> model_role:copywriter
失败策略：expand_with_ai = fail_closed
```

### 20.3 如果模型没有绑定

Analyzer 返回：

```text
[blocker] MODEL_ROLE_UNBOUND
节点“AI 扩写”需要 copywriter 模型角色，但当前 Flow 尚未为它绑定模型连接。
```

引导视图只需要告诉用户“AI 扩写还没有选择模型”；工程视图可以显示该节点到 `model_role:copywriter` 的未满足依赖；Runner 在真正调用模型之前就必须阻断。

## 21. 最终决策

CartridgeFlow Lite 后续 Flow 创作遵循以下固定分工：

```text
业务流程层：描述业务怎么走。
执行契约层：描述节点怎么安全、确定地执行。
工程关系层：由系统自动解释前两层，并发现问题。
```

创作 AI 不再负责维护视觉工程线。它只需要使用结构化入口完成业务拓扑和执行契约，再通过统一 Analyzer 反复检查和修复。

这项拆分的价值不只是让画布更干净。它建立了唯一事实来源，减少 AI 工具调用和上下文负担，使运行前失败更早、更明确，也为卡带打包审核、跨 Base 兼容和后续协议认证提供统一机器证据。
