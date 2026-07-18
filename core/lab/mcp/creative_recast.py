"""Opt-in CF-CRCP validation tools.

The module is intentionally not registered in ``core.lab.mcp.dlc`` yet. The
current base does not claim the CRCP runtime capabilities required to expose
these tools through MCP. The functions remain side-effect free so they can be
conformance-tested before the execution path is enabled.
"""

from __future__ import annotations

import json

from core.protocol.creative_recast import (
    validate_creative_spec as _validate_creative_spec,
    validate_shot_control_bundle as _validate_shot_control_bundle,
)


DLC_ID = "dlc.series_3d_episode_factory"
DLC_PROTOCOL = "CF-CRCP@0.1"
TOOLS = ["validate_shot_control_bundle", "validate_creative_spec", "validate_change_proposal"]


def _json_object(value, field: str) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        parsed = json.loads(value)
        if isinstance(parsed, dict):
            return parsed
    raise ValueError(f"{field} must be a JSON object")


def _param(params: dict, primary: str, fallback: str):
    return params.get(primary) if primary in params else params.get(fallback)


def _validate_change_proposal(proposal: dict) -> dict:
    findings: list[dict] = []
    if not isinstance(proposal, dict):
        return _proposal_result(findings, "change_proposal_invalid", "ChangeProposal must be an object")
    if proposal.get("schema") != "cartridgeflow.change_proposal.v1":
        _proposal_block(findings, "change_proposal_schema", "schema must be cartridgeflow.change_proposal.v1")
    for field in ["proposal_id", "reason", "expected_benefit", "cost_and_risk", "rollback", "question"]:
        if not isinstance(proposal.get(field), str) or not proposal.get(field).strip():
            _proposal_block(findings, "change_proposal_fields", f"{field} is required")
    if proposal.get("protocol") != "CF-CRCP@0.1":
        _proposal_block(findings, "change_proposal_protocol", "protocol must be CF-CRCP@0.1")
    for field in ["current", "proposed"]:
        if not isinstance(proposal.get(field), dict):
            _proposal_block(findings, "change_proposal_fields", f"{field} must be an object")
    affected_locks = proposal.get("affected_locks")
    if not isinstance(affected_locks, list) or any(not isinstance(item, str) or not item.strip() for item in affected_locks):
        _proposal_block(findings, "change_proposal_fields", "affected_locks must be an array of non-empty strings")
    status = proposal.get("status")
    if status not in {"pending_user", "approved", "rejected", "superseded"}:
        _proposal_block(findings, "change_proposal_status", "status is invalid")
    if status == "approved":
        if proposal.get("approved_by") != "user":
            _proposal_block(findings, "change_proposal_approval", "approved_by must be user")
        if not isinstance(proposal.get("approved_revision"), int) or isinstance(proposal.get("approved_revision"), bool) or proposal.get("approved_revision") <= 0:
            _proposal_block(findings, "change_proposal_approval", "approved_revision must be a positive integer")
        if not isinstance(proposal.get("approved_at"), str) or not proposal.get("approved_at").strip():
            _proposal_block(findings, "change_proposal_approval", "approved_at is required for approved proposals")
    return _proposal_result(findings, "change_proposal_valid", "ChangeProposal is valid")


def _proposal_result(findings: list[dict], ok_code: str, ok_message: str) -> dict:
    blockers = [item for item in findings if item.get("severity") == "blocker"]
    if not blockers:
        findings.append({"severity": "info", "code": ok_code, "message": ok_message})
    return {"ok": not blockers, "findings": findings}


def _proposal_block(findings: list[dict], code: str, message: str) -> None:
    findings.append({"severity": "blocker", "code": code, "message": message})


def register(registry):
    """Register only when the CRCP DLC loader has passed its capability gate."""
    def validate_shot_control_bundle(params: dict) -> dict:
        try:
            bundle = _json_object(_param(params, "bundle", "content"), "bundle")
            result = _validate_shot_control_bundle(
                bundle,
                registry._workspace_root,
                check_files=bool(params.get("check_files", False)),
            )
            return {"ok": result["ok"], "validation_ok": result["ok"], "report": result, "content": json.dumps(result, ensure_ascii=False, indent=2)}
        except Exception as exc:
            return {"ok": False, "validation_ok": False, "error": f"shot control bundle validation failed: {exc}"}

    def validate_creative_spec(params: dict) -> dict:
        try:
            spec = _json_object(_param(params, "spec", "content"), "spec")
            result = _validate_creative_spec(spec, deliverable=params.get("deliverable", True) is not False)
            return {"ok": result["ok"], "validation_ok": result["ok"], "report": result, "content": json.dumps(result, ensure_ascii=False, indent=2)}
        except Exception as exc:
            return {"ok": False, "validation_ok": False, "error": f"creative spec validation failed: {exc}"}

    def validate_change_proposal(params: dict) -> dict:
        try:
            proposal = _json_object(_param(params, "proposal", "content"), "proposal")
            result = _validate_change_proposal(proposal)
            return {"ok": result["ok"], "validation_ok": result["ok"], "report": result, "content": json.dumps(result, ensure_ascii=False, indent=2)}
        except Exception as exc:
            return {"ok": False, "validation_ok": False, "error": f"change proposal validation failed: {exc}"}

    registry._registry["media"].update({
        "validate_shot_control_bundle": validate_shot_control_bundle,
        "validate_creative_spec": validate_creative_spec,
        "validate_change_proposal": validate_change_proposal,
    })
