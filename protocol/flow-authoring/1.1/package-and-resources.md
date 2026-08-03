# CF-FARP@1.1 - Package and resources

This file is a normative module of CF-FARP@1.1. The release is defined only by the same-version modules listed in README and CARTRIDGEFLOW-BASE@0.3.

## 5. 卡带包结构

最小包：

```text
cartridge/
  manifest.json
  root.flow.json
  assets/
    registry.json
```

完整包 MAY 包含：

```text
cartridge/
  manifest.json
  root.flow.json
  assets/
    registry.json
    components.json
    prompts/
    schemas/
    ui/
    motion/
    media/
    fixtures/
  tests/
  dlc/
    descriptor.json
    backend/
    frontend/
      components/
    protocols/
    workflows/
    tests/
```

卡带不得要求复制文件到 Base 源码、全局前端、全局协议或全局配置目录后才能运行。

包结构规则：

1. 所有包内路径 MUST 使用相对路径，并在规范化后仍位于卡带根目录。
2. `..` 路径穿越、绝对路径、驱动器路径和指向包外的符号链接 MUST 被拒绝。
3. 卡带不得依赖包外未声明资源；外部依赖必须在 Manifest 中声明角色、权限、失败策略和预检方式。
4. 运行产物默认写入 run-scoped 目录；跨 Run 持久状态必须单独声明 ownership 与 permission。
5. `dlc/` 中的代码、协议、UI、workflow 和私有资源必须随卡带目录整体移动。
6. discovery 阶段 MAY 读取 Manifest、descriptor 和 hash，但 MUST NOT 导入代码、联网、启动进程或产生业务文件。
7. 安装与升级 MUST 先在临时目录完成校验，再通过原子替换或可恢复事务进入正式目录。
8. 普通 `assets/` MUST NOT 包含可执行 JavaScript、WebAssembly、浏览器 Worker、可执行表达式或能触发脚本的主动文档内容。
9. 卡带脚本只能位于 descriptor 声明并逐文件校验的 `dlc/frontend/` 或 `dlc/backend/` 作用域；把脚本改名为图片、HTML、模板或数据文件不改变其可执行身份。
10. Base 必须按解析后的媒体类型、文件内容和使用方式判定主动内容，不能只相信扩展名或 Manifest 标签。

## 6. Manifest 契约

最小 v1.1 Manifest：

```json
{
  "schema_version": "1.0",
  "id": "example.workflow",
  "name": "Example Workflow",
  "version": "1.0.0",
  "kind": "runtime_cartridge",
  "category": "workflow",
  "root_flow": {
    "entry": "root.flow.json",
    "mode": "lifecycle",
    "required": true
  },
  "runtime": {
    "type": "lab",
    "adapter": "builtin:lab"
  },
  "base_contract": {
    "id": "CARTRIDGEFLOW-BASE",
    "version": "0.3"
  },
  "runtime_contract": {
    "protocol": "CF-FARP",
    "protocol_version": "1.1",
    "required_profiles": ["runtime_core", "flow_analysis", "tool_transparency", "execution_plan_runtime", "tuning_authoring", "recipe_release_runtime"],
    "recommended_profiles": [],
    "required_capabilities": [
      "root_flow_execution",
      "structured_io_contract",
      "explicit_input_binding",
      "execution_plan_runtime",
      "execution_plan_v1_authoring",
      "execution_plan_static_conformance",
      "execution_plan_compile",
      "flow_analysis_report_v1",
      "analysis_report_freshness_guard",
      "trusted_subprotocol_registry",
      "tuning_repository_v1",
      "recipe_release_snapshot_v1",
      "tuning_materialize",
      "run_recipe_provenance"
    ],
    "optional_capabilities": [],
    "required_tools": [],
    "optional_tools": []
  },
  "tuning_contract": {
    "protocol": "CF-TUNING",
    "protocol_version": "1.0",
    "adapter": "cf-tuning.repository.v1",
    "release_entry": "tuning/release.json",
    "required_for": ["production", "package", "publish"]
  },
  "delivery_readiness": {
    "level": "dev",
    "runnable": true
  },
  "asset_registry": "assets/registry.json",
  "inputs": [],
  "outputs": [],
  "mcp_tools": []
}
```

规则：

1. `id` 与 `version` MUST 稳定。
2. `base_contract` MUST 指向 `CARTRIDGEFLOW-BASE@0.3` 或 Base 明确支持的后续兼容版本。
3. `runtime_contract` MUST 指向 `CF-FARP@1.1`。
4. `base_contract` 和 `runtime_contract` 是不同契约，版本不得要求相等。
5. `required_*` 缺失必须阻断；`optional_*` 缺失形成可见降级。
6. Manifest MUST 声明 `asset_registry`；没有资产时 registry 仍可为空数组。
7. 使用 interaction 节点时 Manifest MUST 声明 `interaction_components`。
8. Manifest MAY 包含 `publisher`、`branding`、`permissions`、`dependencies`、`environment`、`llm_recipe`、`resource_requirements`、`artifacts`、`delivery`、`protocol_extensions` 和 `portable_dlc`。
9. v1.1 卡带 MUST 要求 `flow_analysis`、`execution_plan_runtime`、`tuning_authoring` 与 `recipe_release_runtime` profiles，以及执行计划、分析和调优发布最低能力；缺失时不得以 v1.1 运行或认证。
10. Manifest MUST 声明精确的 `CF-TUNING@1.0` tuning contract。开发仓库不得打包；`tuning/release.json` 只包含活动发布快照，production/package/publish 缺失时必须阻断。

### 6.1 字段分组

| 分组 | 必需字段 | 作用 |
|---|---|---|
| 身份 | `schema_version`、`id`、`name`、`version`、`kind`、`category` | 标识可分发卡带 |
| 入口 | `root_flow`、`runtime` | 定位 Root Flow 与运行适配器 |
| 契约 | `base_contract`、`runtime_contract` | 声明宿主与 Flow 协议要求 |
| 交付 | `delivery_readiness`、`inputs`、`outputs` | 声明运行阶段与公开 I/O |
| 能力 | `mcp_tools`、可选 `llm_recipe`、`resource_requirements` | 声明模型、工具和本机资源角色 |
| 卡带内容 | `asset_registry`、使用交互时的 `interaction_components` | 声明资产身份、完整性和交互界面契约 |
| 风险 | 可选 `permissions`、`dependencies`、`environment` | 声明权限与外部条件 |
| 扩展 | 可选 `protocol_extensions`、`portable_dlc` | 声明卡带拥有的扩展 |
| 产物 | 可选 `artifacts`、`delivery` | 声明产物策略和主要交付 |

### 6.2 身份与入口

1. `id` MUST 在发布者作用域内稳定且唯一，升级不得静默更换 ID。
2. `version` SHOULD 使用可比较版本格式；升级与回滚必须保留原版本身份。
3. `root_flow.entry` MUST 指向存在的包内 JSON 文件。
4. `root_flow.mode` 在本版本 SHOULD 为 `lifecycle`；其他模式必须由 capability 明确声明。
5. `runtime.adapter` 是 Base 运行适配器身份，不得作为携带本机密钥或供应商 workflow 的入口。
6. `publisher` 和签名信息如果存在，必须与包校验和绑定，不能只作为显示文本。

### 6.3 Runtime Contract

`runtime_contract` 的数组字段语义如下：

- `required_profiles`：缺失任一项即 blocker。
- `recommended_profiles`：缺失形成 warning，并显示受影响体验。
- `required_capabilities`：缺失任一项即 blocker。
- `optional_capabilities`：缺失形成 info 或显式降级。
- `required_tools`：必须能解析到启用的 Manifest tool。
- `optional_tools`：不可用时不得静默替换成语义不同的工具。

每个条目 MUST 是稳定字符串 ID 或带 `id` 的结构化声明。Base 不得通过相似名称、UI 标签或猜测映射 required 身份。

### 6.4 输入与输出注册表

Manifest `inputs` 与 `outputs` 是公开 schema 注册表，不等同于唯一输入节点或唯一交付节点。

```json
{
  "inputs": [
    {
      "id": "request",
      "label": "请求",
      "type": "object",
      "required": true,
      "schema_ref": "asset:schema.request"
    }
  ],
  "outputs": [
    {
      "id": "final_report",
      "label": "最终报告",
      "type": "document",
      "required": true
    }
  ]
}
```

输入可以在流程中多次收集。每次追加输入必须记录来源、interaction 或外部事件身份、目标 Store key 和 revision。不得用 Manifest 注册表暗示运行时可以任意覆盖已有 Store 数据。

### 6.5 权限、依赖与环境

1. `permissions` MUST 描述真实文件、网络、进程、外部写入和敏感数据范围。
2. 权限等级 MUST 可由 UI 展示，不得把危险权限包装成普通说明。
3. `dependencies` MUST 区分 required/optional、package/shared/user-managed 和安装策略。
4. 发现阶段不得因为 dependency 声明自动下载、安装、升级或启动外部程序。
5. `environment` MAY 声明 OS、command、app_config、硬件或网络条件，但不得携带本机凭据值。
6. required dependency 或 environment 条件缺失时必须在业务执行前失败关闭。

### 6.6 协议扩展与 DLC

`protocol_extensions` 只声明卡带显式选择的伴随协议。每项至少包含 `id`、`version`，并可声明 `extends`、required/optional profiles 与 capabilities。扩展必须通过当前卡带 Overlay 解析，不能从其他已安装卡带偷取实现。

存在 `portable_dlc` 时，其 protocol MUST 与 Runtime Contract 完全一致，descriptor MUST 位于包内，并在任何后端或前端激活之前完成完整性校验。

### 6.7 卡带资产 Registry

`asset_registry` 指向包内 JSON 文件。标准结构：

```json
{
  "schema": "cartridgeflow.asset_registry.v1",
  "assets": [
    {
      "id": "ui.review_shell",
      "kind": "interaction_template",
      "path": "assets/ui/review.html",
      "media_type": "text/html",
      "sha256": "...",
      "size": 18420,
      "executable": false
    },
    {
      "id": "prompt.writer",
      "kind": "prompt",
      "path": "assets/prompts/writer.md",
      "media_type": "text/markdown",
      "sha256": "...",
      "size": 3260,
      "executable": false
    }
  ]
}
```

基础 `kind` 词表：

```text
flow model_recipe prompt schema motion_template
interaction_template style media fixture
```

规则：

1. `id` 在卡带版本内 MUST 唯一、稳定且与物理路径解耦；公开引用使用 `asset:<id>`。
2. `path` MUST 是包内相对路径，文件必须存在并匹配 `sha256` 与 `size`。
3. `media_type` 必须由 Base 结合内容检测验证，不能只相信作者声明或扩展名。
4. v1.1 registry 中 `executable` MUST 为 `false`。脚本、WebAssembly、Worker 和其他可执行内容不得作为普通资产注册。
5. Root Flow、模型配方、prompt、schema、动效模板、UI 模板和媒体可以作为卡带内容参与搭建，但 Root Flow 入口仍由 Manifest 单独声明。
6. `flow`、`model_recipe`、`prompt` 和其他声明性资产只能交给对应的结构化解析器；`executable=false` 禁止 Base 对其执行 eval、import、模板表达式代码或操作系统命令。
7. 节点 SHOULD 使用稳定资产引用；兼容导入器 MAY 读取旧相对路径，但必须在保存 v1.1 Flow 前迁移为 asset ID。
8. 删除或更换 asset ID 前必须检查 Root Flow、组件、配方、测试和其他资产的反向引用。悬空 required 引用是 blocker。
9. 运行期间生成的文件属于 Artifact 或 private data，不得回写进只读资产 Registry 冒充包资产。
10. `motion_template` 和 `style` 资产只能是声明性数据。需要执行 JavaScript、Python、表达式引擎或供应商插件代码的动效/渲染模板必须归入相应 DLC backend/frontend，并遵守工具或脚本执行边界。

### 6.8 Interaction Component Registry

`interaction_components` 指向包内 JSON 文件。标准结构：

```json
{
  "schema": "cartridgeflow.interaction_components.v1",
  "components": [
    {
      "id": "review.result",
      "version": "1.0.0",
      "runtime": "passive",
      "entry": {"type": "asset", "ref": "asset:ui.review_shell"},
      "supported_modes": ["display", "collect", "review"],
      "input_schema": "asset:schema.review_input",
      "actions": [
        {"id": "approve", "label": "通过", "payload_schema": "asset:schema.empty"},
        {"id": "revise", "label": "退回修改", "payload_schema": "asset:schema.revision_feedback"},
        {"id": "cancel", "label": "取消", "payload_schema": "asset:schema.empty"}
      ],
      "host_capabilities": []
    },
    {
      "id": "editor.storyboard",
      "version": "1.0.0",
      "runtime": "sandboxed",
      "entry": {"type": "dlc_frontend", "ref": "storyboard_editor"},
      "supported_modes": ["collect", "review"],
      "input_schema": "asset:schema.storyboard_input",
      "actions": [
        {"id": "approve", "label": "通过", "payload_schema": "asset:schema.storyboard_answer"},
        {"id": "revise", "label": "退回修改", "payload_schema": "asset:schema.revision_feedback"},
        {"id": "cancel", "label": "取消", "payload_schema": "asset:schema.empty"}
      ],
      "host_capabilities": ["artifact.read", "draft.write", "interaction.propose"]
    }
  ]
}
```

上例为组件结构节选；其中所有 `asset:schema.*` 引用在真实卡带中都必须作为 `kind=schema` 条目存在于同一 Asset Registry，否则 discovery 失败。

规则：

1. component `id` 与 `version` 在卡带版本内 MUST 唯一稳定，交互节点使用 `component_ref` 引用该 ID，Pending Interaction 固化实际版本与 entry hash。
2. `runtime=passive` 的 entry MUST 引用 `interaction_template` 资产，并满足 6.9 的无脚本规则。
3. `runtime=sandboxed` 的 entry MUST 引用当前卡带 Portable DLC descriptor 中声明的 frontend component；缺少 descriptor、hash 或 capability 时失败关闭。
4. `supported_modes` 只允许 `display | collect | review`。组件不能自行发明改变 Runner 生命周期的模式。
5. `actions` 必须静态枚举稳定 ID、Host 显示 label 与 payload schema。label 是作为纯文本转义呈现的显示值，可以本地化或修改，不参与路由身份，不能包含可执行标记。
6. `host_capabilities` 使用最小授权；未声明能力必须拒绝。组件不得直接声明 URL、key、本机路径、任意网络域或任意 Flow target。
7. 组件 registry 只描述界面契约，不执行代码。发现阶段不得加载 entry、创建 iframe 或运行脚本。
8. passive component 只负责内容与视觉。用于 collect/review 时，Base 必须根据 input/action schema 在 iframe 外生成 Host-owned fields 和 action controls；不得尝试读取无同源 iframe DOM。
9. sandboxed component MAY 在 iframe 内提供复杂编辑控件并通过 `draft.write` 更新草稿，但最终 action control 仍由 Host 拥有。

### 6.9 被动 HTML 与样式安全

`runtime=passive` 的 HTML 是模板资产，不是应用代码。Base MUST 使用 HTML/CSS 解析器检查实际文档结构，禁止仅用正则表达式或文件扩展名判断安全性。

被动 HTML MUST NOT 包含：

- `script`、`iframe`、`object`、`embed`、`applet`、`portal`、`base`、主动 `meta refresh`。
- 任意 `on*` 事件属性、`javascript:` URL、可执行 `data:` 文档、内联模块或动态 import。
- `form`、`input`、`button`、`select`、`textarea`、带 `href` 的 `a/area` 等可提交或导航控件，以及自动提交、任意 frame 导航、弹窗、下载触发或外部网络连接。passive collect/review 的控件由 Host 从 schema 生成。
- 可执行 SVG、`foreignObject`、SMIL 事件、WebAssembly、Worker、Service Worker 或浏览器扩展入口。
- CSS `@import`、外部 URL、脚本表达式或可突破卡带资源作用域的引用。

被动模板必须在等价于下列最小策略的隔离域中呈现：

```text
default-src 'none'; script-src 'none'; connect-src 'none';
img-src 'self' data: blob:; style-src 'self' 'unsafe-inline';
font-src 'self'; object-src 'none'; frame-src 'none';
worker-src 'none'; form-action 'none'; base-uri 'none';
```

包内图片、字体和样式只能通过校验 cartridge、component、asset ID、规范化路径和 hash 的受控 URL 加载。发现主动内容、媒体类型欺骗或无法可靠解析的文档时，Base MUST 返回稳定安全错误并拒绝预览、运行和打包；不得“清理后继续”而不生成新的资产 revision 与 hash。

## 7. 模型配方

卡带 MAY 声明模型角色：

```json
{
  "llm_recipe": {
    "schema": "cartridgeflow.llm_recipe.v1",
    "roles": [
      {
        "id": "planning_model",
        "label": "规划模型",
        "capability": "text.reasoning",
        "api_type": "openai_compatible",
        "wire_api": "responses",
        "model": "configured-locally",
        "required": true
      }
    ]
  }
}
```

卡带也 MAY 通过 `model_recipe` 资产引用同一结构：

```json
{
  "llm_recipe": {
    "asset_ref": "asset:model_recipe.primary"
  }
}
```

inline 配方与 `asset_ref` 只能选择一种。Base 必须在 discovery 阶段解析 asset ID、校验 kind/hash/schema 后得到同一规范化配方；不得把资产显示名称当作本机 Provider 绑定键。

配方 MUST NOT 包含：

- URL 或 endpoint。
- API key、token、Authorization 或私有 header。
- 本机绝对路径。
- 只属于开发者机器的 Provider ID。

Base MUST 通过本机 assignment 将角色连接到 Provider。缺少 required 角色绑定时返回 `PROVIDER_CONFIGURATION_MISSING` 或等价稳定错误。

### 7.1 模型角色字段

| 字段 | 要求 | 语义 |
|---|---|---|
| `id` | MUST | 卡带内稳定角色 ID |
| `label` | MUST | 开发者可读名称，不参与自动猜测 |
| `capability` | MUST | 例如 text.reasoning、vision.analysis、image.generation |
| `api_type` | MUST | 期望的兼容 API 类型 |
| `wire_api` | MUST | 消息 wire contract，例如 responses 或 chat_completions |
| `model` | MUST | 固定模型标识或 `configured-locally` |
| `required` | SHOULD | 是否阻断真实运行 |
| `constraints` | MAY | 上下文、模态、结构化输出或质量约束 |

角色 ID 是卡带与本机 assignment 的连接点。显示名称相同不构成绑定；Base MAY 提供人工拖拽或显式映射，但不得依据厂商名和模糊相似度静默选择 Provider。

### 7.2 绑定与预检

Base 在运行前 MUST：

1. 解析每个 required 模型角色。
2. 检查本机 Provider 是否存在、启用且具有凭据。
3. 检查 api_type、wire_api、模型和模态能力是否满足。
4. 返回不包含密钥的绑定摘要。
5. required 角色不满足时在调用模型前阻断。

预检成功只证明配置可用，不证明外部模型质量、余额、配额或服务稳定性。需要网络探测时必须明确标记为外部调用，并遵守 timeout 与凭据脱敏。

### 7.3 Live、Mock 与 Offline

运行模式至少区分：

- `live`：调用真实本机 Provider。
- `mock_resolved`：固定 resolved envelope。
- `mock_interaction`：固定 needs_user_input envelope。
- `mock_blocked`：固定 blocked envelope。
- `offline_fallback`：明确声明的本地替代路径。

事件和 Run snapshot MUST 记录 role id、脱敏 Provider identity、model、wire_api、used_llm、execution_mode、fallback 和 fallback_reason。mock 或 fallback 不得获得 live 结果标记。

## 8. 工具配方与资源角色

工具声明描述“调用什么契约”，本机资源描述“连接哪个实例”。

远程知识库、搜索索引、数据库查询服务和内容仓库只要通过网络或本机进程提供能力，就属于本节的 MCP、remote API 或其他声明工具。v1.1 不定义独立的全局 Data Source 绑定；需要随卡带携带的静态知识内容应作为 package asset，需要运行时查询的外部内容必须经过工具契约、权限、超时和审计。

```json
{
  "resource_requirements": [
    {
      "role": "document_lookup",
      "kinds": ["mcp", "remote_api"],
      "required": true
    }
  ],
  "mcp_tools": [
    {
      "id": "lookup_documents",
      "type": "mcp",
      "server": "document_tools",
      "tool": "search",
      "resource_role": "document_lookup",
      "enabled": true,
      "required": true,
      "contract": {
        "capability": "remote_tool_call",
        "idempotent": true,
        "side_effect": "read_only",
        "timeout_ms": 30000,
        "retry_policy": {
          "max_attempts": 2,
          "initial_delay_seconds": 0.5,
          "max_delay_seconds": 2,
          "total_timeout_seconds": 45
        }
      },
      "params_schema": {
        "type": "object"
      }
    }
  ]
}
```

规则：

1. 卡带只保存 `resource_role`、tool ID、schema 和行为契约。
2. URL、key、command secret 和认证值 MUST NOT 存入 Manifest 或 Root Flow。
3. Base 在运行前解析本机绑定并做 preflight。
4. 供应商 workflow、上传协议、轮询逻辑和返回解析必须由卡带 DLC 或外部适配包拥有。
5. required resource 未绑定时不得执行调用节点。

### 8.1 Resource Requirement

资源需求结构：

```json
{
  "role": "document_lookup",
  "kinds": ["mcp", "remote_api"],
  "required": true,
  "capabilities": ["search"],
  "constraints": {
    "read_only": true
  }
}
```

规则：

1. `role` MUST 在卡带内稳定唯一。
2. `kinds` MUST 是卡带可接受的本机资源类型集合。
3. `capabilities` 与 `constraints` 描述行为要求，不得嵌入供应商连接细节。
4. required role 没有匹配项时是 blocker；optional role 没有匹配项时必须显示降级。
5. 一个本机资源 MAY 被多张卡带绑定，但卡带之间不得看到彼此的私有 binding 数据。

### 8.2 Manifest Tool Contract

每个工具声明至少包含：

| 字段 | 要求 |
|---|---|
| `id` | 卡带内稳定 tool ID |
| `type` | builtin、mcp、remote 或 plugin 身份 |
| `server` / `tool` | 作用域内调用身份 |
| `resource_role` | 外部资源调用时必需 |
| `enabled` | 是否参与当前卡带工具表 |
| `required` | 缺失时是否阻断 |
| `contract.capability` | 行为能力 |
| `contract.side_effect` | 副作用分类 |
| `contract.idempotent` | 是否可安全重复 |
| `contract.timeout_ms` | 单次有界超时 |
| `contract.retry_policy` | 最大次数、退避和总超时 |
| `params_schema` | 输入参数 schema |
| `result_schema` | 可选结果 schema |

`enabled=true` 不代表自动授予权限；节点仍必须通过 allowed_tools、effect、permission 与当前 binding 校验。

### 8.3 本机 Binding Descriptor

本机 binding MAY 使用以下公开摘要：

```json
{
  "schema": "cartridgeflow.local_bindings.v1",
  "cartridge_id": "example.workflow",
  "roles": {
    "document_lookup": {
      "resource_id": "local.docs.search",
      "kind": "remote_api",
      "ready": true,
      "credential_state": "configured"
    }
  }
}
```

公开摘要不得包含 URL、command、key、token、Authorization、私有 header 或本机绝对路径。真实连接只在 Base 本机配置域解析。

### 8.4 Resource Preflight

预检结果 MUST 区分：

- `ready`：绑定存在且静态条件满足。
- `missing_binding`：没有本机资源映射。
- `missing_credential`：资源存在但凭据缺失。
- `incompatible_kind`：资源类型不在可接受集合。
- `capability_mismatch`：能力或副作用约束不满足。
- `external_unverified`：未做真实连通性验证。

预检不得通过选择“任何可用资源”自动绕过角色约束。

## 9. Delivery Readiness

合法 level：

- `dev`：开发中，不得作为普通用户正式交付。
- `preview`：可演示，但必须显示限制与 fallback。
- `production`：可在满足要求的生产 Base 直接运行。

`production` 卡带 MUST：

- 不依赖设计台、探针 seeded 数据或未打包文件。
- 不携带本机配置和秘密。
- 有明确 primary output。
- 对持久写入、外部副作用和用户 Artifact 有所有权声明。
- 通过兼容性、完整性和交付预检。

补充规则：

1. `runnable=true` 不能覆盖协议 blocker，只表示作者期望该阶段可运行。
2. `dev` 运行 MAY 使用设计台、mock 和探针，但结果必须带开发标记。
3. `preview` 运行 MUST 展示已知限制、外部未验证项与 fallback。
4. `production` 不得要求用户打开 Flow 编辑器修复输入或配置。
5. certification target 与真实 Runtime Contract 不一致时必须阻断认证。
6. 从 preview 提升到 production 必须生成新的预检和认证证据，不能只修改 level 文本。
