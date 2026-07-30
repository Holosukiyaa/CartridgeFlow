# CartridgeFlow 流程创作与运行协议 v1.0

协议标识：`CF-FARP@1.0`

协议状态：`draft`

实现状态：`supported`

本文件是 v1.0 的唯一规范正文。第一部分完整收录并版本化 v0.8 的基础合同；第二部分完整收录 MCP/DLC 透明执行合同；第三部分定义显式执行计划。实现、兼容性和认证不得引用历史正文补足本文件缺失的语义。

---

# 第一部分：基础流程、运行、资源与交付合同
# CartridgeFlow Flow Authoring Runtime 协议 v1.0

协议编号：`CF-FARP-1.0`

协议状态：active

发布状态：完整正文

依赖宿主契约：`CARTRIDGEFLOW-BASE@0.2`

替代版本：`CF-FARP@0.7`

关系：本文完整替代 v0.7，是独立、自包含的 Flow 创作、静态分析与运行规范。实现或认证 v1.0 不需要读取历史 CF-FARP 正文。卡带领域语义由卡带自己的 schema 与 Portable DLC 提供，不属于本协议。

---

## 目录

1. [协议目标](#1-协议目标)
2. [规范关键词](#2-规范关键词)
3. [协议身份与版本](#3-协议身份与版本)
4. [实体](#4-实体)
5. [卡带包结构](#5-卡带包结构)
6. [Manifest 契约](#6-manifest-契约)
7. [模型配方](#7-模型配方)
8. [工具配方与资源角色](#8-工具配方与资源角色)
9. [Delivery Readiness](#9-delivery-readiness)
10. [Root Flow](#10-root-flow)
11. [业务节点与两类搭建模型](#11-业务节点与两类搭建模型)
12. [Kind 与交互节点约束](#12-kind-与交互节点约束)
13. [Store 与数据链](#13-store-与数据链)
14. [Decision Envelope](#14-decision-envelope)
15. [Decision Consume](#15-decision-consume)
16. [Pending Interaction](#16-pending-interaction)
17. [Tool Plan](#17-tool-plan)
18. [工具调用与副作用](#18-工具调用与副作用)
19. [Run 与节点状态](#19-run-与节点状态)
20. [Runtime Error Envelope](#20-runtime-error-envelope)
21. [Checkpoint](#21-checkpoint)
22. [Retry、Resume、Rollback 与 Restart](#22-retryresumerollback-与-restart)
23. [Replay Safety](#23-replay-safety)
24. [Artifact](#24-artifact)
25. [Delivery](#25-delivery)
26. [Fallback 与测试替身](#26-fallback-与测试替身)
27. [测试台与探针](#27-测试台与探针)
28. [Portable DLC](#28-portable-dlc)
29. [DLC Worker 与前端消息](#29-dlc-worker-与前端消息)
30. [Protocol Overlay](#30-protocol-overlay)
31. [资源所有权与卸载](#31-资源所有权与卸载)
32. [兼容性报告](#32-兼容性报告)
33. [认证](#33-认证)
34. [Capability 词表](#34-capability-词表)
35. [从 v0.6 迁移](#35-从-v06-迁移)
36. [禁止事项](#36-禁止事项)
37. [最小一致性清单](#37-最小一致性清单)
38. [完整示例](#38-完整示例)
39. [v0.6 条款处置矩阵](#39-v06-条款处置矩阵)
40. [规范追踪与演进](#40-规范追踪与演进)
41. [三层创作模型与唯一事实来源](#41-三层创作模型与唯一事实来源)
42. [结构化输入输出与数据绑定](#42-结构化输入输出与数据绑定)
43. [可执行控制拓扑](#43-可执行控制拓扑)
44. [Flow Analyzer](#44-flow-analyzer)
45. [派生工程关系](#45-派生工程关系)
46. [诊断、门禁与修复](#46-诊断门禁与修复)
47. [Authoring API 与创作 AI](#47-authoring-api-与创作-ai)
48. [从 v0.7 迁移](#48-从-v07-迁移)
49. [v0.7 条款处置矩阵](#49-v07-条款处置矩阵)
50. [统一 Flow 资源目录](#50-统一-flow-资源目录)

## 1. 协议目标

CF-FARP v1.0 规定：

- 卡带 Manifest 与 Root Flow 的可移植声明。
- 能力节点与交互节点组成的统一业务节点语义。
- 卡带资产、交互组件、稳定引用和可迁移边界。
- 被动 HTML 与可执行脚本的强制分离、隔离和最小授权。
- AI Decision Envelope 与显式消费投影。
- 工具计划、权限、副作用和本机资源绑定。
- 用户交互暂停与恢复。
- 稳定错误身份、检查点、重试、回滚和重放保护。
- Artifact、Delivery、测试台和认证。
- Portable DLC 的作用域、隔离和卸载行为。
- 业务流程、执行契约与派生工程关系的三层边界。
- 结构化输入输出、显式数据绑定与分支数据可用性。
- 可执行控制拓扑的类型隔离和 Runner 消费边界。
- 统一 Flow Analyzer、机器可读 finding、目标级别门禁和源摘要证据。
- 创作 AI 通过 Authoring API 修改源事实、通过 Analyzer 验证的闭环。

本协议 MUST NOT 绑定模型厂商、远程服务品牌、特定媒体引擎、业务领域或某个 Base 实现。

## 2. 规范关键词

- MUST / 必须：强制规则。
- MUST NOT / 不得：禁止行为。
- SHOULD / 应当：除非有可审计理由，否则遵守。
- MAY / 可以：可选行为。

正文语义优先于示例。示例只展示合法结构，不构成供应商或业务推荐。

## 3. 协议身份与版本

协议身份：

```text
CF-FARP@1.0
```

认证标签：

```text
cf-farp-0-8-certified
```

规则：

1. v1.0 是完整快照，不从 v0.7 或更早版本继承隐含语义。
2. 已按其他版本认证的卡带不得使用 v1.0 标签。
3. Base 只有在 `supported_protocols` 中声明 v1.0 时才能运行该卡带。
4. `partial` Base 只能运行其 capability 覆盖的卡带。
5. 未支持的版本必须在执行 Root Flow 前失败关闭。

## 4. 实体

| 实体 | 含义 |
|---|---|
| Base | 实现 Base Contract 并承载本协议的宿主 |
| Cartridge | 可安装、运行和卸载的流程包 |
| Manifest | 卡带身份、需求、权限、工具和交付声明 |
| Root Flow | 可执行流程图 |
| Process Node | 统一业务节点 |
| Capability Node | 执行模型、工具、转换、校验、路由或交付等工作的业务节点 |
| Interaction Node | 使用卡带组件展示内容、收集输入或审核结果的业务节点 |
| Package Asset | 随卡带迁移、不可执行并由稳定 ID 引用的内容资源 |
| Interaction Component | 交互节点引用的界面契约，可由被动模板或隔离脚本前端实现 |
| Store | 单次运行的结构化数据总线 |
| Tool | 有 schema、副作用和失败契约的能力 |
| Resource Role | 卡带对本机模型或工具实例的抽象需求 |
| Decision Envelope | AI 决策的结构化输出 |
| Pending Interaction | 暂停等待用户时的可恢复请求 |
| Checkpoint | 节点前后持久化的运行快照 |
| Artifact | 带身份、来源和 revision 的运行产物 |
| Delivery | 最终交付视图与主要输出 |
| Portable DLC | 卡带拥有的后端、前端、协议和 workflow 扩展 |
| Authoring Fact | 作者持久化的业务拓扑与执行契约源事实 |
| Normalized Topology | Analyzer 从合法控制声明生成的规范化可执行控制图 |
| Engineering Relation | Analyzer 从源事实生成、Runner 不消费的只读工程关系 |
| Flow Analyzer | 无业务副作用的确定性规范化、分析与诊断组件 |
| Analysis Report | 与源摘要、协议和分析目标绑定的机器可读分析结果 |
| Finding | 带稳定 code、位置、严重级别和修复语义的诊断项 |
| Authoring API | 以结构化操作修改业务流程与执行契约的创作接口 |

### 4.1 Protocol

Protocol 定义卡带在不同合规 Base 之间可移植的公开语义。它规定数据结构、状态、失败方式和可观察行为，不规定某个实现内部的类、函数、数据库或 UI 框架。

### 4.2 Base

Base 是实现 `CARTRIDGEFLOW-BASE` 并承载本协议的宿主。Base MUST 公开自身支持的协议版本、profiles、capabilities、tool packs 与 conformance 状态。Base 的内部实现存在，不等于相应能力已经被公开声明。

### 4.3 Cartridge

Cartridge 是可安装、运行、迁移、停用和卸载的流程包。卡带拥有自己的业务 schema、prompt、静态资产、Root Flow、测试和可选 DLC。卡带不得依赖未声明的 Base 私有实现细节。

### 4.4 Manifest

Manifest 是卡带的只读对外声明。发现、兼容性检查和安装预检可以读取 Manifest，但在通过校验前不得执行卡带代码。

### 4.5 Root Flow

Root Flow 是静态可分析的有向流程图。它声明节点、边、起点、协议身份和执行契约，不得依赖运行时猜测来补出主拓扑。

### 4.6 Process Node

Process Node 是统一业务节点。作者视角下，业务节点分为 Capability Node 与 Interaction Node；协议层仍统一使用 `type=process`。`kind` 表示做什么，`executor` 表示由谁执行，`effect` 表示会改变什么，三者必须与真实行为一致。

### 4.7 Store

Store 是单次 Run 内的结构化数据总线。节点只读声明的 input，只写声明的 output 和协议允许的审计字段。Store 不是大文件仓库，也不是跨 Run 的隐式全局状态。

### 4.8 Tool

Tool 是带输入 schema、输出 schema、副作用、幂等性、超时和失败策略的可调用能力。工具可以由 Base、MCP、远程 API 或 Cartridge DLC 提供，但必须通过 Manifest 身份和节点 allowlist 被引用。

### 4.9 Resource Role

Resource Role 是卡带对本机模型或工具实例的稳定抽象需求。卡带声明角色和约束；Base 在本地绑定 URL、key、command、路径或 Provider。远程知识库、检索服务和数据接口必须作为声明工具使用，不建立第二套全局数据来源模型。角色名称不得暗含只在某台机器成立的连接信息。

### 4.10 LLM Provider

LLM Provider 是 Base 本机拥有的模型连接与 wire adapter。卡带只携带模型角色配方，不携带 Provider 密钥、私有地址和个人连接 ID。

### 4.11 Decision Envelope

Decision Envelope 是 AI Decision 的标准输出容器。自然语言说明只能位于结构化 envelope 内，不得用一段文本替代 status、payload、question 或 issues。

### 4.12 Decision Consume Projection

Decision Consume Projection 按显式 path 从 resolved envelope 中读取业务值，写入独立 Store key。后续节点消费该投影，而不是猜测或拆解自然语言 summary。

### 4.13 Pending Interaction

Pending Interaction 是等待用户输入时的持久交互记录。它具有独立身份、schema、状态、创建节点、恢复策略和答案，不等同于前端临时表单状态。

### 4.14 Runtime Error Envelope

Runtime Error Envelope 是公开失败的稳定身份。它跨事件、Run snapshot、HTTP 和 UI 保持相同 error_id 与 code；完整堆栈只保存在本机诊断域。

### 4.15 Checkpoint

Checkpoint 是节点执行前后的持久快照，用于重试、继续、回滚、重启诊断和重放保护。它必须能在 Base 进程重启后重新读取。

### 4.16 Artifact

Artifact 是带稳定 ID、revision、来源、所有权和状态的运行产物。Artifact 可以引用文件、对象或外部受控资源，但不能退化为无来源语义的路径字符串。

### 4.17 Portable DLC

Portable DLC 是由单张卡带拥有的可选扩展单元。它可以携带后端工具、前端工作台、领域协议、供应商 workflow、测试和私有资源，但不得把这些实现写入 Base 核心。

### 4.18 Protocol Overlay

Protocol Overlay 是仅对当前卡带可见的协议注册视图。它不修改全局 registry，卡带停用或卸载后必须消失。

### 4.19 Frontend Sandbox

Frontend Sandbox 是卡带前端的隔离浏览器运行域。它只能使用版本化宿主消息 API，不得访问主前端 DOM、路由器、全局 Store 或同源权限。

### 4.20 Package Asset

Package Asset 是由卡带拥有、随包迁移且不能执行代码的内容资源，例如 prompt、schema、图片、样式、动效模板、被动 HTML 模板、测试 fixture 或可复用子 Flow。资产通过稳定 `asset_id` 引用，不通过散落在节点中的裸路径建立公开身份。

### 4.21 Interaction Component

Interaction Component 是交互节点使用的界面契约。`passive` 组件只组合不可执行资产；`sandboxed` 组件包含脚本并由 Portable DLC frontend 实现。组件只声明输入绑定、展示模式、具名动作、输出 schema 和所需宿主能力，不拥有隐藏拓扑，也不得直接修改 Runner 状态。

## 5. 卡带包结构

最小包：

```text
cartridge/
  manifest.json
  root.flow.json
  assets/
    registry.json
```

完整包 MAY 包含：

```text
cartridge/
  manifest.json
  root.flow.json
  assets/
    registry.json
    components.json
    prompts/
    schemas/
    ui/
    motion/
    media/
    fixtures/
  tests/
  dlc/
    descriptor.json
    backend/
    frontend/
      components/
    protocols/
    workflows/
    tests/
```

卡带不得要求复制文件到 Base 源码、全局前端、全局协议或全局配置目录后才能运行。

包结构规则：

1. 所有包内路径 MUST 使用相对路径，并在规范化后仍位于卡带根目录。
2. `..` 路径穿越、绝对路径、驱动器路径和指向包外的符号链接 MUST 被拒绝。
3. 卡带不得依赖包外未声明资源；外部依赖必须在 Manifest 中声明角色、权限、失败策略和预检方式。
4. 运行产物默认写入 run-scoped 目录；跨 Run 持久状态必须单独声明 ownership 与 permission。
5. `dlc/` 中的代码、协议、UI、workflow 和私有资源必须随卡带目录整体移动。
6. discovery 阶段 MAY 读取 Manifest、descriptor 和 hash，但 MUST NOT 导入代码、联网、启动进程或产生业务文件。
7. 安装与升级 MUST 先在临时目录完成校验，再通过原子替换或可恢复事务进入正式目录。
8. 普通 `assets/` MUST NOT 包含可执行 JavaScript、WebAssembly、浏览器 Worker、可执行表达式或能触发脚本的主动文档内容。
9. 卡带脚本只能位于 descriptor 声明并逐文件校验的 `dlc/frontend/` 或 `dlc/backend/` 作用域；把脚本改名为图片、HTML、模板或数据文件不改变其可执行身份。
10. Base 必须按解析后的媒体类型、文件内容和使用方式判定主动内容，不能只相信扩展名或 Manifest 标签。

## 6. Manifest 契约

最小 v1.0 Manifest：

```json
{
  "schema_version": "1.0",
  "id": "example.workflow",
  "name": "Example Workflow",
  "version": "1.0.0",
  "kind": "runtime_cartridge",
  "category": "workflow",
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
    "id": "CARTRIDGEFLOW-BASE",
    "version": "0.2"
  },
  "runtime_contract": {
    "protocol": "CF-FARP",
    "protocol_version": "0.8",
    "required_profiles": ["runtime_core", "flow_analysis"],
    "recommended_profiles": [],
    "required_capabilities": [
      "root_flow_execution",
      "structured_io_contract",
      "explicit_input_binding",
      "typed_control_edges",
      "executable_topology_filter",
      "flow_analysis_report_v1",
      "analysis_report_freshness_guard"
    ],
    "optional_capabilities": [],
    "required_tools": [],
    "optional_tools": []
  },
  "delivery_readiness": {
    "level": "dev",
    "runnable": true
  },
  "asset_registry": "assets/registry.json",
  "inputs": [],
  "outputs": [],
  "mcp_tools": []
}
```

规则：

1. `id` 与 `version` MUST 稳定。
2. `base_contract` MUST 指向 `CARTRIDGEFLOW-BASE@0.2` 或 Base 明确支持的后续兼容版本。
3. `runtime_contract` MUST 指向 `CF-FARP@1.0`。
4. `base_contract` 和 `runtime_contract` 是不同契约，版本不得要求相等。
5. `required_*` 缺失必须阻断；`optional_*` 缺失形成可见降级。
6. Manifest MUST 声明 `asset_registry`；没有资产时 registry 仍可为空数组。
7. 使用 interaction 节点时 Manifest MUST 声明 `interaction_components`。
8. Manifest MAY 包含 `publisher`、`branding`、`permissions`、`dependencies`、`environment`、`llm_recipe`、`resource_requirements`、`artifacts`、`delivery`、`protocol_extensions` 和 `portable_dlc`。
9. v1.0 卡带 MUST 要求 `flow_analysis` profile，以及 `structured_io_contract`、`explicit_input_binding`、`typed_control_edges`、`executable_topology_filter`、`flow_analysis_report_v1` 和 `analysis_report_freshness_guard` 最低能力；缺失时不得以 v1.0 运行或认证。

### 6.1 字段分组

| 分组 | 必需字段 | 作用 |
|---|---|---|
| 身份 | `schema_version`、`id`、`name`、`version`、`kind`、`category` | 标识可分发卡带 |
| 入口 | `root_flow`、`runtime` | 定位 Root Flow 与运行适配器 |
| 契约 | `base_contract`、`runtime_contract` | 声明宿主与 Flow 协议要求 |
| 交付 | `delivery_readiness`、`inputs`、`outputs` | 声明运行阶段与公开 I/O |
| 能力 | `mcp_tools`、可选 `llm_recipe`、`resource_requirements` | 声明模型、工具和本机资源角色 |
| 卡带内容 | `asset_registry`、使用交互时的 `interaction_components` | 声明资产身份、完整性和交互界面契约 |
| 风险 | 可选 `permissions`、`dependencies`、`environment` | 声明权限与外部条件 |
| 扩展 | 可选 `protocol_extensions`、`portable_dlc` | 声明卡带拥有的扩展 |
| 产物 | 可选 `artifacts`、`delivery` | 声明产物策略和主要交付 |

### 6.2 身份与入口

1. `id` MUST 在发布者作用域内稳定且唯一，升级不得静默更换 ID。
2. `version` SHOULD 使用可比较版本格式；升级与回滚必须保留原版本身份。
3. `root_flow.entry` MUST 指向存在的包内 JSON 文件。
4. `root_flow.mode` 在本版本 SHOULD 为 `lifecycle`；其他模式必须由 capability 明确声明。
5. `runtime.adapter` 是 Base 运行适配器身份，不得作为携带本机密钥或供应商 workflow 的入口。
6. `publisher` 和签名信息如果存在，必须与包校验和绑定，不能只作为显示文本。

### 6.3 Runtime Contract

`runtime_contract` 的数组字段语义如下：

- `required_profiles`：缺失任一项即 blocker。
- `recommended_profiles`：缺失形成 warning，并显示受影响体验。
- `required_capabilities`：缺失任一项即 blocker。
- `optional_capabilities`：缺失形成 info 或显式降级。
- `required_tools`：必须能解析到启用的 Manifest tool。
- `optional_tools`：不可用时不得静默替换成语义不同的工具。

每个条目 MUST 是稳定字符串 ID 或带 `id` 的结构化声明。Base 不得通过相似名称、UI 标签或猜测映射 required 身份。

### 6.4 输入与输出注册表

Manifest `inputs` 与 `outputs` 是公开 schema 注册表，不等同于唯一输入节点或唯一交付节点。

```json
{
  "inputs": [
    {
      "id": "request",
      "label": "请求",
      "type": "object",
      "required": true,
      "schema_ref": "asset:schema.request"
    }
  ],
  "outputs": [
    {
      "id": "final_report",
      "label": "最终报告",
      "type": "document",
      "required": true
    }
  ]
}
```

输入可以在流程中多次收集。每次追加输入必须记录来源、interaction 或外部事件身份、目标 Store key 和 revision。不得用 Manifest 注册表暗示运行时可以任意覆盖已有 Store 数据。

### 6.5 权限、依赖与环境

1. `permissions` MUST 描述真实文件、网络、进程、外部写入和敏感数据范围。
2. 权限等级 MUST 可由 UI 展示，不得把危险权限包装成普通说明。
3. `dependencies` MUST 区分 required/optional、package/shared/user-managed 和安装策略。
4. 发现阶段不得因为 dependency 声明自动下载、安装、升级或启动外部程序。
5. `environment` MAY 声明 OS、command、app_config、硬件或网络条件，但不得携带本机凭据值。
6. required dependency 或 environment 条件缺失时必须在业务执行前失败关闭。

### 6.6 协议扩展与 DLC

`protocol_extensions` 只声明卡带显式选择的伴随协议。每项至少包含 `id`、`version`，并可声明 `extends`、required/optional profiles 与 capabilities。扩展必须通过当前卡带 Overlay 解析，不能从其他已安装卡带偷取实现。

存在 `portable_dlc` 时，其 protocol MUST 与 Runtime Contract 完全一致，descriptor MUST 位于包内，并在任何后端或前端激活之前完成完整性校验。

### 6.7 卡带资产 Registry

`asset_registry` 指向包内 JSON 文件。标准结构：

```json
{
  "schema": "cartridgeflow.asset_registry.v1",
  "assets": [
    {
      "id": "ui.review_shell",
      "kind": "interaction_template",
      "path": "assets/ui/review.html",
      "media_type": "text/html",
      "sha256": "...",
      "size": 18420,
      "executable": false
    },
    {
      "id": "prompt.writer",
      "kind": "prompt",
      "path": "assets/prompts/writer.md",
      "media_type": "text/markdown",
      "sha256": "...",
      "size": 3260,
      "executable": false
    }
  ]
}
```

基础 `kind` 词表：

```text
flow model_recipe prompt schema motion_template
interaction_template style media fixture
```

规则：

1. `id` 在卡带版本内 MUST 唯一、稳定且与物理路径解耦；公开引用使用 `asset:<id>`。
2. `path` MUST 是包内相对路径，文件必须存在并匹配 `sha256` 与 `size`。
3. `media_type` 必须由 Base 结合内容检测验证，不能只相信作者声明或扩展名。
4. v1.0 registry 中 `executable` MUST 为 `false`。脚本、WebAssembly、Worker 和其他可执行内容不得作为普通资产注册。
5. Root Flow、模型配方、prompt、schema、动效模板、UI 模板和媒体可以作为卡带内容参与搭建，但 Root Flow 入口仍由 Manifest 单独声明。
6. `flow`、`model_recipe`、`prompt` 和其他声明性资产只能交给对应的结构化解析器；`executable=false` 禁止 Base 对其执行 eval、import、模板表达式代码或操作系统命令。
7. 节点 SHOULD 使用稳定资产引用；兼容导入器 MAY 读取旧相对路径，但必须在保存 v1.0 Flow 前迁移为 asset ID。
8. 删除或更换 asset ID 前必须检查 Root Flow、组件、配方、测试和其他资产的反向引用。悬空 required 引用是 blocker。
9. 运行期间生成的文件属于 Artifact 或 private data，不得回写进只读资产 Registry 冒充包资产。
10. `motion_template` 和 `style` 资产只能是声明性数据。需要执行 JavaScript、Python、表达式引擎或供应商插件代码的动效/渲染模板必须归入相应 DLC backend/frontend，并遵守工具或脚本执行边界。

### 6.8 Interaction Component Registry

`interaction_components` 指向包内 JSON 文件。标准结构：

```json
{
  "schema": "cartridgeflow.interaction_components.v1",
  "components": [
    {
      "id": "review.result",
      "version": "1.0.0",
      "runtime": "passive",
      "entry": {"type": "asset", "ref": "asset:ui.review_shell"},
      "supported_modes": ["display", "collect", "review"],
      "input_schema": "asset:schema.review_input",
      "actions": [
        {"id": "approve", "label": "通过", "payload_schema": "asset:schema.empty"},
        {"id": "revise", "label": "退回修改", "payload_schema": "asset:schema.revision_feedback"},
        {"id": "cancel", "label": "取消", "payload_schema": "asset:schema.empty"}
      ],
      "host_capabilities": []
    },
    {
      "id": "editor.storyboard",
      "version": "1.0.0",
      "runtime": "sandboxed",
      "entry": {"type": "dlc_frontend", "ref": "storyboard_editor"},
      "supported_modes": ["collect", "review"],
      "input_schema": "asset:schema.storyboard_input",
      "actions": [
        {"id": "approve", "label": "通过", "payload_schema": "asset:schema.storyboard_answer"},
        {"id": "revise", "label": "退回修改", "payload_schema": "asset:schema.revision_feedback"},
        {"id": "cancel", "label": "取消", "payload_schema": "asset:schema.empty"}
      ],
      "host_capabilities": ["artifact.read", "draft.write", "interaction.propose"]
    }
  ]
}
```

上例为组件结构节选；其中所有 `asset:schema.*` 引用在真实卡带中都必须作为 `kind=schema` 条目存在于同一 Asset Registry，否则 discovery 失败。

规则：

1. component `id` 与 `version` 在卡带版本内 MUST 唯一稳定，交互节点使用 `component_ref` 引用该 ID，Pending Interaction 固化实际版本与 entry hash。
2. `runtime=passive` 的 entry MUST 引用 `interaction_template` 资产，并满足 6.9 的无脚本规则。
3. `runtime=sandboxed` 的 entry MUST 引用当前卡带 Portable DLC descriptor 中声明的 frontend component；缺少 descriptor、hash 或 capability 时失败关闭。
4. `supported_modes` 只允许 `display | collect | review`。组件不能自行发明改变 Runner 生命周期的模式。
5. `actions` 必须静态枚举稳定 ID、Host 显示 label 与 payload schema。label 是作为纯文本转义呈现的显示值，可以本地化或修改，不参与路由身份，不能包含可执行标记。
6. `host_capabilities` 使用最小授权；未声明能力必须拒绝。组件不得直接声明 URL、key、本机路径、任意网络域或任意 Flow target。
7. 组件 registry 只描述界面契约，不执行代码。发现阶段不得加载 entry、创建 iframe 或运行脚本。
8. passive component 只负责内容与视觉。用于 collect/review 时，Base 必须根据 input/action schema 在 iframe 外生成 Host-owned fields 和 action controls；不得尝试读取无同源 iframe DOM。
9. sandboxed component MAY 在 iframe 内提供复杂编辑控件并通过 `draft.write` 更新草稿，但最终 action control 仍由 Host 拥有。

### 6.9 被动 HTML 与样式安全

`runtime=passive` 的 HTML 是模板资产，不是应用代码。Base MUST 使用 HTML/CSS 解析器检查实际文档结构，禁止仅用正则表达式或文件扩展名判断安全性。

被动 HTML MUST NOT 包含：

- `script`、`iframe`、`object`、`embed`、`applet`、`portal`、`base`、主动 `meta refresh`。
- 任意 `on*` 事件属性、`javascript:` URL、可执行 `data:` 文档、内联模块或动态 import。
- `form`、`input`、`button`、`select`、`textarea`、带 `href` 的 `a/area` 等可提交或导航控件，以及自动提交、任意 frame 导航、弹窗、下载触发或外部网络连接。passive collect/review 的控件由 Host 从 schema 生成。
- 可执行 SVG、`foreignObject`、SMIL 事件、WebAssembly、Worker、Service Worker 或浏览器扩展入口。
- CSS `@import`、外部 URL、脚本表达式或可突破卡带资源作用域的引用。

被动模板必须在等价于下列最小策略的隔离域中呈现：

```text
default-src 'none'; script-src 'none'; connect-src 'none';
img-src 'self' data: blob:; style-src 'self' 'unsafe-inline';
font-src 'self'; object-src 'none'; frame-src 'none';
worker-src 'none'; form-action 'none'; base-uri 'none';
```

包内图片、字体和样式只能通过校验 cartridge、component、asset ID、规范化路径和 hash 的受控 URL 加载。发现主动内容、媒体类型欺骗或无法可靠解析的文档时，Base MUST 返回稳定安全错误并拒绝预览、运行和打包；不得“清理后继续”而不生成新的资产 revision 与 hash。

## 7. 模型配方

卡带 MAY 声明模型角色：

```json
{
  "llm_recipe": {
    "schema": "cartridgeflow.llm_recipe.v1",
    "roles": [
      {
        "id": "planning_model",
        "label": "规划模型",
        "capability": "text.reasoning",
        "api_type": "openai_compatible",
        "wire_api": "responses",
        "model": "configured-locally",
        "required": true
      }
    ]
  }
}
```

卡带也 MAY 通过 `model_recipe` 资产引用同一结构：

```json
{
  "llm_recipe": {
    "asset_ref": "asset:model_recipe.primary"
  }
}
```

inline 配方与 `asset_ref` 只能选择一种。Base 必须在 discovery 阶段解析 asset ID、校验 kind/hash/schema 后得到同一规范化配方；不得把资产显示名称当作本机 Provider 绑定键。

配方 MUST NOT 包含：

- URL 或 endpoint。
- API key、token、Authorization 或私有 header。
- 本机绝对路径。
- 只属于开发者机器的 Provider ID。

Base MUST 通过本机 assignment 将角色连接到 Provider。缺少 required 角色绑定时返回 `PROVIDER_CONFIGURATION_MISSING` 或等价稳定错误。

### 7.1 模型角色字段

| 字段 | 要求 | 语义 |
|---|---|---|
| `id` | MUST | 卡带内稳定角色 ID |
| `label` | MUST | 开发者可读名称，不参与自动猜测 |
| `capability` | MUST | 例如 text.reasoning、vision.analysis、image.generation |
| `api_type` | MUST | 期望的兼容 API 类型 |
| `wire_api` | MUST | 消息 wire contract，例如 responses 或 chat_completions |
| `model` | MUST | 固定模型标识或 `configured-locally` |
| `required` | SHOULD | 是否阻断真实运行 |
| `constraints` | MAY | 上下文、模态、结构化输出或质量约束 |

角色 ID 是卡带与本机 assignment 的连接点。显示名称相同不构成绑定；Base MAY 提供人工拖拽或显式映射，但不得依据厂商名和模糊相似度静默选择 Provider。

### 7.2 绑定与预检

Base 在运行前 MUST：

1. 解析每个 required 模型角色。
2. 检查本机 Provider 是否存在、启用且具有凭据。
3. 检查 api_type、wire_api、模型和模态能力是否满足。
4. 返回不包含密钥的绑定摘要。
5. required 角色不满足时在调用模型前阻断。

预检成功只证明配置可用，不证明外部模型质量、余额、配额或服务稳定性。需要网络探测时必须明确标记为外部调用，并遵守 timeout 与凭据脱敏。

### 7.3 Live、Mock 与 Offline

运行模式至少区分：

- `live`：调用真实本机 Provider。
- `mock_resolved`：固定 resolved envelope。
- `mock_interaction`：固定 needs_user_input envelope。
- `mock_blocked`：固定 blocked envelope。
- `offline_fallback`：明确声明的本地替代路径。

事件和 Run snapshot MUST 记录 role id、脱敏 Provider identity、model、wire_api、used_llm、execution_mode、fallback 和 fallback_reason。mock 或 fallback 不得获得 live 结果标记。

## 8. 工具配方与资源角色

工具声明描述“调用什么契约”，本机资源描述“连接哪个实例”。

远程知识库、搜索索引、数据库查询服务和内容仓库只要通过网络或本机进程提供能力，就属于本节的 MCP、remote API 或其他声明工具。v1.0 不定义独立的全局 Data Source 绑定；需要随卡带携带的静态知识内容应作为 package asset，需要运行时查询的外部内容必须经过工具契约、权限、超时和审计。

```json
{
  "resource_requirements": [
    {
      "role": "document_lookup",
      "kinds": ["mcp", "remote_api"],
      "required": true
    }
  ],
  "mcp_tools": [
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
        "idempotent": true,
        "side_effect": "read_only",
        "timeout_ms": 30000,
        "retry_policy": {
          "max_attempts": 2,
          "initial_delay_seconds": 0.5,
          "max_delay_seconds": 2,
          "total_timeout_seconds": 45
        }
      },
      "params_schema": {
        "type": "object"
      }
    }
  ]
}
```

规则：

1. 卡带只保存 `resource_role`、tool ID、schema 和行为契约。
2. URL、key、command secret 和认证值 MUST NOT 存入 Manifest 或 Root Flow。
3. Base 在运行前解析本机绑定并做 preflight。
4. 供应商 workflow、上传协议、轮询逻辑和返回解析必须由卡带 DLC 或外部适配包拥有。
5. required resource 未绑定时不得执行调用节点。

### 8.1 Resource Requirement

资源需求结构：

```json
{
  "role": "document_lookup",
  "kinds": ["mcp", "remote_api"],
  "required": true,
  "capabilities": ["search"],
  "constraints": {
    "read_only": true
  }
}
```

规则：

1. `role` MUST 在卡带内稳定唯一。
2. `kinds` MUST 是卡带可接受的本机资源类型集合。
3. `capabilities` 与 `constraints` 描述行为要求，不得嵌入供应商连接细节。
4. required role 没有匹配项时是 blocker；optional role 没有匹配项时必须显示降级。
5. 一个本机资源 MAY 被多张卡带绑定，但卡带之间不得看到彼此的私有 binding 数据。

### 8.2 Manifest Tool Contract

每个工具声明至少包含：

| 字段 | 要求 |
|---|---|
| `id` | 卡带内稳定 tool ID |
| `type` | builtin、mcp、remote 或 plugin 身份 |
| `server` / `tool` | 作用域内调用身份 |
| `resource_role` | 外部资源调用时必需 |
| `enabled` | 是否参与当前卡带工具表 |
| `required` | 缺失时是否阻断 |
| `contract.capability` | 行为能力 |
| `contract.side_effect` | 副作用分类 |
| `contract.idempotent` | 是否可安全重复 |
| `contract.timeout_ms` | 单次有界超时 |
| `contract.retry_policy` | 最大次数、退避和总超时 |
| `params_schema` | 输入参数 schema |
| `result_schema` | 可选结果 schema |

`enabled=true` 不代表自动授予权限；节点仍必须通过 allowed_tools、effect、permission 与当前 binding 校验。

### 8.3 本机 Binding Descriptor

本机 binding MAY 使用以下公开摘要：

```json
{
  "schema": "cartridgeflow.local_bindings.v1",
  "cartridge_id": "example.workflow",
  "roles": {
    "document_lookup": {
      "resource_id": "local.docs.search",
      "kind": "remote_api",
      "ready": true,
      "credential_state": "configured"
    }
  }
}
```

公开摘要不得包含 URL、command、key、token、Authorization、私有 header 或本机绝对路径。真实连接只在 Base 本机配置域解析。

### 8.4 Resource Preflight

预检结果 MUST 区分：

- `ready`：绑定存在且静态条件满足。
- `missing_binding`：没有本机资源映射。
- `missing_credential`：资源存在但凭据缺失。
- `incompatible_kind`：资源类型不在可接受集合。
- `capability_mismatch`：能力或副作用约束不满足。
- `external_unverified`：未做真实连通性验证。

预检不得通过选择“任何可用资源”自动绕过角色约束。

## 9. Delivery Readiness

合法 level：

- `dev`：开发中，不得作为普通用户正式交付。
- `preview`：可演示，但必须显示限制与 fallback。
- `production`：可在满足要求的生产 Base 直接运行。

`production` 卡带 MUST：

- 不依赖设计台、探针 seeded 数据或未打包文件。
- 不携带本机配置和秘密。
- 有明确 primary output。
- 对持久写入、外部副作用和用户 Artifact 有所有权声明。
- 通过兼容性、完整性和交付预检。

补充规则：

1. `runnable=true` 不能覆盖协议 blocker，只表示作者期望该阶段可运行。
2. `dev` 运行 MAY 使用设计台、mock 和探针，但结果必须带开发标记。
3. `preview` 运行 MUST 展示已知限制、外部未验证项与 fallback。
4. `production` 不得要求用户打开 Flow 编辑器修复输入或配置。
5. certification target 与真实 Runtime Contract 不一致时必须阻断认证。
6. 从 preview 提升到 production 必须生成新的预检和认证证据，不能只修改 level 文本。

## 10. Root Flow

```json
{
  "schema_version": "1.0",
  "id": "example.workflow.root",
  "mode": "lifecycle",
  "cartridge_id": "example.workflow",
  "protocol": {
    "id": "CF-FARP",
    "version": "0.8"
  },
  "start": "start",
  "states": {},
  "control_edges": []
}
```

规则：

1. `states` MUST 是非空对象。
2. `start` MUST 指向存在节点。
3. 生命周期节点 MAY 使用 `type=system | terminal`。
4. 业务节点 MUST 使用 `type=process`。
5. `next` 与可执行 `control_edges` 重复边必须去重，冲突边必须阻断。
6. 从 start 不可达的节点必须显式标记 isolated/experimental，否则是结构问题。
7. Flow MUST 可静态分析，不得靠运行时猜测生成主拓扑。

### 10.1 拓扑来源

Root Flow MAY 使用节点 `next`、结构化 `routes`、`action_routes`、`failure_route` 或顶层 `control_edges` 表达可执行关系。v0.7 的顶层 `edges` 是迁移输入，不是 v1.0 的规范持久化字段。Base 必须先完成类型校验，再规范化为同一原子控制图：

1. 相同 source/target/condition 的重复边去重。
2. 相同 route 条件指向不同 target 是 blocker。
3. 指向不存在节点的边是 blocker。
4. 无 start 可达路径的业务节点必须标记 `isolated=true` 或 `experimental=true`。
5. 循环 MUST 显式声明退出条件、最大迭代或由专用循环 capability 承载。

顶层 control edge 最小结构：

```json
{
  "kind": "branch",
  "from": "validate",
  "to": "deliver",
  "condition": "store:validation.passed == true"
}
```

条件表达式必须来自 Base 声明的受限表达式语言，不得执行任意代码。

`control_edges[].kind` 只允许 `control | branch | action_route | failure_route`。数据、模型、工具、MCP、资源和 Artifact 依赖不得写入 `control_edges` 或兼容 `edges`。Runner MUST NOT 把未知 kind、`runtime_effect=false` 或 Analyzer 派生关系解释为后继节点。

### 10.2 生命周期节点

- `type=system` MAY 用于 start、checkpoint 或受控系统事件。
- `type=terminal` 表示路径终止，不执行隐藏业务逻辑。
- 生命周期节点不得伪装成工具、LLM 或持久写入节点。
- 一个 Flow MAY 有多个 terminal，但每条可成功路径必须到达明确终态。

### 10.3 图分析

静态分析至少检查 start、缺失节点、不可达节点、无出口节点、冲突边、未受控循环、数据链来源、分支数据可用性、资源绑定和副作用路径。分析发现与运行事件必须使用稳定 node id。v1.0 Base 必须通过第 44 节 Analyzer 生成规范化拓扑；前端不得维护另一套决定运行语义的图推导规则。

## 11. 业务节点与两类搭建模型

统一模型：

```json
{
  "type": "process",
  "kind": "decision",
  "executor": "llm",
  "effect": "none",
  "input": "request_context",
  "output": "planning_decision"
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
| `type` | 业务节点固定为 process |
| `kind` | 业务语义分类 |
| `executor` | 实际执行主体 |
| `effect` | 最大副作用级别 |
| `inputs` | 具名输入契约，包含 required、schema 和 binding |
| `outputs` | 具名输出契约，包含 Store/Artifact identity 与 schema |
| `input` / `optional_input` | v0.7 迁移输入；保存为 v1.0 前必须规范化到 inputs |
| `output` | v0.7 迁移输入；保存为 v1.0 前必须规范化到 outputs |
| `input_schema` | 输入结构约束 |
| `output_contract` | 标准输出容器身份 |
| `allowed_tools` | 节点可调用工具白名单 |
| `tool_binding` | 工具选择来源和绑定方式 |
| `resource_role` | 本机资源抽象身份 |
| `permission` | 副作用授权要求 |
| `failure_policy` | 失败后的运行语义 |
| `audit_log` | 是否记录副作用审计 |
| `replay_policy` | 恢复时的重放规则 |
| `next` / `routes` | 后续拓扑 |

协议字段 SHOULD 位于节点顶层。为兼容编辑器，Base MAY 从 `params.protocol` 读取等价字段，但规范化结果必须唯一；顶层与嵌套值冲突时必须阻断，不能静默选一个。

### 11.2 多输入与多输出

v1.0 作者源文件 MUST 使用第 42 节定义的结构化 `inputs` 与 `outputs`。字符串、逗号/换行分隔字符串和字符串数组只允许被迁移器读取；Analyzer 对尚未迁移的写法必须产生 `LEGACY_IO_CONTRACT` finding，production、package 与 publish 目标下是 blocker。

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

UI MAY 使用“输入节点”“AI 决策节点”“MCP 读取节点”“远程执行节点”“交互节点”“交付节点”等友好名称，也可以使用领域名称。

不得把所有 Process Node 都显示为模糊“处理节点”，也不得用显示标签反向推导协议字段。

### 11.6 能力节点与交互节点边界

1. 能力节点负责业务执行；模型、工具、远程调用、文件写入和 Artifact 生成不得藏入 interaction component 脚本。
2. 交互节点负责界面与用户动作；它不得直接调用其他节点、改写原子图、绕过 gate 或伪造工具结果。
3. 交互组件只能维护 payload 草稿或提出 action intent；Host control 最终提交已声明 `action_id + payload`，Runner 校验后才按照节点的静态 `action_routes` 继续。
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
  "output": "review_answer",
  "action_routes": {
    "approve": "publish_result",
    "revise": "regenerate",
    "cancel": "cancelled"
  }
}
```

通用规则：

1. `interaction_mode` MUST 为 `display | collect | review`，并被目标组件 `supported_modes` 允许。
2. `component_ref` MUST 解析到当前卡带 interaction component；不得引用其他卡带组件或裸 HTML 路径。
3. `input_binding` 的值只能引用节点已声明的 required/optional input、受控 Run metadata 或 Artifact ref。组件不得读取整个 Store。
4. `display` 使用 `executor=deterministic | plugin`、`effect=none`，不得创建等待用户的 interaction；完成呈现事件后按 `next` 继续。
5. `collect | review` 使用 `executor=user | human`、`effect=writes_store`；组件脚本是隔离 renderer，不是替代用户的 executor。节点 MUST 声明 `output`、`action_routes` 和可解析的 payload schema，并创建可持久恢复的 Pending Interaction。
6. `action_routes` 的 key MUST 是 component actions 的非空子集；只有这些 action 对当前节点可用，target 必须静态存在且可达。
7. Component iframe 只能更新 run-scoped draft 或提出 action intent，不能调用最终 answer/commit API。Host 必须在 iframe 外根据 Registry 生成自身拥有的 action controls；只有用户在 Host control 上的可信操作才能提交 action ID 与当前 draft payload。
8. payload 经 schema 校验后才可写入 output；失败不得恢复 Run。
9. interaction 脚本不因运行在前端而获得 `effect=none` 豁免。它只能通过宿主授权能力产生声明效果，真实能力必须反映在节点 effect、permission、审计和重放规则中。
10. `kind=ui` 在 v1.0 中不是合法别名。旧节点必须迁移为 interaction，并明确组件、模式、输入、输出与动作路由。

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

action route 读取 `action_id`，下游业务读取声明 output。Host commit 必须绑定当前 draft hash 与 input revision，避免脚本在用户确认后替换 payload。

#### 12.9.1 Display

Display 用于欢迎页、中间说明、图片、HTML/Markdown 预览和结果展示。它可以引用 passive 或 sandboxed component，但不得等待提交、写业务 Store 或用脚本决定下一节点。需要按钮影响流程时必须改用 collect/review。

#### 12.9.2 Collect

Collect 用于自定义表单、文件选择和结构化用户输入。首次进入时创建 Pending Interaction；页面刷新、Base 重启或组件重新挂载后必须恢复同一 interaction identity、component version、输入 revision 和草稿引用。

#### 12.9.3 Review

Review 用于展示 Artifact、方案或中间结果并收集批准、退回、修改或取消。批准必须绑定被查看内容的 revision；上游内容变化后旧批准必须 invalidated。`revise` 等动作可以路由到已声明上游节点，但组件本身不得发起回滚或重放。

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
- `resume_next_node`
- `resume_target_node`
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
  "resume": {
    "policy": "resume_by_action_route",
    "action_routes": {
      "approve": "publish_result",
      "revise": "regenerate",
      "cancel": "cancelled"
    }
  },
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
- `resume_next_node`：当前节点契约已满足时，从其后续节点继续。
- `resume_target_node`：跳转到声明且可达的 target_node。
- `resume_by_action_route`：Base 根据已验证 action ID 选择 Pending Interaction 中已固化的静态 route，客户端不能提供 target。
- `restart_run_with_inputs`：使用原始输入和答案创建新的 Run 语义。

Policy 不得绕过尚未满足的 gate、permission 或 required input。目标节点不存在或不可达时必须阻断。

### 16.4 Answer Routes

human gate 和 interaction node MAY 声明按结构化答案进入目标、回滚或拒绝。路由必须静态枚举并校验答案 schema。sandbox component 只能提出允许的 action intent；最终答案由 Host control 提交，且不能直接指定未经契约允许的目标节点。Host commit 的 `action_id` 不存在、payload schema 不匹配、输入 revision 已失效或审批对象已更新时必须返回稳定冲突并保持 Run 暂停。

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

## 28. Portable DLC

携带 DLC 的 Manifest：

```json
{
  "portable_dlc": {
    "protocol": "CF-FARP@1.0",
    "descriptor": "dlc/descriptor.json",
    "activation": "manifest_scoped"
  }
}
```

Descriptor 使用 `cartridgeflow.portable_dlc.v2`，至少声明：

- id、version、owner_cartridge 和 scope。
- backend JSON stdio worker entry。
- 可选 sandbox frontend component entries。
- tools、protocols、resources 和 files SHA-256。

发现阶段不得执行代码。工具只进入当前卡带 Registry。后端不得导入主服务进程；前端不得进入主前端脚本域。

### 28.1 Portable DLC 定义

Portable DLC 必须满足：

1. 所有领域实现由一个明确卡带包拥有。
2. 移动卡带目录后，除声明的本机 binding 和外部依赖外，不修改 Base 文件即可验证和运行。
3. 未安装或未激活时，Base 不暴露该 DLC 的工具、协议、UI、workflow 或领域类型。
4. 激活只影响当前 cartridge/run 作用域。
5. 停用和卸载能够让执行能力从运行视图中消失。

Base 可以提供 descriptor 读取、hash 校验、作用域代理、Worker 宿主、前端 sandbox、Protocol Overlay 和生命周期事务，但不得提供只服务单个 DLC 的业务实现。

### 28.2 Descriptor 完整结构

```json
{
  "schema": "cartridgeflow.portable_dlc.v2",
  "id": "dlc.example.workflow",
  "version": "1.0.0",
  "owner_cartridge": "example.workflow",
  "scope": "cartridge",
  "backend": {
    "entry": "dlc/backend/entry.py",
    "transport": "json_stdio_worker"
  },
  "frontend": {
    "sandbox": "isolated_iframe",
    "components": [
      {
        "id": "storyboard_editor",
        "entry": "dlc/frontend/components/storyboard/index.html",
        "context_keys": ["interaction", "input", "artifacts"],
        "host_capabilities": ["artifact.read", "draft.write", "interaction.propose"],
        "script_policy": "external_hashed_only"
      }
    ]
  },
  "tools": [
    {
      "server": "example_tools",
      "tool": "build_output",
      "handler": "backend.entry:build_output",
      "effect": "writes_artifacts",
      "timeout_ms": 120000,
      "description": "Build the declared output.",
      "params": {}
    }
  ],
  "protocols": [
    {
      "id": "EXAMPLE-DOMAIN",
      "version": "1.0",
      "registry": "dlc/protocols/EXAMPLE-DOMAIN-1.0.json"
    }
  ],
  "resources": [
    {"path": "dlc", "ownership": "package"},
    {"path": ".data/cartridge_dlc/example.workflow", "ownership": "private_data"},
    {"path": "user_outputs", "ownership": "user_artifact"}
  ],
  "files": [
    {"path": "dlc/backend/entry.py", "sha256": "..."},
    {
      "path": "dlc/frontend/components/storyboard/index.html",
      "sha256": "...",
      "media_type": "text/html",
      "role": "frontend_entry"
    },
    {
      "path": "dlc/frontend/components/storyboard/app.js",
      "sha256": "...",
      "media_type": "text/javascript",
      "role": "frontend_script"
    },
    {"path": "dlc/protocols/EXAMPLE-DOMAIN-1.0.json", "sha256": "..."}
  ]
}
```

### 28.3 Descriptor 规则

1. schema MUST 为 `cartridgeflow.portable_dlc.v2`。
2. id、version 和 owner_cartridge MUST 稳定，owner MUST 匹配 Manifest。
3. scope 在本版本 MUST 为 cartridge。
4. backend transport MUST 是 Base 声明支持的隔离 transport；本规范标准值为 json_stdio_worker。
5. frontend 如果存在，sandbox MUST 为 isolated_iframe，并声明非空、ID 唯一的 components。
6. 所有路径 MUST 是包内相对路径且防路径穿越。
7. 可执行代码、协议、前端和 workflow 文件 MUST 出现在 files 并匹配 SHA-256。
8. descriptor tools 必须与 Manifest 启用工具集合完全一致，不能多一个或少一个。
9. tools 必须声明 server、tool、handler、effect、timeout 和 description。
10. descriptor 不得包含可执行表达式、凭据或隐式下载指令。
11. 每个 frontend component `id` MUST 与 Interaction Component Registry 的 `dlc_frontend` ref 一一对应；未被 Registry 引用的 entry 不得自动获得运行入口。
12. frontend entry、脚本、模块、样式、字体、图片、source map 和其他可加载文件必须全部出现在 `files`，并声明真实 media type、role 与 SHA-256。
13. `script_policy` 在 v1.0 MUST 为 `external_hashed_only`：禁止 inline script、inline module、`eval`、`new Function`、字符串定时器、动态生成代码、WebAssembly 和未列入 files 的动态 import。
14. frontend component 的 `host_capabilities` MUST 是对应组件 Registry 声明集合的子集或完全相等，冲突时失败关闭。

### 28.4 发现与验证

发现阶段只允许读取静态文件、解析 JSON 和计算 hash，不得：

- 导入 backend 模块。
- 启动 Worker、浏览器或外部应用。
- 执行 frontend 脚本。
- 发起网络请求。
- 下载依赖或生成业务文件。

验证至少检查 schema、owner、scope、路径、文件存在/hash/media type/role、Manifest tool 对齐、权限、依赖、frontend component 对齐、脚本策略、sandbox、protocol identity 和资源 ownership。Base 必须解析每个 frontend entry 及其静态资源引用，确认所有引用均可由 descriptor files 闭包满足。任一 blocker 使 DLC 进入 rejected/quarantined，不得部分激活。

### 28.5 作用域注册

DLC tool 的规范作用域身份：

```text
cartridge_id@cartridge_version/server/tool
```

主 Registry 只保存代理和 descriptor 元数据，不保存或导入领域 handler。代理调用前再次校验 package path、descriptor hash、当前 cartridge/run scope、Manifest allowlist、permission、effect 和 timeout。默认 Registry 与其他卡带 Registry 不得列出该工具。

相同 server/tool MAY 由不同卡带实现，但完整作用域 identity 不得冲突。

## 29. DLC Worker 与前端消息

Worker 请求 MUST 包含 schema、request_id、run_id、cartridge_id、DLC identity、server、tool 和 params。stdout 只返回 JSON 协议消息。

### 29.1 Worker 请求与响应

```json
{
  "schema": "cartridgeflow.dlc_worker_request.v1",
  "request_id": "request_...",
  "run_id": "run_...",
  "cartridge_id": "example.workflow",
  "dlc_id": "dlc.example.workflow",
  "dlc_version": "1.0.0",
  "server": "example_tools",
  "tool": "build_output",
  "params": {}
}
```

成功响应：

```json
{
  "schema": "cartridgeflow.dlc_worker_response.v1",
  "request_id": "request_...",
  "ok": true,
  "result": {},
  "artifact_refs": []
}
```

失败响应 MUST 携带稳定 code/message 或可转换为 Runtime Error Envelope 的结构。stdout 只能承载一个协议响应；普通日志写 stderr 或 run-scoped 日志。

### 29.2 Worker 生命周期

```text
absent -> validated -> inactive -> starting -> active
active -> stopping -> inactive
inactive -> uninstalling -> absent
starting | active -> failed | timed_out | cancelled
```

规则：

1. 主服务 MUST NOT 通过 import、动态 import 或 sys.path 注入加载 DLC backend。
2. Worker 必须验证 handler 属于 descriptor allowlist。
3. 请求和响应必须是 UTF-8 JSON 对象。
4. timeout、Run cancel 和 host shutdown 必须终止 Worker 执行域。
5. 最终状态必须记录为 succeeded、failed、timed_out 或 cancelled。
6. Worker 退出后主服务不得保留 DLC 模块引用或可调用 handler。
7. 大文件和二进制通过 Artifact 引用传递，不内联到 stdout。

Base MAY 使用每调用进程或持久 Worker，但必须证明作用域隔离、取消、停用和卸载语义等价。

前端组件消息使用领域中立类型：

```json
{
  "schema": "cartridgeflow.interaction_component_message.v1",
  "type": "interaction.propose",
  "request_id": "uuid",
  "channel_id": "channel_...",
  "run_id": "run_...",
  "cartridge_id": "example.workflow",
  "node_id": "review_storyboard",
  "component_id": "editor.storyboard",
  "interaction_id": "interaction_...",
  "payload": {
    "action_id": "submit",
    "draft_hash": "sha256:...",
    "input_revision": 3,
    "proposal_id": "uuid"
  }
}
```

宿主 MUST 校验消息 schema、一次性 channel、iframe/MessagePort identity、cartridge、run、node、component、interaction、input revision、action allowlist、draft hash 和 proposal identity。`interaction.propose` 只请求 Host 选择或展示一个 action，不回答 Pending Interaction，也不恢复 Run。大文件使用受权限控制的 Artifact URL 或上传会话，不通过消息内联。

### 29.3 Frontend Sandbox

主前端不得 import、eval、拼接执行或向主 document 注入卡带 JavaScript。每个 DLC frontend component 必须位于独立 iframe；标准 sandbox token 只允许 `allow-scripts`，MUST NOT 启用 `allow-same-origin`、`allow-top-navigation`、`allow-popups`、`allow-forms`、`allow-downloads`、`allow-modals`、`allow-pointer-lock` 或 `allow-presentation`。Base 增加 sandbox token 必须由后续协议版本和独立 capability 明确授权。

Sandboxed component MUST 从与 Base UI 不同的专用不可信 origin 提供，不携带 Base session cookie、Authorization 或其他 ambient credential，并使用 credentialless iframe 或可证明等价的凭据隔离。资源访问只使用短期、cartridge/component/file/hash scoped 的 Host 发行能力 URL。该 origin 不得承载 Base API、用户页面或其他卡带的共享可写状态。

Production Base MUST 使用独立 renderer/process 或可证明等价的执行隔离，使组件无限循环、内存膨胀、事件风暴或崩溃可以在不终止 Host UI/Runner 的情况下被限制和销毁。Base 必须公布有限的 entry/ready timeout、消息大小与速率、草稿大小、并发请求、内存/CPU 或等价资源策略。无法证明进程与资源隔离时，只能把 sandboxed component 标记为 dev/preview limitation，不能声明 production `interaction_process_isolation`。

frontend response 至少实施等价 CSP：

```text
default-src 'none'; script-src 'self'; connect-src 'none';
img-src 'self' data: blob:; style-src 'self' 'unsafe-inline';
font-src 'self'; object-src 'none'; frame-src 'none';
worker-src 'none'; child-src 'none'; media-src 'self' blob:;
form-action 'none'; base-uri 'none'; navigate-to 'none';
```

Host MUST 将 `frame-ancestors` 设置为当前 Base UI 的精确可信 origin；不得使用 `*`，也不得使用会阻止合法 Host 嵌入的 `'none'`。若 frontend 由独立资源 origin 提供，策略必须显式列出 Base UI origin。

`script-src` MUST NOT 包含 `'unsafe-inline'`、`'unsafe-eval'`、远程 origin、blob script 或 data script。HTML 中 script 只能通过包内相对 `src` 加载 descriptor `role=frontend_script` 文件；模块的静态或动态依赖也必须在 descriptor files 闭包中。禁止 Worker、Service Worker、SharedWorker、Worklet、WebAssembly 和运行时下载代码。

Base 必须强制阻断 iframe 自身导航、链接导航、location 赋值、重定向和其他向非 package URL 发起的导航请求，不能只依赖 `connect-src`。如果目标浏览器不支持 `navigate-to` 或等价拦截，Host 必须提供更强的资源 origin/网络拦截并通过真实浏览器测试；无法证明阻断时不得声明 `sandboxed_interaction_component`。

包内资源只能由同时校验 cartridge/version、component、规范化路径、descriptor membership、media type 和 hash 的端点提供。响应必须使用 `X-Content-Type-Options: nosniff`、`Referrer-Policy: no-referrer`、限制同源资源使用的 Cross-Origin-Resource-Policy，以及默认拒绝 camera、microphone、geolocation、display-capture、clipboard、USB、serial、HID 和 payment 等浏览器能力的 Permissions-Policy。HTML、脚本和 SVG 不得因错误 MIME 被当作其他被动资源执行。

DLC 不得访问主 DOM、全局 Store、路由器、CSS、其他卡带 Run、Artifact 或 private_data。页面切换、卡带停用或卸载时必须销毁 iframe、消息端口、监听器和未完成请求。

浏览器内脚本不得直接调用模型、MCP、remote API、DLC backend tool 或任意外部网络。需要这些能力时，组件更新草稿或提出声明 action，由用户通过 Host control 提交后，Flow 再进入对应能力节点。即使浏览器环境提供了 fetch、WebSocket、EventSource、sendBeacon 或导航 API，CSP 与宿主也必须阻断未授权外联。

### 29.4 消息信封

宿主创建 iframe 后 MUST 建立一次性通信通道：

1. Host 生成不可预测的 `channel_id` 与 nonce，并创建专用 `MessageChannel` 或安全等价物。
2. Host 只向目标 iframe 的 `contentWindow` 发送一次初始化消息并转移专用 port。由于无同源 sandbox 的 origin 为 opaque，通配 target origin 只允许用于这次初始化；必须同时校验目标 window identity。
3. Component 通过专用 port 回应 nonce，Host 验证后使通道进入 ready。
4. 后续业务消息只允许通过该 port，必须携带 channel、cartridge、run、node、component 和 interaction scope。
5. iframe reload、节点切换、Run 终态、卡带停用或超时后 channel 立即失效；旧 port 的消息必须拒绝。

所有请求 MUST 包含 schema、type、request_id、channel_id、run_id、cartridge_id、node_id、component_id、interaction_id 和 payload。需要响应的请求必须有 response/error/cancel/timeout 语义，不能靠单向消息猜测完成状态。

宿主响应示例：

```json
{
  "schema": "cartridgeflow.interaction_host_message.v1",
  "type": "interaction.proposal_result",
  "request_id": "uuid",
  "channel_id": "channel_...",
  "run_id": "run_...",
  "cartridge_id": "example.workflow",
  "node_id": "review_storyboard",
  "component_id": "editor.storyboard",
  "interaction_id": "interaction_...",
  "ok": true,
  "payload": {}
}
```

Host 必须验证消息实际来自分配给该 component instance 的 port。仅检查可伪造的 JSON 字段、`event.origin` 或 cartridge ID 不足以建立信任。

### 29.5 宿主能力

Sandbox MAY 请求 Base 明确授予的通用能力，例如：

- 读取当前 run snapshot 的安全子集。
- 读取当前卡带 Artifact metadata 或受控 URL。
- 更新当前 interaction 的未提交草稿。
- 提出由 Host action control 呈现的 action intent。
- 请求通知或用户下载。

标准 capability ID 至少包括 `run.read_declared`、`artifact.read`、`upload.create`、`draft.read`、`draft.write`、`interaction.propose`、`download.request` 和 `notification.request`。`draft.read/write` 只操作当前 run/interaction 的未提交草稿；跨 Run 私有状态不在该能力范围。每项能力必须在 Component Registry 与 DLC descriptor 中同时声明，并由 Host 按 cartridge/run/node/interaction scope 授权。

最终 action controls 必须由 Host 在 sandbox iframe 外根据 Component Registry 与节点 `action_routes` 生成。组件 MAY 请求 Host 高亮某个 action，但只有用户对 Host control 的可信操作才能调用 answer API。Host commit 必须再次读取并校验当前 draft、展示稳定 action label、绑定 draft hash/input revision/idempotency key，并在成功后关闭所有旧 proposal。iframe 消息不能模拟该可信操作。

下列能力在 v1.0 中禁止授予 frontend component：Pending Interaction 最终提交、任意 Store 读写、任意节点执行、任意路由跳转、模型或工具直调、任意网络代理、凭据读取、Base 文件系统、主前端状态、其他卡带数据、任意 HTML 注入和永久后台任务。

DLC UI 不得绕过 Runner 直接修改已提交状态。Host API 成功只表示宿主请求已受理，不得由组件伪装为节点完成、Artifact 已批准或 Delivery 已成功。

### 29.6 脚本审计与失败关闭

Base 在安装、升级、开发预览和认证前至少检查：

- 所有 HTML entry 已解析且没有 inline script、event handler 或未声明主动内容。
- 所有脚本、模块和资源都在 descriptor files 中且 hash 匹配。
- CSP、sandbox tokens、Host capability 和消息 schema 满足本版本。
- 专用不可信 origin、无 ambient credential、进程/renderer 隔离和有限资源策略真实生效。
- 组件不能通过资源 URL、重定向、source map、SVG、CSS、媒体容器或 MIME 欺骗加载未声明代码。
- 组件尝试 fetch、WebSocket、beacon、表单、图片、媒体或 frame 自导航时，不产生任何外部网络请求。
- 组件无限循环、内存膨胀、消息风暴或崩溃时，Host UI 与 Runner 仍可响应并能销毁该组件执行域。
- 开发模式、热更新和 localhost 不得放宽卡带脚本权限；开发辅助能力必须运行在卡带 sandbox 之外。

任一检查失败必须在脚本执行前返回稳定错误，例如 `INTERACTION_SCRIPT_FORBIDDEN`、`INTERACTION_COMPONENT_HASH_MISMATCH`、`INTERACTION_COMPONENT_CSP_INVALID`、`INTERACTION_HOST_CAPABILITY_DENIED` 或 `INTERACTION_CHANNEL_SCOPE_MISMATCH`。Base 不得静默删除脚本后继续，也不得退回无 sandbox 的 HTML 预览。

## 30. Protocol Overlay

卡带领域协议只能位于卡带 DLC 中。Base 为当前卡带构造：

```text
global protocol registry + current cartridge overlay
```

Overlay 不得写入全局 registry。卡带停用或卸载后，Overlay 必须消失。

Overlay 加载规则：

1. 只读取 descriptor 明确列出的协议文件。
2. 协议 ID/version 在当前 scoped view 中必须唯一。
3. 伴随协议的 `extends` 必须匹配当前 primary protocol 声明。
4. Overlay required profiles/capabilities 必须由 Base 和当前 DLC 共同满足。
5. 其他卡带只有在自己携带或明确依赖同一协议时才能看到该协议。
6. Overlay 失败不得回退为忽略领域协议后继续运行。

## 31. 资源所有权与卸载

DLC 资源 ownership：

- `package`：卸载删除。
- `private_data`：普通卸载删除。
- `shared_dependency`：按引用和用户确认处理。
- `user_artifact`：普通卸载保留。

卸载顺序：

1. 检查活动 Run，默认阻断不安全卸载。
2. 拒绝新调用。
3. 取消或等待活动 Worker。
4. 销毁 iframe。
5. 注销工具代理、路由和 Overlay。
6. 删除 package 与 private_data。
7. 保留 user_artifact，除非用户确认 purge。
8. 执行无残留扫描。

### 31.1 Ownership 规则

- `package`：代码、协议、UI、workflow 和随包资产；卸载必须删除。
- `private_data`：卡带缓存、索引和私有状态；普通卸载默认删除。
- `shared_dependency`：共享模型、应用或运行库；不得由单张卡带擅自删除。
- `user_artifact`：用户生成和明确保存的产物；普通卸载默认保留到通用归档。

路径必须最小化且明确。不得把整个工作区、用户目录或公共模型目录声明为 private_data。

Asset Registry、Interaction Component Registry、passive templates 和 DLC frontend files 都属于 `package`。组件未提交草稿属于 run-scoped runtime state；明确保存为跨 Run 卡带状态时才属于 `private_data` 并需要独立能力、permission 和真实 effect，导出给用户时属于 Artifact。交互节点引用只保存 package identity，不得复制本机 Provider、工具实例、URL、key 或 private path 进入卡带。

### 31.2 安装与升级

安装顺序：读取静态声明 -> 临时目录展开 -> 防路径穿越 -> hash/签名 -> 兼容性/权限/依赖预检 -> 用户确认 -> 原子激活。发现和预检阶段不得执行卡带代码。

升级必须保留旧版本或可恢复备份。任一阶段失败后，要么旧版本继续可用，要么新版本完整激活；不得留下半安装 Registry、Worker、路由或文件集合。

### 31.3 停用

停用顺序：拒绝新调用 -> 等待或取消活动调用 -> 终止 Worker -> 销毁 iframe -> 注销代理/路由/Overlay -> 清理进程缓存。停用不自动删除用户数据。

### 31.4 卸载模式

- `preserve_artifacts`：删除功能、package 和 private_data，保留 user_artifact。
- `purge_all`：在独立高风险确认后同时删除当前卡带 user_artifact。

shared_dependency 只有在引用为零、来源可识别且用户明确允许时才能删除。

### 31.5 无残留验收

卸载后必须证明：

1. 卡带目录和 private_data 不存在。
2. 新旧工具代理均返回 extension_inactive 或不存在。
3. Worker、子进程、端口和任务不再活动。
4. iframe、静态资源路由和消息监听器不存在。
5. Protocol Overlay 和领域类型不可见。
6. 默认 Registry 和其他卡带不受影响。
7. user_artifact 按所选模式保留或清除。

任一残留都使 DLC lifecycle conformance 失败。

## 32. 兼容性报告

兼容性报告 MUST 检查：

- Base Contract 是否满足。
- CF-FARP@1.0 是否注册并被 Base 支持。
- required profiles/capabilities/tool packs 是否满足。
- required model/resource roles 是否绑定。
- Manifest 与 Root Flow 是否合法。
- Asset Registry、稳定引用、hash、media type 和悬空引用是否合法。
- Interaction Component Registry、mode、action、schema 和 node route 是否一致。
- passive HTML 是否无主动内容；sandboxed component 的 descriptor v2、脚本闭包、CSP、channel 和 Host capability 是否满足。
- permission、dependency 和 delivery readiness 是否满足。
- DLC descriptor、hash、scope、Worker 和 sandbox 是否满足。

存在 blocker 时不得运行或认证。

兼容性报告最小结构：

```json
{
  "ok": false,
  "status": "blocked",
  "base_contract": {
    "required": "CARTRIDGEFLOW-BASE@0.2",
    "implemented": "CARTRIDGEFLOW-BASE@0.2",
    "supported": true
  },
  "protocol": {
    "required": "CF-FARP@1.0",
    "supported": true,
    "lifecycle": "supported",
    "migration_target": null
  },
  "profiles": {},
  "capabilities": {},
  "models": {},
  "resources": {},
  "tools": {},
  "permissions": {},
  "dependencies": {},
  "flow_contract": {},
  "assets": {},
  "interaction_components": {},
  "script_security": {},
  "portable_dlc": {},
  "portability": {
    "packaged": [],
    "local_binding_required": [],
    "missing_blockers": [],
    "forbidden": []
  },
  "delivery_readiness": {},
  "findings": []
}
```

finding severity：

- blocker：禁止运行和认证。
- warning：可以按声明开发/预览，但禁止认证；必须显示影响。
- info：可选能力或诊断信息。

### 32.1 Portability Report

开发卡带打包、导出、安装预检和升级前 MUST 生成 portability report，并把发现项稳定分为：

- `packaged`：Root Flow、模型配方、prompt、schema、动效模板、卡带 UI、允许分发的媒体、组件、DLC 代码和测试。
- `local_binding_required`：模型 Provider、工具实例、URL、key、credential、command、用户路径和其他由目标 Base 重新绑定的本机能力。
- `missing_blockers`：被引用但不存在、hash/media type 不匹配、required role 未声明、component/action/schema 不完整或目标 Base 缺少 required capability。
- `forbidden`：凭据、本机绝对路径、未声明脚本、主动 HTML 普通资产、越权 dependency、包外符号链接、未授权网络目标和其他禁止随包传播内容。

报告必须列出每项来源文件或声明、引用者、ownership、迁移处理和稳定 finding code。存在 `missing_blockers` 或 `forbidden` 时不得生成可安装包。仅把敏感字符串替换为空值不等于可迁移；卡带必须保留角色/配方要求，目标 Base 再显式绑定。

旧协议如果位于 Base 历史索引，必须报告 recognized_unsupported_protocol 和迁移目标；未知协议报告 unknown_protocol。不得用当前 v1.0 解释器静默运行旧版本。

## 33. 认证

`cf-farp-0-8-certified` 要求：

1. Base Contract 与 Runtime Contract 均合法。
2. Root Flow 声明 v1.0。
3. 兼容性报告无 blocker 和 warning。
4. 所有 AI decision 具有合法 envelope 与 consume。
5. 所有 required tools 具有完整 contract。
6. 所有 required resource roles 在认证环境完成绑定或被认证夹具明确替代。
7. 错误、恢复、副作用重放和 primary output 门禁通过。
8. DLC 卡带通过作用域、隔离、hash、停用、卸载和无残留测试。
9. Asset Registry、Interaction Component、被动 HTML 和脚本安全检查全部通过。
10. 每个 interaction action 的合法提交、非法 action、schema 失败、重复提交、刷新恢复和 revision 冲突均有证据。
11. portability report 没有 missing blocker 或 forbidden package content。
12. 所有节点使用结构化 inputs、outputs 与 binding，required 数据在所有可达路径上可证明可用。
13. 可执行 control topology 与 derived engineering relations 已隔离，Runner 过滤失败路径有 conformance 证据。
14. production/publish Analysis Report 完整、无 blocker、target 匹配且 source digest 新鲜。
15. fallback、Analyzer finding、analysis freshness 和 Authoring API revision conflict 的正向与失败测试通过。
16. 标签只能由认证工具写入。

```json
{
  "protocol_certification": {
    "status": "certified",
    "label": "cf-farp-0-8-certified",
    "protocol": "CF-FARP",
    "protocol_version": "0.8"
  }
}
```

认证报告必须引用实际 Base Implementation、协议 registry/正文 hash、Manifest/Root Flow hash、capability evidence、测试环境、工具/DLC hash 和测试结果。手工勾选清单不能替代机器报告。

认证只覆盖声明的卡带版本、协议版本、能力集合和测试环境。修改 Root Flow、required capability、工具 contract、DLC files、permission、Artifact/Delivery 语义后必须重新认证。

真实外部服务未验证时必须标记 external_unverified。mock、fixture 和 dry-run 可以证明结构路径，但不能证明真实外部质量或稳定性。

## 34. Capability 词表

v1.0 的完整核心能力词表包括：

```text
manifest_load
manifest_validate
runtime_contract_parse
compatibility_report
root_flow_execution
basic_node_execution
unified_process_node
multi_input_node
runtime_input_node
process_node_kind_parse
process_executor_contract
process_effect_contract
transfer_process
retrieval_process
decision_process
mcp_read_process
mcp_execute_process
remote_call_process
gate_process
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
pending_interaction_record_v2
runtime_resume_after_user_input
node_display_name
package_asset_registry
stable_asset_reference
interaction_component_registry
interaction_node
interaction_named_action_routes
passive_html_safety
sandboxed_interaction_component
interaction_script_csp
interaction_network_guard
interaction_process_isolation
interaction_host_channel
interaction_host_capability_guard
cartridge_portability_report
builtin_tool_call
remote_tool_call
artifact_collect
artifact_preview
data_chain_diagnostics
optional_input
delivery_readiness_check
probe_run
testbench_run
structure_analysis
protocol_display_mapping
portable_dlc_descriptor
portable_dlc_validate
cartridge_scoped_tool_registry
isolated_dlc_worker
dlc_worker_json_rpc
cartridge_protocol_overlay
frontend_dlc_sandbox
package_owned_code
dlc_activation_lifecycle
dlc_uninstall_cleanup
dlc_absence_verification
dlc_resource_ownership
dlc_artifact_retention_policy
dlc_integrity_hash
runtime_error_envelope_v1
runtime_state_machine
checkpoint_persistence
runtime_retry_policy
runtime_checkpoint_resume
runtime_rollback
runtime_restart
side_effect_replay_guard
worker_lifecycle_supervision
model_recipe_binding
local_resource_binding
resource_preflight
artifact_revision
artifact_provenance
artifact_invalidation
delivery_primary_output_guard
structured_io_contract
explicit_input_binding
typed_control_edges
executable_topology_filter
normalized_topology_projection
flow_analysis_report_v1
flow_source_digest
flow_analysis_target_gates
analysis_report_freshness_guard
derived_engineering_relations
dataflow_static_analysis
branch_data_availability_analysis
resource_dependency_analysis
policy_static_analysis
finding_contract_v1
authoring_api_contract
safe_autofix_contract
fallback_visibility_contract
flow_resource_catalog_v1
resource_origin_tracking
node_resource_binding_preflight
explicit_node_model_binding
silent_model_fallback_guard
authoring_model_scope_isolation
```

Base MUST 只声明已实现并有证据的能力。没有声明某能力不等于协议删除该能力，而是该 Base 只能支持不要求该能力的 v1.0 卡带。

## 35. 从 v0.6 迁移

迁移到 v1.0 至少完成：

1. Runtime Contract、Root Flow 和 certification target 改为 v1.0；Base Contract 继续独立声明。
2. 建立 Asset Registry，为 Flow、模型配方、prompt、schema、动效、UI、媒体和 fixture 分配稳定 asset ID、media type、size 与 hash。
3. 将节点和组件中的裸包内路径迁移为 `asset:<id>`；悬空引用必须列为 blocker。
4. 将 `kind=ui` 迁移为 `kind=interaction`，明确 display/collect/review mode、component_ref、input binding、output、action schema 与静态 route。
5. 将节点标题迁移为可编辑 `display_name`，保持 states key/node id 不变。
6. 对现有 HTML 做主动内容分类：无脚本内容迁移为 passive template；含脚本、事件属性或其他主动内容的文件不得进入普通资产。
7. 把需要脚本的界面迁移到 Portable DLC descriptor v2 frontend component，拆出外部脚本并逐文件声明 role、media type 与 hash。
8. 建立 Interaction Component Registry，声明 component runtime、支持模式、输入 schema、具名 actions 和最小 Host capabilities。
9. Pending Interaction 升级为 v2，固化 component identity/hash、input revision、allowed actions 和 action routes。
10. 把外部知识库、索引和数据接口统一迁移为 MCP/remote API 工具；随包静态内容迁移为 package asset。
11. 生成 portability report，区分随包携带、本机重新绑定、缺失阻断和禁止打包内容。
12. 重新计算所有 registry、descriptor 和 package hash，运行 v1.0 conformance 和认证，不沿用 v0.6 标签。
13. 把 legacy input/output 与 params 内数据引用迁移为结构化 inputs、outputs 和 bindings。
14. 把混合 edges 分类为 typed control facts；删除派生 data/resource edges 并由 Analyzer 重建。
15. 生成匹配 source digest 与目标级别的 analysis report，修复 blockers 后才运行、打包或认证。

迁移 MUST 生成新卡带 revision 或副本，不得静默覆盖唯一原件。

迁移工具 MUST 在修改前生成报告，至少列出：旧 Base/Runtime Contract、节点字段变化、隐式 consume、嵌入连接信息、不完整 Tool Contract、不安全副作用、DLC hash 变化和无法自动判断项。

以下变化不得自动猜测：

- 哪个本机资源应绑定某个 role。
- 一个远程操作是否幂等。
- 旧 output 中哪个字段是真实业务消费值。
- 哪些 Artifact 在回滚后仍有效。
- 用户是否授权新的 permission 或 purge_all。
- 旧 HTML 中的脚本究竟只负责呈现还是隐藏了模型、工具、网络或流程控制。
- 旧 UI 按钮对应哪个稳定 action、payload schema 和 Flow route。
- sandboxed component 真正需要哪些 Host capabilities。

这些项必须由开发者明确确认，并写入迁移后的结构化声明。

## 36. 禁止事项

1. 禁止 Base 为单张卡带硬编码业务或供应商实现。
2. 禁止卡带携带本机 URL、key、token 和私有路径。
3. 禁止 AI decision 直接执行副作用。
4. 禁止隐式推导 Decision consume key。
5. 禁止 mcp_read 调用副作用工具。
6. 禁止未授权副作用和无限重试。
7. 禁止非幂等副作用未经确认自动重放。
8. 禁止等待用户时继续执行后续节点。
9. 禁止把 mock、fallback 或空产物作为真实成功。
10. 禁止 primary output 缺失仍标记成功交付。
11. 禁止 DLC 后端进入主服务 import 域。
12. 禁止 DLC 前端获得主前端同源权限。
13. 禁止把 JavaScript、WebAssembly、Worker 或主动 HTML 注册为普通 package asset。
14. 禁止 inline script、inline module、eval、new Function、未列入 descriptor 的动态代码和通过 MIME 欺骗执行内容。
15. 禁止 interaction component 直接调用模型、工具、远程网络、任意节点或任意 Store API。
16. 禁止组件提交 Flow target、permission、effect、Store key 或未声明 action。
17. 禁止只依赖 iframe、文件扩展名、正则清洗或 CSP 文本而不验证实际资源闭包和消息作用域。
18. 禁止开发模式、localhost、热更新或预览入口放宽卡带脚本权限。
19. 禁止卸载后残留 Worker、iframe、MessagePort、代理、Overlay、路由或 private_data。
20. 禁止只声明协议版本而不声明真实 capability 和证据。
21. 禁止把派生 data/resource relation 写入控制图或交给 Runner 调度。
22. 禁止 required input 使用字段名相似、显示名称或画布位置隐式绑定。
23. 禁止使用过期、目标级别不足或 source digest 不匹配的分析报告通过门禁。
24. 禁止 Analyzer 调用业务代码、模型、收费工具或外部副作用资源。
25. 禁止创作 AI 直接编辑派生工程关系或静默应用 confirm/manual 修复。

## 37. 最小一致性清单

- [ ] Manifest 同时声明 Base Contract 与 CF-FARP v1.0。
- [ ] Root Flow 的业务节点可归为能力节点或 interaction 节点，生命周期节点边界明确。
- [ ] 每个节点保持稳定 id，并允许独立修改 display_name。
- [ ] Asset Registry 的 ID、路径、media type、size、hash 和反向引用可验证。
- [ ] interaction 节点声明 component、mode、输入绑定、输出、action 和静态 route。
- [ ] passive HTML 不包含脚本或其他主动内容。
- [ ] sandboxed component 使用 descriptor v2、外部哈希脚本、严格 CSP、隔离 iframe 和一次性 Host channel。
- [ ] interaction script 不能直调模型、工具、网络、Store 或任意节点。
- [ ] required input、output 和 Store 引用可追踪。
- [ ] AI decision 使用 envelope 与显式 consume。
- [ ] required model/resource role 在本机可绑定。
- [ ] 工具 schema、副作用、幂等性、超时和重试策略完整。
- [ ] Runtime Error Envelope 跨层保持同一身份。
- [ ] Checkpoint 可在重启后读取。
- [ ] 四类恢复动作语义独立。
- [ ] 非幂等副作用受重放确认保护。
- [ ] Artifact 与 primary delivery 可验证。
- [ ] DLC 安装、作用域、隔离、停用和卸载通过。
- [ ] Conformance 报告由真实测试生成。
- [ ] 所有 v1.0 节点使用结构化 inputs、outputs、binding 和 schema。
- [ ] control edges 已按类型隔离，Runner 不消费 derived relations。
- [ ] Analyzer 对 topology、dataflow、resources、branches、effects 和 delivery 完成分析。
- [ ] required input 在所有可达路径上可证明可用。
- [ ] fallback 已声明并在 Run/Delivery 中真实标记。
- [ ] 运行、打包或发布使用目标匹配且 source digest 新鲜的 analysis report。
- [ ] findings 具有稳定 code、位置、严重级别和结构化修复等级。

## 38. 完整示例

### 38.1 Decision、交互与消费

```json
{
  "type": "process",
  "kind": "decision",
  "executor": "llm",
  "effect": "none",
  "input": "request_context",
  "output": "planning_decision",
  "output_contract": "decision_envelope.v1",
  "decision_contract": {
    "schema": "decision_envelope.v1",
    "allowed_statuses": ["resolved", "needs_user_input", "blocked"],
    "on_needs_user_input": "pause",
    "interaction": {
      "store_key": "planning_reply",
      "input_schema": {
        "type": "object",
        "properties": {"answer": {"type": "string"}},
        "required": ["answer"]
      },
      "resume_policy": "resume_same_node"
    },
    "consume": {
      "mode": "payload_path",
      "path": "payload.plan",
      "as": "approved_plan",
      "required": true,
      "on_missing": "fail_closed"
    }
  },
  "next": "validate_plan"
}
```

后续 validation 节点读取 `approved_plan`，不读取 `planning_decision`。needs_user_input 时只保存 interaction，不产生 approved_plan。

### 38.2 Interaction Node 与具名动作

```json
{
  "type": "process",
  "kind": "interaction",
  "display_name": "审核分镜与素材",
  "executor": "user",
  "effect": "writes_store",
  "input": ["storyboard", "selected_media"],
  "interaction_mode": "review",
  "component_ref": "editor.storyboard",
  "input_binding": {
    "storyboard": "store:storyboard",
    "media": "store:selected_media"
  },
  "output": "storyboard_review",
  "action_routes": {
    "approve": "render_video",
    "revise": "revise_storyboard",
    "cancel": "cancelled"
  }
}
```

组件只能更新草稿并提出 `approve | revise | cancel` intent。Host 在 iframe 外显示对应 action controls；用户通过 Host control 提交后，Host 校验 interaction、draft hash、input revision、payload schema 和幂等键，把标准答案写入 `storyboard_review`，Runner 再选择静态 route。组件不能自行回答 interaction，也不能直接执行 `render_video` 或 `revise_storyboard`。

### 38.3 Tool Plan 与副作用执行

```json
{
  "type": "process",
  "kind": "mcp_execute",
  "executor": "mcp",
  "effect": "writes_artifacts",
  "input": "approved_tool_plan",
  "output": "draft_bundle",
  "allowed_tools": ["build_output"],
  "tool_binding": "from_tool_plan",
  "permission": "artifact.write",
  "failure_policy": "fail_closed",
  "audit_log": true,
  "replay_policy": {
    "mode": "require_confirmation_unless_idempotent"
  },
  "next": "review_bundle"
}
```

执行前必须校验 Tool Plan、Manifest tool、resource role、params schema、effect、permission 和幂等性。工具成功后仍由 review/validation 决定业务是否通过。

### 38.4 Remote Call

```json
{
  "type": "process",
  "kind": "remote_call",
  "executor": "remote",
  "effect": "read_only",
  "input": "approved_query",
  "output": "search_results",
  "resource_role": "document_lookup",
  "allowed_tools": ["lookup_documents"],
  "tool_binding": "lookup_documents",
  "timeout_ms": 30000,
  "failure_policy": "fail_closed",
  "audit_log": true,
  "next": "summarize"
}
```

节点中没有 URL、key 或 header；Base 根据 document_lookup 的本机 binding 执行预检和调用。

### 38.5 Delivery

```json
{
  "type": "process",
  "kind": "delivery",
  "executor": "deterministic",
  "effect": "writes_store",
  "input": "approved_report,report_artifact",
  "output": "final_delivery",
  "primary_output": "report_artifact",
  "next": "complete"
}
```

Base 验证 report_artifact 存在、hash 匹配、未 invalidated 且审批 revision 正确后，才能生成成功 Delivery snapshot。

## 39. v0.6 条款处置矩阵

| v0.6 内容 | v1.0 位置 | 处置 |
|---|---|---|
| 协议定位、关键词、独立 Base Contract | 1-3、6.3、32 | 完整保留；版本升级为独立 v1.0 快照 |
| Manifest、Root Flow 与静态拓扑 | 5-6、10 | 完整保留；Manifest 新增资产和交互组件入口 |
| Process Node、kind、executor、effect | 11-12 | 保留统一 `type=process`；作者模型明确分为能力节点和交互节点 |
| 节点用户层显示 | 11.5 | 扩展：新增可编辑 `display_name`，稳定 id 不随显示名变化 |
| `kind=ui` | 12.9、35 | 替代并废止：迁移为 `kind=interaction`，不保留别名 |
| UI 展示或收集输入 | 6.8、12.9 | 扩展为 component、mode、input binding、output、具名 action 和静态 route 契约 |
| 卡带静态 assets/prompts/schemas 目录 | 4.20、5、6.7 | 扩展为带稳定 ID、kind、media type、size 和 hash 的 Asset Registry |
| HTML 相对路径或内联内容 | 6.7-6.9、35 | 替代：保存 v1.0 前迁移为 asset/component 引用；主动内容不得作为普通资产 |
| Pending Interaction v1 | 16 | 替代为 v2，增加 component/hash、input revision、allowed actions 和 action routes |
| Decision Envelope 与 consume | 14-15 | 完整保留 |
| Tool Plan、MCP、Remote 与副作用 | 8、17-18、23 | 完整保留；外部知识和数据接口统一通过工具契约 |
| 模型配方与本机 assignment | 7 | 保留并允许通过 `model_recipe` 资产引用 |
| Store、错误、状态、Checkpoint 与恢复 | 13、19-23 | 完整保留；交互动作纳入相同状态与恢复语义 |
| Artifact、Delivery、fallback 与测试台 | 24-27 | 完整保留；测试台新增组件、action、revision 和脚本安全可见性 |
| Portable DLC descriptor v1 | 28 | 替代为 descriptor v2，frontend 从单 entry 改为具名 component entries |
| Frontend iframe sandbox 与 v2 消息 | 29 | 加强并替代：外部哈希脚本、严格 CSP、无同源 iframe、一次性 MessageChannel 和作用域消息 v1 |
| DLC Worker、Overlay、ownership 与卸载 | 28-31 | 完整保留；卸载残留检查增加 iframe、port 和组件资源 |
| 兼容性、认证和 capability 证据 | 32-34 | 扩展资产、组件、脚本安全、具名动作和 portability report |
| v0.6 认证标签 | 3、35 | 不沿用；v1.0 必须重新认证 |

本矩阵是覆盖审计，不表示 v1.0 运行时可以直接解释 v0.6 卡带。迁移必须生成 v1.0 卡带 revision，完成主动内容审计、重新计算 hash 并重新认证。

## 40. 规范追踪与演进

### 40.1 条款追踪

Base 声明的每个 capability MUST 映射到实现入口、正向测试、适用的失败测试和 UI 可见性或 not_applicable 说明。协议认证还必须把关键 MUST/MUST NOT 条款映射到 conformance case。

最低追踪域：

- Manifest 与本机秘密隔离。
- Root Flow 与 Process Node。
- Asset Registry、Interaction Component 与稳定引用。
- 被动 HTML 检查、脚本闭包、CSP、sandbox、Host channel 与 capability guard。
- Decision Envelope 与 Consume。
- Pending Interaction。
- Tool Contract、permission、failure 和 replay。
- Runtime Error、状态迁移与 Checkpoint。
- Artifact revision、provenance、invalidation 和 Delivery。
- DLC descriptor、scope、Worker、sandbox、Overlay、ownership 和卸载。

### 40.2 协议完整性

未来 v1.0 文案修正不得改变规范语义。新增 required 字段、状态、生命周期、副作用、所有权或安全边界必须发布新的完整协议版本。

新版本必须：

1. 自包含，不要求读取旧正文补足含义。
2. 提供目录、完整实体和字段契约。
3. 提供前一版本条款处置矩阵。
4. 明确保留、替代和废止项。
5. 同步机器 registry、版本化 capability/profile vocabulary 与规范 conformance；Base Implementation 必须如实保持 unsupported，直到实现、失败路径和运行 conformance 完成后才加入支持矩阵。
6. 对旧版本给出 recognized/unsupported/unknown 与迁移策略。

### 40.3 实现与协议边界

实现 bug 修复、性能改进、UI 优化和新增符合既有宿主接口的本机资源实例，不要求新协议版本。改变可移植卡带的公开含义时，必须先更新协议版本，不能只改代码和测试。

## 41. 三层创作模型与唯一事实来源

v1.0 把 Flow 明确分为三层：

1. **业务流程层**：节点、主流程、条件分支、用户动作和故障转移，回答“业务怎么走”。
2. **执行契约层**：输入输出、数据绑定、模型与工具角色、权限、副作用、失败、审计和重放策略，回答“节点怎么确定地执行”。
3. **工程关系与诊断层**：规范化拓扑、数据流、资源依赖、风险和 finding，回答“系统如何解释和证明前两层”。

前两层合称 Authoring Facts。它们是卡带的唯一运行事实，由作者、Authoring API 或获得授权的创作 AI 持久化。第三层只能由符合本协议的 Analyzer 从当前 Authoring Facts 生成。

### 41.1 必须持久化的事实

卡带 MUST 持久化：

- 稳定 Flow、node、component、asset、model role、tool role 和 output identity。
- `next`、条件 route、具名 action route、failure route 和合法 control edge。
- 结构化 `inputs`、`outputs`、binding 与 schema。
- 模型、工具、MCP、远程资源和 Artifact 角色声明。
- permission、effect、timeout、failure、audit、retry 和 replay policy。
- interaction component、action、payload schema 与恢复契约。
- 影响业务结果的 fallback mode、触发条件和结果标记。

### 41.2 不得成为第二份事实的内容

以下内容 MUST NOT 作为 Runner 输入或独立业务事实写回 Root Flow：

- 根据 binding 推导的数据流线。
- 根据 model/tool/resource role 推导的依赖线。
- Analyzer 生成的 relation、finding、健康颜色和说明文字。
- 可由源声明重建的 normalized topology。
- 工作台关系线的颜色、虚实、动画、筛选和布局。

Base MAY 缓存派生输出，但缓存 MUST 绑定 `source_digest`、协议版本、Analyzer identity 和 analysis target。摘要不匹配时缓存立即失效，不得用于运行、打包、认证或发布。

### 41.3 修改规则

用户或 AI 想改变数据来源时，必须修改 input binding；想改变执行顺序时，必须修改控制声明；想改变工具或模型依赖时，必须修改资源角色或 binding。拖动、删除或重绘派生工程线不得隐式修改 Authoring Facts。

## 42. 结构化输入输出与数据绑定

v1.0 节点 MUST 使用具名 `inputs` 与 `outputs`。每个名称只在当前节点内作为端口 identity，不得依赖显示名称或字段相似度建立绑定。

### 42.1 输入契约

```json
{
  "inputs": {
    "edition_name": {
      "required": true,
      "schema": {"type": "string", "minLength": 1},
      "binding": {
        "source": "store",
        "key": "daily_config",
        "path": "edition_name"
      }
    },
    "cover_image": {
      "required": false,
      "schema_ref": "asset:schema.image_artifact_ref",
      "binding": {
        "source": "artifact",
        "artifact_id": "daily_cover"
      }
    }
  }
}
```

输入规则：

1. `required` MUST 是 boolean。
2. `schema` 与 `schema_ref` 必须且只能选择一个；无业务值的 trigger 输入 MAY 使用空对象 schema。
3. required input MUST 声明 binding。optional input MAY 声明 `default`，但 default 必须通过 schema。
4. binding `source` 基础词表为 `run_input | store | node_output | artifact | interaction_answer | constant`。
5. `constant` 只能保存非秘密、可移植、通过 schema 的声明值；URL、凭据和本机路径不得借此进入卡带。
6. `node_output` MUST 指向稳定 node id 与 output port；Analyzer 必须解析其最终 Store/Artifact identity。
7. `path` 使用协议规定的受限结构化路径，不得包含脚本、函数或动态求值。
8. 同一 input 不得同时从多个 binding 读取；多来源合并必须由显式 transform/merge 节点完成。

### 42.2 输出契约

```json
{
  "outputs": {
    "editorial": {
      "target": {
        "type": "store",
        "key": "editorial_draft"
      },
      "schema_ref": "asset:schema.editorial_draft",
      "write_policy": "replace_revision"
    },
    "video": {
      "target": {
        "type": "artifact",
        "artifact_id": "final_video"
      },
      "schema_ref": "asset:schema.video_artifact",
      "write_policy": "new_revision"
    }
  }
}
```

输出规则：

1. target `type` 只允许当前 Base 声明支持的 `store | artifact`；跨 Run 持久化必须使用专用工具和 permission，不能伪装成普通 output。
2. Store key 或 Artifact identity 在卡带版本内 MUST 稳定。
3. `schema` 与 `schema_ref` 必须且只能选择一个。
4. `write_policy` 必须与 Store revision、Artifact revision 和 replay policy 相容。
5. 同一路径上两个节点写入相同 identity 时必须有明确 merge/replace 顺序；存在并行或分支覆盖歧义时是 blocker。
6. 执行器只能提交已声明输出。额外字段可以存在于声明对象 schema 内，但不得临时创建未声明 Store key 或 Artifact identity。

### 42.3 类型与路径兼容

Analyzer MUST 对 producer output schema 与 consumer input schema 执行静态兼容检查。至少检查类型、required property、数组元素、nullable、枚举和结构化路径存在性。无法证明兼容时不得生成 `confidence=deterministic` 的 data relation。

模糊字段名、自然语言描述和显示名称只可生成 suggestion finding，不得成为 binding。Base 不得因为 `news` 与 `news_list` 相似而静默连接。

### 42.4 控制路径上的数据可用性

required input 不仅要有生产者，还必须在所有可能到达消费者的控制路径上可用。Analyzer MUST 检查：

- producer 是否在 consumer 之前执行。
- 分支汇合时是否每个可达分支都生产 required identity。
- failure continue/skip 后 required 数据是否仍存在。
- retry、resume 和 rollback 后读取的 revision 是否有效。
- interaction answer、decision consume 和 fallback 是否在对应状态下真实产出。

只有部分分支生产数据时，作者必须增加 default producer、显式 merge/gate、把输入改为 optional，或重构拓扑；Analyzer 不得用空值补齐。

## 43. 可执行控制拓扑

可执行控制拓扑是唯一允许 Runner 消费的图关系集合。它由作者声明产生，但由 Analyzer 规范化和校验。

### 43.1 控制关系类型

| kind | 来源 | 语义 |
|---|---|---|
| `control` | `next` 或无条件 control edge | 成功后的普通后继 |
| `branch` | 条件 route | 条件成立时的后继 |
| `action_route` | interaction `action_routes` | Host 验证具名动作后的后继 |
| `failure_route` | 显式故障转移 | 指定失败类别发生后的恢复后继 |

普通 `failure_policy=fail_closed | continue_with_report | skip_with_report | retry` 是节点策略，不自动产生控制边。只有声明了稳定 target 和触发语义的故障转移才生成 `failure_route`。

### 43.2 规范化拓扑

Analyzer MUST 输出：

```json
{
  "start": "start",
  "control_edges": [
    {
      "id": "control:start:collect_config",
      "kind": "control",
      "from": "start",
      "to": "collect_config",
      "derived_from": ["states.start.next"]
    },
    {
      "id": "branch:quality_gate:passed:delivery",
      "kind": "branch",
      "from": "quality_gate",
      "to": "delivery",
      "condition_id": "passed",
      "derived_from": ["states.quality_gate.routes.passed"]
    }
  ]
}
```

规范化规则：

1. 相同语义的重复声明去重，但报告重复来源。
2. 同一 source/condition/action/failure selector 指向不同 target 是 blocker。
3. terminal 有普通后继、target 不存在、start 不存在或未受控循环是 blocker。
4. 多出口节点必须能区分条件、具名 action 或失败 selector；不得依赖数组顺序决定业务含义。
5. 条件语言必须受限、确定、可静态解析；不得执行 JavaScript、Python、模板表达式或模型输出文本。
6. normalized topology 是派生证据，不替代 Authoring Facts。Runner MAY 使用当前源摘要对应的规范化结果，但必须验证 freshness。

### 43.3 Runner 过滤边界

Runner MUST fail closed：

- 不得遍历 `relations`、`derived_relations`、画布 edges 或 Analyzer 缓存寻找后继。
- 不得执行未知 control kind。
- 不得把 `runtime_effect=false` 的对象解释为控制关系。
- 不得在 Analyzer blocker 存在时通过旧缓存、UI 绿色状态或用户勾选继续。
- 不得根据节点空间位置、连线颜色、字段名或自然语言猜测执行顺序。

## 44. Flow Analyzer

Flow Analyzer 是 v1.0 的规范组件。它读取静态声明，生成规范化拓扑、派生关系和 finding；它不是 Runner，不执行卡带业务代码。

### 44.1 输入与无副作用边界

Analyzer 至少读取 Manifest、Root Flow、Asset Registry、Interaction Component Registry、模型与工具角色、Base capability、目标级别和相关 schema。它 MUST NOT：

- 读取或输出 API key、token、Authorization、私有 URL 明文或本机秘密。
- 调用模型、业务工具、收费接口或产生外部副作用。
- 加载 DLC 业务代码来猜测契约。
- 一边分析一边静默修改 Flow。

连接健康探针是独立、显式授权的预检阶段；其结果可以作为外部 evidence 引用，但不得冒充静态分析。

### 44.2 固定分析阶段

Analyzer MUST 按以下阶段工作，并为每项 finding 标记 stage：

1. `protocol_structure`：协议身份、字段类型、稳定 ID、schema 和引用存在性。
2. `topology`：控制关系规范化、可达性、出口、条件冲突和循环。
3. `dataflow`：producer/consumer、schema、路径、分支确定赋值和覆盖冲突。
4. `resources`：模型、工具、MCP、远程资源、DLC、组件、资产和 Artifact 依赖。
5. `branches`：condition、default、action、Decision consume 和 failure route。
6. `effects`：permission、failure、audit、retry、idempotency、replay 和 fallback。
7. `delivery`：primary output、Artifact revision、目标级别和交付门禁。

早期结构 blocker MAY 降低后续分析置信度，但 Analyzer SHOULD 在安全可行时继续输出独立问题；不得把不完整分析标为完整可信。

### 44.3 Analysis Report v1

```json
{
  "schema": "cartridgeflow.flow_analysis.v1",
  "analysis_id": "analysis_01J00000000000000000000000",
  "analysis_version": "flow-analysis.v1",
  "analyzer": {
    "implementation_id": "example.base.flow-analyzer",
    "implementation_version": "1.0.0"
  },
  "protocol": {
    "id": "CF-FARP",
    "version": "0.8"
  },
  "target": "package",
  "source_digest": "sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
  "normalized_topology": {
    "start": "start",
    "control_edges": []
  },
  "relations": [],
  "findings": [],
  "coverage": {
    "complete": true,
    "stages": ["protocol_structure", "topology", "dataflow", "resources", "branches", "effects", "delivery"]
  },
  "summary": {
    "blockers": 0,
    "warnings": 0,
    "infos": 0,
    "runnable": true,
    "packagable": true,
    "publishable": false
  }
}
```

报告 MUST 包含 schema、analysis identity/version、Analyzer identity/version、协议、target、source digest、normalized topology、relations、findings、coverage 和 summary。时间戳 MAY 用于审计，但不得参与确定性 source digest。

### 44.4 Source Digest

`source_digest` MUST 对影响分析语义的规范化内容计算 SHA-256，至少覆盖 Manifest、Root Flow、引用的 schema、Asset/Component Registry、model/tool/resource role 和目标 Base capability identity。规范化必须定义稳定键顺序、文本编码和路径处理。

密钥、本机凭据值、纯视觉 layout、运行历史和 Analyzer 自己的输出 MUST NOT 进入 digest。任何受覆盖源事实变化都必须使旧报告过期。

### 44.5 分析目标

基础 target 为 `draft | dev | preview | production | package | publish`。同一 finding 可按 target 具有不同阻断级别，但 code 和事实身份不得改变。Base MUST 在报告中记录实际 target，不得用 draft 报告通过 package 或 publish 门禁。

### 44.6 增量分析

Base MAY 对 node、selection 或受影响路径执行增量分析，但最终报告必须与同一源事实、协议、target 下的全量分析在规范语义上等价。局部结果不得被标记为完整 package/publish evidence，除非 Base 已证明未受影响阶段仍对应相同 source digest。

## 45. 派生工程关系

Analyzer MUST 使用统一 relation contract，而不是由不同前端临时猜测。

```json
{
  "id": "relation:data:editorial_ai:editorial:voice_storyboard:editorial",
  "kind": "data",
  "from": {
    "type": "node_output",
    "node_id": "editorial_ai",
    "port": "editorial"
  },
  "to": {
    "type": "node_input",
    "node_id": "voice_storyboard",
    "port": "editorial"
  },
  "derived_from": [
    "states.editorial_ai.outputs.editorial",
    "states.voice_storyboard.inputs.editorial.binding"
  ],
  "confidence": "deterministic",
  "runtime_effect": false
}
```

### 45.1 标准关系类型

基础 kind：

```text
control
branch
action_route
failure_route
data
model_dependency
tool_dependency
mcp_dependency
resource_dependency
artifact_dependency
component_dependency
asset_dependency
policy_dependency
```

`control | branch | action_route | failure_route` 是可执行控制声明的只读投影；其 `runtime_effect=true` 只说明对应源事实会影响运行，不表示 Runner 可以消费 relation 本身。其他关系 MUST 使用 `runtime_effect=false`。

### 45.2 确定性与建议

`confidence` 只允许 `deterministic | suggested`。只有稳定引用、合法 binding 和 schema 证明才能产生 deterministic relation。自然语言或字段相似度只能产生 suggested relation，并同时生成需要作者确认的 finding；suggested relation 不得满足 required dependency 或解除 blocker。

### 45.3 可追溯性

每条 relation MUST 提供稳定 id、kind、from、to、`derived_from`、confidence 和 runtime_effect。`derived_from` 必须定位到当前 Authoring Facts 的字段路径。删除 relation 缓存不得改变运行；修改源字段后相关 relation 必须重算。

## 46. 诊断、门禁与修复

### 46.1 Finding Contract v1

```json
{
  "id": "finding:INPUT_SOURCE_MISSING:voice_storyboard:editorial",
  "severity": "blocker",
  "code": "INPUT_SOURCE_MISSING",
  "stage": "dataflow",
  "node_id": "voice_storyboard",
  "path": "states.voice_storyboard.inputs.editorial.binding",
  "message": "配音与分镜需要 editorial，但尚未绑定数据来源。",
  "expected": "one compatible producer binding",
  "evidence": [],
  "suggested_sources": ["node_output:editorial_ai:editorial"],
  "autofix": {
    "level": "safe",
    "operation": "set_input_binding",
    "arguments": {
      "node_id": "voice_storyboard",
      "input": "editorial",
      "binding": {
        "source": "node_output",
        "node_id": "editorial_ai",
        "output": "editorial"
      }
    }
  }
}
```

每个 finding MUST 包含稳定 id、severity、code、stage、message 和 source path 或 node id。`expected`、evidence、suggested sources 与 autofix 按问题适用性提供。message 是人类说明，自动化只能依赖 code 和结构化字段。

severity 只允许 `blocker | warning | info`。UI 不得把 blocker 降级为绿色状态；Base 不得通过用户勾选修改机器 severity。

### 46.2 最低稳定 Finding Code

v1.0 Base 至少识别并稳定输出：

```text
PROTOCOL_UNSUPPORTED
SOURCE_DIGEST_MISMATCH
ANALYSIS_INCOMPLETE
ANALYSIS_REPORT_STALE
START_NODE_MISSING
CONTROL_TARGET_MISSING
CONTROL_EDGE_KIND_INVALID
CONTROL_EDGE_CONFLICT
TERMINAL_HAS_SUCCESSOR
NODE_UNREACHABLE
NODE_EXIT_MISSING
UNCONTROLLED_CYCLE
INPUT_CONTRACT_MISSING
INPUT_SOURCE_MISSING
INPUT_SOURCE_AMBIGUOUS
INPUT_SCHEMA_INCOMPATIBLE
INPUT_NOT_AVAILABLE_ON_ALL_PATHS
OUTPUT_CONTRACT_MISSING
OUTPUT_IDENTITY_CONFLICT
LEGACY_IO_CONTRACT
MODEL_ROLE_UNDECLARED
MODEL_ROLE_UNBOUND
TOOL_UNDECLARED
TOOL_NOT_ALLOWED
RESOURCE_ROLE_UNBOUND
ASSET_REFERENCE_MISSING
COMPONENT_REFERENCE_MISSING
ACTION_ROUTE_INVALID
BRANCH_DEFAULT_MISSING
FAILURE_POLICY_MISSING
EFFECT_PERMISSION_MISMATCH
RETRY_IDEMPOTENCY_CONFLICT
REPLAY_POLICY_MISSING
FALLBACK_UNDECLARED
PRIMARY_OUTPUT_UNPROVEN
DERIVED_RELATION_IN_CONTROL_GRAPH
```

实现 MAY 增加 code，但不得用一个笼统 code 取代上述可操作身份。跨 Base conformance 只要求事实相同的最低 code 一致，不要求 message、排序或额外建议逐字节相同。

### 46.3 目标门禁

| target | 门禁 |
|---|---|
| `draft` | 允许保存 blocker，但必须保存未完成状态并显示 findings |
| `dev` | 当前运行路径 blocker 必须阻断；mock/fallback 必须显式声明和标记 |
| `preview` | 全部已知限制可见，required 外部资源完成规定预检 |
| `production` | 不依赖编辑器临时修复，不存在协议或交付 blocker |
| `package` | 全量分析完成，source digest 匹配，无 package blocker 或 forbidden content |
| `publish` | package 条件通过，并有权限、安全、资产、认证与审核证据 |

Runner 在创建 Run 前 MUST 至少执行或验证匹配 source digest 的 `dev`/`production` 分析。打包器与发布器 MUST 分别验证相同 target 的完整报告。较高 target 报告 MAY 满足较低 target，前提是协议明确其门禁为严格超集且 source digest 相同；反向替代禁止。

### 46.4 Autofix 分级

autofix `level`：

- `safe`：唯一、确定、可逆，不改变业务路径、不新增权限或外部副作用。
- `confirm`：存在多个合理选择或会改变业务路径、资源、成本或质量。
- `manual`：涉及秘密、权限、收费资源、外部副作用或缺少负责人信息。

Analyzer 只提出修复，不应用修复。Authoring API 应用任何修复后必须产生新 source revision 并重新分析。safe 不等于无审计；所有自动应用操作都必须记录 actor、before digest、operation 和 after digest。

### 46.5 Fallback 可见性

影响内容质量、数据来源、执行器或交付真实性的 fallback MUST 在节点契约中声明 mode、trigger、output guarantee 和 result marker。运行快照必须记录是否使用、原因和实际执行器。工具内部不得把模型失败静默转换为“正常真实成功”。

未声明 fallback 被实际使用时，Run 必须失败或至少不能获得 production delivery success；Analyzer 对可检测的隐藏 fallback 契约缺失输出 `FALLBACK_UNDECLARED`。

## 47. Authoring API 与创作 AI

v1.0 Base 的 dev_authoring 实现 SHOULD 提供三组结构化接口。接口名称可以不同，但行为语义必须可映射。

### 47.1 业务流程操作

```text
create_node
delete_node
rename_node
set_next
set_route
set_action_route
set_failure_route
remove_control_relation
```

### 47.2 执行契约操作

```text
set_input_contract
set_output_contract
set_input_binding
bind_model_role
allow_flow_tool
bind_node_tool
set_permission
set_failure_policy
set_replay_policy
set_fallback_policy
```

### 47.3 分析与修复操作

```text
analyze_flow
analyze_selection
list_findings
explain_relation
propose_fixes
apply_authoring_operation
verify_after_changes
```

Authoring operation MUST 使用稳定对象 identity、结构化参数、expected source revision 或 digest，并原子提交。revision 不匹配时返回 conflict，不得覆盖其他用户或 AI 的新修改。

创作 AI MUST 遵循：理解目标 -> 创建最小业务拓扑 -> 补齐执行契约 -> 分析 -> 修复 blocker -> 复检 -> 向用户展示业务流程与关键关系 -> 运行或打包。AI 不得直接编辑派生 relation、绕过 finding、修改密钥或用自然语言猜测 required binding。

## 48. 从 v0.7 迁移

v0.7 卡带迁移到 v1.0 MUST 生成新 revision 或副本，并至少完成：

1. Runtime Contract、Root Flow、Portable DLC protocol 和 certification target 更新为 v1.0，重新计算所有受影响 hash。
2. 把 `input`、`optional_input`、`output` 和隐藏在 params 中的 Store/Artifact 引用迁移为结构化 `inputs`、`outputs` 与 binding。
3. 为每个输入输出补齐 inline schema 或稳定 schema asset reference。
4. 把顶层 `edges` 分类；只有真实执行关系迁移到 `control_edges`，data/resource/dependency edge 删除并由 Analyzer 重建。
5. 把 `next`、routes、action routes 和 failure routes 规范化检查，解决重复、冲突、悬空目标和循环。
6. 检查每个 required input 在所有可达分支、失败继续、resume 和 rollback 路径上的可用性。
7. 把模型、工具、MCP、远程资源、组件、资产和 Artifact 依赖改为稳定角色或 identity。
8. 显式声明影响业务质量的 fallback；运行结果增加 actual executor、used_fallback 和 reason 证据。
9. 生成 `cartridgeflow.flow_analysis.v1` 报告，修复目标级别 blocker，并保存 source digest evidence。
10. 运行 v1.0 conformance，重新认证；不得沿用 `cf-farp-0-7-certified`。

以下项目不得自动猜测：

- 多个可能 producer 中哪个才是业务来源。
- 字符串 input 中逗号究竟是分隔符还是 key 内容。
- params 内某个字符串是数据绑定、普通文本还是秘密。
- 工程线是否曾被作者误当作控制线。
- 分支缺失数据应使用 default、optional、merge 还是改变业务路径。
- fallback 是否符合产品质量与对外交付承诺。
- 资源、权限、收费接口和外部副作用是否获得授权。

这些项目必须形成 confirm/manual finding，由开发者或负责人明确决定。

## 49. v0.7 条款处置矩阵

| v0.7 内容 | v1.0 位置 | 处置 |
|---|---|---|
| 协议身份、Manifest、资产与 Base Contract | 1-10 | 完整保留并升级为独立 v1.0 快照 |
| `next`、routes 与顶层 `edges` | 10、43、48 | 加强：规范字段改为 typed `control_edges`；旧 `edges` 仅供迁移 |
| Process Node、kind、executor、effect | 11-12 | 完整保留 |
| 字符串 `input`、`optional_input`、`output` | 11、42、48 | 替代：v1.0 作者事实使用结构化 inputs/outputs/binding |
| Store、数据链与 provenance | 13、42、44-45 | 加强：增加 schema 兼容、路径顺序与分支确定赋值 |
| Decision、Consume 与 Pending Interaction | 14-16 | 完整保留；输入输出必须映射结构化端口 |
| Tool Plan、工具、副作用与 replay | 17-23、46 | 完整保留；纳入资源与 policy 静态分析 |
| Artifact、Delivery 与 fallback | 24-27、42、46 | 加强：Artifact 端口结构化，业务 fallback 强制可见 |
| Portable DLC、sandbox、Overlay 与卸载 | 28-31 | 完整保留；descriptor protocol 升级并重新计算 hash |
| compatibility 与 certification | 32-33、44、46 | 加强：必须验证目标匹配且 source digest 新鲜的分析报告 |
| structure/data chain diagnostics | 34、44-46 | 替代并扩展为统一 Flow Analyzer 与 finding contract v1 |
| 前端自行推导工程关系 | 41、45、47 | 废止为权威来源；前端只能消费 Analyzer 投影或过渡兼容结果 |
| v0.7 认证标签 | 3、33、48 | 不沿用；v1.0 必须重新认证 |

本矩阵是覆盖审计，不表示 v1.0 Runner 可以直接解释 v0.7 卡带。迁移必须生成 v1.0 Authoring Facts、全量分析报告、新 hash 和新认证证据。

## 50. 统一 Flow 资源目录

v1.0 Base MUST 为每个 Flow 生成唯一的只读资源解析结果 `cartridgeflow.flow_resource_catalog.v1`。工具管理、模型管理、Analyzer、运行预检、Runner snapshot 和打包预检 MUST 消费同一目录，不得分别从本机配置、Manifest 或节点字段自行拼接另一套事实。

目录构建 MUST 同时读取以下六层事实：

1. Base 内置工具注册表。
2. 本机 MCP、API 与插件资源注册表。
3. 当前卡带已校验的 Portable DLC descriptor。
4. Manifest 的工具和模型需求声明。
5. 当前 Flow 的本机资源与模型连接绑定。
6. Root Flow 具体节点的工具引用与模型连接绑定。

每个工具目录项 MUST 包含稳定 `id`、真实 `resource_id`、`source`、owner、server/tool、availability、Manifest requirement、Flow binding、node references 和 status。`source` 只能是：

```text
base_builtin
local_resource
cartridge_dlc
```

`base_builtin` 表示实现与生命周期属于 Base；`local_resource` 表示连接配置和秘密属于当前机器；`cartridge_dlc` 表示实现与生命周期属于当前卡带包。Portable DLC 工具即使通过 Base 的隔离 worker 执行，也 MUST 标记为 `cartridge_dlc`，不得投影或展示为 `builtin:<server>/<tool>`。Manifest requirement 只声明需求，不等于资源已经存在或已绑定。

目录至少返回：

```json
{
  "schema": "cartridgeflow.flow_resource_catalog.v1",
  "cartridge_id": "example.flow",
  "tools": [
    {
      "id": "fetch_news",
      "resource_id": "dlc:news.media:media/fetch_rss",
      "source": "cartridge_dlc",
      "owner": "news.media",
      "manifest_requirement": {"declared": true, "required": true},
      "flow_binding": {"bound": true, "status": "bound"},
      "node_references": ["fetch_news"],
      "status": "ready"
    }
  ],
  "models": {},
  "findings": [],
  "summary": {"tools": 1, "ready": 1, "referenced": 1, "blockers": 0}
}
```

被节点引用但未在 Manifest 声明的工具 MUST 产生 `NODE_TOOL_NOT_DECLARED` blocker。Manifest required tool 没有可用来源时 MUST 产生 `TOOL_RESOURCE_UNRESOLVED` blocker。被节点引用的本机资源尚未进入 Flow 时 MUST 产生 `NODE_TOOL_RESOURCE_NOT_BOUND` blocker。Runner MUST 在执行任何业务代码前阻断这些 finding，并把成功解析的目录写入 Run snapshot。

### 50.1 运行模型绑定

模型运行绑定 MUST 遵循两个连续步骤：

```text
本机模型连接进入 Flow
-> 每个 AI Decision 节点从当前 Flow 的连接中明确选择一个连接和模型
```

Manifest `llm_recipe.roles` 声明卡带运行所需的模型角色与能力，不保存本机 Provider，也不代表节点已经完成绑定。仅有 Flow role binding 不能使节点可运行；每个 AI Decision 节点 MUST 存在显式 node binding，且其 Provider MUST 已进入当前 Flow。预检缺失时返回 blocker，Runner 不得继承全局默认连接、不得只按角色静默选择 Provider、不得在节点连接失效时回退到另一连接。

模型 API 缺失、不可用或调用失败时，除非节点存在符合第 26 和 46 节的显式 fallback contract，否则 Run MUST 失败。离线生成结果、全局默认模型或 AI 管家连接不得冒充该节点的真实运行结果。

### 50.2 Authoring 与 Mentor 模型隔离

AI 管家、创作 AI、协议解释器和 mentor 使用的模型属于 Base `authoring` scope。它们 MUST 通过独立的 authoring resource binding 管理，不得自动追加到卡带 `llm_recipe.roles`，不得计入卡带运行模型就绪状态，也不得被 Runner 当作业务节点 fallback。

卡带在 `llm_recipe.roles` 中声明 `authoring` 或 `mentor` 时，Analyzer 或运行预检 MUST 返回 `AUTHORING_MODEL_SCOPE_LEAK` blocker。Authoring 调用的审计记录必须标记 scope、实际 Provider 与 model，但不得把秘密或本机连接配置写回 Manifest、Flow 或可移植包。

---

# 第二部分：MCP/DLC 透明执行合同

以下条款是 v1.0 的组成部分，不是对其他协议文件的引用。它补充第一部分的工具、资源、分析、运行和认证语义。
# CartridgeFlow Flow Authoring Runtime 协议 v1.0

协议编号：`CF-FARP-1.0`

协议状态：active

发布状态：完整正文

依赖宿主契约：`CARTRIDGEFLOW-BASE@0.2`

替代版本：`CF-FARP@0.8`

关系：本文完整替代 v0.8，是独立、自包含的 Flow 创作、静态分析、运行与 MCP/DLC 透明执行规范。实现或认证 v1.0 不得依赖历史正文补足含义。v0.8 已发布语义保持只读；旧卡带和旧 DLC 工具通过兼容层运行时必须诚实标记为 `legacy_opaque`，不得静默迁移或冒充 v1.0 透明认证。

---

## 目录

1. [协议目标](#1-协议目标)
2. [继承边界](#2-继承边界)
3. [MCP/DLC 透明执行原则](#3-mcpdlc-透明执行原则)
4. [Profile 与 Capability](#4-profile-与-capability)
5. [透明度等级](#5-透明度等级)
6. [Portable DLC descriptor v3](#6-portable-dlc-descriptor-v3)
7. [MCP Python source format v1](#7-mcp-python-source-format-v1)
8. [静态源码模型](#8-静态源码模型)
9. [静态检查与拒绝规则](#9-静态检查与拒绝规则)
10. [结构化编辑](#10-结构化编辑)
11. [Analyzer 与资源目录](#11-analyzer-与资源目录)
12. [运行时与能力 Broker](#12-运行时与能力-broker)
13. [运行事件](#13-运行事件)
14. [前端画布表达](#14-前端画布表达)
15. [检查器与源码定位](#15-检查器与源码定位)
16. [兼容性与认证门禁](#16-兼容性与认证门禁)
17. [dev.ai-tech-daily 迁移要求](#17-devai-tech-daily-迁移要求)
18. [API 要求](#18-api-要求)
19. [测试计划](#19-测试计划)
20. [完成标准](#20-完成标准)
21. [禁止事项](#21-禁止事项)
22. [定稿前治理决策](#22-定稿前治理决策)

## 1. 协议目标

CF-FARP v1.0 在 v0.8 的 Flow 创作、结构化 I/O、Analyzer、typed control、fallback、Portable DLC 隔离和资源目录基础上，新增 MCP/DLC 工具内部透明执行要求。目标是防止 Root Flow 退化为一个 Python 应用启动图：画布必须拥有业务编排，Python 只能实现原子操作。

本协议要求：

- MCP 节点可以折叠为外层工具节点，也可以展开为内部 operation graph。
- 展开图、Python source model 和运行 stage trace 使用相同稳定 operation id。
- 每个可认证的本地 DLC MCP 节点对应唯一 Python 入口文件。
- fallback、重试、质量判断、资源访问、子进程和 Artifact 创建必须可见。
- 外部能力通过 Base broker 授权执行，不由 DLC 代码直接绕过。
- 无法披露或验证内部过程的远程 MCP 必须显示为黑盒。

## 2. 继承边界

v1.0 完整保留 v0.8 的以下语义，但不要求阅读 v0.8 正文才能实现本文：

- Manifest、Root Flow、业务节点、结构化 `inputs` / `outputs` / `binding`。
- `control_edges` 与 Runner 可执行拓扑过滤。
- `cartridgeflow.flow_analysis.v1`、source digest、target gates 和 finding contract。
- Decision Envelope、Decision Consume、Pending Interaction、Artifact、Checkpoint 和 runtime error envelope。
- Portable DLC 的卡带所有权、作用域隔离、Worker 生命周期、前端 sandbox 和卸载。
- 影响业务质量的 fallback 必须声明并记录实际使用。

v1.0 新增的约束只扩展 MCP/DLC 工具内部可观察性，不允许用新语义重写 v0.8 卡带。旧工具按旧协议运行时，其透明度必须为 `legacy_opaque`。

## 3. MCP/DLC 透明执行原则

1. 画布拥有业务编排。分阶段处理、条件分支、fallback、人工确认和副作用顺序必须存在于可分析声明中。
2. Python 只实现原子操作。RSS 解析、图片生成、编码调用可以在 Python 中实现，但跨阶段业务拓扑不得隐藏在函数体。
3. 一个 MCP 画布节点对应一个 Python 入口文件。禁止多个 MCP 节点共享大型 dispatcher。
4. 展开图必须是执行契约。前端不得根据函数名、注释或自然语言猜测内部流程。
5. 源码解析不得执行卡带代码。Base 只能静态解析受限格式。
6. 声明、实现和运行 trace 必须共享稳定 operation id。
7. 网络、文件、Artifact、secret 和子进程能力必须经过 Base broker。
8. 黑盒必须诚实显示。不能披露的远程 MCP 使用 `opaque` 或 `contract_only`。

## 4. Profile 与 Capability

v1.0 新增必选 Profile：

```text
tool_transparency
```

v1.0 新增能力：

```text
mcp_node_source_format_v1
mcp_node_file_identity
mcp_source_static_parse
mcp_source_model_v1
compound_tool_operation_graph
tool_stage_trace_v1
tool_source_provenance
explicit_fallback_policy
host_capability_broker
opaque_tool_visibility_guard
mcp_graph_authoring_operations
mcp_source_digest_guard
portable_dlc_descriptor_v3
tool_resource_catalog_v2
```

声明 `CF-FARP@1.0` 的卡带必须在 `runtime_contract.required_profiles` 中包含 `tool_transparency`，并要求与其透明度等级匹配的能力。Base 只有在 `BASE_IMPLEMENTATION.json` 与 conformance evidence 同时声明时，才可以运行或认证 v1.0。

## 5. 透明度等级

每个工具资源必须投影一个透明度等级：

| 等级 | 含义 | v1.0 规则 |
|---|---|---|
| `atomic` | 一个原子能力，没有隐藏业务拓扑 | 可显示单 operation、源码和运行事件 |
| `declared_graph` | 多个阶段组成的复合能力 | 必须提供可解析 operation graph |
| `contract_only` | 只知道接口、effect 和资源契约 | 只允许真正原子的远程调用 |
| `opaque` | 无法披露或验证内部过程 | UI 必须显示黑盒；有副作用的复合工具不能透明认证 |
| `legacy_opaque` | v0.8 或旧格式兼容工具 | 可兼容运行，不能取得 v1.0 透明认证 |

## 6. Portable DLC descriptor v3

v1.0 DLC descriptor 使用：

```json
{
  "schema": "cartridgeflow.portable_dlc.v3",
  "id": "example.media",
  "version": "1.0.0",
  "owner_cartridge": "example.media.cartridge",
  "scope": "cartridge",
  "tools": [
    {
      "node_id": "fetch_news",
      "server": "media",
      "tool": "fetch_rss",
      "handler": "run",
      "effect": "read_only",
      "description": "Fetch and normalize feeds.",
      "timeout_ms": 30000,
      "implementation": {
        "language": "python",
        "format": "cartridgeflow.mcp_python.v1",
        "entry": "dlc/mcp_nodes/fetch_news.py"
      },
      "transparency": "declared_graph",
      "source_digest": "sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    }
  ],
  "files": []
}
```

规则：

- `node_id` 与 Root Flow MCP 节点、Manifest tool、descriptor tool 和 Python `MCP_NODE.node_id` 必须一致。
- `implementation.entry` 必须是包内相对路径，且位于 `dlc/mcp_nodes/`。
- 一个入口文件只能声明一个 `MCP_NODE`。
- `dlc/backend/entry.py:invoke` 这类多工具动态 dispatcher 不得通过 v1.0 透明认证。
- 远程 MCP 没有本地 source 时使用 `contract_only` 或 `opaque`，并说明 provider identity 与不可披露原因。

## 7. MCP Python source format v1

新增源码格式：

```text
cartridgeflow.mcp_python.v1
```

文件顺序必须固定：

1. UTF-8 module docstring。
2. 允许的 import。
3. 静态 `MCP_NODE` 字面量。
4. 输入输出类型声明。
5. 使用 `@mcp_operation` 装饰的 operation 函数。
6. 静态 `OPERATIONS` 映射。
7. 标准 `run(ctx, inputs)`。

示例：

```python
"""Fetch and normalize technology RSS feeds."""

from cartridgeflow_dlc import McpContext, mcp_operation


MCP_NODE = {
    "schema": "cartridgeflow.mcp_python.v1",
    "node_id": "fetch_news",
    "server": "media",
    "tool": "fetch_rss",
    "effect": "read_only",
    "inputs": {"feed_set": {"type": "string"}},
    "outputs": {"candidates": {"type": "object"}},
    "operations": [
        {"id": "resolve_feeds", "kind": "transform"},
        {"id": "download_feeds", "kind": "network", "capability": "network.fetch"},
        {"id": "parse_feeds", "kind": "transform"}
    ],
    "edges": [
        {"from": "resolve_feeds", "to": "download_feeds", "kind": "control"},
        {"from": "download_feeds", "to": "parse_feeds", "kind": "control"}
    ],
    "fallbacks": [
        {
            "id": "download_transport_fallback",
            "from": "download_feeds",
            "on": ["network_transport_failed"],
            "mode": "explicit",
            "visible": True
        }
    ]
}


@mcp_operation("resolve_feeds")
def op_resolve_feeds(ctx: McpContext, data: dict) -> dict:
    return {"feeds": ctx.inputs.resolve_feed_set(data["feed_set"])}


@mcp_operation("download_feeds")
def op_download_feeds(ctx: McpContext, data: dict) -> dict:
    return {"responses": ctx.network.fetch_many(data["feeds"])}


@mcp_operation("parse_feeds")
def op_parse_feeds(ctx: McpContext, data: dict) -> dict:
    return {"candidates": parse_rss_or_atom(data["responses"])}


OPERATIONS = {
    "resolve_feeds": op_resolve_feeds,
    "download_feeds": op_download_feeds,
    "parse_feeds": op_parse_feeds
}


def run(ctx: McpContext, inputs: dict) -> dict:
    return ctx.run_declared_graph(MCP_NODE, OPERATIONS, inputs)
```

`MCP_NODE`、operation id、edges、fallbacks 和 schema 必须是静态字面量。operation 函数名称必须为 `op_<operation_id>`。`run()` 只能调用 `ctx.run_declared_graph(...)`，不得包含业务分支、循环、网络、文件、subprocess 或 fallback。

## 8. 静态源码模型

Base parser 必须输出：

```json
{
  "schema": "cartridgeflow.mcp_source_model.v1",
  "node_id": "fetch_news",
  "tool_identity": "media/fetch_rss",
  "format": "cartridgeflow.mcp_python.v1",
  "source": {
    "path": "dlc/mcp_nodes/fetch_news.py",
    "sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
    "line_count": 210
  },
  "operations": [],
  "edges": [],
  "data_relations": [],
  "fallbacks": [],
  "capabilities": [],
  "source_map": {},
  "findings": [],
  "source_digest": "sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
}
```

`source_map` 必须把 operation、edge、schema、fallback 和 capability 定位到文件、symbol、开始行和结束行。前端点击内部节点时只能消费该映射，不得全文搜索或猜测。

## 9. 静态检查与拒绝规则

解析器属于 Base 后端。它使用 `ast.parse` 和可保留格式的 CST 工具进行静态解析，不得 import DLC 模块。

至少检查：

- 一个文件只有一个 `MCP_NODE`。
- node id、server/tool 与 Root Flow、Manifest 和 descriptor 一致。
- `MCP_NODE.operations`、`@mcp_operation` 与 `OPERATIONS` 一一闭合。
- 每个 operation 输入均由边界输入或上游输出提供。
- fallback 显式声明，不形成隐藏控制路径。
- `run()` 是标准 graph runner 调用。
- 禁止 `eval`、`exec`、动态 import、monkey patch 和运行时注册工具。
- 禁止直接使用 `urllib`、`requests`、socket、`open`、任意 `Path` 写入和 `subprocess` 执行受控能力。
- 允许的纯计算 import、SDK import 和已声明 `dlc/lib` 依赖必须可追踪。
- 源码 hash、descriptor hash 和分析 digest 必须一致。
- 无法解释的控制流标记为 `MCP_SOURCE_OPAQUE_CONTROL_FLOW`。

静态解析器不是安全沙箱。它负责格式、证据和 authoring；运行时安全仍由 broker、Worker 隔离和操作系统策略负责。

## 10. 结构化编辑

前端不得拼接 Python 字符串来修改 operation graph。修改流程：

1. 前端提交结构化 authoring operation。
2. 请求携带当前 `source_digest`。
3. 后端验证 revision、权限和 graph 合法性。
4. CST 重写器只修改 `MCP_NODE`、operation stub 或允许的 decorator 区域。
5. 修改后重新 parse、analyze 和计算 hash。
6. 任一环节失败则原文件保持不变。

第一阶段只支持修改 operation 元数据、连线、schema、fallback 和生成新 operation stub。函数体自由编辑由源码编辑器完成，保存后必须重新解析。

## 11. Analyzer 与资源目录

Flow Analyzer 必须把 source model 纳入 source digest。operation graph 形成独立 `tool_internal` scope，不能污染 Root Flow 的可执行控制边。工程关系新增：

```text
tool_operation
capability_dependency
source_implementation
fallback_route
observed_operation
```

统一资源目录升级为：

```text
cartridgeflow.flow_resource_catalog.v2
```

目录项必须增加透明度、入口文件、operation 数量、source digest、parse status 和 broker capabilities。declared graph 与 observed trace 不一致时必须生成稳定 finding。

## 12. 运行时与能力 Broker

Worker 协议从单次输入输出升级为 operation event 流。Worker 只加载当前节点对应文件，不导入整张卡带的通用 dispatcher。

DLC 代码访问受控能力时必须通过：

```text
ctx.network
ctx.artifacts
ctx.process
ctx.secrets
ctx.files
```

broker 在调用前检查 node、operation、permission、effect、参数、目标和 run scope。operation 超时、取消和崩溃必须定位到 operation id，而不仅是外层 MCP node。

## 13. 运行事件

v1.0 新增工具阶段事件：

```text
tool_call_started
tool_operation_started
tool_operation_progress
resource_access_requested
resource_access_completed
fallback_selected
artifact_created
tool_operation_completed
tool_operation_failed
tool_call_completed
```

事件必须携带 `run_id`、`node_id`、`tool_call_id`、`operation_id`、`attempt`、`effect`、时间、输入输出摘要、source digest 和 error identity。敏感值只保存脱敏摘要。

## 14. 前端画布表达

MCP 节点折叠状态必须显示 source、server/tool、版本、owner、transparency、effect、permission、timeout、operation 数量、parse 状态、digest 状态和运行健康状态。

展开状态必须使用明确 MCP 边界容器。Root Flow 连线只连接外层边界端口；内部 operation 使用独立小节点和端口。数据流、控制流、资源依赖、fallback 和失败路径使用不同线型。展开或折叠只改变视图，不改变执行语义。

`opaque` 和 `legacy_opaque` 只能显示黑盒边界、已知契约和不可观测原因，禁止生成推测节点。

## 15. 检查器与源码定位

检查器至少包含：

- `契约`：输入输出、effect、permission、timeout、retry。
- `内部流程`：operation graph、数据映射、fallback。
- `运行轨迹`：declared 与 observed 对比、attempt、进度和错误。
- `源码`：当前 operation 对应源码范围和 digest。
- `安全`：broker capability、资源目标、网络域、子进程和 findings。

点击 operation 必须联动 source map、当前运行事件和数据摘要。长参数、输出和错误使用展开查看，不得堆满节点卡片。

## 16. 兼容性与认证门禁

发布和运行前必须验证：

- Root Flow node、Manifest tool、descriptor tool 和 Python `MCP_NODE` 身份一致。
- source model 不含 blocker。
- graph source digest 未过期。
- 声明 effect 不低于所有 operation 的最大 effect。
- 每个受控能力都有 permission 和 broker capability。
- fallback、retry、compensation 和 replay policy 没有隐藏路径。
- v1.0 compound tool 不得是 `legacy_opaque`。

`legacy_opaque` 可以在兼容模式运行，但不能取得 v1.0 透明认证。

## 17. dev.ai-tech-daily 迁移要求

`dev.ai-tech-daily` 不得继续用多工具 `dlc/backend/entry.py` dispatcher 取得 v1.0 认证。目标结构：

```text
dlc/mcp_nodes/fetch_news.py
dlc/mcp_nodes/voice_storyboard.py
dlc/mcp_nodes/assemble_video.py
dlc/lib/
```

`fetch_news` 必须显式展示 feed 解析、下载、清洗、去重、排序、限制和 RSS 空结果失败出口。`voice_storyboard` 必须显式展示编辑稿校验、口播策略、语音合成、换音色 fallback、分镜渲染和媒体工程写入。`assemble_video` 必须显式展示音频探测、时长策略、字幕、编码、视频探测、质量门禁和交付 Artifact。

## 18. API 要求

Lite 白名单应新增：

```text
GET   /api/lab/flows/{flow_id}/mcp-nodes/{node_id}/source-model
GET   /api/lab/flows/{flow_id}/mcp-nodes/{node_id}/source
PATCH /api/lab/flows/{flow_id}/mcp-nodes/{node_id}/operation-graph
POST  /api/lab/flows/{flow_id}/mcp-nodes/{node_id}/operations
GET   /api/runs/{run_id}/tool-calls/{tool_call_id}/trace
```

源码接口只允许读取 descriptor 已声明、hash 匹配且位于当前卡带包内的文件。PATCH 必须携带 expected source digest，冲突返回 409。

## 19. 测试计划

Parser 测试必须覆盖静态提取、拒绝动态声明、不 import DLC、source map 行号、digest 稳定、直接能力调用检测和 CST 修改原子性。

协议与后端测试必须覆盖身份不一致、`legacy_opaque` 兼容但不可认证、缺失 graph/fallback/broker capability、source digest 过期、未声明网络/文件/subprocess 调用、stage event 与 operation 关联。

前端 E2E 必须覆盖折叠/展开不改变外层布局、内部图与 source model 一致、operation 定位源码和运行事件、结构化编辑冲突、fallback 高亮、opaque 黑盒展示、100%/125% 缩放和窄屏无溢出。

## 20. 完成标准

v1.0 MCP 透明执行只有同时满足以下条件才算落地：

- 每个开发卡带 MCP 节点都有唯一 Python 入口文件。
- Base 不再依赖多工具大型 dispatcher 作为透明工具。
- 所有 composite 工具均可在画布展开真实 operation graph。
- 展开图、source model 和 stage trace 使用同一 operation identity。
- 用户可以看到每个 fallback、资源访问、子进程、Artifact 和失败位置。
- graph 修改真实改变执行契约。
- 未声明能力或隐藏业务控制流阻止 v1.0 发布认证。
- 远程 opaque MCP 被诚实标记。
- v0.8 历史协议、既有卡带和资源目录语义保持兼容。
- 完整 conformance、前端构建、Parser 测试和 Playwright E2E 全部通过。

## 21. 禁止事项

- 不得把每一行 Python 自动伪装成流程节点。
- 不得还原任意第三方动态 Python、闭包、反射或 monkey patch。
- 不得要求远程 MCP 服务公开商业源码；无法公开时必须标为黑盒。
- 不得让前端 import、解释或执行 Python。
- 不得把特定 RSS、视频、媒体或其他业务逻辑写入 Base。
- 不得用函数名、注释或自然语言生成推测内部图。
- 不得将 v0.8 卡带静默标记为 v1.0。

## 22. 定稿前治理决策

以下决策必须在实现完整认证前形成明确结论：

1. `source format v1` 只支持 Python，还是同时预留 TypeScript。
2. 结构化编辑是否允许自动生成 operation 函数 stub。
3. 远程 MCP 的 `contract_only` 认证是否限制为 `none/read_only` 原子工具。
4. DLC Worker 的 OS sandbox 在 Windows、macOS 和 Linux 上分别采用什么实现。
5. 行数门禁采用固定阈值、复杂度阈值还是组合策略。
6. operation graph 布局保存到卡带 authoring metadata，还是用户本地视图状态。
7. graph 与源码不一致时，开发运行完全阻止，还是允许一次明确风险诊断运行。

---

# 第三部分：显式执行计划与令牌运行合同

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

## 55. 与历史版本的迁移边界

从 0.8 或 0.9 迁移到 1.0 是显式创作操作：将旧控制事实转换为执行计划、补齐失败边、重新编译、重新分析、重新做资源预检并重新认证。历史卡带继续按各自协议运行；运行器、前端和 AI 不得在保存、打开或运行时静默升级它们。

## 56. 1.0 完成门槛

只有下列证据全部存在时，登记表才能将 1.0 从 `draft/unsupported` 改为 `active/supported`，并作为默认新建流程协议：

- 本文三部分完整且独立，不引用历史正文补足语义。
- 1.0 词表包含 0.8、0.9 的完整并集及执行计划扩展，并且每项有 Base 证据。
- 清单校验、兼容性、认证、分析器、默认新建流程、运行器、检查点恢复与前端工程投影都走 1.0 真正路径。
- 成功、失败、取消、分叉、三种汇合、循环、批次、三种等待、持久化、恢复、摘要不匹配和副作用重放保护均有正反测试。
- 全量一致性、协议治理审计、构建和静态差异检查通过。
