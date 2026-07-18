# M0 本机生产环境基线

记录日期：2026-07-18

状态：环境与 API 通路已验证；首发 ComfyUI 视频工作流尚未选定。

## 硬件

- GPU：NVIDIA GeForce RTX 3080，12288 MiB VRAM。
- GPU 驱动：610.74。
- CUDA UMD：13.3。
- 系统内存：约 32 GB。

## 工具

| 工具 | 版本 | 路径 | 状态 |
| --- | --- | --- | --- |
| Blender | 4.5.11 LTS | `.tools/blender-4.5.11-windows-x64/blender.exe` | 官方便携包 SHA-256 已验证 |
| FFmpeg | 8.1.1 | `C:/ffmpeg/bin/ffmpeg.exe` | H.264 编解码可用 |
| Python | 3.13.14 | `.tools/python/python.exe` | CartridgeFlow 运行环境 |
| ComfyUI | 0.27.0 | `C:/ComfyUI_windows_portable/ComfyUI` | 本地 API 可用 |
| ComfyUI Python | 3.13.12 | `C:/ComfyUI_windows_portable/python_embeded/python.exe` | torch 2.12.0+cu130 |

Blender 官方包 SHA-256：

```text
E11D3A8E4D4249BE5A7DB4A9325C1F670037D4233467C3B0BDA181001EFE44D3
```

## ComfyUI API

- 地址：`http://127.0.0.1:8188`。
- `GET /system_stats`：成功识别 RTX 3080 与 12288 MiB VRAM。
- API 健康工作流：`config/comfyui/workflows/api_healthcheck.json`。
- `POST /prompt`：成功。
- 历史查询：成功。
- 测试产物：`C:/ComfyUI_windows_portable/ComfyUI/output/CartridgeFlow/healthcheck_00001_.png`。

当前模型：

- `anything-v5.safetensors`。
- Canny、Depth、Lineart 三个 SD1.5 ControlNet。
- PixelArtRedmond15V LoRA。

当前没有视频模型。因此 API 健康检查通过不代表视频增强能力已经通过；首发视频工作流仍需单独选择、下载和基准测试。

## 真实 3D 资产验证

- 本地资产根：`.data/assets/pilot_01`。
- 男性角色与动作库均为 65 根骨骼，骨骼名称和顺序完全一致。
- 免费动作包包含 43 个可导入动作。
- 首镜头动作：`Walk_Loop`，非根位移版本；角色世界位移由卡带控制。
- Blender 4.5.11 可导入角色、动作、Kenney 建筑、Quaternius 街灯、Poly Haven PBR 材质与 HDRI。
- 角色 glTF 原包有两处法线贴图文件名不一致；本地资产包增加兼容副本，原始 ZIP 未修改。

真实卡带工具基准：

| 项目 | 结果 |
| --- | --- |
| 分辨率 | 360x640 |
| 帧率 | 24 fps |
| 时长 | 3 秒 / 72 帧 |
| EEVEE 采样 | 8 |
| 渲染耗时 | 约 12.2 秒 |
| Blender 进程峰值内存 | 约 2 GB |
| 视频 | H.264 MP4 |
| 质量门 | `real_character_motion_scene_rendered` |

验证产物位于 `test_output/series_3d_episode/pilot_m1_card`。该目录属于运行产物，不提交 Git。

## 尚未完成

- 选择一个能在 12GB VRAM 上稳定运行的首发 ComfyUI 视频工作流。
- 使用真实 Blender 控制素材测试该工作流的显存、耗时和一致性。
- 将首镜头扩展为 3 至 5 镜头的完整 15 至 30 秒样片。
