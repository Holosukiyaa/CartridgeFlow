# 机器协议 Registry

`protocol/` 保存机器读取的协议身份和共享词表，不保存运行实现，也不能代替人类阅读的协议正文。

## 当前与历史

| 文件 | 状态 | 含义 |
|---|---|---|
| `CARTRIDGEFLOW-BASE-0.2.json` | active | 当前 Base Contract 身份和正文入口。 |
| `CF-FARP-0.6.json` | active | 当前默认 Flow 协议，依赖 Base Contract 0.2。 |
| `protocol_history.json` | lifecycle index | 旧版本的 recognized 状态和迁移目标。 |
| `CF-FARP-0.3.json` | published snapshot | 保留发布身份，不在运行支持矩阵中。 |
| `CF-FARP-0.4.json` | published snapshot | 保留发布身份，不在运行支持矩阵中。 |
| `CF-FARP-0.5.json` | published snapshot | 保留发布身份，不在运行支持矩阵中。 |
| `CF-FARP-0.1.json` | historical draft | 仅保留历史身份，不在基座支持矩阵中。 |
| `CF-FARP-0.2.json` | historical draft | 仅保留历史身份和迁移解析依据，不在基座支持矩阵中。 |

`ProtocolRegistry.recognizes_protocol()` 能识别历史身份；`supports_protocol()` 只对不在历史生命周期索引中的当前 registry 返回 true。最终运行支持还必须同时出现在 `config/base/BASE_IMPLEMENTATION.json.supported_protocols` 中。

## 共享词表

| 文件 | 作用 |
|---|---|
| `capabilities.json` | 协议可以声明的 capability 身份。 |
| `profiles.json` | capability 组合成的运行 profile。 |
| `tool_packs.json` | 基座通用工具包和工具身份。 |

## 三个权威来源

1. `docs/protocol/`：人类阅读的协议正文和治理规则。
2. `protocol/*.json`：机器发现协议、profile、capability 和 tool pack 的 registry。
3. `config/base/BASE_IMPLEMENTATION.json`：当前这一个基座真实支持的范围。

已发布 registry 和协议正文是不可变快照。实现 bug 修改 `src/core/protocol/` 和测试；协议语义变化必须新增完整版本，不能重写旧文件。
