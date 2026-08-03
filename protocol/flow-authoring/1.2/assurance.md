# CF-FARP@1.1 - Compatibility and certification

This file is a normative module of CF-FARP@1.1. The release is defined only by the same-version modules listed in README and CARTRIDGEFLOW-BASE@0.3.

## 32. 兼容性报告

兼容性报告 MUST 检查：

- Base Contract 是否满足。
- CF-FARP@1.1 是否注册并被 Base 支持。
- required profiles/capabilities/tool packs 是否满足。
- required model/resource roles 是否绑定。
- Manifest 与 Root Flow 是否合法。
- Asset Registry、稳定引用、hash、media type 和悬空引用是否合法。
- Interaction Component Registry、mode、allowed action、schema 和等待契约是否一致。
- passive HTML 是否无主动内容；sandboxed component 的 descriptor v2、脚本闭包、CSP、channel 和 Host capability 是否满足。
- permission、dependency 和 delivery readiness 是否满足。
- DLC descriptor、hash、scope、Worker 和 sandbox 是否满足。

存在 blocker 时不得运行或认证。

兼容性报告最小结构：

```json
{
  "ok": false,
  "status": "blocked",
  "base_contract": {
    "required": "CARTRIDGEFLOW-BASE@0.3",
    "implemented": "CARTRIDGEFLOW-BASE@0.3",
    "supported": true
  },
  "protocol": {
    "required": "CF-FARP@1.1",
    "supported": true,
    "lifecycle": "supported",
    "migration_target": null
  },
  "profiles": {},
  "capabilities": {},
  "models": {},
  "resources": {},
  "tools": {},
  "permissions": {},
  "dependencies": {},
  "flow_contract": {},
  "assets": {},
  "interaction_components": {},
  "script_security": {},
  "portable_dlc": {},
  "portability": {
    "packaged": [],
    "local_binding_required": [],
    "missing_blockers": [],
    "forbidden": []
  },
  "delivery_readiness": {},
  "findings": []
}
```

finding severity：

- blocker：禁止运行和认证。
- warning：可以按声明开发/预览，但禁止认证；必须显示影响。
- info：可选能力或诊断信息。

### 32.1 Portability Report

开发卡带打包、导出、安装预检和升级前 MUST 生成 portability report，并把发现项稳定分为：

- `packaged`：Root Flow、模型配方、prompt、schema、动效模板、卡带 UI、允许分发的媒体、组件、DLC 代码和测试。
- `local_binding_required`：模型 Provider、工具实例、URL、key、credential、command、用户路径和其他由目标 Base 重新绑定的本机能力。
- `missing_blockers`：被引用但不存在、hash/media type 不匹配、required role 未声明、component/action/schema 不完整或目标 Base 缺少 required capability。
- `forbidden`：凭据、本机绝对路径、未声明脚本、主动 HTML 普通资产、越权 dependency、包外符号链接、未授权网络目标和其他禁止随包传播内容。

报告必须列出每项来源文件或声明、引用者、ownership、迁移处理和稳定 finding code。存在 `missing_blockers` 或 `forbidden` 时不得生成可安装包。仅把敏感字符串替换为空值不等于可迁移；卡带必须保留角色/配方要求，目标 Base 再显式绑定。

旧协议如果位于 Base 历史索引，必须报告 recognized_unsupported_protocol 和迁移目标；未知协议报告 unknown_protocol。不得用当前 v1.1 解释器静默运行旧版本。

## 33. 认证

`cf-farp-1-1-certified` 要求：

1. Base Contract 与 Runtime Contract 均合法。
2. Root Flow 声明 v1.1。
3. 兼容性报告无 blocker 和 warning。
4. 所有 AI decision 具有合法 envelope 与 consume。
5. 所有 required tools 具有完整 contract。
6. 所有 required resource roles 在认证环境完成绑定或被认证夹具明确替代。
7. 错误、恢复、副作用重放和 primary output 门禁通过。
8. DLC 卡带通过作用域、隔离、hash、停用、卸载和无残留测试。
9. Asset Registry、Interaction Component、被动 HTML 和脚本安全检查全部通过。
10. 每个 interaction action 的合法提交、非法 action、schema 失败、重复提交、刷新恢复和 revision 冲突均有证据。
11. portability report 没有 missing blocker 或 forbidden package content。
12. 所有节点使用结构化 inputs、outputs 与 binding，required 数据在所有可达路径上可证明可用。
13. `execution_plan` 与 derived engineering relations 已隔离，Runner 只消费计划边且有 conformance 证据。
14. production/publish Analysis Report 完整、无 blocker、target 匹配且 source digest 新鲜。
15. fallback、Analyzer finding、analysis freshness 和 Authoring API revision conflict 的正向与失败测试通过。
16. 标签只能由认证工具写入。

```json
{
  "protocol_certification": {
    "status": "certified",
    "label": "cf-farp-1-1-certified",
    "protocol": "CF-FARP",
    "protocol_version": "1.1"
  }
}
```

认证报告必须引用实际 Base Implementation、协议 registry/正文 hash、Manifest/Root Flow hash、capability evidence、测试环境、工具/DLC hash 和测试结果。手工勾选清单不能替代机器报告。

认证只覆盖声明的卡带版本、协议版本、能力集合和测试环境。修改 Root Flow、required capability、工具 contract、DLC files、permission、Artifact/Delivery 语义后必须重新认证。

真实外部服务未验证时必须标记 external_unverified。mock、fixture 和 dry-run 可以证明结构路径，但不能证明真实外部质量或稳定性。

## 34. Capability 词表

v1.1 的完整核心能力词表包括：

```text
manifest_load
manifest_validate
runtime_contract_parse
compatibility_report
root_flow_execution
basic_node_execution
unified_process_node
multi_input_node
runtime_input_node
process_node_kind_parse
process_executor_contract
process_effect_contract
transfer_process
retrieval_process
decision_process
mcp_read_process
mcp_execute_process
remote_call_process
gate_process
process_mcp_readonly_binding
tool_plan_emit
tool_plan_validate
tool_plan_tool_binding
decision_envelope_v1
decision_envelope_validate
decision_consume_contract
decision_consume_projection
llm_live_mode
llm_mock_mode
llm_offline_fallback
runtime_user_input_request
paused_waiting_user_status
pending_interaction_record_v2
runtime_resume_after_user_input
node_display_name
package_asset_registry
stable_asset_reference
interaction_component_registry
interaction_node
interaction_named_action_routes
passive_html_safety
sandboxed_interaction_component
interaction_script_csp
interaction_network_guard
interaction_process_isolation
interaction_host_channel
interaction_host_capability_guard
cartridge_portability_report
builtin_tool_call
remote_tool_call
artifact_collect
artifact_preview
data_chain_diagnostics
optional_input
delivery_readiness_check
probe_run
testbench_run
structure_analysis
protocol_display_mapping
portable_dlc_descriptor
portable_dlc_validate
cartridge_scoped_tool_registry
isolated_dlc_worker
dlc_worker_json_rpc
cartridge_protocol_overlay
frontend_dlc_sandbox
package_owned_code
dlc_activation_lifecycle
dlc_uninstall_cleanup
dlc_absence_verification
dlc_resource_ownership
dlc_artifact_retention_policy
dlc_integrity_hash
runtime_error_envelope_v1
runtime_state_machine
checkpoint_persistence
runtime_retry_policy
runtime_checkpoint_resume
runtime_rollback
runtime_restart
side_effect_replay_guard
worker_lifecycle_supervision
model_recipe_binding
local_resource_binding
resource_preflight
artifact_revision
artifact_provenance
artifact_invalidation
delivery_primary_output_guard
structured_io_contract
explicit_input_binding
typed_control_edges
executable_topology_filter
normalized_topology_projection
flow_analysis_report_v1
flow_source_digest
flow_analysis_target_gates
analysis_report_freshness_guard
derived_engineering_relations
dataflow_static_analysis
branch_data_availability_analysis
resource_dependency_analysis
policy_static_analysis
finding_contract_v1
authoring_api_contract
safe_autofix_contract
fallback_visibility_contract
flow_resource_catalog_v1
resource_origin_tracking
node_resource_binding_preflight
explicit_node_model_binding
silent_model_fallback_guard
authoring_model_scope_isolation
```

Base MUST 只声明已实现并有证据的能力。没有声明某能力不等于协议删除该能力，而是该 Base 只能支持不要求该能力的 v1.1 卡带。
