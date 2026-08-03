# CF-TUNING@1.0

状态：`active`
实现状态：`supported`

本目录是 CF-TUNING@1.0 的完整独立发布单元。它只能在宿主 CF-FARP 发布显式信任且 Base 精确支持时使用，不从任何历史版本补足语义。

## 1. 定位

CF-TUNING 管理 Root Flow 之外的内部效果调优和配方版本。Root Flow 继续拥有节点身份、执行契约与拓扑；本协议只拥有节点局部参数修订、配方发布快照和物化来源。

## 2. 调优仓库

仓库 schema 为 `cartridgeflow.tuning_repository.v1`，必须包含协议身份、宿主 Flow 身份、单调递增仓库 revision、节点头、不可变修订、不可变发布和活动发布指针。

允许 patch 字段为：`title`、`display_name`、`description`、`experience`、`params`、`timeout_ms`、`model_role`、`agent`、`endpoint`、`tools`、`input_binding`、`inputs`、`outputs`。实现可以进一步收窄，但不得扩大到拓扑、执行器、权限或代码字段。

`experience` 使用完整对象 schema `cartridgeflow.node_experience.v1`，拥有该节点面向普通用户的阶段文案、可见性、输入字段呈现、操作标签、物料投影、结果与失败文案，以及开发者显式开放的安全参数。输入字段只能装饰既有输入契约，不能新增运行输入；数字和选择控件必须随发布固定范围、步长或选项。它只能描述普通用户投影，不得改变 executor、effect、permission、路由或运行结果。开放参数必须使用稳定参数名，禁止开放凭据、可执行字段、Prompt、工具绑定或本机路径。

每个修订必须包含稳定 ID、node ID、父修订、Flow 源摘要、完整 patch、作者、原因和时间。修订 ID 必须由内容摘要派生或被内容摘要保护。

## 3. 发布快照

发布 schema 为 `cartridgeflow.tuning_release.v1`，必须包含：发布 ID、序号、状态 `published`、Flow 身份与摘要、节点修订映射、每个节点的完整 patch、发布时间、发布人和发布摘要。发布摘要覆盖除摘要字段自身外的规范化文档。

发布文档不得包含开发历史、废弃修订或秘密。已发布文档不可原地修改。

## 4. 物化

物化从未修改的 Root Flow 副本开始，按 node ID 应用发布中固定的完整 patch。未知节点、非法字段、Flow 摘要变化或发布摘要变化必须失败关闭。物化后必须产生 `materialization_digest` 并重新运行宿主协议校验。

## 5. 版本操作

创建修订使用乐观并发的 `expected_head`。发布固定当时所有节点头。激活和回滚只改变活动发布指针。任何 API 不得修改既有修订或发布内容。

当 Root Flow 摘要变化但已调优节点仍存在时，开发者显式发布 MAY 为该节点创建只更新 Flow 摘要、完整继承原 patch 且保留父修订的 carry-forward 修订；不得原地改写旧修订，也不得在打开、运行或普通保存时静默执行。

## 6. 运行来源

运行开始时必须把发布 ID、Flow 摘要、节点修订映射、发布摘要和物化摘要复制到 Run snapshot。活动发布之后的变化不得影响已开始运行。

## 7. 安全

仓库与发布不得出现密码、secret、token、API key、Authorization、cookie、私钥、凭据值或本机绝对路径。资源引用必须使用稳定角色或本机配置引用。子协议不得新增可执行内容或修改宿主拓扑。

## 8. 一致性

符合实现必须证明：非法字段被拒绝、并发冲突被拒绝、发布不可变、回滚保留历史、摘要篡改被拒绝、未发布草稿不进入普通运行、运行来源可追溯。
