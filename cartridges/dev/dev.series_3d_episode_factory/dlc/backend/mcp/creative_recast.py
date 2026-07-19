"""Opt-in CF-CRCP validation and two-stage execution tools."""

from __future__ import annotations

import json

from ..adapters.comfy_vace import run_vace_character_replace as _run_vace_character_replace

from ..protocol.creative_recast import (
    validate_candidate_review as _validate_candidate_review,
    validate_cast_pack as _validate_cast_pack,
    validate_creative_spec as _validate_creative_spec,
    validate_run_snapshot as _validate_run_snapshot,
    validate_shot_control_bundle as _validate_shot_control_bundle,
)
from ..protocol.creative_recast_runtime import (
    transition_crcp_run,
)


DLC_ID = "dlc.series_3d_episode_factory"
DLC_PROTOCOL = "CF-CRCP@0.1"
TOOLS = [
    "validate_cast_pack",
    "validate_candidate_review",
    "validate_shot_control_bundle",
    "validate_creative_spec",
    "validate_change_proposal",
    "run_vace_character_replace",
    "run_creative_recast",
]


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
        return _proposal_invalid(findings, "change_proposal_invalid", "ChangeProposal must be an object")
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


def _proposal_invalid(findings: list[dict], code: str, message: str) -> dict:
    _proposal_block(findings, code, message)
    return _proposal_result(findings, code, message)


def _proposal_block(findings: list[dict], code: str, message: str) -> None:
    findings.append({"severity": "blocker", "code": code, "message": message})


def _failure_record(params: dict, label: str, result: dict, snapshot: dict) -> dict:
    files = result.get("files") or []
    output_location = result.get("path") or (files[0] if files else "unknown")
    return {
        "schema": "cartridgeflow.failure_record.v1",
        "failure_id": str(params.get("failure_id") or f"failure-{params.get('run_id') or 'creative-recast'}"),
        "shot_id": str(params.get("shot_id") or "shot_unknown"),
        "run_revision": snapshot.get("revision", 1),
        "label": label,
        "user_feedback": str(params.get("user_feedback") or "Provider execution failed; review the recorded error."),
        "actual_change": str(result.get("error") or "Provider returned an unsuccessful result."),
        "output_location": str(output_location),
        "rollback_target": str(snapshot.get("snapshot_id") or "previous_approved_snapshot"),
        "retry_index": int(params.get("retry_index") or 0),
        "changed_fields": [str(item) for item in params.get("changed_fields") or [] if str(item).strip()],
        "recommendation": str(params.get("recommendation") or "Return to the approved snapshot before retrying."),
    }


def _run_creative_recast(registry, params: dict) -> dict:
    current_state = str(params.get("current_state") or "control_ready").strip()
    raw_spec = _json_object(_param(params, "creative_spec", "spec"), "creative_spec")
    raw_cast_pack = _json_object(params.get("cast_pack"), "cast_pack")
    raw_bundle = _json_object(_param(params, "shot_control_bundle", "bundle"), "shot_control_bundle")
    raw_snapshot = _json_object(_param(params, "run_snapshot", "snapshot"), "run_snapshot")
    spec_result = _validate_creative_spec(raw_spec)
    cast_pack_result = _validate_cast_pack(raw_cast_pack, registry._workspace_root, check_files=True, deliverable=True)
    bundle_result = _validate_shot_control_bundle(raw_bundle)
    snapshot_result = _validate_run_snapshot(raw_snapshot)
    if not spec_result.get("ok") or not cast_pack_result.get("ok") or not bundle_result.get("ok") or not snapshot_result.get("ok"):
        return {
            "ok": False,
            "state": current_state,
            "stage": "validation",
            "error": "CRCP artifacts failed validation",
            "creative_spec": spec_result,
            "cast_pack": cast_pack_result,
            "shot_control_bundle": bundle_result,
            "run_snapshot": snapshot_result,
        }

    context = {
        "approval": params.get("approval") or raw_spec.get("approval"),
        "creative_spec": spec_result,
        "shot_control_bundle": bundle_result,
        "run_snapshot": raw_snapshot,
    }
    events = []
    if current_state == "approved":
        ready = transition_crcp_run("approved", "control_ready", context)
        events.append(ready)
        if not ready.get("ok"):
            return {"ok": False, "state": current_state, "stage": "approval", "events": events, "findings": ready.get("findings") or []}
        current_state = "control_ready"
    if current_state != "control_ready":
        return {
            "ok": False,
            "state": current_state,
            "stage": "state",
            "error": "run_creative_recast must start from approved or control_ready",
        }

    start = transition_crcp_run("control_ready", "running_blender", context)
    events.append(start)
    if not start.get("ok"):
        return {"ok": False, "state": current_state, "stage": "running_blender", "events": events, "findings": start.get("findings") or []}

    blender_params = dict(params.get("blender_params") or {})
    blender_params["render_control_passes"] = True
    blender_result = registry.call("media", "forge_3d_series_episode", blender_params)
    if not blender_result.get("ok"):
        failure = _failure_record(params, "control_bundle_invalid", blender_result, raw_snapshot)
        rejected = transition_crcp_run("running_blender", "rejected", {"failure_record": failure})
        events.append(rejected)
        return {"ok": False, "state": "rejected", "stage": "running_blender", "events": events, "blender_result": blender_result, "failure_record": failure}

    actual_bundle = blender_result.get("control_bundle")
    actual_bundle_validation = _validate_shot_control_bundle(
        actual_bundle,
        registry._workspace_root,
        check_files=bool(blender_result.get("control_bundle_path")),
    )
    if not actual_bundle_validation.get("ok"):
        failed_result = {
            "ok": False,
            "error": "Blender output did not include a valid CRCP control bundle",
            "control_bundle_validation": actual_bundle_validation,
            "path": blender_result.get("control_bundle_path") or blender_result.get("path") or "",
            "files": blender_result.get("files") or [],
        }
        failure = _failure_record(params, "control_bundle_invalid", failed_result, raw_snapshot)
        rejected = transition_crcp_run("running_blender", "rejected", {"failure_record": failure})
        events.append(rejected)
        return {
            "ok": False,
            "state": "rejected",
            "stage": "control_bundle_validation",
            "events": events,
            "blender_result": blender_result,
            "control_bundle_validation": actual_bundle_validation,
            "failure_record": failure,
        }

    comfy_start = transition_crcp_run("running_blender", "running_comfy", {"blender_ok": True})
    events.append(comfy_start)
    if not comfy_start.get("ok"):
        return {"ok": False, "state": "running_blender", "stage": "running_comfy", "events": events, "blender_result": blender_result, "findings": comfy_start.get("findings") or []}

    comfy_params = dict(params.get("comfy_params") or {})
    comfy_params["control_bundle"] = actual_bundle
    comfy_params["control_bundle_path"] = blender_result.get("control_bundle_path") or ""
    comfy_params["creative_spec"] = raw_spec
    comfy_params["cast_pack"] = raw_cast_pack
    comfy_params["run_snapshot"] = raw_snapshot
    comfy_result = registry.call("media", "run_vace_character_replace", comfy_params)
    if not comfy_result.get("ok"):
        failure = _failure_record(params, "style_mismatch", comfy_result, raw_snapshot)
        rejected = transition_crcp_run("running_comfy", "rejected", {"failure_record": failure})
        events.append(rejected)
        return {"ok": False, "state": "rejected", "stage": "running_comfy", "events": events, "blender_result": blender_result, "comfy_result": comfy_result, "failure_record": failure}

    outputs = comfy_result.get("files") or [item for item in [comfy_result.get("path")] if item]
    review = transition_crcp_run("running_comfy", "review_required", {"outputs": outputs})
    events.append(review)
    return {
        "ok": bool(review.get("ok")),
        "state": "review_required" if review.get("ok") else "running_comfy",
        "stage": "review_required",
        "requires_user_review": bool(review.get("ok")),
        "events": events,
        "blender_result": blender_result,
        "control_bundle_validation": actual_bundle_validation,
        "comfy_result": comfy_result,
        "outputs": outputs,
        "findings": review.get("findings") or [],
    }


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

    def validate_cast_pack(params: dict) -> dict:
        try:
            pack = _json_object(_param(params, "cast_pack", "content"), "cast_pack")
            result = _validate_cast_pack(
                pack,
                registry._workspace_root,
                check_files=bool(params.get("check_files", False)),
                deliverable=params.get("deliverable", True) is not False,
            )
            return {"ok": result["ok"], "validation_ok": result["ok"], "report": result, "content": json.dumps(result, ensure_ascii=False, indent=2)}
        except Exception as exc:
            return {"ok": False, "validation_ok": False, "error": f"cast pack validation failed: {exc}"}

    def validate_candidate_review(params: dict) -> dict:
        try:
            review = _json_object(_param(params, "candidate_review", "content"), "candidate_review")
            result = _validate_candidate_review(
                review,
                registry._workspace_root,
                check_files=bool(params.get("check_files", False)),
                deliverable=params.get("deliverable", True) is not False,
            )
            return {"ok": result["ok"], "validation_ok": result["ok"], "report": result, "content": json.dumps(result, ensure_ascii=False, indent=2)}
        except Exception as exc:
            return {"ok": False, "validation_ok": False, "error": f"candidate review validation failed: {exc}"}

    def validate_change_proposal(params: dict) -> dict:
        try:
            proposal = _json_object(_param(params, "proposal", "content"), "proposal")
            result = _validate_change_proposal(proposal)
            return {"ok": result["ok"], "validation_ok": result["ok"], "report": result, "content": json.dumps(result, ensure_ascii=False, indent=2)}
        except Exception as exc:
            return {"ok": False, "validation_ok": False, "error": f"change proposal validation failed: {exc}"}

    def run_creative_recast(params: dict) -> dict:
        try:
            return _run_creative_recast(registry, params)
        except Exception as exc:
            return {"ok": False, "state": str(params.get("current_state") or "control_ready"), "stage": "runtime", "error": f"creative recast run failed: {exc}"}

    def run_vace_character_replace(params: dict) -> dict:
        return _run_vace_character_replace(registry, params)

    registry._registry["media"].update({
        "validate_cast_pack": validate_cast_pack,
        "validate_candidate_review": validate_candidate_review,
        "validate_shot_control_bundle": validate_shot_control_bundle,
        "validate_creative_spec": validate_creative_spec,
        "validate_change_proposal": validate_change_proposal,
        "run_vace_character_replace": run_vace_character_replace,
        "run_creative_recast": run_creative_recast,
    })
