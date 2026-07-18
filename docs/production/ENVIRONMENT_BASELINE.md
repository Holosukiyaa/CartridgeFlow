# M0 本机生产环境基线

记录日期：2026-07-18

状态：环境、API 通路与 Wan2.1 VACE 候选工作流已实测；首发 ComfyUI 视频工作流尚未选定。

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
- `diffusion_models/wan2.1_vace_1.3B_fp16.safetensors`。
- `text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors`。
- `vae/wan_2.1_vae.safetensors`。

| 视频模型文件 | SHA-256 |
| --- | --- |
| `wan2.1_vace_1.3B_fp16.safetensors` | `640CCC0577E6A5D4BB15CD91B11B699EF914FC55F126C5A1C544E152130784F2` |
| `umt5_xxl_fp8_e4m3fn_scaled.safetensors` | `C3355D30191F1F066B26D93FBA017AE9809DCE6C627DDA5F6A66EAA651204F68` |
| `wan_2.1_vae.safetensors` | `2FC39D31359A4B0A64F55876D8FF7FA8D780956AE2CB13463B0223E15148976B` |

### Wan2.1 VACE 1.3B 候选工作流

- API 工作流：`config/comfyui/workflows/wan21_vace_1_3b_v2v_smoke.api.json`。
- 基准脚本：`scripts/benchmark_comfyui_workflow.py`。
- 控制输入：卡带真实 Blender 走路镜头，12 fps。
- 推荐候选控制：逐帧 Canny + 首帧角色参考图。

| 控制方式 | 分辨率 | 帧数 | 步数 | 耗时 | 驱动峰值显存 | 结果 |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| 原始 RGB | 288x512 | 17 | 8 | 51.5 秒 | 约 8.13 GB | 可播放，但模糊且有明显色块 |
| 原始 RGB | 480x832 | 17 | 20 | 56.8 秒 | 10.42 GB | 细节提高，但绿橙色伪影与场景生长不可接受 |
| Canny | 480x832 | 17 | 20 | 87.7 秒 | 10.04 GB | 人物、步态和轮廓稳定，画面可用 |
| Canny | 480x832 | 33 | 20 | 97.9 秒 | 未记录 | 2.75 秒完整生成，无 OOM，长段一致性通过初检 |

33 帧任务开始后，基准前台进程因外层命令超时退出，ComfyUI 后台仍正常完成，因此本行不补写推测的显存峰值。17 帧同分辨率实测已证明该工作流在 12 GB VRAM 内运行。

Canny 版的能力边界：它能保留人物运动、朝向、镜头运动和主要轮廓，但会重新设计房屋、路面等场景细节。它适合把 Blender 预演重渲染为统一的风格化成片，不是严格保留原始几何与材质的普通超分工作流。首发方案是否锁定，需要先人工审看长段视频。

长段输出：`C:/ComfyUI_windows_portable/ComfyUI/output/CartridgeFlow/vace_1_3b_canny_33f_00001_.mp4`。

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
- 将首镜头扩展为 3 至 5 镜头的完整 15 至 30 秒样片。
