"""Flow-scoped resource catalog assembled from all authoritative owners."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from core.extensions import PortableDlcValidationError, load_portable_dlc_descriptor
from core.lab.builtin_mcp import BuiltinMcpRegistry
from core.llm.config_manager import get_assignments, list_providers, public_provider
from core.studio.resources import load_resources


CATALOG_SCHEMA = "cartridgeflow.flow_resource_catalog.v1"
TOOL_SOURCES = {"base_builtin", "local_resource", "cartridge_dlc"}
AUTHORING_MODEL_ROLES = {"authoring", "mentor"}


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
        "schema": CATALOG_SCHEMA,
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
    return {
        "id": tool_id,
        "resource_id": resource_id,
        "name": str(item.get("name") or item.get("description") or tool_id),
        "description": str(item.get("description") or ""),
        "kind": str(item.get("kind") or item.get("type") or ("builtin" if source == "base_builtin" else "mcp")),
        "source": source,
        "owner": owner or ("CARTRIDGEFLOW-BASE" if source == "base_builtin" else "local" if source == "local_resource" else "cartridge"),
        "server": str(item.get("server") or ""),
        "tool": str(item.get("tool") or ""),
        "enabled": item.get("enabled") is not False,
        "locked": source != "local_resource",
        "package_mode": "base" if source == "base_builtin" else "descriptor" if source == "cartridge_dlc" else str(item.get("package_mode") or "external"),
        "manifest_requirement": {
            "declared": bool(declared),
            "required": bool(declared and declared.get("required", True) is not False),
        },
        "flow_binding": {"bound": flow_bound, "status": "bound" if flow_bound else "not_bound"},
        "node_references": refs,
        "status": status,
    }


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
