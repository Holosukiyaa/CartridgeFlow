# CF-FARP@1.0 - Overview and terms

This file is a normative module of CF-FARP@1.0. The release is defined only by the same-version modules listed in README and CARTRIDGEFLOW-BASE@0.2.

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
cf-farp-1-0-certified
```

规则：

1. v1.0 是完整、模块化的发布单元；规范性语义仅来自本目录的发布工件与 README 所列模块。
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
