# CartridgeFlow 下一阶段 TODO

## 0. 当前基准：CF-FARP@0.3

文档版本：0.3  
目标协议：CF-FARP-0.3  
目标基座：cartridgeflow.reference-dev  
编制日期：2026-07-17  
文档状态：执行清单  

当前基座声明为 `CF-FARP@0.3 partial`。已经落地：

- `CF-FARP@0.3` 正式协议正文。
- 机器可读协议注册。
- profile / capability 词表。
- v0.3 flow contract checker。
- compatibility / certification 接入。
- `decision_envelope.v1` 解析与校验。
- AI 决策节点 mock / live / offline fallback 结果标记。
- `needs_user_input` 触发 `paused_waiting_user`。
- pending interaction 记录。
- 测试台识别暂停节点和等待用户输入状态。
- 后端根据 pending interaction answer 写入 store 并按 `resume.policy` 继续执行。
- 测试台回答 pending interaction 并继续轮询。
- 设计台编辑 `decision_contract`、`decision_test_mode`、`mock_decision_envelope`。
- `runtime_resume_after_user_input` 已在 `BASE_IMPLEMENTATION.json` 声明。

恢复策略说明：当前支持 `resume_same_node`、`resume_next_node`、`resume_target_node`。`restart_run_with_inputs` 仍然拒绝自动执行，因为它可能重放已执行过的文件写入、远程调用等不可重复副作用节点。

下一步 P0：

- [x] 实现安全恢复调度器：从 pending interaction 写入 store 后，根据 `resume.policy` 继续执行。
- [x] 恢复执行时重建已完成父节点集合，避免多入边节点被错误卡住。
- [x] 增加测试台回答 pending interaction 的 UI。
- [x] 通过 conformance 后，在 `BASE_IMPLEMENTATION.json` 增加 `runtime_resume_after_user_input`。
- [ ] 对 `restart_run_with_inputs` 增加可审计的副作用重放风险检测，或继续保持显式拒绝。

---

## 历史计划：CF-FARP@0.2

文档版本：0.2  
目标协议：CF-FARP-0.2  
目标基座：cartridgeflow.reference-dev  
编制日期：2026-07-16  
文档状态：执行清单  

本文用于指导下一阶段开发：把已经成型的协议分层模型落到开发基座与 `dev.pixel_episode_director` 中。

本文不是协议正文，不替代以下文件：

- `docs/protocol/CARTRIDGEFLOW_BASE_CONTRACT_v0.1.md`
- `docs/protocol/CARTRIDGEFLOW_FLOW_AUTHORING_RUNTIME_PROTOCOL_v0.1.md`
- `docs/protocol/CARTRIDGEFLOW_FLOW_AUTHORING_RUNTIME_PROTOCOL_v0.2.md`
- `docs/protocol/agent.md`

后续实现必须遵守协议文件。若实现过程中发现协议确实不足，必须走版本化协议变更，不得为了某一个流程直接改基座边界。

---

## 目录

1. 当前结论
2. 下一阶段目标
3. 工作原则
4. 当前状态
5. P0：v0.2 协议检查器
6. P0：v0.2 兼容性与认证
7. P0：运行时节点适配
8. P0：tool_plan 与 MCP 执行边界
9. P1：开发台 UI 分层显示
10. P1：Flow Assistant 升级
11. P1：重写 dev.pixel_episode_director
12. P1：v0.2 基座声明
13. P2：生产基座分离
14. 测试与验收
15. 禁止事项
16. 推荐执行顺序

---

## 1. 当前结论

当前项目已经完成了 v0.1 规范化的第一轮落地，并新增了 v0.2 协议草案。当前开发基座已经进入 `CF-FARP@0.2 partial` 支持状态。

当前状态应理解为：

- `CF-FARP v0.1`：当前开发基座声明为 `partial`，已有 compatibility report、certification report、optional input、协议注册表和 conformance tests。
- `CF-FARP v0.2`：协议正文、机器可读注册表、flow contract checker、tool_plan 校验、certification 接入和最小运行时适配已经建立；当前开发基座声明为 `partial`。
- `dev.pixel_episode_director`：当前是 v0.1 认证样本，不应直接宣称 v0.2 认证。

下一阶段的核心不是继续扩协议，而是把 v0.2 的分层模型落到可检查、可运行、可认证的基座能力中。

v0.2 的关键决策是：

```text
用户层：处理节点 + 后缀
协议层：type=process + kind + executor + effect
```

因此后续工作必须同时满足：

- 用户不需要理解一堆硬节点类型。
- 基座必须能严格检查节点真实行为。
- AI 决策不得直接执行副作用。
- MCP 不强制绑定 AI。
- 有副作用的 MCP 执行必须通过权限、schema、tool_plan 或等价结构校验。

---

## 2. 下一阶段目标

### 2.1 第一目标

实现 v0.2 协议检查器，使系统能够判断一个 root flow 是否符合：

```json
{
  "type": "process",
  "kind": "decision",
  "executor": "llm",
  "effect": "none"
}
```

以及对应的输入、输出、工具、权限和副作用约束。

### 2.2 第二目标

升级 compatibility / certification，使系统能回答：

- 当前基座是否支持 `CF-FARP@0.2`。
- 卡带是否要求 v0.2。
- 每个业务节点是否声明 `kind`、`executor`、`effect`。
- `kind` / `executor` / `effect` 的组合是否合法。
- tool_plan 是否被执行前校验。
- MCP 只读和 MCP 执行是否被正确区分。
- 卡带是否可以写入 `cf-farp-0-2-certified` 标签。

### 2.3 第三目标

让运行时能执行 v0.2 的 `type=process` 节点，同时兼容旧 v0.1 / legacy 节点。

### 2.4 第四目标

重写 `dev.pixel_episode_director` 为 v0.2 压力样本，但不得让它反向污染协议。

---

## 3. 工作原则

### 3.1 先检查，后认证

没有 v0.2 检查器前，不得给任何卡带写入 v0.2 认证标签。

### 3.2 先适配，后改卡带

不要直接把 `dev.pixel_episode_director/root.flow.json` 改成 `type=process` 后再让运行时临时救火。必须先让运行时具备解释 v0.2 节点的能力。

### 3.3 用户层与协议层分离

UI 可以显示：

```text
处理节点-AI决策
处理节点-MCP执行
```

但运行时不得依赖显示名称判断行为，必须读取：

```text
type / kind / executor / effect
```

### 3.4 v0.1 不再吸收 v0.2 语义

v0.1 文件只作为历史合同和已认证卡带解释来源。后续新增动态决策、多输入、MCP 执行边界，应落在 v0.2 或后续版本。

### 3.5 基座声明必须保守

`BASE_IMPLEMENTATION.json` 只有在对应 conformance tests 通过后，才允许声明支持 v0.2 capability。

---

## 4. 当前状态

### 4.1 已有资产

- `docs/protocol/CARTRIDGEFLOW_FLOW_AUTHORING_RUNTIME_PROTOCOL_v0.2.md`
- `protocol/CF-FARP-0.2.json`
- `protocol/capabilities.json`
- `core/protocol/compatibility.py`
- `core/protocol/certification.py`
- `tests/conformance/test_protocol_v02_registry.py`
- `docs/protocol/agent.md`
- `skills/cartridgeflow-protocol-upgrader/`

### 4.2 当前缺口

- v0.2 已经具备 partial 支持，但仍不是 production-ready。
- compatibility checker 已接入 v0.2 flow contract，但还需要更多真实卡带 fixture 覆盖。
- certification checker 已接入 v0.2 flow contract，但还未跑通真实 `dev.pixel_episode_director` 的 v0.2 认证。
- runner / node executor 已有最小 v0.2 process adapter，但还需要在复杂真实流程中验证。
- Flow Assistant 仍有旧的 `input/process/tool` 分类提示。
- `dev.pixel_episode_director` 仍是 v0.1 结构。
- 生产基座尚未分离。

---

## 5. P0：v0.2 协议检查器

目标：新增独立检查层，专门检查 root flow 是否符合 v0.2 节点统一模型。

建议新增文件：

```text
core/protocol/node_contracts.py
core/protocol/flow_contract.py
tests/conformance/test_protocol_v02_node_contract.py
```

### TODO

- [x] 定义 v0.2 允许的 `kind`：
  - `input`
  - `transfer`
  - `retrieval`
  - `decision`
  - `transform`
  - `validation`
  - `routing`
  - `mcp_read`
  - `mcp_execute`
  - `remote_call`
  - `gate`
  - `ui`
  - `human_gate`
  - `delivery`
- [x] 定义 v0.2 允许的 `executor`：
  - `user`
  - `deterministic`
  - `rules`
  - `rag`
  - `llm`
  - `mcp`
  - `remote`
  - `human`
  - `plugin`
- [x] 定义 v0.2 允许的 `effect`：
  - `none`
  - `read_only`
  - `writes_store`
  - `writes_artifacts`
  - `writes_files`
  - `mutates_state`
  - `external_side_effect`
- [x] 检查所有业务节点必须是 `type=process`。
- [x] 允许 `system`、`terminal` 作为生命周期节点，但不得归入业务节点。
- [x] 检查每个 `type=process` 节点必须声明 `kind`、`executor`、`effect`。
- [x] 检查 `kind=input` 必须声明：
  - `input_kind`
  - `source`
  - `output`
  - `input_schema` 或等价 schema 来源
- [x] 检查 `kind=transfer` 只能：
  - `executor=deterministic`
  - `effect=writes_store`
  - 不调用 LLM
  - 不调用 MCP
  - 不写 artifact / file / persistent state
- [x] 检查 `kind=retrieval` 只能产生 `none`、`read_only` 或 `writes_store`。
- [x] 检查 `kind=decision` 如果驱动工具，必须输出 `tool_plan.v1` 或协议等价结构。
- [x] 检查 `kind=mcp_read` 必须：
  - `executor=mcp`
  - `effect=read_only`
  - 声明 `mcp_binding.mode=read_only`
  - 绑定的工具 contract 不得有副作用
- [x] 检查 `kind=mcp_execute` 必须：
  - `executor=mcp`
  - `effect` 高于 `read_only`
  - 声明 `tool_binding`
  - 声明 `allowed_tools`
  - 声明失败策略
- [x] 检查 `kind=gate` 必须输出结构化通过/失败结果。
- [x] 检查 `kind=delivery` 不得引用未产出的 required output。

### 验收标准

- [ ] 不合规节点能产生明确 finding。
- [ ] finding 至少包含 `severity`、`code`、`node_id`、`message`。
- [ ] v0.1 legacy flow 不应被误判为 v0.2 合规。
- [ ] v0.2 最小样例 flow 可以通过检查。

---

## 6. P0：v0.2 兼容性与认证

目标：让 compatibility / certification 正式理解 v0.2，而不是只知道协议已注册。

改造文件：

```text
core/protocol/compatibility.py
core/protocol/certification.py
tests/conformance/test_protocol_v02_certification.py
```

### TODO

- [x] 当 manifest 要求 `CF-FARP@0.2`，compatibility report 必须检查基座是否声明支持 v0.2。
- [x] 当前基座未声明 v0.2 时，要求 v0.2 的普通运行必须 blocker。
- [ ] 开发兼容模式可以允许检查和调试，但必须标记：
  - `mode=development_compatibility`
  - `certifiable=false`
- [x] certification report 必须调用 v0.2 flow contract checker。
- [x] v0.2 认证必须检查：
  - manifest 声明 `base_contract`
  - manifest 声明 `runtime_contract`
  - manifest 声明 `delivery_readiness`
  - root flow 声明 `CF-FARP@0.2`
  - 所有业务节点 `type=process`
  - 所有 process 节点声明 `kind/executor/effect`
  - tool_plan 执行前校验
  - 有副作用 effect 声明权限和日志要求
- [x] 新增 `cf-farp-0-2-certified` 标签写入逻辑。
- [x] 认证接口必须拒绝 warning 和 blocker。
- [x] 认证接口不得因为 v0.1 认证存在而自动给 v0.2 认证。

### 验收标准

- [ ] 要求 v0.2 但基座不支持时，compatibility 返回 blocker。
- [ ] v0.2 flow 缺少 `effect` 时，certification 返回 blocker。
- [ ] v0.2 flow 有 `kind=mcp_execute` 但缺少 `allowed_tools` 时，certification 返回 blocker。
- [ ] 只有完全通过的 v0.2 卡带才能写入 `cf-farp-0-2-certified`。

---

## 7. P0：运行时节点适配

目标：让 runner / node executor 能执行 v0.2 的 `type=process` 节点，同时不破坏旧 flow。

建议新增文件：

```text
core/cartridge/node_normalizer.py
tests/conformance/test_protocol_v02_runtime_adapter.py
```

### TODO

- [x] 新增节点规范化层，把旧节点和 v0.2 节点转为统一内部执行描述。
- [ ] 支持旧节点：
  - `type=ui`
  - `type=runtime`
  - `type=user_gate`
  - `type=terminal`
- [x] 支持 v0.2 节点：
  - `type=process`
  - `kind=input`
  - `kind=ui`
  - `kind=transfer`
  - `kind=retrieval`
  - `kind=decision`
  - `kind=mcp_read`
  - `kind=mcp_execute`
  - `kind=gate`
  - `kind=delivery`
- [x] 明确 v0.2 节点的执行入口字段，例如：
  - `action`
  - `executor`
  - `params.preset`
  - `params.preset_config`
  - `tools`
- [x] `kind=input` 映射到当前 `collect_inputs` 能力。
- [x] `kind=ui` 映射到当前 `show_ui` 能力。
- [x] `kind=transfer` 映射到确定性数据整理能力，不得调用工具。
- [x] `kind=mcp_read` 映射到只读工具调用，执行前校验工具 contract。
- [x] `kind=mcp_execute` 映射到有副作用工具调用，执行前校验权限、allowed_tools、schema。
- [x] `kind=decision` 初期可以支持规则 / 静态 / LLM 三种 executor，但必须禁止直接工具副作用。
- [x] 旧 flow 继续走 legacy adapter。

### 验收标准

- [ ] 旧 v0.1 卡带仍可运行。
- [ ] v0.2 最小 flow 可以运行。
- [ ] v0.2 `kind=transfer` 节点调用工具会被拒绝。
- [ ] v0.2 `kind=decision` 节点直接写文件会被拒绝。

---

## 8. P0：tool_plan 与 MCP 执行边界

目标：实现 AI 决策到 MCP 执行之间的安全桥。

建议新增文件：

```text
core/protocol/tool_plan.py
tests/conformance/test_tool_plan_v1.py
```

### TODO

- [x] 定义 `tool_plan.v1` 最小 schema。
- [x] 实现 `validate_tool_plan(plan, manifest, node)`。
- [x] 校验 `tool_id` 必须存在于 manifest `mcp_tools`。
- [x] 校验 `tool_id` 必须被当前 `kind=mcp_execute` 节点 `allowed_tools` 允许。
- [x] 校验 `params` 符合工具 `params_schema`。
- [x] 校验工具 contract 的 `side_effect` 与节点 `effect` 不冲突。
- [x] 校验 `failure_policy` 必须存在。
- [ ] 执行前写入审计日志摘要。
- [x] AI 输出 tool_plan 失败时必须 fail closed，不得自动执行工具。

### 验收标准

- [ ] tool_plan 缺少 `tool_id` 被拒绝。
- [ ] tool_plan 请求未允许工具被拒绝。
- [ ] tool_plan 参数不符合 schema 被拒绝。
- [ ] read-only 节点执行有副作用工具被拒绝。
- [ ] 通过校验的 tool_plan 可以交给 `kind=mcp_execute` 执行。

---

## 9. P1：开发台 UI 分层显示

目标：让用户看到统一处理节点，但开发者能查看协议字段。

改造范围：

```text
frontend/src/pages/flow-workbench/nodeModel.ts
frontend/src/pages/flow-workbench/types.ts
frontend/src/pages/flow-workbench/views.tsx
frontend/src/pages/flow-workbench/FlowGraphView.tsx
frontend/src/pages/flow-workbench/TestBenchView.tsx
```

### TODO

- [ ] UI 节点标题显示为“处理节点 + 后缀”。
- [ ] 后缀来自 `kind` 或 `display.suffix`。
- [ ] 详情面板展示协议字段：
  - `type`
  - `kind`
  - `executor`
  - `effect`
  - `tool_binding`
  - `allowed_tools`
- [ ] 对高副作用节点显示醒目标记：
  - `writes_artifacts`
  - `writes_files`
  - `mutates_state`
  - `external_side_effect`
- [ ] TestBench 显示 v0.2 flow contract findings。
- [ ] legacy flow 显示为 legacy，不伪装成 v0.2。

### 验收标准

- [ ] 普通用户看到的是“处理节点-AI决策”，不是复杂协议字段。
- [ ] 开发者可以展开查看 `kind/executor/effect`。
- [ ] UI 不用显示名称驱动运行逻辑。

---

## 10. P1：Flow Assistant 升级

目标：让 AI 搭流程时遵守 v0.2，而不是继续生成旧的 `input/process/tool` 分类。

改造文件：

```text
core/lab/flow_assistant_llm.py
core/lab/steward_llm.py
```

### TODO

- [ ] 修改系统提示词，明确用户层统一为“处理节点 + 后缀”。
- [ ] 生成节点时使用 `type=process`。
- [ ] 生成节点时必须补充 `kind`、`executor`、`effect`。
- [ ] 不再要求“process 后面必须挂 tool 节点”作为唯一模式。
- [ ] MCP 只读生成 `kind=mcp_read`。
- [ ] MCP 有副作用生成 `kind=mcp_execute`。
- [ ] AI 决策生成 `kind=decision`，并通过 `tool_plan.v1` 驱动执行。
- [ ] Flow Assistant 输出前调用 v0.2 flow contract checker。
- [ ] 如果检查不通过，自动修正一次；仍不通过则返回结构化错误，不直接应用。

### 验收标准

- [ ] 用户要求“读取资料”时生成 `处理节点-MCP检索` 或 `处理节点-资料检索`。
- [ ] 用户要求“写文件/渲染/发布”时生成 `处理节点-MCP执行`。
- [ ] 用户要求“让 AI 决定下一步”时生成 `处理节点-AI决策`，不是直接工具执行。

---

## 11. P1：重写 dev.pixel_episode_director

目标：把 `dev.pixel_episode_director` 重写为 v0.2 首个压力样本。

当前卡带可以作为经验参考，但不得把旧结构原样升级为“看起来合规”。

### 11.1 Manifest TODO

- [ ] 修改 `base_contract` 为 `CF-FARP@0.2`。
- [ ] 修改 `runtime_contract.protocol_version` 为 `0.2`。
- [ ] 增加 v0.2 required capabilities：
  - `unified_process_node`
  - `process_node_kind_parse`
  - `process_executor_contract`
  - `process_effect_contract`
  - `multi_input_node`
  - `tool_plan_validate`
  - `tool_plan_tool_binding`
- [ ] 暂不写入 `cf-farp-0-2-certified`，直到认证检测通过。
- [ ] 保留 v0.1 认证历史时必须放在历史记录字段，不得与当前认证混淆。

### 11.2 Root Flow TODO

- [ ] 将业务节点统一为 `type=process`。
- [ ] `start` / `complete` 等生命周期节点保留 `system` / `terminal`。
- [ ] 每个业务节点补充：
  - `kind`
  - `executor`
  - `effect`
  - `display.suffix`
- [ ] 把当前入料节点改为：
  - `kind=input`
  - `executor=user`
  - `effect=writes_store`
- [ ] 把资料入库调度改为：
  - `kind=transfer`
  - `executor=deterministic`
  - `effect=writes_store`
- [ ] 把文件读取类节点改为：
  - `kind=mcp_read`
  - `executor=mcp`
  - `effect=read_only`
- [ ] 把素材组装、上下文包整理改为：
  - `kind=retrieval` 或 `kind=transfer`
  - 根据是否读取外部资料区分 effect
- [ ] 把导演/制片/决策类节点改为：
  - `kind=decision`
  - `executor=llm` 或 `rules`
  - `effect=none`
  - 输出 `tool_plan.v1` 或结构化决策
- [ ] 把渲染、关键帧提取、ComfyUI、Godot、FFmpeg、世界状态回写改为：
  - `kind=mcp_execute`
  - `executor=mcp`
  - `effect=writes_artifacts` / `writes_files` / `mutates_state`
  - 声明 `allowed_tools`
- [ ] 把校验节点改为：
  - `kind=gate`
  - `executor=rules`
  - `effect=none` 或 `writes_store`
- [ ] 把交付汇总节点改为：
  - `kind=delivery`
  - `executor=deterministic`
  - `effect=writes_store`

### 11.3 流程收敛 TODO

- [ ] 删除或隔离无意义探索支线。
- [ ] 每个保留支线必须声明：
  - 是否进入主链
  - 是否 isolated
  - 是否 optional
  - 失败是否阻断交付
- [ ] 保留当前资产和工具能力，但把职责拆清楚。
- [ ] 不再新增“看起来有用但没有交付贡献”的节点。
- [ ] 为每个模块定义明确产物：
  - 入料
  - 资料包
  - 决策计划
  - 执行产物
  - 质检报告
  - 交付包

### 11.4 验收标准

- [ ] `dev.pixel_episode_director` 要求 `CF-FARP@0.2`。
- [ ] compatibility report 无 blocker。
- [ ] certification report 无 blocker / warning。
- [ ] 可写入 `cf-farp-0-2-certified`。
- [ ] TestBench 可跑通主链。
- [ ] 输出产物仍包含像素短剧核心交付结果。

---

## 12. P1：v0.2 基座声明

目标：在实现和测试通过后，谨慎声明当前开发基座支持 v0.2。

改造文件：

```text
BASE_IMPLEMENTATION.json
```

### TODO

- [x] 在 conformance tests 通过前，不修改 `supported_protocols`。
- [x] v0.2 runtime adapter 通过后，加入：

```json
{
  "id": "CF-FARP",
  "version": "0.2",
  "status": "partial"
}
```

- [x] 加入 `dynamic_decision_runtime` profile。
- [x] 只声明已经测试通过的 capabilities。
- [x] 更新 `conformance.passed_cases`。
- [x] 保持 `status=partial`，直到生产基座和完整认证流程完成。

### 验收标准

- [ ] `python -m unittest discover -s tests\conformance` 通过。
- [ ] `BASE_IMPLEMENTATION.json` 不声明未注册 capability。
- [ ] v0.2 样例卡带可以通过 compatibility。
- [ ] v0.1 卡带未被破坏。

---

## 13. P2：生产基座分离

目标：把真实交付给用户的运行环境从开发环境中拆出。

本阶段不立即执行，但前面所有实现必须为它留边界。

### TODO

- [ ] 定义 production base 最小 profile。
- [ ] 生产基座只支持协议运行，不依赖 FlowWorkbench。
- [ ] 生产基座只读取卡带包、manifest、root flow、runtime contract、assets。
- [ ] 生产基座能运行 v0.2 certified cartridge。
- [ ] 生产基座拒绝 dev-only capability。
- [ ] package 内写入 compatibility snapshot 和 certification snapshot。

### 验收标准

- [ ] 同一个 v0.2 certified cartridge 可以在开发基座和生产基座运行共同支持的部分。
- [ ] 生产基座不需要搭流程能力。
- [ ] 生产基座不需要测试台能力。

---

## 14. 测试与验收

### 14.1 每轮修改必须运行

```powershell
python -m json.tool protocol\CF-FARP-0.2.json | Out-Null
python -m json.tool protocol\capabilities.json | Out-Null
python -m unittest discover -s tests\conformance
```

### 14.2 修改 Python 核心后必须运行

```powershell
python -m py_compile core\protocol\*.py core\cartridge\*.py core\lab\*.py server\main.py
```

### 14.3 修改前端后必须运行

```powershell
cd frontend
npm run build
```

### 14.4 v0.2 最小新增测试

- [ ] v0.2 registry 存在。
- [ ] 当前基座未声明 v0.2 时，要求 v0.2 的卡带被 blocker。
- [ ] v0.2 最小合法 flow 通过 node contract。
- [ ] 缺少 `kind` 被 blocker。
- [ ] 缺少 `executor` 被 blocker。
- [ ] 缺少 `effect` 被 blocker。
- [ ] `kind=transfer` 调 MCP 被 blocker。
- [ ] `kind=decision` 直接执行副作用被 blocker。
- [ ] `kind=mcp_read` 绑定有副作用工具被 blocker。
- [ ] `kind=mcp_execute` 缺少 `allowed_tools` 被 blocker。
- [ ] tool_plan 请求未允许工具被 blocker。
- [ ] v0.1 卡带仍然通过原有测试。

---

## 15. 禁止事项

- [ ] 禁止把 `CF-FARP@0.2` 加入 `BASE_IMPLEMENTATION.json` 后再补实现。
- [ ] 禁止把 `dev.pixel_episode_director` 直接贴上 v0.2 认证标签。
- [ ] 禁止为了跑通某个流程降低 effect 等级。
- [ ] 禁止用 UI 后缀替代协议字段。
- [ ] 禁止让 AI 决策节点直接写文件、移动文件、渲染、发布或回写状态。
- [ ] 禁止把只读 MCP 和有副作用 MCP 混成一个执行规则。
- [ ] 禁止修改 v0.1 协议含义来吸收 v0.2。
- [ ] 禁止让 Flow Assistant 继续生成旧的“process 后挂 tool”作为唯一合法结构。

---

## 16. 推荐执行顺序

建议严格按以下顺序推进：

1. 实现 v0.2 node / flow contract checker。
2. 给 checker 加 conformance tests。
3. 把 checker 接入 compatibility report。
4. 把 checker 接入 certification report。
5. 实现 `tool_plan.v1` 校验。
6. 实现 v0.2 runtime node adapter。
7. 更新开发台 UI 的“处理节点 + 后缀”显示。
8. 更新 Flow Assistant 生成规则。
9. 用 v0.2 重写 `dev.pixel_episode_director`。
10. 跑完整 conformance tests。
11. 确认无 blocker / warning 后，再写入 v0.2 认证标签。
12. 最后把 `BASE_IMPLEMENTATION.json` 声明升级为 v0.2 partial。

核心判断标准：

```text
先让基座能判断什么是合规，再让基座运行合规流程，最后才让卡带申请认证。
```
