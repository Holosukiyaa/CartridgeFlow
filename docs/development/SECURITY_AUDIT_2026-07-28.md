# CartridgeFlowLite 安全审计（2026-07-28）

## 范围与结论

本次审计覆盖 Python、FastAPI、TypeScript、React、DLC/MCP 子进程、文件与产物路径、HTML/iframe、远程请求、凭据与依赖。审计基于 Lite 的本地单用户威胁模型；卡带业务逻辑仍由卡带或 DLC 持有，没有加入基座。

已修复 5 个高风险和 2 个中风险问题。`npm audit` 为 0，Lite API 仅绑定回环地址，主动 HTML 产物不可执行脚本，统一数据目录和 run 产物均有路径边界。仍有 1 个需要产品与平台共同决定的中风险信任边界：Portable DLC 后端是独立受监督进程，但不是面向恶意 Python 代码的 OS 安全沙箱。

## Findings

### SEC-001（高，已修复）：内置文件工具可访问私有数据目录

**影响：** 卡带声明 `filesystem/read_file` 或写工具后，原实现可直接访问工作区内的 `.data/user/config`，可能读取模型密钥或覆盖本地配置。

**修复：** 文件工具现在拒绝整棵 CartridgeFlow 数据目录的读取、写入和枚举；仅 `read_file`/`exists` 可按明确的 `.data/temp/uploads/<token>` 路径访问上传缓存。外置 `CARTRIDGEFLOW_DATA_ROOT` 仍映射到相同的 `.data/...` 逻辑命名，不向 API 泄漏绝对路径。实现见 [`builtin_mcp.py`](../../src/core/lab/builtin_mcp.py#L79) 和 [`main.py`](../../src/backend/main.py#L72)，回归见 [`test_process_nodes.py`](../../scripts/tests/runtime/test_process_nodes.py#L151)。

### SEC-002（高，已修复）：卡带 ZIP 导入缺少完整资源边界

**影响：** 恶意 ZIP 可利用父目录、绝对路径、符号链接、重复成员、加密成员或高膨胀内容写出解压目录或耗尽资源。

**修复：** 导入同时限制压缩包大小、成员数、单成员大小和总解压大小，并在解压前拒绝非法路径、符号链接、重复项和加密项。实现见 [`main.py`](../../src/backend/main.py#L541)，回归见 [`test_lite_api_surface.py`](../../scripts/tests/lite/test_lite_api_surface.py#L126)。

### SEC-003（高，已修复）：产物可越过当前 run，HTML 产物可成为主动内容

**影响：** 只限制到项目根会允许伪造产物元数据读取其他运行或项目文件；同源 HTML 产物若可执行脚本，还可访问 Base API。

**修复：** 产物路径必须位于当前 `run_id/artifacts` 快照目录；预览与下载均复用该校验。产物响应使用 `sandbox`、`script-src 'none'`、`connect-src 'none'` 和 `no-store`。实现见 [`artifacts.py`](../../src/core/cartridge/artifacts.py#L59) 与 [`main.py`](../../src/backend/main.py#L3224)，回归见 [`test_process_nodes.py`](../../scripts/tests/runtime/test_process_nodes.py#L181) 和 [`test_lite_api_surface.py`](../../scripts/tests/lite/test_lite_api_surface.py#L201)。

### SEC-004（高，已修复）：本地 API 暴露与诊断回显边界过宽

**影响：** 宽松 CORS/Host、网络绑定或公开 OpenAPI 文档会扩大本地服务攻击面；Pydantic/HTTP 错误可能回显提交的密钥。

**修复：** 启动器只绑定 `127.0.0.1` 并在端口占用时失败关闭；FastAPI 使用精确本地 Origin、方法和请求头白名单及 Trusted Host；Lite 隐藏 `/docs`、`/redoc`、`/openapi.json`；验证错误、HTTP 错误和诊断包统一脱敏。实现见 [`launch.py`](../../scripts/launch.py#L33)、[`main.py`](../../src/backend/main.py#L85)、[`lite_main.py`](../../src/backend/lite_main.py#L31) 与 [`main.py`](../../src/backend/main.py#L130)。

### SEC-005（高，已修复）：前端依赖存在已公开高风险公告

**影响：** PostCSS/Nanoid 锁定版本存在公告；React Router 7 的可用版本区间分别受旧 XSS/DoS 与新 RSC CSRF 公告影响。

**修复：** 更新 PostCSS/Nanoid，并移除仅用于三条客户端路由的 React Router，改用浏览器 History API 保持现有 URL、旧路由重定向及前进/后退行为。当前 `npm audit` 为 0。锁定证据见 [`package-lock.json`](../../src/frontend/package-lock.json#L957)，路由入口见 [`App.tsx`](../../src/frontend/src/App.tsx#L1)。

### SEC-006（中，已修复）：外部工具空响应被当作成功

**影响：** 付费 API、MCP 或远程工具返回空 body、`null`、空字符串、空数组或空对象时，Flow 可能把无结果记录为成功，形成静默回退式假成功。

**修复：** HTTP 适配器返回稳定 `tool_empty_response` 失败，保留真实 HTTP 状态且不生成成功内容。实现见 [`external_adapters.py`](../../src/core/studio/external_adapters.py#L205)，回归见 [`test_external_adapters.py`](../../scripts/tests/studio/test_external_adapters.py#L158)。

### SEC-007（中，已修复）：外置统一数据目录的路径语义不完整

**影响：** 运行数据根在项目外时，导入结果会尝试生成项目相对路径，产物快照也会因项目根校验而失败。

**修复：** API 始终公开 `.data/...` 逻辑路径；产物边界改为当前 run，而不是项目根。默认目录、外置目录和历史内部目录层级保持同一语义。回归见 [`test_lite_api_surface.py`](../../scripts/tests/lite/test_lite_api_surface.py#L171)。

### SEC-008（中，未修复，需要产品/平台决策）：DLC 后端不是恶意代码安全沙箱

**证据：** Worker 使用独立 `python -I` 子进程、声明 handler、JSON stdio、超时/取消和进程树终止；但启动器仍会导入并执行包内 Python handler，代码继承当前用户的 OS 文件与网络权限。见 [`worker_client.py`](../../src/core/extensions/worker_client.py#L110) 和 [`worker_bootstrap.py`](../../src/core/extensions/worker_bootstrap.py#L40)。

**当前保护：** descriptor/文件 hash、卡带作用域、工具 allowlist、effect/permission、每调用进程、超时、取消、卸载和日志状态均已验证。这些保护能隔离生命周期和宿主进程，不能抵御蓄意绕过 SDK 的原生 Python 代码。

**所需决策：** 二选一：明确“安装并启用后端 DLC 等同信任本机插件代码”，增加签名/来源/用户确认；或引入 OS 级低权限身份、文件系统 allowlist、网络 namespace/防火墙和资源配额。Python import 黑名单不是可靠安全边界，本次没有以伪沙箱方式修改协议语义。

## 前端内容隔离

- 被动 HTML 使用无脚本 CSP，见 [`passiveHtml.ts`](../../src/frontend/src/pages/flow-workbench/passiveHtml.ts#L1)。
- v0.8 交互组件使用 `sandbox="allow-scripts"`、credentialless iframe、一次性 `MessageChannel`、nonce、scope 和 capability allowlist，见 [`InteractionSandboxFrame.tsx`](../../src/frontend/src/components/InteractionSandboxFrame.tsx#L6)。
- 专用 renderer 使用 `connect-src 'none'` 和同源资源策略，见 [`sandbox_renderer.py`](../../src/core/extensions/sandbox_renderer.py#L128)。

## 验证

```powershell
$env:PYTHONPATH='src'
python -B -m unittest scripts.tests.runtime.test_process_nodes scripts.tests.lite.test_lite_api_surface -v
python -B -m unittest scripts.tests.runtime.test_worker_lifecycle scripts.tests.runtime.test_portable_dlc scripts.tests.runtime.test_sandboxed_interaction -v
python -m pip check
cd src/frontend
npm audit --json
npm run build
```

真实外部模型、MCP、付费 API 和恶意 DLC 的 OS 级攻击测试需要独立受控环境与明确凭据/信任策略，本次未伪造这些结果。
