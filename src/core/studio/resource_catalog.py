"""Flow-scoped resource catalog assembled from all authoritative owners."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import asyncio
import json
import os
from pathlib import Path
import re
import shlex
import threading
from urllib.parse import urlsplit

from core.extensions import PortableDlcValidationError, load_portable_dlc_descriptor
from core.lab.builtin_mcp import BuiltinMcpRegistry
from core.llm.config_manager import get_assignments, list_providers, public_provider
from core.protocol.features import has_protocol_feature
from core.studio.resources import load_resources


CATALOG_SCHEMA = "cartridgeflow.flow_resource_catalog.v1"
CATALOG_SCHEMA_V2 = "cartridgeflow.flow_resource_catalog.v2"
RESOURCE_DETAIL_SCHEMA = "cartridgeflow.flow_resource_detail.v1"
RESOURCE_CONNECTIVITY_SCHEMA = "cartridgeflow.flow_resource_connectivity.v1"
TOOL_SOURCES = {"base_builtin", "local_resource", "cartridge_dlc"}
AUTHORING_MODEL_ROLES = {"authoring", "mentor"}
EXTERNAL_CONNECTOR_KINDS = {"mcp", "remote", "remote_api", "plugin"}
SENSITIVE_FIELD_PATTERN = re.compile(
    r"(?i)(api[_-]?key|token|secret|password|credential|authorization|cookie|auth[_-]?key|(?:^|[_-])key(?:$|[_-]))"
)
URL_PATTERN = re.compile(r"(?i)\b(?:https?|wss?)://[^\s'\"<>]+")
INLINE_SECRET_PATTERN = re.compile(
    r"(?i)\b(?:api[_-]?key|token|secret|password|credential|authorization|cookie|auth[_-]?key)\b\s*[:=]\s*[^\s,;]+"
)
BEARER_TOKEN_PATTERN = re.compile(r"(?i)\bbearer\s+[^\s,;]+")
COMMON_TOKEN_PATTERN = re.compile(r"\b(?:sk|rk|pk|ghp|xox[baprs])[-_][A-Za-z0-9_-]{8,}\b")
AUTH_HEADER_PATTERN = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]+$")
AUTH_SCHEME_PATTERN = AUTH_HEADER_PATTERN
DEFAULT_CONNECTIVITY_TIMEOUT_MS = 10_000
DEFAULT_TOOL_TIMEOUT_MS = 30_000
_CONNECTIVITY_HISTORY: dict[tuple[str, str], dict] = {}
_CONNECTIVITY_HISTORY_LOCK = threading.Lock()


class ResourceCatalogError(RuntimeError):
    """A stable, public-safe resource catalog API failure."""

    def __init__(self, code: str, message: str, *, status_code: int, health: dict | None = None):
        self.code = code
        self.status_code = status_code
        self.health = deepcopy(health) if isinstance(health, dict) else None
        super().__init__(message)


def build_flow_resource_catalog(
    root: str | Path,
    manifest: dict,
    root_flow: dict | None,
    *,
    package_path: str | Path | None = None,
    resources: dict | None = None,
) -> dict:
    root = Path(root)
    manifest = manifest if isinstance(manifest, dict) else {}
    root_flow = root_flow if isinstance(root_flow, dict) else {}
    cartridge_id = str(manifest.get("id") or "")
    runtime_contract = manifest.get("runtime_contract") if isinstance(manifest.get("runtime_contract"), dict) else {}
    catalog_schema = CATALOG_SCHEMA_V2 if has_protocol_feature(
        str(runtime_contract.get("protocol") or ""),
        str(runtime_contract.get("protocol_version") or ""),
        "resource_catalog_v2",
        root,
    ) else CATALOG_SCHEMA
    resources = deepcopy(resources) if isinstance(resources, dict) else load_resources()
    selected_local = set(((resources.get("bindings") or {}).get("tools") or {}).get(cartridge_id) or [])
    manifest_tools = [item for item in manifest.get("mcp_tools") or [] if isinstance(item, dict) and item.get("id")]
    manifest_by_pair = {
        (str(item.get("server") or ""), str(item.get("tool") or "")): item
        for item in manifest_tools
    }
    node_refs = _tool_node_references(root_flow)
    findings: list[dict] = []
    tools: list[dict] = []
    claimed_manifest_ids: set[str] = set()

    base_pairs: set[tuple[str, str]] = set()
    for item in BuiltinMcpRegistry(root).describe():
        server, tool = str(item.get("server") or ""), str(item.get("tool") or "")
        base_pairs.add((server, tool))
        resource_id = f"builtin:{server}/{tool}"
        declared = next((entry for entry in manifest_tools if str(entry.get("id")) == resource_id), None) or manifest_by_pair.get((server, tool))
        if declared:
            claimed_manifest_ids.add(str(declared["id"]))
        tools.append(_catalog_tool(
            cartridge_id=cartridge_id,
            tool_id=str((declared or {}).get("id") or resource_id),
            resource_id=resource_id,
            source="base_builtin",
            item={**item, **(declared or {})},
            declared=declared,
            flow_bound=bool(declared),
            node_refs=node_refs,
        ))

    local_by_id = {
        str(item.get("id")): item
        for item in resources.get("tools") or []
        if isinstance(item, dict) and item.get("id")
    }
    for resource_id, item in local_by_id.items():
        pair = (str(item.get("server") or ""), str(item.get("tool") or ""))
        declared = next((entry for entry in manifest_tools if str(entry.get("id")) == resource_id), None) or manifest_by_pair.get(pair)
        if declared:
            claimed_manifest_ids.add(str(declared["id"]))
        tools.append(_catalog_tool(
            cartridge_id=cartridge_id,
            tool_id=str((declared or {}).get("id") or resource_id),
            resource_id=resource_id,
            source="local_resource",
            item={**item, **(declared or {})},
            declared=declared,
            flow_bound=resource_id in selected_local,
            node_refs=node_refs,
        ))

    dlc_pairs: set[tuple[str, str]] = set()
    if manifest.get("portable_dlc") and package_path:
        try:
            descriptor = load_portable_dlc_descriptor(package_path, manifest)
            for item in descriptor.get("tools") or []:
                pair = (str(item.get("server") or ""), str(item.get("tool") or ""))
                dlc_pairs.add(pair)
                declared = manifest_by_pair.get(pair)
                tool_id = str((declared or {}).get("id") or f"dlc:{pair[0]}/{pair[1]}")
                if declared:
                    claimed_manifest_ids.add(str(declared["id"]))
                tools.append(_catalog_tool(
                    cartridge_id=cartridge_id,
                    tool_id=tool_id,
                    resource_id=f"dlc:{descriptor.get('id')}:{pair[0]}/{pair[1]}",
                    source="cartridge_dlc",
                    item={**item, **(declared or {})},
                    declared=declared,
                    flow_bound=True,
                    node_refs=node_refs,
                    owner=str(descriptor.get("id") or ""),
                ))
        except (OSError, ValueError, PortableDlcValidationError) as exc:
            findings.append({
                "severity": "blocker",
                "code": "CARTRIDGE_DLC_CATALOG_UNAVAILABLE",
                "message": str(exc),
                "path": "manifest.portable_dlc",
            })

    for item in manifest_tools:
        tool_id = str(item.get("id") or "")
        if tool_id in claimed_manifest_ids:
            continue
        pair = (str(item.get("server") or ""), str(item.get("tool") or ""))
        inferred_source = (
            "base_builtin" if pair in base_pairs
            else "cartridge_dlc" if pair in dlc_pairs or manifest.get("portable_dlc")
            else "local_resource"
        )
        tools.append(_catalog_tool(
            cartridge_id=cartridge_id,
            tool_id=tool_id,
            resource_id=tool_id,
            source=inferred_source,
            item=item,
            declared=item,
            flow_bound=False,
            node_refs=node_refs,
        ))
        findings.append({
            "severity": "blocker" if item.get("required", True) is not False else "warning",
            "code": "TOOL_RESOURCE_UNRESOLVED",
            "message": f"Manifest tool {tool_id} has no available {inferred_source} provider.",
            "path": f"manifest.mcp_tools.{tool_id}",
        })

    declared_ids = {str(item.get("id")) for item in manifest_tools}
    for tool_id, refs in node_refs.items():
        if tool_id not in declared_ids:
            findings.append({
                "severity": "blocker",
                "code": "NODE_TOOL_NOT_DECLARED",
                "message": f"Node tool reference {tool_id} is not declared in manifest.mcp_tools.",
                "path": f"root_flow.states.{refs[0]}.allowed_tools",
                "node_ids": refs,
            })

    for item in tools:
        if item["node_references"] and item["status"] != "ready":
            findings.append({
                "severity": "blocker",
                "code": "NODE_TOOL_RESOURCE_NOT_BOUND",
                "message": f"Node tool {item['id']} is referenced but its {item['source']} provider is not bound.",
                "path": f"root_flow.states.{item['node_references'][0]}.allowed_tools",
                "node_ids": item["node_references"],
            })

    tools.sort(key=lambda item: (item["source"], item["id"], item["resource_id"]))
    return {
        "schema": catalog_schema,
        "cartridge_id": cartridge_id,
        "tools": tools,
        "models": _model_catalog(manifest, root_flow),
        "findings": findings,
        "summary": {
            "tools": len(tools),
            "ready": sum(1 for item in tools if item["status"] == "ready"),
            "referenced": sum(1 for item in tools if item["node_references"]),
            "blockers": sum(1 for item in findings if item["severity"] == "blocker"),
        },
    }


def _catalog_tool(
    *,
    cartridge_id: str,
    tool_id: str,
    resource_id: str,
    source: str,
    item: dict,
    declared: dict | None,
    flow_bound: bool,
    node_refs: dict[str, list[str]],
    owner: str = "",
) -> dict:
    if source not in TOOL_SOURCES:
        raise ValueError(f"Unknown tool source: {source}")
    refs = list(node_refs.get(tool_id) or [])
    available = source == "base_builtin" or source == "cartridge_dlc" or item.get("enabled") is not False
    status = "ready" if available and flow_bound else "available" if available else "unavailable"
    if refs and not flow_bound:
        status = "unbound"
    source_model = item.get("_source_model") if isinstance(item.get("_source_model"), dict) else {}
    parse_status = "parsed" if source_model.get("ok") else "not_applicable" if source != "cartridge_dlc" else "opaque"
    kind = str(item.get("kind") or item.get("type") or ("builtin" if source == "base_builtin" else "mcp"))
    presentation_mode, non_readable_reason = _presentation_mode(source, kind, item, parse_status)
    operation_graph = {
        "operations": _public_value(source_model.get("operations") or []),
        "edges": _public_value(source_model.get("edges") or []),
        "fallbacks": _public_value(source_model.get("fallbacks") or []),
        "capabilities": _public_string_list(source_model.get("capabilities")),
    } if presentation_mode == "local_parsable" else {}
    transparency = _public_transparency(item.get("transparency") or ("atomic" if source == "base_builtin" else "legacy_opaque"))
    connector = _connector_projection(resource_id, kind, item) if presentation_mode == "external_connector" else None
    return {
        "id": tool_id,
        "resource_id": resource_id,
        "name": _public_text(item.get("name") or item.get("description") or tool_id),
        "description": _public_text(item.get("description")),
        "kind": kind,
        "source": source,
        "owner": _public_text(owner or ("CARTRIDGEFLOW-BASE" if source == "base_builtin" else "local" if source == "local_resource" else "cartridge")),
        "server": _public_text(item.get("server")),
        "tool": _public_text(item.get("tool")),
        "enabled": item.get("enabled") is not False,
        "locked": source != "local_resource",
        "package_mode": "base" if source == "base_builtin" else "descriptor" if source == "cartridge_dlc" else _public_text(item.get("package_mode") or "external"),
        "manifest_requirement": {
            "declared": bool(declared),
            "required": bool(declared and declared.get("required", True) is not False),
        },
        "flow_binding": {"bound": flow_bound, "status": "bound" if flow_bound else "not_bound"},
        "node_references": refs,
        "status": status,
        "presentation_mode": presentation_mode,
        "transparency": transparency,
        "readability": {
            "state": "readable" if presentation_mode == "local_parsable" else "not_readable",
            "reason": non_readable_reason,
        },
        "connector": connector,
        "contract": _public_contract(item) if presentation_mode == "external_connector" else {},
        "health": _health_summary(cartridge_id, resource_id) if presentation_mode == "external_connector" else _non_connector_health(),
        "node_id": _public_text(item.get("node_id")),
        "implementation": _public_value(item.get("implementation")) if presentation_mode == "local_parsable" and isinstance(item.get("implementation"), dict) else {},
        "source_digest": _public_text(item.get("source_digest")),
        "parse_status": parse_status,
        "operation_count": len(source_model.get("operations") or []) if presentation_mode == "local_parsable" else 0,
        "broker_capabilities": _public_string_list(source_model.get("capabilities")) if presentation_mode == "local_parsable" else [],
        "operation_graph": operation_graph,
    }


def get_flow_resource_detail(
    root: str | Path,
    manifest: dict,
    root_flow: dict | None,
    resource_id: str,
    *,
    package_path: str | Path | None = None,
    resources: dict | None = None,
) -> dict:
    """Return the public-safe detail projection for one catalog resource."""
    report = build_flow_resource_catalog(
        root,
        manifest,
        root_flow,
        package_path=package_path,
        resources=resources,
    )
    resource = _select_catalog_resource(report, resource_id)
    return {
        "schema": RESOURCE_DETAIL_SCHEMA,
        "cartridge_id": report["cartridge_id"],
        "resource": resource,
    }


def check_flow_resource_connectivity(
    root: str | Path,
    manifest: dict,
    root_flow: dict | None,
    resource_id: str,
    *,
    package_path: str | Path | None = None,
    resources: dict | None = None,
) -> dict:
    """Probe a bound external connector without invoking its business tool."""
    source_resources = deepcopy(resources) if isinstance(resources, dict) else load_resources()
    report = build_flow_resource_catalog(
        root,
        manifest,
        root_flow,
        package_path=package_path,
        resources=source_resources,
    )
    resource = _select_catalog_resource(report, resource_id)
    cartridge_id = report["cartridge_id"]
    resolved_resource_id = str(resource["resource_id"])

    if resource.get("presentation_mode") != "external_connector":
        raise _connectivity_failure(
            cartridge_id,
            resolved_resource_id,
            "RESOURCE_CONNECTIVITY_UNSUPPORTED",
            "Only external connector resources support connectivity checks.",
            409,
        )
    if not (resource.get("flow_binding") or {}).get("bound"):
        raise _connectivity_failure(
            cartridge_id,
            resolved_resource_id,
            "EXTERNAL_CONNECTOR_UNBOUND",
            "The external connector is not bound to this Flow.",
            409,
        )

    raw_resource = _local_resource_by_id(source_resources, resolved_resource_id)
    if raw_resource is None:
        raise _connectivity_failure(
            cartridge_id,
            resolved_resource_id,
            "EXTERNAL_CONNECTOR_NOT_CONFIGURED",
            "The external connector configuration is unavailable.",
            409,
        )
    auth_error = _connector_authentication_error(raw_resource)
    if auth_error:
        raise _connectivity_failure(
            cartridge_id,
            resolved_resource_id,
            auth_error[0],
            auth_error[1],
            409,
        )

    timeout_ms = min(_public_contract(raw_resource).get("timeout_ms") or DEFAULT_TOOL_TIMEOUT_MS, DEFAULT_CONNECTIVITY_TIMEOUT_MS)
    try:
        probe = _probe_external_connector(raw_resource, timeout_ms)
    except ResourceCatalogError as exc:
        _record_health(cartridge_id, resolved_resource_id, exc.health or _failed_health(exc.code, str(exc)))
        raise

    health = {
        "status": "healthy",
        "checked_at": _utc_now(),
        "code": "CONNECTIVITY_OK",
        "message": "External connector accepted a real connectivity probe.",
        "retryable": False,
        "adapter": probe["adapter"],
        "http_status": probe.get("http_status"),
    }
    _record_health(cartridge_id, resolved_resource_id, health)
    return {
        "schema": RESOURCE_CONNECTIVITY_SCHEMA,
        "cartridge_id": cartridge_id,
        "resource_id": resolved_resource_id,
        "ok": True,
        "connection_health": health,
    }


def _select_catalog_resource(report: dict, resource_id: str) -> dict:
    target = str(resource_id or "").strip()
    matches = [item for item in report.get("tools") or [] if item.get("resource_id") == target]
    if not matches:
        matches = [item for item in report.get("tools") or [] if item.get("id") == target]
    if not matches:
        raise ResourceCatalogError(
            "RESOURCE_NOT_FOUND",
            "The requested resource is not present in this Flow catalog.",
            status_code=404,
        )
    if len(matches) > 1:
        raise ResourceCatalogError(
            "RESOURCE_AMBIGUOUS",
            "The requested resource identifier matches multiple catalog entries.",
            status_code=409,
        )
    return deepcopy(matches[0])


def _presentation_mode(source: str, kind: str, item: dict, parse_status: str) -> tuple[str, str | None]:
    if source == "cartridge_dlc" and parse_status == "parsed":
        return "local_parsable", None
    declared_type = str(item.get("type") or "").strip().casefold()
    kind_value = str(kind or "").strip().casefold()
    has_connector = any(str(item.get(field) or "").strip() for field in ("endpoint", "openapi_url", "command"))
    has_contract = isinstance(item.get("contract"), dict) and bool(item.get("contract"))
    if source == "local_resource" and has_connector and has_contract and (kind_value in EXTERNAL_CONNECTOR_KINDS or declared_type in EXTERNAL_CONNECTOR_KINDS):
        return "external_connector", "Connector implementation is machine-local and is not readable from the Flow."
    if source == "cartridge_dlc":
        return "unauditable", "Portable DLC source is not statically parseable."
    if source == "local_resource" and has_connector:
        return "unauditable", "The external connector lacks a verifiable call contract."
    return "unauditable", "No readable implementation or verifiable connector contract is available."


def _connector_projection(resource_id: str, kind: str, item: dict) -> dict:
    endpoint = _connection_reference(resource_id, "endpoint", item.get("endpoint"))
    openapi = _connection_reference(resource_id, "openapi_url", item.get("openapi_url"))
    command = _connection_reference(resource_id, "command", item.get("command"))
    return {
        "id": _public_text(resource_id),
        "identity": f"local-resource:{_public_text(resource_id)}",
        "kind": _public_text(kind),
        "endpoint": endpoint,
        "openapi": openapi,
        "command": command,
        "authentication": _authentication_projection(item),
    }


def _connection_reference(resource_id: str, field: str, value) -> dict:
    raw = str(value or "").strip()
    if not raw:
        return {"state": "not_configured", "reference": None, "transport": None}
    transport = "stdio" if field == "command" else str(urlsplit(raw).scheme or "configured").casefold()
    return {
        "state": "configured",
        "reference": f"local-resource:{_public_text(resource_id)}#{field}",
        "transport": transport,
    }


def _authentication_projection(item: dict) -> dict:
    reference = str(item.get("auth_env") or "").strip()
    if not reference:
        return {"required": False, "reference": None, "status": "not_required"}
    return {
        "required": True,
        "reference": _public_text(reference),
        "status": "configured" if os.environ.get(reference) else "missing",
    }


def _public_contract(item: dict) -> dict:
    contract = item.get("contract") if isinstance(item.get("contract"), dict) else {}
    timeout_ms = _positive_int(contract.get("timeout_ms") or item.get("timeout_ms"), DEFAULT_TOOL_TIMEOUT_MS)
    input_schema = item.get("params_schema") or item.get("input_schema") or contract.get("input_schema") or contract.get("params_schema") or {}
    output_schema = item.get("output_schema") or contract.get("output_schema") or {}
    side_effect = _public_text(contract.get("side_effect") or item.get("side_effect") or ("read_only" if item.get("read_only") is True else "unknown"))
    raw_permissions = contract.get("permissions") or contract.get("permission") or item.get("permissions") or item.get("permission") or []
    retry = contract.get("retry") or contract.get("retry_policy")
    if not isinstance(retry, dict):
        retry = {"max_retries": _positive_int(contract.get("max_retries"), 0)}
    idempotent = contract.get("idempotent")
    idempotency = {
        "declared": idempotent if isinstance(idempotent, bool) else None,
        "status": "idempotent" if idempotent is True else "non_idempotent" if idempotent is False else "unknown",
    }
    return {
        "server": _public_text(item.get("server")),
        "tool": _public_text(item.get("tool")),
        "input_schema": _public_value(input_schema),
        "output_schema": _public_value(output_schema),
        "permissions": _public_string_list(raw_permissions),
        "read_only": item.get("read_only") is True or side_effect in {"none", "read_only"},
        "side_effect": side_effect,
        "timeout_ms": timeout_ms,
        "retry": _public_value(retry),
        "idempotency": idempotency,
    }


def _public_transparency(value) -> str:
    candidate = str(value or "").strip()
    return candidate if candidate in {"atomic", "declared_graph", "contract_only", "opaque", "legacy_opaque", "inspectable"} else "legacy_opaque"


def _public_value(value, key: str = ""):
    if SENSITIVE_FIELD_PATTERN.search(key) or key.casefold() in {"endpoint", "openapi_url", "command", "args", "headers", "header"}:
        return "[redacted]"
    if isinstance(value, dict):
        result = {}
        for index, (child_key, child_value) in enumerate(value.items()):
            raw_key = str(child_key)
            public_key = "redacted" if SENSITIVE_FIELD_PATTERN.search(raw_key) else raw_key
            if public_key in result:
                public_key = f"{public_key}_{index}"
            result[public_key] = _public_value(child_value, raw_key)
        return result
    if isinstance(value, list):
        return [_public_value(item, key) for item in value]
    if isinstance(value, tuple):
        return [_public_value(item, key) for item in value]
    if isinstance(value, str):
        text = URL_PATTERN.sub("[redacted-url]", value)
        text = INLINE_SECRET_PATTERN.sub("[redacted]", text)
        text = BEARER_TOKEN_PATTERN.sub("Bearer [redacted]", text)
        return COMMON_TOKEN_PATTERN.sub("[redacted]", text)[:2_000]
    return deepcopy(value)


def _public_text(value) -> str:
    return str(_public_value(str(value or "")))[:2_000]


def _public_string_list(value) -> list[str]:
    raw_values = [value] if isinstance(value, str) else value if isinstance(value, (list, tuple, set)) else []
    result = []
    for item in raw_values:
        public = _public_text(item)
        if public and public not in result:
            result.append(public)
    return result


def _positive_int(value, fallback: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return fallback
    return parsed if parsed >= 0 else fallback


def _health_summary(cartridge_id: str, resource_id: str) -> dict:
    with _CONNECTIVITY_HISTORY_LOCK:
        connection = deepcopy(_CONNECTIVITY_HISTORY.get((cartridge_id, resource_id)))
    return {
        "connection": connection or {
            "status": "not_checked",
            "checked_at": None,
            "code": "CONNECTIVITY_NOT_CHECKED",
            "message": "No connectivity check has been recorded for this connector.",
            "retryable": None,
            "adapter": None,
            "http_status": None,
        },
        "run": {
            "status": "not_observed",
            "last_run_at": None,
            "code": "RUN_TELEMETRY_UNAVAILABLE",
            "message": "No public runtime telemetry is available for this connector.",
        },
    }


def _non_connector_health() -> dict:
    return {
        "connection": {"status": "not_applicable", "checked_at": None, "code": "CONNECTIVITY_NOT_APPLICABLE"},
        "run": {"status": "not_observed", "last_run_at": None, "code": "RUN_TELEMETRY_UNAVAILABLE"},
    }


def _connectivity_failure(cartridge_id: str, resource_id: str, code: str, message: str, status_code: int) -> ResourceCatalogError:
    health = _failed_health(code, message)
    _record_health(cartridge_id, resource_id, health)
    return ResourceCatalogError(code, message, status_code=status_code, health=health)


def _failed_health(code: str, message: str, *, retryable: bool = False, adapter: str | None = None, http_status: int | None = None) -> dict:
    return {
        "status": "failed",
        "checked_at": _utc_now(),
        "code": code,
        "message": _public_text(message),
        "retryable": retryable,
        "adapter": adapter,
        "http_status": http_status,
    }


def _record_health(cartridge_id: str, resource_id: str, health: dict) -> None:
    with _CONNECTIVITY_HISTORY_LOCK:
        _CONNECTIVITY_HISTORY[(cartridge_id, resource_id)] = _public_value(health)


def _local_resource_by_id(resources: dict, resource_id: str) -> dict | None:
    for item in resources.get("tools") or []:
        if isinstance(item, dict) and str(item.get("id") or "") == resource_id:
            return item
    return None


def _connector_authentication_error(item: dict) -> tuple[str, str] | None:
    auth_env = str(item.get("auth_env") or "").strip()
    if auth_env and not os.environ.get(auth_env):
        return "EXTERNAL_CONNECTOR_AUTH_NOT_CONFIGURED", "The connector credential reference is not configured locally."
    return None


def _probe_external_connector(item: dict, timeout_ms: int) -> dict:
    kind = str(item.get("kind") or item.get("type") or "").casefold()
    endpoint = str(item.get("endpoint") or item.get("openapi_url") or "").strip()
    if kind == "mcp":
        return _probe_mcp_connector(item, timeout_ms)
    if kind in {"remote", "remote_api"} and endpoint:
        return _probe_http_connector(item, endpoint, timeout_ms)
    raise ResourceCatalogError(
        "CONNECTIVITY_PROBE_UNSUPPORTED",
        "This connector has no non-invasive connectivity probe.",
        status_code=409,
        health=_failed_health("CONNECTIVITY_PROBE_UNSUPPORTED", "This connector has no non-invasive connectivity probe."),
    )


def _probe_http_connector(item: dict, endpoint: str, timeout_ms: int) -> dict:
    try:
        import httpx
    except ImportError as exc:
        raise ResourceCatalogError(
            "CONNECTIVITY_DEPENDENCY_UNAVAILABLE",
            "The HTTP connectivity dependency is unavailable.",
            status_code=503,
            health=_failed_health("CONNECTIVITY_DEPENDENCY_UNAVAILABLE", "The HTTP connectivity dependency is unavailable."),
        ) from exc
    try:
        with httpx.Client(headers=_connector_auth_headers(item), timeout=timeout_ms / 1000, follow_redirects=False) as client:
            response = client.request("HEAD", endpoint)
    except httpx.TimeoutException as exc:
        raise ResourceCatalogError(
            "CONNECTIVITY_TIMEOUT",
            "The external connector did not respond before the connectivity timeout.",
            status_code=504,
            health=_failed_health("CONNECTIVITY_TIMEOUT", "The external connector did not respond before the connectivity timeout.", retryable=True, adapter="remote_http"),
        ) from exc
    except httpx.HTTPError as exc:
        raise ResourceCatalogError(
            "CONNECTIVITY_UNAVAILABLE",
            "The external connector could not be reached.",
            status_code=502,
            health=_failed_health("CONNECTIVITY_UNAVAILABLE", "The external connector could not be reached.", retryable=True, adapter="remote_http"),
        ) from exc
    if response.status_code in {401, 403}:
        raise ResourceCatalogError(
            "CONNECTIVITY_AUTH_FAILED",
            "The external connector rejected the configured credential reference.",
            status_code=502,
            health=_failed_health("CONNECTIVITY_AUTH_FAILED", "The external connector rejected the configured credential reference.", adapter="remote_http", http_status=response.status_code),
        )
    if not 200 <= response.status_code < 400:
        raise ResourceCatalogError(
            "CONNECTIVITY_HTTP_STATUS",
            "The external connector returned an unsuccessful connectivity response.",
            status_code=502,
            health=_failed_health("CONNECTIVITY_HTTP_STATUS", "The external connector returned an unsuccessful connectivity response.", retryable=response.status_code >= 500, adapter="remote_http", http_status=response.status_code),
        )
    return {"adapter": "remote_http", "http_status": response.status_code}


def _probe_mcp_connector(item: dict, timeout_ms: int) -> dict:
    try:
        return _run_async(_probe_mcp_connector_async(item, timeout_ms))
    except ResourceCatalogError:
        raise
    except TimeoutError as exc:
        raise ResourceCatalogError(
            "CONNECTIVITY_TIMEOUT",
            "The MCP connector did not respond before the connectivity timeout.",
            status_code=504,
            health=_failed_health("CONNECTIVITY_TIMEOUT", "The MCP connector did not respond before the connectivity timeout.", retryable=True),
        ) from exc
    except Exception as exc:
        raise ResourceCatalogError(
            "CONNECTIVITY_PROTOCOL_FAILED",
            "The MCP connector did not complete its initialization handshake.",
            status_code=502,
            health=_failed_health("CONNECTIVITY_PROTOCOL_FAILED", "The MCP connector did not complete its initialization handshake.", retryable=True),
        ) from exc


async def _probe_mcp_connector_async(item: dict, timeout_ms: int) -> dict:
    try:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        from mcp.client.streamable_http import streamable_http_client
        import httpx
    except ImportError as exc:
        raise ResourceCatalogError(
            "CONNECTIVITY_DEPENDENCY_UNAVAILABLE",
            "The MCP connectivity dependency is unavailable.",
            status_code=503,
            health=_failed_health("CONNECTIVITY_DEPENDENCY_UNAVAILABLE", "The MCP connectivity dependency is unavailable."),
        ) from exc

    read_timeout = timeout_ms / 1000
    endpoint = str(item.get("endpoint") or "").strip()
    if endpoint:
        async with httpx.AsyncClient(headers=_connector_auth_headers(item), timeout=read_timeout, follow_redirects=False) as client:
            async with streamable_http_client(endpoint, http_client=client) as (read_stream, write_stream, _session_id):
                async with ClientSession(read_stream, write_stream, read_timeout_seconds=read_timeout) as session:
                    await session.initialize()
        return {"adapter": "mcp_streamable_http"}

    command = _command_parts(item.get("command"))
    if not command:
        raise ResourceCatalogError(
            "EXTERNAL_CONNECTOR_NOT_CONFIGURED",
            "The MCP connector has no endpoint or launch command.",
            status_code=409,
            health=_failed_health("EXTERNAL_CONNECTOR_NOT_CONFIGURED", "The MCP connector has no endpoint or launch command."),
        )
    command.extend(_argument_parts(item.get("args")))
    server = StdioServerParameters(command=command[0], args=command[1:], env=_connector_environment(item), encoding="utf-8")
    with open(os.devnull, "w", encoding="utf-8") as errlog:
        async with stdio_client(server, errlog=errlog) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream, read_timeout_seconds=read_timeout) as session:
                await session.initialize()
    return {"adapter": "mcp_stdio"}


def _connector_auth_headers(item: dict) -> dict[str, str]:
    auth_env = str(item.get("auth_env") or "").strip()
    if not auth_env:
        return {}
    token = os.environ.get(auth_env)
    if not token:
        return {}
    header = str(item.get("auth_header") or "Authorization").strip()
    if not AUTH_HEADER_PATTERN.fullmatch(header):
        raise ResourceCatalogError(
            "EXTERNAL_CONNECTOR_CONFIGURATION_INVALID",
            "The connector authentication configuration is invalid.",
            status_code=409,
            health=_failed_health("EXTERNAL_CONNECTOR_CONFIGURATION_INVALID", "The connector authentication configuration is invalid."),
        )
    scheme = str(item.get("auth_scheme") or "").strip()
    if scheme and not AUTH_SCHEME_PATTERN.fullmatch(scheme):
        raise ResourceCatalogError(
            "EXTERNAL_CONNECTOR_CONFIGURATION_INVALID",
            "The connector authentication configuration is invalid.",
            status_code=409,
            health=_failed_health("EXTERNAL_CONNECTOR_CONFIGURATION_INVALID", "The connector authentication configuration is invalid."),
        )
    return {header: f"{scheme} {token}".strip()}


def _connector_environment(item: dict) -> dict[str, str]:
    environment = {key: os.environ[key] for key in ("PATH", "SYSTEMROOT", "WINDIR") if os.environ.get(key)}
    auth_env = str(item.get("auth_env") or "").strip()
    if auth_env and os.environ.get(auth_env):
        environment[auth_env] = os.environ[auth_env]
    return environment


def _command_parts(value) -> list[str]:
    text = str(value or "").strip()
    return shlex.split(text, posix=os.name != "nt") if text else []


def _argument_parts(value) -> list[str]:
    text = str(value or "").strip()
    if not text:
        return []
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return shlex.split(text, posix=os.name != "nt")
    return [str(item) for item in parsed] if isinstance(parsed, list) else shlex.split(text, posix=os.name != "nt")


def _run_async(awaitable):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(awaitable)
    result: dict = {}

    def run() -> None:
        try:
            result["value"] = asyncio.run(awaitable)
        except BaseException as exc:  # Propagate the real connector failure to the caller.
            result["error"] = exc

    thread = threading.Thread(target=run, name="cartridgeflow-resource-connectivity", daemon=True)
    thread.start()
    thread.join()
    if "error" in result:
        raise result["error"]
    return result["value"]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _tool_node_references(root_flow: dict) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for node_id, node in (root_flow.get("states") or {}).items():
        if not isinstance(node, dict):
            continue
        params = node.get("params") if isinstance(node.get("params"), dict) else {}
        raw = node.get("allowed_tools") or params.get("allowed_tools") or []
        values = [raw] if isinstance(raw, str) else raw if isinstance(raw, list) else []
        for value in values:
            tool_id = str(value or "").strip()
            if tool_id:
                result.setdefault(tool_id, []).append(str(node_id))
    return result


def _model_catalog(manifest: dict, root_flow: dict) -> dict:
    assignments = get_assignments()
    cartridge_id = str(manifest.get("id") or "")
    providers = [public_provider(item) for item in list_providers()]
    runtime_roles = [
        dict(item)
        for item in ((manifest.get("llm_recipe") or {}).get("roles") or [])
        if isinstance(item, dict) and str(item.get("id") or "") not in AUTHORING_MODEL_ROLES
    ]
    flow_bindings = deepcopy((assignments.get("cartridges") or {}).get(cartridge_id) or {})
    node_bindings = {
        key.split("/", 1)[1]: deepcopy(value)
        for key, value in (assignments.get("nodes") or {}).items()
        if key.startswith(f"{cartridge_id}/") and isinstance(value, dict)
    }
    nodes = []
    for node_id, node in (root_flow.get("states") or {}).items():
        if not isinstance(node, dict):
            continue
        params = node.get("params") if isinstance(node.get("params"), dict) else {}
        kind = str(node.get("kind") or params.get("kind") or "")
        executor = str(node.get("executor") or params.get("executor") or "")
        if not ((kind == "decision" and executor == "llm") or node.get("action") == "llm_prompt"):
            continue
        role = str(node.get("model_role") or params.get("model_role") or "")
        binding = (node_bindings.get(str(node_id)) or {}).get(role) if role else None
        nodes.append({
            "node_id": str(node_id),
            "role": role,
            "binding": deepcopy(binding) if isinstance(binding, dict) else None,
            "status": "bound" if isinstance(binding, dict) and binding.get("provider_id") else "unbound",
        })
    authoring_bindings = {
        role: deepcopy(binding)
        for role, binding in (assignments.get("defaults") or {}).items()
        if role in AUTHORING_MODEL_ROLES and isinstance(binding, dict)
    }
    return {
        "providers": providers,
        "runtime_roles": runtime_roles,
        "flow_bindings": flow_bindings,
        "node_bindings": nodes,
        "authoring": {"scope": "base_authoring", "bindings": authoring_bindings},
    }
