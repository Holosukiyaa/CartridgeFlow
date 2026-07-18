# CartridgeFlow Creative Recast Control Protocol v0.1

协议编号：`CF-CRCP-0.1`

协议状态：`active`

发布状态：完整正文

关系：本协议扩展 `CF-FARP@0.4` 的生产内容控制语义，不替代 `CF-FARP@0.4`。卡带运行、节点、副作用、暂停恢复、工具和认证仍以 `CF-FARP@0.4` 为准。

控制属性：`read_only_append_only`

本协议的目标是同时提供创作自由度和可控性。自由度只能出现在声明的 `free` 字段和边界内；所有没有被声明为自由的内容都视为锁定。协议正文、已批准的创作规格和每次运行快照不得被 LLM、ComfyUI 或单个卡带静默改写。

---

## 目录

1. [协议定位](#1-协议定位)
2. [设计目标](#2-设计目标)
3. [规范关键词](#3-规范关键词)
4. [版本治理与只读规则](#4-版本治理与只读规则)
5. [实体定义](#5-实体定义)
6. [与 CF-FARP 的关系](#6-与-cf-farp-的关系)
7. [锁定项与自由项](#7-锁定项与自由项)
8. [创作模式](#8-创作模式)
9. [首版生产基线](#9-首版生产基线)
10. [Shot Control Bundle 契约](#10-shot-control-bundle-契约)
11. [CreativeSpec 契约](#11-creativespec-契约)
12. [资产包契约](#12-资产包契约)
13. [LLM 决策与提示词编译](#13-llm-决策与提示词编译)
14. [变更提案与用户批准](#14-变更提案与用户批准)
15. [工作流与模型治理](#15-工作流与模型治理)
16. [运行状态与执行顺序](#16-运行状态与执行顺序)
17. [失败、重试与回滚](#17-失败重试与回滚)
18. [质量门](#18-质量门)
19. [Artifact 与 Delivery](#19-artifact-与-delivery)
20. [兼容性、能力与认证](#20-兼容性能力与认证)
21. [迁移规则](#21-迁移规则)
22. [示例](#22-示例)
23. [禁止事项](#23-禁止事项)

---

## 1. 协议定位

`CF-CRCP-0.1` 定义系列视频生产中的角色替身、Blender 控制素材、ComfyUI 创作重绘、参考资产、自由度、锁定边界、用户批准、失败回滚和连续性验收规则。

本协议允许：

- 使用无最终身份的 3D 角色作为动作替身。
- 使用用户选择的角色参考图替换替身的外观或身份。
- 在声明的范围内重新设计场景、材质、灯光和风格。
- 使用 LLM 编译镜头计划、提示词和工作流参数提案。
- 对同一动作和镜头生成多个明确标记的创作变体。
- 在用户批准后改变锁定项或生产假设。

本协议禁止：

- LLM 直接改变已批准的锁定项。
- 以“优化提示词”为名偷偷切换模型、工作流、角色或场景。
- 用相同自然语言提示词冒充角色和风格稳定性。
- 把 ComfyUI 的随机变化写回持久世界状态。
- 失败后无记录地重试、换路由或覆盖原始产物。
- 把 Blender 预演、mock、offline fallback 或局部探针结果伪装成正式成片。

## 2. 设计目标

本协议必须满足以下目标：

1. Blender 输出动作和空间事实，ComfyUI 输出可控的创作变化。
2. 每个自由度都能被声明、记录、复现和回退。
3. 用户可以知道本次生成保留了什么、改变了什么。
4. LLM 可以提出新的创作方向，但不能未经用户批准改变生产方向。
5. 角色替换不依赖原始替身的肌肉、服装或脸部轮廓。
6. 场景重绘可以改善免费素材的穿帮和风格不一致，同时保留镜头空间逻辑。
7. 同一 `Shot Control Bundle` 可以被不同 ComfyUI 工作流消费。
8. 更换模型或基座不得破坏控制包、规格快照和交付报告。
9. 每次失败都能定位到锁定项、自由项、控制素材、工作流或资源边界。
10. 协议的语义变更必须经过用户批准并通过版本化流程。

## 3. 规范关键词

本文使用以下关键词：

- MUST：必须。
- MUST NOT：不得。
- SHOULD：应当。
- SHOULD NOT：不应当。
- MAY：可以。

当中文规则与 JSON 示例存在差异时，以中文规范语义为准，JSON 示例只作为合法结构样例。

## 4. 版本治理与只读规则

### 4.1 权威文件

以下文件共同构成协议注册信息：

- `docs/protocol/CARTRIDGEFLOW_CREATIVE_RECAST_CONTROL_PROTOCOL_v0.1.md`：人类可读的规范正文。
- `protocol/CF-CRCP-0.1.json`：机器可读的协议注册。
- `protocol/profiles.json`：profile 词表。
- `protocol/capabilities.json`：capability 词表。

正文是本协议的规范来源。行动指南、卡带说明、提示词模板和实现代码不得反向改变本协议语义。

### 4.2 只读与追加式规则

1. `CF-CRCP@0.1` 发布后不得原地修改任何规范性规则。
2. 拼写、链接或不改变含义的排版修正必须明确标记为 editorial，并保留变更记录。
3. 增加、删除或改变锁定项、自由项、模式、质量门、回滚规则、工作流边界或用户批准条件，必须创建新的协议版本。
4. 新版本必须保留旧版本文件，不能把新含义写回 v0.1。
5. 已批准的 `CreativeSpec`、`ShotSpec`、`Shot Control Bundle` 和运行快照使用不可变 revision；修订必须产生新 revision。
6. 文件系统是否设置 DOS read-only 属性不影响本协议的只读语义；版本化和审计是强制机制。

### 4.3 无静默改变规则

每次执行或计划变更前，LLM、CartridgeFlow 和人工开发者 MUST 声明：

- 本次操作依据的协议版本和章节。
- 当前仍然有效的锁定项。
- 本次使用的自由项及其边界。
- 是否存在新的假设、工作流、模型或路由。
- 是否需要生成 `ChangeProposal`。

如果执行者无法判断一个想法是否改变了协议或已批准的生产方向，必须按需要变更处理并暂停请求用户批准，不得自行解释为“只是优化”。

## 5. 实体定义

### 5.1 CreativeSpec

一个镜头或一组镜头的创作规格，包含角色、世界、风格、锁定项、自由项、边界、参考资产和工作流白名单。

### 5.2 ShotSpec

单个镜头的时间、摄影机、动作、控制包、创作模式和交付要求。`ShotSpec` 必须引用一个已批准的 `CreativeSpec` revision。

### 5.3 Shot Control Bundle

由 Blender 或确定性处理器生成的镜头控制包，包含预演、姿态、深度、遮罩、背景结构和可复现 manifest。它是动作与创作层之间的稳定接口。

### 5.4 CastPack

角色身份、参考图、服装、发型、颜色、不可改变特征和许可来源的集合。

### 5.5 WorldPack

世界、场景、地标、建筑语言、光照和可变化布景的集合。

### 5.6 StylePack

模型、工作流、提示词模板、采样参数、色板、参考图和已知失败边界的集合。

### 5.7 ChangeProposal

对协议、批准规格、锁定项、工作流、模型或生产方向的结构化变更提案。提案不能自动生效。

### 5.8 Approval

由用户或明确授权的人工角色作出的批准、拒绝或要求修改。LLM 不能作为自己的批准人。

### 5.9 FailureRecord

描述一次失败、用户意见、实际变化、回滚目标和下一次建议的结构化记录。

### 5.10 RunSnapshot

一次运行实际使用的所有协议、规格、控制包、模型、工作流、seed、参数、输出和批准状态的不可变快照。

## 6. 与 CF-FARP 的关系

`CF-FARP@0.4` 继续负责：

- manifest、root flow 和节点模型。
- `executor`、`effect` 和工具副作用边界。
- AI `decision_envelope.v1`、显式消费和用户暂停恢复。
- Store、artifact、delivery、测试台和协议认证。

`CF-CRCP@0.1` 负责：

- `CreativeSpec`、`ShotSpec` 和控制包。
- 锁定项、自由项和模式边界。
- ComfyUI 模型与工作流白名单。
- 用户批准和变更提案。
- 创作质量门、失败分类和镜头级回滚。

采用两个协议的卡带 MUST 在 manifest 中声明：

```json
{
  "base_contract": { "id": "CF-FARP", "version": "0.4" },
  "protocol_extensions": [
    {
      "id": "CF-CRCP",
      "version": "0.1",
      "required_profiles": ["creative_control_runtime"],
      "required_capabilities": ["control_bundle_validate", "creative_approval_gate"]
    }
  ]
}
```

当前参考开发基座尚未声明支持 `CF-CRCP@0.1`，因此现阶段可以编写和审查协议合规的产物，但不得声称卡带已经获得 CRCP 认证或可移植运行。

## 7. 锁定项与自由项

### 7.1 显式字段

每个 `CreativeSpec` MUST 声明：

- `locked`：本次生成不得改变的路径列表。
- `free`：允许改变的路径列表。
- `bounds`：每个自由路径的范围、枚举或强度上限。
- `anchors`：用于连续性的参考图、地标、颜色或几何锚点。
- `approval`：批准 revision、批准人和时间。

路径必须使用稳定的点号路径，例如 `camera.motion`, `character.identity`, `world.materials`。不能使用“其他细节”这类无法验证的模糊字段。

### 7.2 默认保守规则

未声明为 `free` 的字段 MUST 视为 `locked`。缺少 `bounds` 的自由字段 MUST 阻断生产运行，除非当前模式明确是 `exploration` 且输出被标记为不可交付预览。

### 7.3 自由不是随机

自由项仍然必须受以下条件约束：

- 有明确的参考图、文本或参数来源。
- 有固定的 seed 或可解释的 seed 族规则。
- 能在 RunSnapshot 中重现。
- 输出必须标记实际改变的字段。
- 用户可以选择接受、拒绝或继续探索。

## 8. 创作模式

合法模式如下：

| 模式 | 默认锁定 | 默认自由 | 交付资格 |
| --- | --- | --- | --- |
| `conservative` | 动作、摄影机、场景结构、角色身份 | 材质、灯光、局部细节 | 可进入复核 |
| `character_replace` | 动作、摄影机、背景结构 | 角色身份、服装、发型、人物材质 | 可进入复核 |
| `creative_recast` | 动作、摄影机、时长、主要叙事构图 | 角色、场景、灯光、材质和风格 | 可进入复核 |
| `exploration` | 仅动作和时长 | 其他已声明字段 | 只能作为预览，不能直接交付 |

模式不是权限。每次运行仍必须生成实际的 `locked`、`free` 和 `bounds` 快照。卡带不得用模式名称推断未声明字段。

## 9. 首版生产基线

以下决定构成 `CF-CRCP@0.1` 的初始基线：

1. 当前男性 65 骨骼角色作为动作替身，不作为最终固定演员。
2. Blender 负责动作、走位、脚底接触、空间、摄影机和控制素材。
3. ComfyUI 可以重新设计场景，也必须具备完全替换角色的实验路径。
4. 角色替换的第一候选输入是姿态、深度、动态遮罩和角色参考图，不是替身的人物边缘。
5. 当前 RTX 3080 12GB 的第一候选工作流是 Wan2.1 VACE 1.3B。
6. 第一校准镜头是当前 2 至 3 秒走路镜头。
7. 第一轮必须对照“只换场景”“只换人物”“人物与场景一起换”。
8. Blender 原片永远保留为可检查和可交付的失败回退。
9. 改变以上任一决定都必须先产生 `ChangeProposal` 并等待用户批准。

## 10. Shot Control Bundle 契约

### 10.1 必须文件

每个镜头控制包 MUST 包含同 fps、同帧数、同宽高的：

| 文件 | 语义 | 要求 |
| --- | --- | --- |
| `preview.mp4` | Blender 预演和失败回退 | 可播放 |
| `character_mask.mp4` | 人物生成/保留区域 | 遮罩语义固定 |
| `depth.mp4` | 空间深度和遮挡 | 不改变前后关系 |
| `pose.mp4` 或姿态数据 | 骨骼运动 | 不编码替身肌肉外观 |
| `background_edges.mp4` | 背景结构 | 仅在场景模式启用 |
| `shot.json` | manifest 和复现参数 | schema 必须正确 |

角色参考图、世界参考图和中间控制图可以作为附加 artifact，但必须登记。

### 10.2 Manifest 最小结构

```json
{
  "schema": "cartridgeflow.shot_control_bundle.v1",
  "bundle_id": "pilot_01_walk_01.bundle",
  "revision": 1,
  "shot_id": "pilot_01_walk_01",
  "fps": 12,
  "frame_count": 33,
  "width": 480,
  "height": 832,
  "source": {
    "engine": "blender",
    "preview": "preview.mp4"
  },
  "controls": {
    "character_mask": "character_mask.mp4",
    "depth": "depth.mp4",
    "pose": "pose.mp4",
    "background_edges": "background_edges.mp4"
  },
  "mask_convention": {
    "white": "generate_or_replace",
    "black": "preserve_control_input"
  },
  "sha256": {},
  "status": "validated"
}
```

所有文件 MUST 写入 sha256 或等价内容哈希。控制包缺失、帧数不一致、遮罩语义未声明或 hash 未记录时，必须阻断 ComfyUI 运行。

## 11. CreativeSpec 契约

最小结构：

```json
{
  "schema": "cartridgeflow.creative_spec.v1",
  "spec_id": "pilot_01_recast",
  "revision": 1,
  "mode": "character_replace",
  "cast_pack": "cast.original_anime_male.v1",
  "world_pack": "world.suburban_daylight.v1",
  "style_pack": "style.polished_3d.v1",
  "locked": [
    "shot.motion",
    "shot.camera",
    "shot.timing",
    "world.landmarks",
    "character.contact_with_ground"
  ],
  "free": [
    "character.identity",
    "character.wardrobe",
    "character.hair",
    "character.material",
    "world.materials",
    "world.lighting"
  ],
  "bounds": {
    "world.lighting.color_temperature": [5000, 6500],
    "world.materials.variation": "bounded",
    "character.identity.reference_count": { "min": 1, "max": 4 }
  },
  "anchors": ["cast.main_reference", "world.house_facade", "shot.camera_path"],
  "allowed_workflows": ["wan21_vace_1_3b_character_replace"],
  "approval": {
    "status": "approved",
    "approved_by": "user",
    "approved_revision": 1
  }
}
```

`locked` 与 `free` 不得有交集。`free` 中的路径如果没有出现在 `bounds` 或被模式定义的固定枚举覆盖，验证器必须返回 blocker。

## 12. 资产包契约

### 12.1 CastPack

MUST 登记角色 ID、主参考图、可选多视角参考图、服装、发型、固定颜色、不可改变特征和许可来源。第一轮公开发布实验 SHOULD 使用原创或已授权角色。

### 12.2 WorldPack

MUST 登记世界 ID、建筑和道路语言、主要地标、光照要求、可变布景和不可变道具。

### 12.3 StylePack

MUST 登记模型文件 hash、workflow hash、提示词模板、负面约束、分辨率、帧数、步数、采样器、scheduler、seed 规则和已知失败边界。

资产包版本变化 MUST 产生新 revision。LLM 不得因为“更适合提示词”而替换资产包内的参考图。

## 13. LLM 决策与提示词编译

### 13.1 LLM 的权限

在 `CF-FARP@0.4` 中，创作决策节点 MUST 使用：

```json
{
  "type": "process",
  "kind": "decision",
  "executor": "llm",
  "effect": "none",
  "output_contract": "decision_envelope.v1"
}
```

LLM 可以：

- 从文本生成 `ShotSpec` 草案。
- 在已批准的 workflow allowlist 中提出工作流参数。
- 把用户意见编译成正向、负向和连续性约束。
- 生成 `FailureRecord` 和 `ChangeProposal` 草案。

LLM 不得：

- 直接写入控制包、资产包、持久世界状态或正式交付目录。
- 直接执行 ComfyUI、Blender 或其他有副作用工具。
- 自己批准自己的提案。
- 把新想法写进 `locked`、`free`、`bounds` 或 allowlist 而不暂停。

### 13.2 提示词分层

提示词 MUST 分为可审计的字段：

- `content_prompt`：镜头内容和叙事事实。
- `identity_prompt`：CastPack 的角色身份。
- `style_prompt`：StylePack 的风格和材质。
- `continuity_prompt`：上一镜头和本镜头的锚点。
- `negative_prompt`：已知失败和不可接受结果。

系统可以把这些字段编译成模型需要的自然语言，但必须保存编译前字段和编译后文本。

## 14. 变更提案与用户批准

### 14.1 必须提案的情况

以下变化 MUST 先暂停并请求用户批准：

- 改变首版生产基线。
- 修改任何 `locked` 字段。
- 把字段从 locked 移到 free，或反向移动。
- 放宽或收紧 `bounds`。
- 切换模型、workflow、采样器或控制信号类别。
- 从角色替换模式切换为创作模式，或反向切换。
- 改变失败后的默认回滚目标。
- 改变本协议、控制包或交付契约。

### 14.2 ChangeProposal 最小结构

```json
{
  "schema": "cartridgeflow.change_proposal.v1",
  "proposal_id": "crcp-proposal-0001",
  "protocol": "CF-CRCP@0.1",
  "reason": "当前人物边缘控制阻碍新角色体型替换。",
  "current": {
    "workflow": "wan21_vace_1_3b_v2v",
    "locked": ["character.silhouette"]
  },
  "proposed": {
    "workflow": "wan21_vace_1_3b_character_replace",
    "locked": ["character.pose", "character.contact_with_ground"]
  },
  "affected_locks": ["character.silhouette"],
  "expected_benefit": "允许动漫角色使用不同体型，同时保留动作。",
  "cost_and_risk": "需要新增姿态和动态遮罩控制，可能增加显存与调试时间。",
  "rollback": "回到 CreativeSpec revision 1 和原 VACE workflow。",
  "question": "是否批准这项受控变更？",
  "status": "pending_user"
}
```

### 14.3 批准语义

合法状态：`pending_user`、`approved`、`rejected`、`superseded`。

- 只有用户明确批准才能进入 `approved`。
- `approved` 必须绑定新 revision、批准人和时间。
- 用户拒绝不得被解释成“稍后自动重试”。
- 没有批准时，执行器只能展示提案和已有结果，不能继续改变生产路径。

## 15. 工作流与模型治理

### 15.1 Allowlist

每个 StylePack MUST 声明 `allowed_workflows` 和 `allowed_models`。生产运行只能使用白名单中的组合。

### 15.2 当前 3080 基线

当前首选候选为 Wan2.1 VACE 1.3B。`480x832`、17 帧短测和 33 帧镜头测是当前可复现基线。14B、量化模型、offload 或其他视频模型都属于新提案，不是隐式升级路径。

### 15.3 参数快照

每次运行 MUST 保存模型 hash、workflow hash、seed、steps、cfg、scheduler、分辨率、帧数、显存基线、峰值显存、耗时和输出 hash。模型缓存或 ComfyUI 默认值不得替代显式快照。

## 16. 运行状态与执行顺序

CRCP 生产运行状态：

```text
draft
 -> awaiting_user_approval
 -> approved
 -> control_ready
 -> running_blender
 -> running_comfy
 -> review_required
 -> accepted | rejected | blocked
```

`rejected` 必须保存 `FailureRecord` 和 `rollback_target`。`blocked` 表示无法安全继续，不得自动转成 `rejected` 或 `accepted`。

执行顺序 MUST 为：

1. 读取并校验 protocol、CreativeSpec、Pack 和 Shot Control Bundle。
2. 生成待批准的有效规格快照。
3. 获得用户批准后锁定 RunSnapshot。
4. 运行 Blender 控制和确定性校验。
5. 运行 allowlist 中的 ComfyUI workflow。
6. 保存原片、增强片、参数和报告。
7. 进入用户复核，不自动发布。

## 17. 失败、重试与回滚

### 17.1 FailureRecord

标准标签包括：

- `motion_reversed`
- `surrogate_leak`
- `identity_drift`
- `scene_drift`
- `temporal_flicker`
- `contact_error`
- `style_mismatch`
- `resource_limit`
- `control_bundle_invalid`
- `unapproved_change`

每次失败 MUST 记录失败镜头、运行 revision、标签、用户意见、实际参数、输出位置、回滚目标和建议变更。

### 17.2 重试边界

重试 MAY 修改已声明的 free 字段，但必须增加 retry index 并列出 changed fields。重试不得修改 locked 字段、模型、workflow 或模式，除非已有 `ChangeProposal` 获得批准。

### 17.3 回滚边界

回滚必须回到最近一个稳定 revision。失败产物保留为审计 artifact，不得被新结果覆盖。ComfyUI 失败时默认回退到 Blender `preview.mp4`，并标记为 `fallback_preview`。

## 18. 质量门

### 18.1 技术门

- 控制包文件齐全、hash 正确、帧率和帧数一致。
- ComfyUI 成功返回并生成可播放文件。
- 输出分辨率、fps、时长和 spec 一致。
- 无未记录的 OOM、断帧、静默 fallback 或并发运行。

### 18.2 动作门

- 人物屏幕位移方向正确。
- 脚步接触与控制包一致。
- 摄影机运动、构图和主要遮挡关系没有突然跳变。

### 18.3 角色门

- 角色在首帧、中段和末帧可辨认。
- 发型、服装、颜色和体型没有无解释变化。
- 替身外观没有残留到被声明为可替换的区域。

### 18.4 连续性门

- 建筑、道路、地标和关键道具不会逐帧生长、消失或换位。
- 灯光方向和色温在镜头内连续。
- 片段连接保留上一片段的延续锚点。

### 18.5 用户门

- 用户能看到保留项和自由项。
- 用户能看到本次实际改变的字段。
- 用户明确接受或拒绝当前 artifact。
- 用户拒绝后可以选择原片、重试 free 字段或提交 ChangeProposal。

## 19. Artifact 与 Delivery

每次运行 MUST 输出：

- `RunSnapshot`。
- Blender 原片和控制包 manifest。
- ComfyUI workflow 与模型参数报告。
- 正向、负向和编译后的提示词。
- 增强视频或明确的 `fallback_preview`。
- 用户批准、复核和 FailureRecord。

交付节点 MUST 区分：

- `preview`：探索或未通过质量门的预览。
- `candidate`：通过技术门，等待用户接受。
- `primary`：用户接受并允许进入后续剪辑的主视频。
- `fallback`：ComfyUI 失败时的 Blender 原片。

任何被标记为 `primary` 的视频都必须能追溯到批准的 CreativeSpec revision。

## 20. 兼容性、能力与认证

### 20.1 必需能力

实现 `CF-CRCP@0.1` 的基座至少需要声明：

```text
control_bundle_v1
control_bundle_validate
creative_spec_v1
creative_mode_policy
creative_workflow_allowlist
creative_change_proposal
creative_approval_gate
creative_run_snapshot
creative_failure_record
creative_quality_gates
creative_artifact_audit
```

### 20.2 兼容性检查

检查器 MUST 检查：

- 协议注册和文档路径。
- companion protocol 是否为 `CF-FARP@0.4`。
- required profiles 和 capabilities。
- locked/free 是否有交集。
- free 是否有 bounds。
- workflow 和 model 是否在 allowlist。
- 控制包帧率、帧数、分辨率和 hash。
- ChangeProposal 是否获得用户批准。
- RunSnapshot 是否完整。
- delivery artifact 是否可追溯。

blocker 存在时不得运行生产路径，也不得添加 CRCP 认证标签。

### 20.3 当前基座状态

当前参考开发基座只支持 `CF-FARP@0.4`，尚未支持 `CF-CRCP@0.1` 的运行、兼容性和认证能力。因此本协议本次作为规范和人工执行约束发布，不能声称机器已经完成 CRCP 认证。

## 21. 迁移规则

1. 不得修改 `CF-FARP@0.4` 或其历史文件。
2. 现有 `DIGITAL_SURROGATE_COMFYUI_COMPLEMENT_ACTION_PLAN.md` 降级为非规范实施指南。
3. 新卡带在采用 CRCP 时，必须保留 `CF-FARP@0.4` 作为运行协议，并增加 `protocol_extensions`。
4. 现有卡带不因本协议自动改变模式、模型、角色或工作流。
5. 新的 `CreativeSpec`、控制包和资产包从 revision 1 开始，不覆盖旧运行产物。
6. 基座实现完成前，协议只能用于人工检查和产物结构化，不得添加认证标签。
7. CRCP 的破坏性修改必须创建 `CF-CRCP@0.2` 或更高版本，并保留 v0.1。

## 22. 示例

### 22.1 只换人物的有效自由度

```json
{
  "mode": "character_replace",
  "locked": [
    "shot.motion",
    "shot.camera",
    "shot.timing",
    "world.landmarks",
    "character.pose",
    "character.contact_with_ground"
  ],
  "free": [
    "character.identity",
    "character.wardrobe",
    "character.hair",
    "character.material"
  ],
  "bounds": {
    "character.identity": "CastPack reference images only",
    "character.material": "StylePack bounded variation"
  }
}
```

### 22.2 需要用户批准的模型切换

```json
{
  "schema": "cartridgeflow.change_proposal.v1",
  "proposal_id": "crcp-proposal-model-0001",
  "change_type": "workflow_or_model",
  "current": "wan2.1_vace_1_3b",
  "proposed": "wan2.1_14B_SCAIL_2_fp16.safetensors",
  "reason": "需要更强的身份替换能力。",
  "risk": ["12GB VRAM 不确定", "耗时增加", "新模型未通过基准"],
  "status": "pending_user"
}
```

`proposed` 中的字符串仅为示意，真实实现必须使用已登记的 workflow/model ID。

## 23. 禁止事项

1. 禁止原地改变 `CF-CRCP@0.1` 的规范语义。
2. 禁止 LLM 未经批准修改 locked、free、bounds、mode 或 allowlist。
3. 禁止以用户一句模糊意见推断用户已经批准模型或工作流切换。
4. 禁止把 prompt 自由度当作角色身份锁定。
5. 禁止用人物 Canny 轮廓强行替代姿态、深度和遮罩控制。
6. 禁止覆盖失败产物或隐藏 fallback。
7. 禁止在没有 RunSnapshot 的情况下生成 primary artifact。
8. 禁止用未声明资产、未登记模型或未授权角色进入公开交付。
9. 禁止因为单个卡带方便而放宽协议验证。
10. 禁止协议、行动指南和 LLM 临时想法同时作为同等级的规范来源。

协议当前的第一项实施目标是：生成一个可校验的 `Shot Control Bundle`，并以用户批准的 `CreativeSpec` 完成三组对照实验。实验结果只能推动新的 ChangeProposal，不能自动改变本协议的基线。
