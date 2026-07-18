# Built-in MCP 与 DLC 模块边界

更新日期：2026-07-18

本文定义 `core/lab` 内置 MCP 工具的代码组织和 DLC 边界。它是实现架构说明，不替代 `CF-FARP@0.4` 或 `CF-CRCP@0.1` 的规范正文。

## 目标

`core/lab/builtin_mcp.py` 只负责：

- 创建 `BuiltinMcpRegistry`。
- 注册文件系统基础工具。
- 读取并注册媒体模块。
- 分发 `server/tool` 调用。
- 暴露工具描述和 DLC 元数据。

它不得继续承载具体像素绘制、短视频、空间 blockout、系列 Blender 或 ComfyUI 实现。

## 目录结构

```text
core/lab/
  builtin_mcp.py                 # 薄 facade，不放业务工具实现
  mcp/
    __init__.py
    dlc.py                       # DLC descriptor 与模块注册表
    shared.py                    # 跨模块的无业务通用辅助函数
    media_core.py                # 基础媒体探测、关键帧、风格化、QC
    pixel_episode.py             # 像素资产、像素分镜、Godot、FFmpeg
    short_video.py               # 短视频脚本、图片、语音、封装
    spatial.py                   # 空间 blockout 和动画预演
    series_3d.py                 # 真实 3D 资产匹配、动作匹配、Blender
```

协议层的 `core/protocol/creative_recast.py` 只提供 Shot Control Bundle 和 CreativeSpec 的只读结构校验。它不属于默认 MCP DLC、不会注册工具，也不会写入或生成任何 artifact；只有 CRCP 基座能力完成声明后，独立的 `core/lab/mcp/creative_recast.py` 才能接入运行时。

模块只能通过 `register(registry)` 暴露工具。模块导入和注册阶段不得执行 Blender、ComfyUI、Godot、网络请求或文件生产副作用。

## DLC 描述

`core/lab/mcp/dlc.py` 为每个模块声明：

- `id`：稳定的模块或 DLC ID。
- `kind`：`core` 或 `dlc`。
- `protocol`：当前模块遵守的主协议。
- `optional_extension`：可选 companion protocol，例如 `CF-CRCP@0.1`。
- `enabled_by_default`：是否在当前基座注册工具入口。
- `modules`：实现文件。

当前映射：

| 模块 | kind | 主协议 | 可选扩展 |
| --- | --- | --- | --- |
| `core.media` | core | `CF-FARP@0.4` | 无 |
| `core.short_video` | core | `CF-FARP@0.4` | 无 |
| `dlc.pixel_episode` | dlc | `CF-FARP@0.4` | 无 |
| `dlc.spatial_blockout` | dlc | `CF-FARP@0.4` | 无 |
| `dlc.series_3d_episode_factory` | dlc | `CF-FARP@0.4` | `CF-CRCP@0.1` |

工具描述会额外返回 `dlc` 字段，使前端、测试台和 Agent 能知道工具属于哪个模块以及哪个协议。

## 协议加载规则

### 当前规则

- 所有已存在的工具入口继续遵守 `CF-FARP@0.4`，以保持旧卡带兼容。
- `CF-CRCP@0.1` 目前只作为系列创作扩展的声明，不会因为导入 `series_3d` 就自动改变旧卡带行为。
- 当前基座尚未声明支持 `CF-CRCP@0.1`，因此不得自动注册 CRCP 专用工具或添加认证标签。

`BuiltinMcpRegistry(workspace_root)` 是默认的基础入口：它只加载 FARP 工具。扩展上下文必须显式传入，推荐使用
`BuiltinMcpRegistry.for_manifest(workspace_root, manifest, capabilities)`。注册器会在
`dlc_report()` 中返回每个 companion protocol 的决定：

- `not_requested`：manifest 没有声明扩展；
- `blocked_missing_capabilities`：声明了扩展，但当前基座缺少所需 capability；
- `unimplemented`：声明和 capability 都满足，但实现模块尚未加入；
- `enabled`：实现模块、显式声明和 capability 均满足。

这些决定只控制模块是否进入 Registry，不会在构造或描述阶段启动 Blender、ComfyUI、Godot、网络请求或文件生产。

运行创建前，`manifest.protocol_extensions` 还会经过兼容性报告：扩展必须已登记、当前基座必须声明支持，且声明的 required profiles/capabilities 必须满足。Registry 门禁是第二道运行时保护，不能替代兼容性阻断。

### 后续规则

当实现 CRCP 专用工具时，必须新增独立模块，例如：

```text
core/lab/mcp/creative_recast.py
```

该模块必须：

1. 声明 `DLC_ID` 和 `DLC_PROTOCOL = "CF-CRCP@0.1"`。
2. 只在 manifest 的 `protocol_extensions` 明确声明并且基座能力满足时注册。
3. 不改变 `core.media`、`pixel_episode`、`short_video`、`spatial` 或 `series_3d` 的默认工具语义。
4. 不能通过导入副作用注册自己。
5. 使用独立的 conformance 测试证明未声明 CRCP 的卡带不会加载该模块。

这保证不采用 CRCP 的其他卡带不承担 CRCP 的输入契约、审批门、控制包校验或运行副作用。

## 依赖规则

- `shared.py` 只能放跨模块、无产品语义的辅助函数。
- 功能模块可以读取 `shared.py`。
- 功能模块之间的依赖必须显式导入，禁止从 facade 的隐式全局名称读取函数。
- `series_3d.py` 可以使用空间模块的通用数值辅助函数，但不能依赖空间 DLC 的运行状态。
- 新增功能不得把实现重新放回 `builtin_mcp.py`。
- 跨 DLC 的数据必须通过显式参数、manifest 或 artifact 传递，不得共享隐藏全局状态。

## 副作用边界

注册模块不是执行模块。真正的副作用只允许发生在工具调用中，并且必须继续遵守 `CF-FARP@0.4` 的 `effect`、permission、audit 和 failure policy。

| 阶段 | 允许副作用 |
| --- | --- |
| Python import | 不允许 |
| `BuiltinMcpRegistry()` | 只建立工具表，不生成文件、不启动服务 |
| `describe()` | 只读描述和 DLC 元数据 |
| `call()` | 由具体工具按 manifest 和节点契约执行 |

## 重构规则

1. 拆分是行为保持型重构，不得顺便改变工具输入输出。
2. 每移动一个工具，必须保留原工具 ID 和返回字段。
3. 新模块先通过导入、工具列表、目标模块 conformance，再删除旧实现。
4. 任何新的协议能力先进入协议版本和 capability 词表，再进入模块实现。
5. 需要改变旧工具语义时，建立 ChangeProposal；不能以“模块化”为理由绕过协议版本治理。

## 当前状态

- facade 已从约 6,855 行降至约 443 行。
- 原有媒体工具已经拆为五个功能模块。
- DLC 描述会随工具描述返回。
- CRCP 专用控制包工具尚未接入，当前没有伪造 CRCP runtime 支持。
- 下一次扩展应新增 `creative_recast.py`，而不是把控制包逻辑写回 `builtin_mcp.py`。
