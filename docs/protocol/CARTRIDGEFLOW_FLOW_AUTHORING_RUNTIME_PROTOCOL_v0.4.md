# CartridgeFlow Flow Authoring Runtime Protocol v0.4

协议编号：`CF-FARP-0.4`

协议状态：active

发布状态：完整正文

关系：本协议完整替代 `CF-FARP-0.3`，并吸收显式决策消费契约的规则。本协议不再是 v0.3 的增量补丁。实现本协议时不得要求读者回看 v0.1、v0.2 或 v0.3 才能理解本协议正文。

---

## 目录

1. [协议定位](#1-协议定位)
2. [设计目标](#2-设计目标)
3. [规范关键词](#3-规范关键词)
4. [版本治理](#4-版本治理)
5. [实体定义](#5-实体定义)
6. [协议与基座分离](#6-协议与基座分离)
7. [卡带包结构](#7-卡带包结构)
8. [Manifest 契约](#8-manifest-契约)
9. [Runtime Contract](#9-runtime-contract)
10. [Delivery Readiness](#10-delivery-readiness)
11. [Root Flow 结构](#11-root-flow-结构)
12. [节点通用规则](#12-节点通用规则)
13. [节点统一模型](#13-节点统一模型)
14. [用户层显示规则](#14-用户层显示规则)
15. [协议层字段](#15-协议层字段)
16. [Kind 规则](#16-kind-规则)
17. [Executor 规则](#17-executor-规则)
18. [Effect 规则](#18-effect-规则)
19. [输入类处理节点](#19-输入类处理节点)
20. [传递、检索与转换节点](#20-传递检索与转换节点)
21. [AI 决策节点](#21-ai-决策节点)
22. [decision_envelope.v1 契约](#22-decision_envelopev1-契约)
23. [decision_contract.consume](#23-decision_contractconsume)
24. [消费投影运行语义](#24-消费投影运行语义)
25. [后续节点消费规则](#25-后续节点消费规则)
26. [交互式暂停与恢复](#26-交互式暂停与恢复)
27. [LLM Provider 与测试模式](#27-llm-provider-与测试模式)
28. [决策与工具计划](#28-决策与工具计划)
29. [MCP、Remote 与工具节点](#29-mcpremote-与工具节点)
30. [数据链与 Store](#30-数据链与-store)
31. [tool_plan.v1 契约](#31-tool_planv1-契约)
32. [Artifact 与 Delivery](#32-artifact-与-delivery)
33. [错误、失败与回退](#33-错误失败与回退)
34. [测试台与探针](#34-测试台与探针)
35. [兼容性报告](#35-兼容性报告)
36. [认证要求](#36-认证要求)
37. [能力声明](#37-能力声明)
38. [迁移规则](#38-迁移规则)
39. [示例](#39-示例)
40. [禁止事项](#40-禁止事项)

---

## 1. 协议定位

`CF-FARP-0.4` 定义 CartridgeFlow 卡带的流程搭建、流程运行、节点语义、输入输出、AI 决策、显式消费、工具调用、用户交互、测试台、探针、产物交付、兼容性检查和认证要求。

本协议面向两类基座：

- 开发基座：支持搭建、调试、探针、诊断、mock、真实 LLM 测试、协议认证和流程编辑。
- 生产基座：不一定支持设计台或测试台，但必须能解释并运行其声明支持的协议能力。

本协议的核心定位是：

```text
可认证的流程搭建与运行协议，包含交互式 AI 决策、显式消费投影、工具副作用边界和可移植认证规则。
```

本协议允许：

- 多次输入。
- 运行中向用户追问。
- AI 决策节点输出结构化业务结果。
- 后续节点通过显式消费契约读取 AI 结果。
- MCP 工具独立存在，或由 AI 通过结构化计划间接驱动。
- 测试台使用 mock、offline fallback 或 live LLM 检测同一决策节点。
- 生产基座只实现运行协议，不携带开发台。

本协议禁止：

- AI 决策节点直接执行工具副作用。
- 用自然语言散文替代结构化决策包。
- 通过隐式命名规则推断后续消费 key。
- 等待用户输入时继续执行后续副作用节点。
- 把 mock 决策伪装成真实 LLM 决策。
- 基座声明支持协议但不实现其必需能力。

## 2. 设计目标

本协议必须满足以下目标：

1. 单个卡带不得反向污染协议。
2. 协议必须可完整阅读，不依赖历史版本。
3. 用户可理解为“输入、资料处理、AI 决策、执行、确认、交付”的流程。
4. 协议层必须保留副作用边界。
5. AI 决策必须可校验、可记录、可复现、可模拟。
6. AI 决策节点必须能表达三类状态：已解决、需要用户补充、阻断。
7. AI 决策节点必须能表达结构化业务结果，例如判断、计划、素材规格、执行建议或工具计划。
8. 后续节点必须通过显式 `decision_contract.consume` 消费 AI 结果。
9. 运行中用户输入不得与唯一入料口强绑定。
10. MCP 不强制绑定 AI，也不得被 AI 无限调用。
11. 生产基座只要支持协议能力，即可运行同协议卡带。
12. 认证标签只能由兼容性和协议检查通过后添加。

## 3. 规范关键词

本文使用以下关键词：

- MUST：必须。
- MUST NOT：不得。
- SHOULD：应当。
- SHOULD NOT：不应当。
- MAY：可以。

当中文描述与 JSON 示例存在差异时，以中文规范语义为准，JSON 示例只作为合法结构样例。

## 4. 版本治理

本协议标识为：

```text
CF-FARP@0.4
```

本协议认证标签为：

```text
cf-farp-0-4-certified
```

协议版本治理规则：

1. `CF-FARP@0.4` 是当前完整协议正文。
2. v0.1、v0.2、v0.3 作为历史快照保留。
3. 历史协议文件不得被 v0.4 反向改写。
4. 已按旧协议认证的卡带可继续按旧协议运行。
5. 新卡带应优先声明 `CF-FARP@0.4`。
6. 认证报告通过前，不得手动添加认证标签。
7. 未来破坏性调整必须形成新协议版本。

## 5. 实体定义

### 5.1 Protocol

Protocol 定义卡带可移植语义。协议不绑定具体前端、后端、模型供应商或 MCP 服务实现。

### 5.2 Base

Base 是协议的具体实现。基座必须声明支持的协议版本、profile、capability 和 tool pack。

### 5.3 Cartridge

Cartridge 是可分发的流程包。卡带至少包含：

- `manifest.json`
- `root.flow.json`

### 5.4 Manifest

Manifest 是卡带对外声明文件，负责声明身份、输入输出、运行时、权限、工具、协议、能力和交付方式。

### 5.5 Root Flow

Root Flow 是卡带的流程图定义，负责声明节点、边、起点、协议版本和节点执行语义。

### 5.6 Node

Node 是流程图中的执行单元。业务节点必须使用统一 process 模型。

### 5.7 Store

Store 是单次运行内的数据上下文。节点通过显式 input/output key 读写 Store。

### 5.8 Tool

Tool 是具备明确输入、输出和副作用声明的能力。工具可来自内置工具、MCP、Remote 服务或插件。

### 5.9 MCP

MCP 是工具能力的一种提供方式，不等同于 AI。MCP 可被确定性节点调用，也可被 AI 通过结构化计划间接驱动。

### 5.10 LLM Provider

LLM Provider 是 AI 决策节点调用模型的适配层。协议不绑定具体模型、厂商、API wire format 或密钥管理方式。

### 5.11 Decision Envelope

Decision Envelope 是 AI 决策节点的标准结构化输出。自然语言只能作为 envelope 内的说明字段，不得替代 envelope。

### 5.12 Decision Consume Projection

Decision Consume Projection 是从 Decision Envelope 中按显式路径取出的业务值，并写入独立 Store key，供后续节点消费。

### 5.13 Pending Interaction

Pending Interaction 是流程暂停等待用户补充输入时保存的交互请求。

### 5.14 Artifact

Artifact 是运行产物，例如 JSON 报告、HTML 预览、图片、视频、音频、文本或压缩包。

## 6. 协议与基座分离

协议不得绑定具体基座实现。

基座可以支持协议的一部分，但必须如实声明：

```json
{
  "id": "CF-FARP",
  "version": "0.4",
  "status": "partial"
}
```

基座声明支持 `CF-FARP@0.4` 时，必须同时声明：

- 支持的 profiles。
- 支持的 capabilities。
- 支持的 tool_packs。
- conformance 状态。

如果基座未声明支持 `CF-FARP@0.4`，不得运行要求 v0.4 能力的通用卡带，除非进入开发兼容模式并明确标记不可认证。

支持同一协议版本和同一能力集合的不同基座，应能运行共同支持范围内的同一卡带。

## 7. 卡带包结构

推荐结构：

```text
cartridge/
  manifest.json
  root.flow.json
  assets/
  prompts/
  schemas/
  tests/
```

卡带不得依赖包外未声明资源。

卡带可以引用外部服务，但必须通过 manifest 声明依赖、权限、工具和失败策略。

卡带内生成的运行产物应写入 run-scoped 输出目录，除非 manifest 明确声明允许写入持久状态。

## 8. Manifest 契约

manifest 必须声明：

```json
{
  "schema_version": "1.0",
  "id": "example.cartridge",
  "name": "Example Cartridge",
  "version": "1.0.0",
  "kind": "runtime_cartridge",
  "root_flow": {
    "entry": "root.flow.json",
    "mode": "lifecycle",
    "required": true
  },
  "runtime": {
    "type": "lab",
    "adapter": "builtin:lab"
  },
  "base_contract": {
    "id": "CF-FARP",
    "version": "0.4"
  },
  "runtime_contract": {
    "protocol": "CF-FARP",
    "protocol_version": "0.4"
  },
  "delivery_readiness": {
    "level": "dev",
    "runnable": true
  }
}
```

manifest 应当声明：

- `publisher`
- `branding`
- `workspace`
- `environment`
- `permissions`
- `dependencies`
- `mcp_tools`
- `inputs`
- `outputs`
- `artifacts`
- `delivery`
- `protocol_certification`

manifest 的 `id` 必须稳定。版本升级不得通过修改 `id` 逃避兼容性约束。

## 9. Runtime Contract

`runtime_contract` 必须声明协议、profile、capability 和工具需求。

示例：

```json
{
  "protocol": "CF-FARP",
  "protocol_version": "0.4",
  "required_profiles": [
    "runtime_core",
    "dynamic_decision_runtime",
    "interactive_decision_runtime"
  ],
  "recommended_profiles": [
    "testbench_core",
    "dev_authoring"
  ],
  "required_capabilities": [
    "root_flow_execution",
    "unified_process_node",
    "decision_envelope_v1",
    "decision_envelope_validate",
    "decision_consume_contract",
    "decision_consume_projection"
  ],
  "optional_capabilities": [
    "artifact_preview",
    "probe_run"
  ],
  "required_tools": [],
  "optional_tools": []
}
```

规则：

1. `protocol` 必须为 `CF-FARP`。
2. `protocol_version` 必须为 `0.4`。
3. `base_contract` 必须与 `runtime_contract` 匹配。
4. `required_capabilities` 缺失时必须阻断认证。
5. `optional_capabilities` 缺失时只能形成信息或警告，不得阻断运行，除非卡带实际运行路径依赖该能力。
6. `required_tools` 必须能在 manifest 的 `mcp_tools` 中找到声明。

## 10. Delivery Readiness

`delivery_readiness` 表示卡带交付成熟度。

合法 level：

- `dev`
- `preview`
- `production`

示例：

```json
{
  "level": "dev",
  "runnable": true,
  "certification_target": "CF-FARP@0.4",
  "notes": "Development cartridge; outputs are run scoped."
}
```

规则：

1. 缺失 `delivery_readiness` 时不得认证。
2. `production` 级卡带必须避免默认修改持久状态。
3. 如果流程写入持久状态，必须声明权限、策略和回滚或跳过行为。
4. 交付结果必须能从 manifest 的 `outputs` 或 `delivery.primary_output` 追踪。

## 11. Root Flow 结构

root flow 必须声明：

```json
{
  "schema_version": "1.0",
  "id": "example.root",
  "mode": "lifecycle",
  "cartridge_id": "example.cartridge",
  "protocol": {
    "id": "CF-FARP",
    "version": "0.4"
  },
  "start": "start",
  "states": {},
  "edges": []
}
```

规则：

1. `states` 必须是非空对象。
2. `start` 必须指向存在的 state。
3. 业务节点必须使用 `type=process`。
4. 生命周期节点可以使用 `type=system` 或 `type=terminal`。
5. `edges` 与节点 `next` 不得表达冲突拓扑。
6. 节点级 `protocol_version` 如存在，必须与 flow 协议一致或由基座按 flow 协议解释。

## 12. 节点通用规则

业务节点统一使用：

```json
{
  "type": "process",
  "kind": "decision",
  "executor": "llm",
  "effect": "none",
  "input": "brief",
  "output": "decision"
}
```

通用规则：

1. `type=process` 是业务节点唯一合法顶层类型。
2. `kind` 表达节点业务语义。
3. `executor` 表达执行主体。
4. `effect` 表达副作用级别。
5. `input` 必须显式声明读取 Store key。
6. `output` 必须显式声明写入 Store key。
7. 多输入可用逗号、换行或数组表达，由基座规范化解释。
8. 节点不得读取未声明 Store key，除非该字段被声明为 optional input。
9. 节点不得写入未声明 output，除非工具结果中有明确 artifact 或审计字段。

## 13. 节点统一模型

协议层节点模型：

```text
type=process
kind=input | transfer | retrieval | decision | transform | validation | routing | mcp_read | mcp_execute | remote_call | gate | ui | human_gate | delivery | ...
executor=user | deterministic | rules | rag | llm | mcp | remote | human | plugin
effect=none | read_only | writes_store | writes_artifacts | writes_files | mutates_state | external_side_effect
```

UI 显示名可以按 `kind` 和 `display.suffix` 转换，但协议语义只能来自 `type`、`kind`、`executor`、`effect` 和契约字段。

## 14. 用户层显示规则

用户层显示应降低协议术语负担，但不得改变协议语义。

推荐显示：

- `kind=input` 显示为“输入节点”。
- `kind=decision, executor=llm` 显示为“AI决策节点”。
- `kind=mcp_read` 显示为“MCP读取节点”。
- `kind=mcp_execute` 显示为“MCP执行节点”。
- `kind=transfer` 显示为“传递节点”。
- `kind=delivery` 显示为“交付节点”。

如果需要更贴近用户，可显示为“素材规格节点”“资料入库节点”“素材工坊节点”，但详情中必须保留协议字段。

不得把所有 process 节点显示为“处理节点-xxx”而隐藏真实 `kind`。

## 15. 协议层字段

节点协议字段包括：

- `type`
- `kind`
- `executor`
- `effect`
- `protocol_version`
- `input`
- `output`
- `output_contract`
- `input_schema`
- `decision_contract`
- `mcp_binding`
- `tool_binding`
- `allowed_tools`
- `permission`
- `failure_policy`
- `audit_log`
- `primary_output`

字段可以位于节点顶层，也可以由兼容适配器从 `params.protocol` 读取，但认证时必须能得到等价标准结构。

## 16. Kind 规则

### 16.1 input

收集用户输入或外部输入，写入 Store。

必须：

- `executor=user | human | remote | plugin`
- `effect=writes_store`
- 声明 `input_schema`
- 声明 `output`

### 16.2 transfer

搬运、合并、重命名 Store 数据。

必须：

- `executor=deterministic | rules`
- `effect=writes_store`
- 不得绑定工具。

### 16.3 retrieval

检索资料、构造上下文或读取只读知识。

必须：

- `effect=read_only | writes_store`
- 不得执行外部副作用。

### 16.4 decision

判断、规划、生成结构化业务结果或请求用户补充。

必须：

- `executor=llm | rules | human`
- AI 决策必须遵守第 21 至 25 节。

### 16.5 mcp_read

调用只读工具。

必须：

- `executor=mcp`
- `effect=read_only`
- 工具 side_effect 必须为 `none`、`read_only` 或 `environment_probe`。

### 16.6 mcp_execute

调用可能产生副作用的工具。

必须：

- `executor=mcp`
- `effect` 与工具副作用匹配。
- 声明 `allowed_tools`。
- 声明 `permission`。
- 声明 `failure_policy`。
- 声明 `audit_log=true`。

### 16.7 gate / human_gate

执行门禁或人工确认。

必须明确：

- 通过条件。
- 不通过时的状态。
- 是否允许继续。

### 16.8 ui

展示 UI 内容或预览。

不得隐式修改业务 Store，除非声明 `effect=writes_store`。

### 16.9 delivery

汇总交付结果。

必须声明：

- `input`
- `output`
- `primary_output`

## 17. Executor 规则

`executor` 定义谁执行节点：

- `user`：用户通过表单或交互输入。
- `deterministic`：确定性代码。
- `rules`：规则引擎。
- `rag`：检索增强处理器。
- `llm`：语言模型。
- `mcp`：MCP 工具执行器。
- `remote`：远程服务。
- `human`：人工审批。
- `plugin`：插件。

AI 能力必须使用 `executor=llm`。不得用 `executor=deterministic` 包装真实模型调用来逃避决策规则。

## 18. Effect 规则

`effect` 定义节点副作用：

- `none`：不读写外部状态，最多写节点 output。
- `read_only`：只读外部资源。
- `writes_store`：写运行 Store。
- `writes_artifacts`：写运行产物。
- `writes_files`：写文件。
- `mutates_state`：修改持久状态。
- `external_side_effect`：调用外部系统产生副作用。

规则：

1. AI 决策节点必须 `effect=none`。
2. `mcp_read` 不得使用副作用 effect。
3. `mcp_execute` 必须声明与工具匹配的 effect。
4. `mutates_state` 和 `external_side_effect` 必须有权限声明。
5. 测试台必须展示副作用级别。

## 19. 输入类处理节点

输入节点可以出现多次，不得与唯一入料口强绑定。

manifest 的 `inputs` 是输入 schema 注册表，不等同于唯一输入节点。

运行中追加输入必须：

- 写入明确 Store key。
- 记录来源。
- 记录交互节点。
- 不覆盖未声明可覆盖的数据。

## 20. 传递、检索与转换节点

传递、检索与转换节点用于整理上下文。

规则：

1. 不得伪装成 AI 决策。
2. 不得执行未声明工具。
3. 结构化输出应优先使用 JSON 或明确 schema。
4. 对下游工具可消费的数据必须稳定。
5. 如果检索节点使用 MCP，只读调用应使用 `kind=mcp_read`。

## 21. AI 决策节点

AI 决策节点必须：

```json
{
  "type": "process",
  "kind": "decision",
  "executor": "llm",
  "effect": "none",
  "output_contract": "decision_envelope.v1"
}
```

AI 决策节点可以做：

- 判断是否通过。
- 判断是否需要用户补充。
- 阻断不可执行需求。
- 生成结构化计划。
- 生成结构化业务规格。
- 生成工具计划。
- 生成下游节点可消费的业务 payload。

AI 决策节点不得做：

- 直接执行工具。
- 写文件。
- 修改持久状态。
- 调用 MCP。
- 绕过 gate 或 permission。

如果 AI 决策节点允许 `resolved`，必须声明 `decision_contract.consume`。

## 22. decision_envelope.v1 契约

最小结构：

```json
{
  "schema": "decision_envelope.v1",
  "status": "resolved",
  "summary": "已经完成决策。",
  "payload": {
    "decision": {}
  }
}
```

合法 `status`：

- `resolved`
- `needs_user_input`
- `blocked`

### 22.1 resolved

`resolved` 表示 AI 已生成可继续执行的结构化结果。

`payload` 可以包含：

- `decision`
- `plan`
- `spec`
- `asset_specs`
- `tool_plan`
- 其他由节点契约声明的结构化字段

### 22.2 needs_user_input

必须包含：

```json
{
  "question": {
    "id": "question_id",
    "prompt": "需要用户补充的信息。",
    "input_schema": {},
    "store_key": "user_reply"
  },
  "resume": {
    "policy": "resume_next_node"
  }
}
```

### 22.3 blocked

必须包含：

```json
{
  "issues": [
    {
      "code": "reason_code",
      "message": "阻断原因"
    }
  ]
}
```

`blocked` 后不得继续执行后续副作用节点。

## 23. decision_contract.consume

`decision_contract.consume` 是 v0.4 的核心契约。它声明后续节点实际消费 envelope 中的哪一部分。

示例：

```json
{
  "decision_contract": {
    "schema": "decision_envelope.v1",
    "allowed_statuses": ["resolved", "needs_user_input", "blocked"],
    "consume": {
      "mode": "payload_path",
      "path": "payload.asset_specs",
      "as": "asset_specs_payload",
      "required": true,
      "on_missing": "fail_closed"
    }
  }
}
```

规则：

1. AI 决策节点允许 `resolved` 时，必须声明 `consume`。
2. `mode` 当前必须为 `payload_path`。
3. `path` 必须为 `payload` 或以 `payload.` 开头。
4. `as` 必须是明确 Store key。
5. `as` 不得等于节点原始 `output`。
6. `required=true` 时，缺失 path 必须失败。
7. `on_missing` 合法值为 `fail_closed` 或 `block_decision`。
8. 禁止通过隐式命名生成消费 key。

## 24. 消费投影运行语义

运行时必须按以下顺序处理 AI 决策：

1. 调用或模拟 LLM。
2. 解析完整 `decision_envelope.v1`。
3. 校验 envelope。
4. 将完整 envelope 写入节点 `output`。
5. 如果 status 为 `resolved`，按 `decision_contract.consume.path` 读取值。
6. 将读取值写入 `decision_contract.consume.as`。
7. 记录 consume path、consume as、投影状态和值摘要。

如果 status 为 `needs_user_input` 或 `blocked`，不得写入消费投影。

## 25. 后续节点消费规则

后续业务节点应读取 `decision_contract.consume.as` 声明的 Store key，而不是读取完整 envelope。

完整 envelope 仅用于：

- 审计。
- 详情展示。
- 暂停恢复。
- 错误追踪。
- 状态判断。

如果后续节点需要业务决策结果，应读取例如：

```text
asset_specs_payload
plan_approval_payload
brief_decision_payload
```

而不是读取：

```text
asset_specs_decision
plan_approval_decision
brief_decision
```

## 26. 交互式暂停与恢复

当 AI 决策输出 `needs_user_input` 时，运行时必须：

1. 停止执行当前节点之后的节点。
2. 将 run status 设置为 `paused_waiting_user`。
3. 记录 pending interaction。
4. 暴露用户补充输入接口。
5. 用户回答后按 `resume.policy` 恢复。

合法 resume policy：

- `resume_same_node`
- `resume_next_node`
- `resume_target_node`
- `restart_run_with_inputs`

如果基座不支持某个 resume policy，不得声明对应能力。

## 27. LLM Provider 与测试模式

协议不绑定模型供应商。

基座必须区分：

- live LLM：真实模型调用。
- mock resolved：固定 resolved 模拟。
- mock interaction：固定 needs_user_input 模拟。
- mock blocked：固定 blocked 模拟。
- offline fallback：缺少模型配置或调用失败时的本地兜底。

测试台不得把 mock 或 offline fallback 伪装成 live LLM。

事件日志必须记录：

- provider id。
- model。
- used_llm。
- fallback。
- decision_test_mode。

## 28. 决策与工具计划

AI 可生成工具计划，但不得执行工具。

合法链路：

```text
AI decision -> consume projection -> gate/validation -> mcp_execute
```

或：

```text
AI decision -> tool_plan.v1 -> mcp_execute(tool_binding=from_tool_plan)
```

AI 输出的工具计划必须被验证：

- 工具是否在 `allowed_tools` 中。
- 参数是否符合 schema。
- 副作用是否匹配节点 effect。
- 权限是否满足。
- 失败策略是否明确。

## 29. MCP、Remote 与工具节点

manifest 中的工具声明必须包含：

```json
{
  "id": "tool_id",
  "type": "builtin",
  "server": "media",
  "tool": "forge_pixel_asset_batch",
  "enabled": true,
  "required": true,
  "contract": {
    "capability": "builtin_tool_call",
    "idempotent": false,
    "side_effect": "writes_artifacts",
    "timeout_ms": 120000,
    "retry_policy": {
      "max_attempts": 1
    }
  },
  "params_schema": {
    "type": "object",
    "additionalProperties": true
  }
}
```

工具节点必须声明：

- `allowed_tools`
- `tool_binding`
- `permission`
- `failure_policy`
- `audit_log`

`mcp_read` 只能调用只读工具。

`mcp_execute` 可以调用副作用工具，但必须接受权限、审计和失败策略约束。

## 30. 数据链与 Store

Store 是单次运行内上下文。

规则：

1. 节点只能读取声明的 `input`。
2. 节点只能写入声明的 `output` 和协议审计字段。
3. 数据链断裂必须在测试台中可见。
4. 探针可以为范围外上游节点注入占位数据，但必须标注 seeded_by_probe。
5. 全流程运行不得使用探针占位数据。
6. Store key 必须稳定、可读、无隐式推导。

## 31. tool_plan.v1 契约

结构：

```json
{
  "schema": "tool_plan.v1",
  "tool_id": "media_forge_pixel_asset_batch",
  "params": {},
  "expected_output": "draft_asset_bundle",
  "reason": "Need to create draft assets from approved specs."
}
```

规则：

1. `tool_id` 必须在 `allowed_tools` 中。
2. `params` 必须符合工具 schema。
3. `expected_output` 必须匹配后续消费。
4. 副作用必须匹配执行节点 effect。
5. tool plan 不得绕过 permission。

## 32. Artifact 与 Delivery

Artifact 必须记录：

- type。
- path。
- source node。
- visibility。
- whether run scoped。

Delivery 节点必须汇总：

- 用户输入。
- AI 决策消费值。
- 工具报告。
- artifact。
- 最终输出。

manifest 应声明：

```json
{
  "delivery": {
    "type": "summary_with_artifacts",
    "primary_output": "episode_delivery",
    "show_artifacts": true
  }
}
```

## 33. 错误、失败与回退

节点失败必须产生结构化事件。

失败策略包括：

- `fail_closed`
- `continue_with_report`
- `skip_with_report`
- `pause_for_user`

规则：

1. 副作用节点默认应使用 `fail_closed` 或 `continue_with_report`。
2. 缺失必需 input 必须报告数据链断裂。
3. AI 输出无法解析为 envelope 时必须阻断或使用明确 offline fallback。
4. `blocked` 不等同于工具失败，它是决策结果。
5. fallback 不得覆盖真实失败而不记录。

## 34. 测试台与探针

测试台必须支持：

- 全流程运行。
- 探针范围运行。
- live / mock / offline 决策模式展示。
- 节点详情。
- 完整 envelope 展示。
- consume path 展示。
- consume as 展示。
- 消费投影值展示。
- 工具结果展示。
- 数据链诊断。
- artifact 预览。

探针规则：

1. 起点和终点必须是合法节点。
2. 探针范围内工具节点之前必须存在处理/决策/输入类节点，除非节点本身是协议化 MCP process。
3. 探针注入数据必须标记 seeded。
4. 探针通过不等同于全流程认证通过。

## 35. 兼容性报告

兼容性报告必须检查：

- 协议是否注册。
- 基座是否声明支持协议。
- required profiles 是否满足。
- required capabilities 是否满足。
- required tools 是否声明。
- tool pack 是否支持。
- root flow 结构是否合法。
- flow contract 是否满足。
- delivery readiness 是否存在。

兼容性报告必须区分：

- blocker。
- warning。
- info。

存在 blocker 时不得运行或认证。

## 36. 认证要求

认证必须满足：

1. manifest 声明 `base_contract`。
2. manifest 声明 `runtime_contract`。
3. manifest 声明 `delivery_readiness`。
4. root flow 声明 `CF-FARP@0.4`。
5. 兼容性报告无 blocker。
6. 兼容性报告无 warning。
7. 所有 AI resolved 决策节点声明合法 `decision_contract.consume`。
8. 所有 required tool 声明 contract。
9. 认证标签由工具或认证流程写入，不得手工伪造。

通过后可添加：

```json
{
  "protocol_certification": {
    "status": "certified",
    "label": "cf-farp-0-4-certified",
    "protocol": "CF-FARP",
    "protocol_version": "0.4"
  }
}
```

## 37. 能力声明

本协议涉及的核心能力包括：

```text
manifest_load
manifest_validate
runtime_contract_parse
compatibility_report
root_flow_execution
basic_node_execution
unified_process_node
multi_input_node
process_node_kind_parse
process_executor_contract
process_effect_contract
runtime_input_node
transfer_process
retrieval_process
decision_process
mcp_read_process
mcp_execute_process
process_mcp_readonly_binding
tool_plan_emit
tool_plan_validate
tool_plan_tool_binding
decision_envelope_v1
decision_envelope_validate
decision_consume_contract
decision_consume_projection
llm_live_mode
llm_mock_mode
llm_offline_fallback
runtime_user_input_request
paused_waiting_user_status
pending_interaction_record
runtime_resume_after_user_input
builtin_tool_call
artifact_collect
data_chain_diagnostics
delivery_readiness_check
probe_run
testbench_run
protocol_display_mapping
```

基座不得用笼统“支持 AI”替代这些能力声明。

## 38. 迁移规则

从 v0.3 迁移到 v0.4 时：

1. 不得修改 v0.3 协议文件。
2. manifest 的 `base_contract.version` 改为 `0.4`。
3. manifest 的 `runtime_contract.protocol_version` 改为 `0.4`。
4. root flow 的 protocol 改为 `0.4`。
5. 每个 AI 决策节点保留完整 `decision_envelope.v1` output。
6. 每个允许 `resolved` 的 AI 决策节点补充 `decision_contract.consume`。
7. 后续业务节点改为读取 `consume.as`。
8. 测试台必须展示 consume 投影。
9. 认证标签改为 `cf-farp-0-4-certified`。

## 39. 示例

### 39.1 判断型决策

```json
{
  "type": "process",
  "kind": "decision",
  "executor": "llm",
  "effect": "none",
  "input": "episode_brief",
  "output": "brief_decision",
  "output_contract": "decision_envelope.v1",
  "decision_contract": {
    "schema": "decision_envelope.v1",
    "allowed_statuses": ["resolved", "needs_user_input", "blocked"],
    "consume": {
      "mode": "payload_path",
      "path": "payload.decision",
      "as": "brief_decision_payload",
      "required": true,
      "on_missing": "fail_closed"
    }
  }
}
```

### 39.2 结构化素材规格决策

```json
{
  "schema": "decision_envelope.v1",
  "status": "resolved",
  "summary": "生成素材规格。",
  "payload": {
    "asset_specs": {
      "schema": "asset_spec_batch.v1",
      "assets": [
        {
          "id": "hero_blue_shirt",
          "kind": "character",
          "name": "蓝色衬衫人物",
          "visual_prompt": "蓝色衬衫的人物角色，2.5D 像素风。",
          "target_status": "draft"
        }
      ]
    }
  }
}
```

对应 consume：

```json
{
  "consume": {
    "mode": "payload_path",
    "path": "payload.asset_specs",
    "as": "asset_specs_payload",
    "required": true,
    "on_missing": "fail_closed"
  }
}
```

### 39.3 工具计划型决策

```json
{
  "schema": "decision_envelope.v1",
  "status": "resolved",
  "summary": "生成工具计划。",
  "payload": {
    "tool_plan": {
      "schema": "tool_plan.v1",
      "tool_id": "media_forge_pixel_asset_batch",
      "params": {
        "asset_specs": "store:asset_specs_payload"
      },
      "expected_output": "draft_asset_bundle"
    }
  }
}
```

## 40. 禁止事项

1. 禁止 AI 决策节点直接执行工具副作用。
2. 禁止用自然语言替代 `decision_envelope.v1`。
3. 禁止通过隐式命名生成消费 key。
4. 禁止后续节点默认读取完整 envelope 作为业务 payload。
5. 禁止 `consume.as` 覆盖原始 envelope output。
6. 禁止 `mcp_read` 调用副作用工具。
7. 禁止未声明 permission 的副作用节点运行。
8. 禁止测试台把 mock 伪装成 live LLM。
9. 禁止探针通过冒充全流程认证通过。
10. 禁止认证器为了单个卡带通过而放宽协议约束。
