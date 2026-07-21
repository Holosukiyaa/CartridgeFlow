"""Resolve portable cartridge resource roles against machine-owned resources."""

from __future__ import annotations

import os
from copy import deepcopy

from core.studio.resources import load_resources


TOOL_KIND_ALIASES = {"remote": "remote_api"}
PRIVATE_CONNECTION_FIELDS = {
    "endpoint",
    "command",
    "args",
    "openapi_url",
    "auth_env",
    "location",
    "format",
    "refresh_mode",
}


class LocalResourceBindingError(ConnectionError):
    pass


def resolve_cartridge_resources(
    manifest: dict,
    resources: dict | None = None,
    configured_keys: set[str] | None = None,
) -> dict:
    manifest = manifest if isinstance(manifest, dict) else {}
    resources = resources if isinstance(resources, dict) else load_resources()
    cartridge_id = str(manifest.get("id") or "").strip()
    requirements = manifest.get("resource_requirements") if isinstance(manifest.get("resource_requirements"), list) else []
    role_bindings = (((resources.get("bindings") or {}).get("roles") or {}).get(cartridge_id) or {})
    resource_index = _resource_index(resources)
    available_keys = _configured_keys(configured_keys)
    role_summaries = {}
    items = []

    for raw_requirement in requirements:
        if not isinstance(raw_requirement, dict):
            continue
        role = str(raw_requirement.get("role") or "").strip()
        if not role:
            continue
        required = raw_requirement.get("required", True) is not False
        accepted_kinds = {_normalize_kind(item) for item in _string_list(raw_requirement.get("kinds"))}
        required_capabilities = set(_string_list(raw_requirement.get("capabilities")))
        constraints = raw_requirement.get("constraints") if isinstance(raw_requirement.get("constraints"), dict) else {}
        resource_id = str(role_bindings.get(role) or "").strip()
        resource = resource_index.get(resource_id)
        state = "ready"
        message = "本机资源已绑定"
        credential_state = "not_required"
        ready = True

        if not resource_id:
            state, message, ready = "missing_binding", "没有绑定本机资源", False
        elif resource is None or resource.get("enabled") is False:
            state, message, ready = "missing_resource", "绑定的本机资源不存在或已停用", False
        elif accepted_kinds and _normalize_kind(resource.get("kind")) not in accepted_kinds:
            state, message, ready = "incompatible_kind", "本机资源类型不符合角色要求", False
        else:
            connection_error = _connection_error(resource)
            actual_capabilities = set(_string_list(resource.get("capabilities")))
            if connection_error:
                state, message, ready = "missing_connection", connection_error, False
            elif required_capabilities and not required_capabilities.issubset(actual_capabilities):
                state, message, ready = "capability_mismatch", "本机资源缺少角色要求的能力", False
            elif constraints.get("read_only") is True and resource.get("read_only") is not True:
                state, message, ready = "capability_mismatch", "角色要求只读资源", False
            else:
                auth_env = str(resource.get("auth_env") or "").strip().upper()
                if auth_env:
                    credential_state = "configured" if auth_env in available_keys else "missing"
                    if credential_state == "missing":
                        state, message, ready = "missing_credential", f"缺少本机变量 {auth_env}", False
                if ready and _normalize_kind(resource.get("kind")) in {"mcp", "remote_api", "plugin", "web", "structured"}:
                    state, message = "external_unverified", "静态条件满足，外部连通性尚未验证"

        severity = "warning"
        if ready and state == "ready":
            status, severity = "ok", "info"
        elif ready:
            status = "warning"
        elif required:
            status, severity = "blocked", "blocker"
        else:
            status = "warning"

        summary = {
            "resource_id": resource_id,
            "kind": _normalize_kind((resource or {}).get("kind")),
            "ready": ready,
            "state": state,
            "credential_state": credential_state,
        }
        role_summaries[role] = summary
        items.append({
            "id": role,
            "role": role,
            "required": required,
            "resource_id": resource_id,
            "kind": summary["kind"],
            "state": state,
            "status": status,
            "severity": severity,
            "message": message,
        })

    statuses = {item["status"] for item in items}
    status = "blocked" if "blocked" in statuses else "warning" if "warning" in statuses else "ok"
    descriptor = {
        "schema": "cartridgeflow.local_bindings.v1",
        "cartridge_id": cartridge_id,
        "contains_secrets": False,
        "roles": role_summaries,
    }
    return {"status": status, "items": items, "descriptor": descriptor}


def resolve_runtime_tool_binding(
    run: dict,
    tool_id: str,
    resources: dict | None = None,
    configured_keys: set[str] | None = None,
) -> dict | None:
    manifest_tool = next(
        (item for item in run.get("mcp_tools") or [] if isinstance(item, dict) and str(item.get("id") or "") == str(tool_id or "")),
        None,
    )
    if not manifest_tool:
        raise LocalResourceBindingError(f"Manifest tool does not exist: {tool_id}")
    role = str(manifest_tool.get("resource_role") or "").strip()
    if not role:
        return None

    manifest = {
        "id": run.get("cartridge_id"),
        "resource_requirements": run.get("resource_requirements") or [],
    }
    resources = resources if isinstance(resources, dict) else load_resources()
    current = resolve_cartridge_resources(manifest, resources, configured_keys)
    current_summary = (current.get("descriptor", {}).get("roles") or {}).get(role) or {}
    snapshot_summary = ((run.get("local_resources") or {}).get("roles") or {}).get(role) or {}
    if not current_summary.get("ready"):
        raise LocalResourceBindingError(f"Local resource role is not ready: {role} ({current_summary.get('state') or 'missing_binding'})")
    expected_id = str(snapshot_summary.get("resource_id") or "").strip()
    current_id = str(current_summary.get("resource_id") or "").strip()
    if not expected_id:
        raise LocalResourceBindingError(f"Run has no local resource snapshot for role: {role}")
    if current_id != expected_id:
        raise LocalResourceBindingError(f"Local resource binding changed during the run: {role}")

    resource = _resource_index(resources).get(current_id)
    if resource is None:
        raise LocalResourceBindingError(f"Bound local resource no longer exists: {current_id}")
    connection = {"id": current_id, "kind": _normalize_kind(resource.get("kind"))}
    for field in PRIVATE_CONNECTION_FIELDS:
        value = resource.get(field)
        if value not in (None, "", []):
            connection[field] = deepcopy(value)
    return {
        "role": role,
        "resource_id": current_id,
        "resource": resource,
        "connection": connection,
    }


def _resource_index(resources: dict) -> dict[str, dict]:
    result = {}
    for item in [*(resources.get("tools") or []), *(resources.get("sources") or [])]:
        if isinstance(item, dict) and item.get("id"):
            result[str(item["id"])] = item
    return result


def _configured_keys(explicit: set[str] | None) -> set[str]:
    if explicit is not None:
        return {str(item).strip().upper() for item in explicit if str(item).strip()}
    return {str(key).strip().upper() for key, value in os.environ.items() if str(value or "").strip()}


def _connection_error(resource: dict) -> str:
    kind = _normalize_kind(resource.get("kind"))
    if kind == "mcp" and not resource.get("endpoint") and not resource.get("command"):
        return "MCP 服务缺少 Endpoint 或启动命令"
    if kind == "remote_api" and not resource.get("endpoint") and not resource.get("openapi_url"):
        return "远程 API 缺少 Endpoint 或 OpenAPI URL"
    if kind == "plugin" and not resource.get("endpoint") and not resource.get("command"):
        return "底座插件缺少入口地址或启动命令"
    if kind in {"local_path", "web", "structured"} and not resource.get("location"):
        return "数据来源缺少位置或 URL"
    return ""


def _normalize_kind(value) -> str:
    kind = str(value or "").strip()
    return TOOL_KIND_ALIASES.get(kind, kind)


def _string_list(value) -> list[str]:
    if isinstance(value, str):
        values = value.replace("\r", "\n").replace(",", "\n").split("\n")
    elif isinstance(value, list):
        values = value
    else:
        values = []
    result = []
    for item in values:
        text = str(item or "").strip()
        if text and text not in result:
            result.append(text)
    return result
