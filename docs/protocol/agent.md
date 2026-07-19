# CartridgeFlow Protocol Documents Agent Note

本文是协议入口说明，不是协议正文。

## 当前基准

新卡带和新基座能力默认使用 `CF-FARP@0.5`：

```text
docs/protocol/CARTRIDGEFLOW_FLOW_AUTHORING_RUNTIME_PROTOCOL_v0.5.md
protocol/CF-FARP-0.5.json
```

v0.5 是完整独立协议。阅读或实现 v0.5 不得依赖历史 FARP 文档，也不得依赖任意领域伴随协议。`CARTRIDGEFLOW_BASE_CONTRACT_v0.1.md` 仍定义协议与具体基座声明之间的通用关系。

## v0.5 重点

- 业务节点统一使用 `type=process`，并声明 `kind`、`executor`、`effect`。
- AI 决策输出 `decision_envelope.v1`；业务值必须通过 `decision_contract.consume` 显式投影。
- `needs_user_input` 必须暂停为 `paused_waiting_user`，提交后按恢复契约继续。
- 有副作用的工具节点必须声明工具白名单、权限、失败策略和审计。
- 卡带专用代码使用 `portable_dlc` 打包；基座只提供通用校验、隔离 worker、作用域 Registry、前端 sandbox 和卸载生命周期。
- DLC 的后端、前端、领域协议、工作流和测试必须由卡带包拥有。
- 卸载删除包代码和私有数据，保留用户产物和共享依赖。

## 领域协议

领域协议不是 FARP v0.5 的组成部分。使用领域协议的卡带必须把其 registry、正文和实现放入自己的 `dlc/protocols/` 与 `dlc/backend/`，并通过 descriptor 声明。未安装该卡带时，根 `protocol/` 和基座能力词表不得保留领域协议副作用。

系列 3D 卡带的 CRCP 材料位于：

```text
cartridges/dev/dev.series_3d_episode_factory/dlc/protocols/
```

只有修改该卡带的创作重绘边界时才读取它；普通卡带不承担 CRCP 规则。

## 后续 Agent 规则

1. 修改协议、兼容性、认证、manifest、root flow、运行时或扩展宿主前，先阅读 v0.5 正文。
2. 不得为了单个卡带放宽基座通用约束。
3. 语义变化必须新增协议版本，不能原地改写只读协议。
4. 新增能力时同步机器声明、profiles、capabilities、基座声明和 conformance 测试。
5. 卡带业务功能必须放入卡带包；卸载残留测试是完成条件。

## 实现入口

- 基座声明：`BASE_IMPLEMENTATION.json`
- 协议 registry：`protocol/`
- 通用协议实现：`core/protocol/`
- Portable DLC 宿主：`core/extensions/`
- 卡带校验和运行：`core/cartridge/`
- 流程执行：`core/lab/`
- 通用 sandbox host：`frontend/src/components/DlcSandboxFrame.tsx`
