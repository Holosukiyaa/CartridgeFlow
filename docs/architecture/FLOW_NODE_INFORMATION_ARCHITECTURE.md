# Flow 节点信息架构调研报告

> 状态：定稿，供 Lite 工作台下一轮节点重构使用
> 日期：2026-07-25
> 范围：只定义节点应该展示什么、何时展示、哪些内容进入详情卡；不规定最终视觉稿，也不在本轮修改节点 UI。

## 1. 结论

当前节点已经有了可用的视觉外壳，但信息架构仍然以“让所有卡片长得一样”为目标。这个方向在功能上不成立。

正确方向是：

1. **统一外壳，不统一正文。** 编号、图标、标题、类型、状态、端口和基础交互可以统一；正文必须由真实 `kind` 决定。
2. **主节点负责读懂流程。** 开发者不打开任何详情时，应能回答：这个节点为什么存在、需要什么、产出什么、怎么继续、是否安全、当前是否可运行。
3. **详情卡负责解释和编辑。** 完整 schema、映射、提示词、工具参数、原始输出、审计和恢复证据才进入详情卡。
4. **设计态和运行态是两套投影。** 运行时应让状态、耗时、结果、错误和选中分支覆盖低优先级配置摘要，而不是在设计信息下面继续堆字段。
5. **开始与结束是生命周期节点，不是缩小版业务节点。** 它们应使用专用结构；结束节点不得拥有普通后继节点。
6. **卫星详情卡必须按节点能力生成。** 现有“基础信息、节点类型、触发条件、输入输出、运行数据、快捷操作”六件套过于机械，应改为每种节点自己的详情集合。

一句话概括：**画布不是 JSON 查看器，也不是运行日志页；它是开发者判断流程语义、正确性和风险的第一现场。**

## 2. 调研依据

### 2.1 项目内部依据

- [CF-FARP 0.7](../protocol/flow-authoring/CARTRIDGEFLOW_FLOW_AUTHORING_RUNTIME_PROTOCOL_v0.7.md) 明确区分生命周期节点、能力节点和交互节点，并为每个 `kind` 规定不同契约。
- [Flow 合同校验器](../../src/core/protocol/flow_contract.py) 会按节点类型检查输入来源、schema、Decision Consume、工具白名单、副作用、权限、失败策略、远程资源角色和 primary output。这些字段的重要性本来就不相等。
- [节点执行器](../../src/core/lab/node_executor.py) 实际产生输入、输出、工具结果、Decision Envelope、Pending Interaction、错误和 Artifact 等运行证据。
- [当前节点视图适配器](../../src/frontend/src/pages/flow-workbench/flowNodeView.ts) 只为每类节点挑了两个固定字段，无法表达协议阻断项、分支语义和运行结果。
- [当前详情卡定义](../../src/frontend/src/pages/flow-workbench/nodeDetails.ts) 以通用栏目决定详情，而不是由节点能力决定。

### 2.2 外部成熟工具的共同实践

- Langflow 默认只在组件上显示必需和常用信息，高级参数进入检查面板；端口直接表达数据类型，单节点输出与日志通过 Inspect 查看。[Langflow Components](https://docs.langflow.org/concepts-components)
- Node-RED 把短运行状态放在节点旁，把配置错误作为明显标记；端口标签用于说明分支，完整属性和帮助进入编辑对话框或侧栏。[Node-RED Nodes](https://nodered.org/docs/user-guide/editor/workspace/nodes)、[Node status](https://nodered.org/docs/creating-nodes/status)
- AWS Step Functions 在画布上保留状态图，把选中步骤的 input、output、definition 放在独立详情标签中，不把原始数据常驻在节点卡上。[Workflow Studio](https://docs.aws.amazon.com/step-functions/latest/dg/workflow-studio.html)、[Execution step details](https://docs.aws.amazon.com/step-functions/latest/dg/workflow-studio-create.html)
- Azure Logic Apps 的运行详情按步骤提供状态、耗时、输入、输出和错误，并允许隐藏敏感输入输出。[Run history](https://learn.microsoft.com/en-us/azure/logic-apps/view-workflow-status-run-history)、[Secure workflow data](https://learn.microsoft.com/en-us/azure/logic-apps/logic-apps-securing-a-logic-app)

这些工具虽然产品目标不同，但结论一致：**节点常驻摘要、详细配置、运行数据和敏感数据必须分层。**

## 3. 现状审计

### 3.1 当前主节点字段的问题

| 当前类型 | 当前常驻字段 | 主要问题 |
|---|---|---|
| 开始/结束 | 节点类型、流程位置 | 只是在解释图形身份，没有说明触发、输入准备或交付是否成立。 |
| 输入 | 输入方式、数据格式 | 缺少来源、必填字段、输出 key、schema 和校验状态。 |
| 交互 | 交互模式、提交动作 | 缺少组件、输入绑定、具名动作、路由和暂停/恢复语义。 |
| AI 决策 | 模型角色、输出契约 | 缺少模型绑定状态、问题目标、输入、Decision Consume 和合法结果。 |
| MCP | 工具绑定、失败策略 | 缺少操作、副作用、权限、重放安全、参数和产物。 |
| 远程 | 远端服务、超时 | 缺少 resource role、绑定健康、操作、副作用和失败/恢复边界。 |
| 传递 | 来源变量、目标变量 | 方向基本正确，但没有映射操作、覆盖策略和类型兼容性。 |
| 交付 | 保存位置、交付契约 | 把“Run Store 中间保存”和“最终交付”混成同一语义。 |
| 门禁 | 门禁类型、分支数量 | 数量不能解释条件、默认分支、失败动作或人工等待。 |
| 自定义 | 执行器、副作用 | 无法判断扩展所有者、真实能力、契约和当前 Base 是否支持。 |

### 3.2 当前分类本身存在语义混合

1. `输入节点` 预设包含“读取文件、扫描项目、导入日志”。用户填写属于 `input`；主动读取文件或项目通常应是 `mcp_read`、`retrieval` 或插件，不应都伪装成用户输入。
2. `AI 决策节点` 同时承载分析、生成、修改、转换和总结。真正的决策需要结果状态和 consume；普通内容生成关注目标格式和输出质量，两者不能只靠同一组字段表达。
3. `交付节点` 的说明包含上下文、草稿、缓存和最终产物。普通 Run Store 写入本来就是节点 output；只有最终交付或跨 Run 持久化才值得成为独立节点。
4. `门禁节点` 同时覆盖 validation、routing、gate 和 human_gate。机器校验、条件路由与人工审批的关注点完全不同。
5. `自定义节点` 当前默认落成 `kind=transform`。这不是自定义能力，只是换了名称的转换节点。

### 3.3 当前示例 Flow 已暴露的信息缺口

对 `.data/user/dev_cartridges/dev.1/root.flow.json` 的审计发现：

- `complete` 是 terminal，却仍然指向 `custom_ms045x5r`。真正的结束节点不应有普通出边，这应直接成为画布 blocker。
- 多个 AI 决策节点没有明确 required input，主卡目前看不出数据从哪里来。
- 远程节点仍保存 `endpoint=remote://pending`，缺少 v0.7 所需的 `resource_role`、有效工具白名单和副作用重放策略。
- 多个 delivery 节点缺少明确 input；卡片却仍能表现得像“已配置”。

这说明 UI 不能只读取已有字段并排版。它需要消费协议规范化结果和静态分析 finding，明确显示“可运行、待配置、阻断”三种配置健康状态。

## 4. 主节点应该回答的六个问题

任何业务主节点在设计态都应尽量回答：

1. **职责：** 这个实例在当前 Flow 中具体负责什么，而不是该节点类别的一般说明。
2. **输入：** 它依赖哪些 Store key、用户数据、组件数据、工具计划或资源。
3. **核心行为：** 它进行收集、决策、读取、写入、转换、校验、路由、展示还是交付。
4. **输出：** 它写出什么 key、契约、Artifact 或交付结果。
5. **流向：** 单一路径可交给连线表达；多分支必须显示分支条件和默认路径。
6. **风险与健康：** 是否缺绑定、缺必填契约、产生副作用、等待权限、不可安全重放或无法交付。

如果某字段不能帮助回答这六个问题，它通常不应占据主节点黄金位置。

## 5. 统一外壳与动态正文

### 5.1 所有业务节点共用的外壳

主节点头部固定包含：

- 节点序号或图中定位号。
- 类型图标。
- 开发者命名的 `display_name`。
- 精确类型标签，例如“AI 决策”“MCP 读取”“人工门禁”，不能只写“处理节点”。
- 配置健康或运行状态，只显示一个主状态。
- 仅在异常时显示的风险标记，例如“外部副作用”“缺少模型绑定”“待人工确认”。

主节点正文固定拥有三个**插槽**，但插槽内容不固定：

1. `purpose`：当前节点的实例职责，最多两行。
2. `essential`：由 kind 决定的 2 至 4 组核心事实。
3. `flow`：输入、输出、Artifact 或分支关系；已经能由端口和连线清楚表达的内容不重复写。

### 5.2 不应常驻主节点的通用字段

- 稳定 node ID：放在标题 tooltip、复制菜单和协议详情中。
- `type=process`：绝大多数业务节点相同，没有辨识价值。
- `scope=sub_flow`：默认值不显示，只在 root、isolated、experimental 或跨 Flow 边界时显示。
- `effect=none`、普通 `writes_store`：默认语义不显示；高风险副作用必须显示。
- 单一 `next` 节点 ID：连线已经表达；只有路由、门禁或不可见跨 Flow 跳转需要文字。
- 完整 prompt、JSON schema、原始请求、原始响应、日志和 traceback。
- API Key、Authorization、私有 header、完整敏感输入输出。
- “可配置”“节点类型”“流程位置”这类没有行动价值的占位文案。

## 6. 设计态与运行态

### 6.1 设计态

设计态主状态只有三种：

- `可运行`：必需契约、绑定和拓扑均通过。
- `待配置`：节点尚未完整，但仍允许保存草稿。
- `阻断`：违反协议或不可能安全运行。

不要用绿色“已启用”覆盖更重要的配置缺口。缺失模型、工具、resource role、primary output、默认分支或输入来源时，主卡必须直接指出最优先的一项。

### 6.2 运行态

运行时主卡应把低优先级设计摘要替换为：

- `未执行 / 排队 / 运行中 / 等待用户 / 已完成 / 已跳过 / 失败 / 已取消`。
- 耗时、attempt 和重试状态。
- 最重要的结果摘要，例如命中数、选中分支、Artifact 数、Decision 状态。
- 失败时显示稳定 error code 和一句人话原因。
- 存在副作用时显示 `未发生 / 已发生 / 部分发生 / 结果未知`。
- 使用 probe、mock、dry-run 或 fallback 时必须明显标记。

完整输入输出、事件、错误 envelope、checkpoint 和恢复动作进入运行详情，不塞进主节点。

## 7. 详情子卡的使用规则

只有满足以下至少一项的信息才值得拆成可钉住详情子卡：

1. 字段较多，无法在主卡中准确概括。
2. 需要编辑复杂结构，例如 schema、映射、动作路由或重试策略。
3. 只在诊断时查看，例如原始输出、事件、审计、checkpoint。
4. 具有安全或恢复语义，需要单独核对。
5. 需要在无限画布上与多个节点并排比较。

以下内容不应再单独成为详情卡：

- 仅重复标题、描述和 node ID 的“基础信息”。
- 仅重复 kind、executor、scope、effect 的“节点类型”。这些字段应并入该节点的“协议契约”详情。
- “快捷操作”。复制、导出、删除属于节点上下文菜单，不是业务详情。
- 只有一个普通 `next` 的“触发条件”。普通上游/下游关系由画布表达。

建议的详情卡族不是固定六件套，而是按需从以下集合中选择：

- 配置与契约。
- 输入 schema 与映射。
- 输出契约与谱系。
- 分支与恢复。
- 资源、权限与副作用。
- 运行输入输出。
- 错误、审计与 checkpoint。
- Artifact 与交付证据。
- 组件与脚本安全。

## 8. 各类节点信息定义

### 8.1 开始节点 `system/start`

**主节点常驻**

- 触发来源：手动、API、计划、事件或父 Flow。
- 初始输入契约：必填字段数量和关键字段名。
- 运行前准备：环境、资源和输入是否通过预检。
- 存在多入口语义时显示入口名称；只有一条出边时不重复下游节点 ID。

**运行态**

- 触发来源、触发时间和 attempt。
- 初始输入是完整、缺失还是校验失败。
- 不在节点内重复整个 Run ID；Run ID 属于全局运行栏。

**详情子卡**

- `触发配置`：触发器、调用方、计划或事件过滤条件。
- `初始输入契约`：schema、默认值、敏感字段、示例。
- `运行前检查`：环境、依赖、资源绑定和兼容性 finding。

**不应展示**

- executor、effect、scope 等固定生命周期事实。
- 没有真实数据产出的“输出变量”。
- 泛泛的“流程入口”。

### 8.2 结束节点 `terminal`

**主节点常驻**

- 终态语义：成功、失败、取消或特定业务终止。
- 是否要求成功交付，还是只表示技术执行结束。
- primary output 或最终 Artifact。
- 交付准备状态和最重要的未满足项。

**运行态**

- `技术完成` 与 `成功交付` 必须分开显示。
- primary output 是否存在、有效、未失效。
- Artifact 数量、交付 revision 或失败终止原因。

**详情子卡**

- `终止条件`：哪些路径可到达该终态。
- `交付快照`：primary/auxiliary outputs、审批 revision、fallback 和未满足项。
- `产物证据`：Artifact 状态、hash、来源和失效关系。

**不应展示**

- 普通 output mapping 的重复副本。
- 任何普通后继节点。terminal 有出边应直接显示拓扑 blocker。

### 8.3 系统检查点与系统事件 `system/checkpoint`

系统 checkpoint、恢复边界和受控系统事件属于 Base 运行基础设施，默认不应作为普通节点出现在节点库中，也不应让开发者手动连线模拟恢复语义。

在画布上，它们只需要以可开关的轻量标记出现：checkpoint revision、创建位置、是否可恢复和完整性状态。完整 Store 摘要、Artifact 引用、replay metadata 和恢复动作进入运行详情。只有协议未来把某种系统节点明确开放为作者可配置能力时，才为它建立独立主卡模板。

### 8.4 输入节点 `input`

**主节点常驻**

- 输入来源和责任方：用户、人工、远程调用方或插件。
- 收集对象：关键字段名与必填数量，而不是只写 `manual`。
- 输出 Store key 和结构类型。
- 校验/准备状态：完整、缺字段、schema 未配置。

**运行态**

- 已收到、等待输入、缺失或校验失败。
- 接收字段数量、文件数量或值类型摘要；敏感值必须脱敏。
- 写入的 output key 和 revision。

**详情子卡**

- `字段与 schema`：类型、必填、默认值、长度和格式规则。
- `来源与映射`：source 到 Store output 的映射。
- `校验与敏感性`：规则、错误提示、敏感字段和留存策略。
- `本次输入`：脱敏后的实际输入和校验结果。

**不应展示**

- 完整用户内容、文件正文或密钥。
- 把读取文件、扫描项目、网页抓取继续算作普通 user input；这些应迁移到 retrieval 或 MCP read。

### 8.5 交互节点 `interaction`

交互节点必须先区分 `display / collect / review`，三者不能共享完全相同的正文。

**主节点常驻**

- 交互目的和 mode。
- `component_ref` 与组件解析/安全状态。
- 输入绑定摘要：界面会看到哪些声明数据。
- collect/review 的具名动作和路由，例如 `approve -> publish`。
- collect/review 的 output 与暂停/恢复策略；display 显示“展示后自动继续”。

**运行态**

- display：已呈现或呈现失败。
- collect/review：等待用户、已回答、已取消、已过期。
- 当前 input revision、answer revision 和最终 action。

**详情子卡**

- `组件契约`：组件版本、runtime、entry hash、支持模式。
- `输入绑定`：每个组件字段来自哪个 Store/Artifact。
- `动作与路由`：allowed actions、payload schema、静态目标和默认处理。
- `脚本安全`：sandbox、CSP、Host capabilities、network/origin finding。
- `交互运行`：草稿、revision、回答、恢复记录和审计。

**不应展示**

- 原始 HTML 或脚本正文。
- 把组件脚本当 executor 或隐藏业务流程。
- 没有动作的 display 节点显示“提交动作”。

### 8.6 AI 决策节点 `decision + llm`

**主节点常驻**

- 当前业务问题或目标，不使用“负责分析信息”这种类别描述。
- 模型角色及本机绑定健康状态，不显示 API Key。
- required input key 摘要。
- 合法结果：resolved、needs user input、blocked 中实际允许哪些。
- consume 投影：从 envelope 的什么业务值写到哪个下游 Store key。

**运行态**

- 模型是否真实调用、provider/model、耗时和 attempt。
- Decision 状态和 consume 是否成功。
- 等待用户时显示问题摘要；blocked 时显示第一项结构化 issue。
- token/cost 只有后端提供可信数据时才显示。

**详情子卡**

- `模型与配方`：model role、连接 ID、recipe 选项和绑定 finding。
- `提示与输入`：system/prompt 模板、变量映射和最终脱敏输入。
- `Decision 契约`：allowed statuses、payload schema、question 和 resume policy。
- `Consume 投影`：path、as、required 和 on_missing。
- `本次决策`：原始 envelope、校验 finding、模型元数据和实际投影。

**不应展示**

- 完整 system prompt、原始长响应和凭据。
- 只写 `decision_envelope.v1` 而不解释 consume 到哪里。
- 把工具已执行结果藏在决策节点中。

**额外建模建议**

当前“生成、修改、总结”都塞入 AI 决策。后续应至少在展示模型中区分“产生选择/计划的 Decision”和“产生内容的 Generation”。前者突出结果状态和 consume；后者突出目标格式、输出 schema 与质量约束。若协议没有稳定生成契约，不应仅靠显示名称假装两者等价。

协议还允许 `decision + rules` 和 `decision + human`。rules 决策应把“规则集、可能结果、默认结果、投影输出”放在主卡，不显示模型角色；需要异步等待人的 decision 应优先建模为 `human_gate`，避免把 Pending Interaction 隐藏在一个看似普通的决策节点中。

### 8.7 检索节点 `retrieval`

**主节点常驻**

- 检索来源或 resource role 及绑定状态。
- query input。
- 核心策略：top-k、过滤、rerank 是否启用。
- 输出集合 key 和结果类型。

**运行态**

- 命中数、空结果、耗时和数据源。
- 是否使用 fallback 或缓存。

**详情子卡**

- `查询映射`：query、filter、scope 和参数来源。
- `检索策略`：top-k、chunk、rerank、阈值和去重。
- `资源与权限`：连接 ID、资源状态和访问范围。
- `结果与谱系`：命中项、来源、revision 和截断信息。

**不应展示**

- 凭据、整篇文档内容或所有命中项。
- 把产生外部修改的能力伪装成 retrieval。

### 8.8 MCP 读取节点 `mcp_read`

**主节点常驻**

- 工具 ID 与具体 operation。
- 工具/资源绑定健康状态。
- 参数来源摘要和 output key。
- 明确的“只读”语义；若工具 contract 可能写入则直接阻断。

**运行态**

- 调用状态、耗时、attempt 和结果数量/大小。
- 实际工具 identity，不只显示友好名称。

**详情子卡**

- `工具契约`：params/result schema、capability、timeout。
- `参数映射`：固定值、Store 引用和校验结果。
- `资源绑定`：Manifest tool、resource role 和连接状态。
- `调用结果`：脱敏参数、结果摘要、错误和审计 call ID。

**不应展示**

- failure/replay 大段配置；只读节点通常不需要占据主卡。
- 工具原始长结果和本机密钥。

### 8.9 MCP 执行节点 `mcp_execute`

**主节点常驻**

- 工具 ID、operation 和绑定健康。
- 输入或 Tool Plan 来源与 output/Artifact。
- 最大副作用，例如写文件、改状态、外部动作。
- 权限/确认要求。
- 失败策略与重放安全摘要。

**运行态**

- queued/running/retrying/succeeded/failed/timed out。
- attempt、耗时、Artifact 数量。
- 副作用状态：未发生、已发生、部分发生、未知。
- 是否允许自动重试，或需要 replay confirmation。

**详情子卡**

- `工具与参数`：allowed tools、binding mode、Tool Plan 和 params schema。
- `权限与副作用`：permission、effect、audit 和外部影响说明。
- `失败与重放`：failure policy、retry、idempotency、deduplication 和 compensation。
- `调用审计`：call ID、参数 hash、attempt、Artifact、错误和 replay metadata。

**不应展示**

- 隐藏副作用或只用“失败即停止”概括安全边界。
- 在主卡展示完整工具参数或认证信息。

### 8.10 远程执行节点 `remote_call`

**主节点常驻**

- resource role 或服务别名，不展示 URL。
- 允许的 operation/tool。
- 本机资源绑定健康状态。
- 输入、输出/Artifact、timeout 和 failure policy 摘要。
- 存在外部副作用时显示权限和 replay 风险。

**运行态**

- 实际 adapter/provider、远程任务状态、耗时和 attempt。
- remote job ID 的短摘要。
- 超时、限流、认证、部分成功或 unknown effect。

**详情子卡**

- `请求与响应映射`：Store 到 params、result 到 output/Artifact。
- `资源契约`：resource role、allowed tools、连接 ID 和健康 finding。
- `超时与失败`：timeout、retry、circuit/fallback 和 replay policy。
- `远程事务`：调用 identity、脱敏请求响应、轮询状态和错误。

**不应展示**

- URL、API Key、Authorization、私有 header 或供应商私有连接参数。
- 只显示“Remote”和一个超时，让未绑定节点看起来可用。

### 8.11 传递节点 `transfer`

**主节点常驻**

- 映射动作：复制、重命名、合并或受限拆分。
- `source -> target`，多映射使用最多三行摘要和 `+N`。
- 覆盖/合并策略。
- 输入输出类型是否兼容。

**运行态**

- 实际读取和写入 key、revision、记录数或字节数。
- 缺失 required input、被跳过的 optional input 或覆盖冲突。

**详情子卡**

- `完整映射`：所有 source、path、target 和操作。
- `合并与冲突`：优先级、覆盖、append 和空值处理。
- `数据谱系`：输入 revision、输出 revision 和直接来源。

**不应展示**

- executor/effect 等固定事实。
- 内容过滤、格式转换或业务判断；这些应进入 transform/validation/routing。

### 8.12 转换节点 `transform`

**主节点常驻**

- 转换目标或规则名称。
- input -> output。
- 输入与输出数据类型/schema 变化。
- deterministic、rules 或 plugin；只有 plugin 等非默认执行器需要明显标记。
- 错误处理摘要。

**运行态**

- 处理数量、成功/拒绝数量、耗时和输出大小。
- schema 不匹配或表达式错误。

**详情子卡**

- `转换规则`：映射表达式、模板、插件引用或代码资产。
- `输入输出 schema`：字段差异和兼容性。
- `样例对照`：脱敏前后样例。
- `运行结果`：错误项和结果摘要。

**不应展示**

- 完整代码或巨型表达式。
- 在 transform 中隐藏 LLM、MCP 或远程调用。

### 8.13 校验节点 `validation`

**主节点常驻**

- 被校验的 input 或 Artifact。
- 规则集名称、规则数量和最高严重级别。
- 通过标准或阈值。
- 通过/不通过路径及 abort 语义。

**运行态**

- passed/failed、issue 数量和第一项关键问题。
- checked revision，避免展示针对旧内容的校验结果。

**详情子卡**

- `校验规则`：规则、阈值、severity 和字段范围。
- `结构化结果`：passed、issues、checked revision。
- `失败处理`：路由、阻断、继续报告和恢复条件。

**不应展示**

- 仅显示 `ok=true`。
- 把校验不通过和执行器崩溃混为同一“失败”。

### 8.14 路由节点 `routing`

**主节点常驻**

- 路由依据：字段、表达式或规则集。
- 每个具名分支的简短条件和目标，最多直接展示四个，其余 `+N`。
- 明确默认分支和无匹配策略。
- 静态分析发现的重叠、冲突或不可达分支。

**运行态**

- 被选中的分支和选择原因。
- 求值输入摘要；敏感值脱敏。
- 未匹配、冲突或表达式失败。

**详情子卡**

- `完整路由表`：优先级、条件、目标和默认分支。
- `静态分析`：冲突、覆盖、不可达和循环风险。
- `本次路由`：求值过程、选择结果和关联 revision。

**不应展示**

- 只有“分支数量”。
- 允许运行时动态生成任意节点 ID。

### 8.15 机器门禁 `gate`

**主节点常驻**

- 门禁目的和被检查对象。
- 必须满足的核心条件或检查数量。
- pass/fail 路径和失败后是阻断、报告还是回流。
- output contract 或证据状态。

**运行态**

- passed/failed、失败检查数量和选中路径。
- 依据的输入/Artifact revision。

**详情子卡**

- `检查项`：条件、证据和严重级别。
- `门禁结果`：结构化 gate result 和失败原因。
- `路由与恢复`：通过、不通过、回流和重新检查规则。

**不应展示**

- 只显示 kind 和分支数量。
- 把人工确认和机器规则混在一张模板里。

### 8.16 人工门禁 `human_gate`

**主节点常驻**

- 谁需要判断、判断什么。
- 可用动作，例如批准、退回、取消。
- 每个动作的静态路由。
- timeout、升级和 resume policy 摘要。
- 审批绑定的对象/revision。

**运行态**

- waiting user、answered、cancelled 或 expired。
- 回答人、时间、action 和 answer revision。
- 上游内容变化导致旧审批失效时必须显示。

**详情子卡**

- `问题与答案 schema`。
- `动作与路由`。
- `等待与恢复`：timeout、escalation、resume policy。
- `审批证据`：被审批 revision、回答、失效和审计历史。

**不应展示**

- 泛化的“请确认是否继续”。
- 客户端可自由提交 target node。

### 8.17 交付节点 `delivery`

**主节点常驻**

- primary output 或 primary Artifact。
- 交付类型/目标和辅助 Artifact 数量。
- 必需审批、readiness 和完整性要求。
- 当前 revision 和配置健康。

**运行态**

- 技术完成、交付成功、交付不完整或产物已失效。
- primary output 是否存在、文件/hash 是否有效。
- delivery revision、Artifact 数和 fallback 标记。

**详情子卡**

- `输出映射`：Store/Artifact 到 delivery snapshot。
- `准备检查`：缺失项、审批、完整性和有效性。
- `Artifact 与谱系`：producer、input revision、状态和失效链。
- `交付快照`：版本、摘要、辅助产物、fallback 和 supersedes。

**不应展示**

- 把普通中间 Store 写入描述成最终交付。
- 只显示保存位置而不显示 primary output 是否真实存在。

### 8.18 持久化/上下文节点（如后续保留）

CF-FARP 中节点声明 output 已经会写入当前 Run Store，因此“保存上下文”通常不需要独立节点。只有以下情况才应保留专用持久化节点：

- 跨 Run 持久化。
- append-only 日志或版本化草稿。
- 显式缓存、TTL 或共享状态。
- 文件/Artifact 写入。

若保留，主节点必须显示作用域、namespace/key、写入模式、冲突策略、留存时间和权限；运行态显示 revision 与实际写入结果。它不能继续借用 `delivery` 的名称和契约。

### 8.19 自定义/扩展节点

**主节点常驻**

- 扩展 owner、ID 和版本。
- overlay 声明的真实 kind、executor 和 effect。
- 输入输出契约摘要。
- Base 支持/激活/校验状态。
- 非默认权限和副作用。

**运行态**

- 实际 adapter/plugin/DLC 版本、操作和状态。
- 扩展返回的稳定指标或错误。

**详情子卡**

- `扩展描述`：owner、descriptor、hash、作用域和生命周期。
- `协议契约`：字段、schema、executor、effect 和 failure rules。
- `权限与隔离`：sandbox、allowed capabilities、资源和 replay。
- `扩展运行`：脱敏输入输出、事件和错误。

**不应展示**

- 在没有已激活 overlay 时显示为普通可运行节点。
- 用“自定义”掩盖未知 kind 或任意脚本。

## 9. 节点详情卡配置表

| 节点 | 默认可打开详情 | 仅有运行后出现 | 不再提供独立卡 |
|---|---|---|---|
| 开始 | 触发配置、初始输入契约、运行前检查 | 本次触发 | 基础信息、节点类型 |
| 结束 | 终止条件、交付快照、产物证据 | 本次终止 | 触发条件、快捷操作 |
| 系统检查点 | 默认不提供业务配置卡 | checkpoint、完整性与恢复证据 | 全部业务配置卡 |
| 输入 | 字段/schema、来源映射、校验与敏感性 | 本次输入 | 节点类型 |
| 交互 | 组件契约、输入绑定、动作路由、脚本安全 | 交互运行 | 通用触发条件 |
| AI 决策 | 模型配方、提示与输入、Decision 契约、Consume | 本次决策 | 通用类型卡 |
| 检索 | 查询映射、检索策略、资源权限 | 结果与谱系 | 通用 IO 卡 |
| MCP 读取 | 工具契约、参数映射、资源绑定 | 调用结果 | 快捷操作 |
| MCP 执行 | 工具参数、权限副作用、失败重放 | 调用审计 | 通用类型卡 |
| 远程 | 请求响应映射、资源契约、超时失败 | 远程事务 | 通用触发卡 |
| 传递 | 完整映射、冲突策略、数据谱系 | 本次传递 | 节点类型 |
| 转换 | 转换规则、输入输出 schema、样例 | 运行结果 | 通用 IO 卡 |
| 校验 | 校验规则、失败处理 | 结构化结果 | 通用类型卡 |
| 路由 | 完整路由表、静态分析 | 本次路由 | 普通 next 列表 |
| 机器门禁 | 检查项、路由恢复 | 门禁结果 | 通用触发卡 |
| 人工门禁 | 问题 schema、动作路由、等待恢复 | 审批证据 | 通用触发卡 |
| 交付 | 输出映射、准备检查、Artifact 谱系 | 交付快照 | 节点类型 |
| 自定义 | 扩展描述、协议契约、权限隔离 | 扩展运行 | 空泛基础信息 |

## 10. 数据与实现边界

### 10.1 不再由前端猜测

主卡片所需信息应来自三个明确来源：

1. **规范化节点契约**：kind、executor、effect、input/output、binding、policy。
2. **静态分析投影**：配置健康、缺失字段、拓扑和数据链 finding。
3. **运行投影**：状态、耗时、attempt、输入输出摘要、结果指标、错误和副作用状态。

前端不应再根据 `node_category`、preset 名称或空字段自行猜一个看似合理的值。

### 10.2 推荐的前端模型

下一轮实现应把当前通用 `buildNodeFields(categoryId)` 改为按协议 kind 区分的判别联合：

```text
NodePresentationModel
├─ LifecycleStartView
├─ LifecycleTerminalView
├─ InputView
├─ InteractionView
├─ DecisionView
├─ RetrievalView
├─ McpReadView
├─ McpExecuteView
├─ RemoteCallView
├─ TransferView
├─ TransformView
├─ ValidationView
├─ RoutingView
├─ GateView
├─ HumanGateView
├─ DeliveryView
└─ ExtensionView
```

每个 view 自己声明：

- `primaryFacts`：主卡常驻事实。
- `flowSummary`：输入、输出或分支。
- `riskBadges`：只显示非默认风险。
- `runSummary`：运行态替换内容。
- `detailSections`：该节点真实可用的详情卡。
- `findings`：配置 warning/blocker。

### 10.3 后端需要补足的投影

现有 `NodeRunState` 只有 status、input/output、error、tool result 和部分 decision 字段。为了让主卡不靠猜测，后端或 API 投影后续至少应补：

- started_at、completed_at、duration、attempt。
- execution mode、mock/dry-run/fallback。
- configuration findings 与 binding health。
- selected route 和 route reason。
- interaction status、action、revision。
- tool call status、effect outcome、idempotency/replay safety。
- Artifact identity/count/status。
- delivery readiness 与 delivery status。
- provider/tool/resource 的公开 identity；不包含密钥。

## 11. 推荐实施顺序

### P0：先修正确性表达

1. 用协议 kind 替代 `node_category` 作为展示分派依据。
2. 加入配置健康与 blocker，让未绑定或不完整节点不能伪装成可运行。
3. 专门实现开始、结束、输入、交互、AI 决策、MCP 执行和交付模板。
4. 拆开 validation、routing、gate、human_gate。
5. 运行态显示错误、Decision 状态、选中分支、副作用和交付状态。

### P1：再修详情体系

1. 删除通用“基础信息/节点类型/快捷操作”卫星卡。
2. 按本报告的节点详情表生成子菜单。
3. 保留现有可拖动、可钉住、刷新恢复和虚线归属关系。
4. 让详情卡读取同一个规范化 view model，避免主卡与详情互相矛盾。

### P2：最后做密度和比较能力

1. 支持主卡“摘要/展开”两档，而不是所有节点固定同高。
2. 支持同类详情并排比较，例如两个 Decision 的 Consume、两个 Tool 的权限和重放策略。
3. 为长 Flow 提供语义缩放：远景只看类型、状态、风险和分支，近景再看正文。

## 12. 验收标准

下一轮节点重构只有满足以下条件才算完成：

- 不打开详情即可指出每个节点的职责、输入、输出和流向。
- 缺模型、工具、资源、schema、默认分支或 primary output 时，主卡直接可见。
- 副作用、权限和不可安全重放不会藏在详情中。
- 单一路径不重复写 next；多分支可以在节点上读懂。
- 运行时能区分未执行、等待、完成、失败、跳过和取消。
- Decision 能看懂 envelope 状态和 consume 去向。
- Interaction 能看懂组件、动作、路由和等待状态。
- Delivery 能区分技术完成与成功交付。
- 详情子菜单随节点类型变化，不再每个节点都出现同一套卡。
- 敏感输入、凭据、完整 prompt、原始长响应和 traceback 不常驻画布。
- 开始节点没有虚构输出；结束节点没有普通出边。

## 13. 最终判断

现有大节点的宽度、留白、色彩、实线主流程和虚线详情归属都可以保留。需要推倒的不是视觉，而是 `flowNodeView.ts` 中“每类两个字段”和 `nodeDetails.ts` 中“所有节点共用详情栏目”的数据组织方式。

下一轮不应继续逐个往卡片里加字段。应先建立按 `kind` 分派的 `NodePresentationModel`，再让主节点、详情卡、运行态和静态分析共同消费它。这样视觉成果可以保留，功能也能经得起开发者实际搭 Flow、查数据链、审副作用和定位失败。

## 14. 落地状态（LITE-028）

本报告的 P0 与 P1 已在 Lite 工作台落地：

- `flowNodeView.ts` 现在是唯一的节点展示模型入口。它先读取生命周期与真实协议 `kind`，再按动作和旧分类做兼容回退，统一生成主卡事实、流向摘要、运行态、配置健康和详情数据。
- `FlowNodeCard.tsx` 不再按视觉分类套用相同字段。开始、结束、输入、交互、决策、检索、MCP、远程、传递、转换、校验、路由、门禁、交付和扩展节点分别显示与开发、排错直接相关的事实。
- 配置健康分为 `ready`、`draft` 和 `blocked`。缺模型角色、工具、资源、schema、默认分支、primary output 等问题会直接出现在主节点，不再伪装成可运行状态。
- `nodeDetails.ts` 按节点能力生成详情菜单；旧的“基础信息/节点类型/触发条件/输入输出/快捷操作”持久化值会迁移到新的能力分区，避免刷新后丢失已钉住详情。
- `NodeDetailCard.tsx` 与主节点消费同一展示模型。详情只补充契约、输入、输出、组件、模型、资源、路由、安全、运行和产物信息，不再重复主卡。
- `assert_node_information_architecture.mjs` 对真实 24 节点 Flow 检查语义类型、配置健康、主卡分区、详情菜单和页面溢出；截图回归覆盖 100%、125%、详情展开和右键菜单。

静态展示现在也能暴露真实流程缺陷。例如结束节点存在出边、交付节点没有 primary output、远程节点缺资源角色或失败策略时，主卡会直接标为阻断。后续 P2 可以继续处理摘要/展开密度与同类节点对比，但不再改变本轮建立的数据边界。
