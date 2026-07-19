# Portable DLC Boundary

更新日期：2026-07-19

本文说明 `CF-FARP@0.5` 的实现边界。规范正文是 `docs/protocol/CARTRIDGEFLOW_FLOW_AUTHORING_RUNTIME_PROTOCOL_v0.5.md`，本文不能替代协议。

## 核心原则

基座只提供通用扩展宿主，不保存任何单卡带业务实现。卡带专用的后端工具、前端工作台、伴随协议、供应商工作流和测试必须位于卡带包内。卸载卡带后，这些代码不得继续出现在工具注册表或基座目录中。

```text
core/extensions/
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
    protocols/
    workflows/
    tests/
```

## 激活链路

1. `ManifestValidator` 读取 `manifest.portable_dlc`。
2. `load_portable_dlc_descriptor` 校验 owner、作用域、工具集合、入口路径、协议覆盖、资源归属和 SHA-256。
3. `BuiltinMcpRegistry.for_manifest(..., package_path=...)` 为当前卡带建立作用域注册表。
4. 每次工具调用启动隔离 Python worker，以 JSON stdin/stdout 通信。
5. 前端入口只通过经过 descriptor 校验的服务端路由提供，并进入 `sandbox="allow-scripts"` 的 iframe。

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

- 不得在 `core/lab/mcp/`、`core/protocol/` 或前端通用页面中硬编码卡带 ID、工具实现或领域协议。
- 不得在 import、descriptor 校验、工具描述或卡带列表阶段启动 Blender、ComfyUI、网络请求或文件生产。
- 不得让卡带工具进入全局默认 Registry。
- 不得让 iframe 获得 `allow-same-origin`、顶层导航或任意文件访问。
- 不得把用户产物当作卡带私有数据随卸载删除。

## 系列 3D 卡带

`dev.series_3d_episode_factory` 的分镜工具、Blender 预演、CRCP 校验代码、ComfyUI 工作流和导演台全部位于：

```text
cartridges/dev/dev.series_3d_episode_factory/dlc/
```

它们不是基座能力。其他卡带不声明该 DLC 时，不会看到这些工具、协议或 UI。
