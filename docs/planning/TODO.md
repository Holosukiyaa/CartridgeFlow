# CartridgeFlowLite TODO

## P0 - 个人产品交付闭环

- [ ] `PRODUCT-001` 定义 `Product Delivery Contract v1`：将卡带的主产物、附件、质量门槛、交付状态、revision 与可复现运行证据收敛为协议和运行时事实；运行成功不再等同于产品已交付。
- [ ] `PRODUCT-002` 实现产品运行记录与产物视图：同一次运行的主产物、附件、摘要、来源卡带版本、输入版本、Runner、耗时、失败/重试和下载记录必须可追溯；“再次运行”创建新 revision，不能覆盖既有交付物。
- [ ] `PRODUCT-003` 实现个人版本地/云端 Runner 放置策略：用户可看见数据去向、外部调用与成本归属；本地资源和敏感输入默认不因云端运行而被静默上传。
已完成：`DIST-001` 已发布 `CF-CRE@1` 正文、机器快照、发布清单轨道、发行候选包构建和静态归档 conformance；当前状态为 `partial`，不宣称签名验签、安装器、资源重绑定、激活或市场已实现。
已完成：`DIST-001A` 已新增开发台使用指南，明确开发导出包、发行候选包和未来可安装发行包的边界，并给出发行构建器的操作与接入顺序。

## P0 - 编排语义基线

- [x] `ORCH-001` 固化 `ExecutionPlan v1`：定义 `sequence`、`fork`、`join(all/any/keyed)`、`loop`、`batch`、`wait` 和 `failure` 的可执行语义，清理当前画布、协议分析和运行器之间不一致的 `action_route`、`failure_route`、循环与合流行为；协议、确定性编译、Token 运行器及工程视图投影已完成。`CF-FARP@1.0` 仍为 draft/unsupported，工程投影不等同于运行支持；验收见 [n8n 编排取经与差异化报告](../architecture/N8N_ORCHESTRATION_BENCHMARK_REPORT.md)。

## P1 - 当前主线

- [ ] `ENG-021` 实施工程视图资源化表达与节点信息层级，覆盖外部 MCP 连接详情、资源画布节点、节点类别标识、可拖拽资源和按内容自适应的卡片布局；验收要求见 [工程视图资源化任务书](./ENGINEERING_VIEW_RESOURCE_TASK_BRIEF.md)。
- [ ] `ORCH-002` 以编译产物 `ExecutionPlan` 和运行期 token 替换一次性队列调度；支持可恢复的多次节点执行、确定性调度与 checkpoint 对齐。
- [ ] `ORCH-003` 建立类型化端口和值引用模型，记录 schema、producer、lineage、digest 和敏感级别；限制共享 `store` 只作为运行缓存，不能再承担隐式数据流语义。
- [ ] `ORCH-004` 实现卡带内子 Flow：固定 `id + version + interface digest`，具备显式输入/输出、effect 与权限契约，禁止 URL、任意 JSON 或跨卡带动态加载。
- [ ] `ORCH-005` 将 Probe/TestBench 升级为 fixtures、局部执行依赖闭包、脱敏输出快照、产物/副作用断言和可控回放。
- [ ] `ORCH-006` 把正常、失败、补偿和人工恢复线路统一投影到画布与运行 trace；每条副作用线路必须显示权限、重试、确认和回滚边界。
- [ ] `DIST-002` 实现个人运行台发行闭环：依照 [个人运行台发行与安装架构](../architecture/PERSONAL_RUNTIME_DISTRIBUTION_ARCHITECTURE.md) 分阶段交付 Release Builder、暂存安装/资源重绑定/版本回滚，以及免费精选市场桥接；发行包不携带密钥、私有 URL、本机路径、日志、Store、检查点或用户产物。

## 后续预研

遗留接口适配的 `ADAPT-001`、`ADAPT-002` 及其验收保留在 [n8n 编排取经与差异化报告](../architecture/N8N_ORCHESTRATION_BENCHMARK_REPORT.md)。它们不是当前个人运行台发行闭环的并行实现任务。
