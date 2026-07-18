# CartridgeFlow TODO

长期方向和验收标准见 `GOAL.md`。这里只记录当前里程碑，不保留历史完成项。

## 当前里程碑：M2 单镜头 ComfyUI 身份替换证明

固定基线：`wan21_vace_1_3b_character_replace`，RTX 3080 12GB，短镜头使用 `4n+1` 帧。工作流消费 Blender 原片、角色生成遮罩和用户批准的角色参考图；深度与姿态进入控制包校验，但当前首发工作流尚不直接消费。

- [x] 将用户选定并确认可用的动漫男性角色参考图登记为 CastPack revision 1。
- [x] 使用同一个 17 帧 Shot Control Bundle 运行三组固定 seed 对照实验，不改变锁定的动作、镜头、时序和场景地标。
- [ ] 对三组候选片检查替身残留、身份漂移、动作反向、脚底接触、背景漂移和时序闪烁，并记录 FailureRecord。
- [ ] 由用户明确接受或驳回候选片；驳回时只修改已声明的 free 字段并增加 retry index。
- [ ] 补齐角色门、连续性门和 artifact audit 后，再评估基座是否可以声明支持 `CF-CRCP@0.1`；通过前不得添加认证标签。
