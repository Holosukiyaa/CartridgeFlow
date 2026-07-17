from __future__ import annotations

from pathlib import Path

from .compatibility import build_compatibility_report
from .flow_contract import build_v02_flow_contract_report, build_v03_flow_contract_report, build_v04_flow_contract_report
from .report import summarize_findings


def build_protocol_certification_report(base: dict, manifest: dict, root_flow: dict | None, project_root: str | Path | None = None) -> dict:
    compatibility = build_compatibility_report(base, manifest, root_flow, project_root)
    findings: list[dict] = []

    if not compatibility.get("ok"):
        findings.append(_finding("blocker", "compatibility_blocked", "Compatibility report contains blockers."))
    if compatibility.get("legacy"):
        findings.append(_finding("blocker", "legacy_not_certifiable", "Legacy cartridges cannot receive a protocol certification label."))
    if (compatibility.get("summary") or {}).get("warning", 0) > 0:
        findings.append(_finding("blocker", "warnings_not_certifiable", "Protocol certification requires zero compatibility warnings."))

    manifest = manifest if isinstance(manifest, dict) else {}
    runtime_contract = manifest.get("runtime_contract")
    base_contract = manifest.get("base_contract")
    delivery_readiness = manifest.get("delivery_readiness")

    if not isinstance(base_contract, dict):
        findings.append(_finding("blocker", "missing_base_contract", "manifest.base_contract is required for certification."))
    if not isinstance(runtime_contract, dict):
        findings.append(_finding("blocker", "missing_runtime_contract", "manifest.runtime_contract is required for certification."))
    if not isinstance(delivery_readiness, dict):
        findings.append(_finding("blocker", "missing_delivery_readiness", "manifest.delivery_readiness is required for certification."))

    if isinstance(base_contract, dict) and isinstance(runtime_contract, dict):
        base_id = str(base_contract.get("id") or "")
        base_version = str(base_contract.get("version") or "")
        protocol_id = str(runtime_contract.get("protocol") or "")
        protocol_version = str(runtime_contract.get("protocol_version") or "")
        if base_id != protocol_id or base_version != protocol_version:
            findings.append(_finding(
                "blocker",
                "contract_mismatch",
                "manifest.base_contract must match runtime_contract protocol and protocol_version.",
            ))

    protocol = compatibility.get("protocol") or {}
    if protocol.get("id") == "CF-FARP" and protocol.get("version") == "0.2":
        flow_contract = compatibility.get("flow_contract") or build_v02_flow_contract_report(root_flow, manifest)
        for item in flow_contract.get("findings") or []:
            findings.append(item)
    if protocol.get("id") == "CF-FARP" and protocol.get("version") == "0.3":
        flow_contract = compatibility.get("flow_contract") or build_v03_flow_contract_report(root_flow, manifest)
        for item in flow_contract.get("findings") or []:
            findings.append(item)
    if protocol.get("id") == "CF-FARP" and protocol.get("version") == "0.4":
        flow_contract = compatibility.get("flow_contract") or build_v04_flow_contract_report(root_flow, manifest)
        for item in flow_contract.get("findings") or []:
            findings.append(item)

    for tool in manifest.get("mcp_tools") or []:
        if not isinstance(tool, dict) or tool.get("required") is not True:
            continue
        contract = tool.get("contract")
        tool_id = tool.get("id") or f"{tool.get('server', '')}/{tool.get('tool', '')}".strip("/")
        if not isinstance(contract, dict) or not contract:
            findings.append(_finding("blocker", "required_tool_contract_missing", f"Required tool lacks contract metadata: {tool_id}"))
            continue
        if not contract.get("capability"):
            findings.append(_finding("blocker", "required_tool_capability_missing", f"Required tool contract lacks capability: {tool_id}"))
        if "idempotent" not in contract:
            findings.append(_finding("blocker", "required_tool_idempotency_missing", f"Required tool contract lacks idempotent flag: {tool_id}"))
        if "side_effect" not in contract:
            findings.append(_finding("blocker", "required_tool_side_effect_missing", f"Required tool contract lacks side_effect: {tool_id}"))

    counts = summarize_findings(findings)
    label = certification_label(protocol.get("id") or "CF-FARP", protocol.get("version") or "0.1")
    return {
        "ok": counts["blocker"] == 0,
        "status": "certified" if counts["blocker"] == 0 else "not_certified",
        "label": label,
        "protocol": protocol,
        "base": compatibility.get("base") or {},
        "cartridge": compatibility.get("cartridge") or {},
        "compatibility": compatibility,
        "summary": counts,
        "findings": findings,
    }


def certification_label(protocol_id: str, protocol_version: str) -> str:
    safe_id = str(protocol_id or "").strip().lower().replace("@", "-").replace(".", "-")
    safe_version = str(protocol_version or "").strip().lower().replace("@", "-").replace(".", "-")
    return f"{safe_id}-{safe_version}-certified"


def apply_protocol_certification_label(manifest: dict, report: dict) -> dict:
    if not report.get("ok"):
        raise ValueError("Cannot apply protocol certification label when certification report is not ok")
    next_manifest = dict(manifest or {})
    label = report.get("label") or certification_label(
        (report.get("protocol") or {}).get("id") or "CF-FARP",
        (report.get("protocol") or {}).get("version") or "0.1",
    )
    next_manifest["protocol_certification"] = {
        "status": "certified",
        "label": label,
        "protocol": (report.get("protocol") or {}).get("id"),
        "protocol_version": (report.get("protocol") or {}).get("version"),
        "base_implementation_id": (report.get("base") or {}).get("implementation_id"),
        "base_implementation_version": (report.get("base") or {}).get("implementation_version"),
    }
    branding = dict(next_manifest.get("branding") or {})
    tags = [str(item) for item in branding.get("tags") or [] if str(item).strip()]
    if label not in tags:
        tags.append(label)
    branding["tags"] = tags
    next_manifest["branding"] = branding
    return next_manifest


def _finding(severity: str, code: str, message: str) -> dict:
    return {"severity": severity, "code": code, "message": message}
