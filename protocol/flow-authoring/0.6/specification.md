# CartridgeFlow Flow Authoring Runtime Protocol v0.6

协议编号：`CF-FARP-0.6`

协议状态：active

发布状态：完整正文

依赖宿主契约：`CARTRIDGEFLOW-BASE@0.2`

关系：本文是独立、自包含的 Flow 搭建与运行规范。实现或认证 v0.6 不需要读取历史 CF-FARP 正文。卡带领域语义由卡带自己的 schema 与 Portable DLC 提供，不属于本协议。

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
11. [Process Node](#11-process-node)
12. [Kind 约束](#12-kind-约束)
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
35. [从 v0.5 迁移](#35-从-v05-迁移)
36. [禁止事项](#36-禁止事项)
37. [最小一致性清单](#37-最小一致性清单)
38. [完整示例](#38-完整示例)
39. [v0.5 条款处置矩阵](#39-v05-条款处置矩阵)
40. [规范追踪与演进](#40-规范追踪与演进)

## 1. 协议目标

CF-FARP v0.6 规定：

- 卡带 Manifest 与 Root Flow 的可移植声明。
- 统一 Process Node 语义。
- AI Decision Envelope 与显式消费投影。
- 工具计划、权限、副作用和本机资源绑定。
- 用户交互暂停与恢复。
- 稳定错误身份、检查点、重试、回滚和重放保护。
- Artifact、Delivery、测试台和认证。
- Portable DLC 的作用域、隔离和卸载行为。

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
CF-FARP@0.6
```

认证标签：

```text
cf-farp-0-6-certified
```

规则：

1. v0.6 是完整快照，不从 v0.5 继承隐含语义。
2. 已按其他版本认证的卡带不得使用 v0.6 标签。
3. Base 只有在 `supported_protocols` 中声明 v0.6 时才能运行该卡带。
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
| Store | 单次运行的结构化数据总线 |
| Tool | 有 schema、副作用和失败契约的能力 |
| Resource Role | 卡带对本机模型、工具或数据源的抽象需求 |
| Decision Envelope | AI 决策的结构化输出 |
| Pending Interaction | 暂停等待用户时的可恢复请求 |
| Checkpoint | 节点前后持久化的运行快照 |
| Artifact | 带身份、来源和 revision 的运行产物 |
| Delivery | 最终交付视图与主要输出 |
| Portable DLC | 卡带拥有的后端、前端、协议和 workflow 扩展 |

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

Process Node 是统一业务节点。`kind` 表示做什么，`executor` 表示由谁执行，`effect` 表示会改变什么。三者必须与真实行为一致。

### 4.7 Store

Store 是单次 Run 内的结构化数据总线。节点只读声明的 input，只写声明的 output 和协议允许的审计字段。Store 不是大文件仓库，也不是跨 Run 的隐式全局状态。

### 4.8 Tool

Tool 是带输入 schema、输出 schema、副作用、幂等性、超时和失败策略的可调用能力。工具可以由 Base、MCP、远程 API 或 Cartridge DLC 提供，但必须通过 Manifest 身份和节点 allowlist 被引用。

### 4.9 Resource Role

Resource Role 是卡带对本机能力实例的稳定抽象需求。卡带声明角色和约束；Base 在本地绑定 URL、key、command、路径或 Provider。角色名称不得暗含只在某台机器成立的连接信息。

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

## 5. 卡带包结构

最小包：

```text
cartridge/
  manifest.json
  root.flow.json
```

完整包 MAY 包含：

```text
cartridge/
  manifest.json
  root.flow.json
  assets/
  prompts/
  schemas/
  tests/
  dlc/
    descriptor.json
    backend/
    frontend/
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

## 6. Manifest 契约

最小 v0.6 Manifest：

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
    "protocol_version": "0.6",
    "required_profiles": ["runtime_core"],
    "recommended_profiles": [],
    "required_capabilities": ["root_flow_execution"],
    "optional_capabilities": [],
    "required_tools": [],
    "optional_tools": []
  },
  "delivery_readiness": {
    "level": "dev",
    "runnable": true
  },
  "inputs": [],
  "outputs": [],
  "mcp_tools": []
}
```

规则：

1. `id` 与 `version` MUST 稳定。
2. `base_contract` MUST 指向 `CARTRIDGEFLOW-BASE@0.2` 或 Base 明确支持的后续兼容版本。
3. `runtime_contract` MUST 指向 `CF-FARP@0.6`。
4. `base_contract` 和 `runtime_contract` 是不同契约，版本不得要求相等。
5. `required_*` 缺失必须阻断；`optional_*` 缺失形成可见降级。
6. Manifest MAY 包含 `publisher`、`branding`、`permissions`、`dependencies`、`environment`、`llm_recipe`、`resource_requirements`、`artifacts`、`delivery`、`protocol_extensions` 和 `portable_dlc`。

### 6.1 字段分组

| 分组 | 必需字段 | 作用 |
|---|---|---|
| 身份 | `schema_version`、`id`、`name`、`version`、`kind`、`category` | 标识可分发卡带 |
| 入口 | `root_flow`、`runtime` | 定位 Root Flow 与运行适配器 |
| 契约 | `base_contract`、`runtime_contract` | 声明宿主与 Flow 协议要求 |
| 交付 | `delivery_readiness`、`inputs`、`outputs` | 声明运行阶段与公开 I/O |
| 能力 | `mcp_tools`、可选 `llm_recipe`、`resource_requirements` | 声明模型、工具和本机资源角色 |
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
      "schema": "schemas/request.schema.json"
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
    "version": "0.6"
  },
  "start": "start",
  "states": {},
  "edges": []
}
```

规则：

1. `states` MUST 是非空对象。
2. `start` MUST 指向存在节点。
3. 生命周期节点 MAY 使用 `type=system | terminal`。
4. 业务节点 MUST 使用 `type=process`。
5. `next` 与 `edges` 重复边必须去重，冲突边必须阻断。
6. 从 start 不可达的节点必须显式标记 isolated/experimental，否则是结构问题。
7. Flow MUST 可静态分析，不得靠运行时猜测生成主拓扑。

### 10.1 拓扑来源

Root Flow MAY 使用节点 `next`、结构化 `routes` 或顶层 `edges` 表达边。Base 必须规范化为同一原子图：

1. 相同 source/target/condition 的重复边去重。
2. 相同 route 条件指向不同 target 是 blocker。
3. 指向不存在节点的边是 blocker。
4. 无 start 可达路径的业务节点必须标记 `isolated=true` 或 `experimental=true`。
5. 循环 MUST 显式声明退出条件、最大迭代或由专用循环 capability 承载。

顶层 edge 最小结构：

```json
{
  "from": "validate",
  "to": "deliver",
  "condition": "store:validation.passed == true"
}
```

条件表达式必须来自 Base 声明的受限表达式语言，不得执行任意代码。

### 10.2 生命周期节点

- `type=system` MAY 用于 start、checkpoint 或受控系统事件。
- `type=terminal` 表示路径终止，不执行隐藏业务逻辑。
- 生命周期节点不得伪装成工具、LLM 或持久写入节点。
- 一个 Flow MAY 有多个 terminal，但每条可成功路径必须到达明确终态。

### 10.3 图分析

静态分析至少检查 start、缺失节点、不可达节点、无出口节点、冲突边、未受控循环、数据链来源和副作用路径。分析发现与运行事件必须使用稳定 node id。

## 11. Process Node

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
mcp_read mcp_execute remote_call gate ui human_gate delivery
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

### 11.1 通用字段

| 字段 | 语义 |
|---|---|
| `id` | 来自 states key 的稳定节点身份 |
| `type` | 业务节点固定为 process |
| `kind` | 业务语义分类 |
| `executor` | 实际执行主体 |
| `effect` | 最大副作用级别 |
| `input` | required Store 输入 |
| `optional_input` | 缺失不阻断的输入 |
| `output` | 主要 Store 输出 |
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

`input` 和 `optional_input` MAY 使用字符串、逗号/换行分隔字符串或字符串数组。Base 必须规范化、去重并保持声明顺序。空值不得成为 Store key。

节点写多个输出时 SHOULD 使用结构化 output map 或单一对象 output。不得依赖执行器根据返回字段名临时发明 Store key。

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

UI MAY 使用“输入节点”“AI 决策节点”“MCP 读取节点”“远程执行节点”“交付节点”等友好名称，也可以使用领域名称。但开发者详情中必须显示 kind、executor、effect、tool/resource binding 和 permission。

不得把所有 Process Node 都显示为模糊“处理节点”，也不得用显示标签反向推导协议字段。

## 12. Kind 约束

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

### 12.9 ui

- 只负责展示或收集声明输入
- 不得绕过 Runner 修改已提交运行状态

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

当 decision 或 human gate 等待用户时，Base MUST：

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

UI 中选择按钮不等于提交。只有 answer API 或等价受控命令可以恢复运行。

### 16.1 Interaction 记录

```json
{
  "schema": "cartridgeflow.pending_interaction.v1",
  "interaction_id": "interaction_...",
  "run_id": "run_...",
  "node_id": "review_plan",
  "status": "waiting_user",
  "question": {
    "id": "approval",
    "prompt": "是否批准当前方案？",
    "input_schema": {"type": "boolean"},
    "store_key": "plan_approval"
  },
  "resume": {"policy": "resume_same_node"},
  "created_at": "...",
  "answered_at": null,
  "answer_revision": 0
}
```

Interaction MUST 持久化到 run-scoped 状态，并能在页面刷新或 Base 重启后读取。

### 16.2 生命周期

```text
waiting_user -> answered | cancelled | expired
```

只有 waiting_user 可以接受首次答案。重复提交必须通过 idempotency key 返回原结果或稳定冲突，不得重复恢复 Run。修改已回答内容必须创建新 answer revision 和明确的回滚/重新审批语义。

### 16.3 Resume Policy

- `resume_same_node`：将答案写入 store_key，重新执行当前节点。
- `resume_next_node`：当前节点契约已满足时，从其后续节点继续。
- `resume_target_node`：跳转到声明且可达的 target_node。
- `restart_run_with_inputs`：使用原始输入和答案创建新的 Run 语义。

Policy 不得绕过尚未满足的 gate、permission 或 required input。目标节点不存在或不可达时必须阻断。

### 16.4 Answer Routes

human gate MAY 声明按结构化答案进入目标、回滚或拒绝。路由必须静态枚举并校验答案 schema。前端只能提交答案，不能直接指定未经契约允许的目标节点。

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

探针范围 MUST 保留原子图拓扑。seeded 数据必须标记，探针通过不等于全流程通过或协议认证。

### 27.1 全流程测试

全流程模式从真实 start 开始，不接受 probe seed，不跳过 required gate，并按声明的 live/mock/tool mode 执行到终态。失败必须保留完整事件、错误和 checkpoint。

### 27.2 探针范围

探针起点和终点必须是合法节点，范围内边来自原子图。范围外 input 可 seeded，但每个 seed 必须通过目标 schema。探针不得通过重连边改变原流程语义。

### 27.3 可观察性

测试台至少展示 execution mode、节点 input/output、Store revision、Decision Envelope、consume path/as/value summary、tool plan、tool call、effect、permission、error、checkpoint、Artifact 和 Delivery。

## 28. Portable DLC

携带 DLC 的 Manifest：

```json
{
  "portable_dlc": {
    "protocol": "CF-FARP@0.6",
    "descriptor": "dlc/descriptor.json",
    "activation": "manifest_scoped"
  }
}
```

Descriptor 使用 `cartridgeflow.portable_dlc.v1`，至少声明：

- id、version、owner_cartridge 和 scope。
- backend JSON stdio worker entry。
- 可选 sandbox frontend entry。
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
  "schema": "cartridgeflow.portable_dlc.v1",
  "id": "dlc.example.workflow",
  "version": "1.0.0",
  "owner_cartridge": "example.workflow",
  "scope": "cartridge",
  "backend": {
    "entry": "dlc/backend/entry.py",
    "transport": "json_stdio_worker"
  },
  "frontend": {
    "entry": "dlc/frontend/index.html",
    "sandbox": "isolated_iframe",
    "context_keys": ["run_snapshot", "artifacts"]
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
    {"path": "dlc/frontend/index.html", "sha256": "..."},
    {"path": "dlc/protocols/EXAMPLE-DOMAIN-1.0.json", "sha256": "..."}
  ]
}
```

### 28.3 Descriptor 规则

1. schema MUST 为 `cartridgeflow.portable_dlc.v1`。
2. id、version 和 owner_cartridge MUST 稳定，owner MUST 匹配 Manifest。
3. scope 在本版本 MUST 为 cartridge。
4. backend transport MUST 是 Base 声明支持的隔离 transport；本规范标准值为 json_stdio_worker。
5. frontend 如果存在，sandbox MUST 为 isolated_iframe。
6. 所有路径 MUST 是包内相对路径且防路径穿越。
7. 可执行代码、协议、前端和 workflow 文件 MUST 出现在 files 并匹配 SHA-256。
8. descriptor tools 必须与 Manifest 启用工具集合完全一致，不能多一个或少一个。
9. tools 必须声明 server、tool、handler、effect、timeout 和 description。
10. descriptor 不得包含可执行表达式、凭据或隐式下载指令。

### 28.4 发现与验证

发现阶段只允许读取静态文件、解析 JSON 和计算 hash，不得：

- 导入 backend 模块。
- 启动 Worker、浏览器或外部应用。
- 执行 frontend 脚本。
- 发起网络请求。
- 下载依赖或生成业务文件。

验证至少检查 schema、owner、scope、路径、文件存在/hash、Manifest tool 对齐、权限、依赖、frontend sandbox、protocol identity 和资源 ownership。任一 blocker 使 DLC 进入 rejected/quarantined，不得部分激活。

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

前端消息使用领域中立类型：

```json
{
  "schema": "cartridgeflow.dlc_ui_message.v2",
  "type": "interaction.submit",
  "request_id": "uuid",
  "run_id": "run_...",
  "cartridge_id": "example.workflow",
  "payload": {}
}
```

宿主 MUST 校验消息 schema、origin context、cartridge scope 和 run scope。大文件使用受权限控制的 Artifact URL 或上传会话，不通过 postMessage 内联。

### 29.3 Frontend Sandbox

主前端不得动态 import 卡带 JavaScript。DLC frontend 必须位于带 sandbox 的独立 iframe，且不得启用 allow-same-origin。包内资源只能由校验 cartridge scope、路径和 hash 的端点提供。

DLC 不得访问主 DOM、全局 Store、路由器、CSS、其他卡带 Run、Artifact 或 private_data。页面切换、卡带停用或卸载时必须销毁 iframe、消息端口、监听器和未完成请求。

### 29.4 消息信封

所有消息 MUST 包含 schema、type、request_id、run_id、cartridge_id 和 payload。需要响应的请求必须有 response/error/cancel/timeout 语义，不能靠单向消息猜测完成状态。

宿主响应示例：

```json
{
  "schema": "cartridgeflow.dlc_ui_host_message.v2",
  "type": "interaction.result",
  "request_id": "uuid",
  "run_id": "run_...",
  "cartridge_id": "example.workflow",
  "ok": true,
  "payload": {}
}
```

### 29.5 宿主能力

Sandbox MAY 请求 Base 明确授予的通用能力，例如：

- 读取当前 run snapshot 的安全子集。
- 读取当前卡带 Artifact metadata 或受控 URL。
- 提交 pending interaction。
- 保存卡带私有草稿。
- 请求通知或用户下载。

能力必须协商并按 cartridge/run scope 授权。DLC UI 不得绕过 Runner 直接修改已提交状态。

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
- CF-FARP@0.6 是否注册并被 Base 支持。
- required profiles/capabilities/tool packs 是否满足。
- required model/resource roles 是否绑定。
- Manifest 与 Root Flow 是否合法。
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
    "required": "CF-FARP@0.6",
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
  "portable_dlc": {},
  "delivery_readiness": {},
  "findings": []
}
```

finding severity：

- blocker：禁止运行和认证。
- warning：可以按声明开发/预览，但禁止认证；必须显示影响。
- info：可选能力或诊断信息。

旧协议如果位于 Base 历史索引，必须报告 recognized_unsupported_protocol 和迁移目标；未知协议报告 unknown_protocol。不得用当前 v0.6 解释器静默运行旧版本。

## 33. 认证

`cf-farp-0-6-certified` 要求：

1. Base Contract 与 Runtime Contract 均合法。
2. Root Flow 声明 v0.6。
3. 兼容性报告无 blocker 和 warning。
4. 所有 AI decision 具有合法 envelope 与 consume。
5. 所有 required tools 具有完整 contract。
6. 所有 required resource roles 在认证环境完成绑定或被认证夹具明确替代。
7. 错误、恢复、副作用重放和 primary output 门禁通过。
8. DLC 卡带通过作用域、隔离、hash、停用、卸载和无残留测试。
9. 标签只能由认证工具写入。

```json
{
  "protocol_certification": {
    "status": "certified",
    "label": "cf-farp-0-6-certified",
    "protocol": "CF-FARP",
    "protocol_version": "0.6"
  }
}
```

认证报告必须引用实际 Base Implementation、协议 registry/正文 hash、Manifest/Root Flow hash、capability evidence、测试环境、工具/DLC hash 和测试结果。手工勾选清单不能替代机器报告。

认证只覆盖声明的卡带版本、协议版本、能力集合和测试环境。修改 Root Flow、required capability、工具 contract、DLC files、permission、Artifact/Delivery 语义后必须重新认证。

真实外部服务未验证时必须标记 external_unverified。mock、fixture 和 dry-run 可以证明结构路径，但不能证明真实外部质量或稳定性。

## 34. Capability 词表

v0.6 的完整核心能力词表包括：

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
pending_interaction_record
runtime_resume_after_user_input
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
```

Base MUST 只声明已实现并有证据的能力。没有声明某能力不等于协议删除该能力，而是该 Base 只能支持不要求该能力的 v0.6 卡带。

## 35. 从 v0.5 迁移

迁移到 v0.6 至少完成：

1. `base_contract` 改为 `CARTRIDGEFLOW-BASE@0.2`。
2. Runtime Contract、Root Flow 和 certification target 改为 v0.6。
3. 从卡带移除 URL、key、私有 header、本机路径和供应商默认端口。
4. 用 model role、resource role 和本机 binding 替代连接信息。
5. Remote 节点改为引用 resource role 与 manifest tool ID。
6. 工具 contract 补齐 idempotent、timeout 和 retry policy。
7. 副作用节点补齐 replay policy、permission、failure policy 和 audit log。
8. 错误处理改为 Runtime Error Envelope。
9. 需要恢复的流程接受 Checkpoint 与四类恢复动作。
10. Artifact 补齐 revision、ownership、状态和来源。
11. DLC protocol 改为 `CF-FARP@0.6`，重新计算 descriptor files hash。
12. 重新运行 v0.6 conformance 和认证，不沿用 v0.5 标签。

迁移 MUST 生成新卡带 revision 或副本，不得静默覆盖唯一原件。

迁移工具 MUST 在修改前生成报告，至少列出：旧 Base/Runtime Contract、节点字段变化、隐式 consume、嵌入连接信息、不完整 Tool Contract、不安全副作用、DLC hash 变化和无法自动判断项。

以下变化不得自动猜测：

- 哪个本机资源应绑定某个 role。
- 一个远程操作是否幂等。
- 旧 output 中哪个字段是真实业务消费值。
- 哪些 Artifact 在回滚后仍有效。
- 用户是否授权新的 permission 或 purge_all。

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
13. 禁止卸载后残留 Worker、代理、Overlay、路由或 private_data。
14. 禁止只声明协议版本而不声明真实 capability 和证据。

## 37. 最小一致性清单

- [ ] Manifest 同时声明 Base Contract 与 CF-FARP v0.6。
- [ ] Root Flow 只使用统一 Process Node。
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

### 38.2 Tool Plan 与副作用执行

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

### 38.3 Remote Call

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

### 38.4 Delivery

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

## 39. v0.5 条款处置矩阵

| v0.5 内容 | v0.6 位置 | 处置 |
|---|---|---|
| 协议定位、目标、关键词、版本治理 | 1-3 | 保留并改为 v0.6 独立快照 |
| 19 类实体定义 | 4.1-4.19 | 完整保留，新增 Resource Role、Error、Checkpoint、revision 语义 |
| 协议与 Base 分离 | 3、6.3、32 | 替代：Base Contract 与 Runtime Contract 不再要求相同身份/版本 |
| 卡带包结构 | 5 | 保留并增加路径安全、发现和原子安装规则 |
| Manifest、Runtime Contract、Readiness | 6-9 | 完整保留并增加本机模型/资源绑定 |
| Root Flow、节点通用规则、字段、显示 | 10-11 | 完整保留并补充规范化、拓扑和冲突处理 |
| Kind、Executor、Effect | 11-12 | 完整保留；新增 remote_call、validation、routing 细则 |
| 输入、传递、检索与转换 | 12-13 | 保留并纳入 Store revision 与谱系 |
| AI Decision 与 Envelope | 14 | 完整保留并加强 status 校验 |
| Consume 与后续消费 | 15 | 完整保留，禁止隐式投影 |
| 交互暂停与恢复 | 16、19、22 | 保留并增加持久 interaction 和四类恢复动作 |
| Provider 与测试模式 | 7、26-27 | 替代为模型角色、本机 assignment 和显式 execution mode |
| Tool Plan、MCP、Remote | 8、17-18 | 完整保留并禁止卡带连接秘密 |
| Store 数据链 | 13 | 完整保留并增加 revision/provenance |
| Artifact 与 Delivery | 24-25 | 扩展为 identity、revision、invalidation 和 primary output 门禁 |
| 错误、失败与回退 | 18、20、26 | 扩展为 Runtime Error Envelope 与稳定分类 |
| 测试台与探针 | 27 | 完整保留并强化 seeded 边界 |
| 兼容性与认证 | 32-33 | 完整保留并增加 Base Contract、binding、恢复和 DLC 证据 |
| Capability 声明 | 34 | 完整保留旧词表并追加 v0.6 能力 |
| Portable DLC 定义与 descriptor | 28 | 完整保留并升级到 CF-FARP@0.6 |
| 发现、验证、作用域注册 | 28.4-28.5 | 完整保留 |
| Worker 隔离 | 29.1-29.2 | 完整保留并增加 cancel/timeout/host shutdown 最终状态 |
| Frontend Sandbox | 29.3-29.5 | 完整保留，消息升级为领域中立 v2 |
| Protocol Overlay | 30 | 完整保留 |
| 资源所有权、激活、停用、卸载 | 31 | 完整保留并增加安装/升级事务与无残留验收 |
| 领域或供应商示例 | 卡带/DLC 私有文档 | 废止其根协议归属，不废止对应通用能力 |

本矩阵是覆盖审计，不表示 v0.6 运行时可以解释 v0.5 卡带。迁移必须生成 v0.6 卡带 revision 并重新认证。

## 40. 规范追踪与演进

### 40.1 条款追踪

Base 声明的每个 capability MUST 映射到实现入口、正向测试、适用的失败测试和 UI 可见性或 not_applicable 说明。协议认证还必须把关键 MUST/MUST NOT 条款映射到 conformance case。

最低追踪域：

- Manifest 与本机秘密隔离。
- Root Flow 与 Process Node。
- Decision Envelope 与 Consume。
- Pending Interaction。
- Tool Contract、permission、failure 和 replay。
- Runtime Error、状态迁移与 Checkpoint。
- Artifact revision、provenance、invalidation 和 Delivery。
- DLC descriptor、scope、Worker、sandbox、Overlay、ownership 和卸载。

### 40.2 协议完整性

未来 v0.6 文案修正不得改变规范语义。新增 required 字段、状态、生命周期、副作用、所有权或安全边界必须发布新的完整协议版本。

新版本必须：

1. 自包含，不要求读取旧正文补足含义。
2. 提供目录、完整实体和字段契约。
3. 提供前一版本条款处置矩阵。
4. 明确保留、替代和废止项。
5. 同步机器 registry、capability vocabulary、Base Implementation 与 conformance。
6. 对旧版本给出 recognized/unsupported/unknown 与迁移策略。

### 40.3 实现与协议边界

实现 bug 修复、性能改进、UI 优化和新增符合既有宿主接口的本机资源实例，不要求新协议版本。改变可移植卡带的公开含义时，必须先更新协议版本，不能只改代码和测试。
