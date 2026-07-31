# CF-FARP@1.0 - Extensions and lifecycle

This file is a normative module of CF-FARP@1.0. The release is defined only by the same-version modules listed in README and CARTRIDGEFLOW-BASE@0.2.

## 28. Portable DLC

携带 DLC 的 Manifest：

```json
{
  "portable_dlc": {
    "protocol": "CF-FARP@1.0",
    "descriptor": "dlc/descriptor.json",
    "activation": "manifest_scoped"
  }
}
```

Descriptor 使用 `cartridgeflow.portable_dlc.v2`，至少声明：

- id、version、owner_cartridge 和 scope。
- backend JSON stdio worker entry。
- 可选 sandbox frontend component entries。
- tools、protocols、resources 和 files SHA-256。

发现阶段不得执行代码。工具只进入当前卡带 Registry。后端不得导入主服务进程；前端不得进入主前端脚本域。

### 28.1 Portable DLC 定义

Portable DLC 必须满足：

1. 所有领域实现由一个明确卡带包拥有。
2. 移动卡带目录后，除声明的本机 binding 和外部依赖外，不修改 Base 文件即可验证和运行。
3. 未安装或未激活时，Base 不暴露该 DLC 的工具、协议、UI、workflow 或领域类型。
4. 激活只影响当前 cartridge/run 作用域。
5. 停用和卸载能够让执行能力从运行视图中消失。

Base 可以提供 descriptor 读取、hash 校验、作用域代理、Worker 宿主、前端 sandbox、Protocol Overlay 和生命周期事务，但不得提供只服务单个 DLC 的业务实现。

### 28.2 Descriptor 完整结构

```json
{
  "schema": "cartridgeflow.portable_dlc.v2",
  "id": "dlc.example.workflow",
  "version": "1.0.0",
  "owner_cartridge": "example.workflow",
  "scope": "cartridge",
  "backend": {
    "entry": "dlc/backend/entry.py",
    "transport": "json_stdio_worker"
  },
  "frontend": {
    "sandbox": "isolated_iframe",
    "components": [
      {
        "id": "storyboard_editor",
        "entry": "dlc/frontend/components/storyboard/index.html",
        "context_keys": ["interaction", "input", "artifacts"],
        "host_capabilities": ["artifact.read", "draft.write", "interaction.propose"],
        "script_policy": "external_hashed_only"
      }
    ]
  },
  "tools": [
    {
      "server": "example_tools",
      "tool": "build_output",
      "handler": "backend.entry:build_output",
      "effect": "writes_artifacts",
      "timeout_ms": 120000,
      "description": "Build the declared output.",
      "params": {}
    }
  ],
  "protocols": [
    {
      "id": "EXAMPLE-DOMAIN",
      "version": "1.0",
      "registry": "dlc/protocols/EXAMPLE-DOMAIN-1.0.json"
    }
  ],
  "resources": [
    {"path": "dlc", "ownership": "package"},
    {"path": ".data/cartridge_dlc/example.workflow", "ownership": "private_data"},
    {"path": "user_outputs", "ownership": "user_artifact"}
  ],
  "files": [
    {"path": "dlc/backend/entry.py", "sha256": "..."},
    {
      "path": "dlc/frontend/components/storyboard/index.html",
      "sha256": "...",
      "media_type": "text/html",
      "role": "frontend_entry"
    },
    {
      "path": "dlc/frontend/components/storyboard/app.js",
      "sha256": "...",
      "media_type": "text/javascript",
      "role": "frontend_script"
    },
    {"path": "dlc/protocols/EXAMPLE-DOMAIN-1.0.json", "sha256": "..."}
  ]
}
```

### 28.3 Descriptor 规则

1. schema MUST 为 `cartridgeflow.portable_dlc.v2`。
2. id、version 和 owner_cartridge MUST 稳定，owner MUST 匹配 Manifest。
3. scope 在本版本 MUST 为 cartridge。
4. backend transport MUST 是 Base 声明支持的隔离 transport；本规范标准值为 json_stdio_worker。
5. frontend 如果存在，sandbox MUST 为 isolated_iframe，并声明非空、ID 唯一的 components。
6. 所有路径 MUST 是包内相对路径且防路径穿越。
7. 可执行代码、协议、前端和 workflow 文件 MUST 出现在 files 并匹配 SHA-256。
8. descriptor tools 必须与 Manifest 启用工具集合完全一致，不能多一个或少一个。
9. tools 必须声明 server、tool、handler、effect、timeout 和 description。
10. descriptor 不得包含可执行表达式、凭据或隐式下载指令。
11. 每个 frontend component `id` MUST 与 Interaction Component Registry 的 `dlc_frontend` ref 一一对应；未被 Registry 引用的 entry 不得自动获得运行入口。
12. frontend entry、脚本、模块、样式、字体、图片、source map 和其他可加载文件必须全部出现在 `files`，并声明真实 media type、role 与 SHA-256。
13. `script_policy` 在 v1.0 MUST 为 `external_hashed_only`：禁止 inline script、inline module、`eval`、`new Function`、字符串定时器、动态生成代码、WebAssembly 和未列入 files 的动态 import。
14. frontend component 的 `host_capabilities` MUST 是对应组件 Registry 声明集合的子集或完全相等，冲突时失败关闭。

### 28.4 发现与验证

发现阶段只允许读取静态文件、解析 JSON 和计算 hash，不得：

- 导入 backend 模块。
- 启动 Worker、浏览器或外部应用。
- 执行 frontend 脚本。
- 发起网络请求。
- 下载依赖或生成业务文件。

验证至少检查 schema、owner、scope、路径、文件存在/hash/media type/role、Manifest tool 对齐、权限、依赖、frontend component 对齐、脚本策略、sandbox、protocol identity 和资源 ownership。Base 必须解析每个 frontend entry 及其静态资源引用，确认所有引用均可由 descriptor files 闭包满足。任一 blocker 使 DLC 进入 rejected/quarantined，不得部分激活。

### 28.5 作用域注册

DLC tool 的规范作用域身份：

```text
cartridge_id@cartridge_version/server/tool
```

主 Registry 只保存代理和 descriptor 元数据，不保存或导入领域 handler。代理调用前再次校验 package path、descriptor hash、当前 cartridge/run scope、Manifest allowlist、permission、effect 和 timeout。默认 Registry 与其他卡带 Registry 不得列出该工具。

相同 server/tool MAY 由不同卡带实现，但完整作用域 identity 不得冲突。

## 29. DLC Worker 与前端消息

Worker 请求 MUST 包含 schema、request_id、run_id、cartridge_id、DLC identity、server、tool 和 params。stdout 只返回 JSON 协议消息。

### 29.1 Worker 请求与响应

```json
{
  "schema": "cartridgeflow.dlc_worker_request.v1",
  "request_id": "request_...",
  "run_id": "run_...",
  "cartridge_id": "example.workflow",
  "dlc_id": "dlc.example.workflow",
  "dlc_version": "1.0.0",
  "server": "example_tools",
  "tool": "build_output",
  "params": {}
}
```

成功响应：

```json
{
  "schema": "cartridgeflow.dlc_worker_response.v1",
  "request_id": "request_...",
  "ok": true,
  "result": {},
  "artifact_refs": []
}
```

失败响应 MUST 携带稳定 code/message 或可转换为 Runtime Error Envelope 的结构。stdout 只能承载一个协议响应；普通日志写 stderr 或 run-scoped 日志。

### 29.2 Worker 生命周期

```text
absent -> validated -> inactive -> starting -> active
active -> stopping -> inactive
inactive -> uninstalling -> absent
starting | active -> failed | timed_out | cancelled
```

规则：

1. 主服务 MUST NOT 通过 import、动态 import 或 sys.path 注入加载 DLC backend。
2. Worker 必须验证 handler 属于 descriptor allowlist。
3. 请求和响应必须是 UTF-8 JSON 对象。
4. timeout、Run cancel 和 host shutdown 必须终止 Worker 执行域。
5. 最终状态必须记录为 succeeded、failed、timed_out 或 cancelled。
6. Worker 退出后主服务不得保留 DLC 模块引用或可调用 handler。
7. 大文件和二进制通过 Artifact 引用传递，不内联到 stdout。

Base MAY 使用每调用进程或持久 Worker，但必须证明作用域隔离、取消、停用和卸载语义等价。

前端组件消息使用领域中立类型：

```json
{
  "schema": "cartridgeflow.interaction_component_message.v1",
  "type": "interaction.propose",
  "request_id": "uuid",
  "channel_id": "channel_...",
  "run_id": "run_...",
  "cartridge_id": "example.workflow",
  "node_id": "review_storyboard",
  "component_id": "editor.storyboard",
  "interaction_id": "interaction_...",
  "payload": {
    "action_id": "submit",
    "draft_hash": "sha256:...",
    "input_revision": 3,
    "proposal_id": "uuid"
  }
}
```

宿主 MUST 校验消息 schema、一次性 channel、iframe/MessagePort identity、cartridge、run、node、component、interaction、input revision、action allowlist、draft hash 和 proposal identity。`interaction.propose` 只请求 Host 选择或展示一个 action，不回答 Pending Interaction，也不恢复 Run。大文件使用受权限控制的 Artifact URL 或上传会话，不通过消息内联。

### 29.3 Frontend Sandbox

主前端不得 import、eval、拼接执行或向主 document 注入卡带 JavaScript。每个 DLC frontend component 必须位于独立 iframe；标准 sandbox token 只允许 `allow-scripts`，MUST NOT 启用 `allow-same-origin`、`allow-top-navigation`、`allow-popups`、`allow-forms`、`allow-downloads`、`allow-modals`、`allow-pointer-lock` 或 `allow-presentation`。Base 增加 sandbox token 必须由后续协议版本和独立 capability 明确授权。

Sandboxed component MUST 从与 Base UI 不同的专用不可信 origin 提供，不携带 Base session cookie、Authorization 或其他 ambient credential，并使用 credentialless iframe 或可证明等价的凭据隔离。资源访问只使用短期、cartridge/component/file/hash scoped 的 Host 发行能力 URL。该 origin 不得承载 Base API、用户页面或其他卡带的共享可写状态。

Production Base MUST 使用独立 renderer/process 或可证明等价的执行隔离，使组件无限循环、内存膨胀、事件风暴或崩溃可以在不终止 Host UI/Runner 的情况下被限制和销毁。Base 必须公布有限的 entry/ready timeout、消息大小与速率、草稿大小、并发请求、内存/CPU 或等价资源策略。无法证明进程与资源隔离时，只能把 sandboxed component 标记为 dev/preview limitation，不能声明 production `interaction_process_isolation`。

frontend response 至少实施等价 CSP：

```text
default-src 'none'; script-src 'self'; connect-src 'none';
img-src 'self' data: blob:; style-src 'self' 'unsafe-inline';
font-src 'self'; object-src 'none'; frame-src 'none';
worker-src 'none'; child-src 'none'; media-src 'self' blob:;
form-action 'none'; base-uri 'none'; navigate-to 'none';
```

Host MUST 将 `frame-ancestors` 设置为当前 Base UI 的精确可信 origin；不得使用 `*`，也不得使用会阻止合法 Host 嵌入的 `'none'`。若 frontend 由独立资源 origin 提供，策略必须显式列出 Base UI origin。

`script-src` MUST NOT 包含 `'unsafe-inline'`、`'unsafe-eval'`、远程 origin、blob script 或 data script。HTML 中 script 只能通过包内相对 `src` 加载 descriptor `role=frontend_script` 文件；模块的静态或动态依赖也必须在 descriptor files 闭包中。禁止 Worker、Service Worker、SharedWorker、Worklet、WebAssembly 和运行时下载代码。

Base 必须强制阻断 iframe 自身导航、链接导航、location 赋值、重定向和其他向非 package URL 发起的导航请求，不能只依赖 `connect-src`。如果目标浏览器不支持 `navigate-to` 或等价拦截，Host 必须提供更强的资源 origin/网络拦截并通过真实浏览器测试；无法证明阻断时不得声明 `sandboxed_interaction_component`。

包内资源只能由同时校验 cartridge/version、component、规范化路径、descriptor membership、media type 和 hash 的端点提供。响应必须使用 `X-Content-Type-Options: nosniff`、`Referrer-Policy: no-referrer`、限制同源资源使用的 Cross-Origin-Resource-Policy，以及默认拒绝 camera、microphone、geolocation、display-capture、clipboard、USB、serial、HID 和 payment 等浏览器能力的 Permissions-Policy。HTML、脚本和 SVG 不得因错误 MIME 被当作其他被动资源执行。

DLC 不得访问主 DOM、全局 Store、路由器、CSS、其他卡带 Run、Artifact 或 private_data。页面切换、卡带停用或卸载时必须销毁 iframe、消息端口、监听器和未完成请求。

浏览器内脚本不得直接调用模型、MCP、remote API、DLC backend tool 或任意外部网络。需要这些能力时，组件更新草稿或提出声明 action，由用户通过 Host control 提交后，Flow 再进入对应能力节点。即使浏览器环境提供了 fetch、WebSocket、EventSource、sendBeacon 或导航 API，CSP 与宿主也必须阻断未授权外联。

### 29.4 消息信封

宿主创建 iframe 后 MUST 建立一次性通信通道：

1. Host 生成不可预测的 `channel_id` 与 nonce，并创建专用 `MessageChannel` 或安全等价物。
2. Host 只向目标 iframe 的 `contentWindow` 发送一次初始化消息并转移专用 port。由于无同源 sandbox 的 origin 为 opaque，通配 target origin 只允许用于这次初始化；必须同时校验目标 window identity。
3. Component 通过专用 port 回应 nonce，Host 验证后使通道进入 ready。
4. 后续业务消息只允许通过该 port，必须携带 channel、cartridge、run、node、component 和 interaction scope。
5. iframe reload、节点切换、Run 终态、卡带停用或超时后 channel 立即失效；旧 port 的消息必须拒绝。

所有请求 MUST 包含 schema、type、request_id、channel_id、run_id、cartridge_id、node_id、component_id、interaction_id 和 payload。需要响应的请求必须有 response/error/cancel/timeout 语义，不能靠单向消息猜测完成状态。

宿主响应示例：

```json
{
  "schema": "cartridgeflow.interaction_host_message.v1",
  "type": "interaction.proposal_result",
  "request_id": "uuid",
  "channel_id": "channel_...",
  "run_id": "run_...",
  "cartridge_id": "example.workflow",
  "node_id": "review_storyboard",
  "component_id": "editor.storyboard",
  "interaction_id": "interaction_...",
  "ok": true,
  "payload": {}
}
```

Host 必须验证消息实际来自分配给该 component instance 的 port。仅检查可伪造的 JSON 字段、`event.origin` 或 cartridge ID 不足以建立信任。

### 29.5 宿主能力

Sandbox MAY 请求 Base 明确授予的通用能力，例如：

- 读取当前 run snapshot 的安全子集。
- 读取当前卡带 Artifact metadata 或受控 URL。
- 更新当前 interaction 的未提交草稿。
- 提出由 Host action control 呈现的 action intent。
- 请求通知或用户下载。

标准 capability ID 至少包括 `run.read_declared`、`artifact.read`、`upload.create`、`draft.read`、`draft.write`、`interaction.propose`、`download.request` 和 `notification.request`。`draft.read/write` 只操作当前 run/interaction 的未提交草稿；跨 Run 私有状态不在该能力范围。每项能力必须在 Component Registry 与 DLC descriptor 中同时声明，并由 Host 按 cartridge/run/node/interaction scope 授权。

最终 action controls 必须由 Host 在 sandbox iframe 外根据 Component Registry 与节点 `allowed_actions` 生成。组件 MAY 请求 Host 高亮某个 action，但只有用户对 Host control 的可信操作才能调用 answer API。Host commit 必须再次读取并校验当前 draft、展示稳定 action label、绑定 draft hash/input revision/idempotency key，并在成功后关闭所有旧 proposal。iframe 消息不能模拟该可信操作，也不能决定执行计划中的后继节点。

下列能力在 v1.0 中禁止授予 frontend component：Pending Interaction 最终提交、任意 Store 读写、任意节点执行、任意路由跳转、模型或工具直调、任意网络代理、凭据读取、Base 文件系统、主前端状态、其他卡带数据、任意 HTML 注入和永久后台任务。

DLC UI 不得绕过 Runner 直接修改已提交状态。Host API 成功只表示宿主请求已受理，不得由组件伪装为节点完成、Artifact 已批准或 Delivery 已成功。

### 29.6 脚本审计与失败关闭

Base 在安装、升级、开发预览和认证前至少检查：

- 所有 HTML entry 已解析且没有 inline script、event handler 或未声明主动内容。
- 所有脚本、模块和资源都在 descriptor files 中且 hash 匹配。
- CSP、sandbox tokens、Host capability 和消息 schema 满足本版本。
- 专用不可信 origin、无 ambient credential、进程/renderer 隔离和有限资源策略真实生效。
- 组件不能通过资源 URL、重定向、source map、SVG、CSS、媒体容器或 MIME 欺骗加载未声明代码。
- 组件尝试 fetch、WebSocket、beacon、表单、图片、媒体或 frame 自导航时，不产生任何外部网络请求。
- 组件无限循环、内存膨胀、消息风暴或崩溃时，Host UI 与 Runner 仍可响应并能销毁该组件执行域。
- 开发模式、热更新和 localhost 不得放宽卡带脚本权限；开发辅助能力必须运行在卡带 sandbox 之外。

任一检查失败必须在脚本执行前返回稳定错误，例如 `INTERACTION_SCRIPT_FORBIDDEN`、`INTERACTION_COMPONENT_HASH_MISMATCH`、`INTERACTION_COMPONENT_CSP_INVALID`、`INTERACTION_HOST_CAPABILITY_DENIED` 或 `INTERACTION_CHANNEL_SCOPE_MISMATCH`。Base 不得静默删除脚本后继续，也不得退回无 sandbox 的 HTML 预览。

## 30. Protocol Overlay

卡带领域协议只能位于卡带 DLC 中。Base 为当前卡带构造：

```text
global protocol registry + current cartridge overlay
```

Overlay 不得写入全局 registry。卡带停用或卸载后，Overlay 必须消失。

Overlay 加载规则：

1. 只读取 descriptor 明确列出的协议文件。
2. 协议 ID/version 在当前 scoped view 中必须唯一。
3. 伴随协议的 `extends` 必须匹配当前 primary protocol 声明。
4. Overlay required profiles/capabilities 必须由 Base 和当前 DLC 共同满足。
5. 其他卡带只有在自己携带或明确依赖同一协议时才能看到该协议。
6. Overlay 失败不得回退为忽略领域协议后继续运行。

## 31. 资源所有权与卸载

DLC 资源 ownership：

- `package`：卸载删除。
- `private_data`：普通卸载删除。
- `shared_dependency`：按引用和用户确认处理。
- `user_artifact`：普通卸载保留。

卸载顺序：

1. 检查活动 Run，默认阻断不安全卸载。
2. 拒绝新调用。
3. 取消或等待活动 Worker。
4. 销毁 iframe。
5. 注销工具代理、路由和 Overlay。
6. 删除 package 与 private_data。
7. 保留 user_artifact，除非用户确认 purge。
8. 执行无残留扫描。

### 31.1 Ownership 规则

- `package`：代码、协议、UI、workflow 和随包资产；卸载必须删除。
- `private_data`：卡带缓存、索引和私有状态；普通卸载默认删除。
- `shared_dependency`：共享模型、应用或运行库；不得由单张卡带擅自删除。
- `user_artifact`：用户生成和明确保存的产物；普通卸载默认保留到通用归档。

路径必须最小化且明确。不得把整个工作区、用户目录或公共模型目录声明为 private_data。

Asset Registry、Interaction Component Registry、passive templates 和 DLC frontend files 都属于 `package`。组件未提交草稿属于 run-scoped runtime state；明确保存为跨 Run 卡带状态时才属于 `private_data` 并需要独立能力、permission 和真实 effect，导出给用户时属于 Artifact。交互节点引用只保存 package identity，不得复制本机 Provider、工具实例、URL、key 或 private path 进入卡带。

### 31.2 安装与升级

安装顺序：读取静态声明 -> 临时目录展开 -> 防路径穿越 -> hash/签名 -> 兼容性/权限/依赖预检 -> 用户确认 -> 原子激活。发现和预检阶段不得执行卡带代码。

升级必须保留旧版本或可恢复备份。任一阶段失败后，要么旧版本继续可用，要么新版本完整激活；不得留下半安装 Registry、Worker、路由或文件集合。

### 31.3 停用

停用顺序：拒绝新调用 -> 等待或取消活动调用 -> 终止 Worker -> 销毁 iframe -> 注销代理/路由/Overlay -> 清理进程缓存。停用不自动删除用户数据。

### 31.4 卸载模式

- `preserve_artifacts`：删除功能、package 和 private_data，保留 user_artifact。
- `purge_all`：在独立高风险确认后同时删除当前卡带 user_artifact。

shared_dependency 只有在引用为零、来源可识别且用户明确允许时才能删除。

### 31.5 无残留验收

卸载后必须证明：

1. 卡带目录和 private_data 不存在。
2. 新旧工具代理均返回 extension_inactive 或不存在。
3. Worker、子进程、端口和任务不再活动。
4. iframe、静态资源路由和消息监听器不存在。
5. Protocol Overlay 和领域类型不可见。
6. 默认 Registry 和其他卡带不受影响。
7. user_artifact 按所选模式保留或清除。

任一残留都使 DLC lifecycle conformance 失败。
