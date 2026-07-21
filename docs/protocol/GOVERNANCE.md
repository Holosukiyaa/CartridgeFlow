# CartridgeFlow Protocol Documents Agent Note

本文是协议入口说明，不是协议正文。

> 文档状态：当前协议治理规则。它约束协议修改和 Flow 编写，但不是协议正文。

## 当前基准

新卡带和新基座能力默认使用 `CARTRIDGEFLOW-BASE@0.2 + CF-FARP@0.6`：

```text
docs/protocol/CARTRIDGEFLOW_BASE_CONTRACT_v0.2.md
docs/protocol/CARTRIDGEFLOW_FLOW_AUTHORING_RUNTIME_PROTOCOL_v0.6.md
protocol/CARTRIDGEFLOW-BASE-0.2.json
protocol/CF-FARP-0.6.json
```

Base v0.2 与 FARP v0.6 都是完整独立协议。阅读或实现当前版本不得依赖历史正文，也不得依赖任意领域伴随协议。Base Contract 约束宿主边界，CF-FARP 约束 Flow 语义，两者版本不要求相同。

## 版本支持策略

当前基座只运行 `CF-FARP@0.6`。`CF-FARP@0.1` 至 `0.5` 进入 `recognized` 状态：基座可以报告其身份和迁移目标，但不得执行 Root Flow、激活 Portable DLC 或签发认证。

版本判断必须经过三层：

1. `protocol/protocol_history.json` 判断旧版本是否已知，并提供迁移目标。
2. `config/base/BASE_IMPLEMENTATION.json.supported_protocols` 判断当前基座是否承诺执行。
3. compatibility report 在执行任何业务代码前 fail closed。

不能只显示“不支持”。已识别旧版本必须返回稳定错误 `recognized_unsupported_protocol` 和 `CF-FARP@0.6` 迁移目标；未知身份返回 `unknown_protocol`。

核心不承诺永久保留旧 validator、adapter 或 DLC 激活路径。旧正文和 registry 快照在独立只读归档建立之前保留为发布证据；归档必须保存稳定地址、SHA-256 和迁移说明。完成归档后，仓库可移除旧正文和旧 registry，只保留轻量历史索引。

## v0.6 重点

- 业务节点统一使用 `type=process`，并声明 `kind`、`executor`、`effect`。
- AI 决策输出 `decision_envelope.v1`；业务值必须通过 `decision_contract.consume` 显式投影。
- `needs_user_input` 必须暂停为 `paused_waiting_user`，提交后按恢复契约继续。
- 有副作用的工具节点必须声明工具白名单、权限、失败策略和审计。
- 卡带专用代码使用 `portable_dlc` 打包；基座只提供通用校验、隔离 worker、作用域 Registry、前端 sandbox 和卸载生命周期。
- DLC 的后端、前端、领域协议、工作流和测试必须由卡带包拥有。
- 卸载删除包代码和私有数据，保留用户产物和共享依赖。

## 领域协议

领域协议不是 FARP v0.6 的组成部分。使用领域协议的卡带必须把其 registry、正文和实现放入自己的 `dlc/protocols/` 与 `dlc/backend/`，并通过 descriptor 声明。未安装该卡带时，根 `protocol/` 和基座能力词表不得保留领域协议副作用。

正式基座不预装领域协议。只有正在开发或安装的卡带明确声明 companion protocol 时，才读取该卡带自己的 `dlc/protocols/`。

## 后续 Agent 规则

1. 修改协议、兼容性、认证、manifest、root flow、运行时或扩展宿主前，先阅读 Base v0.2 和 FARP v0.6 正文。
2. 不得为了单个卡带放宽基座通用约束。
3. 语义变化必须新增协议版本，不能原地改写只读协议。
4. 新增能力时同步机器声明、profiles、capabilities、基座声明和 conformance 测试。
5. 卡带业务功能必须放入卡带包；卸载残留测试是完成条件。

## 实现入口

- 基座声明：`config/base/BASE_IMPLEMENTATION.json`
- 协议 registry：`protocol/`
- 通用协议实现：`src/core/protocol/`
- Portable DLC 宿主：`src/core/extensions/`
- 卡带校验和运行：`src/core/cartridge/`
- 流程执行：`src/core/lab/`
- 通用 sandbox host：`src/frontend/src/components/DlcSandboxFrame.tsx`
