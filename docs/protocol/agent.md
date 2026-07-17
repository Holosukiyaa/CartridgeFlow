# CartridgeFlow Protocol Documents Agent Note

本文是给后续 AI / Agent 的协议入口说明。本文只提供目录级提醒和摘要，不是协议正文，不得替代本目录下的源文件。

## 1. 本目录的性质

`docs/protocol/` 存放 CartridgeFlow 当前规范化工作的核心协议文件。这些文件定义卡带、流程、基座、运行时、兼容性检测和认证标签的边界，是后续继续搭流程、改基座、写生产底座时必须遵守的上层约束。

任何针对单个卡带或单个流程的便利性改动，都不得绕过这些协议直接修改系统边界。如果协议确实不足，应提出版本化协议变更，而不是让开发底座随某个流程漂移。

## 2. 协议文件摘要

### 2.1 `CARTRIDGEFLOW_BASE_CONTRACT_v0.1.md`

该文件定义 CartridgeFlow 规范基座契约 v0.1，重点约束：

- 协议与基座实现的分离关系。
- 开发者环境与生产交付环境的职责边界。
- 基座声明、能力声明、工具包声明、兼容性检查、认证标签的基本规则。
- 卡带包、manifest、root flow、节点、边、数据链、工具、运行时、测试台、产物和版本治理的共同底线。

阅读场景：

- 修改基座能力、能力声明、工具包、兼容性报告或认证规则前。
- 调整卡带包结构、manifest 规范、流程图结构、运行时边界前。
- 判断某个便利功能是否会破坏系统整体性前。

### 2.2 `CARTRIDGEFLOW_FLOW_AUTHORING_RUNTIME_PROTOCOL_v0.1.md`

该文件定义流程搭建与运行协议，协议编号为 `CF-FARP-0.1`，重点约束：

- 卡带在搭建流程、保存流程、运行流程、测试流程、打包交付时必须遵守的协议边界。
- manifest、root flow、节点、边、数据映射、输入输出、工具调用、产物生成、错误处理、测试台和认证流程的可验证规则。
- 同一协议版本下，不同合规基座之间运行共同支持卡带的条件。

阅读场景：

- 修改 flow authoring、runtime execution、node executor、dev flow manager、runner、validator 或测试台行为前。
- 为卡带添加协议认证标签前。
- 实现或调用协议符合性检测接口前。

### 2.3 `CARTRIDGEFLOW_FLOW_AUTHORING_RUNTIME_PROTOCOL_v0.2.md`

该文件定义动态决策流程历史版本，协议编号为 `CF-FARP-0.2`。它保留了统一 process 节点、kind / executor / effect 分层和 MCP 副作用边界，是 v0.3 的直接前置版本，但不再作为新流程的优先基准。重点约束：

- `input` 节点可以出现多次，`manifest.inputs` 是输入 schema 注册表，不是唯一入料口。
- 用户层主要业务节点统一显示为“后缀 + 节点”，例如“输入节点”“AI决策节点”“MCP执行节点”。
- 协议层业务节点统一使用 `type=process`，并必须声明 `kind`、`executor`、`effect`。
- AI 节点应表达为 `kind=decision`、`executor=llm`、`effect=none`，不直接执行工具副作用。
- RAG / 检索节点应表达为 `kind=retrieval` 或 `kind=mcp_read`，并输出上下文包或协议等价结构。
- 传递节点应表达为 `kind=transfer`、`executor=deterministic`、`effect=writes_store`，只搬运、合并、重命名 store 数据。
- 有副作用的 MCP / 工具执行应表达为 `kind=mcp_execute`，并声明 `tool_binding`、`allowed_tools`、权限、失败策略和日志。
- MCP 工具不强制绑定 AI；如果由 AI 决策驱动，必须通过 `tool_plan.v1` 和工具门禁。
- 协议硬类型和 UI 显示类型分离，UI 可以显示“资料检索节点”，但运行语义仍来自协议字段。

注意：v0.2 是历史协议版本。新建含 AI 决策交互的卡带应优先使用 v0.4。

### 2.4 `CARTRIDGEFLOW_FLOW_AUTHORING_RUNTIME_PROTOCOL_v0.3.md`

该文件定义交互式决策与可恢复运行协议，协议编号为 `CF-FARP-0.3`。它是 v0.4 的历史前置版本，重点约束：

- AI 决策节点必须表达为 `kind=decision`、`executor=llm`、`effect=none`。
- AI 决策节点必须输出 `decision_envelope.v1`，不得用自然语言替代结构化决策包。
- 决策结果至少区分 `resolved`、`needs_user_input`、`blocked`。
- `needs_user_input` 必须让运行进入 `paused_waiting_user`，并记录 pending interaction。
- 测试台必须区分 mock、offline fallback 和 live LLM，不得把模拟结果伪装成真实模型结果。
- AI 决策驱动工具时，必须通过 `decision_envelope.v1 -> gate -> mcp_execute`，不得由 AI 节点直接执行工具。
- 基座只支持暂停时，不得声称支持 `runtime_resume_after_user_input`；恢复能力必须单独声明。

### 2.5 `CARTRIDGEFLOW_FLOW_AUTHORING_RUNTIME_PROTOCOL_v0.4.md`

该文件定义完整的流程搭建与运行协议正文，协议编号为 `CF-FARP-0.4`，状态为 active。它是当前新流程搭建的优先协议基准，不再是 v0.3 的增量补丁；阅读 v0.4 不应要求回看 v0.3。重点约束：

- v0.4 supersedes v0.3，但不得改写 v0.3 源文件含义。
- v0.4 正文必须完整覆盖卡带包结构、manifest、runtime contract、delivery readiness、root flow、节点模型、Store、工具、副作用、测试台、兼容性和认证规则。
- AI 决策节点继续输出完整 `decision_envelope.v1` 到节点 `output`。
- AI 决策节点如果允许 `resolved`，必须声明 `decision_contract.consume`。
- `decision_contract.consume.path` 显式声明从 envelope 中读取的业务值，例如 `payload.decision` 或 `payload.asset_specs`。
- `decision_contract.consume.as` 显式声明写入后续节点消费的 store key。
- 基座不得通过隐式命名规则自动推断消费 key。
- 测试台必须展示完整 envelope、consume path、consume as 和实际消费值。

## 3. 后续 Agent 必读规则

1. 修改协议、基座、兼容性检测、认证标签、manifest 语义、root flow 语义、节点执行语义、运行时边界前，必须先阅读本文件。
2. 如果需要具体规则，必须继续阅读对应协议源文件，不得只根据本文摘要推断。
3. 不得为了让某一个卡带通过而临时放宽协议约束。
4. 不得把开发底座的偶然能力当成协议保证。只有协议、基座声明和能力声明共同确认的行为才可视为可移植能力。
5. 协议变更必须走版本化路径。破坏性调整应形成新协议版本，而不是直接覆盖 v0.1 的含义。
6. 新增协议版本时，必须同步机器可读声明、协议目录入口、能力词表和后续 AI 升级技能。
7. 新建 AI 交互式流程时，默认以 `CF-FARP@0.4` 为基准；只有维护旧卡带时才回看 v0.1、v0.2 或 v0.3。

## 4. 相关实现入口

- 机器可读协议声明位于根目录 `protocol/`。
- 后续 AI 的协议升级技能位于 `skills/cartridgeflow-protocol-upgrader/`。
- 当前基座声明位于根目录 `BASE_IMPLEMENTATION.json`。
- 协议相关核心实现位于 `core/protocol/`。
- 卡带校验、注册和运行相关实现主要位于 `core/cartridge/`。
- 开发工作台流程相关实现主要位于 `core/lab/` 和 `frontend/src/pages/flow-workbench/`。

以上实现必须服从本目录协议源文件。实现可以扩展，但不能无版本地改写协议含义。
