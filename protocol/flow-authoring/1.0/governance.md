# CF-FARP@1.0 - Specification governance

This file is a normative module of CF-FARP@1.0. The release is defined only by the same-version modules listed in README and CARTRIDGEFLOW-BASE@0.2.

## 40. 规范追踪与演进

### 40.1 条款追踪

Base 声明的每个 capability MUST 映射到实现入口、正向测试、适用的失败测试和 UI 可见性或 not_applicable 说明。协议认证还必须把关键 MUST/MUST NOT 条款映射到 conformance case。

最低追踪域：

- Manifest 与本机秘密隔离。
- Root Flow 与 Process Node。
- Asset Registry、Interaction Component 与稳定引用。
- 被动 HTML 检查、脚本闭包、CSP、sandbox、Host channel 与 capability guard。
- Decision Envelope 与 Consume。
- Pending Interaction。
- Tool Contract、permission、failure 和 replay。
- Runtime Error、状态迁移与 Checkpoint。
- Artifact revision、provenance、invalidation 和 Delivery。
- DLC descriptor、scope、Worker、sandbox、Overlay、ownership 和卸载。

### 40.2 协议完整性

未来 v1.0 文案修正不得改变规范语义。新增 required 字段、状态、生命周期、副作用、所有权或安全边界必须发布新的完整协议版本。

新版本必须：

1. 自包含，不要求读取旧正文补足含义。
2. 提供目录、完整实体和字段契约。
3. 提供前一版本条款处置矩阵。
4. 明确保留、替代和废止项。
5. 同步机器 registry、版本化 capability/profile vocabulary 与规范 conformance；Base Implementation 必须如实保持 unsupported，直到实现、失败路径和运行 conformance 完成后才加入支持矩阵。
6. 对旧版本给出 recognized/unsupported/unknown 与迁移策略。

### 40.3 实现与协议边界

实现 bug 修复、性能改进、UI 优化和新增符合既有宿主接口的本机资源实例，不要求新协议版本。改变可移植卡带的公开含义时，必须先更新协议版本，不能只改代码和测试。
