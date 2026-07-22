from __future__ import annotations

from copy import deepcopy


V02_KIND_ACTIONS = {
    "input": "collect_inputs",
    "ui": "show_ui",
    "interaction": "render_interaction",
    "human_gate": "confirm_checkpoint",
    "decision": "llm_prompt",
    "transfer": "pass_result",
    "retrieval": "custom_action",
    "transform": "custom_action",
    "validation": "custom_action",
    "routing": "custom_action",
    "gate": "custom_action",
    "delivery": "pass_result",
    "mcp_read": "tool_call",
    "mcp_execute": "tool_call",
    "remote_call": "remote_call",
}

CONTRACT_FIELDS = {
    "kind",
    "executor",
    "effect",
    "input",
    "output",
    "output_contract",
    "input_kind",
    "source",
    "input_schema",
    "tool_binding",
    "allowed_tools",
    "mcp_binding",
    "failure_policy",
    "permission",
    "audit_log",
    "primary_output",
    "decision_contract",
    "decision_test_mode",
    "mock_decision_envelope",
    "display_name",
    "component_ref",
    "interaction_mode",
    "input_binding",
    "action_routes",
}


def normalize_runtime_node(state: dict) -> dict:
    """Return a runtime-facing copy of a root-flow node.

    CF-FARP v0.2 business nodes use type=process plus kind/executor/effect.
    The current lab executor still dispatches by action, so this adapter maps
    protocol-level process kinds to existing runtime actions without changing
    legacy nodes.
    """
    if not isinstance(state, dict):
        return {}
    normalized = deepcopy(state)
    if normalized.get("type") != "process":
        return normalized

    params = dict(normalized.get("params") or {})
    protocol_params = dict(params.get("protocol") or {})
    preset_config = dict(params.get("preset_config") or {})

    for field in CONTRACT_FIELDS:
        if field in normalized and field not in params:
            params[field] = normalized[field]
        if field in protocol_params and field not in params:
            params[field] = protocol_params[field]

    kind = str(params.get("kind") or normalized.get("kind") or "").strip()
    executor = str(params.get("executor") or normalized.get("executor") or "").strip()
    action = normalized.get("action") or V02_KIND_ACTIONS.get(kind) or "custom_action"

    if kind == "decision" and executor and executor != "llm":
        action = normalized.get("action") or "custom_action"

    if kind in {"mcp_read", "mcp_execute"}:
        allowed_tools = _string_list(params.get("allowed_tools"))
        binding = params.get("mcp_binding") if isinstance(params.get("mcp_binding"), dict) else {}
        if not allowed_tools:
            allowed_tools = _string_list(binding.get("allowed_tools"))
        if allowed_tools and not preset_config.get("mcp_tool_id"):
            preset_config["mcp_tool_id"] = allowed_tools[0]
        if not preset_config.get("output_name") and params.get("output"):
            preset_config["output_name"] = params.get("output")

    if kind == "input":
        if not preset_config.get("output_name") and params.get("output"):
            preset_config["output_name"] = params.get("output")
        schema = params.get("input_schema")
        if isinstance(schema, dict) and not preset_config.get("fields"):
            fields = schema.get("fields")
            if isinstance(fields, list):
                preset_config["fields"] = ",".join(str(item) for item in fields if str(item).strip())

    if kind == "delivery" and not params.get("output") and params.get("primary_output"):
        params["output"] = params["primary_output"]

    if preset_config:
        params["preset_config"] = preset_config
    normalized["params"] = params
    normalized["action"] = action
    protocol_version = (
        params.get("protocol_version")
        or protocol_params.get("version")
        or normalized.get("protocol_version")
        or "0.2"
    )
    normalized["_protocol_runtime"] = {
        "protocol": f"CF-FARP@{protocol_version}",
        "kind": kind,
        "executor": executor,
        "effect": str(params.get("effect") or normalized.get("effect") or "").strip(),
        "mapped_action": action,
    }
    return normalized


def _string_list(value) -> list[str]:
    if isinstance(value, str):
        return [item.strip() for item in value.replace("\r", "\n").replace(",", "\n").split("\n") if item.strip()]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []
