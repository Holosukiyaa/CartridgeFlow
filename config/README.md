# 配置边界

`config/` 只放能够随源码提交的底座声明、默认策略和安全模板。当前电脑上的模型、凭据、工具和数据源配置统一保存在 `.data/user/config/`。

## 目录

```text
config/
├─ base/                 基座能力声明与证据，属于源码的一部分
├─ defaults/
│  └─ llm_retry.json     当前底座实际采用的默认重试策略
└─ templates/
   ├─ llm/               Provider 与模型角色绑定模板
   └─ studio/            凭据与工具模板

.data/user/config/
├─ llm/
│  ├─ providers.json      本机 Provider，可能包含密钥
│  └─ assignments.json    本机模型角色绑定
└─ studio/
   ├─ credentials.json    本机环境变量凭据
   └─ resources.json      本机工具和数据源绑定
```

## 文件规则

| 文件 | 类型 | 说明 |
|---|---|---|
| `base/BASE_IMPLEMENTATION.json` | 源码配置 | 声明当前基座遵守的契约、支持的协议、profile、capability、tool pack 和 conformance 入口。 |
| `base/capability_evidence.json` | 源码配置 | 记录 capability 的实现入口、正向测试、失败测试和 UI 证据；改动必须和 conformance 一起提交。 |
| `defaults/llm_retry.json` | 默认策略 | 底座重试上限和退避策略，当前作为可审查的默认运行策略保留。 |
| `templates/llm/providers.json` | 安全模板 | Provider 地址、模型和连接字段的空白示例。 |
| `templates/llm/assignments.json` | 安全模板 | 默认角色、卡带和节点模型绑定的空白示例。 |
| `templates/studio/credentials.json` | 安全模板 | 本机凭据文件的空白结构。 |
| `templates/studio/resources.json` | 安全模板 | 全局工具与卡带角色绑定的空白结构。 |
| `.data/user/config/llm/providers.json` | 本机状态 | Provider 地址、模型和密钥入口；密钥值不能进入卡带或版本库。 |
| `.data/user/config/llm/assignments.json` | 本机状态 | steward、runtime、mentor、worker 以及卡带节点的模型绑定。 |
| `.data/user/config/studio/credentials.json` | 本机状态 | 环境变量凭据，界面只显示脱敏信息。 |
| `.data/user/config/studio/resources.json` | 本机状态 | 全局 MCP、远程 API、基座插件，以及 `bindings.roles` 中卡带工具角色到本机实例的映射。旧 `sources` 会在读取时迁移为工具。 |

## 使用原则

1. 新增本机配置时，先在 `config/templates/` 新增对应模板，模板中不得出现真实 URL、密钥或个人路径。
2. `providers.json`、`assignments.json`、`credentials.json` 和 `resources.json` 都属于 `.data/user/config/` 下的本机状态；旧路径会自动迁移，不会覆盖冲突内容。
3. 卡带只携带模型配方和工具配方，不携带这里的连接地址、密钥或全局绑定。
4. 卡带必须先声明 `resource_requirements`；本机资源按 role 一对一绑定，不能用“任意可用资源”自动绕过角色约束。
5. 修改 `base/BASE_IMPLEMENTATION.json`、`base/capability_evidence.json` 或 `defaults/llm_retry.json` 时，需要同时运行 conformance 测试。
6. 本机 JSON 采用原子写入；文件损坏时会先保存为同目录下的 `*.corrupt-时间.json`，再恢复安全默认值。
7. 配置文件路径是运行时契约的一部分；需要改变路径时，必须同步修改 `src/core/`、后端、前端提示和测试。

## 外部工具执行

| 本机资源类型 | 连接方式 | 卡带保存什么 |
|---|---|---|
| `mcp` + `command` | 官方 MCP SDK stdio client | `resource_role`、server、tool 和行为契约 |
| `mcp` + `endpoint` | 官方 MCP SDK Streamable HTTP client | 同上，不保存 endpoint 或认证信息 |
| `remote_api` | 直接 HTTP endpoint，或用 OpenAPI `operationId` 解析方法和路径 | 稳定 tool ID、参数 schema 和行为契约 |
| `plugin` + `command` | 不启用 shell 的 JSON stdin/stdout CLI | 稳定 tool ID 和行为契约 |

HTTP 的 `http_method`、`auth_header` 和 `auth_scheme` 都属于本机连接配置。`auth_env` 只保存环境变量名称，真实值由 `.data/user/config/studio/credentials.json` 提供，并且只在调用瞬间注入。

CLI 请求使用以下固定信封写入 stdin，进程必须在 stdout 返回 JSON 或文本：

```json
{
  "schema": "cartridgeflow.cli_tool_request.v1",
  "server": "tool_namespace",
  "tool": "tool_name",
  "arguments": {}
}
```

所有外部调用都受卡带 `contract.timeout_ms`、幂等重试、run 取消和宿主退出清理约束。CLI/MCP 子进程只继承当前资源选择的凭据，不继承其他本机密钥。公开结果会保留 adapter、状态码和稳定错误码，但不会返回 endpoint、command、认证值或本机绝对路径。
