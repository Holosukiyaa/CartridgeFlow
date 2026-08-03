# CartridgeFlow AI 辅助创作行动基线

日期：2026-08-03
状态：已冻结的产品与交付基线
交付 ID：`creator-ai-authoring-2026-08`
基线修订：`creator-ai-authoring-2026-08-r2`
冻结时间：2026-08-03 16:48 +08:00
替代：`creator-ai-authoring-2026-08-r1` 以及本文件中此前面向运行时的用户体验计划

## 1. 基线决策

CartridgeFlow 是创作产品。其主要体验帮助创作者与 AI 协作，将不寻常的想法转为
可移植的 cartridge。生产应用执行属于独立的运行时团队，通过 `demos/` 下已签名的
cartridge 包移交。

产品划分为三个界面：

```text
创作者工作室
  自然语言意图 + 创作者自有来源
  -> AI 提出的语义设计
  -> 直接操控与明确接受变更
  -> 逐步冻结的配方和拓扑
  -> 已验证的 cartridge 包

开发者控制台
  完整的工程和调优信息
  -> 协议事实、提示词、绑定、修订、差异、验证、物化、诊断与开发探针

运行时产品
  已签名 cartridge 的安装与执行
  -> 由运行时项目团队负责；`demos/runtime-developer-toolkit` 是移交契约和参考，
     不是 CartridgeFlow 的用户界面
```

本文件是此交付唯一有效的行动基线。Worker 不得实现已替代的普通用户运行页，或前一
计划中的 `cartridgeflow.user_experience_plan.v1` 方向。

2026-08-03 的 Creator 合同补充是本 r2 基线的受控后续：Worker 303 审查发现，已发布
的 Worker 302 投影与变更操作不足以诚实实现完整创作工作流。该补充不改变三界面、
运行时边界或来源安全决策，只补齐其已要求的版本化创作合同与 Creator API。

r2 修订解决了 r1 的前端所有权冲突。创作者工作室是新的 `src/creator-studio/` 应用，
开发者控制台是新的 `src/developer-console/` 应用；现有 `src/frontend/` 工作台仍是
此交付范围外的兼容性实现。冻结的六图视觉基线位于
`docs/design/visual-baselines/creator-ai-authoring-2026-08-r2/`。

## 2. 历史排除项

分支 `workers/worker-201-uxp-contract` 曾包含已替代的面向运行时 UXP 契约提交，尖端
为 `d57df6a`。该工作树和分支已于 2026-08-03 经用户明确批准删除。

- 不得重新创建、合并或 cherry-pick 该分支。
- 不得将其协议版本或证据视为下一版本基线。
- 可复用的实现细节只能由新的、范围正确的 Worker 重新考虑，且不得整批复制。

## 3. 产品论题

官方业务配方不能覆盖创作者长尾目标。因此 CartridgeFlow 不以官方场景配方目录为
核心，而以 AI 协作作者为核心：它理解创作者意图、纳入创作者选择的信息源、提出
语义流程，并将接受的决策转为带版本的协议工件。

较低层次仍需要官方供给：

- 协议定义的能力原语；
- 可信的来源、转换、决策、审阅和交付构件；
- 类型适配器和验证规则；
- 权限与副作用声明；
- 用于评估 AI 创作的隐藏示例和一致性夹具；
- 可选的起始模板，绝非默认产品中心。

平台提供语言、标准库和编译器；创作者与 AI 编写具体 cartridge。

## 4. 不可协商的所有权边界

### 4.1 创作者工作室负责

- 以日常语言捕获意图；
- 添加并描述创作者自有来源；
- 仅提出消除歧义所必需的澄清问题；
- 呈现可由创作者直接编辑的语义画布；
- 将 AI 变更作为明确、可审阅的事务提出；
- 渐进确认和冻结步骤；
- 用通俗语言验证设计；
- 所有阻塞问题解决后生成 cartridge。

### 4.2 开发者控制台负责

- 完整的 Root Flow 拓扑与契约；
- 提示词、配方参数和调优修订；
- 模型角色、工具、来源绑定和资源预检；
- 协议身份、摘要、物化和发布溯源；
- 原始验证器发现项与工程差异；
- 仅开发用途的探针、追踪和诊断；
- 发布可信原语和配方蓝图。

开发者控制台是通过明确 API 连接同一后端的独立前端项目，不能是创作者工作室中的
隐藏模式、路由标志或可展开抽屉。

### 4.3 运行时负责

- 安装和信任存储强制执行；
- 运行时资源与凭据绑定；
- 生产执行、暂停、恢复和失败路由；
- 运行时交互、队列、历史、工件和交付 UI。

创作者工作室可以进行静态验证和受限设计探测，不能发展为生产运行时产品。

## 5. 创作者心智模型

创作者看到的是意图、来源、步骤、决策与交付物，不需要理解 Prompt、schema、MCP、
模型角色、摘要、执行器、边类型或协议版本。

技术术语必须被翻译，不能成为隐藏有后果行为的借口：

| 工程事实 | 面向创作者的表述 |
| --- | --- |
| 文件系统写入权限 | 此步骤会在交付文件夹中创建文件。 |
| 提供方凭据绑定 | cartridge 运行时，此连接需要你的账户。 |
| 类型不匹配 | 上一步提供网页地址；此步骤需要新闻列表。 |
| 上下文限制与分块 | 较长材料可能分为多个部分处理。 |
| 网络副作用 | 此步骤会将选定材料发送到外部服务。 |

创作者始终必须理解外部副作用、所需账户、材料去向、不可逆操作和未解决的设计假设。

## 6. AI 协作创作循环

主要工作流：

```text
表达意图
  -> 附加或命名来源
  -> 回答最少量澄清问题
  -> 检查 AI 提议的语义步骤
  -> 通过对话或直接画布操作编辑
  -> 审阅具体变更集
  -> 接受、拒绝或部分接受
  -> 确认并冻结稳定步骤
  -> 解决设计发现项
  -> 生成 cartridge
```

AI 是理解协议的创作助手，不是黑箱状态修改器。每个 AI 提案在修改已接受设计前都
必须生成结构化变更集。

必需事务生命周期：

1. AI 读取当前已接受修订和可用能力目录。
2. AI 返回提议的语义变更集及未解决假设。
3. 后端将提案编译为结构和配方增量。
4. 后端验证提案，不改变已接受状态。
5. 创作者看到通俗摘要及所有影响。
6. 创作者可全量接受、选择性接受、拒绝或修订。
7. 接受的变更以新修订和溯源原子应用。
8. 撤销创建新的反转修订，不改写历史。

聊天记录只是辅助上下文，不是事实来源；结构化的已接受工件才是事实来源。

## 7. 渐进固化

每个语义步骤拥有一种创作状态：

- `exploring`：AI 和创作者可自由重塑步骤。
- `needs_confirmation`：已有具体提案待审阅。
- `confirmed`：意图和可见行为已接受。
- `frozen`：步骤有固定的配方蓝图、实例配置、契约和修订。
- `blocked`：必需来源、权限、契约或决策未解决。

规则：

- 冻结步骤不得静默变化。
- 修改冻结步骤需要明确解锁或提出新修订。
- 使冻结契约失效的下游变更必须标识受影响步骤，并请求重新确认。
- 任一步骤为 `blocked`、必需契约未解决或已接受修订过期时，生成 cartridge 必须失败。
- 非阻塞建议必须能与阻塞发现项区分。

## 8. 工件模型

下一版协议设计必须区分：

1. **设计意图**：创作者以日常语言表达的目标、约束和期望交付，带稳定修订。
2. **来源引用**：创作者选择的来源身份与预期角色，绝不嵌入凭据。
3. **语义设计计划**：不含原始工程内部细节的创作者步骤与关系。
4. **配方蓝图**：开发者或 AI 创作的可复用、已版本化技术定义，具有类型化契约和
   声明的安全控件。
5. **配方实例**：固定到某一设计的蓝图，具有新实例身份和已接受的创作者值。
6. **创作变更集**：含基础修订、提案溯源、验证及接受结果的可审阅增量。
7. **冻结快照**：将已确认语义绑定到准确蓝图、实例、拓扑和来源引用修订的不可变证据。
8. **根流程**：由已接受创作事实编译、由 CF-FARP 持有的可执行拓扑。
9. **调优发布**：不可变的内部副作用和配方快照。
10. **Cartridge 发布**：已签名的 CF-CRE 移交包。

CF-TUNING@1.0 的作用域是宿主 Flow 与节点 ID，不能单独表达可移植蓝图目录和实例化
生命周期。新契约必须解决蓝图可移植性、实例固定、已接受 AI 变更溯源与冻结语义，
同时不从 CF-FARP 移走拓扑所有权。

## 9. 来源与凭据规则

- 创作者可经日常语言 UI 添加 URL、RSS 源、文件角色、API 角色、MCP 能力或其他支持来源。
- AI 只能从已声明能力推断来源适配器提案。
- 未知适配器保持为阻塞占位符；AI 不得虚构可执行工具或静默回退到其他提供方。
- 凭据、令牌和机器本地路径绝不进入设计工件、配方发布或 cartridge 包。
- 运行时专用账户绑定仍由运行时负责。
- 创作者工作室必须以通俗语言说明未来所需的连接。

## 10. 创作者工作室交互基线

### 10.1 默认工作区

- 左侧：意图历史、AI 协作、创作者来源和已保存个人片段。
- 中央：可直接操控的语义无限画布。
- 右侧：将所选步骤描述为目的、所需内容、结果、可调行为及影响。
- 底部：待处理 AI 变更集、设计发现项和固化进度。
- 顶部：撤销、重做、设计检查、保存和生成 cartridge。

### 10.2 手动画布模式

此前探索的配方库画布保留为高级手动设计视图，但不是默认空状态体验。

手动模式支持：

- 拖放个人、可信或已生成的配方蓝图；
- 连接类型化端口，并建议兼容的下一步骤；
- 编辑声明为创作者安全的值；
- 多选、对齐、分组和创建个人可复用片段；
- 检查通俗语言的输入和输出契约；
- 通过明确变更提案固定或更新蓝图版本。

### 10.3 节点呈现

创作者节点显示业务目的、固化状态、通俗的输入与输出、仅限创作者安全的可调行为、
警告与外部副作用，以及相关时的蓝图来源与更新状态；不得显示提示词、原始 schema、
模型或工具绑定、执行器、节点 ID 或协议字段。

## 11. 开发者控制台架构

创建独立前端包，暂定 `src/developer-console/`。实现 Worker 在搭建前必须按仓库约定
验证最终位置。

要求：

- 独立构建、依赖、路由和发布生命周期；
- 同一后端、明确的开发者 API 命名空间和特权授权；
- 浏览器不得读取开发文件或后端进程内存；
- 面向完整信息的密集工程画布与检查器；
- 原始/语义并排视图与精确修订差异；
- 协议验证、物化、来源绑定和包预检；
- 仅开发用途探针，且与生产运行时行为清晰分隔；
- 即使在开发者界面，秘密也只显示为引用或脱敏状态。

两个前端可共享生成的 API 类型、小型 API 客户端和基础设计令牌，不能共享页面状态、
路由假设或单棵条件组件树。

## 12. 产品不变量

1. 未经接受的变更集，AI 不得修改已接受设计状态。
2. 每项接受变更均可归因、可反转，并基于精确修订。
3. 冻结步骤在明确修订前不可变。
4. 生成技术工件必须在生成 cartridge 前验证。
5. 创作者用语隐藏术语，但不隐藏副作用、权限或不确定性。
6. 业务配方是可选加速器，不是必需产品覆盖。
7. 官方能力原语必须有限、可信并由协议定义。
8. 创作者工作室和开发者控制台是独立前端应用。
9. 运行时 UI 与生产执行在创作者工作室之外。
10. 已签名 cartridge 是唯一生产运行时移交物。

### 12.1 Creator 合同补全补充

Creator Studio 不能以本地 UI 状态模拟已接受设计。它必须使用服务端修订、提案、冻结和
检查事实；因此在 Worker 303 的 API 驱动完成前，需要一个受版本治理的合同补全交付。

**版本与所有权：**

- 不得改变已发布 `CF-FARP@1.2`、`CF-TUNING@1.1` 或已接受 Worker 302 API 的既有
  语义；按协议目录、发布目录与治理证据确定并发布正确的下一版本。
- CF-FARP 继续拥有可执行拓扑；创作合同拥有创作修订、蓝图/实例、来源、冻结和变更集
  事实。
- 设计检查和生成就绪 API 只验证创作事实并生成确定性的编译/移交候选；它们不得伪造
  生产执行或签名运行时行为。

**Creator API 与投影：**

- Creator projection 必须是创作者安全且足够完整的事实来源：当前 revision、语义步骤、
  通俗输入/输出和关系、来源角色和安全远程引用元数据、creator-safe bindings、未解决
  假设、通俗影响、pending proposals、active freezes、history、reversals、阻塞发现项、
  设计检查结果与 generation readiness。
- 投影不得泄露提示词、原始 schema、模型/工具绑定、执行器、凭据、令牌、密码、Cookie、
  Authorization 或机器本地路径。
- 冻结相关投影必须提供构造有效 `freeze_revision` 请求所需的创作者安全快照引用、受影响
  步骤与 revision 事实。

**受审阅的创作变更：**

- 扩展变更集以支持添加、更新、移除来源；添加、更新、移除语义步骤；连接、断开步骤的
  创作者安全输入/输出关系；以及创作者安全绑定值更新。
- 所有 mutation 均必须使用 `proposal -> preview -> accept`，保持乐观 revision、部分接受、
  原子应用与 reversal；不得新增绕过已接受修订的直接写入 API。
- 冻结步骤绝不静默变化。涉及冻结步骤的提案必须经服务验证明确的冻结修订，或以稳定、
  通俗的错误拒绝。
- “请 AI 修改”表示使用当前已接受 revision 再次创建 AI proposal，不引入只有本地 UI
  才理解的隐式状态。

**来源与生成门禁：**

- 允许创作者添加安全的远程 URL、RSS 或其他来源角色；来源保持可移植、可审计且无凭据。
  必须拒绝 URL user-info、敏感查询参数、凭据和机器本地路径。
- blocked findings、未解决契约、过期 revision 或无有效冻结事实时，generation readiness
  必须为失败，Creator Studio 不得显示可生成状态。

**证据：**协议/治理、服务和 API 测试必须证明上述操作只能经事务完成，接受前无状态变化，
部分接受精确匹配 selected change ids，reversal 创建新修订，冻结守卫生效，来源安全规则
生效，Creator projection 不泄露工程/秘密字段，且 generation readiness 正确阻止生成。

## 13. 验收矩阵

| 场景 | 必需证据 |
| --- | --- |
| 意图到草稿 | 创作者陈述和来源产生带明确假设的语义草稿，且不修改已接受状态。 |
| 澄清 | 缺失的重要事实转为少量可回答的创作者问题。 |
| AI 提案 | 提案携带基础修订、语义摘要、技术增量、溯源和验证结果。 |
| 部分接受 | 创作者可原子接受选定提案项并得到新修订。 |
| 直接操控 | 画布编辑走与会话编辑相同的变更集和修订路径。 |
| 渐进冻结 | 步骤经过已定义状态转换；冻结变更需要明确修订。 |
| 来源安全 | 来源角色可移植；凭据和本地路径不进入发布物。 |
| 通俗透明性 | 外部副作用、所需连接与阻塞项保持可见，且没有工程术语。 |
| 蓝图实例 | 可移植蓝图作为具精确版本和创作者安全值的独立实例被固定。 |
| 根流程编译 | 已接受创作事实确定性编译为有效 CF-FARP 拓扑。 |
| 生成 cartridge | 只有未阻塞、当前且已验证的设计才能生成已签名包。 |
| 前端分离 | 两个前端独立构建，并仅通过声明 API 通信。 |
| 运行时边界 | 创作者 UI 不依赖队列、生产运行状态或运行时项目内部实现。 |

视觉外观不是 Worker 验收条件。功能语义、可运维性、协议不变量、API 行为和自动化
证据才是。

## 14. 交付顺序

```text
worker-301-authoring-contract
  -> worker-302-authoring-service
     -> worker-306-creator-contract-completion
        -> worker-303-creator-studio --+
        -> worker-307-authoring-runtime-bridge -+
     -> worker-304-developer-console -----------+-> worker-305-authoring-integration
```

Worker 304 可在 Worker 302 合并后启动。Worker 303 的 API 驱动完成必须等待 Worker 306
被接受并合并；其已有原型不得作为可接受实现。只有 Workers 303、304 与 306 都被接受
并合并后，Worker 305 才可启动。Worker 305 的最终验收还必须等待 Worker 307 被接受并
合并；在此之前它只能记录交接边界，不能以既有样本包替代创作事实到签名包的端到端证据。
任何 Worker 都不得 cherry-pick 被拒绝的 Worker 201 分支。

## 15. Worker 卡片

### Worker 301

**名称与目标：** `worker-301-authoring-contract`：发布下一版创作契约，支持可移植
配方蓝图、实例、AI 变更集与渐进冻结，同时保留 CF-FARP 拓扑所有权。

**状态：** `planned`

**允许写入：** 下一版本 `protocol/tuning/**`、所需可信 `protocol/flow-authoring/**`
发布、协议目录/治理历史、`config/base/**`、`src/core/protocol/**`，以及直接相关的
协议、一致性、治理测试和证据。

**排除：** 后端 API 与持久化、创作者工作室、开发者控制台、运行时工具包、依赖、
`PLAN.md`、`MENTOR_WORKERS.md`、被拒绝的 Worker 201 分支。

**依赖和分支：** 无；`workers/worker-301-authoring-contract`。

**验收：** 已版本化的不可变契约；蓝图/实例/变更集和冻结 schema；确定性验证；秘密
脱敏；准确 FARP 与 TUNING 所有权；迁移和负向测试；治理证据通过。

```powershell
Set-Location -LiteralPath "C:\_HOLOLAB\code\CF WS"
$worktree = "C:\_HOLOLAB\code\CF WS\CartridgeFlow-worker-301-authoring-contract"
git -C ".\CartridgeFlow" worktree add $worktree -b "workers/worker-301-authoring-contract"

$prompt = @'
你是 worker-301-authoring-contract。为 CartridgeFlow AI 辅助创作实现协议基础。
当前产品基线是：创作者表达意图，AI 提出可审阅变更，创作者逐步冻结语义步骤，
已接受事实编译为 CF-FARP 拓扑，已签名包交给独立运行时。不得实现普通用户运行页，
也不得复用被拒绝的运行时 UXP 分支。

允许写入：下一版本 protocol/tuning/**、所需可信 protocol/flow-authoring/** 发布、
协议目录/治理历史、config/base/**、src/core/protocol/**，以及直接相关的协议、
一致性和治理测试/证据。排除后端 API、持久化、两个前端、demos、依赖、PLAN.md、
MENTOR_WORKERS.md。

定义不可变的可移植配方蓝图、固定的配方实例、基于修订的 AI 创作变更集、渐进冻结
快照、不含凭据的来源引用和确定性编译引用。CF-FARP 保留拓扑与可执行契约；
CF-TUNING 持有配方和创作修订事实。拒绝过期修订、静默冻结步骤变更、虚构能力、
秘密、本地路径和不安全公开值。保留所有已发布协议不变。添加正向与负向自动化证据，
且只提交允许范围。

验收：新发布版本和信任关系正确；schema/验证器覆盖所有新工件；规范摘要和脱敏
具有确定性；所有权边界明确；已记录迁移；协议/治理/一致性测试通过。

## Worker 交付报告
变更文件：<每行一个路径>
提交 SHA：<完整 SHA>
测试：<每行一个命令和结果>
已知风险：<无或具体风险>
范围确认：<确认未更改排除路径>
'@
codex -C $worktree $prompt
```

### Worker 302

**名称与目标：** `worker-302-authoring-service`：在明确 API 之后实现创作会话、AI
提案事务、接受/撤销、冻结和确定性工件编译。

**状态：** `planned`

**允许写入：** `src/backend/**`、`src/core/studio/**`、必需的
`src/core/cartridge/**`、`src/core/llm/**` 创作适配器，以及直接相关后端/服务测试。

**排除：** 协议/config 发布、两个前端、demos、依赖清单、无关运行时执行、导师文件。

**依赖和分支：** 已接受并合并的 Worker 301；`workers/worker-302-authoring-service`。

**验收：** 乐观修订、先验证后接受、部分接受、原子应用、反转修订、冻结强制、
以能力为依据的 AI 提案、来源/凭据分离、确定性编译 API 和完整 API/服务测试。

```powershell
Set-Location -LiteralPath "C:\_HOLOLAB\code\CF WS"
$worktree = "C:\_HOLOLAB\code\CF WS\CartridgeFlow-worker-302-authoring-service"
git -C ".\CartridgeFlow" worktree add $worktree -b "workers/worker-302-authoring-service"

$prompt = @'
你是 worker-302-authoring-service。只从已含被接受 worker-301 创作契约的基线启动。
实现 AI 辅助创作者创作的后端和核心服务，不是生产应用运行时。

允许写入：src/backend/**、src/core/studio/**、所需 src/core/cartridge/** 与
src/core/llm/** 创作适配器，以及直接相关后端/服务测试。排除协议/config 发布、
两个前端、demos、依赖清单、无关运行时执行、PLAN.md、MENTOR_WORKERS.md。

实现带修订的设计会话、来源引用、语义设计计划、仅基于声明能力的 AI 提案生成、
预览验证、全量和部分接受、原子应用、拒绝、反转修订、渐进冻结强制、通俗影响数据，
以及到协议工件的确定性编译。聊天只是上下文，不是事实来源。过期提案和静默冻结
步骤变更必须默认失败。不得让凭据和机器本地路径进入创作工件。提供明确的创作者与
开发者 API 投影。只提交允许范围。

验收：API/服务测试证明接受前无修改、乐观冲突拒绝、部分接受、撤销历史、冻结守卫、
来源安全、确定性编译和稳定错误身份。

## Worker 交付报告
变更文件：<每行一个路径>
提交 SHA：<完整 SHA>
测试：<每行一个命令和结果>
已知风险：<无或具体风险>
范围确认：<确认未更改排除路径>
'@
codex -C $worktree $prompt
```

### Worker 303

**名称与目标：** `worker-303-creator-studio`：创建独立、AI 优先的语义创作界面，
具有直接画布编辑和渐进固化。

**状态：** `planned`

**允许写入：** 新 `src/creator-studio/**` 包及其前端测试/依赖文件。

**排除：** 现有 `src/frontend/**`、backend/core/protocol/config、新开发者控制台包、
demos、导师文件。

**依赖和分支：** 已接受并合并的 Workers 302、306；
`workers/worker-303-creator-studio`。

**验收：** 意图/来源录入、语义画布、可部分接受的提案审阅、同一事务路径直接编辑、
可见固化状态、通俗影响、手动画布模式、cartridge 生成门禁；前端测试和构建通过。

```powershell
Set-Location -LiteralPath "C:\_HOLOLAB\code\CF WS"
$worktree = "C:\_HOLOLAB\code\CF WS\CartridgeFlow-worker-303-creator-studio"
git -C ".\CartridgeFlow" worktree add $worktree -b "workers/worker-303-creator-studio"

$prompt = @'
你是 worker-303-creator-studio。只在已接受创作服务合并后启动。创建独立的
src/creator-studio/** 前端，构建面向创作者的 AI 协作创作体验。它是设计产品，
不是应用运行时。

允许写入：新的 src/creator-studio/** 包及其测试和依赖文件。排除现有 src/frontend/**、
backend、core、protocol、config、独立开发者控制台、demos、PLAN.md、
MENTOR_WORKERS.md。

实现意图/来源录入、语义画布生成、通俗步骤检查器、exploring/needs-confirmation/
confirmed/frozen/blocked 状态、AI 变更集审阅、部分接受/拒绝/修订、撤销、通过相同
修订 API 的直接画布编辑、通俗副作用与阻塞项、设计验证和受门禁的 cartridge 生成。
保留一个次级手动画布，可拖动生成/个人/可信蓝图并连接类型化端口。隐藏工程术语，
但不能隐藏后果。不得加入生产运行、队列、运行时历史或结果交付 UI。遵循既有前端
模式，添加功能自动化覆盖，只提交允许范围。

验收：创作者可表达新目标、添加来源、得到草稿、审阅并部分接受变更、冻结步骤、
直接编辑、解决阻塞发现项并生成 cartridge，且不见协议内部细节；测试和构建通过。

## Worker 交付报告
变更文件：<每行一个路径>
提交 SHA：<完整 SHA>
测试：<每行一个命令和结果>
已知风险：<无或具体风险>
范围确认：<确认未更改排除路径>
'@
codex -C $worktree $prompt
```

### Worker 304

**名称与目标：** `worker-304-developer-console`：创建独立的开发者前端，提供完整
工程、调优和诊断可见性。

**状态：** `planned`

**允许写入：** 新 `src/developer-console/**` 包及其测试/依赖文件。只有说明其更符合
仓库约定后，才可选择其他新的同级路径。

**排除：** 现有 `src/frontend/**`、backend/core/protocol/config、demos、根依赖文件、
导师文件。

**依赖和分支：** 已接受并合并的 Worker 302；`workers/worker-304-developer-console`。

**验收：** 独立构建、仅 API 后端连接、密集全流程画布、原始/语义检查器、提示词/
绑定/修订/差异、验证/物化/预检、凭据脱敏、无创作者工作室模式标志；测试和构建通过。

```powershell
Set-Location -LiteralPath "C:\_HOLOLAB\code\CF WS"
$worktree = "C:\_HOLOLAB\code\CF WS\CartridgeFlow-worker-304-developer-console"
git -C ".\CartridgeFlow" worktree add $worktree -b "workers/worker-304-developer-console"

$prompt = @'
你是 worker-304-developer-console。只在已接受创作服务合并后启动。创建一个通过声明
API 连接同一后端的独立开发者前端项目，不要将其隐藏在创作者工作室中。

允许写入：带独立测试与依赖的新 src/developer-console/** 包。仅在说明更符合仓库约定
时可选择另一个新同级包路径。排除 src/frontend/**、backend、core、protocol、config、
demos、根依赖文件、PLAN.md、MENTOR_WORKERS.md。

构建信息密集的工程界面，展示完整 Root Flow 拓扑、类型化契约、提示词、配方参数、
模型/工具/来源绑定、调优修订、精确差异、协议身份、摘要、物化、验证、包预检和
仅开发探针。并排展示原始与语义投影。只通过明确 API 连接，绝不直接读取后端文件。
秘密保持引用或脱敏状态。不要将生产运行时行为放入此控制台。只提交允许范围。

验收：包可独立安装/构建，能经 API 检查所有声明工程投影与诊断，保持与创作者工作室
隔离，不暴露凭据值，并含功能测试。

## Worker 交付报告
变更文件：<每行一个路径>
提交 SHA：<完整 SHA>
测试：<每行一个命令和结果>
已知风险：<无或具体风险>
范围确认：<确认未更改排除路径>
'@
codex -C $worktree $prompt
```

### Worker 306

**名称与目标：** `worker-306-creator-contract-completion`：发布受版本治理的创作合同与
Creator API 补全，使 Creator Studio 能以服务端事实实现来源、语义画布、提案、冻结、
撤销、设计检查与生成门禁。

**状态：** `planned`

**允许写入：** 所需下一版 `protocol/flow-authoring/**`、`protocol/tuning/**`、
`protocol/catalog/**`、必要 `config/base/**` 与治理证据、`src/core/protocol/**`、
`src/core/studio/**`、`src/backend/**`，以及直接相关协议/服务/API/一致性测试。

**排除：** 两个新前端、现有 `src/frontend/**`、demos、运行时执行、根依赖、导师文件。

**依赖和分支：** 已接受并合并的 Workers 301、302；
`workers/worker-306-creator-contract-completion`。

**验收：** 遵循 12.1 的版本、投影、事务、冻结、来源安全与生成门禁要求；已发布合同
保持兼容；协议治理、服务/API、负向安全测试与完整一致性证据通过。

```powershell
Set-Location -LiteralPath "C:\_HOLOLAB\code\CF WS\CartridgeFlow"
$worktree = "C:\_HOLOLAB\code\CF WS\CartridgeFlow-worker-306-creator-contract-completion"
git worktree add $worktree -b "workers/worker-306-creator-contract-completion"

$prompt = @'
你是 worker-306-creator-contract-completion。为已合并的 Worker 302 创作服务补齐受版本
治理的协议、Creator API 和创作者安全投影，使 Worker 303 能实现真正的 API 驱动
Creator Studio。只从当前 main 基线开始；不得修改 Worker 303 工作树或实现任何前端。

允许写入：所需下一版 protocol/flow-authoring/**、protocol/tuning/**、protocol/catalog/**、
必要 config/base/** 与治理证据、src/core/protocol/**、src/core/studio/**、src/backend/**，
以及直接相关协议/服务/API/一致性测试。

排除：src/creator-studio/**、src/developer-console/**、src/frontend/**、demos/**、运行时
执行、队列、运行历史、结果交付 UI、根依赖、PLAN.md、MENTOR_WORKERS.md 和其他工作树。

先检查当前协议目录、发布目录、治理脚本和 capability evidence，确定正确的下一版发布；
不得改变已发布 CF-FARP@1.2、CF-TUNING@1.1 或已接受 Worker 302 API 的既有语义。
CF-FARP 保持可执行拓扑所有权；创作合同持有创作 revision、蓝图/实例、来源、冻结和
变更集事实。

按 PLAN.md 12.1 实现：
1. Creator projection 成为创作者安全且完整的事实来源，含 revision、语义步骤、通俗
   输入/输出和关系、来源角色/安全远程引用、creator-safe bindings、未解决假设、影响、
   pending proposals、active freezes、history、reversals、blocked findings、设计检查及
   generation readiness。
2. 扩展受审阅变更集，支持来源和语义步骤的添加/更新/移除、步骤输入输出关系的连接/
   断开及 creator-safe binding 更新；所有 mutation 必须走 proposal -> preview -> accept，
   保持乐观 revision、部分接受、原子应用和 reversal。禁止直接写入 API。
3. 冻结步骤绝不静默变化。Creator projection 必须提供构造有效 freeze_revision 所需的
   安全快照引用；服务必须验证冻结步骤变更或以稳定、通俗错误拒绝。
4. 来源可接受安全远程 URL、RSS 或来源角色，但必须拒绝 URL user-info、敏感查询参数、
   凭据和机器本地路径；不得让秘密进入工件、投影、日志、编译物或错误。
5. 提供设计检查与确定性 generation readiness/编译候选 API。它们只验证创作事实与
   移交候选，绝不伪造生产执行或已签名运行时行为。
6. “请 AI 修改”重用当前 accepted revision 再次创建 AI proposal，不引入本地隐式状态。

添加协议/治理、服务和 API 正反向测试，证明接受前无状态变化、部分接受精确匹配
selected change ids、reversal 创建新 revision、冻结守卫生效、来源安全规则生效、Creator
projection 无工程/秘密泄露，以及 blocked/过期/未冻结设计阻止 generation readiness。
运行协议治理审计、相关测试和完整 conformance。

仅创建普通提交；不 amend、不 rebase、不改写历史。提交前运行 git diff --check 且确保
git status --short 为空。

## Worker Delivery Report
Changed files: <one path per line>
Commit SHA: <full SHA>
Tests: <command and result per line>
Known risks: <none or concrete risks>
Scope confirmation: <confirm no excluded paths changed>
'@
codex -C $worktree $prompt
```

### Worker 305

**名称与目标：** `worker-305-authoring-integration`：负责最终跨界面验收，并仅更新
新 cartridge 输出所需的运行时移交文档与夹具。

**状态：** `planned`

**允许写入：** `demos/runtime-developer-toolkit/**`、新的集成/验收测试，以及直接
描述三界面边界的维护性顶层/开发文档。

**排除：** 产品协议/core/backend/frontend 实现、依赖、导师文件；缺陷应退回所有者
Worker。

**依赖和分支：** 已接受并合并的 Workers 303、304、306；
`workers/worker-305-authoring-integration`。

**验收：** 从意图到包的端到端证据；两个前端均能构建；包保持独立运行时移交；工具包
验证新包而不消费创作状态；回归套件通过；边界文档准确。

```powershell
Set-Location -LiteralPath "C:\_HOLOLAB\code\CF WS"
$worktree = "C:\_HOLOLAB\code\CF WS\CartridgeFlow-worker-305-authoring-integration"
git -C ".\CartridgeFlow" worktree add $worktree -b "workers/worker-305-authoring-integration"

$prompt = @'
你是 worker-305-authoring-integration。只在已接受的创作者工作室和开发者控制台工作
合并后启动。负责最终跨界面证据和最小运行时移交更新。不要在其他 Worker 所有的文件
中修复产品缺陷；应将它们报告给所有者。

允许写入：demos/runtime-developer-toolkit/**、新的集成/验收测试，以及直接描述三
界面边界的维护性顶层/开发文档。排除 protocol、config、core、backend、两个前端实现、
依赖、PLAN.md、MENTOR_WORKERS.md。

证明从创作者意图与已接受 AI 变更集，经渐进冻结、确定性 Root Flow 编译到已签名
cartridge 生成的完整路径。验证两个前端独立构建。仅在公共 cartridge 移交改变处更新
运行时工具包；它不得消费聊天、设计会话、开发者仓库或前端状态。运行广泛回归证据，
且只提交允许范围。

验收：独立工具包验证已生成包；运行时输入中不存在创作私有状态；创作者/开发者界面
均能构建；集成和回归测试通过；文档明确陈述所有权边界。

## Worker 交付报告
变更文件：<每行一个路径>
提交 SHA：<完整 SHA>
测试：<每行一个命令和结果>
已知风险：<无或具体风险>
范围确认：<确认未更改排除路径>
'@
codex -C $worktree $prompt
```

## 16. 创作到运行时物化桥接

Worker 305 的审查确认：当前 Creator `compile_candidate` 只表达经验证的创作修订摘要，
并不会物化为 `root.flow.json`，也不会进入现有的 CF-CRE 签名打包基础设施。因此在声称
存在“从创作到生产包”的路径之前，必须先交付一个受限的后端/核心桥接。

桥接必须：

1. 仅接受当前、已接受、无阻塞发现且具有有效冻结事实的 Creator revision；过期 revision、
   未冻结步骤、未解决设计检查或不匹配的 compile candidate 必须稳定拒绝。
2. 从该 revision 的已接受语义步骤和关系确定性物化有效的 CF-FARP `root.flow.json`；不从
   聊天、提示词、浏览器本地状态或未接受提案推断运行时事实。
3. 将该 Root Flow 及最小公开发布元数据交给既有 CF-CRE 打包和签名能力，保留可审计的
   接受 revision、冻结快照和编译摘要/摘要值谱系。
4. 不将聊天、Creator 会话、来源内容或私有 URL、开发者仓库、前端状态、提示词、凭据或
   本地路径写入 Root Flow、公开发布载荷、签名归档或 API 响应。
5. 只生成签名的可移交 package；不得启动、模拟或宣称生产运行时执行。

### Worker 307

**名称与目标：** `worker-307-authoring-runtime-bridge`：将可生成的冻结 Creator revision
确定性物化为 CF-FARP Root Flow，并交给现有 CF-CRE 签名打包路径。

**状态：** `planned`

**允许写入：** `src/backend/**`、`src/core/studio/**`、直接相关的
`src/core/cartridge/**`、`scripts/tests/api/**`、`scripts/tests/studio/**`、
`scripts/tests/integration/**`，以及直接相关的维护性开发文档。

**排除：** `protocol/**`、`config/**`、两个前端实现、`demos/**`、根依赖文件、
`PLAN.md`、`MENTOR_WORKERS.md`。若现有发布契约不足以表达上述事实，停止并报告所需的
协议所有者工作，不得隐式扩展已发布协议。

**依赖和分支：** 已接受并合并的 Workers 302、303、304、306；
`workers/worker-307-authoring-runtime-bridge`。

**验收：** API/服务/集成测试证明完整正向路径从 Creator 已接受 revision 和 freeze 事实到
确定性 `root.flow.json`、已签名 CF-CRE 归档及既有签名验证；重复请求在相同事实下产生
稳定输出或受控的幂等结果。测试还必须证明过期、未冻结、被阻塞、候选不匹配、篡改签名和
任何私有创作/开发者/前端状态均被拒绝，且所有失败均不产生可安装包。两个前端与运行时
工具包不在本 Worker 修改范围内。

## 17. 视觉设计里程碑

在 Worker 303 实现验收前进行视觉探索：

1. 活跃设计对话期间的 AI 协作创作工作区。
2. 有部分接受和影响的 AI 提案审阅。
3. 语义画布上的渐进冻结与来源阻塞状态。
4. 使用已生成和个人蓝图的高级手动画布。
5. 独立、信息密集的开发者控制台。

下一张图片为里程碑 1。必须展示一个新颖创作者请求、三个创作者选择的来源、五个
AI 提议语义步骤、混合固化状态、一个未解决来源和一个待审阅变更集；不得展示应用
运行时、队列、媒体结果或原始工程术语。
