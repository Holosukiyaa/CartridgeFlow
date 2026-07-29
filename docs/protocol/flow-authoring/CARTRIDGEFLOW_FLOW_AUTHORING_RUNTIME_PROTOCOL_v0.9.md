# CartridgeFlow Flow Authoring Runtime Protocol v0.9

协议编号：`CF-FARP-0.9`

协议状态：active

发布状态：完整正文

依赖宿主契约：`CARTRIDGEFLOW-BASE@0.2`

替代版本：`CF-FARP@0.8`

关系：本文完整替代 v0.8，是独立、自包含的 Flow 创作、静态分析、运行与 MCP/DLC 透明执行规范。实现或认证 v0.9 不得依赖历史正文补足含义。v0.8 已发布语义保持只读；旧卡带和旧 DLC 工具通过兼容层运行时必须诚实标记为 `legacy_opaque`，不得静默迁移或冒充 v0.9 透明认证。

---

## 目录

1. [协议目标](#1-协议目标)
2. [继承边界](#2-继承边界)
3. [MCP/DLC 透明执行原则](#3-mcpdlc-透明执行原则)
4. [Profile 与 Capability](#4-profile-与-capability)
5. [透明度等级](#5-透明度等级)
6. [Portable DLC descriptor v3](#6-portable-dlc-descriptor-v3)
7. [MCP Python source format v1](#7-mcp-python-source-format-v1)
8. [静态源码模型](#8-静态源码模型)
9. [静态检查与拒绝规则](#9-静态检查与拒绝规则)
10. [结构化编辑](#10-结构化编辑)
11. [Analyzer 与资源目录](#11-analyzer-与资源目录)
12. [运行时与能力 Broker](#12-运行时与能力-broker)
13. [运行事件](#13-运行事件)
14. [前端画布表达](#14-前端画布表达)
15. [检查器与源码定位](#15-检查器与源码定位)
16. [兼容性与认证门禁](#16-兼容性与认证门禁)
17. [dev.ai-tech-daily 迁移要求](#17-devai-tech-daily-迁移要求)
18. [API 要求](#18-api-要求)
19. [测试计划](#19-测试计划)
20. [完成标准](#20-完成标准)
21. [禁止事项](#21-禁止事项)
22. [定稿前治理决策](#22-定稿前治理决策)

## 1. 协议目标

CF-FARP v0.9 在 v0.8 的 Flow 创作、结构化 I/O、Analyzer、typed control、fallback、Portable DLC 隔离和资源目录基础上，新增 MCP/DLC 工具内部透明执行要求。目标是防止 Root Flow 退化为一个 Python 应用启动图：画布必须拥有业务编排，Python 只能实现原子操作。

本协议要求：

- MCP 节点可以折叠为外层工具节点，也可以展开为内部 operation graph。
- 展开图、Python source model 和运行 stage trace 使用相同稳定 operation id。
- 每个可认证的本地 DLC MCP 节点对应唯一 Python 入口文件。
- fallback、重试、质量判断、资源访问、子进程和 Artifact 创建必须可见。
- 外部能力通过 Base broker 授权执行，不由 DLC 代码直接绕过。
- 无法披露或验证内部过程的远程 MCP 必须显示为黑盒。

## 2. 继承边界

v0.9 完整保留 v0.8 的以下语义，但不要求阅读 v0.8 正文才能实现本文：

- Manifest、Root Flow、业务节点、结构化 `inputs` / `outputs` / `binding`。
- `control_edges` 与 Runner 可执行拓扑过滤。
- `cartridgeflow.flow_analysis.v1`、source digest、target gates 和 finding contract。
- Decision Envelope、Decision Consume、Pending Interaction、Artifact、Checkpoint 和 runtime error envelope。
- Portable DLC 的卡带所有权、作用域隔离、Worker 生命周期、前端 sandbox 和卸载。
- 影响业务质量的 fallback 必须声明并记录实际使用。

v0.9 新增的约束只扩展 MCP/DLC 工具内部可观察性，不允许用新语义重写 v0.8 卡带。旧工具按旧协议运行时，其透明度必须为 `legacy_opaque`。

## 3. MCP/DLC 透明执行原则

1. 画布拥有业务编排。分阶段处理、条件分支、fallback、人工确认和副作用顺序必须存在于可分析声明中。
2. Python 只实现原子操作。RSS 解析、图片生成、编码调用可以在 Python 中实现，但跨阶段业务拓扑不得隐藏在函数体。
3. 一个 MCP 画布节点对应一个 Python 入口文件。禁止多个 MCP 节点共享大型 dispatcher。
4. 展开图必须是执行契约。前端不得根据函数名、注释或自然语言猜测内部流程。
5. 源码解析不得执行卡带代码。Base 只能静态解析受限格式。
6. 声明、实现和运行 trace 必须共享稳定 operation id。
7. 网络、文件、Artifact、secret 和子进程能力必须经过 Base broker。
8. 黑盒必须诚实显示。不能披露的远程 MCP 使用 `opaque` 或 `contract_only`。

## 4. Profile 与 Capability

v0.9 新增必选 Profile：

```text
tool_transparency
```

v0.9 新增能力：

```text
mcp_node_source_format_v1
mcp_node_file_identity
mcp_source_static_parse
mcp_source_model_v1
compound_tool_operation_graph
tool_stage_trace_v1
tool_source_provenance
explicit_fallback_policy
host_capability_broker
opaque_tool_visibility_guard
mcp_graph_authoring_operations
mcp_source_digest_guard
portable_dlc_descriptor_v3
tool_resource_catalog_v2
```

声明 `CF-FARP@0.9` 的卡带必须在 `runtime_contract.required_profiles` 中包含 `tool_transparency`，并要求与其透明度等级匹配的能力。Base 只有在 `BASE_IMPLEMENTATION.json` 与 conformance evidence 同时声明时，才可以运行或认证 v0.9。

## 5. 透明度等级

每个工具资源必须投影一个透明度等级：

| 等级 | 含义 | v0.9 规则 |
|---|---|---|
| `atomic` | 一个原子能力，没有隐藏业务拓扑 | 可显示单 operation、源码和运行事件 |
| `declared_graph` | 多个阶段组成的复合能力 | 必须提供可解析 operation graph |
| `contract_only` | 只知道接口、effect 和资源契约 | 只允许真正原子的远程调用 |
| `opaque` | 无法披露或验证内部过程 | UI 必须显示黑盒；有副作用的复合工具不能透明认证 |
| `legacy_opaque` | v0.8 或旧格式兼容工具 | 可兼容运行，不能取得 v0.9 透明认证 |

## 6. Portable DLC descriptor v3

v0.9 DLC descriptor 使用：

```json
{
  "schema": "cartridgeflow.portable_dlc.v3",
  "id": "example.media",
  "version": "1.0.0",
  "owner_cartridge": "example.media.cartridge",
  "scope": "cartridge",
  "tools": [
    {
      "node_id": "fetch_news",
      "server": "media",
      "tool": "fetch_rss",
      "handler": "run",
      "effect": "read_only",
      "description": "Fetch and normalize feeds.",
      "timeout_ms": 30000,
      "implementation": {
        "language": "python",
        "format": "cartridgeflow.mcp_python.v1",
        "entry": "dlc/mcp_nodes/fetch_news.py"
      },
      "transparency": "declared_graph",
      "source_digest": "sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    }
  ],
  "files": []
}
```

规则：

- `node_id` 与 Root Flow MCP 节点、Manifest tool、descriptor tool 和 Python `MCP_NODE.node_id` 必须一致。
- `implementation.entry` 必须是包内相对路径，且位于 `dlc/mcp_nodes/`。
- 一个入口文件只能声明一个 `MCP_NODE`。
- `dlc/backend/entry.py:invoke` 这类多工具动态 dispatcher 不得通过 v0.9 透明认证。
- 远程 MCP 没有本地 source 时使用 `contract_only` 或 `opaque`，并说明 provider identity 与不可披露原因。

## 7. MCP Python source format v1

新增源码格式：

```text
cartridgeflow.mcp_python.v1
```

文件顺序必须固定：

1. UTF-8 module docstring。
2. 允许的 import。
3. 静态 `MCP_NODE` 字面量。
4. 输入输出类型声明。
5. 使用 `@mcp_operation` 装饰的 operation 函数。
6. 静态 `OPERATIONS` 映射。
7. 标准 `run(ctx, inputs)`。

示例：

```python
"""Fetch and normalize technology RSS feeds."""

from cartridgeflow_dlc import McpContext, mcp_operation


MCP_NODE = {
    "schema": "cartridgeflow.mcp_python.v1",
    "node_id": "fetch_news",
    "server": "media",
    "tool": "fetch_rss",
    "effect": "read_only",
    "inputs": {"feed_set": {"type": "string"}},
    "outputs": {"candidates": {"type": "object"}},
    "operations": [
        {"id": "resolve_feeds", "kind": "transform"},
        {"id": "download_feeds", "kind": "network", "capability": "network.fetch"},
        {"id": "parse_feeds", "kind": "transform"}
    ],
    "edges": [
        {"from": "resolve_feeds", "to": "download_feeds", "kind": "control"},
        {"from": "download_feeds", "to": "parse_feeds", "kind": "control"}
    ],
    "fallbacks": [
        {
            "id": "download_transport_fallback",
            "from": "download_feeds",
            "on": ["network_transport_failed"],
            "mode": "explicit",
            "visible": True
        }
    ]
}


@mcp_operation("resolve_feeds")
def op_resolve_feeds(ctx: McpContext, data: dict) -> dict:
    return {"feeds": ctx.inputs.resolve_feed_set(data["feed_set"])}


@mcp_operation("download_feeds")
def op_download_feeds(ctx: McpContext, data: dict) -> dict:
    return {"responses": ctx.network.fetch_many(data["feeds"])}


@mcp_operation("parse_feeds")
def op_parse_feeds(ctx: McpContext, data: dict) -> dict:
    return {"candidates": parse_rss_or_atom(data["responses"])}


OPERATIONS = {
    "resolve_feeds": op_resolve_feeds,
    "download_feeds": op_download_feeds,
    "parse_feeds": op_parse_feeds
}


def run(ctx: McpContext, inputs: dict) -> dict:
    return ctx.run_declared_graph(MCP_NODE, OPERATIONS, inputs)
```

`MCP_NODE`、operation id、edges、fallbacks 和 schema 必须是静态字面量。operation 函数名称必须为 `op_<operation_id>`。`run()` 只能调用 `ctx.run_declared_graph(...)`，不得包含业务分支、循环、网络、文件、subprocess 或 fallback。

## 8. 静态源码模型

Base parser 必须输出：

```json
{
  "schema": "cartridgeflow.mcp_source_model.v1",
  "node_id": "fetch_news",
  "tool_identity": "media/fetch_rss",
  "format": "cartridgeflow.mcp_python.v1",
  "source": {
    "path": "dlc/mcp_nodes/fetch_news.py",
    "sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
    "line_count": 210
  },
  "operations": [],
  "edges": [],
  "data_relations": [],
  "fallbacks": [],
  "capabilities": [],
  "source_map": {},
  "findings": [],
  "source_digest": "sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
}
```

`source_map` 必须把 operation、edge、schema、fallback 和 capability 定位到文件、symbol、开始行和结束行。前端点击内部节点时只能消费该映射，不得全文搜索或猜测。

## 9. 静态检查与拒绝规则

解析器属于 Base 后端。它使用 `ast.parse` 和可保留格式的 CST 工具进行静态解析，不得 import DLC 模块。

至少检查：

- 一个文件只有一个 `MCP_NODE`。
- node id、server/tool 与 Root Flow、Manifest 和 descriptor 一致。
- `MCP_NODE.operations`、`@mcp_operation` 与 `OPERATIONS` 一一闭合。
- 每个 operation 输入均由边界输入或上游输出提供。
- fallback 显式声明，不形成隐藏控制路径。
- `run()` 是标准 graph runner 调用。
- 禁止 `eval`、`exec`、动态 import、monkey patch 和运行时注册工具。
- 禁止直接使用 `urllib`、`requests`、socket、`open`、任意 `Path` 写入和 `subprocess` 执行受控能力。
- 允许的纯计算 import、SDK import 和已声明 `dlc/lib` 依赖必须可追踪。
- 源码 hash、descriptor hash 和分析 digest 必须一致。
- 无法解释的控制流标记为 `MCP_SOURCE_OPAQUE_CONTROL_FLOW`。

静态解析器不是安全沙箱。它负责格式、证据和 authoring；运行时安全仍由 broker、Worker 隔离和操作系统策略负责。

## 10. 结构化编辑

前端不得拼接 Python 字符串来修改 operation graph。修改流程：

1. 前端提交结构化 authoring operation。
2. 请求携带当前 `source_digest`。
3. 后端验证 revision、权限和 graph 合法性。
4. CST 重写器只修改 `MCP_NODE`、operation stub 或允许的 decorator 区域。
5. 修改后重新 parse、analyze 和计算 hash。
6. 任一环节失败则原文件保持不变。

第一阶段只支持修改 operation 元数据、连线、schema、fallback 和生成新 operation stub。函数体自由编辑由源码编辑器完成，保存后必须重新解析。

## 11. Analyzer 与资源目录

Flow Analyzer 必须把 source model 纳入 source digest。operation graph 形成独立 `tool_internal` scope，不能污染 Root Flow 的可执行控制边。工程关系新增：

```text
tool_operation
capability_dependency
source_implementation
fallback_route
observed_operation
```

统一资源目录升级为：

```text
cartridgeflow.flow_resource_catalog.v2
```

目录项必须增加透明度、入口文件、operation 数量、source digest、parse status 和 broker capabilities。declared graph 与 observed trace 不一致时必须生成稳定 finding。

## 12. 运行时与能力 Broker

Worker 协议从单次输入输出升级为 operation event 流。Worker 只加载当前节点对应文件，不导入整张卡带的通用 dispatcher。

DLC 代码访问受控能力时必须通过：

```text
ctx.network
ctx.artifacts
ctx.process
ctx.secrets
ctx.files
```

broker 在调用前检查 node、operation、permission、effect、参数、目标和 run scope。operation 超时、取消和崩溃必须定位到 operation id，而不仅是外层 MCP node。

## 13. 运行事件

v0.9 新增工具阶段事件：

```text
tool_call_started
tool_operation_started
tool_operation_progress
resource_access_requested
resource_access_completed
fallback_selected
artifact_created
tool_operation_completed
tool_operation_failed
tool_call_completed
```

事件必须携带 `run_id`、`node_id`、`tool_call_id`、`operation_id`、`attempt`、`effect`、时间、输入输出摘要、source digest 和 error identity。敏感值只保存脱敏摘要。

## 14. 前端画布表达

MCP 节点折叠状态必须显示 source、server/tool、版本、owner、transparency、effect、permission、timeout、operation 数量、parse 状态、digest 状态和运行健康状态。

展开状态必须使用明确 MCP 边界容器。Root Flow 连线只连接外层边界端口；内部 operation 使用独立小节点和端口。数据流、控制流、资源依赖、fallback 和失败路径使用不同线型。展开或折叠只改变视图，不改变执行语义。

`opaque` 和 `legacy_opaque` 只能显示黑盒边界、已知契约和不可观测原因，禁止生成推测节点。

## 15. 检查器与源码定位

检查器至少包含：

- `契约`：输入输出、effect、permission、timeout、retry。
- `内部流程`：operation graph、数据映射、fallback。
- `运行轨迹`：declared 与 observed 对比、attempt、进度和错误。
- `源码`：当前 operation 对应源码范围和 digest。
- `安全`：broker capability、资源目标、网络域、子进程和 findings。

点击 operation 必须联动 source map、当前运行事件和数据摘要。长参数、输出和错误使用展开查看，不得堆满节点卡片。

## 16. 兼容性与认证门禁

发布和运行前必须验证：

- Root Flow node、Manifest tool、descriptor tool 和 Python `MCP_NODE` 身份一致。
- source model 不含 blocker。
- graph source digest 未过期。
- 声明 effect 不低于所有 operation 的最大 effect。
- 每个受控能力都有 permission 和 broker capability。
- fallback、retry、compensation 和 replay policy 没有隐藏路径。
- v0.9 compound tool 不得是 `legacy_opaque`。

`legacy_opaque` 可以在兼容模式运行，但不能取得 v0.9 透明认证。

## 17. dev.ai-tech-daily 迁移要求

`dev.ai-tech-daily` 不得继续用多工具 `dlc/backend/entry.py` dispatcher 取得 v0.9 认证。目标结构：

```text
dlc/mcp_nodes/fetch_news.py
dlc/mcp_nodes/voice_storyboard.py
dlc/mcp_nodes/assemble_video.py
dlc/lib/
```

`fetch_news` 必须显式展示 feed 解析、下载、清洗、去重、排序、限制和 RSS 空结果失败出口。`voice_storyboard` 必须显式展示编辑稿校验、口播策略、语音合成、换音色 fallback、分镜渲染和媒体工程写入。`assemble_video` 必须显式展示音频探测、时长策略、字幕、编码、视频探测、质量门禁和交付 Artifact。

## 18. API 要求

Lite 白名单应新增：

```text
GET   /api/lab/flows/{flow_id}/mcp-nodes/{node_id}/source-model
GET   /api/lab/flows/{flow_id}/mcp-nodes/{node_id}/source
PATCH /api/lab/flows/{flow_id}/mcp-nodes/{node_id}/operation-graph
POST  /api/lab/flows/{flow_id}/mcp-nodes/{node_id}/operations
GET   /api/runs/{run_id}/tool-calls/{tool_call_id}/trace
```

源码接口只允许读取 descriptor 已声明、hash 匹配且位于当前卡带包内的文件。PATCH 必须携带 expected source digest，冲突返回 409。

## 19. 测试计划

Parser 测试必须覆盖静态提取、拒绝动态声明、不 import DLC、source map 行号、digest 稳定、直接能力调用检测和 CST 修改原子性。

协议与后端测试必须覆盖身份不一致、`legacy_opaque` 兼容但不可认证、缺失 graph/fallback/broker capability、source digest 过期、未声明网络/文件/subprocess 调用、stage event 与 operation 关联。

前端 E2E 必须覆盖折叠/展开不改变外层布局、内部图与 source model 一致、operation 定位源码和运行事件、结构化编辑冲突、fallback 高亮、opaque 黑盒展示、100%/125% 缩放和窄屏无溢出。

## 20. 完成标准

v0.9 MCP 透明执行只有同时满足以下条件才算落地：

- 每个开发卡带 MCP 节点都有唯一 Python 入口文件。
- Base 不再依赖多工具大型 dispatcher 作为透明工具。
- 所有 composite 工具均可在画布展开真实 operation graph。
- 展开图、source model 和 stage trace 使用同一 operation identity。
- 用户可以看到每个 fallback、资源访问、子进程、Artifact 和失败位置。
- graph 修改真实改变执行契约。
- 未声明能力或隐藏业务控制流阻止 v0.9 发布认证。
- 远程 opaque MCP 被诚实标记。
- v0.8 历史协议、既有卡带和资源目录语义保持兼容。
- 完整 conformance、前端构建、Parser 测试和 Playwright E2E 全部通过。

## 21. 禁止事项

- 不得把每一行 Python 自动伪装成流程节点。
- 不得还原任意第三方动态 Python、闭包、反射或 monkey patch。
- 不得要求远程 MCP 服务公开商业源码；无法公开时必须标为黑盒。
- 不得让前端 import、解释或执行 Python。
- 不得把特定 RSS、视频、媒体或其他业务逻辑写入 Base。
- 不得用函数名、注释或自然语言生成推测内部图。
- 不得将 v0.8 卡带静默标记为 v0.9。

## 22. 定稿前治理决策

以下决策必须在实现完整认证前形成明确结论：

1. `source format v1` 只支持 Python，还是同时预留 TypeScript。
2. 结构化编辑是否允许自动生成 operation 函数 stub。
3. 远程 MCP 的 `contract_only` 认证是否限制为 `none/read_only` 原子工具。
4. DLC Worker 的 OS sandbox 在 Windows、macOS 和 Linux 上分别采用什么实现。
5. 行数门禁采用固定阈值、复杂度阈值还是组合策略。
6. operation graph 布局保存到卡带 authoring metadata，还是用户本地视图状态。
7. graph 与源码不一致时，开发运行完全阻止，还是允许一次明确风险诊断运行。
