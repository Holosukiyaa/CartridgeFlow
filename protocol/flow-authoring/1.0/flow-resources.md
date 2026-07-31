# CF-FARP@1.0 - Flow resource catalog

This file is a normative module of CF-FARP@1.0. The release is defined only by the same-version modules listed in README and CARTRIDGEFLOW-BASE@0.2.

## 50. 统一 Flow 资源目录

v1.0 Base MUST 为每个 Flow 生成唯一的只读资源解析结果 `cartridgeflow.flow_resource_catalog.v1`。工具管理、模型管理、Analyzer、运行预检、Runner snapshot 和打包预检 MUST 消费同一目录，不得分别从本机配置、Manifest 或节点字段自行拼接另一套事实。

目录构建 MUST 同时读取以下六层事实：

1. Base 内置工具注册表。
2. 本机 MCP、API 与插件资源注册表。
3. 当前卡带已校验的 Portable DLC descriptor。
4. Manifest 的工具和模型需求声明。
5. 当前 Flow 的本机资源与模型连接绑定。
6. Root Flow 具体节点的工具引用与模型连接绑定。

每个工具目录项 MUST 包含稳定 `id`、真实 `resource_id`、`source`、owner、server/tool、availability、Manifest requirement、Flow binding、node references 和 status。`source` 只能是：

```text
base_builtin
local_resource
cartridge_dlc
```

`base_builtin` 表示实现与生命周期属于 Base；`local_resource` 表示连接配置和秘密属于当前机器；`cartridge_dlc` 表示实现与生命周期属于当前卡带包。Portable DLC 工具即使通过 Base 的隔离 worker 执行，也 MUST 标记为 `cartridge_dlc`，不得投影或展示为 `builtin:<server>/<tool>`。Manifest requirement 只声明需求，不等于资源已经存在或已绑定。

目录至少返回：

```json
{
  "schema": "cartridgeflow.flow_resource_catalog.v1",
  "cartridge_id": "example.flow",
  "tools": [
    {
      "id": "fetch_news",
      "resource_id": "dlc:news.media:media/fetch_rss",
      "source": "cartridge_dlc",
      "owner": "news.media",
      "manifest_requirement": {"declared": true, "required": true},
      "flow_binding": {"bound": true, "status": "bound"},
      "node_references": ["fetch_news"],
      "status": "ready"
    }
  ],
  "models": {},
  "findings": [],
  "summary": {"tools": 1, "ready": 1, "referenced": 1, "blockers": 0}
}
```

被节点引用但未在 Manifest 声明的工具 MUST 产生 `NODE_TOOL_NOT_DECLARED` blocker。Manifest required tool 没有可用来源时 MUST 产生 `TOOL_RESOURCE_UNRESOLVED` blocker。被节点引用的本机资源尚未进入 Flow 时 MUST 产生 `NODE_TOOL_RESOURCE_NOT_BOUND` blocker。Runner MUST 在执行任何业务代码前阻断这些 finding，并把成功解析的目录写入 Run snapshot。

### 50.1 运行模型绑定

模型运行绑定 MUST 遵循两个连续步骤：

```text
本机模型连接进入 Flow
-> 每个 AI Decision 节点从当前 Flow 的连接中明确选择一个连接和模型
```

Manifest `llm_recipe.roles` 声明卡带运行所需的模型角色与能力，不保存本机 Provider，也不代表节点已经完成绑定。仅有 Flow role binding 不能使节点可运行；每个 AI Decision 节点 MUST 存在显式 node binding，且其 Provider MUST 已进入当前 Flow。预检缺失时返回 blocker，Runner 不得继承全局默认连接、不得只按角色静默选择 Provider、不得在节点连接失效时回退到另一连接。

模型 API 缺失、不可用或调用失败时，除非节点存在符合第 26 和 46 节的显式 fallback contract，否则 Run MUST 失败。离线生成结果、全局默认模型或 AI 管家连接不得冒充该节点的真实运行结果。

### 50.2 Authoring 与 Mentor 模型隔离

AI 管家、创作 AI、协议解释器和 mentor 使用的模型属于 Base `authoring` scope。它们 MUST 通过独立的 authoring resource binding 管理，不得自动追加到卡带 `llm_recipe.roles`，不得计入卡带运行模型就绪状态，也不得被 Runner 当作业务节点 fallback。

卡带在 `llm_recipe.roles` 中声明 `authoring` 或 `mentor` 时，Analyzer 或运行预检 MUST 返回 `AUTHORING_MODEL_SCOPE_LEAK` blocker。Authoring 调用的审计记录必须标记 scope、实际 Provider 与 model，但不得把秘密或本机连接配置写回 Manifest、Flow 或可移植包。

---
