# 机器协议 Registry

`protocol/` 保存机器读取的协议身份和共享词表，不保存运行实现，也不能代替人类阅读的协议正文。

## 当前与历史

| 文件 | 状态 | 含义 |
|---|---|---|
| `CARTRIDGEFLOW-BASE-0.2.json` | active | 当前 Base Contract 身份和正文入口。 |
| `CF-FARP-0.7.json` | active specification | 最新 Flow 协议；当前参考底座尚未声明运行支持。 |
| `CF-FARP-0.6.json` | supported previous | 当前参考底座实际运行的上一版 Flow 协议。 |
| `protocol_history.json` | lifecycle index | 旧版本的 recognized 状态和迁移目标。 |
| `CF-FARP-0.3.json` | published snapshot | 保留发布身份，不在运行支持矩阵中。 |
| `CF-FARP-0.4.json` | published snapshot | 保留发布身份，不在运行支持矩阵中。 |
| `CF-FARP-0.5.json` | published snapshot | 保留发布身份，不在运行支持矩阵中。 |
| `CF-FARP-0.1.json` | historical draft | 仅保留历史身份，不在基座支持矩阵中。 |
| `CF-FARP-0.2.json` | historical draft | 仅保留历史身份和迁移解析依据，不在基座支持矩阵中。 |

`ProtocolRegistry.recognizes_protocol()` 能识别历史身份；`supports_protocol()` 只说明仓库存在可解释的发布 registry。最终运行支持必须同时出现在 `config/base/BASE_IMPLEMENTATION.json.supported_protocols` 中。当前 `CF-FARP@0.7` 可被识别但不在 Base 支持矩阵中，因此运行前必须返回 `unsupported_protocol`。

## 共享词表

| 文件 | 作用 |
|---|---|
| `capabilities.json`、`profiles.json` | v0.6 及当前 Base 使用的 capability/profile 词表。 |
| `capabilities-0.7.json`、`profiles-0.7.json` | v0.7 独立快照使用的版本化词表。 |
| `tool_packs.json` | 基座通用工具包和工具身份。 |

## 三个权威来源

1. `docs/protocol/`：人类阅读的协议正文和治理规则。
2. `protocol/*.json`：机器发现协议、profile、capability 和 tool pack 的 registry。
3. `config/base/BASE_IMPLEMENTATION.json`：当前这一个基座真实支持的范围。

已发布 registry、版本化词表和协议正文是不可变快照。实现 bug 修改 `src/core/protocol/` 和测试；协议语义变化必须新增完整版本，不能重写旧文件。从 v0.7 起，新协议不得继续复用一个会被后续版本原地扩写的 capability/profile 文件。
