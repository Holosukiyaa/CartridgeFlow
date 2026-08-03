# CF-FARP@1.1 - Trusted tuning and recipe releases

This file is a normative module of CF-FARP@1.1. The release is defined only by the same-version modules listed in README, CARTRIDGEFLOW-BASE@0.3, and the explicitly trusted CF-TUNING@1.0 registry.

## 1. 信任声明

CF-FARP@1.1 信任 `CF-TUNING@1.0` 作为 `authoring_tuning` 子协议。该信任只允许对子协议声明的节点局部字段做确定性物化，不允许子协议新增、删除节点，修改 `execution_plan`，改变节点 `type`、`kind`、`executor`、`effect` 或注入可执行代码。

Manifest MUST 声明：

```json
{
  "tuning_contract": {
    "protocol": "CF-TUNING",
    "protocol_version": "1.0",
    "release_entry": "tuning/release.json"
  }
}
```

开发态可以尚未生成 `release_entry`；production、package 与 publish 目标必须存在通过校验的发布快照。

## 2. 两级版本

节点调优修订固定单个节点的允许字段、父修订、Flow 源摘要、作者、原因和时间。配方发布固定 Flow 源摘要以及每个节点采用的调优修订。两者一经创建都不可变。

发布后产生的新节点修订不得改变现有普通用户版本。只有创建并激活新的配方发布，普通用户运行时才消费新参数。

## 3. 物化与运行

Base 必须从原始 Root Flow 的副本开始物化。调优 patch 使用允许字段的浅层替换；`params` 作为完整对象替换，不允许通过路径表达式穿透到未授权字段。物化结果必须再次经过 CF-FARP Analyzer 和资源预检。

节点局部 `experience` 由受信任的 CF-TUNING 发布拥有。Base 必须把它作为非执行性的普通用户投影随节点修订和配方发布固定；普通用户界面只能消费活动发布中的投影，不得读取未发布草稿，也不得根据该投影改变路由、权限或执行语义。

开发测试可以消费显式标记为 `draft` 的节点头；打包、安装和普通运行只能消费 `published` 发布快照。运行记录至少包含：

- `protocol` 与 `protocol_version`；
- `recipe_release_id` 与发布摘要；
- `flow_digest`；
- `node_revisions`；
- `materialization_digest`。

## 4. 激活与回滚

激活操作只修改活动发布指针。回滚是把指针切换到一个既有发布，不得删除后续发布、重写节点修订或伪造相同 ID 的新内容。运行开始后必须继续使用已固定的发布身份，不能跟随活动指针变化。

## 5. 秘密与布局

调优仓库和发布快照不得保存凭据值、Authorization header、私有 token 或本机绝对路径。可以保存稳定的资源角色或凭据引用。普通用户的个人画布布局不是配方效果事实，不进入配方发布；开发者共享的说明性布局必须与运行语义分离。

## 6. 失败关闭

以下情况必须阻断物化、打包或运行：未知子协议、宿主协议未信任、Base 未支持、Flow 摘要不匹配、修订不存在、节点不存在、非法 patch 字段、秘密字段、发布摘要错误或发布文档被修改。
