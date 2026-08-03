# CF-FARP@1.1

状态：`active`
实现状态：`supported`
依赖 Base Contract：`CARTRIDGEFLOW-BASE@0.3`

本目录是 CF-FARP@1.1 的完整规范发布单元。实现、验证和认证只应读取本目录列出的规范模块、同目录的 `release.json`、`profiles.json`、`capabilities.json`，以及明确声明的 Base Contract；不得从任何早期 CF-FARP 正文补足语义。

## 规范模块

- [概览与术语](overview.md)
- [包与资源](package-and-resources.md)
- [流程与数据](flow-and-data.md)
- [运行与恢复](runtime-and-recovery.md)
- [扩展与生命周期](extensions-and-lifecycle.md)
- [兼容性与认证](assurance.md)
- [规范治理](governance.md)
- [创作与静态分析](authoring-and-analysis.md)
- [统一 Flow 资源目录](flow-resources.md)
- [工具透明执行](tool-transparency.md)
- [显式执行计划](execution-plan.md)
- [受信任调优与配方版本](tuning-and-releases.md)
- [一致性要求](conformance.md)

## 非规范迁移资料

[迁移资料](migration.md) 只描述历史卡带如何显式转换为本版本；它不为 CF-FARP@1.1 增加、删除或解释运行时语义。

## 机器工件

- `release.json`：发布身份、Base 依赖和规范入口。
- `profiles.json`、`capabilities.json`：本版本的词表快照。
- `trusted_subprotocols`：本版本允许 Base 在不污染 Root Flow 语义的前提下解析的受信任内部子协议。
