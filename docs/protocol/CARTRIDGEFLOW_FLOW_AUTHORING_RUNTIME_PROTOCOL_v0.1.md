# CartridgeFlow Flow Authoring and Runtime Protocol v0.1

协议编号：CF-FARP-0.1

状态：Draft

发布日期：2026-07-16

适用对象：流程设计者、卡带开发者、工具包开发者、基座实现者、生产运行时实现者、测试台实现者。

适用范围：CartridgeFlow 卡带中的流程搭建、流程校验、流程运行、流程诊断、流程交付。

上位文件：`CartridgeFlow Base Contract v0.1`

本文性质：规范性文件。除非明确标注为“建议”或“示例”，本文中的“必须”“不得”“应当”均为协议要求。

---

## 目录

1. [协议定位](#1-协议定位)
2. [规范关键词](#2-规范关键词)
3. [实体定义](#3-实体定义)
4. [适用范围和非目标](#4-适用范围和非目标)
5. [合规对象](#5-合规对象)
6. [协议版本](#6-协议版本)
7. [流程搭建总原则](#7-流程搭建总原则)
8. [开发态和生产态](#8-开发态和生产态)
9. [流程文件结构](#9-流程文件结构)
10. [Manifest 运行声明](#10-manifest-运行声明)
11. [Root Flow 结构](#11-root-flow-结构)
12. [节点通用规则](#12-节点通用规则)
13. [节点类型规则](#13-节点类型规则)
14. [边和拓扑规则](#14-边和拓扑规则)
15. [数据链规则](#15-数据链规则)
16. [工具调用规则](#16-工具调用规则)
17. [远程调用规则](#17-远程调用规则)
18. [UI 节点规则](#18-ui-节点规则)
19. [Artifact 规则](#19-artifact-规则)
20. [持久状态规则](#20-持久状态规则)
21. [权限、环境和依赖规则](#21-权限环境和依赖规则)
22. [运行前检查](#22-运行前检查)
23. [运行时执行规则](#23-运行时执行规则)
24. [失败、中断和回退规则](#24-失败中断和回退规则)
25. [事件和诊断规则](#25-事件和诊断规则)
26. [测试和探针规则](#26-测试和探针规则)
27. [交付规则](#27-交付规则)
28. [兼容性规则](#28-兼容性规则)
29. [协议认证规则](#29-协议认证规则)
30. [禁止行为](#30-禁止行为)
31. [合规检查清单](#31-合规检查清单)
32. [一致性测试要求](#32-一致性测试要求)
33. [附录 A：标准字段参考](#附录-a标准字段参考)
34. [附录 B：节点类型矩阵](#附录-b节点类型矩阵)
35. [附录 C：错误等级](#附录-c错误等级)
36. [附录 D：覆盖矩阵](#附录-d覆盖矩阵)

---

## 1. 协议定位

### 1.1 本协议的目的

本协议规定 CartridgeFlow 中“流程搭建”和“流程运行”必须遵守的基础规则。

本协议的核心目标是：

- 使流程可以在开发基座中被规范搭建。
- 使流程可以在生产基座中被可靠运行。
- 使卡带不依赖某个具体基座实现的私有行为。
- 使同一协议版本下的不同基座能够运行共同支持范围内的卡带。
- 使流程错误可以被静态检查、运行时事件和测试台诊断准确暴露。

### 1.2 本协议与 Base Contract 的关系

Base Contract 定义 CartridgeFlow 的总体契约、基座可替换原则、能力协商和版本治理。

本协议是 Base Contract 下的第一份具体子协议，专门约束：

- 如何搭建流程。
- 如何声明流程。
- 如何运行流程。
- 如何诊断流程。
- 如何把开发态流程交付为生产态卡带。

### 1.3 本协议不绑定具体实现

本协议不绑定：

- Python。
- FastAPI。
- React。
- 当前 FlowWorkbench。
- 当前 Runner。
- 当前 TestBench。

任何基座实现只要通过本协议要求的一致性测试，即可声明支持本协议。

### 1.4 本协议的严肃性

本协议不是建议文档。

流程设计者不得以“某个卡带临时需要”为理由绕过本协议。

基座实现者不得以“当前实现方便”为理由改变本协议语义。

工具开发者不得以“工具内部知道怎么处理”为理由省略 schema、失败结构和副作用声明。

---

## 2. 规范关键词

本文使用以下规范关键词：

| 关键词 | 含义 |
| --- | --- |
| 必须 | 强制要求。不满足即不符合协议。 |
| 不得 | 明确禁止。出现即为协议违规。 |
| 应当 | 默认要求。只有在有书面理由且不破坏协议目的时才可偏离。 |
| 可以 | 允许行为。 |
| 建议 | 非强制，但推荐作为默认实践。 |

英文语义对应：

- 必须：MUST
- 不得：MUST NOT
- 应当：SHOULD
- 可以：MAY

---

## 3. 实体定义

### 3.1 卡带

卡带是可被 CartridgeFlow 基座加载、校验、运行和交付的流程包。

卡带至少包含：

- `manifest.json`
- `root.flow.json`
- `assets/`

### 3.2 基座

基座是实现 CartridgeFlow 协议的运行环境。

基座可以是：

- 开发基座。
- 生产基座。
- 桌面基座。
- 服务端基座。
- 测试基座。

### 3.3 开发基座

开发基座用于搭建、调试、测试和打包卡带。

开发基座可以包含：

- 设计台。
- 测试台。
- 探针。
- 节点编辑。
- MCP 工具编辑。
- 诊断面板。

### 3.4 生产基座

生产基座用于最终用户运行卡带。

生产基座不要求支持设计台、节点编辑或探针，但必须支持卡带声明的运行协议、能力和工具契约。

### 3.5 流程

流程是由节点和边组成的有向执行图。

流程在 `root.flow.json` 中声明。

### 3.6 节点

节点是流程中的最小执行单元。

节点必须有唯一 ID，并应声明：

- 类型。
- 动作。
- 输入。
- 输出。
- 参数。
- 布局。
- 下一节点或边。

### 3.7 边

边表示节点之间的控制流关系。

边可以由 `next` 或 `edges` 表达。

### 3.8 Store

Store 是一次运行中的共享数据空间。

所有节点间数据传递必须通过 `context.store` 或协议等价机制完成。

### 3.9 工具

工具是由工具包提供的可调用能力。

工具必须具有参数 schema、输出 schema、失败结构和副作用声明。

### 3.10 Artifact

Artifact 是一次运行产生的可交付产物。

Artifact 可以是文本、JSON、HTML、图片、视频、音频或其他被 manifest 允许的类型。

### 3.11 持久状态

持久状态是运行结束后仍会影响后续运行的数据。

示例：

- `world_state.json`
- asset manifest
- 用户配置
- installed cartridge registry

---

## 4. 适用范围和非目标

### 4.1 适用范围

本协议适用于：

- 新建卡带流程。
- 修改已有卡带流程。
- 运行卡带流程。
- 生产基座加载卡带。
- 测试台诊断卡带。
- 工具包接入流程。
- 开发态卡带转为生产态卡带。

### 4.2 非目标

本协议不规定：

- 某个具体领域流程如何设计。
- UI 具体视觉样式。
- LLM prompt 的写作风格。
- 某个工具内部算法。
- 某个视频、图像、报告、游戏卡带的业务质量标准。

上述内容应由领域卡带规范或工具包规范补充。

---

## 5. 合规对象

### 5.1 流程合规

一个流程符合本协议，必须满足：

- `root.flow.json` 结构合法。
- 节点和边符合本协议。
- 数据链可解释。
- 工具调用可解释。
- 失败策略明确。
- 无未声明副作用。
- 无未标记孤立节点。

### 5.2 卡带合规

一个卡带符合本协议，必须满足：

- manifest 声明运行契约。
- root flow 符合流程合规要求。
- required tools 可被解析。
- required assets 可被定位。
- delivery 输出可被解释。
- 生产态卡带不依赖开发基座私有能力。

### 5.3 基座合规

一个基座符合本协议，必须满足：

- 声明支持的协议版本。
- 声明支持的 profiles。
- 声明支持的 capabilities。
- 声明支持的 tool packs。
- 通过一致性测试。
- 不改变协议语义。

### 5.4 工具包合规

一个工具包符合本协议，必须满足：

- 工具可枚举。
- 工具参数 schema 可导出。
- 工具输出 schema 可导出或至少文档化。
- 工具失败结构稳定。
- 工具副作用可声明。
- 工具版本可判断。

---

## 6. 协议版本

### 6.1 当前版本

当前版本为：

```text
CF-FARP-0.1
```

对应 Base Contract：

```text
CartridgeFlow Base Contract v0.1
```

### 6.2 版本兼容

基座不得仅凭协议主版本相同即假定完全兼容。

兼容性必须同时检查：

- 协议版本。
- required profiles。
- required capabilities。
- required tool packs。
- tool contract versions。
- implementation lock。

### 6.3 版本升级

协议升级必须提供：

- 变更说明。
- 兼容性说明。
- 迁移规则。
- 一致性测试更新。
- 示例卡带更新。

---

## 7. 流程搭建总原则

### 7.1 先声明，再实现

搭建流程时，必须先声明：

- 输入。
- 输出。
- 数据键。
- 节点职责。
- 工具需求。
- 失败策略。
- 交付产物。

不得先堆节点，再让底座去适配该流程。

### 7.2 不得边搭流程边改协议语义

在搭建某张卡带时，不得直接修改：

- flow 执行顺序语义。
- fan-out/join 语义。
- input/output 解析语义。
- tool_call 执行语义。
- 探针语义。
- 测试台通过标准。

如确需修改，必须先提交协议变更。

### 7.3 流程不应依赖隐式上下文

流程不得依赖：

- 设计台当前选中节点。
- 测试台临时状态。
- 开发者本地缓存。
- 某个基座私有变量。
- 未声明环境变量。

所有运行依赖必须进入 manifest、root flow、assets 或 tool contract。

### 7.4 主链和探索分支必须分离

主链必须代表默认生产路径。

探索分支必须：

- 标记为 isolated，或
- 放入 branch，或
- 保持不可执行，或
- 放入单独开发卡带。

探索分支不得静默影响主链结果。

---

## 8. 开发态和生产态

### 8.1 开发态

开发态流程允许：

- 节点仍在调整。
- 工具契约仍在细化。
- 存在 isolated 探索节点。
- 使用测试台探针。
- 使用调试输出。

开发态流程不得被标记为生产交付卡带。

### 8.2 生产态

生产态流程必须：

- 能由生产基座加载。
- 能通过 compatibility report。
- 不依赖设计台。
- 不依赖测试台。
- 不依赖探针 seeded keys。
- 不依赖未打包 assets。
- 不依赖未声明工具。
- 不依赖未声明外部服务。

### 8.3 交付状态

卡带应声明：

```json
{
  "delivery_readiness": {
    "level": "dev | preview | production"
  }
}
```

生产基座可以拒绝运行 `dev` 卡带。

生产基座运行 `preview` 卡带时，应提示能力未完全冻结。

生产基座运行 `production` 卡带前，必须进行运行前检查。

---

## 9. 流程文件结构

### 9.1 必需文件

卡带必须包含：

```text
manifest.json
root.flow.json
assets/
```

### 9.2 `manifest.json`

manifest 必须声明卡带身份、运行契约、输入、输出、工具、依赖、artifact 和交付策略。

### 9.3 `root.flow.json`

root flow 必须声明可执行流程图。

root flow 不得作为纯设计稿使用。

### 9.4 `assets/`

assets 必须包含卡带运行所需的静态资源。

生产态卡带不得依赖 assets 外部的开发临时文件。

---

## 10. Manifest 运行声明

### 10.1 `runtime_contract`

生产态卡带必须声明 `runtime_contract` 或协议等价字段。

推荐结构：

```json
{
  "runtime_contract": {
    "contract": "cartridgeflow.base",
    "version": ">=0.1 <0.2",
    "required_profiles": ["runtime_core"],
    "recommended_profiles": ["testbench_core"],
    "required_capabilities": {
      "flow.next_edges": ">=0.1",
      "runtime.context_store": ">=0.1"
    },
    "required_tools": [],
    "optional_tools": [],
    "implementation_lock": null
  }
}
```

### 10.2 required profiles

卡带必须只声明自己运行所需的 profile。

生产态卡带不得无故要求 `lab_designer`。

### 10.3 required capabilities

卡带必须声明自身运行所需 capability。

如果流程使用 fan-out/join，则必须要求：

```text
flow.fanout_join
```

如果流程使用 remote_call，则必须要求：

```text
runtime.remote_call
```

### 10.4 required tools

卡带必须声明运行必需工具。

工具声明至少包括：

- server
- tool
- contract version

### 10.5 implementation lock

卡带不得默认锁定具体基座实现。

如果卡带依赖基座私有扩展，必须声明 `implementation_lock`，并不得标记为通用可移植卡带。

---

## 11. Root Flow 结构

### 11.1 必需字段

root flow 必须包含：

```json
{
  "schema_version": "1.0",
  "id": "example.root",
  "name": "Example Root Flow",
  "mode": "lifecycle",
  "cartridge_id": "example",
  "start": "start",
  "states": {},
  "edges": []
}
```

### 11.2 start

`start` 必须指向存在的节点。

生产态流程必须能从 `start` 到达至少一个 terminal 节点。

### 11.3 states

`states` 必须是对象。

每个 key 是节点 ID。

节点 ID 在同一 root flow 中必须唯一。

### 11.4 edges

`edges` 必须是数组。

每条边必须指向存在的 source 和 target。

### 11.5 layout

layout 仅用于显示。

运行时不得依赖 layout 判断执行顺序。

---

## 12. 节点通用规则

### 12.1 节点最小结构

每个节点应包含：

```json
{
  "type": "runtime",
  "title": "Node Title",
  "action": "tool_call",
  "params": {},
  "next": "next_node"
}
```

### 12.2 节点 ID

节点 ID 必须：

- 在流程内唯一。
- 稳定。
- 可读。
- 使用英文、数字、下划线。

不得使用临时编号作为长期 ID。

### 12.3 节点标题

节点标题用于 UI 展示，不得作为运行语义。

### 12.4 节点职责

每个节点必须职责单一。

不得在同一节点中混合：

- AI 判断。
- 工具执行。
- UI 展示。
- 持久状态写入。
- 远程调用。

### 12.5 input/output

除 `start`、纯 UI 欢迎节点和 terminal 节点外，关键节点必须声明 input/output 或协议等价字段。

---

## 13. 节点类型规则

### 13.1 system 节点

system 节点用于启动或生命周期控制。

system 节点不得执行业务工具。

### 13.2 input 节点

input 节点负责把 manifest inputs 写入 store。

input 节点必须声明输出 key。

### 13.3 process 节点

process 节点负责判断、规划或生成结构化指令。

process 节点不得直接执行工具副作用。

process 节点输出如果供工具消费，应当是结构化文本或 JSON。

### 13.4 tool 节点

tool 节点负责执行工具。

tool 节点必须：

- 绑定工具。
- 声明工具参数。
- 声明输出 key。
- 声明失败策略。

tool 节点不得承担 AI 决策职责。

### 13.5 remote 节点

remote 节点负责调用外部服务。

remote 节点必须声明：

- remote service。
- timeout 或等价控制。
- 失败策略。
- 是否 isolated。

### 13.6 transfer 节点

transfer 节点只能搬运、合并、重命名 store 数据。

transfer 节点不得调用工具或远程服务。

### 13.7 gate 节点

gate 节点负责门禁或质检。

gate 节点必须返回结构化通过/失败结果。

gate 节点必须声明失败是否中断。

### 13.8 ui 节点

ui 节点负责展示或收集。

ui 节点不得修改持久状态。

### 13.9 terminal 节点

terminal 节点表示流程结束。

terminal 节点不得再有默认生产出边。

### 13.10 placeholder 节点

placeholder 节点仅用于设计占位。

生产态主链不得依赖 placeholder 节点。

### 13.11 human_gate 节点

需要人工确认、人工选择或人工审批的节点必须声明为 human gate 或协议等价节点。

human gate 节点必须声明：

- 提示文本。
- 需要用户确认的数据。
- 用户可选择的动作。
- 默认超时策略。
- 拒绝或超时后的流程行为。

生产基座如果不支持人工交互，不得运行要求 human gate 的卡带，除非卡带声明了自动策略。

---

## 14. 边和拓扑规则

### 14.1 next

`next` 表示主出边。

如果节点无 `next`，可以通过 `edges` 表示出边。

### 14.2 edges

`edges` 表示显式边集合。

同一 source/target 重复声明时，基座必须去重或报 warning。

### 14.3 fan-out

一个节点可以有多个下游。

fan-out 表示多个分支均应执行，除非分支被条件或隔离规则排除。

### 14.4 join

多个父节点汇入同一节点时，join 节点必须等待所有父节点完成。

不得只因第一条路径到达就执行 join。

### 14.5 cycle

v0.1 默认不支持无限循环。

如果存在循环，必须由专门的循环协议声明最大次数、退出条件和状态写入规则。

未声明循环不得进入生产态。

### 14.6 isolated

不可从 start 到达的节点必须标记：

```json
{
  "params": {
    "isolated": true
  }
}
```

未标记 isolated 的不可达节点必须作为结构问题报告。

### 14.7 条件分支

v0.1 默认不允许隐式条件分支。

如果流程需要条件分支，必须显式声明：

- 条件来源。
- 条件表达式或选择器。
- 可达分支。
- 默认分支。
- 未匹配时的行为。

不得通过工具返回某个私有字段，让 runner 以未声明方式改变执行路径。

### 14.8 分支互斥

fan-out 默认表示所有分支均执行。

如果多个分支是互斥关系，必须使用条件分支协议声明。

不得把互斥分支伪装成 fan-out 后再依赖工具内部跳过。

---

## 15. 数据链规则

### 15.1 store 是唯一数据总线

节点间数据必须通过 store 或协议等价机制传递。

不得通过未声明全局变量传递业务数据。

### 15.2 必需输入

`input` 中声明的 key 为必需输入。

运行时缺失必需输入必须记录 data chain break。

### 15.3 可选输入

可选输入必须单独声明。

推荐：

```json
{
  "optional_input": "comfy_upgrade_bundle"
}
```

可选输入缺失不得被当作数据链断裂，但必须可见。

### 15.4 输出

节点产出的关键数据必须写入 output 指定的 key。

声明 output 但未写入，应当被诊断。

### 15.5 store 引用

工具参数可以引用：

```text
store:key
store:key.field
```

引用缺失必需 key 必须被记录。

### 15.6 数据形状

关键 store key 应当有 schema 或文档说明。

例如：

- `episode_brief` 是用户输入对象。
- `asset_check_report` 是门禁报告。
- `render_bundle` 是渲染产物包。

### 15.7 不得静默跳过

基座不得把必需输入缺失静默视为正常成功。

---

## 16. 工具调用规则

### 16.1 工具必须有契约

工具必须声明：

- server。
- tool。
- 参数 schema。
- 输出结构。
- 失败结构。
- 副作用。
- 版本。

### 16.2 工具库默认值

manifest 中的 tool default params 是模板默认值。

### 16.3 节点实例参数

root flow 中的 tool params 是节点实例参数。

节点实例参数优先于工具库默认值。

### 16.4 工具结果

工具结果必须包含 `ok` 或协议等价字段。

失败时必须包含 `error` 或结构化 issues。

### 16.5 工具副作用

工具必须声明副作用等级。

常见等级：

- read
- write_artifact
- write_workspace
- write_persistent_state
- remote

### 16.6 工具不得修改协议语义

工具不得通过返回特殊私有字段改变流程调度语义。

### 16.7 工具幂等性

工具应声明是否幂等。

幂等工具在同一输入下重复执行，不应造成额外持久副作用。

非幂等工具必须声明：

- 会产生什么副作用。
- 是否允许重试。
- 重试时如何避免重复写入。

### 16.8 工具重试

工具重试必须由节点或工具契约显式声明。

不得由基座对所有工具无差别自动重试。

写持久状态、扣费、调用外部生成服务等非幂等工具，默认不得自动重试。

### 16.9 工具超时

长时间工具必须声明 timeout 或接受基座默认 timeout。

超时必须返回结构化失败，不得让 run 无限挂起。

---

## 17. 远程调用规则

### 17.1 remote_call

外部服务调用必须使用 `remote_call` 或标记为 remote 的工具。

### 17.2 远程服务声明

远程节点必须声明：

- 服务名称。
- URL 或服务发现方式。
- 凭据来源。
- timeout。
- retry。
- fallback。

### 17.3 远程探索

远程能力未稳定前必须 isolated。

### 17.4 远程结果

远程结果必须说明：

- 是否真实调用远程。
- provider。
- request id 或 trace id。
- 输出文件。
- 失败原因。

### 17.5 远程凭据

远程服务凭据不得写入卡带包。

凭据必须来自：

- 用户配置。
- 生产基座安全凭据存储。
- 环境变量。
- 运行时一次性输入。

如果生产基座无法提供凭据，必须在运行前检查阶段阻断或进入明确 fallback。

### 17.6 远程可审计性

远程调用应记录：

- 服务名。
- provider。
- request id。
- 调用时间。
- 成功或失败。
- 产物位置。

不得记录明文密钥。

---

## 18. UI 节点规则

### 18.1 UI 职责

UI 节点负责用户交互和展示。

UI 节点不得承担工具执行或持久状态写入。

### 18.2 欢迎 UI

欢迎 UI 可以作为第一可运行 UI 节点。

欢迎 UI 不得改变业务 store。

### 18.3 结果 UI

结果 UI 必须读取已存在结果 key。

结果 UI 不得伪造核心产物。

### 18.4 生产运行界面

生产运行界面应展示：

- 输入表单。
- 运行状态。
- 失败原因。
- fallback。
- artifact。
- delivery。

生产运行界面不应要求用户理解完整节点图。

---

## 19. Artifact 规则

### 19.1 Artifact 声明

manifest 必须声明允许的 artifact 类型。

### 19.2 Artifact 产生

工具产生 artifact 时，必须在结果中暴露路径或文件清单。

### 19.3 Artifact 范围

artifact 默认属于一次 run。

不得把 run artifact 静默登记为长期 approved asset。

### 19.4 Artifact 交付

delivery 必须能解释最终交付给用户的 artifact。

---

## 20. 持久状态规则

### 20.1 持久状态写入

持久状态写入必须由明确节点完成。

### 20.2 写入前提

持久状态写入前，上游关键节点必须成功。

### 20.3 失败保护

流程失败后不得继续写持久状态。

### 20.4 测试污染

测试运行不得默认污染生产持久状态。

如果当前基座不支持 dry-run，必须在测试说明和诊断中标记风险。

### 20.5 审计

持久状态写入应记录：

- 写入节点。
- 写入路径。
- 写入前摘要。
- 写入后摘要。
- run id。

---

## 21. 权限、环境和依赖规则

### 21.1 权限

卡带必须声明需要的敏感权限。

### 21.2 环境

卡带必须声明关键系统命令或运行环境。

### 21.3 依赖

依赖必须可检查。

依赖缺失时，必须说明：

- 中断。
- fallback。
- 跳过。
- 需要用户安装。

### 21.4 凭据

卡带不得内置用户私密凭据。

凭据必须来自安全配置或用户输入。

### 21.5 文件路径边界

工具读取或写入文件时，必须遵守基座的工作区边界。

生产基座必须能阻止：

- 写入未授权绝对路径。
- 读取未授权系统文件。
- 通过 `../` 逃逸工作区。
- 覆盖卡带包外未授权文件。

如卡带确需访问工作区外路径，必须声明权限并由用户确认。

### 21.6 网络边界

需要网络访问的卡带必须声明网络能力。

生产基座可以限制：

- 可访问域名。
- 可访问端口。
- 请求方法。
- 超时时间。

卡带不得在未声明网络能力时发起远程请求。

---

## 22. 运行前检查

### 22.1 必须检查项

生产基座运行前必须检查：

- manifest 可解析。
- root flow 可解析。
- runtime contract 兼容。
- required profiles 满足。
- required capabilities 满足。
- required tools 满足。
- required assets 满足。
- permissions 可处理。
- environment/dependencies 可处理。

### 22.2 compatibility report

运行前必须生成 compatibility report。

报告必须说明：

- 可运行或不可运行。
- 缺失能力。
- 缺失工具。
- 降级项。
- 阻断项。

### 22.3 不得盲跑

生产基座不得在未完成运行前检查时执行卡带。

---

## 23. 运行时执行规则

### 23.1 执行起点

执行必须从 root flow `start` 开始。

### 23.2 执行顺序

执行顺序由图结构决定，不由 layout 决定。

### 23.3 节点进入

节点执行前必须产生进入事件或等价记录。

### 23.4 节点完成

节点完成后必须记录：

- 状态。
- 输入 key。
- 输出 key。
- 工具结果。
- 错误。

### 23.5 join 等待

join 节点必须等待所有必需父节点完成。

### 23.6 终止

到达 terminal 或触发 abort 时，运行必须终止。

### 23.7 执行确定性

在相同输入、相同工具版本、相同基座能力和相同外部服务响应下，流程控制流应当确定。

layout、节点显示顺序和 UI 排序不得影响执行顺序。

### 23.8 取消

基座可以支持取消运行。

取消时必须：

- 标记 run 为 cancelled。
- 停止未开始节点。
- 对运行中的工具按工具能力尝试取消。
- 不继续执行持久状态写入节点。
- 记录取消事件。

### 23.9 恢复

v0.1 不要求生产基座支持断点恢复。

如果基座支持恢复，必须声明 capability，并明确：

- 哪些节点可恢复。
- store 如何恢复。
- artifact 如何恢复。
- 非幂等工具是否会重跑。

---

## 24. 失败、中断和回退规则

### 24.1 失败类型

失败至少分为：

- 结构失败。
- 数据链失败。
- 工具失败。
- 远程失败。
- 门禁失败。
- 权限失败。
- 依赖失败。
- 持久状态失败。

### 24.2 abort_on_failed

节点声明 `abort_on_failed=true` 时，失败必须中断流程。

### 24.3 业务失败

工具返回 `ok=true` 但 `validation_ok=false` 或 `asset_ok=false` 时，可以视为业务失败。

节点必须声明该类失败是否中断。

### 24.4 fallback

fallback 必须显式记录。

fallback 后的 run 可以完成，但不得假装未降级。

### 24.5 失败后状态

失败后不得继续执行会造成持久副作用的节点。

### 24.6 重试和幂等

重试只能在明确安全的条件下发生。

基座执行重试前必须判断：

- 节点是否允许重试。
- 工具是否幂等。
- 失败是否可重试。
- 是否会重复写持久状态。

### 24.7 部分失败

fan-out 中某个分支失败时，join 节点是否继续执行必须由流程声明。

默认规则：

- 必需分支失败，join 不得继续。
- 可选分支失败，可以继续，但必须诊断为 warning 或 fallback。

---

## 25. 事件和诊断规则

### 25.1 标准事件

基座应支持以下事件或等价事件：

- run_created
- structure_checked
- compatibility_checked
- state_entered
- node_executed
- node_failed
- node_skipped
- artifact_collected
- run_completed
- run_failed

### 25.2 事件稳定性

事件名应稳定。

前端、测试台、生产运行界面不得使用互相不一致的事件名解释同一语义。

### 25.3 诊断输出

诊断必须包含：

- severity。
- kind。
- node id。
- detail。
- repair suggestion。

### 25.4 诊断可见性

关键错误不得只存在于日志。

生产运行界面必须能向用户展示阻断原因。

### 25.5 审计日志

生产基座应保留最小审计日志。

审计日志至少包括：

- run id。
- 卡带 id 和版本。
- base implementation id 和版本。
- 协议版本。
- 输入摘要。
- 节点失败。
- 权限确认。
- 持久状态写入。

审计日志不得泄露敏感输入或密钥。

---

## 26. 测试和探针规则

### 26.1 全流程测试

全流程测试必须从 start 执行可达主链。

### 26.2 探针测试

探针测试必须保留子图拓扑。

不得把子图拍平成线性流程。

### 26.3 探针范围

探针范围应为 start probe 到 end probe 之间所有路径的节点并集。

### 26.4 seeded keys

探针替身补齐的 key 必须标记。

seeded key 不得被当作真实上游产物。

### 26.5 探针结论限制

局部探针通过不代表全流程通过。

---

## 27. 交付规则

### 27.1 交付卡带

交付卡带必须可由生产基座直接运行。

### 27.2 交付前检查

交付前必须检查：

- delivery_readiness。
- runtime contract。
- compatibility report。
- data chain。
- required assets。
- required tools。
- persistent state strategy。

### 27.3 交付包

交付包必须包含运行所需文件。

交付包不得依赖开发工作区临时状态。

### 27.4 交付结果

交付结果必须由 manifest outputs、artifacts 和 delivery 描述。

---

## 28. 兼容性规则

### 28.1 兼容判断

兼容必须同时满足：

- 协议版本匹配。
- required profiles 匹配。
- required capabilities 匹配。
- required tool packs 匹配。
- tool contract versions 匹配。
- implementation lock 匹配。

### 28.2 共同可运行范围

两个基座的共同可运行范围，是它们共同支持能力覆盖的卡带集合。

### 28.3 降级兼容

recommended profile 或 optional capability 缺失时，可以降级运行。

降级必须显示。

### 28.4 阻断兼容

required profile、required capability 或 required tool 缺失时，必须阻断运行。

---

## 29. 协议认证规则

### 29.1 认证目的

协议认证用于标记某张卡带已经通过指定协议版本的机器检查。

协议认证不是人工命名标签，不得手工添加。

### 29.2 认证检测接口

开发基座应提供只读认证检测接口。

认证检测接口必须返回：

- ok。
- status。
- label。
- protocol。
- base。
- cartridge。
- compatibility。
- summary。
- findings。

### 29.3 认证写入接口

开发基座可以提供认证标签写入接口。

写入接口必须重新执行认证检测。

前端、脚本或开发者不得仅凭本地缓存结果写入认证标签。

### 29.4 认证通过条件

认证通过必须同时满足：

- compatibility report 无 blocker。
- compatibility report 无 warning。
- 卡带不是 legacy 模式。
- manifest 声明 base_contract。
- manifest 声明 runtime_contract。
- manifest 声明 delivery_readiness。
- base_contract 与 runtime_contract 指向同一协议版本。
- required tool 具备 contract 元数据。

### 29.5 认证标签

认证通过后，基座可以写入：

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

同一 label 可以同步写入 `branding.tags`。

### 29.6 禁止伪认证

未通过认证检测时，不得写入 `protocol_certification`。

legacy 卡带不得获得协议认证标签。

---

## 30. 禁止行为

以下行为被本协议禁止：

1. 为单张卡带修改流程执行语义。
2. 生产态卡带依赖设计台状态。
3. 生产态卡带依赖测试台探针。
4. 工具无 schema。
5. 工具失败结构不稳定。
6. 必需 input 缺失但静默成功。
7. 远程服务无声明。
8. fallback 无记录。
9. 失败后继续写持久状态。
10. 未声明私有扩展却依赖具体基座。
11. 只看协议版本就声称完全兼容。
12. 交付包依赖开发临时文件。

---

## 31. 合规检查清单

### 31.1 流程结构

- [ ] root flow 有 start。
- [ ] root flow 有 terminal。
- [ ] 所有 next 指向有效节点。
- [ ] 所有 edges 指向有效节点。
- [ ] 无未标记 isolated 节点。
- [ ] fan-out/join 语义明确。

### 31.2 数据链

- [ ] 每个关键节点声明 input。
- [ ] 每个关键节点声明 output。
- [ ] 必需 input 有上游生产者。
- [ ] 可选 input 单独声明。
- [ ] store 引用可解析。

### 31.3 工具

- [ ] required tools 已声明。
- [ ] 工具有参数 schema。
- [ ] 工具有失败结构。
- [ ] 工具副作用明确。
- [ ] 节点实例参数可解释。
- [ ] 非幂等工具声明了重试限制。
- [ ] 长时间工具声明了 timeout。
- [ ] 远程工具不包含明文凭据。

### 31.4 运行

- [ ] 运行前 compatibility report 通过。
- [ ] abort_on_failed 节点策略明确。
- [ ] fallback 可见。
- [ ] artifact 可收集。
- [ ] 持久状态写入受保护。
- [ ] 条件分支没有隐式实现。
- [ ] 取消后不会继续写持久状态。
- [ ] fan-out 部分失败策略明确。

### 31.4.1 安全边界

- [ ] 文件读写遵守工作区边界。
- [ ] 工作区外访问已声明权限。
- [ ] 网络访问已声明能力。
- [ ] 凭据不进入卡带包。

### 31.5 交付

- [ ] delivery_readiness 为 production。
- [ ] 不依赖设计台。
- [ ] 不依赖探针。
- [ ] 不依赖开发缓存。
- [ ] 生产基座可加载运行。

---

## 32. 一致性测试要求

### 32.1 基座一致性测试

声明支持本协议的基座必须通过：

- 线性流程测试。
- fan-out/join 测试。
- context.store 测试。
- input/output 缺失测试。
- abort_on_failed 测试。
- fallback 可见性测试。
- isolated node 测试。
- artifact 测试。
- compatibility report 测试。

### 32.2 工具一致性测试

工具包必须通过：

- 参数 schema 导出测试。
- 参数校验测试。
- 成功输出测试。
- 失败结构测试。
- 副作用声明测试。

### 32.3 交付一致性测试

生产态卡带必须通过：

- 无开发基座依赖测试。
- assets 完整性测试。
- required tools 测试。
- delivery 输出测试。

---

## 附录 A：标准字段参考

### A.1 节点 params 推荐字段

```json
{
  "node_category": "process",
  "input": "input_key",
  "optional_input": "optional_key",
  "output": "output_key",
  "abort_on_failed": false,
  "isolated": false
}
```

### A.2 工具结果推荐字段

```json
{
  "ok": true,
  "path": "",
  "files": [],
  "content": "",
  "error": "",
  "issues": [],
  "repairs": [],
  "fallback": false
}
```

### A.3 兼容性报告推荐字段

```json
{
  "compatible": true,
  "missing_required": [],
  "missing_optional": [],
  "warnings": [],
  "blocking": []
}
```

---

## 附录 B：节点类型矩阵

| 节点类别 | 允许副作用 | 是否可进生产主链 | 主要职责 |
| --- | --- | --- | --- |
| system | 否 | 是 | 生命周期控制 |
| input | 写 store | 是 | 输入入库 |
| process | 写 store | 是 | 规划和判断 |
| tool | 取决于工具 | 是 | 执行工具 |
| remote | 是 | 条件允许 | 外部服务 |
| transfer | 写 store | 是 | 数据传递 |
| gate | 取决于实现 | 是 | 门禁质检 |
| ui | 写 UI store | 是 | 展示交互 |
| terminal | 否 | 是 | 结束 |
| placeholder | 否 | 否 | 占位 |

---

## 附录 C：错误等级

| 等级 | 含义 | 是否阻断 |
| --- | --- | --- |
| info | 信息 | 否 |
| warning | 可降级或需注意 | 否，除非生产策略要求 |
| error | 协议或运行错误 | 通常阻断 |
| fatal | 会导致错误结果或状态污染 | 必须阻断 |

---

## 附录 D：覆盖矩阵

本协议覆盖以下方向：

| 方向 | 覆盖章节 |
| --- | --- |
| 协议定位 | 1 |
| 术语和实体 | 2, 3 |
| 合规对象 | 5 |
| 版本 | 6 |
| 搭建原则 | 7 |
| 开发/生产分离 | 8 |
| 文件结构 | 9 |
| manifest | 10 |
| root flow | 11 |
| 节点 | 12, 13 |
| 拓扑 | 14 |
| 数据链 | 15 |
| 工具 | 16 |
| 远程 | 17 |
| UI | 18 |
| artifact | 19 |
| 持久状态 | 20 |
| 权限依赖环境安全边界 | 21 |
| 运行前检查 | 22 |
| 运行时、取消、恢复、确定性 | 23 |
| 失败、fallback、重试、部分失败 | 24 |
| 事件诊断审计 | 25 |
| 测试探针 | 26 |
| 交付 | 27 |
| 兼容性 | 28 |
| 禁止行为 | 29 |
| 检查清单 | 30 |
| 一致性测试 | 31 |

---

## 结语

本协议的核心要求是：

> 流程必须以声明式、可验证、可诊断、可交付的方式搭建；运行必须以协议为准，而不是以某个开发基座的偶然实现为准。

任何符合本协议的生产基座，都应能运行其能力范围内的符合协议卡带。
