from __future__ import annotations

from .flow_contract import SIDE_EFFECT_EFFECTS


REQUIRED_TOOL_PLAN_FIELDS = {"schema", "tool_id", "params", "expected_output", "failure_policy"}


def validate_tool_plan(plan: dict | None, manifest: dict | None, node: dict | None = None) -> list[dict]:
    findings: list[dict] = []
    plan = plan if isinstance(plan, dict) else {}
    manifest = manifest if isinstance(manifest, dict) else {}
    node = node if isinstance(node, dict) else {}

    if plan.get("schema") != "tool_plan.v1":
        findings.append(_finding("blocker", "tool_plan_schema_invalid", "tool_plan schema must be tool_plan.v1."))

    for field in sorted(REQUIRED_TOOL_PLAN_FIELDS):
        value = plan.get(field)
        if field not in plan or value is None or value == "":
            findings.append(_finding("blocker", f"tool_plan_{field}_missing", f"tool_plan.{field} is required."))

    tool_id = str(plan.get("tool_id") or "").strip()
    manifest_tools = {
        str(tool.get("id")): tool
        for tool in manifest.get("mcp_tools") or []
        if isinstance(tool, dict) and tool.get("id")
    }
    if tool_id and tool_id not in manifest_tools:
        findings.append(_finding("blocker", "tool_plan_tool_not_declared", f"tool_id is not declared in manifest.mcp_tools: {tool_id}"))

    allowed_tools = _allowed_tools(node)
    if allowed_tools and tool_id and tool_id not in allowed_tools:
        findings.append(_finding("blocker", "tool_plan_tool_not_allowed", f"tool_id is not allowed by current process node: {tool_id}"))

    if tool_id in manifest_tools:
        tool = manifest_tools[tool_id]
        findings.extend(_validate_plan_params(plan.get("params"), tool.get("params_schema"), tool_id))
        findings.extend(_validate_plan_effect(plan, tool, node, tool_id))

    return findings


def _validate_plan_params(params, schema, tool_id: str) -> list[dict]:
    findings: list[dict] = []
    if not isinstance(params, dict):
        return [_finding("blocker", "tool_plan_params_invalid", "tool_plan.params must be an object.")]
    if not isinstance(schema, dict) or not schema:
        return findings
    if schema.get("type") and schema.get("type") != "object":
        return [_finding("blocker", "tool_params_schema_unsupported", f"params_schema for {tool_id} must be an object schema.")]

    properties = schema.get("properties") if isinstance(schema.get("properties"), dict) else {}
    required = schema.get("required") if isinstance(schema.get("required"), list) else []
    for field in required:
        if field not in params:
            findings.append(_finding("blocker", "tool_plan_required_param_missing", f"tool_plan.params missing required field for {tool_id}: {field}"))
    for field, value in params.items():
        field_schema = properties.get(field)
        if isinstance(field_schema, dict):
            expected_type = field_schema.get("type")
            if expected_type and not _value_matches_type(value, expected_type):
                findings.append(_finding("blocker", "tool_plan_param_type_invalid", f"tool_plan.params.{field} does not match schema type {expected_type}."))
        elif schema.get("additionalProperties") is False:
            findings.append(_finding("blocker", "tool_plan_additional_param_forbidden", f"tool_plan.params.{field} is not allowed by params_schema."))
    return findings


def _validate_plan_effect(plan: dict, tool: dict, node: dict, tool_id: str) -> list[dict]:
    node_effect = str(node.get("effect") or _nested(node, "params", "effect") or "").strip()
    side_effect = str((tool.get("contract") or {}).get("side_effect") or "").strip().lower()
    side_effecting_tool = any(token in side_effect for token in ["write", "mutate", "artifact", "file", "state", "publish", "external", "remote"])
    if side_effecting_tool and node_effect not in SIDE_EFFECT_EFFECTS:
        return [_finding("blocker", "tool_plan_effect_conflict", f"tool {tool_id} has side effects but current node effect is {node_effect or 'missing'}.")]
    return []


def _allowed_tools(node: dict) -> list[str]:
    raw = node.get("allowed_tools")
    if raw is None and isinstance(node.get("params"), dict):
        raw = node["params"].get("allowed_tools")
    if isinstance(raw, str):
        return [item.strip() for item in raw.replace("\r", "\n").replace(",", "\n").split("\n") if item.strip()]
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()]
    return []


def _value_matches_type(value, expected_type) -> bool:
    if isinstance(expected_type, list):
        return any(_value_matches_type(value, item) for item in expected_type)
    if expected_type == "string":
        return isinstance(value, str)
    if expected_type == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected_type == "boolean":
        return isinstance(value, bool)
    if expected_type == "object":
        return isinstance(value, dict)
    if expected_type == "array":
        return isinstance(value, list)
    if expected_type == "null":
        return value is None
    return True


def _nested(data: dict, *keys: str):
    current = data
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _finding(severity: str, code: str, message: str) -> dict:
    return {"severity": severity, "code": code, "message": message}
