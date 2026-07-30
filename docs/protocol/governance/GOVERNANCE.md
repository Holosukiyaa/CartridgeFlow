# CartridgeFlow Protocol Documents Agent Note

## CF-FARP@1.0 当前边界

`CF-FARP@1.0` 是当前正式且受支持的执行计划协议。Base 已声明令牌运行、
兼容性分派、持久化恢复、透明工具门禁与认证所需证据；默认新建流程使用 1.0。
历史版本只能通过其自身契约运行，任何升级都必须显式完成并重新校验，不能由
保存、打开或运行操作静默触发。

本文是协议入口说明，不是协议正文。

> 文档状态：当前协议治理规则。它约束协议修改和 Flow 编写，但不是协议正文。

## 当前基准

新协议设计和新卡带目标默认使用 `CARTRIDGEFLOW-BASE@0.2 + CF-FARP@1.0`：

```text
docs/protocol/base-contract/CARTRIDGEFLOW_BASE_CONTRACT_v0.2.md
docs/protocol/flow-authoring/CARTRIDGEFLOW_FLOW_AUTHORING_RUNTIME_PROTOCOL_v1.0.md
protocol/base/CARTRIDGEFLOW-BASE-0.2.json
protocol/releases/CF-FARP-0.9.json
```

Base v0.2 与 FARP v1.0 都是完整独立协议。阅读或实现目标版本不得依赖历史正文，也不得依赖任意领域伴随协议。Base Contract 约束宿主边界，CF-FARP 约束 Flow 创作、静态分析、运行语义与 MCP/DLC 透明执行，两者版本不要求相同。

## 版本支持策略

最新正式规范是 `CF-FARP@1.0`。当前参考基座声明 `CF-FARP@0.6 partial`、`CF-FARP@0.7 partial`、`CF-FARP@0.8 partial` 与 `CF-FARP@1.0 partial`。v1.0 当前覆盖静态 parser、descriptor v3、source digest guard、结构化 source editing、Analyzer 透明度 finding、资源目录 v2 投影、declared operation trace events 与 operation capability broker preflight；OS 级 sandbox 与更细粒度资源目标 enforcement 仍按 partial evidence 管理。v0.8 已实现 Analyzer、typed control filtering、结构化 I/O、统一 Flow 资源目录、目标门禁、失败路径和 conformance 证据；`CF-FARP@0.1` 至 `0.5` 继续处于 `recognized` 状态。

版本判断必须经过三层：

1. `protocol/catalog/release_manifest.json` 是唯一版本生命周期、默认新建版本、迁移目标和快照路径来源。
2. `config/base/BASE_IMPLEMENTATION.json.supported_protocols` 判断当前基座是否承诺执行。
3. compatibility report 在执行任何业务代码前 fail closed。

`protocol/governance/protocol_history.json` 仅保留旧版兼容镜像，必须与 release manifest 一致。修改协议发布状态时，先修改 release manifest，再同步镜像、Base 声明、文档和证据；`python scripts/audit_protocol_governance.py` 必须通过。

不能只显示“不支持”。已进入历史索引但 Base 未实现的旧版本必须返回稳定错误 `recognized_unsupported_protocol` 和当前可执行迁移目标；未知身份返回 `unknown_protocol`。

核心不承诺永久保留旧 validator、adapter 或 DLC 激活路径。旧正文和 registry 快照在独立只读归档建立之前保留为发布证据；归档必须保存稳定地址、SHA-256 和迁移说明。完成归档后，仓库可移除旧正文和旧 registry，只保留轻量历史索引。

## v1.0 重点

- v1.0 不改写 v0.8，旧 DLC/MCP 工具必须诚实标记为 `legacy_opaque`。
- 画布拥有 MCP/DLC 复合工具的业务编排；Python 只实现原子 operation。
- 每个 v1.0 MCP 画布节点对应唯一 `dlc/mcp_nodes/<node_id>.py` 入口文件。
- 展开图、`cartridgeflow.mcp_source_model.v1` 和 operation runtime trace 使用同一稳定 operation id。
- Base 后端静态解析源码，不 import、不执行 DLC；前端只消费 source model 和 source map。
- 网络、文件、Artifact、secret 和子进程通过 Base broker 调用，不允许 DLC 直接绕过透明契约。
- 无法披露内部实现的远程 MCP 必须显示为 `contract_only` 或 `opaque`，不得生成推测内部节点。

## v0.8 重点

- 业务流程与执行契约是 Authoring Facts；工程关系和诊断只能由 Analyzer 派生。
- v0.8 作者源文件使用结构化 `inputs`、`outputs`、binding 和 schema，禁止依赖字段名或视觉线隐式连接。
- 可执行关系使用 typed control semantics；Runner 不得消费 data/resource relation 或未知 edge。
- 统一 Flow Analyzer 输出 digest-bound `cartridgeflow.flow_analysis.v1`、规范化拓扑、工程关系和稳定 findings。
- draft、dev、preview、production、package、publish 使用不同但明确的目标门禁，过期报告不能放行。
- 创作 AI 通过 Authoring API 修改源事实，Analyzer 只读分析，safe/confirm/manual 修复分级且修改后强制复检。
- 影响业务质量的 fallback 必须声明并在 Run/Delivery 中记录实际使用情况。

v0.8 完整保留 v0.7 的以下安全与运行边界：

- 业务节点统一使用 `type=process`，作者视角分为能力节点与 `kind=interaction` 交互节点。
- 节点稳定 id 与可编辑 `display_name` 分离。
- 卡带资产通过稳定 ID、media type、size 与 hash 注册；运行产物不冒充包资产。
- 被动 HTML 禁止脚本和主动内容；任何脚本必须进入 Portable DLC descriptor v2 frontend component。
- 脚本只在专用不可信 origin 和无同源 iframe 中运行，使用严格 CSP、逐文件 hash、进程隔离、一次性 Host channel 和最小 capability。
- 交互组件只能维护草稿或提出具名 action intent，最终提交由 iframe 外的 Host control 完成，Flow 路由保持静态可分析。
- AI 决策输出 `decision_envelope.v1`；业务值必须通过 `decision_contract.consume` 显式投影。
- `needs_user_input` 必须暂停为 `paused_waiting_user`，提交后按恢复契约继续。
- 有副作用的工具节点必须声明工具白名单、权限、失败策略和审计。
- 卡带专用代码使用 `portable_dlc` 打包；基座只提供通用校验、隔离 worker、作用域 Registry、前端 sandbox 和卸载生命周期。
- DLC 的后端、前端、领域协议、工作流和测试必须由卡带包拥有。
- 卸载删除包代码和私有数据，保留用户产物和共享依赖。

## 领域协议

领域协议不是 FARP current release 的组成部分。使用领域协议的卡带必须把其 registry、正文和实现放入自己的 `dlc/protocols/` 与 `dlc/backend/`，并通过 descriptor 声明。未安装该卡带时，根 `protocol/` 和基座能力词表不得保留领域协议副作用。

正式基座不预装领域协议。只有正在开发或安装的卡带明确声明 companion protocol 时，才读取该卡带自己的 `dlc/protocols/`。

## 后续 Agent 规则

1. 修改新协议语义、Analyzer、资产、交互节点或扩展宿主前，先读取 release manifest 指定的 current Base/FARP 正文；修复兼容版本时同时核对对应快照，不能用 current 语义冒充旧版事实。
2. 不得为了单个卡带放宽基座通用约束。
3. 语义变化必须新增协议版本，不能原地改写只读协议。
4. 新增能力时同步版本化 registry、profiles、capabilities 和 conformance 目标；只有实现、失败路径和证据齐全后才加入基座支持声明。
5. 卡带业务功能必须放入卡带包；卸载残留测试是完成条件。

## 实现入口

- 基座声明：`config/base/BASE_IMPLEMENTATION.json`
- 协议 registry：`protocol/`
- 通用协议实现：`src/core/protocol/`
- Portable DLC 宿主：`src/core/extensions/`
- 卡带校验和运行：`src/core/cartridge/`
- 流程执行：`src/core/lab/`
- 通用 sandbox host：`src/frontend/src/components/DlcSandboxFrame.tsx`
