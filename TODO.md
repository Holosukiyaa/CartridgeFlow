# CartridgeFlow TODO

- [x] 清理旧卡带，只保留 `dev.series_3d_episode_factory`。
- [x] 修复纯 Blender 全分镜渲染与最终 MP4 交付链路。

长期方向和验收标准见 `GOAL.md`。这里不保留历史完成项，只记录当前里程碑的下一步。

## 当前里程碑：M0 本机生产基线

- [x] 记录 Blender、FFmpeg、Python、ComfyUI、CUDA 和模型的实际路径与版本。
- [x] 确认 ComfyUI 本地 API 可调用，并保存一个最小 workflow JSON。
- [ ] 在 RTX 3080 12GB 上测试候选工作流，记录分辨率、帧数、耗时、峰值显存和结果。
- [ ] 只选定一个首发 ComfyUI 工作流，明确它负责的镜头类型和失败边界。
- [x] 写入 `docs/production/ENVIRONMENT_BASELINE.md`，保证他人可以复现实测。
- [x] 冻结第一条 15 至 30 秒样片的角色、场景、动作、镜头数和无对白方案。

M0 完成后清空本页，再写 M1“真实 3D 单镜头”的具体任务。
