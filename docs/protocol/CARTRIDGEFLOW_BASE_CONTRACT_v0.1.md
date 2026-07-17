# CartridgeFlow Base Contract v0.1

状态：Draft

发布日期：2026-07-16

适用范围：CartridgeFlow 项目底座、卡带规范、Flow 设计台、测试台、内置 MCP 工具包和所有开发卡带。

本文目标：把过去在搭卡带时边做边改底座得到的经验，沉淀为一套稳定、可讨论、可版本化、不可随单个流程任意漂移的基础契约。以后任何卡带都必须先在这套契约内表达自己；只有当契约本身确实不足时，才允许通过正式变更流程升级契约。

---

## 目录

1. [文档定位](#1-文档定位)
2. [核心问题](#2-核心问题)
3. [设计原则](#3-设计原则)
4. [分层架构和可替换基座](#4-分层架构和可替换基座)
5. [版本治理](#5-版本治理)
6. [变更治理](#6-变更治理)
7. [卡带包契约](#7-卡带包契约)
8. [Manifest 契约](#8-manifest-契约)
9. [Root Flow 契约](#9-root-flow-契约)
10. [节点契约](#10-节点契约)
11. [边和拓扑契约](#11-边和拓扑契约)
12. [数据链契约](#12-数据链契约)
13. [工具和 MCP 契约](#13-工具和-mcp-契约)
14. [运行时契约](#14-运行时契约)
15. [测试台契约](#15-测试台契约)
16. [诊断契约](#16-诊断契约)
17. [UI 和用户运行界面契约](#17-ui-和用户运行界面契约)
18. [Artifact 契约](#18-artifact-契约)
19. [持久状态契约](#19-持久状态契约)
20. [远程服务契约](#20-远程服务契约)
21. [Fallback 契约](#21-fallback-契约)
22. [权限、环境和依赖契约](#22-权限环境和依赖契约)
23. [卡带搭建流程](#23-卡带搭建流程)
24. [Base Contract 变更流程](#24-base-contract-变更流程)
25. [参考卡带和测试矩阵](#25-参考卡带和测试矩阵)
26. [常见反模式](#26-常见反模式)
27. [当前实现对齐状态](#27-当前实现对齐状态)
28. [v0.1 收敛路线](#28-v01-收敛路线)
29. [附录 A：规范关键词](#附录-a规范关键词)
30. [附录 B：节点类型速查表](#附录-b节点类型速查表)
31. [附录 C：卡带评审清单](#附录-c卡带评审清单)

---

## 1. 文档定位

### 1.1 这是什么

本文是一份基础契约，不是一张卡带的设计说明。

它规定：

- CartridgeFlow 的底座哪些行为必须稳定。
- 卡带应该如何声明输入、输出、节点、工具、artifact 和副作用。
- 流程搭建时什么可以改，什么不能因为单张卡带随手改。
- 工具如何暴露参数 schema、输出结构和失败结构。
- 测试台如何判断流程是跑通、跑错、断链、fallback、隔离还是失败。
- Base Contract 如何通过版本号演进。

### 1.2 这不是什么

本文不是：

- `dev.pixel_episode_director` 的专属流程规范。
- 某个 UI 页面或某个工具函数的实现文档。
- 一次性的复盘报告。
- 能绕过讨论直接要求所有旧卡带立刻重写的命令。

### 1.3 为什么现在要写

当前项目已经进入一个危险阶段：

1. 一边搭流程，一边改底座。
2. 某个卡带不舒服，就顺手改 runner、executor、测试台或 MCP 面板。
3. 这对当前卡带可能立刻变好，但底座整体契约被悄悄改变。
4. 后续再搭其他卡带时，无法判断当前行为是通用能力、临时补丁，还是某张卡带遗留的偏置。

因此必须先把底座规范化。以后搭卡带时，优先在规范内表达需求；规范不足时，先提交契约变更，再改底座。

### 1.4 第一版目标

v0.1 的目标不是一次性设计完美系统，而是先锁住关键边界：

- 底座不再被单张卡带随意拉扯。
- 节点职责稳定。
- 工具契约可见。
- 数据链可诊断。
- 探针不改变流程语义。
- 副作用可追踪。
- 远程能力可隔离。
- Fallback 可见。
- 版本变更有规则。

---

## 2. 核心问题

### 2.1 过去的问题

在探索 `dev.pixel_episode_director` 这类复杂卡带时，暴露出以下问题：

- 流程图越搭越大，但哪些节点是真生产、哪些节点是装饰不清楚。
- AI 节点输出可能没有被下游工具真正消费。
- 工具参数藏在 Python 函数体里，MCP 面板无法解释。
- 局部探针曾经可能只跑一条分支，误以为整段流程通过。
- 工具 fallback 后继续跑，用户不知道产物来自真实能力还是兜底。
- 持久状态可能在失败后仍被回写。
- 故意隔离和意外断链在图上长得一样。
- 某张卡带需要的特殊逻辑容易被写入底座。

这些问题本质上不是某个流程的错误，而是底层契约不够清楚。

### 2.2 现在要解决的问题

当前最重要的问题不是“某条流程是否最合理”，而是：

> 如何保证搭任何卡带时，都不会干涉 CartridgeFlow 的原始设计和整体一致性。

因此本文从“搭卡带时不能破坏底座”出发，规定基础行为。

### 2.3 判断标准

以后遇到需求时，先问四个问题：

1. 这是卡带实例可以通过 `manifest/root.flow/assets` 表达的需求吗？
2. 这是某个工具包应该实现的能力吗？
3. 这是 Base Contract 已经允许但当前实现没做好的能力吗？
4. 这是否真的需要修改 Base Contract？

只有第 4 种情况，才允许动底座契约。

---

## 3. 设计原则

### 3.1 底座优先稳定

底座稳定性高于单张卡带短期体验。

某张卡带为了跑通而想改底座时，必须证明该改动是通用能力，而不是领域特例。

### 3.2 卡带优先声明

卡带必须通过声明式配置表达自己：

- `manifest.json`
- `root.flow.json`
- assets
- MCP 工具声明
- 输入输出 schema
- artifact 策略

不能通过修改 core 代码来补充卡带语义。

### 3.3 工具优先契约

工具不是黑盒函数。

每个工具都必须有：

- 参数 schema
- 默认参数
- 必填参数
- 输出结构
- 失败结构
- 副作用说明
- artifact 说明

### 3.4 诊断优先于猜测

测试台不能只显示“已完成”。它必须显示：

- 数据链是否断裂。
- 哪些输入由探针替身补齐。
- 哪些节点失败。
- 哪些节点 fallback。
- 哪些节点被故意隔离。
- 哪些 artifact 被生产。

### 3.5 副作用必须显式

任何写文件、写状态、调远程、生成媒体、修改世界状态的行为都必须可见、可追踪、可中断。

### 3.6 允许探索，但探索必须被隔离

探索节点可以存在，但必须标记：

- `isolated=true`
- `scope=branch`
- `status=experimental`
- 或放入独立 dev 卡带

探索能力不能静默接入主生产线。

### 3.7 版本控制优先于口头约定

所有契约必须有版本号。

口头说“以后不要这样”不够，必须能写入：

- 文档版本
- manifest 字段
- schema 字段
- 测试矩阵
- 迁移说明

---

## 4. 分层架构和可替换基座

CartridgeFlow 必须按层管理，不能让领域流程穿透到底座。

### 4.1 Layer 0：Base Core

Base Core 是最小底座。

职责：

- 卡带发现和加载。
- manifest 校验。
- root.flow 校验。
- root.flow 调度。
- 节点执行分发。
- context.store 生命周期。
- run 记录。
- event 记录。
- artifact 收集。
- permissions/environment/dependencies 状态。
- 测试台探针和诊断基础。

Base Core 不应该知道：

- 像素短剧是什么。
- Godot 是什么。
- ComfyUI 是什么。
- 某个领域流程需要几个镜头。
- 某个卡带的世界状态结构。

### 4.2 Layer 1：Base Contract

Base Contract 是本文。

职责：

- 规定 Base Core 的稳定行为。
- 规定卡带如何声明能力。
- 规定节点、工具、数据、测试、artifact 的契约。
- 规定版本和变更流程。

### 4.3 Layer 2：First-party Tool Packs

一方工具包可以由项目自带，但必须通过工具契约暴露。

示例：

- `filesystem`
- `media`
- `llm`
- `workspace`
- `archive`

工具包可以包含领域能力，例如：

- `media/godot_render_pixel_episode`
- `media/ffmpeg_mux_episode`
- `media/remote_upgrade_keyframes`

但这些领域能力必须被封装在工具包内，不能反向修改 Base Core 的语义。

### 4.4 Layer 3：Cartridge Spec

卡带规范定义一张卡带如何被描述。

包括：

- package 目录结构。
- manifest 字段。
- root.flow 字段。
- assets 结构。
- MCP 工具声明。
- 输入输出声明。
- artifact 和 delivery 声明。

### 4.5 Layer 4：Cartridge Instance

具体卡带属于这一层。

示例：

- `dev.file_summary`
- `dev.log_diagnosis`
- `dev.multi_file_summary`
- `dev.pixel_episode_director`

具体卡带可以复杂，但不能要求底座为它写特殊逻辑。

### 4.6 Layer 5：External Services

外部服务包括：

- ComfyUI
- 云端 GPU 服务
- 数据库
- 发布平台
- 远程 MCP server

外部服务必须通过 `remote_call` 或 MCP 工具契约接入。

不能假装外部服务是本地稳定能力。

### 4.7 Base Contract 不是 Base Implementation

必须明确区分两个概念：

| 名称 | 含义 | 例子 |
| --- | --- | --- |
| Base Contract | 本文定义的规范、契约、行为要求。 | `CartridgeFlow Base Contract v0.1` |
| Base Implementation | 一个实际可运行的基座实现。 | 当前 Python/FastAPI/React 基座、未来 Rust/Node/Python 新基座 |

Base Contract 规定“什么行为必须成立”。

Base Implementation 负责“用某套代码实现这些行为”。

卡带依赖的首要对象应该是 Base Contract，而不是某一个具体实现。

### 4.8 可替换基座原则

CartridgeFlow 应允许多个不同基座实现同时存在。

例如：

```text
cartridgeflow.reference-python  支持 Base Contract 0.1
cartridgeflow.desktop-runtime   支持 Base Contract 0.1
cartridgeflow.server-runtime    支持 Base Contract 0.1 和 0.2
cartridgeflow.experimental-v2   支持 Base Contract 0.2
```

只要这些基座声明并通过同一套 Contract/Profile/Capability 测试，就应该能运行共同支持范围内的卡带。

### 4.9 基座实现清单

每个基座实现都应该有自己的 base manifest。

建议结构：

```json
{
  "base_id": "cartridgeflow.reference-python",
  "base_name": "CartridgeFlow Reference Python Base",
  "base_version": "0.1.0",
  "supported_contracts": [
    {
      "name": "cartridgeflow.base",
      "version": "0.1",
      "status": "supported"
    }
  ],
  "profiles": [
    "runtime_core",
    "shelf_runner",
    "lab_designer",
    "testbench_core"
  ],
  "capabilities": {
    "flow.next_edges": "0.1",
    "flow.fanout_join": "0.1",
    "runtime.context_store": "0.1",
    "runtime.abort_on_failed": "0.1",
    "diagnostics.data_chain": "0.1",
    "diagnostics.structure": "0.1",
    "testbench.probe_subgraph": "0.1",
    "artifacts.collection": "0.1"
  },
  "tool_packs": [
    {
      "server": "filesystem",
      "contract_version": "0.1"
    },
    {
      "server": "media",
      "contract_version": "0.1",
      "optional": true
    }
  ]
}
```

### 4.10 Profiles：基座能力档位

同一个 Base Contract 可以有不同 profile。

建议先定义这些 profile：

| Profile | 必需性 | 说明 |
| --- | --- | --- |
| `runtime_core` | 必需 | 能加载卡带、执行 root.flow、维护 store、写 run/events。 |
| `shelf_runner` | 推荐 | 能在货架/运行界面启动卡带。 |
| `lab_designer` | 可选 | 能编辑卡带、预览 graph、管理节点和边。 |
| `testbench_core` | 推荐 | 能运行全流程测试、探针测试和诊断。 |
| `packager` | 可选 | 能打包、导入、安装卡带。 |
| `tool_registry` | 推荐 | 能枚举工具、暴露 schema、绑定节点。 |

一个纯运行基座可以只支持 `runtime_core + shelf_runner`。

一个开发基座应支持 `runtime_core + lab_designer + testbench_core + tool_registry`。

### 4.10.1 开发基座和生产基座

协议和基座分离后，必须进一步区分开发环境和生产环境。

| 基座类型 | 目标用户 | 必需能力 | 不应承担的职责 |
| --- | --- | --- | --- |
| 开发基座 | 卡带开发者、流程设计者、工具开发者 | 设计台、测试台、诊断、schema 编辑、探针、打包 | 不应该作为交付时唯一可运行环境 |
| 生产基座 | 最终用户、部署环境、交付运行时 | 协议验证、卡带加载、运行、权限/依赖检查、结果展示 | 不应该要求用户进入设计台或理解节点图 |

开发基座负责把卡带搭好、测好、打包好。

生产基座只需要支持卡带声明的协议、profiles、capabilities 和 tool contracts，就应该能直接运行该卡带。

这意味着：

- 卡带不能依赖设计台状态才能运行。
- 卡带不能依赖测试台替身数据才能运行。
- 卡带不能依赖开发基座里的临时文件缓存才能运行。
- 卡带交付包必须包含运行所需的 manifest、root.flow、assets 和工具契约声明。
- 生产基座可以没有 `lab_designer` 和 `testbench_core`，但必须有 `runtime_core`。

### 4.10.2 开发到生产的交付边界

从开发基座交付到生产基座时，必须进行一次交付检查。

检查项：

- 卡带声明了 `runtime_contract`。
- 卡带没有未标记的孤立节点。
- 卡带没有依赖探针 seeded keys。
- 卡带没有依赖开发基座私有扩展，或已声明 `implementation_lock`。
- 卡带 assets 完整。
- required tools 已声明。
- 生产基座 compatibility report 通过。

交付检查通过后，生产基座应该能在没有设计台的情况下运行卡带。

### 4.10.3 生产基座最小能力

生产基座最小 profile：

```json
{
  "profiles": ["runtime_core", "shelf_runner"],
  "capabilities": {
    "flow.next_edges": "0.1",
    "flow.fanout_join": "0.1",
    "runtime.context_store": "0.1",
    "runtime.abort_on_failed": "0.1",
    "artifacts.collection": "0.1",
    "delivery.summary_with_artifacts": "0.1"
  }
}
```

生产基座可以不支持：

- 节点编辑。
- 边编辑。
- AI 管家改图。
- 探针调试。
- 详细开发诊断。
- MCP 工具模板编辑。

但如果卡带要求这些能力，它就不是面向普通生产基座的交付卡带。

### 4.10.4 交付卡带定义

交付卡带是指可以交给生产基座直接运行的卡带。

交付卡带必须满足：

1. 不依赖 `lab_designer`。
2. 不依赖 `testbench_core`。
3. 不依赖未打包 assets。
4. 不依赖开发工作区临时文件。
5. 不依赖未声明 tool pack。
6. 不依赖未声明外部服务。
7. 运行入口是 manifest inputs 和 root.flow start。
8. 交付结果由 manifest outputs、artifacts 和 delivery 描述。

开发卡带可以不满足这些条件，但必须标记为 dev 或 experimental，不能当成交付卡带发布。

### 4.11 Capabilities：比版本更细的能力协商

只声明“支持 Base Contract v0.1”还不够。

基座必须声明更细的 capabilities，因为不同卡带需要不同能力。

示例：

```json
{
  "capabilities": {
    "flow.fanout_join": "0.1",
    "flow.isolated_nodes": "0.1",
    "runtime.remote_call": "0.1",
    "runtime.persistent_state_guard": "0.1",
    "diagnostics.data_chain": "0.1",
    "testbench.probe_subgraph": "0.1"
  }
}
```

规则：

- 卡带只应要求自己真的需要的 capability。
- 基座只应声明自己已经通过一致性测试的 capability。
- 卡带和基座的兼容性由 Contract + Profile + Capability + Tool Pack 一起决定。

### 4.12 Tool Packs 也是可替换的

不同基座可以使用不同工具包实现，只要工具契约相同。

例如：

```text
filesystem/read_file
```

可以由 Python 实现，也可以由 Node 实现。

只要参数 schema、输出 schema、错误结构和副作用语义一致，卡带不应该关心具体实现语言。

### 4.13 可移植卡带定义

一张卡带是可移植的，当且仅当：

1. 它声明了 `base_contract` 范围。
2. 它声明了 required profiles。
3. 它声明了 required capabilities。
4. 它声明了 required tool packs 和工具契约版本。
5. 它没有依赖某个具体 base implementation 的私有行为。
6. 它通过该 contract/profile/capability 的一致性测试。

同一个卡带可以在多个基座上运行，只要这些基座都满足它的声明。

### 4.14 私有扩展规则

基座实现可以提供私有扩展，但必须命名空间隔离。

建议格式：

```json
{
  "x_cartridgeflow_reference_python": {
    "some_private_option": true
  }
}
```

规则：

- 私有扩展不得影响标准 contract 行为。
- 卡带如果依赖私有扩展，必须声明 `implementation_lock`。
- 被 implementation locked 的卡带不再视为可移植卡带。

---

## 5. 版本治理

### 5.1 版本对象

CartridgeFlow 至少有四类版本：

| 版本 | 说明 |
| --- | --- |
| Base Contract Version | 本文档定义的基础契约版本。 |
| Flow Schema Version | `root.flow.json` 的结构版本。 |
| Manifest Schema Version | `manifest.json` 的结构版本。 |
| Tool Contract Version | 工具参数和输出契约版本。 |

### 5.2 Base Contract 版本号

Base Contract 使用语义版本：

```text
MAJOR.MINOR.PATCH
```

规则：

- `PATCH`：修正文档、补充说明、不改变契约含义。
- `MINOR`：新增兼容能力，旧卡带仍可按旧行为运行。
- `MAJOR`：破坏兼容，需要迁移旧卡带。

示例：

- `0.1.0`：第一版草案。
- `0.2.0`：新增可选输入契约。
- `1.0.0`：冻结稳定版。
- `2.0.0`：节点模型有破坏性变化。

### 5.3 卡带声明契约版本

建议后续在 `manifest.json` 中加入最小声明：

```json
{
  "base_contract": "0.1",
  "manifest_schema_version": "1.0",
  "flow_schema_version": "1.0"
}
```

在 v0.1 阶段，如果字段尚未实现，测试台应以默认兼容模式处理。

更完整的声明建议使用 `runtime_contract`：

```json
{
  "runtime_contract": {
    "contract": "cartridgeflow.base",
    "version": ">=0.1 <0.2",
    "required_profiles": [
      "runtime_core"
    ],
    "recommended_profiles": [
      "testbench_core",
      "tool_registry"
    ],
    "required_capabilities": {
      "flow.next_edges": ">=0.1",
      "flow.fanout_join": ">=0.1",
      "runtime.context_store": ">=0.1",
      "runtime.abort_on_failed": ">=0.1",
      "artifacts.collection": ">=0.1"
    },
    "optional_capabilities": {
      "diagnostics.data_chain": ">=0.1",
      "testbench.probe_subgraph": ">=0.1"
    },
    "required_tools": [
      {
        "server": "filesystem",
        "tool": "read_file",
        "contract_version": ">=0.1"
      }
    ],
    "optional_tools": [],
    "implementation_lock": null
  }
}
```

规则：

- `version` 可以是精确版本，也可以是范围。
- `required_profiles` 缺失则不能运行。
- `recommended_profiles` 缺失时可以运行，但测试台或设计体验可能降级。
- `required_capabilities` 缺失则不能运行。
- `optional_capabilities` 缺失时必须显示能力降级。
- `required_tools` 缺失则不能运行相关节点。
- `implementation_lock` 非空时，该卡带不再是跨基座可移植卡带。

### 5.4 工具契约版本

每个工具建议声明：

```json
{
  "server": "media",
  "tool": "godot_render_pixel_episode",
  "contract_version": "0.1",
  "params_schema": {},
  "result_schema": {}
}
```

工具契约升级规则：

- 新增可选参数：minor。
- 新增输出字段：minor。
- 删除参数：major。
- 改变参数含义：major。
- 改变失败结构：major。

### 5.5 兼容策略

底座加载卡带时必须知道：

- 这张卡带要求哪个契约版本。
- 当前底座支持哪个契约版本。
- 是否需要兼容模式。
- 是否必须迁移。

不允许在不知道契约版本的情况下静默按最新规则解释旧卡带。

### 5.6 基座选择流程

当用户运行卡带时，基座应按以下顺序判断：

1. 读取卡带 `runtime_contract`。
2. 读取当前 base implementation manifest。
3. 判断 Base Contract version 是否匹配。
4. 判断 required profiles 是否全部支持。
5. 判断 required capabilities 是否全部支持。
6. 判断 required tool packs 和 tool contracts 是否全部支持。
7. 如果存在 `implementation_lock`，判断当前基座 ID 是否匹配。
8. 生成兼容性报告。
9. 只有兼容性报告通过，才允许运行。

### 5.7 同规范不等于完全兼容

两个基座都支持 Base Contract v0.1，不代表它们能运行所有 v0.1 卡带。

兼容性必须同时满足：

```text
Base Contract 匹配
+ Profile 匹配
+ Capability 匹配
+ Tool Pack 匹配
+ Tool Contract 匹配
+ 无冲突 implementation lock
```

例如：

- 基座 A 支持 `runtime_core + filesystem`。
- 基座 B 支持 `runtime_core + filesystem + media`。
- 文件总结卡带可在 A 和 B 上运行。
- 像素短剧卡带如果要求 `media/godot_render_pixel_episode`，只能在 B 或等价 media 工具包基座上运行。

### 5.8 共同可运行子集

不同基座之间的互通范围，是它们共同支持能力的交集。

定义：

```text
Portable Cartridge Set(Base A, Base B)
= 两个基座共同支持的 Contract/Profile/Capability/Tool Contract 所覆盖的卡带集合
```

这意味着：

- 卡带越少依赖私有能力，越容易跨基座运行。
- 基座越完整支持标准 profiles 和 tool packs，可运行卡带越多。
- 规范版本只是入口，能力交集才是真正可移植范围。

### 5.9 基座升级策略

一个新基座可以支持多个规范版本。

示例：

```json
{
  "supported_contracts": [
    {"name": "cartridgeflow.base", "version": "0.1"},
    {"name": "cartridgeflow.base", "version": "0.2"}
  ]
}
```

升级到 v0.2 时，基座不应强迫所有 v0.1 卡带立即迁移。

推荐策略：

- v0.2 基座保留 v0.1 兼容解释器。
- v0.1 卡带继续按 v0.1 契约运行。
- 新卡带可以选择声明 `>=0.2 <0.3`。
- 旧卡带迁移必须有迁移报告和自动/半自动迁移工具。

### 5.10 一致性测试

一个基座不能只声称支持某个 contract/profile/capability，必须通过一致性测试。

最小一致性测试包括：

| 测试 | 覆盖能力 |
| --- | --- |
| manifest load test | manifest schema、卡带发现。 |
| root flow linear test | `next` 主链执行。 |
| fan-out/join test | 多分支汇入语义。 |
| context store test | input/output/store 引用。 |
| abort test | `abort_on_failed` 和失败中断。 |
| artifact test | artifact 收集和 delivery。 |
| isolated node test | 故意隔离和意外断链区分。 |
| probe subgraph test | 探针范围保留子图拓扑。 |
| tool schema test | 工具 schema 导出和参数校验。 |

未来应把这些测试做成可运行的 `base_conformance_tests`。

---

## 6. 变更治理

### 6.1 哪些改动算 Base Contract 变更

以下改动必须走 Base Contract 变更流程：

- 改变 root.flow 执行顺序。
- 改变 fan-out/join 语义。
- 改变 `context.store` 读写语义。
- 改变 `input/output` 解析规则。
- 改变节点成功/失败判定。
- 改变 `tool_call` 或 `remote_call` 的职责。
- 改变探针范围语义。
- 改变测试台“通过”的定义。
- 改变 artifact 收集规则。
- 改变 fallback 是否算成功。
- 改变 MCP schema 的事实来源。

### 6.2 哪些改动不算 Base Contract 变更

以下改动通常不需要修改 Base Contract：

- 新增一张卡带。
- 修改某张卡带的节点布局。
- 修改某张卡带的 prompt。
- 修改某张卡带的默认输入。
- 新增一个工具，只要符合工具契约。
- 修复某个工具内部 bug，不改变工具契约。
- 优化 UI 样式，不改变测试和运行语义。

### 6.3 单张卡带不得推动底座特殊化

禁止因为单张卡带需要而做如下改动：

- 在 runner 里硬编码卡带 ID。
- 在 node executor 里识别某个卡带字段。
- 在测试台里为某张卡带隐藏错误。
- 在 Base Core 里加入领域默认值。
- 在 registry 里特殊读取某张卡带的 assets。

如果必须出现领域逻辑，应放入工具包或卡带 assets。

### 6.4 三卡带原则

一个底座新能力，至少要能解释三类卡带的需求，才适合进入 Base Contract。

例如：

- 数据链诊断：适用于文件总结、日志诊断、像素短剧。
- MCP schema：适用于 filesystem、media、未来 database。
- 探针子图：适用于所有带分支的流程。

如果只服务一张卡带，应优先作为卡带级配置或工具级能力。

---

## 7. 卡带包契约

### 7.1 标准目录结构

一张卡带至少包含：

```text
cartridge_id/
  manifest.json
  root.flow.json
  assets/
```

可选包含：

```text
  assets/welcome.html
  assets/*.json
  assets/templates/
  assets/examples/
  assets/tool_profiles/
```

### 7.2 包内禁止内容

卡带包内不应包含：

- 需要写入 Base Core 的代码补丁。
- 用户私密 API key。
- 临时 tunnel URL 作为默认值。
- 未声明来源的二进制大文件。
- 与卡带无关的测试输出。
- 运行时全局缓存。

### 7.3 包内可包含内容

卡带包内可以包含：

- 示例输入。
- 示例 assets。
- welcome UI。
- 模板文件。
- workflow JSON。
- 本地静态资源。
- profile 和 manifest。

### 7.4 卡带包不得假装独立可执行

除非另有导入/安装/运行规范，`.cartridge.zip` 只是卡带包，不是独立应用。

它依赖 CartridgeFlow Runtime 执行。

---

## 8. Manifest 契约

### 8.1 必需字段

`manifest.json` 必须包含：

```json
{
  "schema_version": "1.0",
  "id": "dev.example",
  "name": "Example",
  "version": "0.1.0",
  "kind": "runtime_cartridge",
  "category": "dev_flow",
  "description": "",
  "root_flow": {
    "entry": "root.flow.json",
    "mode": "lifecycle",
    "required": true
  },
  "runtime": {},
  "workspace": {},
  "environment": {},
  "permissions": [],
  "dependencies": [],
  "mcp_tools": [],
  "inputs": [],
  "outputs": [],
  "artifacts": {},
  "delivery": {}
}
```

### 8.2 ID 规则

卡带 ID 必须稳定。

规则：

- 小写。
- 使用 `.`、`_`、`-`。
- dev 卡带应以 `dev.` 开头。
- 不应包含空格、中文、临时版本词。

示例：

```text
dev.file_summary
dev.pixel_episode_director
com.company.report_generator
```

### 8.3 inputs 规则

每个输入字段必须说明：

- `id`
- `label`
- `type`
- `required`
- `default`
- `placeholder`
- 可选项 `options`

输入字段只是用户入料，不等同于流程内部数据键。

用户输入必须由某个节点，例如 `collect_inputs`，明确写入 `context.store`。

### 8.4 outputs 规则

每个输出必须声明：

- `id`
- `label`
- `type`
- `required`

输出 ID 必须对应某个最终节点可产生的 store key 或 artifact。

### 8.5 mcp_tools 规则

`mcp_tools` 是卡带可用工具库，不是节点实例参数。

每个工具必须声明：

```json
{
  "id": "media_godot_render_pixel_episode",
  "name": "Media Godot Render",
  "type": "builtin",
  "server": "media",
  "tool": "godot_render_pixel_episode",
  "description": "",
  "default_params": {},
  "params_schema": {},
  "enabled": true
}
```

注意：

- 工具库默认参数不一定等于节点运行参数。
- 节点实例可以覆盖工具默认参数。
- UI 必须区分“工具模板默认值”和“节点实例覆盖值”。

### 8.6 dependencies 规则

依赖必须说明：

- `id`
- `type`
- `description`
- `install.strategy`

如果依赖是可选能力，必须写清楚 fallback 行为。

### 8.7 environment 规则

环境检查只负责发现能力，不负责偷偷安装或修改系统。

环境项必须说明：

- command
- required/optional
- unavailable 时流程如何处理

### 8.8 runtime_contract 规则

卡带应声明自己需要运行在哪类规范基座上。

推荐字段：

```json
{
  "base_contract": "0.1",
  "runtime_contract": {
    "contract": "cartridgeflow.base",
    "version": ">=0.1 <0.2",
    "required_profiles": ["runtime_core"],
    "recommended_profiles": ["testbench_core"],
    "required_capabilities": {
      "flow.next_edges": ">=0.1",
      "runtime.context_store": ">=0.1"
    },
    "required_tools": [
      {
        "server": "filesystem",
        "tool": "read_file",
        "contract_version": ">=0.1"
      }
    ],
    "implementation_lock": null
  }
}
```

`base_contract` 是简写，用于人读和老实现兼容。

`runtime_contract` 是完整机器可读契约，用于未来基座选择、兼容性报告和跨基座运行。

### 8.9 implementation_lock 规则

默认情况下，卡带不得锁死具体基座实现。

只有在以下情况允许使用 `implementation_lock`：

- 卡带依赖某个基座私有扩展。
- 卡带正在实验尚未标准化的能力。
- 卡带明确只作为某个基座的内部测试卡带。

示例：

```json
{
  "runtime_contract": {
    "implementation_lock": {
      "base_id": "cartridgeflow.reference-python",
      "reason": "uses experimental x_cartridgeflow_reference_python extension"
    }
  }
}
```

一旦使用 `implementation_lock`：

- 货架必须显示“非可移植卡带”。
- 打包时必须写入 warning。
- 其他基座可以拒绝运行。

### 8.10 compatibility_report 规则

基座加载卡带时，应生成兼容性报告。

建议结构：

```json
{
  "compatible": true,
  "contract": {
    "required": ">=0.1 <0.2",
    "provided": "0.1"
  },
  "profiles": {
    "missing_required": [],
    "missing_recommended": ["testbench_core"]
  },
  "capabilities": {
    "missing_required": [],
    "missing_optional": []
  },
  "tools": {
    "missing_required": [],
    "missing_optional": []
  },
  "implementation_lock": {
    "locked": false,
    "matched": true
  }
}
```

报告必须能解释：

- 为什么能跑。
- 为什么不能跑。
- 哪些能力缺失但可降级。
- 哪些能力缺失会阻断。

### 8.11 protocol_certification 规则

协议认证标签只能由基座认证检测接口写入。

卡带不得手工伪造认证标签。

认证检测必须至少满足：

- compatibility report 无 blocker。
- compatibility report 无 warning。
- 卡带不是 legacy 模式。
- `base_contract` 已声明。
- `runtime_contract` 已声明。
- `delivery_readiness` 已声明。
- required tool 具备 contract 元数据。

建议字段：

```json
{
  "protocol_certification": {
    "status": "certified",
    "label": "cf-farp-0-1-certified",
    "protocol": "CF-FARP",
    "protocol_version": "0.1",
    "base_implementation_id": "cartridgeflow.reference-dev",
    "base_implementation_version": "0.1.0"
  }
}
```

认证失败时，基座必须拒绝写入 `protocol_certification` 和认证 tag。

### 8.12 delivery_readiness 规则

卡带应能声明自己是否可交付给生产基座。

建议字段：

```json
{
  "delivery_readiness": {
    "level": "dev | preview | production",
    "requires_lab_designer": false,
    "requires_testbench": false,
    "requires_unpacked_workspace": false,
    "notes": ""
  }
}
```

含义：

| level | 含义 |
| --- | --- |
| `dev` | 仍在开发，只保证开发基座内可调试。 |
| `preview` | 可演示，但可能依赖部分开发能力或未冻结工具。 |
| `production` | 可交付给符合协议的生产基座直接运行。 |

生产基座可以拒绝运行 `delivery_readiness.level=dev` 的卡带，或要求用户显式确认。

---

## 9. Root Flow 契约

### 9.1 必需字段

`root.flow.json` 必须包含：

```json
{
  "schema_version": "1.0",
  "id": "dev.example.root",
  "name": "Example Root Flow",
  "mode": "lifecycle",
  "cartridge_id": "dev.example",
  "start": "start",
  "states": {},
  "edges": []
}
```

### 9.2 Root Flow 是执行图，不是设计稿

`root.flow.json` 里的状态和边代表真实可执行结构。

不允许把大量“未来可能有”的节点放入主图，除非它们：

- `isolated=true`
- 或 `scope=branch`
- 或 `action=custom_action`
- 或明确不会被主链执行

### 9.3 Root Flow 必须能被静态分析

测试台至少应分析：

- start 是否存在。
- terminal 是否存在。
- next 是否指向有效节点。
- edges 是否指向有效节点。
- 是否存在未标记孤立节点。
- 是否存在循环风险。
- 是否存在重复边。

### 9.4 Root Flow 不应该表达领域底座逻辑

Root Flow 可以表达领域流程，但不能要求底座识别领域语义。

例如：

- 可以有 `generate_shot_plan` 节点。
- 不能要求 runner 知道“镜头表”是什么。

---

## 10. 节点契约

### 10.1 节点基本字段

每个节点建议包含：

```json
{
  "type": "runtime",
  "title": "节点标题",
  "action": "tool_call",
  "params": {
    "node_category": "tool",
    "input": "some_key",
    "output": "other_key"
  },
  "next": "next_node",
  "layout": {"x": 0, "y": 0}
}
```

### 10.2 节点职责必须单一

节点不能同时承担多个核心职责。

禁止：

- 一个 `llm_prompt` 节点直接写文件。
- 一个 `tool_call` 节点判断剧情策略。
- 一个 `ui` 节点修改持久状态。
- 一个 `pass_result` 节点调远程服务。

### 10.3 标准节点类别

| category | 典型 action | 职责 |
| --- | --- | --- |
| `system` | `start` | 启动流程。 |
| `input` | `collect_inputs` | 收集用户输入并写入 store。 |
| `ui` | `show_ui` | 展示 UI 或结果。 |
| `process` | `llm_prompt` | 判断、规划、生成结构化指令。 |
| `tool` | `tool_call` | 执行本地或内置工具。 |
| `remote` | `remote_call` | 调用外部服务。 |
| `transfer` | `pass_result` | 合并、复制、传递 store 数据。 |
| `gate` | `tool_call` 或 `llm_prompt` | 质检或门禁，应有明确失败策略。 |
| `terminal` | 无或 `complete` | 结束流程。 |
| `placeholder` | `custom_action` | 占位或探索，不应影响主线。 |

### 10.4 process 节点规则

process 节点负责：

- 分析输入。
- 规划下一步。
- 生成工具可消费的指令。
- 产出结构化文本或 JSON。

process 节点不得：

- 直接读写文件。
- 直接调用 MCP。
- 直接修改 artifact。
- 直接修改持久状态。

### 10.5 tool 节点规则

tool 节点负责：

- 调用工具。
- 把工具结果写入 store。
- 产生 artifact。
- 返回结构化结果。

tool 节点必须：

- 有 process 父节点，除非规范明确豁免。
- 声明 `input` 和 `output`。
- 声明失败策略。
- 不做 AI 决策。

### 10.6 remote 节点规则

remote 节点代表外部依赖。

remote 节点必须：

- 显式标识 `remote_service`。
- 声明是否 `isolated`。
- 声明 timeout 或失败策略。
- 返回 provider 信息。
- 返回是否真实使用远端服务。

如果 remote 节点进入主链，它应遵守和 tool 节点相同的 process 父节点规则。

如果 remote 节点只是探索通道，必须 `isolated=true`。

### 10.7 transfer 节点规则

transfer 节点只做数据搬运。

允许：

- 复制 key。
- 合并多个 key。
- 重命名 key。
- 生成轻量结构。

不允许：

- 调工具。
- 调 LLM。
- 写文件。
- 访问远端。

### 10.8 gate 节点规则

gate 节点用于门禁和质检。

gate 节点必须有：

- 明确输入。
- 明确检查项。
- 明确失败结构。
- 明确是否 `abort_on_failed`。

gate 节点不应该只是“写一句审核意见”。

### 10.9 UI 节点规则

UI 节点负责：

- 欢迎页。
- 表单。
- 结果展示。
- Markdown/HTML/JSON 预览。

UI 节点不负责：

- 生成业务结果。
- 判断流程是否通过。
- 写持久状态。

### 10.10 custom_action 规则

`custom_action` 只允许用于占位或临时探索。

进入主链前必须转成：

- `llm_prompt`
- `tool_call`
- `remote_call`
- `pass_result`
- `show_ui`

---

## 11. 边和拓扑契约

### 11.1 next 和 edges 的关系

`next` 表示节点的主出口。

`edges` 表示补充边或显式图结构。

如果同一条边同时存在于 `next` 和 `edges`，执行器必须去重。

但规范建议：收敛后的卡带减少重复声明，避免改漏。

### 11.2 fan-out 规则

一个节点可以指向多个下游节点。

fan-out 用于：

- 并行读取资料。
- 同时触发多个准备动作。
- 把一个调度指令分给多个机器。

fan-out 的每个下游都必须能解释自己的输入。

### 11.3 join 规则

多个父节点汇入同一节点时，join 节点必须等所有父节点完成后再执行。

join 不能只等第一条路径完成。

测试台探针也必须保留 join 语义。

### 11.4 孤立节点规则

从 `start` 不可达的节点分两类：

1. 故意隔离：必须 `params.isolated=true`。
2. 意外断链：必须 warning 或 error。

故意隔离节点可以存在，但不能影响主链。

### 11.5 探索分支规则

探索分支应满足：

- 不参与默认主运行。
- 不污染主链 artifact。
- 不写持久状态。
- 不改变主链成功/失败。
- 有明确接回规则。

---

## 12. 数据链契约

### 12.1 context.store 是唯一运行期数据总线

所有节点间数据传递必须通过 `context.store`。

用户输入进入 store 的方式必须明确，例如：

```text
collect_inputs -> episode_brief
```

### 12.2 input 和 output 是流程契约

`params.input` 不是注释，是契约。

`params.output` 不是 UI 标签，是 store key。

测试台必须依据它们做数据链诊断。

### 12.3 必需输入和可选输入必须分开

v0.1 建议新增或约定以下字段：

```json
{
  "input": "required_a,required_b",
  "optional_input": "optional_c,optional_d"
}
```

或：

```json
{
  "inputs": {
    "required": ["required_a", "required_b"],
    "optional": ["optional_c"]
  }
}
```

规则：

- `input` 中的 key 缺失，应视为数据链断裂。
- `optional_input` 中的 key 缺失，应显示为可选缺失，不算断裂。
- 不允许把可选输入混在 `input` 里靠静默跳过。

这一条对升级通道、可选素材、多供应商 fallback 特别重要。

### 12.4 store key 命名规则

store key 应使用：

- 小写。
- 下划线。
- 名词或名词短语。
- 语义稳定。

示例：

```text
episode_brief
series_bible_text
asset_check_report
shot_plan_json
render_bundle
episode_video
```

不建议：

```text
result
data
tmp
xxx
output1
```

### 12.5 store 引用规则

工具参数可以使用：

```text
store:key
store:key.field
store:key.items[0]
```

如果 base key 不存在，执行器必须记录 missing store ref。

### 12.6 数据链断裂规则

以下情况算数据链断裂：

- 节点声明读取 `input`，但运行时 store 中不存在该 key。
- 工具参数引用 `store:key`，但 key 不存在。
- 必需输入由探针替身补齐，但完整运行中没有真实上游生产者。

### 12.7 数据链通过规则

数据链通过必须满足：

- 所有必需 input 在运行时存在。
- 所有必需 `store:` 引用可解析。
- 关键输出被写入 store。
- 探针补齐的 key 被明确标记，不冒充真实上游。

### 12.8 数据契约不能只靠自然语言

节点 description 不能替代 `input/output`。

AI prompt 不能替代数据契约。

工具说明不能替代 result schema。

---

## 13. 工具和 MCP 契约

### 13.1 工具事实来源

工具契约的事实来源必须是可导出的结构，不应该只存在于函数体里的 `params.get()`。

最小要求：

- 工具注册表能导出 description。
- 工具注册表能导出 params。
- 后端能转为 `params_schema`。
- 前端能渲染字段。

长期目标：

- 工具用 dataclass 或 pydantic 定义入参。
- schema 自动生成。
- API 校验、前端表单、文档共用同一来源。

### 13.2 工具必须声明参数 schema

每个工具参数至少包含：

- name
- type
- description
- default
- required
- enum
- secret
- path_kind

示例：

```json
{
  "type": "object",
  "required": ["shot_plan_path"],
  "properties": {
    "shot_plan_path": {
      "type": "string",
      "description": "Path to shot_plan.json"
    },
    "require_godot_native": {
      "type": "boolean",
      "default": false
    }
  }
}
```

### 13.3 工具必须声明输出结构

建议新增：

```json
{
  "result_schema": {
    "type": "object",
    "required": ["ok"],
    "properties": {
      "ok": {"type": "boolean"},
      "path": {"type": "string"},
      "content": {},
      "files": {"type": "array"},
      "error": {"type": "string"}
    }
  }
}
```

### 13.4 工具失败结构

工具失败必须返回：

```json
{
  "ok": false,
  "error": "human readable error",
  "issues": [],
  "repair": "suggested repair"
}
```

门禁类工具建议返回：

```json
{
  "ok": true,
  "asset_ok": false,
  "issues": [],
  "repairs": []
}
```

质检类工具建议返回：

```json
{
  "ok": true,
  "validation_ok": false,
  "issues": [],
  "repairs": []
}
```

### 13.5 工具副作用声明

工具必须声明副作用等级：

| 等级 | 说明 |
| --- | --- |
| `none` | 只计算，不读写外部文件。 |
| `read` | 读取文件或远端。 |
| `write_artifact` | 写 run-scoped artifact。 |
| `write_workspace` | 写工作区文件。 |
| `write_persistent_state` | 写持久状态。 |
| `remote` | 调外部服务。 |

测试台和运行界面应显示副作用等级。

### 13.6 工具默认参数和节点实例参数

必须区分：

- 工具库默认参数：`manifest.mcp_tools[].default_params`
- 节点实例参数：`root.flow.states[].tools[].params`

规则：

- 节点实例参数优先。
- 工具库默认参数是模板。
- UI 必须显示继承和覆盖关系。

### 13.7 工具不应隐藏领域状态

工具可以读领域文件，但必须通过参数声明路径。

禁止在工具内部无声明地固定读取某张卡带路径。

允许默认值，但默认值必须可覆盖，并在 schema 中可见。

---

## 14. 运行时契约

### 14.1 运行基本阶段

一次 run 至少包含：

1. 创建 run。
2. 初始化权限、环境、依赖。
3. 创建 root flow state。
4. 结构检查。
5. 输入收集。
6. 节点执行。
7. artifact 收集。
8. delivery 生成。
9. run 完成或失败。

### 14.1.1 生产基座运行前检查

生产基座即使不包含设计台和测试台，也必须在运行前做最小检查：

1. manifest 可解析。
2. root.flow 可解析。
3. `runtime_contract` 与当前基座兼容。
4. required profiles/capabilities/tools 可满足。
5. required assets 存在或可由声明的工具生成。
6. required environment/dependencies 已满足，或有明确 fallback。
7. permissions 可被用户确认。

生产基座不得在未生成兼容性报告的情况下盲目运行卡带。

### 14.2 run 状态

run 状态必须明确：

```text
created
running
completed
failed
cancelled
```

不允许节点失败但 run 仍显示完全成功，除非失败已被显式 fallback 并记录。

### 14.3 节点状态

节点状态至少包括：

```text
idle
running
completed
failed
skipped
```

### 14.4 abort_on_failed 规则

节点可以声明：

```json
{
  "abort_on_failed": true
}
```

当工具返回失败并触发 abort 时：

- 当前节点标记 failed。
- 流程停止。
- 后续持久状态节点不得执行。
- 测试台必须显示阻断原因。

### 14.5 失败不等于异常

工具可能正常执行但业务校验失败。

示例：

- `ok=true, validation_ok=false`
- `ok=true, asset_ok=false`

这也必须能触发失败策略。

### 14.6 运行事件必须可解释

事件至少应包括：

- `run_created`
- `structure_checked`
- `probe_range_selected`
- `state_entered`
- `lab_node_executed`
- `lab_node_failed`
- `lab_node_skipped`
- `run_completed`
- `run_failed`

事件命名必须稳定，不应前后端使用不同名称。

---

## 15. 测试台契约

### 15.1 测试台目的

测试台不是“点一下看能不能跑完”。

测试台必须回答：

- 是否执行到了目标节点。
- 每个节点输入是什么。
- 每个节点输出是什么。
- 数据链是否断。
- 工具是否真实执行。
- 是否触发 fallback。
- 是否产生 artifact。
- 是否有孤立节点。
- 是否有探针替身数据。

### 15.2 全流程测试

全流程测试必须：

- 从 root `start` 执行。
- 保留 fan-out/join。
- 运行所有可达主链节点。
- 生成完整 data_chain 报告。

### 15.3 探针测试

探针测试必须：

- 选择 start probe 和 end probe。
- 范围是两者之间所有路径的节点并集。
- 保留子图原始拓扑。
- 不把子图拍平成单线。
- 对范围外依赖使用 seeded keys 时必须标注。

### 15.4 探针不得证明全链路正确

局部探针通过，只说明该子图在替身上下文下可运行。

它不能证明：

- 上游真实存在。
- 下游会正确消费。
- 完整数据链无断裂。
- 持久状态安全。

测试台必须用 UI 文案明确这一点。

### 15.5 测试台通过条件

测试台“通过”至少要求：

- run 未 failed。
- 无未处理 `lab_node_failed`。
- data_chain 无真实 breaks。
- structure 无 suspicious orphan。
- abort 节点没有被错误跳过。

如果存在 fallback，可以通过，但必须显示为“通过但使用 fallback”。

### 15.6 测试台警告条件

以下情况应 warning：

- 存在 intentional isolated 节点。
- 存在 fallback。
- 存在 optional input 缺失。
- 存在探针 seeded keys。
- 存在未消费输出。
- 存在重复边。

### 15.7 测试台错误条件

以下情况应 error：

- 必需 input 缺失。
- 必需 `store:` 引用缺失。
- 未标记孤立节点。
- 工具失败且未 fallback。
- 门禁失败。
- 渲染失败但继续写状态。
- 输出声明无法生产。

---

## 16. 诊断契约

### 16.1 诊断类型

诊断至少分为：

- 结构诊断。
- 数据链诊断。
- 工具诊断。
- 运行诊断。
- Artifact 诊断。
- Fallback 诊断。
- 副作用诊断。

### 16.2 诊断严重级别

建议：

| 级别 | 含义 |
| --- | --- |
| `info` | 正常信息，例如故意隔离。 |
| `warning` | 需要注意，但不一定失败。 |
| `error` | 契约违反或运行失败。 |
| `fatal` | 流程不能继续或数据可能被污染。 |

### 16.3 诊断必须指向节点

每条诊断应包含：

- node id
- node title
- severity
- kind
- detail
- repair suggestion

### 16.4 诊断不能只在日志里

诊断必须进入测试台 UI。

命令行或 JSON 事件可以作为补充，但用户不能靠翻日志发现核心错误。

---

## 17. UI 和用户运行界面契约

### 17.1 设计台和运行界面分离

设计台用于搭流程。

运行界面用于普通用户跑卡带。

普通用户不应该面对 30 个节点的工业画布。

### 17.2 运行界面必须展示工位级进度

复杂卡带应定义 milestone：

```text
开始
入料口
资料入库
资产门禁
导演制片
质检
出片
出料口
完成
```

UI 应以工位显示状态，而不是默认暴露所有机器节点。

### 17.3 UI 节点输出规则

UI 输出应支持：

- HTML。
- Markdown。
- JSON structured view。
- artifact preview。

### 17.4 UI 不得隐藏错误

运行界面可以简化，但不能隐藏：

- 失败工位。
- 失败原因。
- fallback。
- 缺失依赖。
- 权限拒绝。
- 持久状态是否写入。

---

## 18. Artifact 契约

### 18.1 Artifact 类型

允许类型应在 manifest 中声明：

```json
{
  "artifacts": {
    "allowed_types": ["html", "json", "text", "image", "video"]
  }
}
```

### 18.2 Artifact 来源

artifact 可以来自：

- filesystem write。
- media 工具输出。
- HTML preview。
- JSON report。
- video/audio/image 文件。

工具必须通过 `path`、`files`、`preview_path` 等结构化字段暴露 artifact。

### 18.3 Artifact 生命周期

artifact 应优先 run-scoped。

除非声明为持久资产，否则不应写入卡带 assets。

### 18.4 Artifact 和持久资产区别

artifact 是某次运行产物。

asset 是卡带自带或经过审批的可复用资源。

不能把运行产物静默当作 approved asset。

---

## 19. 持久状态契约

### 19.1 持久状态定义

持久状态指 run 结束后仍会影响未来运行的数据。

示例：

- `world_state.json`
- asset manifest。
- 用户配置。
- installed cartridge。
- tool defaults。

### 19.2 持久状态写入必须显式

写持久状态必须由独立节点完成。

节点必须声明：

- 写入路径。
- 输入来源。
- 写入策略。
- 是否允许跳过。
- 是否需要上游成功。

### 19.3 失败后不得写状态

如果上游关键节点失败，持久状态节点不得执行。

例如：

- 渲染失败后不得写 `world_state.json`。
- 资产门禁失败后不得登记 approved asset。
- 远程升级失败后不得覆盖最终产物状态。

### 19.4 测试和生产状态隔离

测试运行不应默认污染生产状态。

建议：

- `test_output/` 用于运行产物。
- `.data/cartridge_runs/` 用于 run 记录。
- 卡带 assets 中的持久文件只在明确策略下修改。
- 测试台提供 dry-run 或 copy-on-write 模式。

---

## 20. 远程服务契约

### 20.1 远程服务必须显式

任何依赖外部服务的节点必须：

- 使用 `remote_call`，或
- 使用标注了 remote 副作用的 MCP 工具。

不能把远程调用伪装成本地工具。

### 20.2 远程节点必须可隔离

远程能力探索阶段必须：

```json
{
  "params": {
    "isolated": true,
    "remote_service": "comfyui"
  }
}
```

### 20.3 远程节点进入主链的条件

远程节点接入主链前必须具备：

- 参数 schema。
- 输出 schema。
- timeout。
- retry 策略。
- 失败策略。
- fallback 策略。
- QC 节点或质量判断。
- 测试样例。

### 20.4 远程服务默认值

禁止把个人临时公网地址写成默认值。

允许默认：

```text
http://127.0.0.1:8188
```

或空值加用户输入。

---

## 21. Fallback 契约

### 21.1 Fallback 是能力，不是遮羞布

Fallback 可以提高 demo 稳定性，但必须可见。

### 21.2 Fallback 必须写入结果

Fallback 后的结果必须包含：

```json
{
  "fallback": true,
  "fallback_reason": "",
  "provider": "local_fallback"
}
```

或等价字段。

### 21.3 Fallback 不能污染质量判断

使用 fallback 的 run 不能被描述成“完整真实能力通过”。

测试台应显示：

```text
通过，但使用 fallback。
```

### 21.4 Fallback 分级

| 等级 | 说明 |
| --- | --- |
| `presentation_fallback` | 只影响展示。 |
| `provider_fallback` | 换供应商或本地替代。 |
| `quality_fallback` | 质量降低但流程继续。 |
| `semantic_fallback` | 语义结果被替代，应 warning。 |

LLM 离线兜底通常属于 `semantic_fallback`，必须标记。

---

## 22. 权限、环境和依赖契约

### 22.1 权限

卡带需要访问敏感能力时必须声明权限。

示例：

- 文件写入。
- 网络访问。
- 外部命令。
- 持久状态修改。

### 22.2 环境

环境检查负责发现工具是否可用。

例如：

- `godot`
- `ffmpeg`
- `python`
- `node`

环境不可用时，流程必须知道：

- 中断。
- fallback。
- 跳过。
- 等待用户配置。

### 22.3 依赖

依赖不应隐式安装。

依赖声明应告诉用户：

- 需要什么。
- 为什么需要。
- 没有会怎样。
- 如何安装。

---

## 23. 卡带搭建流程

### 23.1 标准流程

搭卡带应按以下顺序：

1. 写卡带意图说明。
2. 定义输入输出。
3. 定义数据键。
4. 定义需要的工具。
5. 检查工具 schema。
6. 搭 root.flow。
7. 跑结构检查。
8. 跑数据链检查。
9. 跑局部探针。
10. 跑全流程。
11. 固化文档。
12. 再考虑扩展分支。

### 23.2 不允许的搭建方式

禁止：

- 一边搭卡带一边改 runner。
- 一边搭卡带一边改变测试台通过标准。
- 卡带缺什么就在 Base Core 加特例。
- 工具参数不声明 schema。
- 数据键靠 prompt 自然语言传递。
- 失败后继续写持久状态。

### 23.3 卡带文档最小要求

每张复杂卡带至少应有：

- 流程说明。
- 输入字段说明。
- 数据键表。
- 节点职责表。
- 工具表。
- 产物表。
- 已知限制。
- 测试方式。

### 23.4 流程重搭规则

如果当前流程是探索期形成的，可以保留作为经验样本。

正式重搭时应：

- 先冻结 Base Contract。
- 先定义数据键。
- 先定义工具契约。
- 再搭主链。
- 最后加探索分支。

### 23.5 开发态到生产态

一张卡带从开发基座进入生产基座前，必须经历状态转换。

建议状态：

```text
dev -> preview -> production
```

转换要求：

| 状态 | 允许情况 | 禁止情况 |
| --- | --- | --- |
| `dev` | 可以有探索节点、调试字段、测试输出 | 不得作为普通用户交付物 |
| `preview` | 可以演示主链，允许少量 fallback | 不得隐瞒未冻结能力 |
| `production` | 可在符合协议的生产基座运行 | 不得依赖设计台、探针、未声明私有扩展 |

### 23.6 生产交付包检查

生产交付包必须通过：

- `runtime_contract` 检查。
- `delivery_readiness.level=production`。
- 无未标记孤立节点。
- 无真实数据链断裂。
- required tools 完整。
- required assets 完整。
- required environment 有明确处理策略。
- 持久状态写入策略明确。

如果生产基座不支持测试台，它仍然必须能读取开发基座生成的交付检查报告，或自行生成兼容性报告。

---

## 24. Base Contract 变更流程

### 24.1 什么时候提交变更

以下情况应提交 Base Contract 变更：

- 多张卡带重复遇到同一限制。
- 某个实现行为已经事实成为底座能力，但文档未定义。
- 测试台无法表达某类真实错误。
- 工具契约无法描述某类工具。
- 需要新增节点类别或 action。

### 24.2 变更单内容

每个变更单必须包含：

```text
标题
背景
当前限制
影响的卡带
提议规则
兼容性
迁移方案
测试矩阵
拒绝方案
```

### 24.3 通过标准

变更通过前必须回答：

- 是否破坏旧卡带？
- 是否有兼容模式？
- 是否影响测试台判断？
- 是否影响 runner 语义？
- 是否影响工具 schema？
- 是否已更新参考卡带？

### 24.4 禁止暗改

任何改变底座语义的代码改动，都必须对应文档变更。

没有文档的底座行为，不能被视为稳定契约。

---

## 25. 参考卡带和测试矩阵

### 25.1 参考卡带

建议固定三类参考卡带：

| 卡带 | 用途 |
| --- | --- |
| `dev.file_summary` | 最小 AI + filesystem + UI 闭环。 |
| `dev.multi_file_summary` | 多输入、多文件、多结果。 |
| `dev.pixel_episode_director` | 复杂分支、media 工具、artifact、持久状态、远程隔离。 |

### 25.2 每次底座改动必须测试

至少测试：

- Python 语法。
- 前端构建。
- manifest/root.flow 校验。
- 数据链诊断。
- 探针子图。
- MCP schema 渲染。
- artifact 收集。

### 25.3 测试矩阵

| 能力 | file_summary | multi_file_summary | pixel_episode_director |
| --- | --- | --- | --- |
| collect_inputs | 必测 | 必测 | 必测 |
| llm_prompt | 必测 | 必测 | 必测 |
| tool_call | 必测 | 必测 | 必测 |
| fan-out/join | 可选 | 建议 | 必测 |
| artifact | 必测 | 必测 | 必测 |
| remote_call | 不测 | 不测 | 隔离测试 |
| persistent state | 不测 | 不测 | 必测 |
| fallback | 建议 | 建议 | 必测 |

---

## 26. 常见反模式

### 26.1 为单张卡带改底座

表现：

- runner 里出现具体卡带 ID。
- executor 识别某个领域字段。
- 测试台为某张卡带隐藏 warning。

处理：

- 移回卡带配置。
- 移入工具包。
- 或提交 Base Contract 变更。

### 26.2 AI 节点空转

表现：

- AI 节点输出没人消费。
- 下游工具仍使用硬编码参数。
- prompt 只是在流程图上增加仪式感。

处理：

- 让 AI 输出结构化 JSON 并被工具消费。
- 或删掉 AI 节点，用 transfer/tool 直连。

### 26.3 工具无 schema

表现：

- UI 只能显示 JSON textarea。
- 用户不知道参数含义。
- 参数真实契约散落在函数体。

处理：

- 工具注册表导出 schema。
- 前端字段化渲染。
- 节点实例显示覆盖关系。

### 26.4 可选输入伪装成必需输入

表现：

- `input` 写了多个 key。
- 某些 key 经常不存在。
- 执行器静默跳过。

处理：

- 引入 `optional_input`。
- 测试台区分 optional missing 和 data chain break。

### 26.5 Fallback 假装成功

表现：

- 没有真实 provider，却显示成功。
- 产物质量降低但 UI 不提示。

处理：

- 输出 provider/fallback 字段。
- 测试台显示 fallback warning。

### 26.6 探针通过冒充全流程通过

表现：

- 局部探针 seeded 了上游数据。
- UI 只显示通过。

处理：

- 显示 seeded keys。
- 明确局部探针不证明真实上游。

### 26.7 持久状态被测试污染

表现：

- 测试多次写入 world_state。
- episode history 重复堆积。

处理：

- 测试模式 copy-on-write。
- 持久写入节点显式确认。
- dry-run。

### 26.8 把规范等同于当前实现

表现：

- 认为当前 Python/FastAPI/React 基座就是规范本身。
- 新规范只是在当前代码上继续打补丁。
- 卡带写法隐含依赖当前实现的私有行为。

处理：

- 区分 Base Contract 和 Base Implementation。
- 为当前实现补 base implementation manifest。
- 卡带只声明 contract/profile/capability/tool 依赖。
- 依赖私有行为时必须 `implementation_lock`。

### 26.9 只看规范版本就声称兼容

表现：

- 两个基座都写“支持 v0.1”，就默认能跑所有 v0.1 卡带。
- 忽略 tool packs、capabilities、profiles。
- 缺少 media/remote/testbench 能力时才在运行中失败。

处理：

- 兼容判断必须同时检查 Contract、Profile、Capability、Tool Contract。
- 基座能力必须通过 conformance tests 后才能声明。
- 货架运行前必须生成 compatibility report。

### 26.10 把开发态卡带直接交付给用户

表现：

- 卡带只能在 FlowWorkbench 里跑。
- 卡带依赖探针 seeded 数据。
- 卡带依赖设计台缓存文件。
- 用户必须看节点图才知道怎么运行。
- 生产环境缺少设计台就无法启动。

处理：

- 增加 `delivery_readiness`。
- 交付前跑生产交付包检查。
- 生产基座只依赖 runtime_contract 和 manifest inputs。
- 探索节点转 isolated 或移除。
- 用户运行入口收敛到货架/运行界面。

### 26.11 生产基座偷偷要求开发能力

表现：

- 名义上是生产运行时，但启动卡带时要求设计台。
- 运行失败后只能让用户打开测试台排查。
- 生产环境依赖编辑器才能绑定工具。

处理：

- 生产基座只声明 `runtime_core/shelf_runner` 等真实支持能力。
- 缺少工具或能力时在兼容性报告阶段阻断。
- 调试和编辑留在开发基座。

---

## 27. 当前实现对齐状态

本节用于区分“当前已经具备的基底能力”和“Base Contract v0.1 要求但尚未完全实现的能力”。这能避免把目标误当现状，也能防止后续为了某张卡带临时补洞。

### 27.1 已经基本具备的能力

当前项目已经具备以下基底雏形：

| 能力 | 当前状态 | 说明 |
| --- | --- | --- |
| 卡带发现和加载 | 已具备 | `CartridgeRegistry` 可加载 dev/installed/builtin 卡带。 |
| manifest 基础校验 | 已具备 | 已校验必需字段、root flow、mcp_tools 基础结构。 |
| root.flow 执行 | 已具备 | `RootFlowEngine` 支持 next、edges、fan-out/join。 |
| 节点分发执行 | 已具备 | `LabNodeExecutor` 支持 UI、LLM、tool、remote、transfer 等 action。 |
| 结构检查 | 已具备雏形 | 可识别 unreachable 节点，并区分 `isolated=true`。 |
| 数据链体检 | 已具备雏形 | 执行器能记录 missing input/store refs，runner 能汇总。 |
| 探针子图 | 已具备雏形 | 探针范围保留分支并集和子图拓扑。 |
| MCP params schema | 已具备雏形 | 后端可从内置工具描述生成 schema，前端可字段化渲染。 |
| artifact 收集 | 已具备 | filesystem/media 工具结果可被收集为 artifact。 |
| remote 隔离标记 | 已具备雏形 | `params.isolated=true` 已可被结构检查识别。 |
| abort_on_failed | 已具备 | 工具节点失败可触发流程中断。 |

### 27.2 尚未完全实现但应进入 v0.1 收敛的能力

以下能力是本文规范要求或强烈建议，但当前实现可能尚未完整：

| 能力 | 缺口 | 建议优先级 |
| --- | --- | --- |
| `base_contract` manifest 字段 | 卡带尚未声明依赖契约版本。 | P0 |
| base implementation manifest | 当前基座尚未声明自己的 supported contracts/profiles/capabilities/tool packs。 | P0 |
| `runtime_contract` 兼容检查 | 加载卡带时尚未生成机器可读 compatibility report。 | P0 |
| `delivery_readiness` | 卡带尚未声明 dev/preview/production 交付状态。 | P0 |
| 生产基座运行前检查 | 生产环境尚未形成独立于设计台的最小兼容检查流程。 | P0 |
| `optional_input` | 可选输入尚未从必需 input 中分离。 | P0 |
| base conformance tests | 尚未形成跨基座一致性测试套件。 | P1 |
| result schema | 工具主要只有 params schema，输出契约未系统化。 | P1 |
| 工具副作用等级 | 工具没有统一声明 read/write/remote/persistent。 | P1 |
| 节点实例参数继承 UI | MCP 面板仍需更清楚地区分默认参数和节点覆盖参数。 | P1 |
| fallback 统一结构 | 不同工具的 fallback 字段口径还不统一。 | P1 |
| 持久状态 dry-run | 测试台尚不能完全避免污染持久状态文件。 | P1 |
| 运行界面工位化 | 复杂卡带仍主要面对节点级测试界面。 | P2 |
| event 命名清理 | 个别旧事件名/新事件名需要统一。 | P2 |
| Base Contract RFC 模板 | 尚未形成独立模板文件。 | P2 |

### 27.3 当前卡带不得倒逼底座补特例

在上述缺口补齐前，具体卡带不得通过临时改 core 绕过规范。

例如：

- 可选输入未实现时，可以先在卡带文档中标注，但不能让执行器静默吞掉所有缺失输入。
- result schema 未实现时，可以先在工具描述中写明输出字段，但不能让前端假装工具已完全可解释。
- dry-run 未实现时，测试会污染持久状态的问题必须在测试说明里显式提醒，不能把它当正常生产语义。

### 27.4 当前实现和规范冲突时的处理

如果当前实现与本文发生冲突，应按以下顺序处理：

1. 判断本文是否过度设计或不符合实际。
2. 如果是文档问题，修改本文并记录版本。
3. 如果是实现问题，提交实现改动并补测试。
4. 如果是卡带问题，改卡带，不改底座。
5. 如果无法判断，先写变更单，不直接改 core。

---

## 28. v0.1 收敛路线

### 28.1 第一阶段：冻结规则

产物：

- 本文档。
- Base Contract 版本号。
- 卡带搭建流程。
- 变更流程。

验收：

- 团队在搭新卡带前先读本文。
- 不再随单张卡带改底座。

### 28.2 第二阶段：补 manifest 字段

建议新增：

```json
{
  "base_contract": "0.1",
  "manifest_schema_version": "1.0",
  "flow_schema_version": "1.0"
}
```

同时新增基座实现清单，例如：

```text
BASE_IMPLEMENTATION.json
```

用于声明当前基座支持的 contracts、profiles、capabilities 和 tool packs。

### 28.2.1 第二阶段补充：兼容性报告

实现卡带加载时的 compatibility report：

- contract 是否匹配。
- required profiles 是否匹配。
- required capabilities 是否匹配。
- required tools 是否匹配。
- implementation lock 是否匹配。
- 缺失能力是阻断还是降级。

### 28.2.2 第二阶段补充：交付状态

实现 `delivery_readiness`：

- `dev`：开发卡带。
- `preview`：演示卡带。
- `production`：生产交付卡带。

生产基座默认只直接运行 `production`，对 `dev/preview` 给出确认或拒绝。

### 28.3 第三阶段：补可选输入契约

实现：

- `optional_input`
- 测试台 optional missing warning
- data_chain 不把 optional missing 视为 error

### 28.4 第四阶段：补 result_schema

工具契约从 params schema 扩展到 result schema。

### 28.5 第五阶段：补基座一致性测试

新增 `base_conformance_tests`：

- 线性流程。
- fan-out/join。
- context store。
- abort_on_failed。
- artifact。
- isolated node。
- probe subgraph。
- tool schema。

只有通过对应测试的基座，才能声明支持对应 capability。

### 28.6 第六阶段：运行界面工位化

复杂卡带运行时显示 milestone，而不是暴露全部节点。

### 28.7 第七阶段：持久状态 dry-run

测试台支持不污染持久状态的运行方式。

---

## 附录 A：规范关键词

本文使用以下关键词：

- 必须：强制规则，不满足就是契约违反。
- 不得：禁止行为。
- 应该：强建议，除非有明确理由。
- 可以：允许行为。
- 建议：非强制，但推荐。

---

## 附录 B：节点类型速查表

| action | category | 是否允许副作用 | 是否需要上游 process | 说明 |
| --- | --- | --- | --- | --- |
| `start` | system | 否 | 否 | 起点。 |
| `collect_inputs` | input | 写 store | 否 | 用户输入入库。 |
| `show_ui` | ui | 写 UI store | 否 | 展示。 |
| `llm_prompt` | process | 写 store | 否 | AI 处理。 |
| `tool_call` | tool | 视工具而定 | 是 | 本地/内置工具。 |
| `remote_call` | remote | 是 | 是，隔离节点除外 | 外部服务。 |
| `pass_result` | transfer | 写 store | 否 | 数据传递。 |
| `custom_action` | placeholder | 否 | 否 | 占位，不应进主生产。 |

---

## 附录 C：卡带评审清单

### C.1 基础信息

- [ ] manifest 有稳定 ID。
- [ ] manifest 有版本号。
- [ ] root.flow 有 start。
- [ ] root.flow 有 terminal。
- [ ] welcome UI 可读。

### C.2 数据链

- [ ] 每个关键节点声明 input。
- [ ] 每个关键节点声明 output。
- [ ] input 都有上游生产者。
- [ ] optional input 已单独声明。
- [ ] 没有靠 prompt 口头传递的数据。

### C.3 工具

- [ ] 每个工具有 params_schema。
- [ ] 每个工具有默认参数。
- [ ] 每个工具有失败结构。
- [ ] 工具副作用明确。
- [ ] 节点实例参数和工具默认参数可区分。

### C.4 拓扑

- [ ] fan-out/join 语义明确。
- [ ] 无未标记孤立节点。
- [ ] 探索节点已 isolated。
- [ ] 重复边已清理或可解释。

### C.5 运行

- [ ] 门禁节点有失败策略。
- [ ] 渲染/合成类节点失败会中断或显式 fallback。
- [ ] 持久状态写入在最后阶段。
- [ ] 失败后不会继续写状态。

### C.6 测试

- [ ] 全流程测试通过。
- [ ] 局部探针测试覆盖关键子图。
- [ ] data_chain 无真实 breaks。
- [ ] structure 无 suspicious orphan。
- [ ] fallback 被明确显示。

### C.7 文档

- [ ] 有流程说明。
- [ ] 有节点职责表。
- [ ] 有数据键表。
- [ ] 有工具表。
- [ ] 有产物路径表。
- [ ] 有已知限制。

---

## 结语

CartridgeFlow 的底座应该像一台稳定的卡带机，而不是每插入一张新卡带就重新改主板。

卡带可以探索，工具可以扩展，流程可以重搭，但 Base Contract 必须可版本化、可审查、可迁移。

v0.1 的核心不是把所有事情一次规定完，而是先立住一条底线：

> 任何流程都不能为了自己短期跑通，悄悄改变整套系统的基础语义。
