from __future__ import annotations

from pathlib import Path

from .capability_registry import ProtocolRegistry
from .flow_contract import build_v02_flow_contract_report, build_v03_flow_contract_report, build_v04_flow_contract_report
from .report import report_status, summarize_findings


class CompatibilityBlockedError(RuntimeError):
    def __init__(self, report: dict):
        self.report = report
        super().__init__("Cartridge is not compatible with current base")


def build_compatibility_report(base: dict, manifest: dict, root_flow: dict | None, project_root: str | Path | None = None) -> dict:
    root = Path(project_root) if project_root else Path.cwd()
    registry = ProtocolRegistry(root)
    findings: list[dict] = []
    findings.extend(registry.validate_base(base))

    manifest = manifest if isinstance(manifest, dict) else {}
    root_flow = root_flow if isinstance(root_flow, dict) else {}
    base_protocols = {
        (str(item.get("id")), str(item.get("version"))): item
        for item in base.get("supported_protocols") or []
        if isinstance(item, dict)
    }

    runtime_contract = manifest.get("runtime_contract")
    base_contract = manifest.get("base_contract")
    legacy = not isinstance(runtime_contract, dict)
    if legacy:
        findings.append(_finding(
            "warning",
            "missing_runtime_contract",
            "manifest.runtime_contract is missing; legacy compatibility mode is used.",
        ))
        runtime_contract = {
            "protocol": "CF-FARP",
            "protocol_version": "0.1",
            "required_profiles": ["runtime_core"],
            "recommended_profiles": [],
            "required_capabilities": ["root_flow_execution", "basic_node_execution"],
            "optional_capabilities": [],
            "required_tools": [],
            "optional_tools": [],
        }

    protocol_id = str(runtime_contract.get("protocol") or (base_contract or {}).get("id") or "CF-FARP")
    protocol_version = str(runtime_contract.get("protocol_version") or (base_contract or {}).get("version") or "0.1")
    if not registry.supports_protocol(protocol_id, protocol_version):
        findings.append(_finding("blocker", "unknown_protocol", f"Protocol is not registered: {protocol_id}@{protocol_version}"))
    if (protocol_id, protocol_version) not in base_protocols:
        findings.append(_finding("blocker", "unsupported_protocol", f"Base does not support required protocol: {protocol_id}@{protocol_version}"))

    base_profiles = set(base.get("profiles") or [])
    base_capabilities = set(base.get("capabilities") or [])
    required_profiles = _string_list(runtime_contract.get("required_profiles"))
    recommended_profiles = _string_list(runtime_contract.get("recommended_profiles"))
    required_capabilities = _string_list(runtime_contract.get("required_capabilities"))
    optional_capabilities = _string_list(runtime_contract.get("optional_capabilities"))

    missing_required_profiles = [item for item in required_profiles if item not in base_profiles]
    missing_recommended_profiles = [item for item in recommended_profiles if item not in base_profiles]
    missing_required_capabilities = [item for item in required_capabilities if item not in base_capabilities]
    missing_optional_capabilities = [item for item in optional_capabilities if item not in base_capabilities]

    for item in missing_required_profiles:
        findings.append(_finding("blocker", "missing_required_profile", f"Base is missing required profile: {item}"))
    for item in missing_recommended_profiles:
        findings.append(_finding("warning", "missing_recommended_profile", f"Base is missing recommended profile: {item}"))
    for item in missing_required_capabilities:
        findings.append(_finding("blocker", "missing_required_capability", f"Base is missing required capability: {item}"))
    for item in missing_optional_capabilities:
        findings.append(_finding("info", "missing_optional_capability", f"Base is missing optional capability: {item}"))

    manifest_tool_map = {
        str(item.get("id")): item
        for item in manifest.get("mcp_tools") or []
        if isinstance(item, dict) and item.get("id")
    }
    manifest_tools = set(manifest_tool_map.keys())
    required_tools = _dedupe([
        *_tool_ids(runtime_contract.get("required_tools")),
        *[
            str(item.get("id"))
            for item in manifest.get("mcp_tools") or []
            if isinstance(item, dict) and item.get("id") and item.get("required") is True
        ],
    ])
    optional_tools = _dedupe([
        *_tool_ids(runtime_contract.get("optional_tools")),
        *[
            str(item.get("id"))
            for item in manifest.get("mcp_tools") or []
            if isinstance(item, dict) and item.get("id") and item.get("required") is not True
        ],
    ])
    missing_required_tools = [item for item in required_tools if item not in manifest_tools]
    missing_optional_tools = [item for item in optional_tools if item not in manifest_tools]
    for item in missing_required_tools:
        findings.append(_finding("blocker", "missing_required_tool", f"Manifest is missing required tool: {item}"))
    for item in missing_optional_tools:
        findings.append(_finding("warning", "missing_optional_tool", f"Manifest is missing optional tool: {item}"))
    supported_tool_packs = set(base.get("tool_packs") or [])
    unsupported_required_tools = []
    unsupported_optional_tools = []
    for tool_id in required_tools:
        tool = manifest_tool_map.get(tool_id)
        if not tool:
            continue
        tool_pack = _tool_pack_for_tool(tool)
        if tool_pack and tool_pack not in supported_tool_packs:
            unsupported_required_tools.append({"id": tool_id, "tool_pack": tool_pack})
            findings.append(_finding("blocker", "unsupported_required_tool_pack", f"Base does not support required tool pack: {tool_id} requires {tool_pack}"))
    for tool_id in optional_tools:
        tool = manifest_tool_map.get(tool_id)
        if not tool:
            continue
        tool_pack = _tool_pack_for_tool(tool)
        if tool_pack and tool_pack not in supported_tool_packs:
            unsupported_optional_tools.append({"id": tool_id, "tool_pack": tool_pack})
            findings.append(_finding("warning", "unsupported_optional_tool_pack", f"Base does not support optional tool pack: {tool_id} requires {tool_pack}"))

    flow_contract = None
    if not isinstance(root_flow, dict) or not isinstance(root_flow.get("states"), dict) or not root_flow.get("states"):
        findings.append(_finding("blocker", "invalid_root_flow", "root_flow.states must be a non-empty object"))
    elif root_flow.get("start") and root_flow.get("start") not in root_flow.get("states", {}):
        findings.append(_finding("blocker", "invalid_root_flow_start", f"root_flow.start points to missing state: {root_flow.get('start')}"))
    elif protocol_id == "CF-FARP" and protocol_version == "0.2":
        flow_contract = build_v02_flow_contract_report(root_flow, manifest)
        findings.extend(flow_contract.get("findings") or [])
    elif protocol_id == "CF-FARP" and protocol_version == "0.3":
        flow_contract = build_v03_flow_contract_report(root_flow, manifest)
        findings.extend(flow_contract.get("findings") or [])
    elif protocol_id == "CF-FARP" and protocol_version == "0.4":
        flow_contract = build_v04_flow_contract_report(root_flow, manifest)
        findings.extend(flow_contract.get("findings") or [])

    delivery = manifest.get("delivery_readiness")
    if not isinstance(delivery, dict):
        delivery = {"level": "legacy", "runnable": True}
        findings.append(_finding(
            "warning",
            "missing_delivery_readiness",
            "manifest.delivery_readiness is missing; cartridge is treated as development-only legacy content.",
        ))
    else:
        level = delivery.get("level")
        if level not in {"dev", "preview", "production"}:
            findings.append(_finding("blocker", "invalid_delivery_readiness", "delivery_readiness.level must be dev, preview, or production"))
        delivery = {**delivery, "runnable": level in {"dev", "preview", "production"}}

    counts = summarize_findings(findings)
    status = report_status(findings)
    return {
        "ok": counts["blocker"] == 0,
        "status": status,
        "legacy": legacy,
        "base": {
            "implementation_id": base.get("implementation_id"),
            "implementation_version": base.get("implementation_version"),
            "environment": base.get("environment"),
        },
        "cartridge": {
            "id": manifest.get("id"),
            "version": manifest.get("version"),
        },
        "protocol": {
            "required": f"{protocol_id}@{protocol_version}",
            "id": protocol_id,
            "version": protocol_version,
            "supported": (protocol_id, protocol_version) in base_protocols,
            "mode": "legacy_compatibility" if legacy else "protocol_aware",
        },
        "profiles": {
            "required": required_profiles,
            "recommended": recommended_profiles,
            "missing_required": missing_required_profiles,
            "missing_recommended": missing_recommended_profiles,
        },
        "capabilities": {
            "required": required_capabilities,
            "optional": optional_capabilities,
            "missing_required": missing_required_capabilities,
            "missing_optional": missing_optional_capabilities,
        },
        "tools": {
            "required": required_tools,
            "optional": optional_tools,
            "missing_required": missing_required_tools,
            "missing_optional": missing_optional_tools,
            "unsupported_required": unsupported_required_tools,
            "unsupported_optional": unsupported_optional_tools,
        },
        "delivery_readiness": delivery,
        "flow_contract": flow_contract,
        "summary": counts,
        "findings": findings,
    }


def _string_list(value) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _tool_ids(value) -> list[str]:
    if not isinstance(value, list):
        return []
    result = []
    for item in value:
        if isinstance(item, str) and item.strip():
            result.append(item.strip())
        elif isinstance(item, dict) and item.get("id"):
            result.append(str(item["id"]).strip())
    return result


def _dedupe(values: list[str]) -> list[str]:
    result = []
    seen = set()
    for value in values:
        item = str(value).strip()
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _tool_pack_for_tool(tool: dict) -> str:
    tool_type = str(tool.get("type") or "builtin").strip()
    server = str(tool.get("server") or "").strip()
    if not tool_type or not server:
        return ""
    return f"{tool_type}.{server}"


def _finding(severity: str, code: str, message: str) -> dict:
    return {"severity": severity, "code": code, "message": message}
