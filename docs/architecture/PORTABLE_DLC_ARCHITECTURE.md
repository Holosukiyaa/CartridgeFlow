# Portable DLC Architecture

更新日期：2026-07-21

本文记录 `CARTRIDGEFLOW-BASE@0.2 + CF-FARP@0.7` 的 Portable DLC 目标架构，包括激活链路、交互组件脚本隔离、资源所有权和不可破坏的实现边界。当前参考底座仍只实现 v0.6 partial；规范正文位于 `docs/protocol/CARTRIDGEFLOW_BASE_CONTRACT_v0.2.md` 和 `docs/protocol/CARTRIDGEFLOW_FLOW_AUTHORING_RUNTIME_PROTOCOL_v0.7.md`，本文不能替代协议。

## 核心原则

基座只提供通用扩展宿主，不保存任何单卡带业务实现。卡带专用的后端工具、前端工作台、伴随协议、供应商工作流和测试必须位于卡带包内。卸载卡带后，这些代码不得继续出现在工具注册表或基座目录中。

```text
src/core/extensions/
  descriptor.py        # 元数据和完整性校验
  registry.py          # 卡带作用域代理注册
  worker_client.py     # 隔离进程客户端
  worker_bootstrap.py  # JSON stdio worker 入口
  worker_sdk.py        # worker 内最小 SDK

cartridges/<source>/<cartridge-id>/
  manifest.json
  root.flow.json
  dlc/
    descriptor.json
    backend/
    frontend/
      components/
    protocols/
    workflows/
    tests/
```

## 激活链路

1. `ManifestValidator` 读取 `manifest.portable_dlc`。
2. `load_portable_dlc_descriptor` 校验 owner、作用域、工具集合、入口路径、协议覆盖、资源归属和 SHA-256。
3. `BuiltinMcpRegistry.for_manifest(..., package_path=...)` 为当前卡带建立作用域注册表。
4. 每次工具调用启动隔离 Python worker，以 JSON stdin/stdout 通信。
5. 前端交互组件只通过经过 descriptor v2 文件成员、media type 和 hash 校验的专用不可信 origin 提供，并进入只有 `allow-scripts`、无 ambient credential 的无同源 iframe。
6. 生产宿主使用独立 renderer/process 或等价资源隔离，组件卡死或崩溃不得拖垮 Host UI 与 Runner。
7. 每个交互节点通过 Component Registry 解析具名 frontend component，Host 使用一次性 MessageChannel 提供最小授权能力。
8. 组件只维护草稿或提出 action intent；iframe 外的 Host controls 才能提交 Pending Interaction 并恢复 Flow。

未声明 `portable_dlc` 的卡带只获得基座工具。默认 `BuiltinMcpRegistry(root)` 不加载任何卡带代码。

## 资源归属

descriptor 中的资源必须标记为：

| ownership | 卸载行为 |
| --- | --- |
| `package` | 随卡带包删除 |
| `private_data` | 随卡带卸载删除 |
| `shared_dependency` | 不自动删除 |
| `user_artifact` | 默认保留 |

卸载还必须清空作用域注册缓存。已经拿到的工具代理在包路径消失后返回 `extension_inactive`，不能继续执行残留代码。

## 禁止事项

- 不得在 `src/core/lab/mcp/`、`src/core/protocol/` 或前端通用页面中硬编码卡带 ID、工具实现或领域协议。
- 不得在 import、descriptor 校验、工具描述或卡带列表阶段启动 Blender、ComfyUI、网络请求或文件生产。
- 不得让卡带工具进入全局默认 Registry。
- 不得让 iframe 获得 `allow-same-origin`、顶层导航或任意文件访问。
- 不得执行 inline script、eval、未登记模块、Worker、WebAssembly 或允许组件直接联网。
- 不得让交互组件直接调用模型、工具、任意节点或 Store；组件只提交已声明 action，Runner 负责路由。
- 不得把用户产物当作卡带私有数据随卸载删除。

## 空基座验收

正式基座不预装业务卡带。干净检出后：

- `CartridgeRegistry.list_cartridges()` 返回空列表；
- 默认 `BuiltinMcpRegistry` 只暴露基座拥有的通用工具；
- `src/core/`、`src/backend/` 和通用前端不包含任何卡带 id 或领域工具实现；
- 安装一张 Portable DLC 卡带时，工具只进入该卡带作用域；
- 删除卡带包后，已有代理返回 `extension_inactive`。
